import base64
import re
from collections import defaultdict
from dataclasses import dataclass, field
from io import BytesIO
from typing import Optional, List
from pydantic import BaseModel, Field


from docling_core.types.doc import BoundingBox
from docling.chunking import HierarchicalChunker
from docling.datamodel.document import ConversionResult
from docling_core.types.doc import DoclingDocument


@dataclass(frozen=True, kw_only=True)
class ImageBoundingBox:
    """
    A set of bounding box coordinates meant to represent a subregion within a rendered page.
    Serves as a normalized conversion from Docling's BoundingBox.
    """
    x1: float
    y1: float
    x2: float
    y2: float

    @staticmethod
    def from_docling_bbox(
        bbox: BoundingBox, 
        page_height: float,
        scale: float
    ) -> "ImageBoundingBox":
        """
        Converts a Docling Bounding Box to an ImageBoundingBox.
        """
        return ImageBoundingBox(
            x1 = round(bbox.l * scale),
            y1 = round((page_height - bbox.t) * scale),
            x2 = round(bbox.r * scale),
            y2 = round((page_height - bbox.b) * scale)
        )

@dataclass
class ElementRef:
    """
    A text-based document element with its Docling-sourced bbox.
    Coordinates are in rendered page image space (top-left origin, pixels).
    The bbox comes from Docling's PDF parser — it is not model-predicted.
    """
    element_id: str             
    label: str                  
    page_number: int            
    bbox_image_px: ImageBoundingBox
    bbox_pdf: BoundingBox       
    text_excerpt: str           


@dataclass
class FigureRef:
    """
    A picture element with its page-level bbox and cropped image.
    The crop is what gets sent to the model as an image_url part.
    Sub-element bboxes within the crop are model-predicted at inference time.
    """
    figure_id: str              
    page_number: int
    bbox_image_px: list[float]  
    bbox_pdf: BoundingBox       
    base64_png: str             


class LocalFinding(BaseModel):
    element_id: Optional[str] = Field(None, description="The unique identifier of the vulnerable element (from the structured text ID tags).")
    figure_id: Optional[str] = Field(None, description="The unique identifier of the figure (if the vulnerability is in a figure).")
    sub_bbox: Optional[List[float]] = Field(None, description="A bounding box within the figure crop space [x1, y1, x2, y2] (0-1000 scale).")
    element_type: str = Field(..., description="The type of the element, e.g. section_heading, paragraph, diagram_node, diagram_edge, table_cell, table_header, caption, code_block, list_item.")
    finding: str = Field(..., description="Description of the vulnerability finding.")
    standard_ref: str = Field(..., description="Security standard reference cited for this vulnerability finding.")
    severity: str = Field(..., description="Severity classification (critical, high, medium, low, observation).")
    confidence: float = Field(..., description="Confidence score between 0.0 and 1.0.")
    title: Optional[str] = Field(None, description="An optional short, descriptive title for the finding.")
    web_references: Optional[List[str]] = Field(default_factory=list, description="Optional list of web reference URLs.")
    recommendations: Optional[List[str]] = Field(default_factory=list, description="Optional list of recommendation strings.")



@dataclass
class EvaluationChunk:
    """
    One semantic unit of the document, produced by HierarchicalChunker.
    Carries both structured text (with [ID:...] annotations) and any
    figure crops that are referenced within this section.
    """
    chunk_id: str
    heading: str
    page_range: tuple[int, int]
    structured_text: str # text for the model
    element_refs: list[ElementRef] = field(default_factory=list)
    figures: list[FigureRef] = field(default_factory=list)


def _build_element_lookup(
    doc: DoclingDocument,
    scale: float
) -> dict[str, ElementRef]:
    """
    Iterates every item in the DoclingDocument and builds a dict keyed by
    self_ref. Pictures are excluded — they go into the figure lookup.
    Tables use their markdown export as the text excerpt so the model
    sees structured table content rather than a raw string.
    """
    lookup: dict[str, ElementRef] = {}
    _last_table_header: str | None = None

    for item, _level in doc.iterate_items():
        if not hasattr(item, "prov") or not item.prov:
            continue

        label = (
            item.label.value
            if hasattr(item.label, "value")
            else str(item.label)
        )

        # Skip decorative page elements (headers, footers)
        if label in ("picture", "page_header", "page_footer"):
            continue

        prov = item.prov[0]
        page = doc.pages.get(prov.page_no)
        if page is None or page.size is None:
            continue

        bbox_px = ImageBoundingBox.from_docling_bbox(prov.bbox, page.size.height, scale)

        if label == "table" and hasattr(item, "export_to_markdown"):
            text = item.export_to_markdown()
            lines = text.strip().split('\n')

            # Detect if this table has a header separator (e.g. |---|---|)
            sep_idx: int | None = None
            for i, line in enumerate(lines[:4]):
                if re.match(r'^\s*\|([\s:-]+\|)+\s*$', line):
                    sep_idx = i
                    break

            if sep_idx is not None and sep_idx >= 1:
                # Store header rows + separator for continuation tables
                _last_table_header = '\n'.join(lines[:sep_idx + 1])
            elif sep_idx is None and _last_table_header:
                # Continuation table without headers: prepend last seen header
                text = _last_table_header + '\n' + text

        elif hasattr(item, "text") and item.text:
            text = item.text
        elif hasattr(item, "export_to_markdown"):
            text = item.export_to_markdown()
        else:
            text = ""

        lookup[item.self_ref] = ElementRef(
            element_id=item.self_ref,
            label=label,
            page_number=prov.page_no,
            bbox_image_px=bbox_px,
            bbox_pdf=prov.bbox,
            text_excerpt=text
        )

    return lookup


def _build_figure_lookup(
    doc: DoclingDocument,
    result: ConversionResult,
    scale: float
) -> dict[str, FigureRef]:
    """
    Iterates doc.pictures, extracts each crop via picture.get_image(),
    and converts the page-level bbox to image coordinates.
    If a crop fails to render, base64_png is set to "" and the figure
    is excluded from the chunk's figures list downstream.
    """
    lookup: dict[str, FigureRef] = {}

    for picture in doc.pictures:
        if not picture.prov:
            continue

        prov = picture.prov[0]
        page = doc.pages.get(prov.page_no)
        if page is None or page.size is None:
            continue

        bbox_px = ImageBoundingBox.from_docling_bbox(prov.bbox, page.size.height, scale)

        try:
            img = picture.get_image(result)
            buf = BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.standard_b64encode(buf.getvalue()).decode()
        except Exception:
            b64 = ""

        lookup[picture.self_ref] = FigureRef(
            figure_id=picture.self_ref,
            page_number=prov.page_no,
            bbox_image_px=bbox_px,
            bbox_pdf=prov.bbox,
            base64_png=b64
        )

    return lookup


def _attach_captions(doc: DoclingDocument, figures: list[dict]) -> None:
    """
    Captions are separate DocItemLabel.CAPTION elements in Docling's output —
    they are not properties of the picture item itself. This function matches
    each caption to the nearest figure on the same page by measuring the
    vertical distance between the bottom of the figure and the top of the
    caption (PDF coordinate space). The closest figure above the caption wins.
    """
    for item, _level in doc.iterate_items():
        label = (
            item.label.value
            if hasattr(item.label, "value")
            else str(item.label)
        )
        if label != "caption":
            continue
        if not hasattr(item, "prov") or not item.prov:
            continue

        caption_prov = item.prov[0]
        caption_page = caption_prov.page_no
        caption_top = caption_prov.bbox.t  # top of caption in PDF space

        best_fig: dict | None = None
        best_dist = float("inf")

        for fig in figures:
            if fig["page"] != caption_page:
                continue
            for pic in doc.pictures:
                if pic.self_ref != fig["id"] or not pic.prov:
                    continue
                fig_bottom = pic.prov[0].bbox.b  # bottom of figure in PDF space
                dist = caption_top - fig_bottom  # positive = caption below figure
                if 0 < dist < best_dist:
                    best_dist = dist
                    best_fig = fig

        if best_fig is not None:
            best_fig["caption"] = getattr(item, "text", None)


def _find_page_gaps(doc: DoclingDocument) -> list[dict]:
    """
    Identifies pages that contain no section heading. These are flagged in
    the document index so Pass 1 agents can reason about missing sections.
    Contiguous ungrouped pages are reported as a single gap entry.
    """
    section_pages: set[int] = set()

    for item, _level in doc.iterate_items():
        label = (
            item.label.value
            if hasattr(item.label, "value")
            else str(item.label)
        )
        if label == "section_heading" and hasattr(item, "prov") and item.prov:
            section_pages.add(item.prov[0].page_no)

    all_pages = sorted(doc.pages.keys())
    unassigned = [p for p in all_pages if p not in section_pages]

    if not unassigned:
        return []

    gaps: list[dict] = []
    start = unassigned[0]
    prev = unassigned[0]

    for page in unassigned[1:]:
        if page != prev + 1:
            gaps.append({"pages": list(range(start, prev + 1))})
            start = page
        prev = page

    gaps.append({"pages": list(range(start, prev + 1))})
    return gaps


def merge_chunks(raw_chunks: list[EvaluationChunk], max_chars: int = 4000) -> list[EvaluationChunk]:
    merged_chunks: list[EvaluationChunk] = []
    if not raw_chunks:
        return merged_chunks

    import copy
    current_chunk = copy.copy(raw_chunks[0])
    current_chunk.element_refs = list(current_chunk.element_refs)
    current_chunk.figures = list(current_chunk.figures)

    for next_chunk in raw_chunks[1:]:
        same_section = current_chunk.heading == next_chunk.heading
        len_combined = len(current_chunk.structured_text) + len(next_chunk.structured_text)
        
        if same_section and len_combined <= max_chars:
            current_chunk.structured_text = (
                current_chunk.structured_text + "\n\n" + next_chunk.structured_text
            ).strip()
            current_chunk.element_refs.extend(next_chunk.element_refs)
            
            seen_figs = {f.figure_id for f in current_chunk.figures}
            for fig in next_chunk.figures:
                if fig.figure_id not in seen_figs:
                    current_chunk.figures.append(fig)
            
            min_page = min(current_chunk.page_range[0], next_chunk.page_range[0])
            max_page = max(current_chunk.page_range[1], next_chunk.page_range[1])
            current_chunk.page_range = (min_page, max_page)
        else:
            merged_chunks.append(current_chunk)
            current_chunk = copy.copy(next_chunk)
            current_chunk.element_refs = list(current_chunk.element_refs)
            current_chunk.figures = list(current_chunk.figures)

    merged_chunks.append(current_chunk)
    
    for idx, c in enumerate(merged_chunks):
        c.chunk_id = f"chunk_{idx}"
        
    return merged_chunks


def build_chunks(
    doc: DoclingDocument,
    result: ConversionResult,
    chunker: HierarchicalChunker,
    scale: float = 2.0
) -> list[EvaluationChunk]:
    """
    Runs HierarchicalChunker over the DoclingDocument and converts each
    DocChunk into an EvaluationChunk. The structured_text field annotates
    every element with its [ID:ref|label|page] tag so the model can
    reference it by ID in its findings output. Figure crops are collected
    separately and attached to the chunk they appear in.
    """
    element_lookup = _build_element_lookup(doc, scale)
    figure_lookup = _build_figure_lookup(doc, result, scale)

    chunks: list[EvaluationChunk] = []

    for i, chunk in enumerate(chunker.chunk(doc)):
        text_lines: list[str] = []
        chunk_elements: list[ElementRef] = []
        chunk_figures: list[FigureRef] = []

        for item in chunk.meta.doc_items:
            ref_id = item.self_ref

            elem = element_lookup.get(ref_id)
            if elem is not None:
                chunk_elements.append(elem)
                text_lines.append(
                    f"[ID:{ref_id}|{elem.label}|p{elem.page_number}]"
                )
                text_lines.append(elem.text_excerpt)
                text_lines.append("")

            fig = figure_lookup.get(ref_id)
            if fig is not None and fig.base64_png:
                chunk_figures.append(fig)

        all_pages = (
            {e.page_number for e in chunk_elements}
            | {f.page_number for f in chunk_figures}
        )
        page_range = (min(all_pages), max(all_pages)) if all_pages else (0, 0)
        heading = (chunk.meta.headings or [f"Section {i + 1}"])[0]

        chunks.append(EvaluationChunk(
            chunk_id=f"chunk_{i}",
            heading=heading,
            page_range=page_range,
            structured_text="\n".join(text_lines).strip(),
            element_refs=chunk_elements,
            figures=chunk_figures
        ))

    merged = merge_chunks(chunks)
    _attach_figures_by_page(merged, figure_lookup)
    _propagate_section_figures(merged)
    return merged


def _attach_figures_by_page(
    chunks: list[EvaluationChunk],
    figure_lookup: dict[str, FigureRef]
) -> None:
    """
    Assigns figures to chunks by page proximity.

    HierarchicalChunker is text-based and typically doesn't include
    picture items in chunk.meta.doc_items, so the ref_id match in
    build_chunks never fires. This function assigns each unattached
    figure to the chunk whose page range contains the figure's page,
    falling back to the nearest chunk by page distance.
    """
    attached_ids: set[str] = set()
    for chunk in chunks:
        attached_ids.update(f.figure_id for f in chunk.figures)

    for fig in figure_lookup.values():
        if not fig.base64_png or fig.figure_id in attached_ids:
            continue

        # Prefer a chunk whose page range includes the figure's page
        best_chunk: EvaluationChunk | None = None
        best_dist = float('inf')

        for chunk in chunks:
            if chunk.page_range[0] <= fig.page_number <= chunk.page_range[1]:
                best_chunk = chunk
                break
            dist = min(
                abs(fig.page_number - chunk.page_range[0]),
                abs(fig.page_number - chunk.page_range[1])
            )
            if dist < best_dist:
                best_dist = dist
                best_chunk = chunk

        if best_chunk is not None:
            best_chunk.figures.append(fig)


def _propagate_section_figures(chunks: list[EvaluationChunk]) -> None:
    """
    Ensures every chunk of a multi-chunk section can see ALL figures
    from that section. Without this, a table on page 7 that references
    diagrams on pages 8-9 (same section, different chunk due to size
    limits) would cause false 'missing diagram' findings.
    """
    heading_groups: dict[str, list[int]] = defaultdict(list)
    for i, chunk in enumerate(chunks):
        heading_groups[chunk.heading].append(i)

    for _heading, indices in heading_groups.items():
        if len(indices) <= 1:
            continue

        # Collect all unique figures from every chunk in this section
        all_figures: list[FigureRef] = []
        seen_ids: set[str] = set()
        for idx in indices:
            for fig in chunks[idx].figures:
                if fig.figure_id not in seen_ids:
                    all_figures.append(fig)
                    seen_ids.add(fig.figure_id)

        # Distribute to every chunk so the agent always sees them
        for idx in indices:
            chunks[idx].figures = list(all_figures)


def build_document_index(doc: DoclingDocument) -> dict:
    """
    Builds a lightweight structural map of the document directly from
    Docling's parsed output — no model call required. This is what was
    previously Pass 1 in the three-pass design; Docling makes it free.

    The page_gaps list flags ranges of pages with no section heading,
    which signals to Pass 1 agents that a required section may be absent.
    """
    sections: list[dict] = []
    figures: list[dict] = []
    tables: list[dict] = []

    for item, _level in doc.iterate_items():
        if not hasattr(item, "prov") or not item.prov:
            continue

        label = (
            item.label.value
            if hasattr(item.label, "value")
            else str(item.label)
        )
        prov = item.prov[0]

        if label == "section_heading":
            sections.append({
                "id": item.self_ref,
                "title": getattr(item, "text", ""),
                "page": prov.page_no
            })
        elif label == "picture":
            figures.append({
                "id": item.self_ref,
                "page": prov.page_no,
                "caption": None  # filled by _attach_captions
            })
        elif label == "table":
            tables.append({
                "id": item.self_ref,
                "page": prov.page_no
            })

    _attach_captions(doc, figures)

    return {
        "sections": sections,
        "figures": figures,
        "tables": tables,
        "page_gaps": _find_page_gaps(doc)
    }
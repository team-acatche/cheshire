import base64
from dataclasses import dataclass, field
from io import BytesIO
from typing import Optional, List
from pydantic import BaseModel, Field


from docling_core.types.doc import BoundingBox
from docling.chunking import HierarchicalChunker
from docling.datamodel.document import ConversionResult
from docling_core.types.doc import DoclingDocument


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
    bbox_image_px: list[float]  
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


def _to_image_px(
    bbox: BoundingBox, 
    page_height: float,
    scale: float
) -> list[float]:
    """
    Docling stores bboxes in PDF coordinate space:
      - origin at bottom-left
      - Y increases upward
      - units in points

    Rendered page images use image coordinate space:
      - origin at top-left
      - Y increases downward
      - units in pixels

    bbox.t is the top edge in PDF space (larger Y value).
    Subtracting from page_height flips the axis, then multiply by scale.
    """
    x1 = round(bbox.l * scale)
    y1 = round((page_height - bbox.t) * scale)
    x2 = round(bbox.r * scale)
    y2 = round((page_height - bbox.b) * scale)
    return [x1, y1, x2, y2]


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

    for item, _level in doc.iterate_items():
        if not hasattr(item, "prov") or not item.prov:
            continue

        label = (
            item.label.value
            if hasattr(item.label, "value")
            else str(item.label)
        )

        if label == "picture":
            continue  # handled in _build_figure_lookup

        prov = item.prov[0]
        page = doc.pages.get(prov.page_no)
        if page is None or page.size is None:
            continue

        bbox_px = _to_image_px(prov.bbox, page.size.height, scale)

        if hasattr(item, "text") and item.text:
            text = item.text[:120]
        elif hasattr(item, "export_to_markdown"):
            text = item.export_to_markdown()[:120]
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

        bbox_px = _to_image_px(prov.bbox, page.size.height, scale)

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

    return chunks


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
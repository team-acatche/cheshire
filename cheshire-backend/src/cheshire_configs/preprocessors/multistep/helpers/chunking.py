"""
Hierarchical document chunking, section hierarchy detection, chunk merging,
and visual figure attachment.
"""

from collections import defaultdict
import copy
import re

from docling.datamodel.document import ConversionResult
from docling_core.transforms.chunker.hierarchical_chunker import HierarchicalChunker
from docling_core.types.doc import DoclingDocument

from .constants import DEFAULT_IMAGE_SCALE, DEFAULT_MAX_CHUNK_CHARS
from .elements import _build_element_lookup, _build_figure_lookup
from .hierarchy import HeaderHierarchyResolver, parse_header_token
from .models import ElementRef, EvaluationChunk, FigureRef


def _extract_section_key(heading: str) -> str | None:
    # extracts the major section identifier using the hierarchy token parser
    h: str = heading.strip()
    if not h:
        return None
    tok = parse_header_token(h)
    if tok.root_key:
        return tok.root_key
    m = re.match(r"^([A-Za-z]|\d+)\b(?:\.|\s|$)", h)
    if m:
        return m.group(1)
    m2 = re.match(r"^section\s+([A-Za-z]|\d+)\b", h, re.IGNORECASE)
    if m2:
        return m2.group(1)
    return None


def _merge_chunk_pair(
    current_chunk: EvaluationChunk,
    next_chunk: EvaluationChunk,
    current_key: str | None,
) -> None:
    # merges next_chunk into current_chunk in-place.
    # concatenates text, combines element refs, deduplicates figures, and updates page range.
    if current_key is not None and current_chunk.heading != next_chunk.heading:
        # if chunks have breadcrumbs under a common parent section, preserve the parent heading
        if " - " in current_chunk.heading:
            parent_heading: str = current_chunk.heading.split(" - ")[0].strip()
            current_chunk.heading = parent_heading
        else:
            # if current heading is a parent heading (e.g. "f. system considerations"), preserve it.
            is_parent: bool = bool(re.match(rf"^{current_key}\.\s+[A-Za-z]", current_chunk.heading, re.IGNORECASE))
            if not is_parent:
                current_chunk.heading = f"Section {current_key} Subsections"

    current_chunk.structured_text = (
        current_chunk.structured_text + "\n\n" + next_chunk.structured_text
    ).strip()
    current_chunk.element_refs.extend(next_chunk.element_refs)

    seen_figs: set[str] = {f.figure_id for f in current_chunk.figures}
    for fig in next_chunk.figures:
        if fig.figure_id not in seen_figs:
            current_chunk.figures.append(fig)
            seen_figs.add(fig.figure_id)

    min_page: int = min(current_chunk.page_range[0], next_chunk.page_range[0])
    max_page: int = max(current_chunk.page_range[1], next_chunk.page_range[1])
    current_chunk.page_range = (min_page, max_page)


def merge_chunks(
    raw_chunks: list[EvaluationChunk],
    max_chars: int = DEFAULT_MAX_CHUNK_CHARS,
) -> list[EvaluationChunk]:
    """
    Merges contiguous chunks that share the same major section identifier
    provided their combined text length does not exceed max_chars.
    """
    if not raw_chunks:
        return []

    merged_chunks: list[EvaluationChunk] = []
    current_chunk: EvaluationChunk = copy.copy(raw_chunks[0])
    current_chunk.element_refs = list(current_chunk.element_refs)
    current_chunk.figures = list(current_chunk.figures)
    current_key: str | None = _extract_section_key(current_chunk.heading)

    for next_chunk in raw_chunks[1:]:
        next_key: str | None = _extract_section_key(next_chunk.heading)

        same_section: bool = (
            current_chunk.heading == next_chunk.heading or
            (current_key is not None and next_key is not None and current_key == next_key)
        )
        len_combined: int = len(current_chunk.structured_text) + len(next_chunk.structured_text)

        if same_section and len_combined <= max_chars:
            _merge_chunk_pair(current_chunk, next_chunk, current_key)
        else:
            merged_chunks.append(current_chunk)
            current_chunk = copy.copy(next_chunk)
            current_chunk.element_refs = list(current_chunk.element_refs)
            current_chunk.figures = list(current_chunk.figures)
            current_key = next_key

    merged_chunks.append(current_chunk)

    for idx, c in enumerate(merged_chunks):
        c.chunk_id = f"chunk_{idx}"

    return merged_chunks


def _attach_figures_by_page(
    chunks: list[EvaluationChunk],
    figure_lookup: dict[str, FigureRef],
) -> None:
    """
    Assigns figures to chunks by explicit text mention or page proximity.

    HierarchicalChunker is text-based and typically doesn't include
    picture items in chunk.meta.doc_items, so the ref_id match in
    build_chunks never fires. This function assigns each unattached
    figure to the chunk whose text references it, or whose page range
    contains the figure's page, falling back to nearest page distance.
    """
    attached_ids: set[str] = {
        figure.figure_id
        for chunk in chunks
        for figure in chunk.figures
    }

    for figure in figure_lookup.values():
        if not figure.base64_png or figure.figure_id in attached_ids:
            continue

        best_chunk: EvaluationChunk | None = None

        # 1. Prefer a chunk whose structured_text explicitly references this figure ID
        for chunk in chunks:
            if figure.figure_id in chunk.structured_text:
                best_chunk = chunk
                break

        # 2. If not explicitly referenced, find a chunk by page range proximity
        if best_chunk is None:
            best_dist: float = float('inf')
            for chunk in chunks:
                if chunk.page_range[0] <= figure.page_number <= chunk.page_range[1]:
                    best_chunk = chunk
                    break
                dist: float = min(
                    abs(figure.page_number - chunk.page_range[0]),
                    abs(figure.page_number - chunk.page_range[1]),
                )
                if dist < best_dist:
                    best_dist = dist
                    best_chunk = chunk

        if best_chunk is not None:
            best_chunk.figures.append(figure)
            attached_ids.add(figure.figure_id)


def _propagate_section_figures(chunks: list[EvaluationChunk]) -> None:
    """
    Ensures every chunk of a multi-chunk section can see ALL figures
    from that section. Without this, a table on page 7 that references
    diagrams on pages 8-9 (same section, different chunk due to size
    limits) would cause false 'missing diagram' findings.
    """
    heading_groups: dict[str, list[int]] = defaultdict(list)
    for i, chunk in enumerate(chunks):
        key: str = _extract_section_key(chunk.heading) or chunk.heading
        heading_groups[key].append(i)

    for _heading, indices in heading_groups.items():
        # Skip single chunk or empty sections
        if len(indices) <= 1:
            continue

        # Collect all unique figures from this multi-chunk section
        all_figures: list[FigureRef] = []
        seen_ids: set[str] = set()
        for idx in indices:
            for fig in chunks[idx].figures:
                if fig.figure_id not in seen_ids:
                    all_figures.append(fig)
                    seen_ids.add(fig.figure_id)

        # Distribute shared figures to every chunk in the section
        for idx in indices:
            chunks[idx].figures = list(all_figures)


def build_chunks(
    doc: DoclingDocument,
    result: ConversionResult,
    chunker: HierarchicalChunker,
    scale: float = DEFAULT_IMAGE_SCALE,
) -> list[EvaluationChunk]:
    """
    Runs HierarchicalChunker over the DoclingDocument and converts each
    DocChunk into an EvaluationChunk. The structured_text field annotates
    every element with its [ID:ref|label|page] tag so the model can
    reference it by ID in its findings output. Figure crops are collected
    separately and attached to the chunk they appear in.
    """
    figure_lookup: dict[str, FigureRef] = _build_figure_lookup(doc, result, scale)
    element_lookup: dict[str, ElementRef] = _build_element_lookup(doc, result, figure_lookup, scale)

    chunks: list[EvaluationChunk] = []
    hierarchy_resolver = HeaderHierarchyResolver()

    for i, chunk in enumerate(chunker.chunk(doc)):
        text_lines: list[str] = []
        chunk_elements: list[ElementRef] = []
        chunk_figures: list[FigureRef] = []

        for item in chunk.meta.doc_items:
            ref_id: str = item.self_ref

            elem: ElementRef | None = element_lookup.get(ref_id)
            if elem is not None:
                chunk_elements.append(elem)
                text_lines.append(f"[ID:{ref_id}|{elem.label}|p{elem.page_number}]")
                text_lines.append(elem.text_excerpt)
                text_lines.append("")  # forces an extra newline when joined

                # if this element was a table with an image crop, attach the crop figure directly
                table_fig_id: str = f"table_crop_{ref_id}"
                if table_fig_id in figure_lookup:
                    crop_fig: FigureRef = figure_lookup[table_fig_id]
                    if crop_fig.base64_png:
                        chunk_figures.append(crop_fig)

                continue

            fig: FigureRef | None = figure_lookup.get(ref_id)
            if fig is not None and fig.base64_png:
                chunk_figures.append(fig)

        all_pages: set[int] = (
            {e.page_number for e in chunk_elements}
            | {f.page_number for f in chunk_figures}
        )
        page_range: tuple[int, int] = (min(all_pages), max(all_pages)) if all_pages else (0, 0)
        
        # resolve hierarchical heading using active scope stack
        heading: str = f"Section {i + 1}"
        if chunk.meta.headings:
            for h in chunk.meta.headings:
                heading = hierarchy_resolver.process_heading(h)
        else:
            heading = f"Section {i + 1}"

        chunks.append(EvaluationChunk(
            chunk_id=f"chunk_{i}",
            heading=heading,
            page_range=page_range,
            structured_text="\n".join(text_lines).strip(),
            element_refs=chunk_elements,
            figures=chunk_figures,
        ))

    merged: list[EvaluationChunk] = merge_chunks(chunks)
    _attach_figures_by_page(merged, figure_lookup)
    _propagate_section_figures(merged)
    return merged

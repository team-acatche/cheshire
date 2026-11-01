"""
Hierarchical document chunking, section hierarchy detection, chunk merging,
and visual figure attachment.
"""

from collections import defaultdict
import copy
import re
from typing import Any

from docling.datamodel.document import ConversionResult
from docling_core.transforms.chunker.hierarchical_chunker import HierarchicalChunker
from docling_core.types.doc import DoclingDocument

from .constants import DEFAULT_IMAGE_SCALE, DEFAULT_MAX_CHUNK_CHARS
from .elements import _build_element_lookup, _build_figure_lookup, _get_item_label, promote_heuristic_headings
from .geometry import _to_topleft_dict
from .hierarchy import HeaderHierarchyResolver, _eval_single_line_heading, _extract_heading_from_text, _is_spurious_heading, _normalize_heading_text, parse_header_token
from .models import ElementRef, EvaluationChunk, FigureRef


def _extract_section_key(heading: str) -> str | None:
    # extracts the major section or compound subsection identifier using the hierarchy token parser
    h: str = heading.strip()
    if not h:
        return None
    if " - " in h:
        parts = h.split(" - ")
        keys: list[str] = []
        for part in parts:
            tok = parse_header_token(part.strip())
            if tok.is_unnumbered or not tok.segments:
                continue
            if len(tok.segments) > 1:
                keys.append("/".join(s.raw for s in tok.segments))
            else:
                k = tok.prefix_label or tok.root_key
                if k:
                    keys.append(k)
        if keys:
            return "/".join(keys)

    tok = parse_header_token(h)
    if tok.segments and len(tok.segments) > 1:
        return "/".join(s.raw for s in tok.segments)
    if not tok.is_unnumbered and tok.root_key:
        return tok.prefix_label or tok.root_key

    m2 = re.match(r"^section\s+([A-Za-z]|\d+)\b", h, re.IGNORECASE)
    if m2:
        return m2.group(1).upper()
    return None


def _merge_chunk_pair(
    current_chunk: EvaluationChunk,
    next_chunk: EvaluationChunk,
    current_key: str | None,
) -> None:
    # merges next_chunk into current_chunk in-place.
    # concatenates text, combines element refs, deduplicates figures, and updates page range.
    if current_key is not None and current_chunk.heading != next_chunk.heading:
        # preserve the longest common breadcrumb prefix between the two chunks
        parts_a = [p.strip() for p in current_chunk.heading.split(" - ")]
        parts_b = [p.strip() for p in next_chunk.heading.split(" - ")]
        common: list[str] = []
        for pa, pb in zip(parts_a, parts_b):
            if pa.lower() == pb.lower():
                common.append(pa)
            else:
                break
        if common:
            current_chunk.heading = " - ".join(common)
        elif " - " in current_chunk.heading:
            current_chunk.heading = current_chunk.heading.split(" - ")[0].strip()
        else:
            is_parent: bool = bool(re.match(rf"^{re.escape(current_key)}[\.\-–—:\s]+[A-Za-z]", current_chunk.heading, re.IGNORECASE))
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
                if chunk.page_range == (0, 0):
                    continue
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
    Ensures chunks that share the same subsection or explicitly reference
    diagrams from a companion subsection can see those figures, while preventing
    table crops and unrelated figures from flooding across the entire section.
    """
    # 1. Intra-subsection figure sharing: chunks sharing the exact same section key (e.g. continuation chunks)
    sub_groups: dict[str, list[int]] = defaultdict(list)
    for i, chunk in enumerate(chunks):
        key: str | None = _extract_section_key(chunk.heading)
        if key:
            sub_groups[key].append(i)

    for _key, indices in sub_groups.items():
        if len(indices) <= 1:
            continue
        shared_figs: list[FigureRef] = []
        seen_ids: set[str] = set()
        for idx in indices:
            for fig in chunks[idx].figures:
                if not fig.figure_id.startswith("table_crop_") and fig.figure_id not in seen_ids:
                    shared_figs.append(fig)
                    seen_ids.add(fig.figure_id)
        for idx in indices:
            for sf in shared_figs:
                if not any(f.figure_id == sf.figure_id for f in chunks[idx].figures):
                    chunks[idx].figures.append(sf)

    # 2. Cross-subsection propagation: if a chunk in major section E explicitly mentions
    # diagrams in another subsection (e.g. "See diagram in section 2"), propagate figures from that subsection
    major_groups: dict[str, list[int]] = defaultdict(list)
    for i, chunk in enumerate(chunks):
        key = _extract_section_key(chunk.heading)
        if key:
            major_groups[key.split("/")[0]].append(i)

    diag_mention_re = re.compile(r'\b(?:diagrams?|flowcharts?|figure|figures)\b', re.IGNORECASE)
    for _maj, indices in major_groups.items():
        if len(indices) <= 1:
            continue
        section_diagrams: list[FigureRef] = []
        seen_diag_ids: set[str] = set()
        for idx in indices:
            c = chunks[idx]
            if "diagram" in c.heading.lower():
                for fig in c.figures:
                    if not fig.figure_id.startswith("table_crop_") and fig.figure_id not in seen_diag_ids:
                        section_diagrams.append(fig)
                        seen_diag_ids.add(fig.figure_id)

        if not section_diagrams:
            continue

        for idx in indices:
            c = chunks[idx]
            if "diagram" in c.heading.lower():
                continue
            if diag_mention_re.search(c.structured_text):
                for df in section_diagrams:
                    if not any(f.figure_id == df.figure_id for f in c.figures):
                        c.figures.append(df)


def _find_horizontal_pair(elem: ElementRef, all_elems: list[ElementRef]) -> ElementRef | None:
    """
    Finds a horizontally aligned value element situated to the right of a label element
    on the same page, addressing multi-column reading order separation in forms and cover blocks.
    """
    txt = elem.text_excerpt.strip()
    if not (txt.endswith(":") or txt.endswith(":-") or (len(txt.split()) <= 4 and txt.endswith(":"))):
        return None
    bA = elem.bbox_pdf
    if not bA:
        return None
    hA = abs(bA.t - bA.b)
    best_cand: ElementRef | None = None
    min_dist = float("inf")
    for cand in all_elems:
        if cand.element_id == elem.element_id or cand.page_number != elem.page_number:
            continue
        bB = cand.bbox_pdf
        if not bB:
            continue
        # Candidate must sit horizontally to the right
        if bB.l < bA.l + 10.0:
            continue
        # Check vertical overlap (same row / line)
        y_ov = min(max(bA.t, bA.b), max(bB.t, bB.b)) - max(min(bA.t, bA.b), min(bB.t, bB.b))
        hB = abs(bB.t - bB.b)
        if y_ov > 0.35 * min(max(1.0, hA), max(1.0, hB)):
            dist = bB.l - bA.r
            if 0.0 <= dist < min_dist:
                min_dist = dist
                best_cand = cand
    return best_cand


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
    promote_heuristic_headings(doc)
    figure_lookup: dict[str, FigureRef] = _build_figure_lookup(doc, result, scale)
    element_lookup: dict[str, ElementRef] = _build_element_lookup(doc, result, figure_lookup, scale)

    # Collect all outline section headings in physical reading order
    section_headings: list[tuple[int, float, str, Any]] = []
    for it in getattr(doc, "texts", []) or []:
        if not hasattr(it, "prov") or not it.prov:
            continue
        p_no = it.prov[0].page_no
        lbl = _get_item_label(it)
        txt = getattr(it, "orig", "") or getattr(it, "text", "")
        h = _extract_heading_from_text(txt) or (_normalize_heading_text(txt) if lbl in ("section_header", "section_heading") else None)
        if h and not _is_spurious_heading(h):
            page = doc.pages.get(p_no) if hasattr(doc, "pages") and doc.pages else None
            p_h = getattr(getattr(page, "size", None), "height", 792.0) if page else 792.0
            tb = _to_topleft_dict(it.prov[0].bbox, p_h)
            section_headings.append((p_no, tb["t"], h, it))

    section_headings.sort(key=lambda x: (x[0], x[1]))

    chunks: list[EvaluationChunk] = []
    hierarchy_resolver = HeaderHierarchyResolver()
    heading_idx = 0

    def advance_headings(page: int, top: float) -> str | None:
        nonlocal heading_idx
        last_h = None
        while heading_idx < len(section_headings):
            h_p, h_t, h_txt, _ = section_headings[heading_idx]
            if (h_p, h_t) <= (page, top):
                if not hierarchy_resolver.is_stale_heading(h_txt):
                    last_h = hierarchy_resolver.process_heading(h_txt)
                heading_idx += 1
            else:
                break
        return last_h

    raw_doc_chunks = list(chunker.chunk(doc))

    def _chunk_sort_key(chk: Any) -> tuple[int, float]:
        min_p = 999999
        min_t = float("inf")
        has_items = False
        for it in getattr(chk.meta, "doc_items", []):
            if hasattr(it, "prov") and it.prov:
                p_no = getattr(it.prov[0], "page_no", 999999)
                bbox = getattr(it.prov[0], "bbox", None)
                t_val = 0.0
                if bbox:
                    page = doc.pages.get(p_no) if hasattr(doc, "pages") and doc.pages else None
                    p_h = getattr(getattr(page, "size", None), "height", 792.0) if page else 792.0
                    t_val = _to_topleft_dict(bbox, p_h)["t"]
                has_items = True
                if p_no < min_p:
                    min_p = p_no
                    min_t = t_val
                elif p_no == min_p:
                    if t_val < min_t:
                        min_t = t_val
        if not has_items or min_t == float("inf"):
            min_t = 0.0
        return (min_p, min_t)

    raw_doc_chunks.sort(key=_chunk_sort_key)

    for i, chunk in enumerate(raw_doc_chunks):
        chunk_all_elems = [element_lookup[it.self_ref] for it in chunk.meta.doc_items if it.self_ref in element_lookup]
        if not chunk_all_elems:
            continue

        chk_p, chk_t = _chunk_sort_key(chunk)
        advance_headings(chk_p, chk_t)

        sub_chunks: list[tuple[str, list[ElementRef], list[FigureRef], list[str]]] = []
        cur_elements: list[ElementRef] = []
        cur_figures: list[FigureRef] = []
        cur_lines: list[str] = []

        def flush_sub_chunk() -> None:
            nonlocal cur_elements, cur_figures, cur_lines, cur_heading
            if not cur_elements:
                return
            h = cur_heading or hierarchy_resolver.get_current_breadcrumb() or f"Section {len(chunks) + len(sub_chunks) + 1}"
            sub_chunks.append((h, cur_elements, cur_figures, cur_lines))
            cur_elements = []
            cur_figures = []
            cur_lines = []

        cur_heading = hierarchy_resolver.get_current_breadcrumb()
        if not cur_heading:
            clean_headings = [
                _normalize_heading_text(h) for h in (chunk.meta.headings or [])
                if _normalize_heading_text(h) and not _is_spurious_heading(_normalize_heading_text(h))
            ]
            if clean_headings and not any(hierarchy_resolver.is_stale_heading(h) for h in clean_headings):
                cur_heading = hierarchy_resolver.process_headings(clean_headings)

        for item in chunk.meta.doc_items:
            ref_id: str = item.self_ref

            elem: ElementRef | None = element_lookup.get(ref_id)
            if elem is not None:
                # Check if this element advances past a section heading in reading order
                if elem.bbox_pdf:
                    page = doc.pages.get(elem.page_number) if hasattr(doc, "pages") and doc.pages else None
                    p_h = getattr(getattr(page, "size", None), "height", 792.0) if page else 792.0
                    elem_t = _to_topleft_dict(elem.bbox_pdf, p_h)["t"]
                    adv_h = advance_headings(elem.page_number, elem_t)
                    if adv_h and cur_elements:
                        flush_sub_chunk()
                        cur_heading = adv_h

                cand: str | None = None
                if elem.label in ("section_header", "section_heading"):
                    cand = _extract_heading_from_text(elem.text_excerpt)
                    if not cand:
                        clean_elem = _normalize_heading_text(elem.text_excerpt)
                        if clean_elem and not _is_spurious_heading(clean_elem):
                            cand = clean_elem
                elif elem.label == "table":
                    first_line = elem.text_excerpt.strip().splitlines()[0] if elem.text_excerpt else ""
                    if first_line.startswith("|") and not first_line.startswith("|---"):
                        parts = [p.strip() for p in first_line.split("|")[1:-1] if p.strip()]
                        if len(parts) == 1:
                            banner_txt = _normalize_heading_text(parts[0])
                            if not _is_spurious_heading(banner_txt):
                                c_match = _extract_heading_from_text(banner_txt)
                                if c_match:
                                    cand = c_match
                                elif 2 <= len(banner_txt.split()) <= 12 and len(banner_txt) <= 100 and not banner_txt.endswith("."):
                                    cand = banner_txt
                else:
                    cand = _extract_heading_from_text(elem.text_excerpt)

                if cand and not _is_spurious_heading(cand) and not hierarchy_resolver.is_stale_heading(cand):
                    new_h = hierarchy_resolver.process_heading(cand)
                    # if accumulated content already exists, split chunk at this section header boundary
                    if cur_elements:
                        flush_sub_chunk()
                    cur_heading = new_h

                cur_elements.append(elem)
                cur_lines.append(f"[ID:{ref_id}|{elem.label}|p{elem.page_number}]")

                # Check if this element is a label ending with colon that has a horizontally aligned value
                elem_text = elem.text_excerpt
                h_val = _find_horizontal_pair(elem, chunk_all_elems)
                if h_val and h_val.text_excerpt.strip() and h_val.text_excerpt.strip() not in elem_text:
                    elem_text = f"{elem_text.strip()} {h_val.text_excerpt.strip()}"

                cur_lines.append(elem_text)
                cur_lines.append("")

                table_fig_id: str = f"table_crop_{ref_id}"
                if table_fig_id in figure_lookup:
                    crop_fig: FigureRef = figure_lookup[table_fig_id]
                    if crop_fig.base64_png:
                        cur_figures.append(crop_fig)
                continue

            fig: FigureRef | None = figure_lookup.get(ref_id)
            if fig is not None and fig.base64_png:
                cur_figures.append(fig)

        flush_sub_chunk()

        for h, elems, figs, lines in sub_chunks:
            all_pages: set[int] = {e.page_number for e in elems} | {f.page_number for f in figs}
            page_range: tuple[int, int] = (min(all_pages), max(all_pages)) if all_pages else (0, 0)
            chunks.append(EvaluationChunk(
                chunk_id=f"chunk_{len(chunks)}",
                heading=h,
                page_range=page_range,
                structured_text="\n".join(lines).strip(),
                element_refs=elems,
                figures=figs,
            ))

    advance_headings(999999, 999999.0)

    # Ensure unchunked figures or sections (e.g. standalone diagram pages or screenshot sections) form chunks
    covered_pages: set[int] = set()
    for c in chunks:
        if c.page_range != (0, 0):
            for p in range(c.page_range[0], c.page_range[1] + 1):
                covered_pages.add(p)

    for fig_id, fig in figure_lookup.items():
        if fig_id.startswith("table_crop_"):
            continue
        if fig.page_number not in covered_pages:
            matching_h: str | None = None
            for p, t, h, it in section_headings:
                if p <= fig.page_number:
                    matching_h = h
            h_str = matching_h or f"Section p{fig.page_number}"
            # Check if there is an unchunked text heading element on this page
            p_elems: list[ElementRef] = [
                e for e in element_lookup.values()
                if e.page_number == fig.page_number and e.label in ("section_header", "section_heading")
            ]
            p_lines: list[str] = []
            for pe in p_elems:
                p_lines.append(f"[ID:{pe.element_id}|{pe.label}|p{pe.page_number}]\n{pe.text_excerpt}")
            p_lines.append(f"[ID:{fig_id}|picture|p{fig.page_number}]")

            chunks.append(EvaluationChunk(
                chunk_id=f"chunk_{len(chunks)}",
                heading=h_str,
                page_range=(fig.page_number, fig.page_number),
                structured_text="\n\n".join(p_lines).strip(),
                element_refs=p_elems,
                figures=[fig],
            ))
            covered_pages.add(fig.page_number)

    chunks.sort(key=lambda c: (c.page_range[0], c.page_range[1]))
    for idx, c in enumerate(chunks):
        c.chunk_id = f"chunk_{idx}"

    merged: list[EvaluationChunk] = merge_chunks(chunks)
    _attach_figures_by_page(merged, figure_lookup)
    _propagate_section_figures(merged)
    return merged

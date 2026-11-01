"""
Geometric, spatial, and coordinate translation utilities for rendered PDF bounding boxes.
"""

import re
from typing import Any, Optional
from docling_core.types.doc import BoundingBox, CoordOrigin
from tools.helpers.output_schema import PageBoundingBox
from .models import TableCellRef


def _get_item_label(item: Any) -> str:
    """
    Extracts the string representation of an item's label across Docling versions.
    """
    return item.label.value if hasattr(item.label, "value") else str(item.label)


def _is_bottom_left(bbox: Any) -> bool:
    t = getattr(bbox, "t", None)
    b = getattr(bbox, "b", None)
    if t is not None and b is not None:
        if t > b:
            return True
        if t < b:
            origin = getattr(bbox, "coord_origin", None)
            if origin is not None:
                origin_str = getattr(origin, "value", str(origin)).upper()
                if "BOTTOM" in origin_str:
                    return True
            return False
    origin = getattr(bbox, "coord_origin", None)
    if origin is not None:
        origin_str = getattr(origin, "value", str(origin)).upper()
        if "BOTTOM" in origin_str:
            return True
    return False


def _to_topleft_dict(bbox: Any, page_h: float) -> dict[str, float]:
    """
    Converts a Docling BoundingBox or [l, t, r, b] to a top-left origin dictionary with keys 'l', 't', 'r', 'b'.
    Guarantees 't' <= 'b' and 'l' <= 'r' in top-left coordinate space.
    """
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        l, t, r, b = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
        return {"l": min(l, r), "t": min(t, b), "r": max(l, r), "b": max(t, b)}

    l = float(getattr(bbox, "l", 0.0))
    r = float(getattr(bbox, "r", 0.0))
    t = float(getattr(bbox, "t", 0.0))
    b = float(getattr(bbox, "b", 0.0))

    if _is_bottom_left(bbox):
        t_high = max(t, b)
        b_low = min(t, b)
        return {
            "l": min(l, r),
            "t": max(0.0, page_h - t_high),
            "r": max(l, r),
            "b": max(0.0, page_h - b_low),
        }

    return {
        "l": min(l, r),
        "t": min(t, b),
        "r": max(l, r),
        "b": max(t, b),
    }


def _compute_box_overlap(b1: dict[str, float], b2: dict[str, float]) -> tuple[float, float]:
    """
    Calculates the 2D spatial overlap (horizontal and vertical pixels) between two bounding boxes.
    Returns (x_overlap_px, y_overlap_px).
    """
    x_ov = max(0.0, min(b1["r"], b2["r"]) - max(b1["l"], b2["l"]))
    y_ov = max(0.0, min(b1["b"], b2["b"]) - max(b1["t"], b2["t"]))
    return x_ov, y_ov


def _snap_table_finding_bboxes(
    finding_text: str,
    title: str,
    table_cells: list[TableCellRef],
    raw_bboxes: list[PageBoundingBox],
    table_bbox: BoundingBox,
    page_number: int,
) -> list[PageBoundingBox]:
    """
    Snaps finding bounding boxes on tables to deterministic table cell and row geometry,
    preventing multimodal vision coordinate drift, column border bleeding, and row overflow.
    Prioritizes key title identifiers over incidental descriptive text, and supports
    multi-row/table-level highlights when findings affect multiple entries.
    """
    if not table_cells:
        return raw_bboxes or [PageBoundingBox(**table_bbox.model_dump(), page_no=page_number)]

    origin = getattr(table_bbox, "coord_origin", CoordOrigin.BOTTOMLEFT)
    raw_title = (title or "").strip()
    raw_body = (finding_text or "").strip()
    title_lower = raw_title.lower()
    body_lower = raw_body.lower()
    combined_lower = f"{title_lower} {body_lower}".strip()

    # Check if finding applies to table structure / entire table (e.g. lacks column headers, hardcoded paths across table)
    is_table_wide = bool(re.search(
        r'\b(lacks?\s+column\s+headers?|lacks?\s+headers?|missing\s+headers?|missing\s+column|no\s+column\s+headers?|entire\s+table|whole\s+table|all\s+rows|majority\s+of\s+the\s+table|table-wide)\b',
        combined_lower,
    ))
    if is_table_wide:
        return [PageBoundingBox(**table_bbox.model_dump(), page_no=page_number)]

    stop_words = {
        "the", "and", "for", "with", "this", "that", "from", "table", "report", "section",
        "missing", "empty", "contains", "specification", "specifications", "field", "fields",
        "value", "values", "row", "column", "cell", "does", "not", "have", "should", "must",
        "out", "commercial", "community", "support", "end", "life", "eol"
    }

    # Title tokens carry primary weight since titles name the exact offending component/technology
    title_tokens = (set(re.findall(r'[a-zA-Z0-9_\-\.]{2,}', title_lower)) | set(re.findall(r'[a-zA-Z0-9]{2,}', title_lower))) - stop_words
    body_tokens = (set(re.findall(r'[a-zA-Z0-9_\-\.]{3,}', body_lower)) | set(re.findall(r'[a-zA-Z0-9]{3,}', body_lower))) - stop_words

    scored_cells: list[tuple[float, TableCellRef]] = []

    for cell in table_cells:
        c_text = (cell.text or "").strip()
        c_lower = c_text.lower()
        if not c_lower:
            continue

        c_tokens = (set(re.findall(r'[a-zA-Z0-9_\-\.]{2,}', c_lower)) | set(re.findall(r'[a-zA-Z0-9]{2,}', c_lower))) - stop_words
        title_overlap = c_tokens & title_tokens
        body_overlap = (c_tokens & body_tokens) - title_overlap

        # Exact substring match in title (e.g. "RabbitMQ", "3.12", "Kong Enterprise", "3.6", or filename stems)
        clean_cell = re.sub(r'[^\w\s\.]', '', c_lower).strip()
        c_stem = re.sub(r'\.[a-zA-Z0-9]+$', '', clean_cell).strip()
        title_substr_match = bool(
            clean_cell and len(clean_cell) >= 2 and (
                clean_cell in title_lower or (c_stem and len(c_stem) >= 2 and c_stem in title_lower)
            )
        )

        # Title-weighted scoring
        title_score = len(title_overlap) * 12.0 + (30.0 if title_substr_match else 0.0)
        body_score = len(body_overlap) * 2.0

        # Multi-word phrase bonus in body, capped so descriptive phrases cannot dwarf title subjects
        phrase_score = 0.0
        c_words = re.findall(r'\b[a-zA-Z0-9_\-\.]{3,}\b', c_lower)
        if len(c_words) >= 3:
            for w_idx in range(len(c_words) - 2):
                tri_gram = f"{c_words[w_idx]} {c_words[w_idx+1]} {c_words[w_idx+2]}"
                if tri_gram in combined_lower:
                    phrase_score += 4.0
            phrase_score = min(phrase_score, 12.0)

        spatial_score = 0.0
        if raw_bboxes:
            for rb in raw_bboxes:
                x_ov = max(0.0, min(max(rb.l, rb.r), max(cell.bbox_pdf.l, cell.bbox_pdf.r)) - max(min(rb.l, rb.r), min(cell.bbox_pdf.l, cell.bbox_pdf.r)))
                y_ov = max(0.0, min(max(rb.t, rb.b), max(cell.bbox_pdf.t, cell.bbox_pdf.b)) - max(min(rb.t, rb.b), min(cell.bbox_pdf.t, cell.bbox_pdf.b)))
                if x_ov > 0 and y_ov > 0:
                    c_w = max(1.0, abs(cell.bbox_pdf.r - cell.bbox_pdf.l))
                    c_h = max(1.0, abs(cell.bbox_pdf.t - cell.bbox_pdf.b))
                    spatial_score = max(spatial_score, (x_ov * y_ov) / (c_w * c_h))

        total_score = title_score * 3.0 + body_score * 2.0 + phrase_score * 2.0 + spatial_score * 5.0
        if total_score > 0.0:
            scored_cells.append((total_score, cell))

    # Fallback to purely spatial overlap if no text score was positive
    if not scored_cells and raw_bboxes:
        for cell in table_cells:
            for rb in raw_bboxes:
                x_ov = max(0.0, min(max(rb.l, rb.r), max(cell.bbox_pdf.l, cell.bbox_pdf.r)) - max(min(rb.l, rb.r), min(cell.bbox_pdf.l, cell.bbox_pdf.r)))
                y_ov = max(0.0, min(max(rb.t, rb.b), max(cell.bbox_pdf.t, cell.bbox_pdf.b)) - max(min(rb.t, rb.b), min(cell.bbox_pdf.t, cell.bbox_pdf.b)))
                area_ov = x_ov * y_ov
                if area_ov > 0:
                    scored_cells.append((area_ov, cell))

    if not scored_cells:
        return raw_bboxes or [PageBoundingBox(**table_bbox.model_dump(), page_no=page_number)]

    scored_cells.sort(key=lambda x: x[0], reverse=True)
    best_score, best_cell = scored_cells[0]

    # Check for multi-cell/multi-row matches across distinct rows
    # (e.g. findings citing multiple report rows or missing classes across several table entries)
    score_threshold = max(2.0, best_score * 0.6) if best_score >= 2.0 else best_score
    strong_cells = [cell for sc, cell in scored_cells if sc >= score_threshold]

    # Group strong cells by vertical row position
    row_groups: list[list[TableCellRef]] = []
    for sc_cell in strong_cells:
        placed = False
        for rg in row_groups:
            # Overlap in vertical extent means same row
            ref_b = rg[0].bbox_pdf
            y_ov = min(max(ref_b.t, ref_b.b), max(sc_cell.bbox_pdf.t, sc_cell.bbox_pdf.b)) - max(min(ref_b.t, ref_b.b), min(sc_cell.bbox_pdf.t, sc_cell.bbox_pdf.b))
            if y_ov > 0.4 * min(abs(ref_b.t - ref_b.b), abs(sc_cell.bbox_pdf.t - sc_cell.bbox_pdf.b)):
                rg.append(sc_cell)
                placed = True
                break
        if not placed:
            row_groups.append([sc_cell])

    # If the finding spans multiple distinct rows (e.g. 2+ distinct rows matched with strong scores),
    # return the merged bounding box for each matched row rather than collapsing to a single cell
    if len(row_groups) >= 2 and (not raw_bboxes or best_score >= 10.0):
        multi_bboxes: list[PageBoundingBox] = []
        for rg in row_groups:
            l = min(c.bbox_pdf.l for c in rg)
            r = max(c.bbox_pdf.r for c in rg)
            t = max(c.bbox_pdf.t for c in rg) if origin == CoordOrigin.BOTTOMLEFT else min(c.bbox_pdf.t for c in rg)
            b = min(c.bbox_pdf.b for c in rg) if origin == CoordOrigin.BOTTOMLEFT else max(c.bbox_pdf.b for c in rg)
            multi_bboxes.append(PageBoundingBox(
                l=l, t=t, r=r, b=b, coord_origin=origin, page_no=page_number
            ))
        return multi_bboxes

    # Sub-line / bullet segment matching within the matched single cell
    raw_segments = [s.strip() for s in re.split(r'[\n\r•\u2022]+', best_cell.text) if s.strip()]
    if len(raw_segments) > 1:
        seg_scores = []
        for s_idx, seg in enumerate(raw_segments):
            s_toks = set(re.findall(r'\b[a-zA-Z0-9_\-\.]{2,}\b', seg.lower())) - stop_words
            s_title_overlap = len(title_tokens & s_toks)
            s_body_overlap = len(body_tokens & s_toks)
            s_clean = re.sub(r'[^\w\s]', '', seg.lower()).strip()
            s_phrase = 10 if (s_clean and len(s_clean.split()) >= 2 and (s_clean in combined_lower or seg.lower() in combined_lower)) else 0
            seg_scores.append((s_title_overlap * 6 + s_body_overlap * 2 + s_phrase, s_idx))

        max_sc = max((sc for sc, idx in seg_scores), default=0)
        if max_sc > 0:
            threshold = max(2.0, max_sc * 0.5)
            matching_indices = [idx for sc, idx in seg_scores if sc >= threshold]
            if matching_indices and len(matching_indices) < len(raw_segments):
                start_seg = min(matching_indices)
                end_seg = max(matching_indices)
                total_segs = len(raw_segments)
                frac_top = start_seg / total_segs
                frac_bottom = (end_seg + 1) / total_segs

                cell_t = best_cell.bbox_pdf.t
                cell_b = best_cell.bbox_pdf.b
                sub_t = cell_t + frac_top * (cell_b - cell_t)
                sub_b = cell_t + frac_bottom * (cell_b - cell_t)

                return [PageBoundingBox(
                    l=best_cell.bbox_pdf.l,
                    t=sub_t,
                    r=best_cell.bbox_pdf.r,
                    b=sub_b,
                    coord_origin=origin,
                    page_no=page_number,
                )]

    # If multiple strong cells belong to the SAME top row (e.g. "RabbitMQ" and "3.12"),
    # merge them to highlight the complete component + version subject
    top_row_cells = row_groups[0] if row_groups else [best_cell]
    if len(top_row_cells) > 1 and (not raw_bboxes or best_score >= 10.0):
        l = min(c.bbox_pdf.l for c in top_row_cells)
        r = max(c.bbox_pdf.r for c in top_row_cells)
        t = max(c.bbox_pdf.t for c in top_row_cells) if origin == CoordOrigin.BOTTOMLEFT else min(c.bbox_pdf.t for c in top_row_cells)
        b = min(c.bbox_pdf.b for c in top_row_cells) if origin == CoordOrigin.BOTTOMLEFT else max(c.bbox_pdf.b for c in top_row_cells)
        return [PageBoundingBox(
            l=l, t=t, r=r, b=b, coord_origin=origin, page_no=page_number
        )]

    return [PageBoundingBox(
        l=best_cell.bbox_pdf.l,
        t=best_cell.bbox_pdf.t,
        r=best_cell.bbox_pdf.r,
        b=best_cell.bbox_pdf.b,
        coord_origin=origin,
        page_no=page_number,
    )]

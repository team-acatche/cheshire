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


def _to_topleft_dict(bbox: BoundingBox, page_h: float) -> dict[str, float]:
    """
    Converts a Docling BoundingBox to a top-left origin dictionary with keys 'l', 't', 'r', 'b'.
    """
    if bbox.coord_origin == CoordOrigin.BOTTOMLEFT:
        return {"l": bbox.l, "t": page_h - bbox.t, "r": bbox.r, "b": page_h - bbox.b}
    return {"l": bbox.l, "t": bbox.t, "r": bbox.r, "b": bbox.b}


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
    """
    if not table_cells:
        return raw_bboxes or [PageBoundingBox(**table_bbox.model_dump(), page_no=page_number)]

    origin = getattr(table_bbox, "coord_origin", CoordOrigin.BOTTOMLEFT)
    search_text = f"{title or ''} {finding_text or ''}".strip().lower()

    stop_words = {
        "the", "and", "for", "with", "this", "that", "from", "table", "report", "section",
        "missing", "empty", "contains", "specification", "specifications", "field", "fields",
        "value", "values", "row", "column", "cell", "does", "not", "have", "should", "must"
    }
    search_tokens = set(re.findall(r'\b[a-zA-Z0-9_\-\.]{3,}\b', search_text)) - stop_words

    best_cell: Optional[TableCellRef] = None
    best_score = -1.0

    for cell in table_cells:
        c_text = (cell.text or "").strip().lower()
        if not c_text:
            continue

        c_tokens = set(re.findall(r'\b[a-zA-Z0-9_\-\.]{3,}\b', c_text)) - stop_words
        overlap_tokens = search_tokens & c_tokens
        token_score = float(len(overlap_tokens))

        phrase_score = 0.0
        c_words = re.findall(r'\b[a-zA-Z0-9_\-\.]{3,}\b', c_text)
        if len(c_words) >= 3:
            for w_idx in range(len(c_words) - 2):
                tri_gram = f"{c_words[w_idx]} {c_words[w_idx+1]} {c_words[w_idx+2]}"
                if tri_gram in search_text:
                    phrase_score += 15.0

        spatial_score = 0.0
        if raw_bboxes:
            for rb in raw_bboxes:
                x_ov = max(0.0, min(rb.r, cell.bbox_pdf.r) - max(rb.l, cell.bbox_pdf.l))
                if origin == CoordOrigin.BOTTOMLEFT:
                    y_ov = max(0.0, min(rb.t, cell.bbox_pdf.t) - max(rb.b, cell.bbox_pdf.b))
                else:
                    y_ov = max(0.0, min(rb.b, cell.bbox_pdf.b) - max(rb.t, cell.bbox_pdf.t))
                if x_ov > 0 and y_ov > 0:
                    c_w = max(1.0, cell.bbox_pdf.r - cell.bbox_pdf.l)
                    c_h = max(1.0, abs(cell.bbox_pdf.t - cell.bbox_pdf.b))
                    spatial_score = max(spatial_score, (x_ov * y_ov) / (c_w * c_h))

        total_score = phrase_score * 3.0 + token_score * 2.0 + spatial_score * 5.0
        if total_score > best_score:
            best_score = total_score
            best_cell = cell

    # Fallback to purely spatial overlap if no text score was positive
    if (best_score <= 0.0 or best_cell is None) and raw_bboxes:
        max_ov = 0.0
        for cell in table_cells:
            for rb in raw_bboxes:
                x_ov = max(0.0, min(rb.r, cell.bbox_pdf.r) - max(rb.l, cell.bbox_pdf.l))
                if origin == CoordOrigin.BOTTOMLEFT:
                    y_ov = max(0.0, min(rb.t, cell.bbox_pdf.t) - max(rb.b, cell.bbox_pdf.b))
                else:
                    y_ov = max(0.0, min(rb.b, cell.bbox_pdf.b) - max(rb.t, cell.bbox_pdf.t))
                area_ov = x_ov * y_ov
                if area_ov > max_ov:
                    max_ov = area_ov
                    best_cell = cell
        if max_ov > 0.0:
            best_score = 1.0

    if not best_cell:
        return raw_bboxes or [PageBoundingBox(**table_bbox.model_dump(), page_no=page_number)]

    # Sub-line / bullet segment matching within the matched cell
    raw_segments = [s.strip() for s in re.split(r'[\n\r•\u2022]+', best_cell.text) if s.strip()]
    if len(raw_segments) > 1:
        seg_scores = []
        for s_idx, seg in enumerate(raw_segments):
            s_toks = set(re.findall(r'\b[a-zA-Z0-9_\-\.]{3,}\b', seg.lower())) - stop_words
            s_overlap = len(search_tokens & s_toks)
            s_clean = re.sub(r'[^\w\s]', '', seg.lower()).strip()
            # Multi-word phrase bonus (requires at least 2 words to avoid single generic word bonus)
            s_phrase = 10 if (s_clean and len(s_clean.split()) >= 2 and (s_clean in search_text or seg.lower() in search_text)) else 0
            seg_scores.append((s_overlap * 2 + s_phrase, s_idx))

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

                cell_h = abs(best_cell.bbox_pdf.t - best_cell.bbox_pdf.b)
                if origin == CoordOrigin.BOTTOMLEFT:
                    sub_t = best_cell.bbox_pdf.t - frac_top * cell_h
                    sub_b = best_cell.bbox_pdf.t - frac_bottom * cell_h
                else:
                    sub_t = best_cell.bbox_pdf.t + frac_top * cell_h
                    sub_b = best_cell.bbox_pdf.t + frac_bottom * cell_h

                return [PageBoundingBox(
                    l=best_cell.bbox_pdf.l,
                    t=sub_t,
                    r=best_cell.bbox_pdf.r,
                    b=sub_b,
                    coord_origin=origin,
                    page_no=page_number,
                )]

    return [PageBoundingBox(
        l=best_cell.bbox_pdf.l,
        t=best_cell.bbox_pdf.t,
        r=best_cell.bbox_pdf.r,
        b=best_cell.bbox_pdf.b,
        coord_origin=origin,
        page_no=page_number,
    )]

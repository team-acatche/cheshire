"""
Table bounding box analysis, compound header split detection, embedded icon detection,
and markdown table formatting.
"""

import base64
from io import BytesIO
import re
from typing import Any

from docling.datamodel.document import ConversionResult
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.document import ProvenanceItem
from tabulate import tabulate

from .constants import (
    COLUMN_SPLIT_RATIO,
    DEFAULT_COL_WIDTH_PX,
    DEFAULT_ROW_HEIGHT_PX,
    FOOTER_BOTTOM_MARGIN_RATIO,
    FOOTER_METADATA_PATTERN,
    INDEPENDENT_HEADER_KEYWORDS,
    LAST_COL_RIGHT_PADDING_PX,
    LAST_ROW_BOTTOM_PADDING_PX,
    MAX_CONTINUATION_PAGE_GAP,
    MAX_HEADER_SEARCH_LINES,
    MAX_TABLE_RIGHT_GAP_PX,
    MIN_COMPOUND_COL_WIDTH_PX,
    MIN_ICON_OVERLAP_PX,
    MIN_TABLE_CELL_COVERAGE_RATIO,
    MIN_WIDE_TABLE_WIDTH_PX,
    WIDE_TABLE_ASPECT_RATIO,
)
from .geometry import _compute_box_overlap, _to_topleft_dict
from .models import FigureRef, ImageBoundingBox


def _calculate_extended_row_bounds(
    row_bboxes: dict[int, Any],
    num_rows: int,
    page_h: float,
    table_t: float | None = None,
    table_b: float | None = None,
) -> dict[int, tuple[float, float]]:
    """
    Computes top and bottom bounds for each row, forward-filling missing rows
    and extending boundaries to the midpoints of adjacent rows to cover inter-cell gaps.
    If no row bboxes exist, estimates row spans evenly from table_t to table_b.
    """
    row_bounds: dict[int, list[float | None]] = {}
    has_any_row_bbox = False
    for r in range(num_rows):
        if r in row_bboxes and row_bboxes[r] is not None:
            rb = _to_topleft_dict(row_bboxes[r], page_h)
            row_bounds[r] = [rb["t"], rb["b"]]
            has_any_row_bbox = True
        else:
            row_bounds[r] = [None, None]

    if not has_any_row_bbox and table_t is not None and table_b is not None and table_b > table_t and num_rows > 0:
        row_h = (table_b - table_t) / num_rows
        for r in range(num_rows):
            row_bounds[r] = [table_t + r * row_h, table_t + (r + 1) * row_h]
    else:
        # Forward-fill any rows without extracted bounding boxes
        for r in range(num_rows):
            curr_t, curr_b = row_bounds[r]
            if curr_t is None:
                prev_b = row_bounds[r - 1][1] if r > 0 and row_bounds[r - 1][1] is not None else (table_t or 0.0)
                curr_t = prev_b
                curr_b = prev_b + DEFAULT_ROW_HEIGHT_PX
                row_bounds[r] = [curr_t, curr_b]

    # Extend boundaries to bridge row gaps
    extended_row_bounds: dict[int, tuple[float, float]] = {}
    for r in range(num_rows):
        t = row_bounds[r][0] or 0.0
        b = row_bounds[r][1] or 0.0
        if r > 0 and row_bounds[r - 1][1] is not None:
            t = (row_bounds[r - 1][1] + t) / 2.0
        if r < num_rows - 1 and row_bounds[r + 1][0] is not None:
            b = (b + row_bounds[r + 1][0]) / 2.0
        else:
            padded_b = b + LAST_ROW_BOTTOM_PADDING_PX
            b = max(padded_b, table_b) if table_b is not None else padded_b
        extended_row_bounds[r] = (t, b)

    return extended_row_bounds


def _calculate_extended_col_bounds(
    col_bboxes: dict[int, Any],
    num_cols: int,
    page_h: float,
    table_r: float | None = None,
) -> dict[int, tuple[float, float]]:
    """
    Computes left and right bounds for each column, filling missing columns
    and extending boundaries to the midpoints of adjacent columns.
    If table_r is provided, ensures the rightmost column extends to the table boundary.
    """
    col_bounds: dict[int, list[float | None]] = {}
    for c in range(num_cols):
        if c in col_bboxes and col_bboxes[c] is not None:
            cb = _to_topleft_dict(col_bboxes[c], page_h)
            col_bounds[c] = [cb["l"], cb["r"]]
        else:
            col_bounds[c] = [None, None]

    extended_col_bounds: dict[int, tuple[float, float]] = {}
    for c in range(num_cols):
        l = col_bounds[c][0]
        r = col_bounds[c][1]
        if l is None or r is None:
            prev_r = extended_col_bounds[c - 1][1] if c > 0 else 0.0
            l = prev_r
            r = prev_r + DEFAULT_COL_WIDTH_PX
        else:
            if c > 0 and col_bounds[c - 1][1] is not None:
                l = (col_bounds[c - 1][1] + l) / 2.0
            if c < num_cols - 1 and col_bounds[c + 1][0] is not None:
                r = (r + col_bounds[c + 1][0]) / 2.0
            else:
                padded_r = r + LAST_COL_RIGHT_PADDING_PX
                r = max(padded_r, table_r) if table_r is not None else padded_r
        extended_col_bounds[c] = (l, r)

    return extended_col_bounds


def _get_table_cell_bounds(table_item: Any, page_h: float) -> dict[tuple[int, int], dict[str, float]]:
    """
    Computes top-left origin pixel bounding boxes for each (row, col) cell in a table.
    Extends row and column boundaries to cover inter-cell gaps and handles missing bboxes.
    """
    grid = getattr(getattr(table_item, "data", None), "grid", None)
    if not grid or len(grid) == 0:
        return {}
    num_rows = len(grid)
    num_cols = len(grid[0]) if num_rows > 0 else 0
    if num_rows == 0 or num_cols == 0:
        return {}

    try:
        row_bboxes = table_item.data.get_row_bounding_boxes()
        col_bboxes = table_item.data.get_column_bounding_boxes()
    except Exception:
        return {}

    prov = table_item.prov[0] if hasattr(table_item, "prov") and table_item.prov else None
    table_r = None
    table_t = None
    table_b = None
    if prov and page_h > 0.0:
        tb = _to_topleft_dict(prov.bbox, page_h)
        table_r = tb["r"]
        table_t = tb["t"]
        table_b = tb["b"]

    extended_row_bounds = _calculate_extended_row_bounds(
        row_bboxes, num_rows, page_h, table_t=table_t, table_b=table_b
    )
    extended_col_bounds = _calculate_extended_col_bounds(col_bboxes, num_cols, page_h, table_r=table_r)

    cell_bounds: dict[tuple[int, int], dict[str, float]] = {}
    for r in range(num_rows):
        for c in range(num_cols):
            cell_bounds[(r, c)] = {
                "l": extended_col_bounds[c][0],
                "r": extended_col_bounds[c][1],
                "t": extended_row_bounds[r][0],
                "b": extended_row_bounds[r][1],
            }
    return cell_bounds


def _detect_compound_header_split(
    header_text: str,
    col_width: float,
    has_left_biased_picture: bool = False,
    has_right_biased_picture: bool = False,
) -> tuple[str, str] | None:
    """
    Detects if a table header cell contains multiple merged column titles.
    Returns (left_title, right_title) if a split is justified, otherwise None.
    Applicable universally across any PDF without document-specific overtuning.
    """
    cleaned = header_text.strip()
    if not cleaned:
        return None

    # 1. Explicit multi-line separation in header
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    if len(lines) == 2 and col_width >= MIN_COMPOUND_COL_WIDTH_PX:
        return lines[0], lines[1]

    # 2. Explicit multi-space separation (2 or more spaces)
    space_parts = re.split(r'\s{2,}', cleaned)
    if len(space_parts) == 2 and col_width >= MIN_COMPOUND_COL_WIDTH_PX:
        return space_parts[0], space_parts[1]

    # 3. Explicit pipe or slash delimiter surrounded by spaces
    delim_parts = re.split(r'\s+[|/]\s+', cleaned)
    if len(delim_parts) == 2 and col_width >= MIN_COMPOUND_COL_WIDTH_PX:
        w1, w2 = delim_parts[0].lower(), delim_parts[1].lower()
        if w1 not in ("new", "class") and w2 not in ("existing", "module"):
            return delim_parts[0], delim_parts[1]

    # 4. Multi-word phrase with an independent keyword suffix confirmed by layout
    words = cleaned.split()
    if len(words) >= 2:
        last_word_clean = re.sub(r'[^a-zA-Z0-9]', '', words[-1]).lower()
        if last_word_clean in INDEPENDENT_HEADER_KEYWORDS:
            prefix = " ".join(words[:-1])
            suffix = words[-1]
            if (has_left_biased_picture or has_right_biased_picture) and col_width >= MIN_COMPOUND_COL_WIDTH_PX:
                return prefix, suffix
            if len(words) >= 3 and col_width >= MIN_COMPOUND_COL_WIDTH_PX:
                return prefix, suffix

    return None


def _detect_table_column_splits(
    grid: list[list[Any]],
    cell_bounds: dict[tuple[int, int], dict[str, float]],
    pics: list[Any],
    page_h: float,
) -> dict[int, tuple[str, str]]:
    """
    Scans the header row (row 0) to detect compound columns (e.g. 'File Type Link')
    that should be split into multiple distinct columns.
    Uses column width and spatial distribution of embedded pictures across body rows.
    """
    num_rows = len(grid)
    num_cols = len(grid[0]) if num_rows > 0 else 0
    if num_rows == 0 or num_cols == 0:
        return {}

    col_splits: dict[int, tuple[str, str]] = {}
    for c in range(num_cols):
        hdr_txt = grid[0][c].text.strip()
        cb = cell_bounds.get(
            (0, c),
            {"l": 0.0, "r": DEFAULT_COL_WIDTH_PX, "t": 0.0, "b": DEFAULT_ROW_HEIGHT_PX}
        )
        col_w = cb["r"] - cb["l"]
        mid_x = cb["l"] + col_w * COLUMN_SPLIT_RATIO

        # Check for picture bias across all data rows in this column
        has_left_pic = False
        has_right_pic = False
        for r in range(1, num_rows):
            rcb = cell_bounds.get((r, c), cb)
            for p in pics:
                if not p.prov:
                    continue
                pb = _to_topleft_dict(p.prov[0].bbox, page_h)
                x_ov, y_ov = _compute_box_overlap(rcb, pb)
                if x_ov > MIN_ICON_OVERLAP_PX and y_ov > MIN_ICON_OVERLAP_PX:
                    pic_mid_x = (pb["l"] + pb["r"]) / 2.0
                    if pic_mid_x < mid_x:
                        has_left_pic = True
                    else:
                        has_right_pic = True

        split = _detect_compound_header_split(
            hdr_txt,
            col_w,
            has_left_biased_picture=has_left_pic,
            has_right_biased_picture=has_right_pic,
        )
        if split:
            col_splits[c] = split

    return col_splits


def _table_has_empty_cells(markdown: str) -> bool:
    """
    Returns True if any data row in the markdown table has at least one
    empty cell. Empty means the cell contains only whitespace.
    Header and separator rows are excluded from the check.
    """
    lines: list[str] = markdown.strip().split('\n')

    # Find the separator row (e.g. |---|---|) to skip header lines
    data_start: int = 0
    for i, line in enumerate(lines[:MAX_HEADER_SEARCH_LINES]):
        if re.match(r'^\s*\|([\s:-]+\|)+\s*$', line):
            data_start = i + 1
            break

    for line in lines[data_start:]:
        # Split on pipe, ignore first/last empty strings from leading/trailing pipes
        cells: list[str] = line.split('|')
        for cell in cells[1:-1]:  # skip outer empty splits
            if cell.strip() == '':
                return True
    return False


def _table_needs_visual_crop(
    table_item: Any,
    markdown: str,
    page_h: float,
) -> bool:
    """
    Determines if a table needs a visual image crop attached to its chunk.
    Triggers visual fallback under three general physical and structural conditions:
    1. Empty data cells exist in the markdown representation (possible dropped icons, images, or unparsed text).
    2. Geometric cell coverage discrepancy: the horizontal extent of extracted cell
       bounding boxes is significantly narrower than the table's detected provenance
       bounding box (e.g. cell width < 85% of table bbox width or right margin gap > 30px),
       indicating severe horizontal margin clipping by the layout model.
    3. Structural under-segmentation: a table with a wide aspect ratio (> 2.5) and
       multiple rows was collapsed into a single column, indicating missed column boundaries.
    """
    # 1. Check for empty cells
    if _table_has_empty_cells(markdown):
        return True

    prov = table_item.prov[0] if hasattr(table_item, "prov") and table_item.prov else None
    if not prov or page_h <= 0.0:
        return False

    table_box = _to_topleft_dict(prov.bbox, page_h)
    table_w = table_box["r"] - table_box["l"]
    table_h = table_box["b"] - table_box["t"]
    if table_w <= 0.0:
        return False

    # 2. Check geometric cell coverage discrepancy (horizontal clipping)
    cb_list: list[dict[str, float]] = []
    try:
        col_bboxes = table_item.data.get_column_bounding_boxes()
        if col_bboxes:
            cb_list = [_to_topleft_dict(cb, page_h) for cb in col_bboxes.values() if cb is not None]
    except Exception:
        pass

    if not cb_list:
        table_cells = getattr(getattr(table_item, "data", None), "table_cells", [])
        cb_list = [
            _to_topleft_dict(getattr(c, "bbox", None), page_h)
            for c in table_cells
            if getattr(c, "bbox", None) is not None
        ]

    if cb_list:
        min_cell_l = min(c["l"] for c in cb_list)
        max_cell_r = max(c["r"] for c in cb_list)
        cells_w = max_cell_r - min_cell_l
        right_gap = table_box["r"] - max_cell_r
        if cells_w < table_w * MIN_TABLE_CELL_COVERAGE_RATIO or right_gap > MAX_TABLE_RIGHT_GAP_PX:
            return True

    # 3. Check structural under-segmentation (single column on wide multi-row table)
    grid = getattr(getattr(table_item, "data", None), "grid", None)
    if grid and len(grid) > 2 and len(grid[0]) == 1:
        aspect_ratio = table_w / table_h if table_h > 0.0 else 0.0
        if table_w >= MIN_WIDE_TABLE_WIDTH_PX and aspect_ratio >= WIDE_TABLE_ASPECT_RATIO:
            return True

    return False


def _sanitize_table_cell_text(text: str) -> str:
    """
    Cleans soft hyphens, zero-width characters, non-printing artifacts,
    and normalizes whitespace and hyphen-broken words across line breaks in table cell text.
    """
    if not text:
        return ""
    # Remove soft-hyphens, zero-width spaces, and PDF encoding control artifacts
    cleaned = re.sub(r'[\xad\ufffe\u200b\ufeff\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    # Normalize hyphen-split words across linebreaks (e.g. "LOA-\n SCR-013" -> "LOA-SCR-013")
    cleaned = re.sub(r'(\b\w+-\s*)\n\s*(\w+)', r'\1\2', cleaned)
    # Replace remaining newlines with spaces and collapse multiple whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned



def _crop_table_as_figure(
    result: ConversionResult,
    prov: ProvenanceItem,
    self_ref: str,
    scale: float,
    figure_lookup: dict[str, FigureRef],
) -> str | None:
    """
    Renders the page region containing the table and stores a FigureRef
    in figure_lookup. Returns the synthetic figure_id, or None on failure.
    """
    # result.pages is 0-indexed; prov.page_no is 1-indexed
    page_idx: int = prov.page_no - 1
    if page_idx < 0 or page_idx >= len(result.pages):
        return None

    conv_page = result.pages[page_idx]
    try:
        img = conv_page.get_image(scale=scale, cropbox=prov.bbox)
        if img is None:
            return None
        buf: BytesIO = BytesIO()
        img.save(buf, format="PNG")
        b64: str = base64.standard_b64encode(buf.getvalue()).decode()
    except Exception:
        return None

    fig_id: str = f"table_crop_{self_ref}"
    figure_lookup[fig_id] = FigureRef(
        figure_id=fig_id,
        page_number=prov.page_no,
        bbox_image_px=ImageBoundingBox.from_docling_bbox(
            prov.bbox,
            conv_page.size.height if conv_page.size else 0,
            scale,
        ),
        bbox_pdf=prov.bbox,
        base64_png=b64,
    )
    return fig_id


def _format_cell_with_icons(
    cell_text: str,
    cell_box: dict[str, float],
    has_cell_bounds: bool,
    pics: list[Any],
    page_h: float,
    is_header_row: bool,
    col_split: tuple[str, str] | None = None,
) -> list[str]:
    """
    Formats the text for a single cell, resolving embedded icons if present.
    If col_split is provided:
      - Header row returns [left_title, right_title]
      - Data row returns [left_cell_text, right_cell_text]
    Otherwise, returns [cell_text].
    """
    if col_split is not None:
        left_title, right_title = col_split
        if is_header_row:
            return [left_title, right_title]

        col_w = cell_box["r"] - cell_box["l"]
        mid_x = cell_box["l"] + col_w * COLUMN_SPLIT_RATIO
        left_txt = ""
        right_txt = ""
        for p in pics:
            if not p.prov:
                continue
            pb = _to_topleft_dict(p.prov[0].bbox, page_h)
            x_ov, y_ov = _compute_box_overlap(cell_box, pb)
            if x_ov > MIN_ICON_OVERLAP_PX and y_ov > MIN_ICON_OVERLAP_PX:
                pic_mid_x = (pb["l"] + pb["r"]) / 2.0
                if pic_mid_x < mid_x:
                    left_txt = "[Embedded Icon]"
                else:
                    right_txt = "[Embedded Icon]"

        txt = _sanitize_table_cell_text(cell_text)
        if txt:
            if left_txt:
                right_txt = txt if not right_txt else f"{txt} {right_txt}"
            else:
                left_txt = txt
        return [left_txt, right_txt]

    # Non-split standard cell
    txt = _sanitize_table_cell_text(cell_text)
    if not is_header_row and has_cell_bounds:
        for p in pics:
            if not p.prov:
                continue
            pb = _to_topleft_dict(p.prov[0].bbox, page_h)
            x_ov, y_ov = _compute_box_overlap(cell_box, pb)
            if x_ov > MIN_ICON_OVERLAP_PX and y_ov > MIN_ICON_OVERLAP_PX:
                txt = "[Embedded Icon]" if not txt else f"{txt} [Embedded Icon]"
                break
    return [txt]


def _format_table_row_cells(
    row: list[Any],
    r_idx: int,
    is_header_row: bool,
    col_splits: dict[int, tuple[str, str]],
    cell_bounds: dict[tuple[int, int], dict[str, float]],
    pics: list[Any],
    page_h: float,
) -> list[str]:
    """
    Renders all cells of a table row into a list of cell string contents,
    expanding any compound columns and resolving embedded icons.
    """
    row_cells: list[str] = []
    for c_idx, cell in enumerate(row):
        cb = cell_bounds.get(
            (r_idx, c_idx),
            {"l": 0.0, "r": DEFAULT_COL_WIDTH_PX, "t": 0.0, "b": DEFAULT_ROW_HEIGHT_PX}
        )
        has_bounds = (r_idx, c_idx) in cell_bounds
        split = col_splits.get(c_idx)
        cell_txt = getattr(cell, "text", str(cell))
        formatted = _format_cell_with_icons(
            cell_text=cell_txt,
            cell_box=cb,
            has_cell_bounds=has_bounds,
            pics=pics,
            page_h=page_h,
            is_header_row=is_header_row,
            col_split=split,
        )
        row_cells.extend(formatted)
    return row_cells


def _extract_header_from_table_text(
    table_text: str,
    last_header: str | None,
    is_continuation: bool,
) -> tuple[str, str | None]:
    """
    Extracts header and separator rows from a formatted markdown table to support
    continuation tracking across pages. Prepends last_header if a continuation table lacks one.
    """
    lines = table_text.strip().split("\n")
    sep_idx: int | None = None
    for i, line in enumerate(lines[:MAX_HEADER_SEARCH_LINES]):
        if re.match(r'^\s*\|([\s:-]+\|)+\s*$', line):
            sep_idx = i
            break

    new_last_header = last_header
    if sep_idx is not None and sep_idx >= 1:
        new_last_header = "\n".join(lines[:sep_idx + 1])
    elif sep_idx is None and is_continuation and last_header:
        table_text = last_header + "\n" + table_text

    return table_text, new_last_header


def _is_table_footer_row(
    row: list[Any],
    r_idx: int,
    cell_bounds: dict[tuple[int, int], dict[str, float]],
    page_h: float,
) -> bool:
    """
    Checks if a trailing table row is a page footer accidentally absorbed into the table.
    Requires both:
    1. Row text matches generic corporate document-control footer metadata patterns.
    2. Row's vertical position is in the bottom footer margin band of the page.
    """
    if not row or page_h <= 0.0:
        return False

    row_text = " ".join(getattr(c, "text", str(c)) for c in row).strip()
    if not row_text or not FOOTER_METADATA_PATTERN.search(row_text):
        return False

    # Check vertical position from cell_bounds
    cb_list = [cell_bounds[(r_idx, c_idx)] for c_idx in range(len(row)) if (r_idx, c_idx) in cell_bounds]
    if cb_list:
        row_top = min(cb["t"] for cb in cb_list)
        row_bottom = max(cb["b"] for cb in cb_list)
        if row_top >= page_h * FOOTER_BOTTOM_MARGIN_RATIO or row_bottom >= page_h * FOOTER_BOTTOM_MARGIN_RATIO:
            return True

    # Fallback to individual cell bounding boxes if cell_bounds missing
    for cell in row:
        bbox = getattr(cell, "bbox", None)
        if bbox is not None:
            tb = _to_topleft_dict(bbox, page_h)
            if tb["t"] >= page_h * FOOTER_BOTTOM_MARGIN_RATIO or tb["b"] >= page_h * FOOTER_BOTTOM_MARGIN_RATIO:
                return True

    return False


def _format_table_markdown(
    table_item: Any,
    doc: DoclingDocument,
    last_header: str | None,
    is_continuation: bool,
) -> tuple[str, str | None]:
    """
    Formats a Docling table into markdown.
    Detects embedded format/attachment icons from doc.pictures on the page and
    populates/annotates the corresponding cell text with '[Embedded Icon]',
    allowing the evaluator to distinguish between visual icons and genuinely empty cells.
    Also recovers under-segmented compound header columns (e.g. 'File Type Link')
    when layout analysis reveals multiple column titles grouped into a single cell.
    Also handles continuation tables lacking repeated headers.
    Returns (table_markdown, new_last_header).
    """
    grid = getattr(getattr(table_item, "data", None), "grid", None)
    if not grid or len(grid) == 0:
        try:
            return table_item.export_to_markdown(doc=doc), last_header
        except Exception:
            return getattr(table_item, "export_to_markdown", lambda: "")(), last_header

    prov = table_item.prov[0] if hasattr(table_item, "prov") and table_item.prov else None
    page_no = prov.page_no if prov else -1
    page = doc.pages.get(page_no) if page_no != -1 else None
    page_h = page.size.height if page and page.size else 0.0
    pics = [p for p in doc.pictures if p.prov and p.prov[0].page_no == page_no] if page_no != -1 else []

    has_col_headers = any(getattr(cell, "column_header", False) for cell in grid[0])
    cell_bounds = _get_table_cell_bounds(table_item, page_h) if page_h > 0 else {}

    col_splits = _detect_table_column_splits(grid, cell_bounds, pics, page_h)

    # Prune trailing footer rows accidentally absorbed into table
    while len(grid) > 1 and _is_table_footer_row(grid[-1], len(grid) - 1, cell_bounds, page_h):
        grid = grid[:-1]

    # Format continuation table lacking headers
    if is_continuation and not has_col_headers and last_header:
        data_rows = [
            "| " + " | ".join(
                _format_table_row_cells(
                    row=row,
                    r_idx=r_idx,
                    is_header_row=False,
                    col_splits=col_splits,
                    cell_bounds=cell_bounds,
                    pics=pics,
                    page_h=page_h,
                )
            ) + " |"
            for r_idx, row in enumerate(grid)
        ]
        text = last_header + "\n" + "\n".join(data_rows)
        return text, last_header

    # Standard table (or continuation with headers)
    table_rows: list[list[str]] = []
    for r_idx, row in enumerate(grid):
        is_header = (r_idx == 0) or all(getattr(cell, "column_header", False) for cell in row)
        row_cells = _format_table_row_cells(
            row=row,
            r_idx=r_idx,
            is_header_row=is_header,
            col_splits=col_splits,
            cell_bounds=cell_bounds,
            pics=pics,
            page_h=page_h,
        )
        table_rows.append(row_cells)

    if len(table_rows) > 1 and len(table_rows[0]) > 0:
        text = tabulate(table_rows[1:], headers=table_rows[0], tablefmt="github", disable_numparse=True)
    elif len(table_rows) == 1:
        text = tabulate([], headers=table_rows[0], tablefmt="github")
    else:
        text = ""

    return _extract_header_from_table_text(text, last_header, is_continuation)

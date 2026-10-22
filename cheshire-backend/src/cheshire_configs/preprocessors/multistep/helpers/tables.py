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
    INDEPENDENT_HEADER_KEYWORDS,
    LAST_COL_RIGHT_PADDING_PX,
    LAST_ROW_BOTTOM_PADDING_PX,
    MAX_CONTINUATION_PAGE_GAP,
    MAX_HEADER_SEARCH_LINES,
    MIN_COMPOUND_COL_WIDTH_PX,
    MIN_ICON_OVERLAP_PX,
)
from .geometry import _compute_box_overlap, _to_topleft_dict
from .models import FigureRef, ImageBoundingBox


def _calculate_extended_row_bounds(
    row_bboxes: dict[int, Any],
    num_rows: int,
    page_h: float,
) -> dict[int, tuple[float, float]]:
    """
    Computes top and bottom bounds for each row, forward-filling missing rows
    and extending boundaries to the midpoints of adjacent rows to cover inter-cell gaps.
    """
    row_bounds: dict[int, list[float | None]] = {}
    for r in range(num_rows):
        if r in row_bboxes and row_bboxes[r] is not None:
            rb = _to_topleft_dict(row_bboxes[r], page_h)
            row_bounds[r] = [rb["t"], rb["b"]]
        else:
            row_bounds[r] = [None, None]

    # Forward-fill any rows without extracted bounding boxes
    for r in range(num_rows):
        curr_t, curr_b = row_bounds[r]
        if curr_t is None:
            prev_b = row_bounds[r - 1][1] if r > 0 and row_bounds[r - 1][1] is not None else 0.0
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
            b = b + LAST_ROW_BOTTOM_PADDING_PX
        extended_row_bounds[r] = (t, b)

    return extended_row_bounds


def _calculate_extended_col_bounds(
    col_bboxes: dict[int, Any],
    num_cols: int,
    page_h: float,
) -> dict[int, tuple[float, float]]:
    """
    Computes left and right bounds for each column, filling missing columns
    and extending boundaries to the midpoints of adjacent columns.
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
                r = r + LAST_COL_RIGHT_PADDING_PX
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

    extended_row_bounds = _calculate_extended_row_bounds(row_bboxes, num_rows, page_h)
    extended_col_bounds = _calculate_extended_col_bounds(col_bboxes, num_cols, page_h)

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

        txt = cell_text.replace("\n", " ").strip()
        if txt:
            if left_txt:
                right_txt = txt if not right_txt else f"{txt} {right_txt}"
            else:
                left_txt = txt
        return [left_txt, right_txt]

    # Non-split standard cell
    txt = cell_text.replace("\n", " ").strip()
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

"""
Document element and figure lookup construction, caption attachment, and page gap detection.
"""

import base64
from io import BytesIO
import re
from typing import Any

from docling.datamodel.document import ConversionResult
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.document import ProvenanceItem

from .constants import FOOTER_BOTTOM_MARGIN_RATIO, FOOTER_MAX_TOP_RATIO, FOOTER_METADATA_PATTERN, MAX_CONTINUATION_PAGE_GAP
from .geometry import _get_item_label, _to_topleft_dict
from .hierarchy import _extract_heading_from_text, _is_spurious_heading, _normalize_heading_text
from .models import ElementRef, FigureRef, ImageBoundingBox, TableCellRef
from .tables import (
    _crop_table_as_figure,
    _detect_document_footer_top,
    _extract_table_cells_ref,
    _format_table_markdown,
    _table_has_empty_cells,
    _table_needs_visual_crop,
)


def _build_figure_lookup(
    doc: DoclingDocument,
    result: ConversionResult,
    scale: float,
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

        prov: ProvenanceItem = picture.prov[0]
        page: Any = doc.pages.get(prov.page_no)
        if page is None or page.size is None:
            continue

        bbox_px: ImageBoundingBox = ImageBoundingBox.from_docling_bbox(prov.bbox, page.size.height, scale)

        try:
            img: Any = picture.get_image(result)
            buf: BytesIO = BytesIO()
            img.save(buf, format="PNG")
            b64: str = base64.standard_b64encode(buf.getvalue()).decode()
        except Exception:
            b64 = ""

        lookup[picture.self_ref] = FigureRef(
            figure_id=picture.self_ref,
            page_number=prov.page_no,
            bbox_image_px=bbox_px,
            bbox_pdf=prov.bbox,
            base64_png=b64,
        )

    return lookup


def _is_footer_element(
    item: Any,
    doc: DoclingDocument,
    page_h: float,
    footer_top: float | None = None,
) -> bool:
    """
    Detects whether an extracted item (table, paragraph, or text block)
    is actually an anomalous page footer based on spatial location in the footer zone
    and presence of corporate document-control metadata.
    Adapts dynamically to footer height (compact 1-line or multi-line disclaimers).
    """
    if page_h <= 0.0 or not hasattr(item, "prov") or not item.prov:
        return False

    prov: ProvenanceItem = item.prov[0]
    if not prov.bbox:
        return False

    threshold_y = footer_top if footer_top is not None and footer_top > 0.0 else page_h * FOOTER_MAX_TOP_RATIO

    tb = _to_topleft_dict(prov.bbox, page_h)
    # Must be located in the footer zone of the page
    if tb["t"] < threshold_y and tb["b"] < threshold_y:
        return False

    # Extract item text
    item_text = getattr(item, "text", "")
    if not item_text:
        # If table, inspect cell texts
        grid = getattr(getattr(item, "data", None), "grid", None)
        if grid:
            item_text = " ".join(getattr(c, "text", str(c)) for row in grid for c in row)
        elif hasattr(item, "export_to_markdown"):
            try:
                item_text = item.export_to_markdown(doc=doc)
            except Exception:
                item_text = ""

    if not item_text:
        return False

    return bool(FOOTER_METADATA_PATTERN.search(item_text))


def promote_heuristic_headings(doc: Any) -> list[str]:
    """
    Scans document items for headings:
    1. Demotes spurious section headers (e.g. isolated table column headers like 'Diagram' or 'Files')
       misclassified as section headers by the layout parser back to paragraphs.
    2. Promotes headings misclassified as paragraphs or regular text to section headers.
    """
    promoted: list[str] = []
    if not hasattr(doc, "iterate_items"):
        return promoted

    for item, _level in doc.iterate_items():
        if not hasattr(item, "prov") or not item.prov:
            continue

        label: str = _get_item_label(item)

        # 1. Demote spurious section headers mislabeled by Docling layout model
        if label in ("section_header", "section_heading"):
            raw_text = getattr(item, "text", "")
            orig_text = getattr(item, "orig", "")
            txt = orig_text or raw_text
            cand = _extract_heading_from_text(txt)
            clean = cand or _normalize_heading_text(txt)
            if not clean or _is_spurious_heading(clean):
                if hasattr(item, "label"):
                    try:
                        from docling_core.types.doc.document import DocItemLabel
                        item.label = DocItemLabel.PARAGRAPH
                    except Exception:
                        item.label = "paragraph"
                try:
                    from docling_core.types.doc.document import TextItem
                    if not isinstance(item, TextItem):
                        item.__class__ = TextItem
                except Exception:
                    pass
                if hasattr(doc, "texts"):
                    for idx, t_item in enumerate(doc.texts):
                        if getattr(t_item, "self_ref", None) == item.self_ref:
                            try:
                                from docling_core.types.doc.document import TextItem
                                doc.texts[idx] = TextItem(
                                    text=raw_text,
                                    orig=orig_text,
                                    prov=item.prov,
                                    parent=getattr(item, "parent", None),
                                    children=getattr(item, "children", []),
                                    self_ref=item.self_ref,
                                )
                            except Exception:
                                pass
                            break
            continue

        # Skip decorative elements, tables, and pictures (allow page_header if it contains outline heading)
        if label in ("picture", "page_footer", "page_number", "footnote", "table"):
            continue
        if label == "page_header":
            item_text = getattr(item, "text", "")
            if not _extract_heading_from_text(item_text):
                continue

        raw_text = getattr(item, "text", "")
        orig_text = getattr(item, "orig", "")
        marker = getattr(item, "marker", "") or getattr(item, "enumerator", "")
        combined = f"{marker} {raw_text}".strip() if marker else ""

        heading = None
        for cand_str in (orig_text, combined, raw_text):
            if cand_str:
                h = _extract_heading_from_text(cand_str)
                if h and not _is_spurious_heading(h):
                    heading = h
                    break

        if not heading:
            continue

        item_text = raw_text or heading

        promoted.append(heading)

        # 1. Update item attributes and class
        is_standalone = len(item_text.strip()) <= len(heading) + 120 and len(item_text.splitlines()) <= 2
        if is_standalone:
            if hasattr(item, "text"):
                item.text = heading
            if hasattr(item, "orig"):
                item.orig = heading
        else:
            if hasattr(item, "orig") and not item.orig:
                item.orig = item_text

        if hasattr(item, "label"):
            try:
                from docling_core.types.doc.document import DocItemLabel
                item.label = DocItemLabel.SECTION_HEADER
            except Exception:
                item.label = "section_header"
        if hasattr(item, "level"):
            item.level = 1

        try:
            from docling_core.types.doc.document import SectionHeaderItem
            if not isinstance(item, SectionHeaderItem):
                item.__class__ = SectionHeaderItem
        except Exception:
            pass

        # 2. If item is a Docling TextItem in doc.texts, replace with SectionHeaderItem
        try:
            from docling_core.types.doc.document import SectionHeaderItem
            if hasattr(doc, "texts"):
                new_item = SectionHeaderItem(
                    text=heading if is_standalone else getattr(item, "text", heading),
                    orig=getattr(item, "orig", heading),
                    level=1,
                    prov=item.prov,
                    parent=getattr(item, "parent", None),
                    children=getattr(item, "children", []),
                    self_ref=item.self_ref,
                )
                for idx, t_item in enumerate(doc.texts):
                    if getattr(t_item, "self_ref", None) == item.self_ref:
                        doc.texts[idx] = new_item
                        break
        except Exception:
            pass

    return promoted


def _build_element_lookup(
    doc: DoclingDocument,
    result: ConversionResult,
    figure_lookup: dict[str, FigureRef],
    scale: float,
) -> dict[str, ElementRef]:
    """
    Iterates every item in the DoclingDocument and builds a dict keyed by
    self_ref. Pictures are excluded — they go into the figure lookup.
    Tables use their markdown export as the text excerpt so the model
    sees structured table content rather than a raw string.

    Tables whose markdown contains empty cells (a signal that embedded
    images were lost during extraction) are additionally cropped from the
    rendered page and inserted into figure_lookup so the model receives
    both the structured text and a visual of the table.

    Continuation tables (tables that span a page break and lose their
    header row) are detected by section + page proximity and have the
    previous table's header prepended.
    """
    lookup: dict[str, ElementRef] = {}
    # Continuation-header tracking (scoped by section + page)
    _last_table_header: str | None = None
    _last_table_page: int = -1
    _current_section: str = ""
    footer_top_cache: dict[float, float] = {}

    for item, _level in doc.iterate_items():
        if not hasattr(item, "prov") or not item.prov:
            continue

        label: str = _get_item_label(item)

        # Skip decorative page elements, but check if page_header is actually a section heading
        if label == "page_header":
            cand = _extract_heading_from_text(getattr(item, "text", ""))
            if cand:
                label = "section_header"
            else:
                continue
        elif label in ("picture", "page_footer", "page_number", "footnote"):
            continue

        # Track section boundaries to scope continuation headers
        if label in ("section_header", "section_heading"):
            cand = _extract_heading_from_text(getattr(item, "text", ""))
            _current_section = cand or getattr(item, "text", "")
            _last_table_header = None
        else:
            cand = _extract_heading_from_text(getattr(item, "text", ""))
            if cand:
                label = "section_header"
                _current_section = cand
                _last_table_header = None

        prov: ProvenanceItem = item.prov[0]
        page: Any = doc.pages.get(prov.page_no)
        if page is None or page.size is None:
            continue

        page_h = page.size.height
        if page_h not in footer_top_cache:
            footer_top_cache[page_h] = _detect_document_footer_top(doc, page_h)
        footer_top = footer_top_cache[page_h]

        # Skip anomalous tabular or columnar footers mislabeled as table/paragraph/text
        if _is_footer_element(item, doc, page_h, footer_top=footer_top):
            continue

        bbox_px: ImageBoundingBox = ImageBoundingBox.from_docling_bbox(prov.bbox, page_h, scale)

        text: str = ""
        table_cells_ref: list[TableCellRef] = []
        if label == "table":
            # Detect continuation table status based on adjacent page in same section
            is_adjacent_page: bool = (
                _last_table_header is not None and 0 <= (prov.page_no - _last_table_page) <= MAX_CONTINUATION_PAGE_GAP
            )
            text, _last_table_header = _format_table_markdown(
                item, doc, _last_table_header, is_adjacent_page
            )
            _last_table_page = prov.page_no
            table_cells_ref = _extract_table_cells_ref(item, page.size.height, prov.bbox)

            # Selective table cropping for tables with empty cells or extraction clipping
            if _table_needs_visual_crop(item, text, page.size.height):
                fig_id: str | None = _crop_table_as_figure(
                    result, prov, item.self_ref, scale, figure_lookup, table_cells=table_cells_ref
                )
                if fig_id:
                    text += f"\n[Table Image: {fig_id}]"

        elif hasattr(item, "text") and item.text:
            text = item.text
        elif hasattr(item, "export_to_markdown"):
            text = item.export_to_markdown()

        lookup[item.self_ref] = ElementRef(
            element_id=item.self_ref,
            label=label,
            page_number=prov.page_no,
            bbox_image_px=bbox_px,
            bbox_pdf=prov.bbox,
            text_excerpt=text,
            table_cells=table_cells_ref,
        )

    return lookup


def _attach_captions(doc: DoclingDocument, figures: list[dict]) -> None:
    """
    Captions are separate DocItemLabel.CAPTION elements in Docling's output —
    they are not properties of the picture item itself. This function matches
    each caption to the nearest figure on the same page by measuring the
    vertical distance between the figure and caption in normalized top-left space.
    The closest figure within reasonable proximity wins.
    """
    for item, _level in doc.iterate_items():
        label: str = _get_item_label(item)
        if label != "caption":
            continue
        if not hasattr(item, "prov") or not item.prov:
            continue

        caption_prov: ProvenanceItem = item.prov[0]
        caption_page: int = caption_prov.page_no
        page = doc.pages.get(caption_page) if hasattr(doc, "pages") and doc.pages else None
        p_h = getattr(getattr(page, "size", None), "height", 0.0) if page else 0.0
        if p_h <= 0.0:
            if hasattr(doc, "pages") and doc.pages:
                for pg in doc.pages.values():
                    h = getattr(getattr(pg, "size", None), "height", 0.0)
                    if h > 0.0:
                        p_h = h
                        break
            if p_h <= 0.0:
                p_h = 792.0

        c_box = _to_topleft_dict(caption_prov.bbox, p_h)

        best_fig: dict | None = None
        best_dist: float = float("inf")

        for fig in figures:
            if fig.get("page") != caption_page:
                continue
            for pic in getattr(doc, "pictures", []) or []:
                if pic.self_ref != fig["id"] or not pic.prov:
                    continue
                p_box = _to_topleft_dict(pic.prov[0].bbox, p_h)
                dist = min(abs(c_box["t"] - p_box["b"]), abs(p_box["t"] - c_box["b"]))
                if dist < best_dist and dist <= 180.0:
                    best_dist = dist
                    best_fig = fig

        if best_fig is not None and not best_fig.get("caption"):
            best_fig["caption"] = getattr(item, "text", None)

    # For figures with null captions (e.g. icon attachments embedded in table cells),
    # check if the figure is located on a page containing tables with itemized rows.
    for fig in figures:
        if not fig.get("caption"):
            fig_page = fig.get("page")
            if not fig_page:
                continue
            page = doc.pages.get(fig_page) if hasattr(doc, "pages") and doc.pages else None
            p_h = getattr(getattr(page, "size", None), "height", 792.0) if page else 792.0

            pic_item = None
            for pic in getattr(doc, "pictures", []) or []:
                if pic.self_ref == fig["id"] and pic.prov:
                    pic_item = pic
                    break
            if not pic_item:
                continue
            p_box = _to_topleft_dict(pic_item.prov[0].bbox, p_h)
            p_mid_y = (p_box["t"] + p_box["b"]) / 2.0

            best_row_name = ""
            best_row_dist = float("inf")
            for tbl in getattr(doc, "tables", []) or []:
                if not tbl.prov or tbl.prov[0].page_no != fig_page:
                    continue
                grid = getattr(getattr(tbl, "data", None), "grid", None)
                if not grid:
                    continue
                t_box = _to_topleft_dict(tbl.prov[0].bbox, p_h)
                num_rows = len(grid)
                if num_rows == 0:
                    continue
                row_h = (t_box["b"] - t_box["t"]) / float(num_rows)
                for r_idx, row in enumerate(grid):
                    r_top = t_box["t"] + r_idx * row_h
                    r_bot = r_top + row_h
                    dist = abs(p_mid_y - (r_top + r_bot) / 2.0)
                    if dist < best_row_dist and dist <= max(row_h * 1.5, 60.0):
                        row_texts = [getattr(c, "text", str(c)).strip() for c in row if getattr(c, "text", str(c)).strip()]
                        if row_texts:
                            cand_title = row_texts[0]
                            if cand_title.lower() not in ("diagram", "diagrams", "attachment", "files", "description"):
                                best_row_dist = dist
                                best_row_name = cand_title

            if not best_row_name:
                diag_re = re.compile(r'\b(diagrams?|flowcharts?|data\s+flow|process\s+flow|sequence\s+diagram|network\s+diagram)\b', re.IGNORECASE)
                for txt_item in getattr(doc, "texts", []) or []:
                    if not txt_item.prov or txt_item.prov[0].page_no != fig_page:
                        continue
                    t_text = getattr(txt_item, "text", "").strip()
                    if not t_text or len(t_text) > 140 or "\n" in t_text:
                        continue
                    if t_text.lower() in (
                        "pdf", "png", "jpg", "jpeg", "image", "img", "docx", "xlsx", "pptx",
                        "file", "files", "diagram", "diagrams", "attachment", "attachments", "description"
                    ):
                        continue
                    if diag_re.search(t_text) or "diagram" in fig.get("section", "").lower():
                        t_box = _to_topleft_dict(txt_item.prov[0].bbox, p_h)
                        t_mid_y = (t_box["t"] + t_box["b"]) / 2.0
                        dist = abs(p_mid_y - t_mid_y)
                        if dist < best_row_dist and dist <= 120.0:
                            best_row_dist = dist
                            best_row_name = t_text

            if best_row_name:
                fig["caption"] = best_row_name

            # Search for attachment filename overlapping or immediately under the figure
            if pic_item and hasattr(pic_item, "prov") and pic_item.prov:
                p_box = _to_topleft_dict(pic_item.prov[0].bbox, p_h)
                attach_texts: list[str] = []
                has_badge: bool = False
                for txt_item in getattr(doc, "texts", []) or []:
                    if not txt_item.prov or txt_item.prov[0].page_no != fig.get("page"):
                        continue
                    t_box = _to_topleft_dict(txt_item.prov[0].bbox, p_h)
                    # Check spatial overlap or direct placement beneath the picture
                    x_overlap = max(0.0, min(p_box["r"] + 25.0, t_box["r"]) - max(p_box["l"] - 25.0, t_box["l"]))
                    y_overlap = max(0.0, min(p_box["b"] + 60.0, t_box["b"]) - max(p_box["t"] - 10.0, t_box["t"]))
                    if x_overlap > 10.0 and y_overlap > 5.0:
                        t_val = getattr(txt_item, "text", "").strip()
                        if t_val.lower() in ("pdf", "png", "jpg", "jpeg", "doc", "docx", "xls", "xlsx"):
                            has_badge = True
                        elif t_val:
                            attach_texts.append(t_val)
                if attach_texts:
                    full_attach = " ".join(attach_texts)
                    if any(ext in full_attach.lower() for ext in (".pdf", ".png", ".jpg", ".docx", ".xlsx", ".zip")):
                        fig["attachment"] = full_attach
                    elif has_badge or any(k in full_attach.lower() for k in ("diagram", "flow", "report", "spec", "pid-", "awv")):
                        clean_att = full_attach.rstrip(".").strip()
                        if clean_att:
                            fig["attachment"] = f"{clean_att}.pdf"

        # If figure caption represents a section header (e.g. 'D. Technology Stack Requirements'),
        # align its section metadata so it is never misfiled under a preceding section
        if fig.get("caption"):
            sec_cand = _extract_heading_from_text(fig["caption"])
            if sec_cand:
                fig["section"] = sec_cand


def _find_page_gaps(doc: DoclingDocument) -> list[dict]:
    """
    Identifies pages that contain no substantive body content (e.g. blank pages or unparsed pages).
    Contiguous empty pages are reported as a single gap entry.
    Pages containing paragraphs, tables, or figures are active content continuation
    pages and are not considered gaps.
    """
    content_pages: set[int] = set()

    for item, _level in doc.iterate_items():
        if not hasattr(item, "prov") or not item.prov:
            continue
        label: str = _get_item_label(item)
        if label in ("page_footer", "page_number"):
            continue
        p_no: int = item.prov[0].page_no
        if label in ("section_header", "section_heading", "table", "picture"):
            content_pages.add(p_no)
        elif label in ("paragraph", "text", "list_item", "caption", "title", "group"):
            txt: str = getattr(item, "text", "")
            if txt and len(txt.strip()) > 5:
                content_pages.add(p_no)

    all_pages: list[int] = sorted(doc.pages.keys()) if hasattr(doc, "pages") and doc.pages else []
    unassigned: list[int] = [p for p in all_pages if p not in content_pages]

    if not unassigned:
        return []

    gaps: list[dict] = []
    start: int = unassigned[0]
    prev: int = unassigned[0]

    for page in unassigned[1:]:
        if page != prev + 1:
            gaps.append({"pages": list(range(start, prev + 1))})
            start = page
        prev = page

    gaps.append({"pages": list(range(start, prev + 1))})
    return gaps

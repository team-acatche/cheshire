"""
Document element and figure lookup construction, caption attachment, and page gap detection.
"""

import base64
from io import BytesIO
from typing import Any

from docling.datamodel.document import ConversionResult
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.document import ProvenanceItem

from .constants import FOOTER_BOTTOM_MARGIN_RATIO, FOOTER_METADATA_PATTERN, MAX_CONTINUATION_PAGE_GAP
from .geometry import _get_item_label, _to_topleft_dict
from .models import ElementRef, FigureRef, ImageBoundingBox
from .tables import (
    _crop_table_as_figure,
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
) -> bool:
    """
    Detects whether an extracted item (table, paragraph, or text block)
    is actually an anomalous page footer based on spatial location in the bottom margin band
    and presence of corporate document-control metadata.
    """
    if page_h <= 0.0 or not hasattr(item, "prov") or not item.prov:
        return False

    prov: ProvenanceItem = item.prov[0]
    if not prov.bbox:
        return False

    tb = _to_topleft_dict(prov.bbox, page_h)
    # Must be located in the bottom margin band of the page
    if tb["t"] < page_h * FOOTER_BOTTOM_MARGIN_RATIO and tb["b"] < page_h * FOOTER_BOTTOM_MARGIN_RATIO:
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

    for item, _level in doc.iterate_items():
        if not hasattr(item, "prov") or not item.prov:
            continue

        label: str = _get_item_label(item)

        # Skip decorative page elements (headers, footers)
        if label in ("picture", "page_header", "page_footer"):
            continue

        # Track section boundaries to scope continuation headers
        if label in ("section_header", "section_heading"):
            _current_section = getattr(item, "text", "")
            _last_table_header = None

        prov: ProvenanceItem = item.prov[0]
        page: Any = doc.pages.get(prov.page_no)
        if page is None or page.size is None:
            continue

        # Skip anomalous tabular or columnar footers mislabeled as table/paragraph/text
        if _is_footer_element(item, doc, page.size.height):
            continue

        bbox_px: ImageBoundingBox = ImageBoundingBox.from_docling_bbox(prov.bbox, page.size.height, scale)

        text: str = ""
        if label == "table":
            # Detect continuation table status based on adjacent page in same section
            is_adjacent_page: bool = (
                _last_table_header is not None and 0 <= (prov.page_no - _last_table_page) <= MAX_CONTINUATION_PAGE_GAP
            )
            text, _last_table_header = _format_table_markdown(
                item, doc, _last_table_header, is_adjacent_page
            )
            _last_table_page = prov.page_no

            # Selective table cropping for tables with empty cells or extraction clipping
            if _table_needs_visual_crop(item, text, page.size.height):
                fig_id: str | None = _crop_table_as_figure(
                    result, prov, item.self_ref, scale, figure_lookup
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
        label: str = _get_item_label(item)
        if label != "caption":
            continue
        if not hasattr(item, "prov") or not item.prov:
            continue

        caption_prov: ProvenanceItem = item.prov[0]
        caption_page: int = caption_prov.page_no
        caption_top: float = caption_prov.bbox.t  # top of caption in PDF space

        best_fig: dict | None = None
        best_dist: float = float("inf")

        for fig in figures:
            if fig["page"] != caption_page:
                continue
            for pic in doc.pictures:
                if pic.self_ref != fig["id"] or not pic.prov:
                    continue
                fig_bottom: float = pic.prov[0].bbox.b  # bottom of figure in PDF space
                dist: float = caption_top - fig_bottom  # positive = caption below figure
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
        label: str = _get_item_label(item)
        if label in ("section_header", "section_heading") and hasattr(item, "prov") and item.prov:
            section_pages.add(item.prov[0].page_no)

    all_pages: list[int] = sorted(doc.pages.keys())
    unassigned: list[int] = [p for p in all_pages if p not in section_pages]

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

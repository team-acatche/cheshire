"""
Multistep preprocessing helper package.

Organized into focused submodules:
- constants: Configuration constants for sizing, padding, and thresholds.
- models: Domain dataclasses and Pydantic validation models.
- geometry: Bounding box normalization, top-left conversion, and overlap calculations.
- tables: Table bounding, compound column splitting, and markdown table rendering.
- elements: Document element/figure lookups, caption attachment, and page gaps.
- chunking: Hierarchical chunking, section merging, and visual figure attachment.
- indexing: Structural document map extraction and page indexing.
"""

from .chunking import (
    _attach_figures_by_page,
    _extract_section_key,
    _merge_chunk_pair,
    _propagate_section_figures,
    build_chunks,
    merge_chunks,
)
from .constants import (
    COLUMN_SPLIT_RATIO,
    DEFAULT_COL_WIDTH_PX,
    DEFAULT_IMAGE_SCALE,
    DEFAULT_MAX_CHUNK_CHARS,
    DEFAULT_ROW_HEIGHT_PX,
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
from .elements import (
    _attach_captions,
    _build_element_lookup,
    _build_figure_lookup,
    _find_page_gaps,
)
from .geometry import (
    _compute_box_overlap,
    _get_item_label,
    _to_topleft_dict,
)
from .indexing import (
    build_document_index,
)
from .models import (
    ElementRef,
    EvaluationChunk,
    FigureRef,
    ImageBoundingBox,
    LocalFinding,
)
from .tables import (
    _calculate_extended_col_bounds,
    _calculate_extended_row_bounds,
    _crop_table_as_figure,
    _detect_compound_header_split,
    _detect_table_column_splits,
    _extract_header_from_table_text,
    _format_cell_with_icons,
    _format_table_markdown,
    _format_table_row_cells,
    _get_table_cell_bounds,
    _sanitize_table_cell_text,
    _table_has_empty_cells,
    _table_needs_visual_crop,
)

__all__ = [
    # Constants
    "DEFAULT_ROW_HEIGHT_PX",
    "LAST_ROW_BOTTOM_PADDING_PX",
    "DEFAULT_COL_WIDTH_PX",
    "LAST_COL_RIGHT_PADDING_PX",
    "MIN_ICON_OVERLAP_PX",
    "MAX_CONTINUATION_PAGE_GAP",
    "MAX_HEADER_SEARCH_LINES",
    "MAX_TABLE_RIGHT_GAP_PX",
    "MIN_TABLE_CELL_COVERAGE_RATIO",
    "MIN_WIDE_TABLE_WIDTH_PX",
    "WIDE_TABLE_ASPECT_RATIO",
    "COLUMN_SPLIT_RATIO",
    "MIN_COMPOUND_COL_WIDTH_PX",
    "INDEPENDENT_HEADER_KEYWORDS",
    "DEFAULT_MAX_CHUNK_CHARS",
    "DEFAULT_IMAGE_SCALE",
    # Models
    "ImageBoundingBox",
    "ElementRef",
    "FigureRef",
    "LocalFinding",
    "EvaluationChunk",
    # Geometry
    "_get_item_label",
    "_to_topleft_dict",
    "_compute_box_overlap",
    # Tables
    "_calculate_extended_row_bounds",
    "_calculate_extended_col_bounds",
    "_get_table_cell_bounds",
    "_detect_compound_header_split",
    "_detect_table_column_splits",
    "_table_has_empty_cells",
    "_table_needs_visual_crop",
    "_sanitize_table_cell_text",
    "_crop_table_as_figure",
    "_format_cell_with_icons",
    "_format_table_row_cells",
    "_extract_header_from_table_text",
    "_format_table_markdown",
    # Elements
    "_build_figure_lookup",
    "_build_element_lookup",
    "_attach_captions",
    "_find_page_gaps",
    # Chunking
    "_extract_section_key",
    "_merge_chunk_pair",
    "merge_chunks",
    "_attach_figures_by_page",
    "_propagate_section_figures",
    "build_chunks",
    # Indexing
    "build_document_index",
]

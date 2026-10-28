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
from .hierarchy import (
    HeaderHierarchyResolver,
    HeaderToken,
    ScopeLevel,
    Segment,
    SeqType,
    parse_header_token,
)
from .constants import (
    COLUMN_SPLIT_RATIO,
    DEFAULT_COL_WIDTH_PX,
    DEFAULT_IMAGE_SCALE,
    DEFAULT_MAX_CHUNK_CHARS,
    DEFAULT_ROW_HEIGHT_PX,
    FOOTER_BOTTOM_MARGIN_RATIO,
    FOOTER_MAX_TOP_RATIO,
    FOOTER_METADATA_PATTERN,
    INDEPENDENT_HEADER_KEYWORDS,
    LAST_COL_RIGHT_PADDING_PX,
    LAST_ROW_BOTTOM_PADDING_PX,
    MAX_CONTINUATION_PAGE_GAP,
    MAX_HEADER_SEARCH_LINES,
    MAX_TABLE_RIGHT_GAP_PX,
    MIN_COMPOUND_COL_WIDTH_PX,
    MIN_ICON_OVERLAP_PX,
    BOOLEAN_LITERAL_STRINGS,
    FALLBACK_VALUE_LEN_DIVERGENCE,
    FALLBACK_VALUE_WORD_DIVERGENCE,
    FASTEMBED_TABLE_MODEL,
    FASTEMBED_TABLE_SIMILARITY_THRESHOLD,
    HORIZONTAL_TABLE_MIN_ROWS,
    HORIZONTAL_TABLE_NUM_COLS,
    MIN_TABLE_CELL_COVERAGE_RATIO,
    MIN_WIDE_TABLE_WIDTH_PX,
    NLI_ENTAILMENT_THRESHOLD,
    WIDE_TABLE_ASPECT_RATIO,
)
from .elements import (
    _attach_captions,
    _build_element_lookup,
    _build_figure_lookup,
    _find_page_gaps,
    _is_footer_element,
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
    _detect_document_footer_top,
    _detect_table_column_splits,
    _extract_header_from_table_text,
    _format_cell_with_icons,
    _format_table_markdown,
    _format_table_row_cells,
    _get_table_cell_bounds,
    _is_category_divider_row,
    _is_table_footer_row,
    _sanitize_table_cell_text,
    _table_has_empty_cells,
    _table_needs_visual_crop,
    _infer_cell_value_type,
    _classify_with_fastembed,
    _classify_with_nli_relation,
    _compute_cosine_similarity,
    is_horizontal_two_column_table,
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
    "FOOTER_BOTTOM_MARGIN_RATIO",
    "FOOTER_MAX_TOP_RATIO",
    "FOOTER_METADATA_PATTERN",
    "DEFAULT_MAX_CHUNK_CHARS",
    "HORIZONTAL_TABLE_MIN_ROWS",
    "HORIZONTAL_TABLE_NUM_COLS",
    "NLI_ENTAILMENT_THRESHOLD",
    "FASTEMBED_TABLE_MODEL",
    "FASTEMBED_TABLE_SIMILARITY_THRESHOLD",
    "FALLBACK_VALUE_LEN_DIVERGENCE",
    "FALLBACK_VALUE_WORD_DIVERGENCE",
    "BOOLEAN_LITERAL_STRINGS",
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
    "_detect_document_footer_top",
    "_detect_table_column_splits",
    "_table_has_empty_cells",
    "_table_needs_visual_crop",
    "_sanitize_table_cell_text",
    "_crop_table_as_figure",
    "_format_cell_with_icons",
    "_format_table_row_cells",
    "_extract_header_from_table_text",
    "_format_table_markdown",
    "_is_category_divider_row",
    "_is_table_footer_row",
    "_infer_cell_value_type",
    "_classify_with_fastembed",
    "_classify_with_nli_relation",
    "_compute_cosine_similarity",
    "is_horizontal_two_column_table",
    # Elements
    "_build_figure_lookup",
    "_build_element_lookup",
    "_attach_captions",
    "_find_page_gaps",
    "_is_footer_element",
    # Chunking
    "_extract_section_key",
    "_merge_chunk_pair",
    "merge_chunks",
    "_attach_figures_by_page",
    "_propagate_section_figures",
    "build_chunks",
    # Indexing
    "build_document_index",
    # hierarchy
    "HeaderHierarchyResolver",
    "HeaderToken",
    "ScopeLevel",
    "Segment",
    "SeqType",
    "parse_header_token",
]

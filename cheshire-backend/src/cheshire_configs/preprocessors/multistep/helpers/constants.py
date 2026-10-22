"""
Configuration constants for multistep preprocessing, table formatting, and chunking.
"""

# Bounding box default dimensions and padding (in rendered page pixel space)
DEFAULT_ROW_HEIGHT_PX: float = 40.0
LAST_ROW_BOTTOM_PADDING_PX: float = 15.0
DEFAULT_COL_WIDTH_PX: float = 50.0
LAST_COL_RIGHT_PADDING_PX: float = 20.0

# Embedded visual icon detection overlap threshold (in rendered page pixels)
MIN_ICON_OVERLAP_PX: float = 10.0

# Continuation table tracking limits
MAX_CONTINUATION_PAGE_GAP: int = 1
MAX_HEADER_SEARCH_LINES: int = 4

# Compound header column splitting parameters
COLUMN_SPLIT_RATIO: float = 0.5
MIN_COMPOUND_COL_WIDTH_PX: float = 120.0

# Keywords denoting independent auxiliary table columns that commonly merge with primary columns
INDEPENDENT_HEADER_KEYWORDS: frozenset[str] = frozenset({
    "link", "links", "url", "urls",
    "format", "attachment", "attachments",
})

# Default text scale and chunk length thresholds
DEFAULT_MAX_CHUNK_CHARS: int = 4000
DEFAULT_IMAGE_SCALE: float = 2.0

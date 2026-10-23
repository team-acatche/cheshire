"""
Configuration constants for multistep preprocessing, table formatting, and chunking.
"""

import re

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

# Table cell coverage and clipping detection thresholds
MIN_TABLE_CELL_COVERAGE_RATIO: float = 0.85
MAX_TABLE_RIGHT_GAP_PX: float = 30.0
MIN_WIDE_TABLE_WIDTH_PX: float = 300.0
WIDE_TABLE_ASPECT_RATIO: float = 2.5

# Page footer spatial and metadata detection thresholds
FOOTER_BOTTOM_MARGIN_RATIO: float = 0.85
FOOTER_METADATA_PATTERN: re.Pattern[str] = re.compile(
    r"(?i)\b("
    r"classification\s*:"
    r"|confidential\b"
    r"|internal\s+use\s+only\b"
    r"|strictly\s+confidential\b"
    r"|document\s+owner\s*:"
    r"|doc\s+owner\s*:"
    r"|document\s+title\s*:"
    r"|doc\s+title\s*:"
    r"|document\s+id\s*:"
    r"|page\s+no\.?\s*:"
    r"|page\s+\d+\s+of\s+\d+"
    r"|all\s+rights\s+reserved"
    r")"
)

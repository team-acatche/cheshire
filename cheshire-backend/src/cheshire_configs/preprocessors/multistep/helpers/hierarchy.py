"""
header hierarchy resolution and outline sequence parsing using an active scope stack.
supports uppercase, lowercase, numeric, compound, and unnumbered section identifiers.
"""

from dataclasses import dataclass
from enum import Enum
import re


class SeqType(Enum):
    numeric = "numeric"
    upper_alpha = "upper_alpha"
    lower_alpha = "lower_alpha"
    roman_upper = "roman_upper"
    roman_lower = "roman_lower"
    compound = "compound"
    unnumbered = "unnumbered"


@dataclass(frozen=True)
class Segment:
    kind: SeqType
    val: int
    raw: str


@dataclass
class HeaderToken:
    raw_heading: str
    title: str
    segments: list[Segment]
    prefix_label: str
    root_key: str
    is_unnumbered: bool = False


@dataclass
class ScopeLevel:
    token: HeaderToken
    raw_heading: str
    title: str
    root_key: str
    depth: int
    max_child_val: int = 0


def _parse_roman(s: str) -> int | None:
    # parse roman numeral string into an integer value
    roman_map = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    s_lower = s.lower()
    # validate standard roman numeral pattern
    if not re.match(r"^m{0,4}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$", s_lower):
        return None
    total = 0
    prev_val = 0
    for char in reversed(s_lower):
        val = roman_map.get(char, 0)
        if val < prev_val:
            total -= val
        else:
            total += val
            prev_val = val
    return total if total > 0 else None


def _alpha_to_int(s: str) -> int:
    # convert alphabetic string to integer (e.g. a=1, z=26, aa=27)
    val = 0
    for char in s.lower():
        val = val * 26 + (ord(char) - ord("a") + 1)
    return val


def _parse_segment(seg_str: str) -> Segment:
    # parse single segment string into typed segment instance
    if not seg_str:
        return Segment(kind=SeqType.unnumbered, val=0, raw="")

    # numeric segment (capped at 999 to reject port numbers, year numbers, etc.)
    if seg_str.isdigit():
        val = int(seg_str)
        if val <= 999:
            return Segment(kind=SeqType.numeric, val=val, raw=seg_str)
        return Segment(kind=SeqType.unnumbered, val=0, raw=seg_str)

    # roman numeral check (prefer multi-character roman e.g. II, III, IV)
    roman_val = _parse_roman(seg_str)
    if roman_val is not None and len(seg_str) > 1:
        kind = SeqType.roman_upper if seg_str.isupper() else SeqType.roman_lower
        return Segment(kind=kind, val=roman_val, raw=seg_str)

    # uppercase alphabetic segment: strictly single letter or repeated double letter (e.g. AA, BB)
    if seg_str.isalpha() and seg_str.isupper():
        if len(seg_str) == 1:
            val = ord(seg_str) - ord("A") + 1
            return Segment(kind=SeqType.upper_alpha, val=val, raw=seg_str)
        elif len(seg_str) == 2 and seg_str[0] == seg_str[1]:
            val = 26 + (ord(seg_str[0]) - ord("A") + 1)
            return Segment(kind=SeqType.upper_alpha, val=val, raw=seg_str)
        return Segment(kind=SeqType.unnumbered, val=0, raw=seg_str)

    # lowercase alphabetic segment: strictly single letter or repeated double letter
    if seg_str.isalpha() and seg_str.islower():
        if len(seg_str) == 1:
            val = ord(seg_str) - ord("a") + 1
            return Segment(kind=SeqType.lower_alpha, val=val, raw=seg_str)
        elif len(seg_str) == 2 and seg_str[0] == seg_str[1]:
            val = 26 + (ord(seg_str[0]) - ord("a") + 1)
            return Segment(kind=SeqType.lower_alpha, val=val, raw=seg_str)
        return Segment(kind=SeqType.unnumbered, val=0, raw=seg_str)

    # fallback unnumbered value
    return Segment(kind=SeqType.unnumbered, val=0, raw=seg_str)


def _split_identifier_to_segments(ident_str: str) -> list[Segment]:
    # split an identifier string into atomic segment tokens
    parts = [p for p in re.split(r"[\.\-_/]+", ident_str) if p]
    segments: list[Segment] = []
    for part in parts:
        # if part combines letters and digits like e1 or 1a, split them
        sub_parts = re.findall(r"[A-Za-z]+|\d+", part)
        for sp in sub_parts:
            segments.append(_parse_segment(sp))
    return segments


def _is_spurious_heading(text: str) -> bool:
    """
    Identifies text that represents table header rows, status/choice selectors,
    pipe-separated table lines, or document metadata fields, which should never
    be treated as document section headings.
    """
    if not text:
        return True
    clean = text.strip()
    if not clean:
        return True

    # 0. Ellipsis, prompt, or truncation indicators at the end
    if clean.endswith("..") or clean.endswith("...") or clean.endswith("…"):
        return True

    # 0b. Isolated table column header keywords without outline numbering
    clean_lower = clean.lower().rstrip(":")
    if clean_lower in (
        "diagram", "diagrams", "attachment", "attachments", "file", "files",
        "description", "class/module", "class", "module", "role", "changes",
        "revised by", "version", "date", "status", "link", "links", "reference", "references"
    ):
        return True

    # 1. Pipe-separated table rows or markdown syntax
    if clean.startswith("|") or clean.endswith("|") or clean.count("|") >= 2:
        return True

    # 2. Option/choice slash indicators: (N)ew / (E)xisting, (Y/N), (N)ew /, etc.
    if re.search(r"\([A-Za-z0-9]+\)[a-zA-Z]*\s*/", clean) or clean.endswith("/"):
        return True
    if re.search(r"\b(?:new\s*/\s*existing|yes\s*/\s*no|read\s*/\s*write|mandatory\s*/\s*optional)\b", clean, re.IGNORECASE):
        return True

    # 3. Concatenated table column headers (multiple column descriptors in a single line)
    col_keywords = re.findall(
        r"\b(?:description|attachment|attachments|class/module|module|class|status|comments?|date|version|file|files|service\s+name|user/group|role|access\s+type|link|repository\s+link|activity|activities|manhours?|hours?|estimates?)\b",
        clean,
        re.IGNORECASE,
    )
    if len(col_keywords) >= 2:
        return True

    # 4. Document-level tracking / metadata fields (headers, footers, classification banners)
    if re.match(
        r"^(?:classification|document\s+title|document\s+owner|page\s+no|tracking\s+number|tracking\s+information|project\s+owner|primary\s+rsc|related\s+rsc|date\s+prepared|version\s+history|sign-offs?|prepared\s+by|approved\s+by)\b",
        clean,
        re.IGNORECASE,
    ):
        return True

    return False


def _is_genuine_identifier(cand: str, full_str: str) -> bool:
    # determine if candidate token is an outline identifier or normal word / filename
    if not cand:
        return False
    # reject file extensions
    if re.search(r"\.(?:pdf|sql|json|yaml|yml|xml|txt|csv|docx|png|jpg|jpeg|gif|zip|tar|gz|sh|py|java|cs|ts|js)$", cand, re.IGNORECASE):
        return False
    if re.search(r"\.(?:pdf|sql|json|yaml|yml|xml|txt|csv|docx)\b", full_str, re.IGNORECASE):
        return False
    if "\\" in full_str or "//" in full_str or "C:/" in full_str or "c:/" in full_str:
        return False
    # all digits is an identifier if <= 999
    if cand.isdigit():
        return int(cand) <= 999
    # single letter
    if len(cand) == 1 and cand.isalpha():
        return True
    # repeated double letter (e.g. AA, BB)
    if len(cand) == 2 and cand.isalpha() and cand[0] == cand[1]:
        return True
    # multi-letter roman numeral
    if _parse_roman(cand) is not None and len(cand) > 1:
        return True
    # mixed letters and digits (e.g. E1, 1a, E12)
    has_digit = any(c.isdigit() for c in cand)
    has_alpha = any(c.isalpha() for c in cand)
    if has_digit and has_alpha and not any(c in cand for c in (".", "-", "_", "/")):
        alpha_count = sum(1 for c in cand if c.isalpha())
        digit_count = sum(1 for c in cand if c.isdigit())
        if alpha_count <= 2 and digit_count <= 3:
            return True
    # compound tokens with delimiters: each sub-part must be a valid outline segment
    if any(c in cand for c in (".", "-", "_", "/")):
        parts = [p for p in re.split(r"[\.\-_/]+", cand) if p]
        if not parts:
            return False
        for p in parts:
            if p.isdigit():
                if int(p) > 999:
                    return False
            elif len(p) == 1 and p.isalpha():
                continue
            elif _parse_roman(p) is not None and len(p) > 1:
                continue
            else:
                return False
        return True
    return False


INVISIBLE_CHARS_RE = re.compile(r'[\u200b\u200c\u200d\u200e\u200f\ufeff\u2060\u2061\u2062\u2063\u2064\xad]')


def _normalize_heading_text(s: str) -> str:
    """
    Normalizes heading text by stripping zero-width spaces, invisible formatting characters,
    non-breaking spaces, and collapsing excess whitespace.
    """
    if not s:
        return ""
    cleaned = INVISIBLE_CHARS_RE.sub(" ", s).replace("\u00a0", " ")
    collapsed = " ".join(cleaned.split())
    # Collapse isolated space before dot or colon for section tokens (e.g. 'F .' -> 'F.')
    return re.sub(r"\b([A-Za-z]|\d+)\s+([\.:])(?=\s|$)", r"\1\2", collapsed)


def parse_header_token(heading: str) -> HeaderToken:
    # parse a raw heading string into a structured header token
    clean = _normalize_heading_text(heading)
    if not clean or _is_spurious_heading(clean):
        return HeaderToken(
            raw_heading=clean,
            title="",
            segments=[],
            prefix_label="",
            root_key="",
            is_unnumbered=True,
        )

    # check if heading is already a breadcrumb like "e. processing - 1. modules"
    if " - " in clean:
        first_part = clean.split(" - ")[0].strip()
        first_token = parse_header_token(first_part)
        if not first_token.is_unnumbered and first_token.root_key and first_token.title:
            return HeaderToken(
                raw_heading=clean,
                title=clean,
                segments=first_token.segments,
                prefix_label=first_token.prefix_label,
                root_key=first_token.root_key,
                is_unnumbered=False,
            )

    # reject multiple choice, status indicators, or table header legend slashes like (N)ew / (E)xisting or (Y/N)
    if re.search(r"\([A-Za-z0-9]+\)[a-zA-Z]*\s*/\s*\([A-Za-z0-9]+\)", clean):
        return HeaderToken(
            raw_heading=clean,
            title=clean,
            segments=[],
            prefix_label="",
            root_key="",
            is_unnumbered=True,
        )

    # strip optional structural prefix words like section or appendix
    working_str = clean
    prefix_word_match = re.match(
        r"^(?:section|appendix|annex|chapter|part|article|schedule)\s+",
        working_str,
        re.IGNORECASE,
    )
    if prefix_word_match:
        working_str = working_str[prefix_word_match.end():].strip()

    # check parenthesized identifier: e.g. (1), (a), (1.1) requiring whitespace before title if present
    paren_match = re.match(r"^\(([A-Za-z0-9]+(?:[\.\-_][A-Za-z0-9]+)*)\)(?:\s+(.*)|$)", working_str)
    if paren_match:
        raw_id = paren_match.group(1)
        title = (paren_match.group(2) or "").strip().rstrip(":")
        segments = _split_identifier_to_segments(raw_id)
        root_key = segments[0].raw if segments else raw_id
        return HeaderToken(
            raw_heading=clean,
            title=title,
            segments=segments,
            prefix_label=raw_id,
            root_key=root_key,
        )

    # check identifier followed by explicit delimiter (., -, :, ), /) or whitespace
    # e.g. "e. processing", "a - section", "1) modules", "1.1 specification", "e1 modules"
    delim_match = re.match(
        r"^([A-Za-z0-9]+(?:[\.\-_/][A-Za-z0-9]+)*)(?:[\.\-:\)\/\s]+)(.*)$",
        working_str,
    )
    if delim_match:
        candidate_id = delim_match.group(1)
        rem_title = delim_match.group(2).strip().rstrip(":")

        if _is_genuine_identifier(candidate_id, working_str):
            segments = _split_identifier_to_segments(candidate_id)
            if segments:
                root_key = segments[0].raw
                return HeaderToken(
                    raw_heading=clean,
                    title=rem_title,
                    segments=segments,
                    prefix_label=candidate_id,
                    root_key=root_key,
                )

    # check standalone identifier without trailing title (e.g. "section e" or "1.1")
    lone_match = re.match(r"^([A-Za-z0-9]+(?:[\.\-_/][A-Za-z0-9]+)*)[\.\-:\)]*$", working_str)
    if lone_match:
        candidate_id = lone_match.group(1)
        if _is_genuine_identifier(candidate_id, working_str):
            segments = _split_identifier_to_segments(candidate_id)
            if segments:
                root_key = segments[0].raw
                return HeaderToken(
                    raw_heading=clean,
                    title="",
                    segments=segments,
                    prefix_label=candidate_id,
                    root_key=root_key,
                )

    # unnumbered header fallback
    return HeaderToken(
        raw_heading=clean,
        title=clean,
        segments=[],
        prefix_label="",
        root_key="",
        is_unnumbered=True,
    )


def _eval_single_line_heading(line: str) -> str | None:
    # evaluates whether a clean single line matches standard outline heading grammar
    if not line or _is_spurious_heading(line):
        return None

    clean = _normalize_heading_text(line)
    if not clean or len(clean) > 140:
        return None

    # reject bullet characters, list markers, and arrows
    if clean[0] in ("•", "◦", "▪", "▫", "*", "–", "—", ">", "→") and not re.match(r"^[A-Za-z0-9]", clean):
        return None

    # reject file extensions and filesystem paths
    if re.search(r"\.(?:pdf|sql|json|yaml|yml|xml|txt|csv|docx)\b", clean, re.IGNORECASE):
        return None
    if "\\" in clean or "//" in clean or "C:/" in clean or "c:/" in clean:
        return None

    # reject multiple choice selectors, status abbreviations, or table option slashes like (N)ew / (E)xisting or (Y/N)
    if re.search(r"\([A-Za-z0-9]+\)[a-zA-Z]*\s*/\s*\([A-Za-z0-9]+\)", clean):
        return None

    clean_line = clean.rstrip(":")

    # reject concatenated table column headers with multiple column descriptors
    if len(re.findall(r"\b(?:description|attachment|attachments|class/module|module|class|status|comments?|date|version)\b", clean_line, re.IGNORECASE)) >= 2:
        return None

    # 1. Structural prefix keyword: e.g. "Section 1. Overview", "Appendix A - Notes", "Section B", "SECTION B"
    prefix_match = re.match(
        r"^(?:section|chapter|part|appendix|annex|article|schedule)\s+([A-Za-z0-9]+(?:[\.\-_][A-Za-z0-9]+)*)(?:(?:\s*[\.\-–—:]\s*|\s+)(\S.*))?$",
        clean_line,
        re.IGNORECASE,
    )
    if prefix_match:
        title = (prefix_match.group(2) or "").strip().rstrip(":")
        if not title:
            return clean_line
        words = title.split()
        if len(words) <= 15 and not re.search(r"\.\s+[A-Z]", title):
            return clean_line

    # 2. Compound Alphanumeric Outline: e.g. "E.1 Modules", "E.2 - Database Design", "1.A Overview", "A.1.1 Detail", "(1.1) Detail"
    compound_seg = r"(?:[A-Za-z]|\d+|[IVXLCDMivxlcdm]+)"
    compound_match = (
        re.match(rf"^\(({compound_seg}(?:[\.\-_]{compound_seg})+)\)\s+(\S.*)$", clean_line)
        or re.match(rf"^({compound_seg}(?:[\.\-_]{compound_seg})+)(?:\s*[\.\-–—:]\s*|\s+)(\S.*)$", clean_line)
    )
    if compound_match:
        cand_id = compound_match.group(1)
        if _is_genuine_identifier(cand_id, clean_line):
            title = compound_match.group(2).strip().rstrip(":")
            words = title.split()
            if len(words) <= 14 and not re.search(r"\.\s+[A-Z]", title):
                if not title.endswith(".") or len(words) <= 6:
                    return clean_line

    # 3. Uppercase Alphabetic Outline: strictly single letter e.g. "A. Primary Title", "B. Secondary Title", "B - Design", "(A) Scope"
    alpha_match = (
        re.match(r"^\(([A-Z])\)\s+(\S.*)$", clean_line)
        or re.match(r"^([A-Z])\s*[\.\-–—:]\s+(\S.*)$", clean_line)
        or re.match(r"^([B-HJ-Z])\s+([A-Z][a-zA-Z0-9].*)$", clean_line)
        or re.match(r"^([AI])\s+([A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+)*)$", clean_line)
    )
    if alpha_match:
        title = alpha_match.group(2).strip().rstrip(":")
        words = title.split()
        if len(words) <= 12 and not re.search(r"\.\s+[A-Z]", title):
            if not title.endswith(".") or len(words) <= 6:
                return clean_line

    # 4. Numeric or Decimal Outline: e.g. "1. Outline Unit", "2. Component Design", "1.1 Architecture", "(1) Unit"
    num_match = (
        re.match(r"^\((\d+(?:\.\d+)*)\)\s+(\S.*)$", clean_line)
        or re.match(r"^(\d+(?:\.\d+)+)(?:\s*[\.\-–—:]\s*|\s+)(\S.*)$", clean_line)
        or re.match(r"^(\d+)\s*[\.\-–—:]\s+(\S.*)$", clean_line)
        or re.match(r"^(\d+)\s+([A-Z][a-zA-Z0-9].*)$", clean_line)
    )
    if num_match:
        title = (num_match.group(2) or "").strip().rstrip(":")
        words = title.split()
        if len(words) <= 12 and not re.search(r"\.\s+[A-Z]", title):
            if not (title.endswith(".") and len(words) > 4):
                return clean_line

    # 5. Roman Numeral Outline: multi-letter e.g. "II. Overview", "IV. Specifications", "(II) Implementation", "III - Testing"
    roman_match = (
        re.match(r"^\(([IVXLCDM]+)\)\s+(\S.*)$", clean_line)
        or re.match(r"^([IVXLCDM]+)\s*[\.\-–—:]\s+(\S.*)$", clean_line)
    )
    if roman_match:
        roman_cand = roman_match.group(1)
        if _parse_roman(roman_cand) is not None and len(roman_cand) > 1:
            title = roman_match.group(2).strip().rstrip(":")
            words = title.split()
            if len(words) <= 12 and not re.search(r"\.\s+[A-Z]", title):
                return clean_line

    return None


def _extract_heading_from_text(raw_text: str) -> str | None:
    # extracts a structural section heading candidate from raw text using outline syntax and layout heuristics.
    # returns the clean heading string if valid, or none if text is narrative body content, a list item, or table cell.
    # strictly logic-dependent; uses zero domain-specific or document-specific wordlists.
    if not raw_text:
        return None

    # Clean invisible characters first
    cleaned = _normalize_heading_text(raw_text)
    if not cleaned:
        return None

    # Fast path for single line
    if "\n" not in raw_text and "\r" not in raw_text:
        return _eval_single_line_heading(cleaned)

    # Multi-line handling
    raw_lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    lines = [_normalize_heading_text(l) for l in raw_lines if _normalize_heading_text(l)]
    if not lines:
        return None

    # 1. Try 2-line heading where line 0 is a standalone label (e.g. 'B.' or 'Section B') and line 1 is title
    if len(lines) >= 2:
        l0, l1 = lines[0], lines[1]
        if len(l0) <= 20 and len(l1) <= 80 and not l1.endswith("."):
            if re.match(r"^(?:(?:section|chapter|part|appendix|annex|article|schedule)\s+)?[A-Za-z0-9]+(?:[\.\-_][A-Za-z0-9]+)*(?:\s*[\.\-–—:\)])?\s*$", l0, re.IGNORECASE):
                stitched_cand = _eval_single_line_heading(f"{l0} {l1}")
                if stitched_cand:
                    return stitched_cand

    # 2. Check heading at the beginning of the text block (line 0 or line 1)
    for l in lines[:2]:
        cand = _eval_single_line_heading(l)
        if cand:
            return cand
    if len(lines) >= 3 and lines[0].endswith(":") and len(lines[0].split()) <= 6:
        cand = _eval_single_line_heading(lines[2])
        if cand:
            return cand

    return None


class HeaderHierarchyResolver:
    # stack-based header hierarchy resolver tracking active parent scopes
    def __init__(self):
        self.stack: list[ScopeLevel] = []

    def reset(self) -> None:
        # clear active stack state
        self.stack = []

    def get_root_key(self) -> str | None:
        # return root section key of the current active branch
        return self.stack[0].root_key if self.stack else None

    def get_root_heading(self) -> str | None:
        # return root section title of the current active branch
        return self.stack[0].raw_heading if self.stack else None

    def get_current_breadcrumb(self) -> str:
        # return joined breadcrumb of open headers
        return " - ".join(level.raw_heading for level in self.stack)

    def _find_same_level_update(self, token: HeaderToken) -> int | None:
        """
        Detects if a heading shares the exact same sequence segments as an open level in the stack,
        indicating a title update or subtopic change for that level (e.g.
        '4. Reports - Audit and Provenance Logs' -> '4. Reports - Operational and Compliance Reports').
        """
        if not token.segments:
            return None
        for idx in range(len(self.stack) - 1, -1, -1):
            anc = self.stack[idx]
            if anc.token.segments and len(anc.token.segments) == len(token.segments):
                if all(
                    token.segments[i].kind == anc.token.segments[i].kind
                    and token.segments[i].val == anc.token.segments[i].val
                    for i in range(len(token.segments))
                ):
                    return idx
        return None

    def is_stale_heading(self, heading: str) -> bool:
        """
        Determines whether a heading candidate (e.g. from Docling's chunk.meta.headings)
        is stale or regressive relative to the active hierarchy scope stack.
        Returns True if the heading refers to an already closed or prior section/sequence,
        or False if it matches the current scope, advances a major sequence, or is a valid child/sibling.
        """
        if not self.stack:
            return False
        clean = _normalize_heading_text(heading)
        if not clean or _is_spurious_heading(clean):
            return True
        token = parse_header_token(clean)
        if token.is_unnumbered or not token.segments:
            return False
        # If the root of the stack is unnumbered (preamble, document title, cover page),
        # any incoming structured/numbered heading is NEVER stale and replaces the unnumbered root.
        if self.stack and (self.stack[0].token.is_unnumbered or not self.stack[0].token.segments):
            return False
        # Matches currently open level
        if self._find_matching_level(token, clean) is not None:
            return False
        # Compound descendant of an open ancestor
        if self._find_compound_ancestor(token) is not None:
            return False
        # Same sequence index update (e.g. new title for same level)
        if self._find_same_level_update(token) is not None:
            return False
        # Valid sibling continuation
        if self._find_sibling_level(token) is not None:
            return False
        # Sequence reset (e.g. restarts at 1) of an existing subordinate level
        if self._find_reset_level(token) is not None:
            return False
        # Check if new token has a sequence kind matching an open level with val <= open_level.val
        if self.stack and token.segments:
            new_seg = token.segments[0]
            for anc in self.stack:
                if anc.token.segments:
                    anc_seg = anc.token.segments[0]
                    if new_seg.kind == anc_seg.kind and new_seg.val < anc_seg.val:
                        return True

        # Subordinate sequence under current stack top
        if self.stack and self.stack[-1].token.segments and token.segments:
            parent = self.stack[-1]
            root_seg = self.stack[0].token.segments[0] if self.stack[0].token.segments else None
            is_same_kind_as_root = bool(root_seg and token.segments[0].kind == root_seg.kind)
            if not is_same_kind_as_root:
                first_val = token.segments[0].val
                last_val = token.segments[-1].val
                if parent.max_child_val == 0:
                    parent_val = parent.token.segments[0].val if parent.token.segments else 0
                    if (1 <= first_val <= 2 or 1 <= last_val <= 2) or (parent_val > 0 and (first_val >= parent_val or last_val >= parent_val)):
                        return False
                else:
                    if first_val >= parent.max_child_val or last_val >= parent.max_child_val:
                        return False
        # Major sequence advance (e.g. Section F -> G, D -> E.1, or 1 -> B)
        if self.stack[0].token.segments and token.segments:
            root_seg_curr = self.stack[0].token.segments[0]
            root_seg_new = token.segments[0]
            if root_seg_curr.kind == SeqType.upper_alpha and root_seg_new.kind == SeqType.roman_upper and len(root_seg_new.raw) == 1:
                alpha_val = _alpha_to_int(root_seg_new.raw)
                gap = alpha_val - root_seg_curr.val
                if 0 < gap <= 2:
                    return False
            if root_seg_curr.raw.upper() in ("I", "V", "X") and root_seg_new.kind == SeqType.roman_upper:
                c_rom = _parse_roman(root_seg_curr.raw)
                if c_rom is not None:
                    gap = root_seg_new.val - c_rom
                    if 0 < gap <= 2:
                        return False
            gap = root_seg_new.val - root_seg_curr.val
            has_structural_prefix = bool(
                re.search(r"\b(?:section|chapter|part|appendix|annex|article|schedule|appendices)\b", token.raw_heading, re.IGNORECASE)
            )
            if gap > 0:
                if root_seg_new.kind == root_seg_curr.kind:
                    if has_structural_prefix or gap <= 2:
                        return False
                if root_seg_curr.kind == SeqType.numeric and root_seg_new.kind == SeqType.upper_alpha:
                    return False
        return True

    def _find_matching_level(self, token: HeaderToken, clean: str) -> int | None:
        # find if heading already matches an active open level in the scope stack
        clean_norm = clean.strip().lower()
        clean_clean = re.sub(r"[^\w\s]", "", clean_norm)

        for idx in range(len(self.stack) - 1, -1, -1):
            anc = self.stack[idx]
            anc_norm = anc.raw_heading.strip().lower()

            # 1. exact raw heading string match
            if clean_norm == anc_norm:
                return idx

            # 2. normalized string match (ignoring punctuation differences)
            anc_clean = re.sub(r"[^\w\s]", "", anc_norm)
            if clean_clean and clean_clean == anc_clean:
                return idx

            # 3. token prefix label and title match
            if token.prefix_label and anc.token.prefix_label:
                if token.prefix_label.lower() == anc.token.prefix_label.lower():
                    t1 = token.title.strip().lower()
                    t2 = anc.token.title.strip().lower()
                    if not t1 or not t2 or t1 == t2:
                        return idx
                    c1 = re.sub(r"[^\w\s]", "", t1)
                    c2 = re.sub(r"[^\w\s]", "", t2)
                    if c1 and c1 == c2:
                        return idx

            # 4. identical segments with matching title
            if token.segments and anc.token.segments and len(token.segments) == len(anc.token.segments):
                if all(
                    token.segments[i].kind == anc.token.segments[i].kind
                    and token.segments[i].val == anc.token.segments[i].val
                    for i in range(len(token.segments))
                ):
                    t1 = token.title.strip().lower()
                    t2 = anc.token.title.strip().lower()
                    if not t1 or not t2 or t1 == t2:
                        return idx
                    c1 = re.sub(r"[^\w\s]", "", t1)
                    c2 = re.sub(r"[^\w\s]", "", t2)
                    if c1 and c1 == c2:
                        return idx

        return None

    def process_headings(self, headings: list[str]) -> str:
        # process an ordered list of hierarchical headings (e.g. from chunk.meta.headings)
        if not headings:
            return self.get_current_breadcrumb()

        cleaned_headings = [_normalize_heading_text(h) for h in headings if _normalize_heading_text(h) and not _is_spurious_heading(_normalize_heading_text(h))]
        if not cleaned_headings:
            return self.get_current_breadcrumb()

        # if headings list exactly mirrors the active open stack, avoid unnecessary state churn
        if [lvl.raw_heading for lvl in self.stack] == cleaned_headings:
            return self.get_current_breadcrumb()

        last_breadcrumb = ""
        for clean in cleaned_headings:
            last_breadcrumb = self.process_heading(clean)
        return last_breadcrumb or self.get_current_breadcrumb()

    def process_heading(self, heading: str) -> str:
        # process a new heading and update the active scope stack
        clean = _normalize_heading_text(heading)
        if not clean or _is_spurious_heading(clean):
            return self.get_current_breadcrumb()

        token = parse_header_token(clean)

        # handle unnumbered headers without modifying sequence stack
        if token.is_unnumbered or not token.segments:
            if self.stack:
                top_raw = self.stack[-1].raw_heading
                if " - " in top_raw:
                    base = top_raw.split(" - ")[0].strip()
                    sub = clean.split(" - ", 1)[-1].strip() if " - " in clean else clean
                    updated = f"{base} - {sub}"
                    self.stack[-1] = ScopeLevel(
                        token=self.stack[-1].token,
                        raw_heading=updated,
                        title=updated,
                        root_key=self.stack[-1].root_key,
                        depth=self.stack[-1].depth,
                        max_child_val=self.stack[-1].max_child_val,
                    )
                    return self.get_current_breadcrumb()
                elif self.stack[-1].token.is_unnumbered:
                    self.stack[-1] = ScopeLevel(
                        token=token,
                        raw_heading=clean,
                        title=clean,
                        root_key=self.stack[-1].root_key,
                        depth=self.stack[-1].depth,
                        max_child_val=self.stack[-1].max_child_val,
                    )
                    return self.get_current_breadcrumb()
                else:
                    self.stack.append(ScopeLevel(
                        token=token,
                        raw_heading=clean,
                        title=clean,
                        root_key=self.stack[0].root_key,
                        depth=len(self.stack),
                        max_child_val=0,
                    ))
                    return self.get_current_breadcrumb()
            self.stack = [
                ScopeLevel(
                    token=token,
                    raw_heading=clean,
                    title=clean,
                    root_key=clean,
                    depth=0,
                )
            ]
            return clean

        # pop any trailing unnumbered leaf headers so a numbered heading attaches to the structural ancestor
        while len(self.stack) > 1 and self.stack[-1].token.is_unnumbered:
            self.stack.pop()

        # check if heading is stale relative to active stack
        if self.is_stale_heading(clean):
            return self.get_current_breadcrumb()

        # check if heading matches an already open level in the active stack
        match_idx = self._find_matching_level(token, clean)
        if match_idx is not None:
            # trim any descendants that were open below this level
            self.stack = self.stack[: match_idx + 1]
            return self.get_current_breadcrumb()

        # if stack only had an unnumbered preamble and a major section arrives, replace root
        if self.stack and (self.stack[0].token.is_unnumbered or not self.stack[0].token.segments) and len(token.segments) == 1:
            self.stack = [
                ScopeLevel(
                    token=token,
                    raw_heading=clean,
                    title=token.title,
                    root_key=token.root_key,
                    depth=0,
                )
            ]
            return self.get_current_breadcrumb()

        # check if new heading starts an advancing major sequence (e.g. root segment advances over active root)
        if self.stack and self.stack[0].token.segments and token.segments:
            root_seg_curr = self.stack[0].token.segments[0]
            root_seg_new = token.segments[0]

            if root_seg_curr.kind == SeqType.upper_alpha and root_seg_new.kind == SeqType.roman_upper and len(root_seg_new.raw) == 1:
                alpha_val = _alpha_to_int(root_seg_new.raw)
                gap = alpha_val - root_seg_curr.val
                if 0 < gap <= 2:
                    root_seg_new = Segment(kind=SeqType.upper_alpha, val=alpha_val, raw=root_seg_new.raw)
                    token = HeaderToken(
                        raw_heading=token.raw_heading,
                        title=token.title,
                        segments=[root_seg_new] + token.segments[1:],
                        prefix_label=token.prefix_label,
                        root_key=root_seg_new.raw,
                        is_unnumbered=False,
                    )

            if root_seg_curr.raw.upper() in ("I", "V", "X") and root_seg_new.kind == SeqType.roman_upper:
                c_rom = _parse_roman(root_seg_curr.raw)
                if c_rom is not None:
                    gap = root_seg_new.val - c_rom
                    if 0 < gap <= 2:
                        self.stack = [
                            ScopeLevel(
                                token=token,
                                raw_heading=clean,
                                title=token.title,
                                root_key=token.root_key,
                                depth=0,
                            )
                        ]
                        return self.get_current_breadcrumb()

            gap = root_seg_new.val - root_seg_curr.val
            has_structural_prefix = bool(
                re.search(r"\b(?:section|chapter|part|appendix|annex|article|schedule|appendices)\b", token.raw_heading, re.IGNORECASE)
            )
            is_advance = (
                gap > 0
                and (
                    (root_seg_new.kind == root_seg_curr.kind and (has_structural_prefix or gap <= 2 or (root_seg_curr.kind == SeqType.upper_alpha and root_seg_new.val <= 26)))
                    or (root_seg_curr.kind == SeqType.numeric and root_seg_new.kind == SeqType.upper_alpha)
                )
            )
            if is_advance:
                self.stack = [
                    ScopeLevel(
                        token=token,
                        raw_heading=clean,
                        title=token.title,
                        root_key=token.root_key,
                        depth=0,
                    )
                ]
                return self.get_current_breadcrumb()

        # check if new heading is a compound descendant of an open ancestor
        compound_match_idx = self._find_compound_ancestor(token)
        if compound_match_idx is not None:
            # trim stack above matched ancestor
            self.stack = self.stack[: compound_match_idx + 1]
            level = ScopeLevel(
                token=token,
                raw_heading=clean,
                title=token.title,
                root_key=self.stack[0].root_key,
                depth=len(self.stack),
            )
            self.stack.append(level)
            return self.get_current_breadcrumb()

        # check if new heading updates/refines an open level with matching sequence segments
        same_idx = self._find_same_level_update(token)
        if same_idx is not None:
            self.stack = self.stack[: same_idx + 1]
            self.stack[same_idx] = ScopeLevel(
                token=token,
                raw_heading=clean,
                title=token.title,
                root_key=self.stack[same_idx].root_key,
                depth=same_idx,
            )
            return self.get_current_breadcrumb()

        # check if new heading is a sibling continuation of any stack level
        sibling_match_idx = self._find_sibling_level(token)
        if sibling_match_idx is not None:
            # pop sibling and all its children, then push new sibling
            root_key = self.stack[0].root_key if sibling_match_idx > 0 else token.root_key
            self.stack = self.stack[:sibling_match_idx]
            parent = self.stack[-1] if self.stack else None
            if parent and token.segments:
                parent.max_child_val = max(parent.max_child_val, token.segments[-1].val, token.segments[0].val)
            level = ScopeLevel(
                token=token,
                raw_heading=clean,
                title=token.title,
                root_key=root_key,
                depth=sibling_match_idx,
            )
            self.stack.append(level)
            return self.get_current_breadcrumb()

        # check if new heading restarts a subordinate sequence (e.g. sequence resets to 1)
        reset_match_idx = self._find_reset_level(token)
        if reset_match_idx is not None:
            root_key = self.stack[0].root_key
            self.stack = self.stack[:reset_match_idx]
            parent = self.stack[-1] if self.stack else None
            if parent and token.segments:
                parent.max_child_val = max(token.segments[-1].val, token.segments[0].val)
            level = ScopeLevel(
                token=token,
                raw_heading=clean,
                title=token.title,
                root_key=root_key,
                depth=reset_match_idx,
            )
            self.stack.append(level)
            return self.get_current_breadcrumb()

        # Check if new token is allowed to be a subordinate child
        # A token of the same sequence kind as ANY open level in the stack with val <= anc.val can NEVER be a child
        if self.stack and token.segments:
            new_seg = token.segments[0]
            for anc in self.stack:
                if anc.token.segments:
                    anc_seg = anc.token.segments[0]
                    if new_seg.kind == anc_seg.kind and new_seg.val <= anc_seg.val:
                        return self.get_current_breadcrumb()

        # new subordinate child level descending under current top
        root_key = self.stack[0].root_key if self.stack else token.root_key
        parent = self.stack[-1] if self.stack else None
        if parent and token.segments:
            parent.max_child_val = max(parent.max_child_val, token.segments[-1].val, token.segments[0].val)
        level = ScopeLevel(
            token=token,
            raw_heading=clean,
            title=token.title,
            root_key=root_key,
            depth=len(self.stack),
        )
        self.stack.append(level)
        return self.get_current_breadcrumb()

    def _find_reset_level(self, token: HeaderToken) -> int | None:
        # if new token has value 1 (or 'a') and matches the kind of a subordinate level in stack,
        # it indicates that a previous sibling sequence at that level has closed and restarted
        if not token.segments:
            return None
        new_seg = token.segments[-1]
        if new_seg.val == 1:
            for idx in range(len(self.stack) - 1, 0, -1):
                anc_seg = self.stack[idx].token.segments[-1] if self.stack[idx].token.segments else None
                if anc_seg and anc_seg.kind == new_seg.kind and anc_seg.val > 1:
                    return idx
        return None

    def _find_compound_ancestor(self, token: HeaderToken) -> int | None:
        # find ancestor whose segments match the prefix of token segments
        if len(token.segments) <= 1:
            return None
        for idx in range(len(self.stack) - 1, -1, -1):
            anc = self.stack[idx]
            anc_len = len(anc.token.segments)
            if anc_len < len(token.segments):
                if all(
                    token.segments[i].raw.lower() == anc.token.segments[i].raw.lower()
                    for i in range(anc_len)
                ):
                    return idx
        return None

    def _find_sibling_level(self, token: HeaderToken) -> int | None:
        # search from top of stack to root for a compatible sibling sequence
        for idx in range(len(self.stack) - 1, -1, -1):
            anc = self.stack[idx]
            if self._is_sibling(token, anc.token):
                return idx
        return None

    def _is_sibling(self, new_tok: HeaderToken, old_tok: HeaderToken) -> bool:
        # determine if two tokens continue the same sequence level
        if not new_tok.segments or not old_tok.segments:
            return False
        # must have matching segment count
        if len(new_tok.segments) != len(old_tok.segments):
            return False
        # all prefix segments must match
        for i in range(len(new_tok.segments) - 1):
            if new_tok.segments[i].raw.lower() != old_tok.segments[i].raw.lower():
                return False
        # last segment must share sequence type and have increasing value
        last_new = new_tok.segments[-1]
        last_old = old_tok.segments[-1]
        if last_new.kind == last_old.kind:
            if last_new.val > last_old.val:
                return True
        if last_old.raw.upper() in ("I", "V", "X") and last_new.kind == SeqType.roman_upper:
            c_rom = _parse_roman(last_old.raw)
            if c_rom is not None and last_new.val > c_rom:
                return True
        return False

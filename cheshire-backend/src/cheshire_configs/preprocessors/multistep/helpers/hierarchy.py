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
    # numeric segment
    if seg_str.isdigit():
        return Segment(kind=SeqType.numeric, val=int(seg_str), raw=seg_str)

    # roman numeral check (prefer multi-character roman or lowercase i)
    roman_val = _parse_roman(seg_str)
    if roman_val is not None and (len(seg_str) > 1 or seg_str.lower() in ("i", "v", "x")):
        kind = SeqType.roman_upper if seg_str.isupper() else SeqType.roman_lower
        return Segment(kind=kind, val=roman_val, raw=seg_str)

    # uppercase alphabetic segment
    if seg_str.isalpha() and seg_str.isupper():
        return Segment(kind=SeqType.upper_alpha, val=_alpha_to_int(seg_str), raw=seg_str)

    # lowercase alphabetic segment
    if seg_str.isalpha() and seg_str.islower():
        return Segment(kind=SeqType.lower_alpha, val=_alpha_to_int(seg_str), raw=seg_str)

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


def _is_genuine_identifier(cand: str, full_str: str) -> bool:
    # determine if candidate token is an identifier or normal word
    # all digits is always an identifier
    if cand.isdigit():
        return True
    # compound tokens with delimiters are always identifiers
    if any(c in cand for c in (".", "-", "_", "/")):
        return True
    # mixed letters and digits (e.g. e1, 1a) are identifiers
    has_digit = any(c.isdigit() for c in cand)
    has_alpha = any(c.isalpha() for c in cand)
    if has_digit and has_alpha:
        return True
    # single letter followed by punctuation or space
    if len(cand) == 1 and cand.isalpha():
        return True
    # roman numerals followed by delimiter
    if _parse_roman(cand) is not None:
        if re.match(rf"^{re.escape(cand)}[\.\-:\)\s]", full_str):
            return True
    return False


def parse_header_token(heading: str) -> HeaderToken:
    # parse a raw heading string into a structured header token
    clean = heading.strip()
    if not clean:
        return HeaderToken(
            raw_heading="",
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

    # strip optional structural prefix words like section or appendix
    working_str = clean
    prefix_word_match = re.match(
        r"^(?:section|appendix|annex|chapter|part|article|schedule)\s+",
        working_str,
        re.IGNORECASE,
    )
    if prefix_word_match:
        working_str = working_str[prefix_word_match.end():].strip()

    # check parenthesized identifier: e.g. (1), (a), (1.1)
    paren_match = re.match(r"^\(([A-Za-z0-9]+(?:[\.\-_][A-Za-z0-9]+)*)\)\s*(.*)$", working_str)
    if paren_match:
        raw_id = paren_match.group(1)
        title = paren_match.group(2).strip()
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
        rem_title = delim_match.group(2).strip()

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


def _extract_heading_from_text(raw_text: str) -> str | None:
    # extracts a structural section heading candidate from raw text using outline syntax and layout heuristics.
    # returns the clean heading string if valid, or none if text is narrative body content, a list item, or table cell.
    # strictly logic-dependent; uses zero domain-specific or document-specific wordlists.
    if not raw_text:
        return None

    text = raw_text.strip()
    if not text or len(text) > 120:
        return None

    # reject bullet characters, list markers, and arrows
    if text[0] in ("•", "◦", "▪", "▫", "*", "–", "—", ">", "→") and not re.match(r"^[A-Za-z0-9]", text):
        return None

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return None
    line = lines[0]
    if len(lines) > 1 and len(line) > 60:
        return None

    clean_line = line.rstrip(":")

    # 1. Structural prefix keyword: e.g. "Section 1. Overview", "Appendix A - Notes", "Article 3: Governance"
    prefix_match = re.match(
        r"^(?:section|chapter|part|appendix|annex|article|schedule)\s+([A-Za-z0-9]+(?:[\.\-_][A-Za-z0-9]+)*)(?:[\.\-–—:\s]+)(\S.*)$",
        clean_line,
        re.IGNORECASE,
    )
    if prefix_match:
        title = prefix_match.group(2).strip()
        words = title.split()
        if len(words) <= 15 and not re.search(r"\.\s+[A-Z]", title):
            return clean_line

    # 2. Uppercase Alphabetic Outline: e.g. "A. Primary Title", "B. Secondary Title", "(A) Scope", "B - Design"
    alpha_match = re.match(
        r"^(?:\(?([A-Z]{1,3})\)?[\.\-–—:\)]\s+)(\S.*)$",
        clean_line,
    )
    if alpha_match:
        title = alpha_match.group(2).strip()
        words = title.split()
        if len(words) <= 12 and not re.search(r"\.\s+[A-Z]", title):
            if not title.endswith(".") or len(words) <= 6:
                return clean_line

    # 3. Numeric or Decimal Outline: e.g. "1. Outline Unit", "2. Component Design", "1.1 Architecture", "2.3.1 Cache"
    num_match = re.match(
        r"^(?:(?:\((\d+(?:\.\d+)*)\)|\b(\d+(?:\.\d+)+)[\.\-–—:\)]?|\b(\d+)[\.\-–—:\)])\s+)(\S.*)$",
        clean_line,
    )
    if num_match:
        title = num_match.group(4).strip()
        words = title.split()
        if len(words) <= 10 and not re.search(r"\.\s+[A-Z]", title):
            if title.endswith(".") and len(words) > 4:
                return None
            return clean_line

    # 4. Roman Numeral Outline: e.g. "I. Overview", "IV. Specifications", "(II) Implementation"
    roman_match = re.match(
        r"^(?:\(?([IVXLCDM]+)\)?[\.\-–—:\)]\s+)(\S.*)$",
        clean_line,
    )
    if roman_match:
        roman_cand = roman_match.group(1)
        if _parse_roman(roman_cand) is not None:
            title = roman_match.group(2).strip()
            words = title.split()
            if len(words) <= 12 and not re.search(r"\.\s+[A-Z]", title):
                return clean_line

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

        cleaned_headings = [h.strip() for h in headings if h.strip()]
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
        clean = heading.strip()
        if not clean:
            return self.get_current_breadcrumb()

        token = parse_header_token(clean)

        # handle unnumbered headers without modifying sequence stack
        if token.is_unnumbered or not token.segments:
            if self.stack:
                return f"{self.get_current_breadcrumb()} - {clean}"
            return clean

        # check if heading matches an already open level in the active stack
        match_idx = self._find_matching_level(token, clean)
        if match_idx is not None:
            # trim any descendants that were open below this level
            self.stack = self.stack[: match_idx + 1]
            return self.get_current_breadcrumb()

        # if stack only had an unnumbered preamble and a major section arrives, replace root
        if self.stack and self.stack[0].token.is_unnumbered and len(token.segments) == 1:
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

        # check if new heading is a sibling continuation of any stack level
        sibling_match_idx = self._find_sibling_level(token)
        if sibling_match_idx is not None:
            # pop sibling and all its children, then push new sibling
            root_key = self.stack[0].root_key if sibling_match_idx > 0 else token.root_key
            self.stack = self.stack[:sibling_match_idx]
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
            level = ScopeLevel(
                token=token,
                raw_heading=clean,
                title=token.title,
                root_key=root_key,
                depth=reset_match_idx,
            )
            self.stack.append(level)
            return self.get_current_breadcrumb()

        # new subordinate child level descending under current top
        root_key = self.stack[0].root_key if self.stack else token.root_key
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
        return False

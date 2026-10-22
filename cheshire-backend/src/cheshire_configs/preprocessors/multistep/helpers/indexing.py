"""
Lightweight structural document map extraction and indexing, including
reference document inventory harvesting for global standards auditing.
"""

import re
from typing import Any

from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.document import ProvenanceItem

from .elements import _attach_captions, _find_page_gaps
from .geometry import _get_item_label


def _is_reference_section(section_title: str) -> bool:
    """
    Checks if a section title indicates a Reference Documents / References section.
    """
    return bool(re.search(
        r'\b(reference\s*documents?|references|related\s*documents?|companion\s*documents?|applicable\s*documents?)\b',
        section_title,
        re.IGNORECASE,
    ))


def _is_reference_table(grid: list[list[Any]]) -> bool:
    """
    Determines if a table within a reference section contains reference document rows,
    distinguishing it from auxiliary tables like Attachments or Repository Links.
    """
    if not grid or len(grid) == 0:
        return False
    header_texts = [
        getattr(c, "text", "").lower().strip()
        for c in grid[0]
        if hasattr(c, "text") and c.text
    ]
    # Negative indicators: table is strictly for file attachments or raw URLs
    is_attachment = any("format" in h for h in header_texts) and not any("document" in h or "reference" in h for h in header_texts)
    is_repo_link = any(h in ("url", "path", "url / path", "repository") for h in header_texts) and not any("document" in h for h in header_texts)
    if is_attachment or is_repo_link:
        return False

    return any(
        any(k in h for k in ("document", "title", "reference", "spec", "code", "standard"))
        for h in header_texts
    )


def _extract_reference_table_rows(grid: list[list[Any]]) -> list[str]:
    """
    Extracts structured document titles and reference codes from a reference table.
    """
    if len(grid) <= 1:
        return []

    header_texts = [
        getattr(c, "text", "").lower().strip()
        for c in grid[0]
        if hasattr(c, "text") and c.text
    ]

    title_col: int | None = None
    ref_col: int | None = None
    for idx, h in enumerate(header_texts):
        if any(k in h for k in ("reference", "code", "link", "id", "version", "doc #")):
            if ref_col is None and ("title" not in h or "reference" in h):
                ref_col = idx
        if any(k in h for k in ("title", "name", "standard", "specification", "document")) and ref_col != idx:
            if title_col is None:
                title_col = idx

    entries: list[str] = []
    for row in grid[1:]:
        row_cells = [
            getattr(c, "text", "").strip()
            for c in row
            if hasattr(c, "text") and c.text
        ]
        if not any(row_cells):
            continue

        if title_col is not None and title_col < len(row):
            title = getattr(row[title_col], "text", "").strip()
            if not title:
                continue
            if ref_col is not None and ref_col < len(row):
                ref = getattr(row[ref_col], "text", "").strip()
                entry = f"{title} ({ref})" if ref else title
            else:
                entry = title
        else:
            entry = " - ".join(c for c in row_cells if c)

        if entry:
            entries.append(entry)

    return entries


def _extract_reference_text_items(text: str) -> list[str]:
    """
    Extracts reference document entries from bulleted lists or lines under a reference section.
    """
    lines = text.strip().split("\n")
    entries: list[str] = []
    for line in lines:
        cleaned = re.sub(r'^\s*[-*•\d\.]+\s*', '', line).strip()
        if not cleaned:
            continue
        if any(k in cleaned.lower() for k in ("srs", "brd", "requirements", "specification", "architecture", "standard", "policy", "guideline", "document")):
            entries.append(cleaned)
    return entries


def _extract_overview_companion_docs(text: str) -> list[str]:
    """
    Detects companion documents explicitly delegated or referenced in overview/framing paragraphs.
    e.g. 'in accordance with the approved System Requirements Specification (SRS-2025-LO-004)'
    """
    matches = re.finditer(
        r'\b((?:System|Software|Business)?\s*Requirements\s+(?:Specification|Document)|SRS|BRD|Solutions?\s+(?:Architecture\s+)?Document)(?:\s*[-–(]\s*([A-Za-z0-9_\-\.]+)\)?)?',
        text,
        re.IGNORECASE,
    )
    cleaned: list[str] = []
    for m in matches:
        full_match = m.group(0).strip()
        if len(full_match) > 3:
            cleaned.append(full_match)
    return cleaned


def build_document_index(doc: DoclingDocument) -> dict:
    """
    Builds a lightweight structural map of the document directly from
    Docling's parsed output — no model call required. This is what was
    previously Pass 1 in the three-pass design; Docling makes it free.

    The page_gaps list flags ranges of pages with no section heading,
    which signals to Pass 1 agents that a required section may be absent.

    The reference_documents list captures an inventory of all companion
    and external reference documents cited in reference tables, lists, or
    introductory overview text.
    """
    sections: list[dict] = []
    figures: list[dict] = []
    tables: list[dict] = []
    reference_documents: list[str] = []
    seen_refs: set[str] = set()
    current_section: str = ""

    def _add_ref(ref_str: str) -> None:
        normalized = ref_str.strip()
        if normalized and normalized not in seen_refs:
            seen_refs.add(normalized)
            reference_documents.append(normalized)

    for item, _level in doc.iterate_items():
        if not hasattr(item, "prov") or not item.prov:
            continue

        label: str = _get_item_label(item)
        prov: ProvenanceItem = item.prov[0]

        if label in ("section_header", "section_heading"):
            current_section = getattr(item, "text", "")
            sections.append({
                "id": item.self_ref,
                "title": current_section,
                "page": prov.page_no,
            })
        elif label == "picture":
            figures.append({
                "id": item.self_ref,
                "page": prov.page_no,
                "caption": None,  # filled by _attach_captions
                "section": current_section,
            })
        elif label == "table":
            tables.append({
                "id": item.self_ref,
                "page": prov.page_no,
                "section": current_section,
            })
            # Harvest reference documents from reference tables
            if _is_reference_section(current_section):
                grid = getattr(getattr(item, "data", None), "grid", None)
                if grid and _is_reference_table(grid):
                    for row_entry in _extract_reference_table_rows(grid):
                        _add_ref(row_entry)

        elif label in ("paragraph", "list_item", "text"):
            item_text = getattr(item, "text", "")
            if item_text:
                if _is_reference_section(current_section):
                    for entry in _extract_reference_text_items(item_text):
                        _add_ref(entry)
                elif "overview" in current_section.lower() or "introduction" in current_section.lower():
                    for entry in _extract_overview_companion_docs(item_text):
                        _add_ref(entry)

    _attach_captions(doc, figures)

    return {
        "sections": sections,
        "figures": figures,
        "tables": tables,
        "reference_documents": reference_documents,
        "page_gaps": _find_page_gaps(doc),
    }

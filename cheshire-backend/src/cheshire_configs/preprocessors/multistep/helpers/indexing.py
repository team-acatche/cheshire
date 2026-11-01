"""
Lightweight structural document map extraction and indexing, including
reference document inventory harvesting for global standards auditing.
"""

import re
from typing import Any

from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.document import ProvenanceItem

from .elements import _attach_captions, _find_page_gaps, _is_footer_element, promote_heuristic_headings
from .geometry import _get_item_label, _to_topleft_dict
from .hierarchy import HeaderHierarchyResolver, _extract_heading_from_text, _is_spurious_heading, _normalize_heading_text
from .tables import _detect_document_footer_top


def _is_reference_section(section_title: str) -> bool:
    """
    Checks if a section title indicates a Reference Documents / References section.
    """
    return bool(re.search(
        r'\b(reference\s*documents?|references|related\s*documents?|companion\s*documents?|applicable\s*documents?)\b',
        section_title,
        re.IGNORECASE,
    ))


def _is_diagram_section(section_title: str) -> bool:
    """
    Checks if a section title indicates a Diagrams section or subsection.
    """
    return bool(re.search(
        r'\b(diagrams?|flowcharts?|architecture\s+diagrams?)\b',
        section_title,
        re.IGNORECASE,
    ))


def _is_diagram_table(grid: list[list[Any]], table_item: Any = None, doc: Any = None) -> bool:
    """
    Determines if a table in a diagrams section contains diagram rows.
    Checks header rows and content rows across the grid and markdown export.
    """
    if not grid or len(grid) == 0:
        if table_item and hasattr(table_item, "export_to_markdown"):
            try:
                md = (table_item.export_to_markdown(doc=doc) if doc else table_item.export_to_markdown()).lower()
                return bool(re.search(r'\b(diagram|flowchart|architecture\s+diagram|data\s+flow|network\s+diagram|sequence\s+diagram)\b', md))
            except Exception:
                try:
                    md = table_item.export_to_markdown().lower()
                    return bool(re.search(r'\b(diagram|flowchart|architecture\s+diagram|data\s+flow|network\s+diagram|sequence\s+diagram)\b', md))
                except Exception:
                    return False
        return False

    # Check header rows
    for row in grid[:min(2, len(grid))]:
        header_texts = [
            getattr(c, "text", str(c)).lower().strip()
            for c in row
            if getattr(c, "text", str(c))
        ]
        if any(
            any(k in h for k in ("diagram", "flowchart", "architecture diagram", "data flow", "process flow", "sequence diagram", "network diagram"))
            for h in header_texts
        ):
            return True

    # Check data rows for explicit diagram references
    for row in grid:
        row_txt = " ".join(getattr(c, "text", str(c)).lower().strip() for c in row if getattr(c, "text", str(c)))
        if re.search(r'\b(diagram|flowchart|data\s+flow|network\s+diagram|sequence\s+diagram|process\s+flow)\b', row_txt):
            return True

    return False


def _extract_diagram_table_rows(grid: list[list[Any]], table_item: Any = None, doc: Any = None) -> list[dict]:
    """
    Extracts diagram entries (name, attachment/link) from a diagram table.
    Supports both standard tables with headers and continuation tables without headers.
    """
    if not grid or len(grid) == 0:
        if table_item and hasattr(table_item, "export_to_markdown"):
            try:
                md = table_item.export_to_markdown(doc=doc) if doc else table_item.export_to_markdown()
                lines = [l.strip() for l in md.splitlines() if l.strip().startswith("|") and not l.strip().startswith("|---")]
                if len(lines) > 1:
                    res = []
                    for l in lines[1:]:
                        parts = [p.strip() for p in l.split("|")[1:-1]]
                        if parts and any(parts):
                            res.append({"name": parts[0], "attachment": parts[1] if len(parts) > 1 else ""})
                    return res
            except Exception:
                return []
        return []

    # Detect if row 0 is a header row (short column descriptors without file extensions or specific titles)
    r0_cells = [getattr(c, "text", str(c)).strip() for c in grid[0] if getattr(c, "text", str(c)).strip()]
    is_data_row = any(
        re.search(r'\.(pdf|png|jpg|docx|svg|vsdx)\b', c, re.IGNORECASE) or len(c) > 35 or " – " in c or " - " in c
        for c in r0_cells
    )
    has_header = (not is_data_row) and any(
        any(k in getattr(c, "text", str(c)).lower() for k in ("diagram", "title", "name", "figure", "type", "description", "attachment", "file", "link"))
        for c in grid[0]
    )

    diagram_col: int | None = None
    attach_col: int | None = None

    if has_header:
        for idx, c in enumerate(grid[0]):
            txt = getattr(c, "text", str(c)).lower().strip()
            if any(k in txt for k in ("diagram", "title", "name", "figure", "type", "description")):
                if diagram_col is None:
                    diagram_col = idx
            if any(k in txt for k in ("attachment", "file", "link", "artifact", "document")):
                if attach_col is None:
                    attach_col = idx

    if diagram_col is None:
        diagram_col = 0
    if attach_col is None and len(grid[0]) > 1:
        attach_col = 1

    start_idx = 1 if has_header else 0
    entries: list[dict] = []

    for row in grid[start_idx:]:
        row_cells = [
            getattr(c, "text", str(c)).strip()
            for c in row
            if getattr(c, "text", str(c)).strip()
        ]
        if not any(row_cells):
            continue

        diag_name = ""
        if diagram_col < len(row):
            diag_name = _normalize_heading_text(getattr(row[diagram_col], "text", str(row[diagram_col])))
        if not diag_name:
            diag_name = _normalize_heading_text(row_cells[0])

        # Ignore if diag_name itself looks like a column header repetition
        if diag_name.lower() in ("diagram", "diagrams", "figure", "title"):
            continue

        attachment = ""
        if attach_col is not None and attach_col < len(row):
            attachment = _normalize_heading_text(getattr(row[attach_col], "text", str(row[attach_col])))

        if diag_name:
            entries.append({
                "name": diag_name,
                "attachment": attachment,
            })

    return entries


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

    The page_gaps list flags ranges of pages with no substantive content,
    which signals to agents that pages may be blank or unparsed.

    The reference_documents list captures an inventory of all companion
    and external reference documents cited in reference tables, lists, or
    introductory overview text.

    The diagram_documents list captures mandatory diagrams itemized in
    dedicated diagram tables under Diagrams sections.
    """
    promote_heuristic_headings(doc)

    sections: list[dict] = []
    figures: list[dict] = []
    tables: list[dict] = []
    reference_documents: list[str] = []
    diagram_documents: list[dict] = []
    seen_refs: set[str] = set()
    current_section: str = ""
    hierarchy_resolver = HeaderHierarchyResolver()
    footer_top_cache: dict[float, float] = {}

    def _add_ref(ref_str: str) -> None:
        normalized = ref_str.strip()
        if normalized and normalized not in seen_refs:
            seen_refs.add(normalized)
            reference_documents.append(normalized)

    seen_item_ids: set[str] = set()
    all_doc_items: list[Any] = []

    try:
        items_iter = [it for it, _ in doc.iterate_items(with_groups=True)]
    except Exception:
        try:
            items_iter = [it for it, _ in doc.iterate_items()]
        except Exception:
            items_iter = []

    for item in items_iter:
        ref_id = getattr(item, "self_ref", None)
        if ref_id:
            seen_item_ids.add(ref_id)
        all_doc_items.append(item)

    # Include any items from doc.texts, doc.tables, doc.pictures not yielded in iterate_items
    for pool in (getattr(doc, "texts", []) or [], getattr(doc, "tables", []) or [], getattr(doc, "pictures", []) or []):
        for item in pool:
            ref_id = getattr(item, "self_ref", None)
            if ref_id and ref_id not in seen_item_ids:
                seen_item_ids.add(ref_id)
                all_doc_items.append(item)

    def _item_sort_key(it: Any) -> tuple[int, float, int, float]:
        prov_list = getattr(it, "prov", None)
        if not prov_list:
            return (999999, 0.0, 1, 0.0)
        p = prov_list[0]
        p_no = getattr(p, "page_no", 999999)
        bbox = getattr(p, "bbox", None)
        if not bbox:
            return (p_no, 0.0, 1, 0.0)
        page = doc.pages.get(p_no) if hasattr(doc, "pages") and doc.pages else None
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
        tb = _to_topleft_dict(bbox, p_h)
        lbl = _get_item_label(it)
        cand_heading = _extract_heading_from_text(getattr(it, "text", ""))
        is_heading = 0 if (lbl in ("section_header", "section_heading") or cand_heading) else 1
        # Section headers near page top (t <= 140.0) take priority on that page before content/figures
        v_band = 0.0 if (is_heading == 0 and tb["t"] <= 140.0) else round(tb["t"] / 40.0) * 40.0
        return (p_no, v_band, is_heading, tb["t"], tb["l"])

    all_doc_items.sort(key=_item_sort_key)

    for item in all_doc_items:
        if not hasattr(item, "prov") or not item.prov:
            continue

        prov: ProvenanceItem = item.prov[0]
        page: Any = doc.pages.get(prov.page_no) if hasattr(doc, "pages") and doc.pages else None
        page_h: float = getattr(getattr(page, "size", None), "height", 0.0) if page else 0.0
        if page_h > 0.0:
            if page_h not in footer_top_cache:
                footer_top_cache[page_h] = _detect_document_footer_top(doc, page_h)
            footer_top = footer_top_cache[page_h]
            # Exclude corporate document-control footers so footer text/tables are never indexed as body content
            if _is_footer_element(item, doc, page_h, footer_top=footer_top):
                continue

        label: str = _get_item_label(item)

        if label == "page_header":
            cand = _extract_heading_from_text(getattr(item, "text", ""))
            if cand:
                label = "section_header"

        if label in ("section_header", "section_heading"):
            raw_heading = getattr(item, "text", "")
            cand = _extract_heading_from_text(raw_heading)
            clean_heading = cand or _normalize_heading_text(raw_heading)
            if clean_heading and not _is_spurious_heading(clean_heading):
                current_section = hierarchy_resolver.process_heading(clean_heading)
                root_section = hierarchy_resolver.get_root_heading() or current_section
                sections.append({
                    "id": item.self_ref,
                    "title": current_section,
                    "root_section": root_section,
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
            grid = getattr(getattr(item, "data", None), "grid", None)

            # 1. Check if table caption contains an outline section heading
            table_cand: str | None = None
            if hasattr(item, "caption_text"):
                try:
                    cap_txt = item.caption_text(doc).strip()
                    table_cand = _extract_heading_from_text(cap_txt)
                except Exception:
                    table_cand = None

            # 2. Check if row 0 is a full-width section banner header (single non-empty cell e.g. section title)
            if not table_cand and grid and len(grid) > 0:
                non_empty_r0 = [c for c in grid[0] if getattr(c, "text", str(c)).strip()]
                if len(non_empty_r0) == 1:
                    cell_txt = _normalize_heading_text(getattr(non_empty_r0[0], "text", str(non_empty_r0[0])))
                    if not _is_spurious_heading(cell_txt):
                        c_match = _extract_heading_from_text(cell_txt)
                        if c_match:
                            table_cand = c_match
                        elif 2 <= len(cell_txt.split()) <= 12 and len(cell_txt) <= 100 and not cell_txt.endswith("."):
                            has_multi_col = any(
                                len([c for c in row if getattr(c, "text", str(c)).strip()]) >= 2
                                for row in grid[1:min(4, len(grid))]
                            )
                            if has_multi_col:
                                table_cand = cell_txt

            if table_cand and not hierarchy_resolver.is_stale_heading(table_cand):
                current_section = hierarchy_resolver.process_heading(table_cand)
                root_section = hierarchy_resolver.get_root_heading() or current_section
                sections.append({
                    "id": item.self_ref,
                    "title": current_section,
                    "root_section": root_section,
                    "page": prov.page_no,
                })

            table_headers: list[str] = []
            table_rows_summary: list[str] = []
            if grid and len(grid) > 0:
                table_headers = [getattr(c, "text", str(c)).strip() for c in grid[0] if getattr(c, "text", str(c)).strip()]
                for row in grid[1:26]:
                    row_txt = " | ".join(getattr(c, "text", str(c)).strip() for c in row if getattr(c, "text", str(c)).strip())
                    if row_txt:
                        table_rows_summary.append(row_txt)
            elif hasattr(item, "export_to_markdown"):
                try:
                    md = item.export_to_markdown(doc=doc) if doc else item.export_to_markdown()
                    lines = [l.strip() for l in md.splitlines() if l.strip().startswith("|") and not l.strip().startswith("|---")]
                    if lines:
                        table_headers = [p.strip() for p in lines[0].split("|")[1:-1] if p.strip()]
                        table_rows_summary = [" | ".join(p.strip() for p in l.split("|")[1:-1] if p.strip()) for l in lines[1:26]]
                except Exception:
                    pass

            tables.append({
                "id": item.self_ref,
                "page": prov.page_no,
                "section": current_section,
                "headers": table_headers,
                "rows": table_rows_summary,
            })

            # harvest reference documents from reference tables
            if _is_reference_section(current_section) and grid and _is_reference_table(grid):
                for row_entry in _extract_reference_table_rows(grid):
                    _add_ref(row_entry)

            # harvest diagrams from diagram tables under Diagrams subsections or diagram-containing tables
            if _is_diagram_section(current_section) or _is_diagram_table(grid, item, doc=doc):
                for diag_entry in _extract_diagram_table_rows(grid, item, doc=doc):
                    diag_entry["table_id"] = item.self_ref
                    diagram_documents.append(diag_entry)
                    # Register into figures so caption-based auditing also discovers the diagram
                    figures.append({
                        "id": item.self_ref,
                        "page": prov.page_no,
                        "caption": diag_entry["name"],
                        "attachment": diag_entry.get("attachment", ""),
                        "section": current_section,
                    })

        elif label in ("paragraph", "list_item", "text", "caption", "title", "group", "field_heading", "field_region", "field_item", "key_value_region", "code", "reference") or (hasattr(item, "text") and getattr(item, "text", "")):
            item_text = getattr(item, "text", "")
            orig_text = getattr(item, "orig", "")
            marker = getattr(item, "marker", "") or getattr(item, "enumerator", "")
            combined = f"{marker} {item_text}".strip() if marker else ""
            cand = None
            for c_str in (orig_text, combined, item_text):
                if c_str:
                    c = _extract_heading_from_text(c_str)
                    if c and not _is_spurious_heading(c):
                        cand = c
                        break
            if cand and not hierarchy_resolver.is_stale_heading(cand):
                current_section = hierarchy_resolver.process_heading(cand)
                root_section = hierarchy_resolver.get_root_heading() or current_section
                sections.append({
                    "id": item.self_ref,
                    "title": current_section,
                    "root_section": root_section,
                    "page": prov.page_no,
                })
            elif _is_reference_section(current_section):
                for entry in _extract_reference_text_items(item_text):
                    _add_ref(entry)
            elif "overview" in current_section.lower() or "introduction" in current_section.lower():
                for entry in _extract_overview_companion_docs(item_text):
                    _add_ref(entry)

    # Supplement diagram_documents and figures from enriched tables across all sections
    seen_diag_names: set[str] = {d["name"].lower().strip() for d in diagram_documents}
    diag_re = re.compile(r'\b(diagrams?|flowcharts?|data\s+flow|process\s+flow|sequence\s+diagram|network\s+diagram)\b', re.IGNORECASE)
    non_diag_ext_re = re.compile(r'\.(json|xml|yaml|yml|sql|config|csv|txt|properties)\b', re.IGNORECASE)

    for t in tables:
        t_section = t.get("section", "")
        headers_lower = [_normalize_heading_text(h).lower() for h in t.get("headers", [])]
        is_diag_section = _is_diagram_section(t_section)
        has_diag_col = any(diag_re.search(h) for h in headers_lower)

        # Detect column indices
        diag_col = 0
        attach_col = 1 if len(t.get("headers", [])) > 1 else None
        for idx, h in enumerate(headers_lower):
            if any(k in h for k in ("diagram", "flowchart", "title", "name", "figure", "type")):
                diag_col = idx
            if any(k in h for k in ("attachment", "file", "link", "artifact", "document")):
                attach_col = idx

        for row_str in t.get("rows", []):
            parts = [_normalize_heading_text(p) for p in row_str.split("|")]
            diag_name = parts[diag_col] if diag_col < len(parts) else (parts[0] if parts else "")
            attach_name = parts[attach_col] if (attach_col is not None and attach_col < len(parts)) else ""

            if not diag_name or diag_name.lower() in seen_diag_names:
                continue
            if diag_name.lower() in ("diagram", "diagrams", "figure", "title", "name", "type", "description", "report", "file", "files"):
                continue

            # In dedicated diagram sections or tables with diagram columns, harvest all legitimate rows
            # In other tables, only harvest rows that explicitly name a diagram and are not raw data files
            if is_diag_section or has_diag_col or (diag_re.search(diag_name) and not non_diag_ext_re.search(diag_name)):
                diag_entry = {
                    "name": diag_name,
                    "attachment": attach_name,
                    "table_id": t["id"],
                    "page": t.get("page", 1),
                }
                diagram_documents.append(diag_entry)
                seen_diag_names.add(diag_name.lower())
                figures.append({
                    "id": t["id"],
                    "page": t.get("page", 1),
                    "caption": diag_name,
                    "attachment": attach_name,
                    "section": t_section,
                })

    _attach_captions(doc, figures)

    # Supplement diagram_documents from figures with diagram captions
    for f in figures:
        cap = f.get("caption", "")
        if cap and diag_re.search(cap) and not non_diag_ext_re.search(cap):
            cap_clean = _normalize_heading_text(cap)
            if cap_clean.lower() not in seen_diag_names and cap_clean.lower() not in ("diagram", "diagrams", "figure"):
                diag_entry = {
                    "name": cap_clean,
                    "attachment": f.get("attachment", ""),
                    "table_id": f["id"],
                    "page": f.get("page", 1),
                }
                diagram_documents.append(diag_entry)
                seen_diag_names.add(cap_clean.lower())

    # Update any diagram_documents missing attachments if a figure on that page has one
    for d in diagram_documents:
        if not d.get("attachment"):
            for f in figures:
                if f.get("page") == d.get("page") and f.get("attachment"):
                    if d["name"].lower() in (f.get("caption", "") or "").lower() or (f.get("caption", "") or "").lower() in d["name"].lower():
                        d["attachment"] = f["attachment"]
                        break

    # Supplement diagram_documents from text items under diagram sections or naming diagrams
    for item, _ in doc.iterate_items():
        if not hasattr(item, "prov") or not item.prov:
            continue
        lbl = _get_item_label(item)
        if lbl in ("page_footer", "page_number", "footnote", "section_header", "section_heading"):
            continue
        txt = getattr(item, "text", "").strip()
        if not txt or len(txt) > 140 or "\n" in txt:
            continue
        txt_clean = _normalize_heading_text(txt)
        if _extract_heading_from_text(txt_clean) is not None:
            continue
        if diag_re.search(txt_clean) and not non_diag_ext_re.search(txt_clean):
            if txt_clean.lower() not in seen_diag_names and txt_clean.lower() not in ("diagram", "diagrams", "figure", "attachment", "attachments", "title", "name"):
                diag_entry = {
                    "name": txt_clean,
                    "attachment": "",
                    "table_id": item.self_ref,
                    "page": item.prov[0].page_no,
                }
                diagram_documents.append(diag_entry)
                seen_diag_names.add(txt_clean.lower())

    return {
        "sections": sections,
        "figures": figures,
        "tables": tables,
        "reference_documents": reference_documents,
        "diagram_documents": diagram_documents,
        "page_gaps": _find_page_gaps(doc),
    }

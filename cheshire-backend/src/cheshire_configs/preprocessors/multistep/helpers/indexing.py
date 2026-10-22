"""
Lightweight structural document map extraction and indexing.
"""

from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.document import ProvenanceItem

from .elements import _attach_captions, _find_page_gaps
from .geometry import _get_item_label


def build_document_index(doc: DoclingDocument) -> dict:
    """
    Builds a lightweight structural map of the document directly from
    Docling's parsed output — no model call required. This is what was
    previously Pass 1 in the three-pass design; Docling makes it free.

    The page_gaps list flags ranges of pages with no section heading,
    which signals to Pass 1 agents that a required section may be absent.
    """
    sections: list[dict] = []
    figures: list[dict] = []
    tables: list[dict] = []
    current_section: str = ""

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

    _attach_captions(doc, figures)

    return {
        "sections": sections,
        "figures": figures,
        "tables": tables,
        "page_gaps": _find_page_gaps(doc),
    }

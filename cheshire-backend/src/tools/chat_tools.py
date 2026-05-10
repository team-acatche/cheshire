from typing import cast, Any

from haystack.dataclasses import Document
from haystack.tools import tool
from haystack import component

from tools.knowledge import KnowledgeState, current_knowledge_state
from knowledge_base.history import EventType

@tool
def read_vulnerabilities_from_event_store(confirm: bool) -> dict[str, Any]:
    """
    Read all of the findings from the audit.
    """
    state = current_knowledge_state.get()
    docs = state.event_store.query(
        filters={
            "field": "meta.event_type",
            "operator": "==",
            "value": EventType.VULNERABILITY_FINDING,
        }
    )
    return {"findings": docs}

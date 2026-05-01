from typing import cast

from haystack.dataclasses import Document
from haystack.tools import tool, Tool
from lancedb_haystack import LanceDBDocumentStore # type: ignore

from knowledge_base.history import EventType

def read_vulnerabilities_from_event_store_tool(event_store: LanceDBDocumentStore) -> Tool:
    @tool
    def read_vulnerabilities() -> list[Document]:
        """
        Read all of the findings from the audit.
        """
        return event_store.perform_query(
            filters={
                "field": "meta.event_type",
                "operator": "==",
                "value": EventType.VULNERABILITY_FINDING,
            }
        )
    
    return cast(Tool, read_vulnerabilities)
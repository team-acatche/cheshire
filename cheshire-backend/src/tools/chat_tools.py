from typing import cast, Any

from haystack.dataclasses import Document
from haystack.tools import create_tool_from_function, Tool, ComponentTool
from haystack import component
from lancedb_haystack import LanceDBDocumentStore # type: ignore

from knowledge_base.history import EventType

@component
class ReadVulnerabilitiesTool:
    def __init__(self, event_store: LanceDBDocumentStore):
        self.event_store = event_store

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "tools.chat_tools.ReadVulnerabilitiesTool",
            "init_parameters": {
                "event_store": self.event_store.to_dict()
            }
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReadVulnerabilitiesTool":
        init_params = data.get("init_parameters", {})
        return cls(event_store=LanceDBDocumentStore.from_dict(init_params["event_store"]))

    @component.output_types(documents=list[Document])
    def run(self) -> dict[str, list[Document]]:
        """
        Read all of the findings from the audit.
        """
        docs = self.event_store.perform_query(
            filters={
                "field": "meta.event_type",
                "operator": "==",
                "value": EventType.VULNERABILITY_FINDING,
            }
        )
        return {"documents": docs}

def read_vulnerabilities_from_event_store_tool(event_store: LanceDBDocumentStore) -> Tool:
    return ComponentTool(
        component=ReadVulnerabilitiesTool(event_store),
        name="read_vulnerabilities",
        description="Read all of the findings from the audit.",
        outputs_to_string={"source": "documents"}
    )
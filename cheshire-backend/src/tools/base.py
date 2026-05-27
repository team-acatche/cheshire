from typing import cast

from haystack.core.component import Component
from haystack.components.embedders.types import TextEmbedder
from haystack.document_stores.in_memory import InMemoryDocumentStore
from haystack.tools import Tool, create_tool_from_function, PipelineTool, tool, ComponentTool

from tools.vulnerability_tools import add_vulnerability, read_vulnerabilities, accept_finding, flag_contradiction
from tools.helpers import document_to_string, vulnerabilities_to_string
from cheshire_configs.retrievers.hybrid_retriever import HybridInMemoryRetriever

def query_document_tool(document_store: InMemoryDocumentStore, embedder: TextEmbedder) -> Tool:
    _query_document: Tool = ComponentTool(
        component=cast(Component, HybridInMemoryRetriever(document_store, embedder)),
        name="query_document",
        description="Query the document store using keyword search for any relevant documents.",
        outputs_to_string={"source": "documents", "handler": document_to_string}
    )
    _query_document.warm_up()
    return _query_document

def add_vulnerability_tool(vulnerability_state: str) -> Tool:
    _add_vulnerability_tool = create_tool_from_function(
	    function=add_vulnerability,
	    description="Add a vulnerability to the vulnerability list.",
	    outputs_to_state={vulnerability_state: {"source": "vulnerability"}}
    )
    _add_vulnerability_tool.warm_up()
    return _add_vulnerability_tool

def read_vulnerabilities_tool(vulnerability_state: str) -> Tool:
    _read_vulnerabilities_tool = create_tool_from_function(
	    function=read_vulnerabilities,
	    description="Read the vulnerability list.",
	    inputs_from_state={vulnerability_state: "vulnerabilities"},
	    outputs_to_string={"source": "vulnerabilities", "handler": vulnerabilities_to_string}
    )
    _read_vulnerabilities_tool.warm_up()
    return _read_vulnerabilities_tool

def accept_finding_tool(state_key: str) -> Tool:
    _accept_finding_tool = create_tool_from_function(
        function=accept_finding,
        description="Accept a finding as valid and non-duplicate. Call this for each unique finding you want to keep.",
        outputs_to_state={state_key: {"source": "finding"}}
    )
    _accept_finding_tool.warm_up()
    return _accept_finding_tool

def flag_contradiction_tool(state_key: str) -> Tool:
    _flag_contradiction_tool = create_tool_from_function(
        function=flag_contradiction,
        description="Flag two findings as contradicting each other across sections.",
        outputs_to_state={state_key: {"source": "contradiction"}}
    )
    _flag_contradiction_tool.warm_up()
    return _flag_contradiction_tool

@tool
def finish(
    confirm: bool # the model needs one required argument for tool calling to work properly, but this is otherwise unnecessary
) -> str:
    """Finish the audit. Call this tool when you are done with the audit. Be sure to provide an argument to this function when calling it."""
    return "Audit finished."

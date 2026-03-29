from haystack.core.pipeline import Pipeline
from haystack.tools import Tool, create_tool_from_function, PipelineTool, tool

from tools.vulnerability_tools import add_vulnerability, read_vulnerabilities
from tools.helpers import document_to_string, vulnerabilities_to_string

def query_document_tool(query_pipeline: Pipeline) -> Tool:
    _query_document: Tool = PipelineTool(
        pipeline=query_pipeline,
        input_mapping={"query": ["embedder.text"]},
        output_mapping={"retriever.documents": "documents"},
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

@tool
def finish_tool(
    _confirm: bool # the model needs one required argument for tool calling to work properly, but this is otherwise unnecessary
) -> str:
    """Finish the audit."""
    return "Audit finished."

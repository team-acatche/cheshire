import asyncio

from dotenv import load_dotenv
load_dotenv()

import os
from pathlib import Path

import logging
logger = logging.getLogger("uvicorn.error")

from haystack.core.pipeline import Pipeline
from haystack.document_stores.in_memory import InMemoryDocumentStore
from haystack.components.writers import DocumentWriter
from docling_haystack.converter import DoclingConverter, ExportType
from docling.chunking import HybridChunker

from haystack.tools import PipelineTool
from haystack.tools.from_function import create_tool_from_function
from tools.helpers.document_to_string import document_to_string, vulnerabilities_to_string
from tools.query_tool import query_pipeline
from tools.vulnerability_tools import read_vulnerabilities, add_vulnerability
from tools.exa import web_search

from haystack.components.agents import Agent
from haystack.components.generators.utils import print_streaming_chunk
from haystack_integrations.components.generators.ollama import OllamaChatGenerator
from haystack_integrations.components.embedders.ollama import OllamaDocumentEmbedder
from haystack.dataclasses import ChatMessage

from tools.helpers.output_schema import VulnerabilityDetails

# RAG Pipeline
document_store = InMemoryDocumentStore(embedding_similarity_function="cosine")

docling_converter = DoclingConverter(
	chunker=HybridChunker(
		tokenizer=os.getenv("HF_EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v2-moe"),
		max_tokens=2**13,
	)
)

embedder = OllamaDocumentEmbedder(
	model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
	url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
)
document_writer = DocumentWriter(document_store)

rag_pipeline = Pipeline()
rag_pipeline.add_component("converter", docling_converter)
rag_pipeline.add_component("embedder", embedder)
rag_pipeline.add_component("writer", document_writer)
rag_pipeline.connect("converter", "embedder")
rag_pipeline.connect("embedder", "writer")

# Tools
query_document = PipelineTool(
	pipeline=query_pipeline(document_store),
	input_mapping={"query": ["embedder.text"]},
	output_mapping={"retriever.documents": "documents"},
	name="query_document",
	description="Query the document store using keyword search for any relevant documents.",
	outputs_to_string={"source": "documents", "handler": document_to_string}
)
query_document.warm_up()

add_vulnerability_tool = create_tool_from_function(
	function=add_vulnerability,
	description="Add a vulnerability to the vulnerability list.",
	outputs_to_state={"vulnerabilities_list": {"source": "vulnerabilities"}}
)
add_vulnerability_tool.warm_up()

read_vulnerabilities_tool = create_tool_from_function(
	function=read_vulnerabilities,
	description="Read the vulnerability list.",
	inputs_from_state={"vulnerabilities_list": "vulnerabilities"},
	outputs_to_string={"source": "vulnerabilities", "handler": vulnerabilities_to_string}
)
read_vulnerabilities_tool.warm_up()

# Agent
model = OllamaChatGenerator(
	model=os.getenv("OLLAMA_CHAT_MODEL", "llama3.2"),
	url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
	generation_kwargs={
		"num_ctx": 2**14,
		# Qwen 3
		"temperature": 0.6,
		"top_p": 0.95,
		"top_k": 20,
		"min_p": 0,
	},
	think=True,
)

analyst = Agent(
	chat_generator=model,
	system_prompt=
	"""
	You are an expert security auditor. Given the system overview below, identify vulnerabilities by querying the document store and cross-referencing known CVEs and attack patterns online.
	## Process
	Repeat the following process until the full document store has been covered:
	0. **Know**: Use `query_document` to obtain a quick overview of the system (usually obtained by searching for the introduction or background). Afterwards, plan your angle of analysis.
	1. **Plan**: Identify a specific component or area to investigate next.
	2. **Query**: Use `query_document` to retrieve relevant details (be specific with queries).
	3. **Research**: Use `web_search` to find known vulnerabilities matching what you found (e.g., CVEs, OWASP entries, exploit patterns). Ensure that what you're searching is specific to the component you're investigating.
	Continue until you have analyzed the entire system specification.
	4. **Store**: Use `add_vulnerability` to store the vulnerabilities you found to combine later into a final report.
	## Rules
	- Prioritize attack surface: auth, inputs, network exposure, third-party deps, secrets handling, privilege boundaries.
	- Cross-reference document findings with current threat intelligence.
	- Never assume a component is secure without querying and searching it.
	- Ensure that the vulnerabilites and recommendations are as relevant and as recent as possible to the system you are analyzing.
	- Escalate query specificity if initial results are vague.
	- When adding a vulnerability, use the bounding box and page number of the document chunk that you are referencing.
	- To ensure that the final response is lossless, use `read_vulnerabilities` to read the vulnerability list before producing the final summary.
	""",
	tools=[query_document, web_search, add_vulnerability_tool, read_vulnerabilities_tool],
	exit_conditions=["text"],
	streaming_callback=print_streaming_chunk, # TODO: switch to logger
	state_schema={
		"vulnerabilities_list": {"type": list[VulnerabilityDetails]},
	}
)


async def evaluate_file(document_path: Path) -> list[VulnerabilityDetails] | None:
	if document_path.suffix != ".pdf" or not document_path.exists():
		return None

	logger.info(f"agent({document_path.name}): Loading...")
	rag_pipeline.run({"converter": {"paths": [document_path]}})
	logger.info(f"agent({document_path.name}): File loaded into memory.")

	logger.info(f"agent({document_path.name}): Starting audit...")
	response = analyst.run(messages=[ChatMessage.from_user("Start the audit")])
	logger.info(f"agent({document_path.name}): Audit complete.")

	return response["vulnerabilities_list"]

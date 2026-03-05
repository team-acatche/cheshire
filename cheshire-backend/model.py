import asyncio

from dotenv import load_dotenv
load_dotenv()

import os
from pathlib import Path
from typing import Callable

import logging
logger = logging.getLogger("uvicorn.error")

from haystack.core.pipeline import Pipeline
from haystack.components.generators.chat.llm import ChatGenerator, ChatMessage
from haystack.components.generators.utils import print_streaming_chunk
from haystack.tools import ToolsType
from haystack.components.agents import Agent

from tools.helpers.output_schema import VulnerabilityDetails

def _create_agent(model: ChatGenerator, tools: ToolsType) -> Agent:
	return Agent(
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
		tools=tools,
		exit_conditions=["text"],
		streaming_callback=print_streaming_chunk, # TODO (feat): switch to logger
		state_schema={
			"vulnerabilities_list": {"type": list[VulnerabilityDetails]},
		}
	)


async def evaluate_file(
	document_path: Path,
	*,
	model: ChatGenerator,
	tools: ToolsType,
	document_preprocessor: Callable[[Path], None] | None = None,
) -> list[VulnerabilityDetails] | None:
	if document_path.suffix != ".pdf" or not document_path.exists():
		return None

	analyst = _create_agent(model, tools)

	logger.info(f"agent({document_path.name}): Loading...")
	if document_preprocessor:
		document_preprocessor(document_path)
	logger.info(f"agent({document_path.name}): File loaded into memory.")

	logger.info(f"agent({document_path.name}): Starting audit...")
	response = analyst.run(messages=[ChatMessage.from_user("Start the audit")])
	logger.info(f"agent({document_path.name}): Audit complete.")

	return response["vulnerabilities_list"]

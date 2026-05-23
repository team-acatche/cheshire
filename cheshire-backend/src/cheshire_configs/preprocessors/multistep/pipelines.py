import json
import os
from haystack import Pipeline
from haystack.components.agents import Agent
from haystack.utils import Secret
from haystack.tools import Tool

from haystack_integrations.components.generators.openrouter import OpenRouterChatGenerator

from cheshire_configs.preprocessors.multistep.components.chunker import MultistepDoclingConverter
from cheshire_configs.preprocessors.multistep.components.message_builder import ChunkMessageBuilder
from cheshire_configs.preprocessors.multistep.components.findings_parser import FindingsParser
from cheshire_configs.preprocessors.multistep.components.synthesis_message_builder import SynthesisMessageBuilder, PASS2_SYSTEM_PROMPT

from typing import cast
from tools.exa import web_search
from cheshire_configs.preprocessors.multistep.tools import get_standard, query_other_section
from tools.helpers.output_schema import VulnerabilityDetails

from dotenv import load_dotenv
load_dotenv("../../../.env.user")

PASS1_SYSTEM_PROMPT = """\
Role: Technical design document auditor.

INPUT
Text: [ID:<ref>|<label>|p<n>]
Figures: [Figure ID:<ref>|p<n>]

TOOLS
- get_standard(query): Search for details, requirements, or guidelines of security standards relevant to the query.
- web_search(query): Used to research external technical vulnerabilities and attack patterns not covered by the company standards.
- query_other_section(section_title): Retrieve content of another section by its title.
- add_vulnerability(vulnerability): Record a vulnerability/compliance gap finding. The `vulnerability` dictionary must match the schema: { "title": "str", "description": "str", "page_no": int, "bbox": { "l": float, "t": float, "r": float, "b": float }, "web_references": ["str"], "recommendations": ["str"] }

CONSTRAINTS
- sub_bbox is in figure crop coordinates.
- Call get_standard to retrieve relevant requirements before citing any standard.
- Use web_search specifically to investigate technical vulnerabilities not covered by company standards.
- You MUST call add_vulnerability for every finding. This is the primary output channel.
- After recording all findings via add_vulnerability, also output a JSON array summary as your final text response. Each item must include: element_id, figure_id (or null), sub_bbox (or null), title, description, page_no, web_references, recommendations.
- If no findings, output [].
"""


def _make_tools() -> list[Tool]:
    return [cast(Tool, get_standard), cast(Tool, web_search), cast(Tool, query_other_section)]


def build_preprocessing_pipeline() -> Pipeline:
    pipeline = Pipeline()

    pipeline.add_component(
        "docling_converter",
        MultistepDoclingConverter(images_scale=2.0)
    )

    # Single-component pipeline — no connections needed
    return pipeline


def build_evaluation_pipeline() -> Pipeline:
    generator = OpenRouterChatGenerator(
        api_key=Secret.from_env_var("OPENROUTER_API_KEY"),
        model=os.getenv("OPENROUTER_MODEL", "ServiceNow-AI/Apriel-1.6-15b-Thinker"),
    )

    from tools.base import add_vulnerability_tool
    agent_tools = _make_tools() + [add_vulnerability_tool("vulnerabilities_list")]

    agent = Agent(
        chat_generator=generator,
        tools=agent_tools,
        system_prompt=PASS1_SYSTEM_PROMPT,
        max_agent_steps=10,
        exit_conditions=["text"],
		state_schema={
			"vulnerabilities_list": {"type": list[VulnerabilityDetails]},
		}
    )

    pipeline = Pipeline()
    pipeline.add_component("chunk_message_builder", ChunkMessageBuilder())
    pipeline.add_component("agent", agent)
    pipeline.add_component("findings_parser", FindingsParser())

    pipeline.connect("chunk_message_builder.messages", "agent.messages")
    pipeline.connect("agent.last_message", "findings_parser.last_message")

    return pipeline

def build_synthesis_pipeline() -> Pipeline:
    generator = OpenRouterChatGenerator(
        api_key=Secret.from_env_var("OPENROUTER_API_KEY"),
        model=os.getenv("OPENROUTER_MODEL", "ServiceNow-AI/Apriel-1.6-15b-Thinker"),
    )

    from tools.base import accept_finding_tool, flag_contradiction_tool
    from tools.helpers.output_schema import Contradiction

    agent = Agent(
        chat_generator=generator,
        tools=[
            accept_finding_tool("accepted_findings"),
            flag_contradiction_tool("contradictions"),
        ],
        system_prompt=PASS2_SYSTEM_PROMPT,
        max_agent_steps=200,
        exit_conditions=["text"],
        state_schema={
            "accepted_findings": {"type": list[VulnerabilityDetails]},
            "contradictions": {"type": list[Contradiction]},
        }
    )

    pipeline = Pipeline()
    pipeline.add_component("synthesis_message_builder", SynthesisMessageBuilder())
    pipeline.add_component("agent", agent)

    pipeline.connect("synthesis_message_builder.messages", "agent.messages")

    return pipeline
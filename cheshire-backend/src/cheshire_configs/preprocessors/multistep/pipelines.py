import json
from haystack import Pipeline
from haystack.components.agents import Agent
from haystack.utils import Secret
from haystack.tools import Tool

from haystack_integrations.components.generators.openrouter import OpenRouterChatGenerator

from cheshire_configs.preprocessors.multistep.components.chunker import MultistepDoclingConverter
from cheshire_configs.preprocessors.multistep.components.message_builder import ChunkMessageBuilder
from cheshire_configs.preprocessors.multistep.components.findings_parser import FindingsParser
from cheshire_configs.preprocessors.multistep.components.synthesis_message_builder import SynthesisMessageBuilder
from cheshire_configs.preprocessors.multistep.components.synthesis_parser import SynthesisParser

from typing import cast
from tools.exa import web_search
from cheshire_configs.preprocessors.multistep.tools import get_standard, query_other_section

from dotenv import load_dotenv
load_dotenv("../../../.env.user")

PASS1_SYSTEM_PROMPT_TEMPLATE = """\
Role: Technical design document auditor.

INPUT
Text: [ID:<ref>|<label>|p<n>]
Figures: [Figure ID:<ref>|p<n>]

TOOLS
- get_standard(standard_id): Required before citing. Available: {standard_ids}
- web_search(query): For external claims only.
- query_other_section(section_title): Retrieve content of another section by its title.

OUTPUT
JSON array of findings (or []).
Finding format:
{
  "element_id": "str",
  "figure_id": "str|null",
  "sub_bbox": "[x1,y1,x2,y2]|null", # within figure crop
  "element_type": "section_heading|paragraph|diagram_node|diagram_edge|table_cell|table_header|caption|code_block|list_item",
  "finding": "str",
  "standard_ref": "str", # must fetch first
  "severity": "critical|high|medium|low|observation",
  "confidence": "float" # 0.0-1.0
}

CONSTRAINTS
- sub_bbox is in figure crop coordinates.
- Call get_standard before citing any standard.\
"""


def _make_system_prompt(standards_path: str = "standards.json") -> str:
    with open(standards_path) as f:
        standard_ids = ", ".join(json.load(f).keys())
    return PASS1_SYSTEM_PROMPT_TEMPLATE.format(standard_ids=standard_ids)


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


def build_evaluation_pipeline(standards_path: str = "standards.json") -> Pipeline:
    generator = OpenRouterChatGenerator(
        api_key=Secret.from_env_var("OPENROUTER_API_KEY"),
        model=os.getenv("OPENROUTER_MODEL", "ServiceNow-AI/Apriel-1.6-15b-Thinker"),
    )

    agent = Agent(
        chat_generator=generator,
        tools=_make_tools(),
        system_prompt=_make_system_prompt(standards_path),
        max_agent_steps=10,
        exit_conditions=["text"]
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

    pipeline = Pipeline()
    pipeline.add_component("synthesis_message_builder", SynthesisMessageBuilder())
    pipeline.add_component("generator", generator)
    pipeline.add_component("synthesis_parser", SynthesisParser())

    pipeline.connect("synthesis_message_builder.messages", "generator.messages")
    pipeline.connect("generator.replies", "synthesis_parser.replies")

    return pipeline
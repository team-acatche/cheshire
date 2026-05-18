import json
from haystack import Pipeline
from haystack.components.agents import Agent
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.utils import Secret
from haystack.tools import Tool

from cheshire_configs.preprocessors.multistep.components.chunker import MultistepDoclingConverter
from cheshire_configs.preprocessors.multistep.components.message_builder import ChunkMessageBuilder
from cheshire_configs.preprocessors.multistep.components.findings_parser import FindingsParser

# TODO: fix;  from tools import get_standard, web_search

from dotenv import load_dotenv
load_dotenv("../../../.env.user")

PASS1_SYSTEM_PROMPT_TEMPLATE = """\
You are a technical design document auditor evaluating one document section.

INPUT
Text elements are tagged [ID:<ref>|<label>|p<n>]. Figures appear as images
tagged [Figure ID:<ref>|p<n>]. A document index provides global context.

TOOLS — call before acting on any result
  get_standard(standard_id)  →  Call before citing any standard.
                                Available IDs: {standard_ids}
  web_search(query)          →  Only to verify external technical claims.

OUTPUT  Return only a JSON array. Empty array [] if no issues found.
Each finding:
  element_id    string       ID tag of the affected element
  figure_id     string|null  Figure ID if finding concerns a figure; else null
  sub_bbox      int[4]|null  [x1,y1,x2,y2] within the figure crop in pixels;
                             null if you cannot locate precisely — do not guess
  element_type  string       section_heading|paragraph|diagram_node|diagram_edge|
                             table_cell|table_header|caption|code_block|list_item
  finding       string       Specific description of the issue
  standard_ref  string       Standard ID; must have been retrieved first
  severity      string       critical|high|medium|low|observation
  confidence    float        0.0–1.0

CONSTRAINTS
  sub_bbox coordinates are within the figure crop image, not the page.
  Never cite a standard without first calling get_standard.\
"""


def _make_system_prompt(standards_path: str = "standards.json") -> str:
    with open(standards_path) as f:
        standard_ids = ", ".join(json.load(f).keys())
    return PASS1_SYSTEM_PROMPT_TEMPLATE.format(standard_ids=standard_ids)


def _make_tools() -> list[Tool]:
    with open("standards.json") as f:
        standards: dict = json.load(f)

    standards_tool = Tool(
        name="get_standard",
        description=(
            "Retrieve the full text of a design standard by its ID. "
            "Call this before citing any standard in a finding."
        ),
        function=lambda standard_id: standards.get(
            standard_id, f"Standard '{standard_id}' not found."
        ),
        parameters={
            "type": "object",
            "properties": {
                "standard_id": {
                    "type": "string",
                    "description": "The standard ID to retrieve, e.g. 'SEC-4.1'"
                }
            },
            "required": ["standard_id"]
        }
    )

    web_search_tool = Tool(
        name="web_search",
        description=(
            "Search the web to verify an external technical claim, "
            "check whether a protocol or technology is current, "
            "or look up an external specification."
        ),
        function=web_search,
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                }
            },
            "required": ["query"]
        }
    )

    return [standards_tool, web_search_tool]


def build_preprocessing_pipeline() -> Pipeline:
    pipeline = Pipeline()

    pipeline.add_component(
        "docling_converter",
        DoclingConverter(images_scale=2.0)
    )

    # Single-component pipeline — no connections needed
    return pipeline


def build_evaluation_pipeline(standards_path: str = "standards.json") -> Pipeline:
    generator = OpenAIChatGenerator(
        api_key=Secret.from_env_var("OPENROUTER_API_KEY"),
        api_base_url="https://openrouter.ai/api/v1",
        model="qwen/qwen3-vl-235b-a22b-instruct",
        generation_kwargs={"max_tokens": 2048}
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
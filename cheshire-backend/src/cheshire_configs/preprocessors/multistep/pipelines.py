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

CONTEXT
You are evaluating one section of a larger document at a time. The full 
document index is provided so you can see all sections, tables, and figures 
that exist across the entire document. Use query_other_section to inspect 
content from other sections when needed.

IMPORTANT:
- Do NOT flag a section as "missing" simply because it is not in the current 
chunk — check the document index first. All sections in the document are 
listed there.
- Do NOT flag content as "incomplete" or "cut off" if it appears at the 
boundary of the current section. Adjacent sections may continue the content.
- Tables may span multiple chunks. Do NOT flag table headers as missing if 
the current chunk contains continuation rows — the headers are in the 
preceding chunk of the same section.

INPUT
Text: [ID:<ref>|<label>|p<n>]
Figures: [Figure ID:<ref>|p<n>]

TOOLS
- get_standard(query): Search for relevant requirements from the company's 
internal security standards. Results are from company-specific guidelines — 
reference them as "company standard" in your findings, not by external 
framework names.
- web_search(query): Used to research external technical vulnerabilities and 
attack patterns not covered by the company standards.
- query_other_section(section_title): Retrieve content of another section by 
its title. Use this to verify cross-references or check if content exists 
elsewhere in the document before flagging it as missing.
- add_local_finding(finding): Record a local vulnerability/finding gap. The `finding` dictionary must match the schema: { "title": "str (short descriptive summary of the finding)", "element_id": "str", "figure_id": "str|null", "sub_bbox": [x1,y1,x2,y2]|null, "element_type": "section_heading|paragraph|diagram_node|diagram_edge|table_cell|table_header|caption|code_block|list_item", "finding": "str (detailed description of the vulnerability)", "standard_ref": "str", "severity": "critical|high|medium|low|observation", "confidence": float }

CONSTRAINTS
- sub_bbox is in figure crop coordinates.
- Call get_standard to retrieve relevant requirements before citing any 
standard. Reference results as "company standard", not by external 
framework names (e.g. do not say "ASVS 1.1" or such).
- Use web_search specifically to investigate technical vulnerabilities not 
covered by company standards.
- You MUST call add_local_finding for every finding. This is the primary 
output channel.
- Do NOT report findings about missing sections or incomplete content — 
only report actual security vulnerabilities, compliance gaps, or design 
flaws found in the content that is present.
- web_references MUST only contain URLs that were actually returned by 
web_search or get_standard tool calls. Do NOT fabricate, guess, or 
hallucinate URLs, document names, or reference identifiers.
- If figures/diagrams are included in this section, their images are 
embedded in the message. Visually evaluate them for correctness, 
completeness, and security design quality. Do NOT claim a diagram is 
missing if its image is attached.
- If no findings, no action is needed.
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


from haystack.tools import create_tool_from_function
from cheshire_configs.preprocessors.multistep.tools import add_local_finding, accept_local_finding
from cheshire_configs.preprocessors.multistep.helpers import LocalFinding

def add_local_finding_tool(state_key: str) -> Tool:
    _tool = create_tool_from_function(
        function=add_local_finding,
        description="Record a local vulnerability/finding gap.",
        outputs_to_state={state_key: {"source": "finding"}}
    )
    _tool.warm_up()
    return _tool

def accept_local_finding_tool(state_key: str) -> Tool:
    _tool = create_tool_from_function(
        function=accept_local_finding,
        description="Accept a local finding as valid and non-duplicate. Call this for each unique local finding you want to keep.",
        outputs_to_state={state_key: {"source": "finding"}}
    )
    _tool.warm_up()
    return _tool



def build_evaluation_pipeline() -> Pipeline:
    generator = OpenRouterChatGenerator(
        api_key=Secret.from_env_var("OPENROUTER_API_KEY"),
        model=os.getenv("OPENROUTER_MODEL", "ServiceNow-AI/Apriel-1.6-15b-Thinker"),
    )

    from cheshire_configs.preprocessors.multistep.pipelines import add_local_finding_tool
    agent_tools = _make_tools() + [add_local_finding_tool("findings_list")]

    agent = Agent(
        chat_generator=generator,
        tools=agent_tools,
        system_prompt=PASS1_SYSTEM_PROMPT,
        max_agent_steps=10,
        exit_conditions=["text"],
        state_schema={
            "findings_list": {"type": list},
        }
    )

    pipeline = Pipeline()
    pipeline.add_component("chunk_message_builder", ChunkMessageBuilder())
    pipeline.add_component("agent", agent)

    pipeline.connect("chunk_message_builder.messages", "agent.messages")

    return pipeline

def build_synthesis_pipeline() -> Pipeline:
    generator = OpenRouterChatGenerator(
        api_key=Secret.from_env_var("OPENROUTER_API_KEY"),
        model=os.getenv("OPENROUTER_MODEL", "ServiceNow-AI/Apriel-1.6-15b-Thinker"),
    )

    from tools.base import flag_contradiction_tool
    from tools.helpers.output_schema import Contradiction

    agent = Agent(
        chat_generator=generator,
        tools=[
            accept_local_finding_tool("accepted_findings"),
            flag_contradiction_tool("contradictions"),
        ],
        system_prompt=PASS2_SYSTEM_PROMPT,
        max_agent_steps=200,
        exit_conditions=["text"],
        state_schema={
            "accepted_findings": {"type": list[LocalFinding]},
            "contradictions": {"type": list[Contradiction]},
        }
    )

    pipeline = Pipeline()
    pipeline.add_component("synthesis_message_builder", SynthesisMessageBuilder())
    pipeline.add_component("agent", agent)

    pipeline.connect("synthesis_message_builder.messages", "agent.messages")

    return pipeline
import json
import os
from haystack import Pipeline
from haystack.components.agents import Agent
from haystack.utils import Secret
from haystack.tools import Tool, create_tool_from_function

from haystack_integrations.components.generators.openrouter import OpenRouterChatGenerator

from cheshire_configs.preprocessors.multistep.helpers import EvaluationChunk, LocalFinding
from cheshire_configs.preprocessors.multistep.components.chunker import MultistepDoclingConverter
from cheshire_configs.preprocessors.multistep.components.message_builder import ChunkMessageBuilder
from cheshire_configs.preprocessors.multistep.components.findings_parser import FindingsParser
from cheshire_configs.preprocessors.multistep.components.synthesis_message_builder import SynthesisMessageBuilder
from cheshire_configs.preprocessors.multistep.tools import add_local_finding, accept_local_finding

from typing import cast
from tools.exa import web_search
from cheshire_configs.preprocessors.multistep.tools import query_other_section
from tools.helpers.output_schema import VulnerabilityDetails
from globals import STANDARDS_DIR

from dotenv import load_dotenv
load_dotenv("../../../.env.user")


def _load_standards_as_list(filename: str) -> str:
    path = STANDARDS_DIR / filename
    if not path.is_file():
        return "No specific rules configured."
    try:
        with open(path, "r", encoding="utf-8") as f:
            rules = json.load(f)
        if isinstance(rules, list):
            return "\n".join(f"- {r}" for r in rules if isinstance(r, str) and r.strip())
    except Exception as e:
        return f"Error loading standards from {filename}: {e}"
    return "No specific rules configured."


def build_pass1_system_prompt() -> str:
    local_rules = _load_standards_as_list("local_rules.json")
    return f"""\
Role: Technical design document auditor (Local Section & Diagram Quality).
Target Model: Qwen 3 VL 235B

CONTEXT
You are evaluating one section of a larger document at a time. The full document index is provided so you can see all sections, tables, and figures that exist across the entire document. Use query_other_section to inspect content from other sections when needed.

MANDATORY LOCAL STANDARDS CHECKLIST:
{local_rules}

INPUT FORMAT
Text: [ID:<ref>|<label>|p<n>]
Figures: [Figure ID:<ref>|p<n>] (images are attached)

TOOLS
- query_other_section(section_title): Retrieve content of another section by its title. Use this to verify cross-references before flagging issues.
- web_search(query): RESTRICTED. Use ONLY to check whether a specific software library or version mentioned in the text is deprecated or outdated. Do NOT search for generic external vulnerabilities.
- add_local_finding(finding): Record a local vulnerability or compliance gap. The `finding` dictionary must match the schema:
  {{
    "title": "str (short descriptive summary)",
    "element_id": "str (MUST NOT be null; anchor to element tag or closest section heading tag)",
    "figure_id": "str|null",
    "sub_bbox": [x1, y1, x2, y2]|null (0-1000 scale in figure crop coordinates),
    "element_type": "section_heading|paragraph|diagram_node|diagram_edge|table_cell|table_header|caption|code_block|list_item",
    "finding": "str (detailed description including verbatim standard citation)",
    "standard_ref": "str (exact quoted standard text)",
    "severity": "critical|high|medium|low|observation",
    "confidence": float (0.0 to 1.0),
    "recommendations": list["str"],
    "web_references": list["str (valid HTTP/HTTPS URLs only, empty list if none)"]
  }}

AUDIT RULES & CONSTRAINTS

1. LOCAL CHECKLIST COMPLIANCE:
- Evaluate the present section against the mandatory local standards checklist above.
- Verify technical specifications contain no empty fields and no outdated or deprecated components.
- If evaluating the Reports section: confirm the Reports table has all required columns (Report, New/Existing, Description, Attachment, Class/Module) and no missing cells.
- If evaluating the Estimates section: confirm it includes time estimates for all 6 required phases (Technical Specifications, Requirements Definition, Implementation, Coding & Unit Testing, System Testing, UAT). Flag any phase missing from this section.
- Do NOT flag whole missing sections or whole missing diagrams—global document inventory is audited in Pass 2.

2. EXTERNAL REFERENCES & DELEGATED CONTENT:
- Do NOT flag details or requirements as missing if the document explicitly delegates or references them to an external companion document (e.g., Solutions Document, Requirements Document, external API specification, or third-party contract listed in Reference Documents).
- It is standard and expected for technical design documents to omit details that are formally specified in referenced companion documents.

3. VISUAL DIAGRAM QUALITY & DRAFTING NORMS:
- Visually evaluate all embedded diagram images across four criteria:
  * Correctness: Accurate data/control flows, valid technical relationships, and explicit security/trust boundaries.
  * Appropriateness: Matches the defined project and section text.
  * Clarity: Legible labels, clear directionality, clean layout.
  * Drafting Norms: Flowcharts and sequence diagrams MUST follow standard architectural drafting conventions: use orthogonal routing (flag curved lines or splines) and standard symbols (rectangles for processes, diamonds for decisions).
- For diagram findings: specify figure_id, localized sub_bbox ([x1, y1, x2, y2] in 0-1000 scale), and element_type ("diagram_node", "diagram_edge", or "caption").

4. PROVENANCE & FRONTEND ANCHORING:
- MANDATORY FRONTEND ANCHORING: Never leave element_id null. When flagging a missing item or gap, anchor it to the relevant section_heading or parent paragraph ID so the UI can render a visible, clickable highlight on the PDF canvas.
- In "standard_ref": quote the exact text of the requirement from the checklist above.
- In "finding": explicitly embed the standard provenance: "[Company Standard: '<exact requirement>'] <detailed description of gap>."
- "web_references": MUST only contain valid HTTP/HTTPS URLs returned by web_search (for deprecated software checks). Leave as [] if none.
- Boundary awareness: Do not flag content as truncated or missing simply because it continues across chunk or table boundaries.
- If no local violations, take no action.
"""


PASS1_SYSTEM_PROMPT = build_pass1_system_prompt()


def _make_tools() -> list[Tool]:
    return [cast(Tool, web_search), cast(Tool, query_other_section)]


def build_preprocessing_pipeline() -> Pipeline:
    pipeline: Pipeline = Pipeline()

    pipeline.add_component(
        "docling_converter",
        MultistepDoclingConverter(images_scale=2.0)
    )

    # Single-component pipeline — no connections needed
    return pipeline


def add_local_finding_tool(state_key: str) -> Tool:
    _tool: Tool = create_tool_from_function(
        function=add_local_finding,
        description="Record a local vulnerability/finding gap.",
        outputs_to_state={state_key: {"source": "finding"}}
    )
    _tool.warm_up()
    return _tool

def accept_local_finding_tool(state_key: str) -> Tool:
    _tool: Tool = create_tool_from_function(
        function=accept_local_finding,
        description="Accept a local finding as valid and non-duplicate. Call this for each unique local finding you want to keep.",
        outputs_to_state={state_key: {"source": "finding"}}
    )
    _tool.warm_up()
    return _tool



def build_evaluation_pipeline() -> Pipeline:
    generator: OpenRouterChatGenerator = OpenRouterChatGenerator(
        api_key=Secret.from_env_var("OPENROUTER_API_KEY"),
        model=os.getenv("OPENROUTER_MODEL", "ServiceNow-AI/Apriel-1.6-15b-Thinker"),
    )

    agent_tools: list[Tool] = _make_tools() + [add_local_finding_tool("findings_list")]

    agent: Agent = Agent(
        chat_generator=generator,
        tools=agent_tools,
        system_prompt=build_pass1_system_prompt(),
        max_agent_steps=10,
        exit_conditions=["text"],
        state_schema={
            "chunks_cache": {"type": list[EvaluationChunk]},
            "findings_list": {"type": list},
        }
    )

    pipeline: Pipeline = Pipeline()
    pipeline.add_component("chunk_message_builder", ChunkMessageBuilder())
    pipeline.add_component("agent", agent)

    pipeline.connect("chunk_message_builder.messages", "agent.messages")

    return pipeline


def build_pass2_system_prompt() -> str:
    global_rules = _load_standards_as_list("global_rules.json")
    return f"""\
Role: Technical reviewer & document-level compliance synthesizer.

OBJECTIVE
Synthesize local findings from Pass 1 (deduplicate and resolve contradictions) and execute the global company standards checklist audit against the entire document structure.

MANDATORY GLOBAL STANDARDS CHECKLIST:
{global_rules}

INPUT
1. Document Index: Full inventory of sections, tables, figures, and page gaps across the PDF.
2. All Findings: Array of local findings from Pass 1.

TOOLS
- accept_local_finding(finding): Accept a local finding as valid, or record a new document-level finding. The `finding` dictionary must match the schema:
  {{
    "title": "str",
    "element_id": "str (MUST NOT be null; anchor to existing section ID from document index)",
    "figure_id": "str|null",
    "sub_bbox": [x1, y1, x2, y2]|null,
    "element_type": "str",
    "finding": "str",
    "standard_ref": "str",
    "severity": "str",
    "confidence": float,
    "recommendations": ["str"],
    "web_references": ["str"]
  }}
- flag_contradiction(finding_a_title, finding_b_title, description): Flag two findings that contradict each other across sections.

TASKS

TASK 1: DEDUPLICATION & CONTRADICTION RESOLUTION
1. Review all input findings from Pass 1.
2. Deduplicate: if multiple findings describe the same issue across different sections, keep only the most detailed version.
3. If two findings contradict each other, call flag_contradiction.
4. For each unique, valid finding, call accept_local_finding with the original fields preserved.

TASK 2: GLOBAL STANDARDS CHECKLIST AUDIT
Audit the document index and Pass 1 findings against the mandatory global checklist above:
1. Required Sections: Verify the document index contains all required sections and subsections:
   A. Overview; B. Reference Documents; C. Technical Specifications; D. Technology Stack Requirements; E. Processing Specifications (1. Modules, 2. Diagrams, 3. Files and Records, 4. Reports, 5. Parameter and Lookup Files); F. System Considerations; G. Security Considerations; H. Estimates; I. Attachments; J. Sonar Scan Result; K. Appendices.
2. Required Diagrams: Verify the document contains all 4 mandatory diagram types (inspect document index figure captions and Pass 1 findings):
   1. Data Flow Diagram, 2. Network Diagram, 3. Sequence Diagram, 4. Process Flow Diagram.
3. Required Tables: Verify the Reports table exists in document index tables or findings.
4. Required Reference Documents: Verify Solutions and Requirements documents are listed under Reference Documents.
5. Third-Party Contract: Verify reference to third-party contract if applicable.

TASK 3: EXTERNAL REFERENCES & DELEGATED CONTENT
- Do NOT flag details as missing if the document index indicates they are covered in companion documents listed under Section B (Reference Documents).

RECORDING GLOBAL OMISSIONS (FRONTEND SAFE):
- For any missing section, diagram, table, or reference document: call accept_local_finding.
- MANDATORY ANCHORING: Never leave element_id null. Anchor the missing finding to the closest related section ID in document_index (e.g. anchor missing diagrams to Section E / Diagrams, or anchor a missing top-level section to Section A. Overview or the preceding section).
- In "finding", format as: "[Company Standard: '<exact requirement>'] Document is non-compliant: <details of missing section, diagram, or table>."
- Set severity to "high" or "critical", confidence to 1.0, and provide actionable remediation in "recommendations".

CONSTRAINTS
- You MUST call accept_local_finding for every valid, non-duplicate finding. This is the only way findings are recorded.
- Preserve ALL original fields exactly as given when accepting valid Pass 1 findings.
- Do NOT accept duplicate findings.
- After processing all findings, output a brief text summary of what you did.
"""


PASS2_SYSTEM_PROMPT = build_pass2_system_prompt()


def build_synthesis_pipeline() -> Pipeline:
    generator: OpenRouterChatGenerator = OpenRouterChatGenerator(
        api_key=Secret.from_env_var("OPENROUTER_API_KEY"),
        model=os.getenv("OPENROUTER_MODEL", "ServiceNow-AI/Apriel-1.6-15b-Thinker"),
    )

    from tools.base import flag_contradiction_tool
    from tools.helpers.output_schema import Contradiction

    agent: Agent = Agent(
        chat_generator=generator,
        tools=[
            accept_local_finding_tool("accepted_findings"),
            flag_contradiction_tool("contradictions"),
        ],
        system_prompt=build_pass2_system_prompt(),
        max_agent_steps=200,
        exit_conditions=["text"],
        state_schema={
            "accepted_findings": {"type": list[LocalFinding]},
            "contradictions": {"type": list[Contradiction]},
        }
    )

    pipeline: Pipeline = Pipeline()
    pipeline.add_component("synthesis_message_builder", SynthesisMessageBuilder())
    pipeline.add_component("agent", agent)

    pipeline.connect("synthesis_message_builder.messages", "agent.messages")

    return pipeline
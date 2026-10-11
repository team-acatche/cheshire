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
    "title": "str (concise, direct summary of the issue, e.g. 'Reports Table: Missing Class/Module Field' or 'Compatibility: Deprecated Runtime Version')",
    "element_id": "str (MUST NOT be null; anchor to element tag or closest section heading tag)",
    "figure_id": "str|null",
    "sub_bbox": [x1, y1, x2, y2]|null (0-1000 scale in figure crop coordinates),
    "element_type": "section_heading|paragraph|diagram_node|diagram_edge|table_cell|table_header|caption|code_block|list_item",
    "finding": "str (detailed description explaining why the element violates the company standard)",
    "standard_ref": "str (exact quoted standard text from the checklist)",
    "severity": "critical|high|medium|low|observation",
    "confidence": float (0.0 to 1.0),
    "recommendations": ["Actionable recommendation 1", "Actionable recommendation 2"],
    "web_references": ["https://example.com/reference-url"]
  }}

AUDIT RULES & CONSTRAINTS

1. NARROW ADMINISTRATIVE EXCLUSION (WHAT TO SKIP VS. AUDIT):
- ONLY the following managerial blocks are excluded from standards evaluation:
  * Approvals, "Approved By", "Reviewed By", sign-off tables, and signature/date rows.
  * Version/Revision history tables, changelogs, author metadata, and distribution lists.
  * Do NOT flag missing signatures, unpopulated dates, or empty cells in these administrative blocks.
- IN-SCOPE FOR AUDITING (DO NOT SKIP):
  * ALL technical, architectural, operational, and system specifications across the document MUST be audited.
  * COMPATIBILITY SPECIFICATIONS (e.g., supported client/server operating systems, browsers, runtimes, frameworks, network protocols, hardware): Rigorously audit these for outdated, deprecated, or end-of-life components (Standard #1).
  * RETENTION SPECIFICATIONS (e.g., data retention periods, log retention, record archiving schedules, purge routines, backup policies): Verify these contain complete parameters and no empty fields or deprecated mechanisms.
  * Any section containing specifications, system considerations, configurations, or technical parameters is strictly in-scope.

2. TABLE AUDITING & SECTION SCOPING:
- REPORTS TABLE SCOPING:
  * You MUST only evaluate a table against the Reports schema (`Report`, `New/Existing`, `Description`, `Attachment`, `Class/Module`) if the current section heading explicitly indicates it is the Reports section (e.g. `Reports`, `4. Reports`, `E.4 Reports`, `Processing Specifications - Reports`).
  * Other tables (such as `Lookup Files`, `Parameters`, `Modules`, `Files and Records`, `Compatibility`, `Estimates`, `Attachments`) are NOT Reports tables. NEVER evaluate them against Reports table columns.
- EMPTY CELLS VS. VALID MEDIA/LINKS:
  * Table cells containing hyperlinks, URLs, attachment paths/references, icons, or embedded images/diagrams are VALIDLY POPULATED. NEVER mark them as empty.
  * Table cells containing placeholders such as "---", "--", "-", "N/A", "n/a", "None", "null", "TBD", "TODO", "[ ]", or blank whitespace are EMPTY/UNPOPULATED. If a required field in the Reports table or technical specifications contains one of these placeholders, flag it as a missing/empty field.
- EMPTY VS. NON-COMPLIANT:
  * Distinguish between "empty/missing" (when a field, cell, value, or estimate phase is absent or filled with a placeholder like "---") and "non-compliant/outdated" (when content is present but deprecated, obsolete, invalid, or violates architectural standards). Do not label non-compliant specifications as "empty".

3. LOCAL CHECKLIST COMPLIANCE:
- Evaluate the present section against the mandatory local standards checklist above.
- Verify technical specifications contain no empty fields and no outdated or deprecated components.
- If evaluating the Estimates section: confirm it includes time estimates for all 6 required phases (Technical Specifications, Requirements Definition, Implementation, Coding & Unit Testing, System Testing, UAT). Flag any phase missing from this section.
- Do NOT flag whole missing sections or whole missing diagrams—global document inventory is audited in Pass 2.

4. EXTERNAL REFERENCES & DELEGATED CONTENT:
- Do NOT flag details or requirements as missing if the document explicitly delegates or references them to an external companion document (e.g., Solutions Document, Requirements Document / System Requirements Specification, external API specification, or third-party contract listed in Reference Documents).
- It is standard and expected for technical design documents to omit details that are formally specified in referenced companion documents.

5. VISUAL DIAGRAM QUALITY & DRAFTING NORMS:
- Visually evaluate all embedded diagram images across four criteria:
  * Correctness: Accurate data/control flows, valid technical relationships, and explicit security/trust boundaries.
  * Appropriateness: Matches the defined project and section text.
  * Clarity: Legible labels, clear directionality, clean layout.
  * Drafting Norms: Flowcharts and sequence diagrams MUST follow standard architectural drafting conventions: use orthogonal routing (flag curved lines or splines) and standard symbols (rectangles for processes, diamonds for decisions).
- For diagram findings: specify figure_id, localized sub_bbox ([x1, y1, x2, y2] in 0-1000 scale), and element_type ("diagram_node", "diagram_edge", or "caption").

6. PROVENANCE & FRONTEND ANCHORING:
- MANDATORY FRONTEND ANCHORING: Never leave element_id null. When flagging a missing item or gap, anchor it to the relevant section_heading or parent paragraph ID so the UI can render a visible, clickable highlight on the PDF canvas.
- In "title": Provide a concise, plain-English summary. Do NOT include "[Company Standard: '...']" in the title.
- In "standard_ref": Quote the exact text of the requirement from the checklist above.
- In "finding": Clearly explain the violation and standard requirement.
- "web_references": MUST only contain valid HTTP/HTTPS URLs returned by web_search (for deprecated software checks). Leave as [] if none.
- Boundary awareness: Do not flag content as truncated or missing simply because it continues across chunk or table boundaries.
- If multiple local violations exist in this section, invoke add_local_finding for each violation. If no violations exist, take no action.

7. JSON ARRAY FORMAT:
- "recommendations" and "web_references" MUST be native JSON arrays of strings like ["item1", "item2"]. NEVER format them as a single string containing brackets or single quotes like "['item']". If there are no web references, pass an empty array [].
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
        exit_conditions=["text", "add_local_finding"],
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
    "title": "str (clean, concise summary, e.g. 'Missing Section: Sonar Scan Result')",
    "element_id": "str (MUST NOT be null; anchor to existing section ID from document index)",
    "figure_id": "str|null",
    "sub_bbox": [x1, y1, x2, y2]|null,
    "element_type": "str",
    "finding": "str (detailed description of the compliance gap)",
    "standard_ref": "str (exact quoted standard text from global checklist)",
    "severity": "str",
    "confidence": float,
    "recommendations": ["Actionable remediation step 1"],
    "web_references": ["https://example.com/reference-url"]
  }}
- flag_contradiction(finding_a_title, finding_b_title, description): Flag two findings that contradict each other across sections.

TASKS

TASK 1: DEDUPLICATION & CONTRADICTION RESOLUTION
1. Review all input findings from Pass 1.
2. Deduplicate: if multiple findings describe the same issue across different sections, keep only the most detailed version.
3. Discard any finding from Pass 1 that targets purely administrative or managerial content (such as Version History, Approver blocks, or Document Control tables).
4. If two findings contradict each other, call flag_contradiction.
5. For each unique, valid finding, call accept_local_finding with the original fields preserved.

TASK 2: GLOBAL STANDARDS CHECKLIST AUDIT
Audit the document index and Pass 1 findings against the mandatory global checklist above:

1. Required Sections (SEMANTIC MATCHING):
   - Check `document_index["sections"]` by semantic topic and intent, NOT by exact letter prefixes (A, B, C...) or numbering:
     * Overview (matches "Overview", "1. Overview", "Executive Summary")
     * Reference Documents (matches "Reference Documents", "References", "Related Documents")
     * Technical Specifications (matches "Technical Specifications", "Technical Specs", "Specifications")
     * Technology Stack Requirements (matches "Technology Stack Requirements", "Technology Stack", "Tech Stack")
     * Processing Specifications (matches "Processing Specifications", "Processing") and subsections: Modules, Diagrams, Files and Records, Reports, Parameter and Lookup Files
     * System Considerations (matches "System Considerations", "Operational Considerations")
     * Security Considerations (matches "Security Considerations", "Security Architecture")
     * Estimates (matches "Estimates", "Project Estimates", "Effort Estimates")
     * Attachments (matches "Attachments", "Exhibits")
     * Sonar Scan Result (matches "Sonar Scan Result", "SonarQube Results", "Sonar Analysis", "Static Code Analysis")
     * Appendices (matches "Appendices", "Appendix")
   - CRITICAL: Only flag a required section as missing if there is GENUINELY NO corresponding section in `document_index["sections"]`. Do NOT flag sections as missing simply because they omit letter prefixes like "A." or "B.".

2. Required Reference Documents (ALIAS RECOGNITION):
   - Check Reference Documents / References in `document_index["sections"]` and Pass 1 findings.
   - Recognize that standard industry titles satisfy the "Requirements Document" requirement:
     * "System Requirements Specification" (SRS), "Software Requirements Specification", "Business Requirements Document" (BRD), or "Requirements Specification" ALL satisfy the Requirements Document standard. Do NOT flag the Requirements Document as missing if any of these are referenced.
     * "Solutions Document", "Solutions Architecture Document", or "Solution Design" satisfies the Solutions Document standard.

3. Required Diagrams:
   - Verify the document contains all 4 mandatory diagram types (inspect `document_index["figures"]` captions, sections, and Pass 1 findings):
     1. Data Flow Diagram, 2. Network Diagram, 3. Sequence Diagram, 4. Process Flow Diagram.

4. Required Tables (Reports Table):
   - Check `document_index["tables"]`: if any table has `"section"` indicating "Reports" (e.g. section title contains "Reports"), or if Pass 1 evaluated a table under the Reports section, the Reports table exists. Only flag missing if no table exists under the Reports section.

5. Third-Party Contract:
   - Verify reference to third-party contract if applicable.

TASK 3: EXTERNAL REFERENCES & DELEGATED CONTENT
- Do NOT flag details as missing if the document index indicates they are covered in companion documents listed under Reference Documents.

RECORDING GLOBAL OMISSIONS (FRONTEND SAFE):
- For any missing section, diagram, table, or reference document: call accept_local_finding.
- MANDATORY ANCHORING: Never leave element_id null. Anchor the missing finding to the closest related section ID in document_index (e.g. anchor missing diagrams to Section E / Diagrams, or anchor a missing top-level section to Section A / Overview or the preceding section).
- In "title": Provide a clean, concise title (e.g. 'Missing Section: Sonar Scan Result'). Do NOT wrap in "[Company Standard: '...']".
- In "standard_ref": Quote the exact requirement from the global checklist above.
- In "finding": Document the non-compliance clearly: "<exact requirement> is missing: <details>."
- Set severity to "high" or "critical", confidence to 1.0, and provide actionable remediation in "recommendations".

CONSTRAINTS
- You MUST call accept_local_finding for every valid, non-duplicate finding. This is the only way findings are recorded.
- Preserve ALL original fields exactly as given when accepting valid Pass 1 findings.
- Do NOT accept duplicate findings.
- "recommendations" and "web_references" MUST be native JSON arrays of strings. If none, pass [].
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
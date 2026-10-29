import json
import os
from haystack import Pipeline
from haystack.components.agents import Agent
from haystack.utils import Secret
from haystack.tools import Tool, create_tool_from_function

from haystack_integrations.components.generators.openrouter import OpenRouterChatGenerator
from cheshire_configs.resilient_generator import make_resilient_openrouter_generator

from cheshire_configs.preprocessors.multistep.helpers import (
    EvaluationChunk,
    LocalFinding,
    ASSUME_EXTERNAL_ATTACHMENTS_COMPLIANT,
)
from cheshire_configs.preprocessors.multistep.components.chunker import MultistepDoclingConverter
from cheshire_configs.preprocessors.multistep.components.message_builder import ChunkMessageBuilder
from cheshire_configs.preprocessors.multistep.components.findings_parser import FindingsParser

from cheshire_configs.preprocessors.multistep.tools import add_local_finding, accept_local_finding, merge_findings

import re
from typing import cast, Optional, Any
from tools.exa import web_search
from cheshire_configs.preprocessors.multistep.tools import query_other_section
from tools.helpers.output_schema import VulnerabilityDetails
from globals import DATA_PATH, STANDARDS_DIR
from knowledge_base.repository import KnowledgeRepository
from knowledge_base.qdrant import QdrantRepositoryManager

from dotenv import load_dotenv
load_dotenv("../../../.env.user")

# regex patterns matching document-level rules
GLOBAL_RULE_PATTERNS = [
    re.compile(r"(?i)\bthe document must (contain|include|have)\b"),
    re.compile(r"(?i)\bthe document should (contain|include|have)\b"),
    re.compile(r"(?i)\bdocument must (contain|include|have)\b"),
    re.compile(r"(?i)\bdocument should (contain|include|have)\b"),
    re.compile(r"(?i)\bshould be present as a reference document\b"),
    re.compile(r"(?i)\bmust be present as a reference document\b"),
    re.compile(r"(?i)\b(table|diagram|section|reference document) should exist\b"),
    re.compile(r"(?i)\b(table|diagram|section|reference document) must exist\b"),
    re.compile(r"(?i)\bmust be present in the document\b"),
    re.compile(r"(?i)\bmust be included in the document\b"),
    re.compile(r"(?i)\bshould be present in the document\b"),
    re.compile(r"(?i)\bshould be included in the document\b"),
    re.compile(r"(?i)\bdocument-level\b"),
]

_SEEDED_EMBEDDINGS: dict[str, Any] = {}

def classify_rule_nature(rule: str, embedder: Any = None) -> str:
    # check regex patterns for global rules
    for pattern in GLOBAL_RULE_PATTERNS:
        if pattern.search(rule):
            return "global"

    # check semantic similarity against seeded rules
    try:
        from cheshire_configs.preprocessors.multistep.helpers.tables import _get_fastembed_model, _compute_cosine_similarity
        g_path = STANDARDS_DIR / "global_rules.json"
        l_path = STANDARDS_DIR / "local_rules.json"
        if not g_path.is_file() or not l_path.is_file():
            return "local"
        model = embedder if embedder is not None else _get_fastembed_model()
        if model is not None and hasattr(model, "embed"):
            if embedder is not None:
                g_rules = json.loads(g_path.read_text(encoding="utf-8"))
                l_rules = json.loads(l_path.read_text(encoding="utf-8"))
                g_embs = list(embedder.embed(g_rules))
                l_embs = list(embedder.embed(l_rules))
            else:
                if "global" not in _SEEDED_EMBEDDINGS or "local" not in _SEEDED_EMBEDDINGS:
                    g_rules = json.loads(g_path.read_text(encoding="utf-8"))
                    l_rules = json.loads(l_path.read_text(encoding="utf-8"))
                    _SEEDED_EMBEDDINGS["global"] = list(model.embed(g_rules))
                    _SEEDED_EMBEDDINGS["local"] = list(model.embed(l_rules))
                g_embs = _SEEDED_EMBEDDINGS["global"]
                l_embs = _SEEDED_EMBEDDINGS["local"]
            rule_emb = list(model.embed([rule]))[0]
            max_g = max(_compute_cosine_similarity(rule_emb, g) for g in g_embs)
            max_l = max(_compute_cosine_similarity(rule_emb, l) for g in l_embs)
            if max_g > max_l and max_g >= 0.70:
                return "global"
    except Exception:
        pass

    # fallback to local
    return "local"


def _load_user_asserted_rules(
    knowledge_repo: Optional[KnowledgeRepository] = None,
    rule_nature: Optional[str] = None,
) -> list[str]:
    # get knowledge repo from qdrant if not provided
    if knowledge_repo is None:
        _, knowledge_repo = QdrantRepositoryManager.get_repositories(DATA_PATH)

    # query facts with user_asserted source
    docs = knowledge_repo.query(filters={
        "field": "meta.source",
        "operator": "==",
        "value": "user_asserted",
    })

    rules: list[str] = []
    seen: set[str] = set()
    for doc in docs:
        content = (doc.content or "").strip()
        if not content or content in seen:
            continue
        seen.add(content)
        # filter by rule nature, checking metadata first with classifier fallback
        if rule_nature is not None:
            nature = doc.meta.get("rule_nature") or classify_rule_nature(content)
            if nature != rule_nature:
                continue
        rules.append(content)

    return rules


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


def build_pass1_system_prompt(knowledge_repo: Optional[KnowledgeRepository] = None) -> str:
    local_rules = _load_standards_as_list("local_rules.json")

    # load and append user asserted local rules
    user_rules = _load_user_asserted_rules(knowledge_repo, rule_nature="local")
    if user_rules:
        user_rules_str = "\n".join(f"- {r}" for r in user_rules)
        if local_rules and local_rules != "No specific rules configured.":
            local_rules = f"{local_rules}\n{user_rules_str}"
        else:
            local_rules = user_rules_str

    if ASSUME_EXTERNAL_ATTACHMENTS_COMPLIANT:
        attachment_figure_policy = (
            "- ATTACHMENTS & EXTERNAL LINKS (ASSUME COMPLIANT):\n"
            "  * Some figures or content might be referenced as file attachments or external links.\n"
            "  * Assume that the content within said attachments or external links is perfectly compliant.\n"
            "  * Do NOT open or attempt to fetch/inspect said attachments or links.\n"
            "- INLINE / EMBEDDED FIGURES (SCRUTINIZE FOR QUALITY):\n"
            "  * If there are figures (diagrams, architecture drawings, flowcharts) present directly within the document itself, scrutinize them thoroughly in the same way as the rest of the document to ensure high quality."
        )
    else:
        attachment_figure_policy = (
            "- ATTACHMENTS & FIGURES AUDITING:\n"
            "  * Scrutinize all figures and content, whether embedded directly or referenced as external file attachments or links, to ensure quality and compliance."
        )

    return f"""\
Role: Expert Technical Design & Security Auditor (Local Section & Diagram Quality).

CONTEXT & PREEMPTIVE OBJECTIVE
You are performing a critical preemptive evaluation of a technical design document before it is handed over to the Information Security department. Your primary objective is to lessen further walkthrough and revision cycles with InfoSec by proactively catching discrepancies early and delivering high-quality, verifiable recommendations.
You are evaluating one section of the larger document at a time. The full document index is provided so you can see all sections, tables, and figures that exist across the entire document. Use query_other_section to inspect content from other sections when cross-referencing.

CORE MANDATE & GUIDING QUESTIONS
Your ultimate job is to determine if the document contains adequate, correct information to start development. Alongside completeness and correctness, you MUST focus on answering two central questions:
1. "Is the technical design secure enough to produce a secure-by-design program once deployed?"
2. "Is the technical design specifications enough to initiate development?"
To closely mimic a security expert, you have been given the `web_search` tool to use the internet as an active knowledge base to ensure both questions are thoroughly investigated and answered.
The findings you record should help the user/author achieve higher document quality and a more secure technical design if it isn't already.

FOUR CATEGORIES OF FINDINGS TO RECORD
The discrepancies that will be recorded as findings are:
a) Company Standards: Violations of internal company rules, required document structure, schemas, tables, and lifecycle estimates.
b) Security Standards and Risk: Architectural vulnerabilities, unmitigated attack surfaces, missing encryption (in transit, at rest, TDE), authentication/authorization weaknesses, secret exposure, outdated or vulnerable components, or failure to produce a secure-by-design program.
c) Writing Quality: Ambiguities, internal contradictions across sections, vague requirements, lack of clarity, or non-standard diagramming drafting norms.
d) Content Correctness and Appropriateness: Inaccurate technical parameters, improper diagram symbols or irrelevant elements, or insufficient specification detail to initiate development.

MANDATORY LOCAL STANDARDS CHECKLIST:
{local_rules}

INPUT FORMAT
Text: [ID:<ref>|<label>|p<n>]
Figures: [Figure ID:<ref>|p<n>] (images are attached)

TOOLS
- query_other_section(section_title): Retrieve content of another section by its title. Use this to verify cross-references before flagging issues.
- web_search(query): Search the web using the internet as a security knowledge base to verify external facts, industry classifications, security standards, regulatory directives, CVEs, attack patterns, technology-specific security requirements, or software documentation. Do NOT rely on training memory for external facts.
- add_local_finding(finding): Record a local vulnerability, security gap, or compliance discrepancy. The `finding` dictionary must match the schema:
  {{
    "title": "str (concise, direct summary of the issue, e.g. 'Reports Table: Missing Class/Module Field' or 'Compatibility: Deprecated Runtime Version')",
    "element_id": "str (MUST NOT be null; anchor to element tag or closest section heading tag)",
    "figure_id": "str|null",
    "sub_bbox": [x1, y1, x2, y2]|[[x1, y1, x2, y2], ...]|null (0-1000 scale in figure crop coordinates),
    "element_type": "section_heading|paragraph|diagram_node|diagram_edge|table_cell|table_header|caption|code_block|list_item",
    "finding": "str (detailed description explaining why the element violates standards or poses risk)",
    "standard_ref": "str (exact quoted standard text from checklist if a company standard, or relevant category name like 'Security Standards & Risk', 'Writing Quality', 'Content Correctness & Appropriateness')",
    "severity": "major|minor|observation",
    "confidence": 1.0|0.8|0.6,
    "recommendations": ["Actionable recommendation 1", "Actionable recommendation 2"] (MANDATORY: must contain at least one concrete recommendation),
    "web_references": ["https://example.com/reference-url"] (MANDATORY if referencing any external fact, standard, directive, CVE, or document; pass [] only if finding is purely internal to the document)
  }}

AUDIT RULES & CONSTRAINTS

1. SITUATIONAL STANDARDS & SENSIBLE DECISION-MAKING:
- Standards and checklist items are SITUATIONAL. You must determine whether a standard applies by referencing it against the document's content, intended audience, and technology context.
- Use your capability to make justifiable and sensible decisions on which rules to apply and which to ignore depending on the situation:
  * Do NOT rigidly apply rules where the document's specific context renders them inapplicable or unnecessary.
  * For example: specifications for internal tooling do not need a Third-Party Contract; certain database encryption standards (such as Transparent Data Encryption / TDE) apply only when the project intends to use specific technologies like Azure SQL; and web-specific controls apply only when web components are present.
  * Do NOT restrict yourself to those specific examples. Apply sensible and justifiable situational reasoning to all rules and technologies found in the document.
  * When deciding that a rule does not apply to a given component or section, ensure your reasoning is grounded in the document content.

2. ATTACHMENT & FIGURE AUDITING POLICY:
{attachment_figure_policy}

3. NARROW ADMINISTRATIVE EXCLUSION (WHAT TO SKIP VS. AUDIT):
- ONLY the following managerial blocks are excluded from standards evaluation:
  * Approvals, "Approved By", "Reviewed By", sign-off tables, and signature/date rows.
  * Version/Revision history tables, changelogs, author metadata, and distribution lists.
  * Corporate page-control footers (e.g. Classification, Document Owner, Document Title, Page No.) appearing at the bottom of pages or near tables. NEVER evaluate page footers as technical content, and NEVER flag table rows or schema definitions because footer metadata appears adjacent to or within them.
  * Do NOT flag missing signatures, unpopulated dates, or empty cells in these administrative blocks.
- IN-SCOPE FOR AUDITING (DO NOT SKIP):
  * ALL technical, architectural, operational, and system specifications across the document MUST be audited.
  * COMPATIBILITY SPECIFICATIONS (e.g., supported client/server operating systems, browsers, runtimes, frameworks, network protocols, hardware): Rigorously audit these for outdated, deprecated, or end-of-life components (Standard #1).
  * RETENTION SPECIFICATIONS (e.g., data retention periods, log retention, record archiving schedules, purge routines, backup policies): Verify these contain complete parameters and no deprecated mechanisms.
  * Any section containing specifications, system considerations, configurations, or technical parameters is strictly in-scope.

4. TABLE AUDITING, SECTION SCOPING & SENSIBLE EMPTINESS:
- REPORTS TABLE SCOPING:
  * You MUST only evaluate a table against the Reports schema (`Report`, `New/Existing`, `Description`, `Attachment`, `Class/Module`) if the current section heading explicitly indicates it is the Reports section (e.g. `Reports`, `4. Reports`, `E.4 Reports`, `Processing Specifications - Reports`).
  * Other tables (such as `Lookup Files`, `Parameters`, `Modules`, `Files and Records`, `Compatibility`, `Estimates`, `Attachments`) are NOT Reports tables. NEVER evaluate them against Reports table columns.
- VALID MEDIA/LINKS & FORMAT ICONS:
  * Table cells containing hyperlinks, URLs, attachment paths/references, icons, `[Embedded Icon]` annotations, or embedded images/diagrams are VALIDLY POPULATED. NEVER mark them as empty.
  * FORMAT COLUMNS WITH EMBEDDED ICONS: In Attachments tables or specification tables where format or attachment columns display visual format badges/icons (e.g. Word, Excel, PDF icons) and are annotated with `[Embedded Icon]` or visible in the table crop: the format field is VALIDLY POPULATED. NEVER mark it as an empty field or missing format.
- SENSIBLE ALTERNATIVE FOR EMPTINESS:
  * Some table cells could be empty if they genuinely have no content or if a field is not applicable for that specific item. Empty cells should be recognized as a sensible alternative for emptiness, just like "N/A", "n/a", or "None".
  * Only flag an empty cell or missing value if that specific information is mandatory, meaningful, and necessary to initiate development or ensure security for the item in question.
  * Distinguish between genuine author omissions (where required technical parameters are missing) and sensible non-applicability.
- EMPTY VS. NON-COMPLIANT:
  * Distinguish between "empty/missing" (when a required field or estimate phase is absent) and "non-compliant/outdated" (when content is present but deprecated, obsolete, invalid, or violates security/architectural standards). Do not label non-compliant specifications as "empty".
- CONTINUATION TABLES ACROSS PAGE BREAKS:
  * Tables that span multiple pages frequently continue on the following page without repeating headers.
  * If a table on the following page continues the rows of a table from the preceding page, it is a VALID continuation table. NEVER flag continuation tables as empty, missing headers, or having an unpopulated/blank body when their continuation rows are present.
- TABLE TEXT FRAGMENTATION & MARGIN CLIPPING:
  * In tables extracted from documents, long cell content frequently experiences line-wrapping, hyphen-splitting, or margin clipping during table conversion.
  * Distinguish between genuine omissions and parser extraction artifacts. When a table cell or row is populated, NEVER flag it as "incomplete information", "malformed", or "missing content" simply because its text was line-wrapped, hyphen-split, or truncated by the markdown table extractor.

5. LOCAL CHECKLIST & SECURITY COMPLIANCE:
- Evaluate the present section against the mandatory local standards checklist and security principles.
- Verify technical specifications contain no outdated or deprecated components, and contain sufficient detail to initiate development.
- Assess whether technical specifications and configurations are secure-by-design (e.g. secure defaults, authentication, authorization, data protection).
- LEAD-IN PARAGRAPHS & SUBSECTION RELATIONSHIPS:
  * High-level section headings (e.g., "System Considerations", "Processing Specifications", "Security Considerations") frequently begin with introductory or lead-in framing paragraphs, with detailed specifications following in subsequent subsections or chunks.
  * NEVER flag a section as empty, unpopulated, or missing content if it contains introductory or lead-in framing text whose detailed specifications are elaborated in its succeeding subsections or elsewhere in the document.
  * Always check the document index and sibling subsections before declaring any specifications missing.
- If evaluating the Estimates section: confirm it includes time estimates for all 6 required phases (Technical Specifications, Requirements Definition, Implementation, Coding & Unit Testing, System Testing, UAT). Flag any phase missing from this section.
- SONAR SCAN RESULTS AUDITING:
  * When evaluating the Sonar Scan Results section: verify that a Quality Gate is specified.
  * Check that the scan results PASS the specified Quality Gate overall. If Quality Gate Overall is "FAIL" (or fails to meet the target), flag this as non-compliant.
  * Confirm that the scan contains NO specified critical issues (Critical Issues target = 0). If any critical issues are present (e.g., 2 critical issues), flag this as a critical violation of company standards.
- Do NOT flag whole missing sections or whole missing diagrams—global document inventory is audited in Pass 2.

6. EXTERNAL REFERENCES, DELEGATED CONTENT & EXTERNAL FACT GROUNDING:
- Do NOT flag details or requirements as missing if the document explicitly delegates or references them to an external companion document (e.g., Solutions Document, Requirements Document / System Requirements Specification, external API specification, or third-party contract listed in Reference Documents).
- It is standard and expected for technical design documents to omit details that are formally specified in referenced companion documents.
- MANDATORY EXTERNAL FACT GROUNDING & REFERENCES:
  * Whenever citing or referencing an external fact, classification, industry standard, government/regulatory directive, CVE, or external document (such as SIC being superseded by PSIC, ISO standards, NIST, regulatory circulars, or companion document specifications):
    - You MUST NOT rely on your own memory, even if you were trained on that data.
    - You MUST use `web_search` to verify the external fact or document and retrieve the official source/URL.
    - Adding the reference URL(s) to "web_references" is MANDATORY whenever referencing any external fact, standard, directive, or document.

7. VISUAL DIAGRAM QUALITY & DRAFTING NORMS:
- Figures referenced as external attachments or links are assumed compliant and not opened (per Attachment Policy).
- Embedded diagram images in the document MUST be scrutinized across four criteria:
  * Correctness: Accurate data/control flows, valid technical relationships, and explicit security/trust boundaries answering "is the technical design secure enough to produce a secure-by-design program once deployed?"
  * Appropriateness: Matches the defined project and section text with sufficient specification to initiate development.
  * Clarity: Legible labels, clear directionality, clean layout.
  * Drafting Norms: Flowcharts and sequence diagrams MUST follow standard architectural drafting conventions: use orthogonal routing (flag curved lines or splines) and standard symbols (rectangles for processes, diamonds for decisions).
- For diagram findings: specify figure_id, localized sub_bbox ([x1, y1, x2, y2] in 0-1000 scale, or [[x1, y1, x2, y2], ...] if multiple highlights), and element_type ("diagram_node", "diagram_edge", or "caption").

8. PROVENANCE & FRONTEND ANCHORING:
- MANDATORY FRONTEND ANCHORING: Never leave element_id null. When flagging a missing item or gap, anchor it to the relevant section_heading or parent paragraph ID so the UI can render a visible, clickable highlight on the PDF canvas.
- In "title": Provide a concise, plain-English summary. Do NOT include "[Company Standard: '...']" in the title.
- In "standard_ref": Quote the exact text of the requirement from the checklist above, or cite the relevant category ('Security Standards & Risk', 'Writing Quality', 'Content Correctness & Appropriateness').
- In "finding": Clearly explain the violation, risk, or specification gap and how it impacts development readiness or security posture.
- "web_references": MUST contain valid HTTP/HTTPS URLs returned by web_search whenever citing an external fact, standard, directive, CVE, or document. Leave as [] only when the finding is strictly internal to the document.
- Boundary awareness: Do not flag content as truncated or missing simply because it continues across chunk, page, or table boundaries, or because long cell text is wrapped or fragmented across lines within a table.
- If multiple local violations exist in this section, invoke add_local_finding for each violation. If no violations exist, take no action.

9. JSON ARRAY FORMAT & MANDATORY RECOMMENDATIONS:
- "recommendations": MANDATORY native JSON array of strings like ["item1", "item2"]. Every finding MUST contain at least one concrete, actionable recommendation that helps the author resolve the issue before InfoSec review. NEVER pass an empty array [] or omit recommendations.
- "web_references": Native JSON array of URL strings. Mandatory whenever referencing any external fact, standard, directive, or document. If no external facts are cited, pass [].

10. SEVERITY & CONFIDENCE SCORING RUBRIC:
- SEVERITY TIERS:
  * "major": Findings that will most likely halt approval from the Information Security Department and should be resolved before approval. Violations that compromise core architectural integrity, security posture, or hard security standards (e.g., Sonar Quality Gate FAIL, critical scan issues, end-of-life/deprecated runtime or framework, missing essential security controls/considerations, or critical compliance gaps).
  * "minor": Findings that will most likely hinder development, but might still be approved by Information Security; should be resolved before development. Deficiencies such as missing technical specifications or estimates needed to initiate development, unpopulated required technical parameters, secondary compliance gaps, or ambiguities that would impede engineering implementation.
  * "observation": Findings that will not affect approval nor development, but will help improve the quality of the document. Advisory notes, best practice suggestions, stylistic inconsistencies, formatting discrepancies, or minor documentation drafting notes (e.g., non-orthogonal curved lines in flowcharts, missing standard visual diagram symbols).
- CONFIDENCE SCORING:
  Score confidence using calibrated discrete levels based on evidence firmness:
  * 1.0 (Deterministic / Direct Factual Evidence): Factual, verifiable gap directly observed in text or structure (e.g. Sonar Quality Gate explicitly FAILED, critical issues count > 0, an explicit required phase missing from the Estimates table, missing table header).
  * 0.8 (Semantic / Visual Evidence): Explicit textual or visual evidence requiring semantic understanding (e.g. placeholder like "TBD", "???", "TODO" in an architecture diagram or specification field; software version confirmed deprecated via web search).
  * 0.6 (Contextual / Inferred Evidence): Contextual deduction where evidence is indirect, phrasing is ambiguous, or companion document delegation is possible but unverified.
  * DISCARD SPECULATIVE FINDINGS (< 0.6): Do NOT create findings with confidence below 0.6. If a potential issue is speculative, unevidenced, or likely delegated to a companion document, omit it entirely.
"""


# pass1 system prompt placeholder
PASS1_SYSTEM_PROMPT: Optional[str] = None


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

def merge_findings_tool(state_key: str) -> Tool:
    _tool: Tool = create_tool_from_function(
        function=merge_findings,
        description="Combine multiple same-topic findings into one, aggregating unique fields (element_id, sub_bbox, etc.) into a list, and summarizing their titles and descriptions into a single finding.",
        outputs_to_state={state_key: {"source": "finding"}}
    )
    _tool.warm_up()
    return _tool



def build_evaluation_pipeline(knowledge_repo: Optional[KnowledgeRepository] = None) -> Pipeline:
    # resilient generator with exponential retry and timeout
    generator: OpenRouterChatGenerator = make_resilient_openrouter_generator()

    agent_tools: list[Tool] = _make_tools() + [add_local_finding_tool("findings_list")]

    agent: Agent = Agent(
        chat_generator=generator,
        tools=agent_tools,
        system_prompt=build_pass1_system_prompt(knowledge_repo=knowledge_repo),
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


def build_dedup_system_prompt() -> str:
    return """\
Role: Technical reviewer — finding deduplication, quality gate & contradiction resolution.

CONTEXT & PREEMPTIVE OBJECTIVE
You are performing a quality gate and deduplication review of all local findings recorded in Pass 1 before the document is handed over to the Information Security department. Your objective is to lessen further walkthrough and revision cycles with InfoSec by filtering false positives, merging duplicates, and ensuring findings are high-quality, actionable, and verifiable.

CORE MANDATE & FINDING CATEGORIES
Ensure the accepted findings represent genuine, verifiable discrepancies across four categories:
a) Company standards: Compliance gaps against internal rules and required schemas.
b) Security standards and risk: Evaluating "is the technical design secure enough to produce a secure-by-design program once deployed?"
c) Writing quality: Ambiguities, contradictions, vague specifications, and visual drafting norms.
d) Content correctness and appropriateness: Evaluating "is the technical design specifications enough to initiate development?"
Your review ensures findings help the author achieve higher document quality and a more secure technical design.

INPUT
All Findings: Array of local findings from Pass 1.

TOOLS
- accept_local_finding(finding): Accept a unique, non-duplicate local finding as valid. The `finding` dictionary must match the schema:
  {
    "title": "str",
    "element_id": "str (MUST NOT be null)" or ["str"],
    "figure_id": "str|null",
    "sub_bbox": [x1, y1, x2, y2]|[[x1, y1, x2, y2], ...]|null,
    "element_type": "str",
    "finding": "str",
    "standard_ref": "str",
    "severity": "major|minor|observation",
    "confidence": 1.0|0.8|0.6,
    "recommendations": ["str"],
    "web_references": ["str"]
  }
- merge_findings(findings, title, finding): Combine multiple same-topic duplicate findings into one single finding.
  * `findings`: Array of the duplicate finding objects (from the input findings list) that describe the exact same issue on the exact same object.
  * `title`: A single concise, summarized title for the merged finding.
  * `finding`: A single synthesized description summarizing the noncompliant portions into one coherent finding.
  The tool automatically aggregates unique fields (element_id into a list, sub_bbox into a list of highlights, web_references, recommendations) and selects the highest severity (major > minor > observation) and confidence (max score).
- flag_contradiction(finding_a_title, finding_b_title, description): Flag two findings that contradict each other across sections.

TASKS
1. Review all input findings from Pass 1.
2. Deduplicate and merge same-topic findings:
   - STRICT SIMILARITY DEFINITION:
     All findings to be merged MUST talk about the EXACT SAME OBJECT (e.g. the exact same diagram / figure_id, or the exact same paragraph / element_id) with the EXACT SAME ISSUE / TOPIC.
     * DISSIMILAR (DO NOT MERGE): If a finding talks about a deprecated GitHub Actions version and another talks about a deprecated Kubernetes version, they are DIFFERENT — keep them separate and call accept_local_finding for each.
     * SAME ISSUE & SAME OBJECT (MERGE): If two findings talk about a single diagram being incomplete (e.g. finding A points out a "TBD" in the diagram while finding B points out a "???" field), they are the SAME finding. Merge them by calling `merge_findings(findings=[finding_A, finding_B], title="...", finding="...")` so that multiple sub_bbox highlights mark each noncompliant portion in the merged finding.
   - If multiple findings describe the exact same issue across different sections or elements, merge them using merge_findings if they target the same underlying object/topic.
3. Discard false positives, low-confidence findings, situationally inapplicable rules, and non-technical findings:
   - Discard any finding with confidence < 0.6, speculative gaps, or findings where compliance is delegated to an external companion document.
   - Discard findings that rigidly enforced situationally inapplicable rules (e.g., flagging a Third-Party Contract requirement on specifications for internal tooling, or flagging technology-specific requirements that do not apply to the project's actual tech stack).
   - Discard findings flagging empty table cells or placeholders ("N/A", "None", "---") where the cell genuinely has no content or where emptiness is a sensible alternative for that record.
   - Discard findings claiming that figures or content referenced as external file attachments or external links are non-compliant, uninspected, or missing details (content referenced via attachments or links is assumed to be perfectly compliant).
   - Discard any finding that targets purely administrative or managerial content (such as Version History, Approver blocks, or Document Control tables).
   - Discard any finding claiming that the "Format" column in Attachments tables is empty when it is annotated with `[Embedded Icon]` or visually displays format badges/icons (e.g. Word, Excel icons).
   - Discard any finding claiming a parent section (such as "System Considerations" or "Processing Specifications") is empty or missing content when it provides introductory lead-in framing for succeeding subsections.
   - Discard any finding claiming that a continuation table (such as the Look-Up Files continuation table on page 13) is empty, missing headers, or an unpopulated second table when it continues the previous page's table.
   - Discard any finding claiming that a populated table specification, parameter, or cell entry is incomplete, malformed, or missing information when the issue arises from table parser line-wrapping, hyphen-splitting, or margin clipping of long cell text, rather than a genuine author omission or placeholder.
   - Discard any finding claiming a violation based on corporate page-control footers, document classification markings, or page numbering metadata.
4. If two findings contradict each other, call flag_contradiction.
5. For each unique, valid finding without duplicates, call accept_local_finding with the original fields preserved, ensuring severity is calibrated according to:
   * "major": findings that will most likely halt approval from the Information Security Department; should be resolved before approval.
   * "minor": findings that will most likely hinder development, but might still be approved; should be resolved before development.
   * "observation": findings that will not affect approval nor development, but will help improve the quality of the document.
   Ensure confidence is calibrated (1.0, 0.8, or 0.6). For groups of duplicate same-topic findings, call merge_findings.
   Ensure that every accepted finding provides actionable, quality recommendations and verifiable references that will facilitate InfoSec walkthroughs.

CONSTRAINTS
- You MUST call accept_local_finding for every unique, non-duplicate finding, or merge_findings for groups of duplicate same-topic findings. This is the only way findings are recorded.
- Preserve ALL original fields exactly as given when accepting valid findings.
- Do NOT accept duplicate findings individually.
- "recommendations" and "web_references" MUST be native JSON arrays of strings. "recommendations" is MANDATORY and must contain at least one concrete, actionable recommendation.
- After processing all findings, output a brief text summary of what you did.
"""


def build_global_audit_system_prompt(knowledge_repo: Optional[KnowledgeRepository] = None) -> str:
    global_rules = _load_standards_as_list("global_rules.json")

    # load and append user asserted global rules
    user_rules = _load_user_asserted_rules(knowledge_repo, rule_nature="global")
    if user_rules:
        user_rules_str = "\n".join(f"- {r}" for r in user_rules)
        if global_rules and global_rules != "No specific rules configured.":
            global_rules = f"{global_rules}\n{user_rules_str}"
        else:
            global_rules = user_rules_str

    if ASSUME_EXTERNAL_ATTACHMENTS_COMPLIANT:
        attachment_clause = (
            "- ATTACHMENTS & EXTERNAL LINKS (ASSUME COMPLIANT):\n"
            "  * If required sections, diagrams, or documents are referenced as file attachments or external links, assume that the content within said attachments or links is perfectly compliant and satisfies the requirement. Do NOT open or inspect said attachments or links."
        )
    else:
        attachment_clause = (
            "- ATTACHMENTS & EXTERNAL LINKS AUDITING:\n"
            "  * Verify that all external attachments and links are present and accessible, scrutinizing them for compliance."
        )

    return f"""\
Role: Technical reviewer — document-level compliance auditor.

CONTEXT & PREEMPTIVE OBJECTIVE
You are performing a document-level compliance audit on the full document structure before it is handed over to the Information Security department.
Your review is a preemptive step designed to lessen further walkthrough and revision cycles with InfoSec.

CORE MANDATE & GUIDING QUESTIONS
Your ultimate job is to determine if the document contains adequate, correct information to start development. Alongside completeness and correctness, you MUST focus on answering two central questions:
1. "Is the technical design secure enough to produce a secure-by-design program once deployed?"
2. "Is the technical design specifications enough to initiate development?"
You have been provided with the `web_search` tool to use the internet as an active knowledge base to ensure these questions are answered authoritatively when assessing technology choices, architectural patterns, and industry standards.
The findings should help the user/author achieve higher document quality and a more secure technical design if it isn't already.

FOUR CATEGORIES OF FINDINGS TO RECORD
Record discrepancies according to four explicit categories:
a) Company Standards: Global checklist omissions (missing required sections, mandatory diagrams, reference documents, or tables).
b) Security Standards and Risk: System-wide security deficiencies, missing security considerations, inadequate technology stack specifications, unaddressed trust boundaries, or designs that fail to be secure-by-design.
c) Writing Quality: Inconsistencies across document structure, unclear architectural relationships, or structural omissions.
d) Content Correctness and Appropriateness: Missing or inappropriate specifications required to initiate development.

MANDATORY GLOBAL STANDARDS CHECKLIST:
{global_rules}

INPUT
1. Document Index: Full inventory of sections, tables, figures, and page gaps across the PDF.
2. Accepted Finding Titles: Summary of findings already recorded in Pass 1 (for context only — do NOT re-record these).

TOOLS
- query_other_section(section_title): Retrieve content of another section by its title.
- web_search(query): Search the web using the internet as a security knowledge base to verify external standards, regulations, CVEs, or technology-specific requirements.
- accept_local_finding(finding): Record a NEW document-level finding. The `finding` dictionary must match the schema:
  {{
    "title": "str (clean, concise summary, e.g. 'Missing Section: Sonar Scan Result')",
    "element_id": "str (MUST NOT be null; anchor to existing section ID from document index)",
    "figure_id": "str|null",
    "sub_bbox": [x1, y1, x2, y2]|null,
    "element_type": "str",
    "finding": "str (detailed description of the compliance gap or security risk)",
    "standard_ref": "str (exact quoted standard text from global checklist, or relevant category name like 'Security Standards & Risk', 'Writing Quality', 'Content Correctness & Appropriateness')",
    "severity": "major|minor|observation",
    "confidence": 1.0|0.8|0.6,
    "recommendations": ["Actionable remediation step 1"] (MANDATORY: must contain at least one concrete remediation step that will facilitate InfoSec approval),
    "web_references": ["https://example.com/reference-url"] (MANDATORY if referencing external facts/standards; else [])
  }}

AUDIT RULES & TASKS

TASK 1: GLOBAL STANDARDS CHECKLIST & SITUATIONAL APPLICABILITY AUDIT
Audit the document index against the mandatory global checklist above, applying situational reasoning:
- SITUATIONAL STANDARDS & SENSIBLE DECISIONS:
  * Some standards are situational. Determine whether a standard applies by referencing it against the document's content, purpose, and technology context.
  * Use your capability to make justifiable and sensible decisions on which rules to apply and which to ignore depending on the situation.
  * For example: specifications for internal tooling do NOT need a Third-Party Contract; standards contingent on specific technologies (such as TDE for Azure SQL) only apply if those technologies are specified. Do not restrict yourself to those examples; apply sensible situational reasoning across all checklist items based on project context.
  * If a standard is genuinely not applicable to the system described in the document, do NOT flag it as missing.

{attachment_clause}

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
   - Check `document_index.get("reference_documents", [])` as well as Reference Documents / References in `document_index["sections"]` and the accepted finding titles.
   - Recognize that standard industry titles satisfy the "Requirements Document" requirement:
     * "System Requirements Specification" (SRS), "Software Requirements Specification", "Business Requirements Document" (BRD), or "Requirements Specification" ALL satisfy the Requirements Document standard. Do NOT flag the Requirements Document as missing if any of these appear in `document_index["reference_documents"]`, in section headings, or in accepted finding titles.
     * "Solutions Document", "Solutions Architecture Document", or "Solution Design" satisfies the Solutions Document standard. Do NOT flag the Solutions Document as missing if any of these appear in `document_index["reference_documents"]`, in section headings, or in accepted finding titles.

3. Required Diagrams:
   - Verify the document contains all mandatory diagram types (inspect `document_index["figures"]` captions, sections, and accepted finding titles):
     1. Data Flow Diagram, 2. Network Diagram, 3. Sequence Diagram, 4. Process Flow Diagram.
   - If a diagram is referenced as an external attachment or link, assume it is compliant and present (per Attachment Policy).

4. Required Tables (Reports Table):
   - Check `document_index["tables"]`: if any table has `"section"` indicating "Reports" (e.g. section title contains "Reports"), or if accepted findings reference a table under the Reports section, the Reports table exists. Only flag missing if no table exists under the Reports section.

5. Third-Party Contract:
   - Verify reference to third-party contract IF APPLICABLE. Internal tooling and projects without third-party vendor integrations do NOT require a third-party contract. Only flag as missing if the document clearly involves third-party services, vendors, or external contractor systems and lacks a contract reference.

TASK 2: EXTERNAL REFERENCES & DELEGATED CONTENT
- Do NOT flag details as missing if the document index indicates they are covered in companion documents listed under Reference Documents.

RECORDING GLOBAL OMISSIONS (FRONTEND SAFE):
- For any missing section, diagram, table, or reference document that is genuinely required: call accept_local_finding.
- MANDATORY ANCHORING: Never leave element_id null. Anchor the missing finding to the closest related section ID in document_index (e.g. anchor missing diagrams to Section E / Diagrams, or anchor a missing top-level section to Section A / Overview or the preceding section).
- In "title": Provide a clean, concise title (e.g. 'Missing Section: Sonar Scan Result'). Do NOT wrap in "[Company Standard: '...']".
- In "standard_ref": Quote the exact requirement from the global checklist above, or cite the relevant category.
- In "finding": Document the non-compliance clearly: "<exact requirement> is missing: <details>."
- Set severity according to the impact rubric:
  * "major": For omissions that will most likely halt approval from the Information Security Department (e.g., missing Security Considerations, Sonar Scan Result, or missing required architectural/security diagrams like DFD/Network/Sequence/Process Flow, or missing Reports tables); should be resolved before approval.
  * "minor": For omissions that will most likely hinder development, but might still be approved (e.g., missing reference documents, optional companion contracts, or secondary technical specifications); should be resolved before development.
  * "observation": For findings that will not affect approval nor development, but help improve the quality of the document.
- Set confidence to 1.0 (deterministic structural absence directly verified against the complete document index). Provide actionable remediation in "recommendations".

CONSTRAINTS
- Only record NEW document-level findings. Do NOT re-record findings from the accepted list.
- "recommendations" and "web_references" MUST be native JSON arrays of strings. "recommendations" is MANDATORY and must contain at least one concrete remediation step for drafting or incorporating the missing item that will facilitate InfoSec approval. If no external facts or documents are cited, pass [] for "web_references".
- After processing, output a brief text summary of what you did.
"""


def _make_generator() -> OpenRouterChatGenerator:
    # resilient generator with exponential retry and timeout
    return make_resilient_openrouter_generator()


def build_dedup_pipeline() -> Pipeline:
    """Pipeline for TASK 1: deduplication & contradiction resolution.
    Receives only the findings list — no document index needed."""
    from cheshire_configs.preprocessors.multistep.components.dedup_message_builder import DedupMessageBuilder
    from tools.base import flag_contradiction_tool
    from tools.helpers.output_schema import Contradiction

    agent: Agent = Agent(
        chat_generator=_make_generator(),
        tools=[
            accept_local_finding_tool("accepted_findings"),
            merge_findings_tool("accepted_findings"),
            flag_contradiction_tool("contradictions"),
        ],
        system_prompt=build_dedup_system_prompt(),
        max_agent_steps=200,
        exit_conditions=["text"],
        state_schema={
            "accepted_findings": {"type": list[LocalFinding]},
            "contradictions": {"type": list[Contradiction]},
        }
    )

    pipeline: Pipeline = Pipeline()
    pipeline.add_component("dedup_message_builder", DedupMessageBuilder())
    pipeline.add_component("agent", agent)

    pipeline.connect("dedup_message_builder.messages", "agent.messages")

    return pipeline


def build_global_audit_pipeline(knowledge_repo: Optional[KnowledgeRepository] = None) -> Pipeline:
    """Pipeline for TASK 2: global standards checklist audit.
    Receives the document index + compact accepted-findings summary
    in a fresh context with no prior tool-call history."""
    from cheshire_configs.preprocessors.multistep.components.global_audit_message_builder import GlobalAuditMessageBuilder

    agent: Agent = Agent(
        chat_generator=_make_generator(),
        tools=[
            accept_local_finding_tool("audit_findings"),
            cast(Tool, web_search),
        ],
        system_prompt=build_global_audit_system_prompt(knowledge_repo=knowledge_repo),
        max_agent_steps=30,
        exit_conditions=["text"],
        state_schema={
            "audit_findings": {"type": list[LocalFinding]},
        }
    )

    pipeline: Pipeline = Pipeline()
    pipeline.add_component("global_audit_message_builder", GlobalAuditMessageBuilder())
    pipeline.add_component("agent", agent)

    pipeline.connect("global_audit_message_builder.messages", "agent.messages")

    return pipeline
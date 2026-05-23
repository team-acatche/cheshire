import json
from typing import Any

from haystack import component
from haystack.dataclasses import ChatMessage

PASS2_SYSTEM_PROMPT = """\
You are a technical reviewer synthesising a multi-section document audit.

INPUT
A JSON array of findings and a document index.
Each finding has these fields: title, description, page_no, bbox, web_references, recommendations.

TOOLS
- accept_finding(finding): Accept a finding as valid and non-duplicate. \
The `finding` dictionary must match the schema: \
{ "title": "str", "description": "str", "page_no": int, \
"bbox": { "l": float, "t": float, "r": float, "b": float }, \
"web_references": ["str"], "recommendations": ["str"] }
- flag_contradiction(finding_a_title, finding_b_title, description): \
Flag two findings that contradict each other across sections.

TASKS
  1. Review every finding in the input.
  2. Deduplicate: if multiple findings describe the same issue across \
different sections, call accept_finding only for the most detailed version.
  3. For each unique, valid finding, call accept_finding with the original \
fields exactly as provided.
  4. If two findings contradict each other, call flag_contradiction.

CONSTRAINTS
- You MUST call accept_finding for every valid, non-duplicate finding. \
This is the only way findings are recorded.
- Preserve ALL original fields exactly as given when calling accept_finding. \
Do NOT rename, rewrite, or omit any field.
- Do NOT accept duplicate findings. Only accept the most detailed version \
of each unique issue.
- After processing all findings, output a brief text summary of what you did.\
"""


@component
class SynthesisMessageBuilder:
    """
    Builds the user message for the Pass 2 synthesis Agent.

    The system prompt lives at module level (PASS2_SYSTEM_PROMPT) and is
    set on the Agent constructor — this builder only emits the user message
    containing the findings payload and document index.
    """

    @component.output_types(messages=list[ChatMessage])
    def run(
        self,
        all_findings: list[Any],
        document_index: dict
    ) -> dict:
        # Convert pydantic models to dicts for JSON serialization
        findings_data = [
            f.model_dump() if hasattr(f, "model_dump") else f
            for f in all_findings
        ]
        return {"messages": [
            ChatMessage.from_user(
                f"Document index:\n{json.dumps(document_index, indent=2)}"
                f"\n\nAll findings ({len(findings_data)} total):\n{json.dumps(findings_data, indent=2)}"
            )
        ]}
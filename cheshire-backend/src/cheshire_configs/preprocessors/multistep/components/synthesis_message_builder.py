import json
from typing import Any

from haystack import component
from haystack.dataclasses import ChatMessage

PASS2_SYSTEM_PROMPT = """\
You are a technical reviewer synthesising a multi-section document audit.

INPUT
A JSON array of findings and a document index.
Each finding has these fields: title, description, page_no, bbox, web_references, recommendations.

TASKS
  1. Deduplicate findings that describe the same issue across different sections. Keep the most detailed version of each.
  2. Identify cross-section contradictions.

OUTPUT  Return ONLY a valid JSON object:
{
  "findings": [
    {"title": "str", "description": "str", "page_no": int, "bbox": {"l": float, "t": float, "r": float, "b": float}, "web_references": ["str"], "recommendations": ["str"]}
  ],
  "contradictions": [
    {"section_a": "str", "section_b": "str", "description": "str"}
  ]
}

CONSTRAINTS
- Preserve ALL original fields for each finding exactly as given: title, description, page_no, bbox, web_references, recommendations.
- Do NOT rename, remove, or add fields to findings.
- Only remove true duplicates (same underlying issue found in multiple sections). When uncertain, keep both.
- Output MUST be valid JSON. No markdown fences, no commentary outside the JSON object.\
"""


@component
class SynthesisMessageBuilder:
    """
    Builds the two-message conversation for Pass 2:
    a system message carrying the task definition, and a user message
    carrying the findings payload and document index.

    Keeping the system prompt here rather than in the generator constructor
    mirrors the pattern used in Pass 1 and means all prompt logic lives
    in message builder components, not scattered across pipeline config.
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
        messages = [
            ChatMessage.from_system(PASS2_SYSTEM_PROMPT),
            ChatMessage.from_user(
                f"Document index:\n{json.dumps(document_index, indent=2)}"
                f"\n\nAll findings:\n{json.dumps(findings_data, indent=2)}"
            )
        ]
        return {"messages": messages}
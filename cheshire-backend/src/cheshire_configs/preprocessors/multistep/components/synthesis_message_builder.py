import json
from typing import Any

from haystack import component
from haystack.dataclasses import ChatMessage


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
        findings_data: list[dict] = [
            f.model_dump() if hasattr(f, "model_dump") else f
            for f in all_findings
        ]
        return {"messages": [
            ChatMessage.from_user(
                f"Document index:\n{json.dumps(document_index, indent=2)}"
                f"\n\nAll findings ({len(findings_data)} total):\n{json.dumps(findings_data, indent=2)}"
            )
        ]}
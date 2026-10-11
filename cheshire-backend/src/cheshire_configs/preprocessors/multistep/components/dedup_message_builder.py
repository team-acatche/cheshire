import json
from typing import Any

from haystack import component
from haystack.dataclasses import ChatMessage


@component
class DedupMessageBuilder:
    """
    Builds the user message for the dedup Agent (Pass 2a).

    Sends only the findings list — no document index — to keep
    the initial context small and leave room for tool-call history.
    """

    @component.output_types(messages=list[ChatMessage])
    def run(
        self,
        all_findings: list[Any],
    ) -> dict:
        # Convert pydantic models to dicts for JSON serialization
        findings_data: list[dict] = [
            f.model_dump() if hasattr(f, "model_dump") else f
            for f in all_findings
        ]
        return {"messages": [
            ChatMessage.from_user(
                f"All findings ({len(findings_data)} total):\n{json.dumps(findings_data, indent=2)}"
            )
        ]}

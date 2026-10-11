import json
from typing import Any

from haystack import component
from haystack.dataclasses import ChatMessage

from cheshire_configs.preprocessors.multistep.helpers import LocalFinding


@component
class GlobalAuditMessageBuilder:
    """
    Builds the user message for the global audit Agent (Pass 2b).

    Sends the full document index and a compact summary of accepted
    finding titles from deduplication — NOT the full finding details.
    This keeps the context small so the model can focus on the
    document-level checklist audit.
    """

    @component.output_types(messages=list[ChatMessage])
    def run(
        self,
        document_index: dict,
        accepted_findings: list[Any]
    ) -> dict:
        # Build a compact summary: just titles + element types
        finding_titles: list[str] = []
        for f in accepted_findings:
            title: str | None = (
                getattr(f, "title", None)
                or (f.get("title") if isinstance(f, dict) else None)
            )
            if title:
                finding_titles.append(title)
            else:
                # Fallback: truncate the finding description
                desc: str = (
                    getattr(f, "finding", None)
                    or (f.get("finding") if isinstance(f, dict) else None)
                    or ""
                )
                finding_titles.append(desc[:80] + "..." if len(desc) > 80 else desc)

        return {"messages": [
            ChatMessage.from_user(
                f"Document index:\n{json.dumps(document_index, indent=2)}"
                f"\n\nAccepted finding titles from deduplication ({len(finding_titles)} total):\n"
                + "\n".join(f"- {t}" for t in finding_titles)
            )
        ]}

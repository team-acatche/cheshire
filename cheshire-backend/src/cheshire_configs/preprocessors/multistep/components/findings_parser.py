from haystack import component
from haystack.dataclasses import ChatMessage
import json


@component
class FindingsParser:
    """
    Parses the Agent's final text response into a list of finding dicts.
    Attaches chunk provenance to each finding.
    Falls back gracefully on JSON parse failure.
    """

    @component.output_types(findings=list)  # List[dict]
    def run(
        self,
        last_message: ChatMessage,
        chunk_id: str,
        chunk_heading: str
    ) -> dict:

        raw = (last_message.text or "[]").strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        try:
            findings: list[dict] = json.loads(raw)
        except json.JSONDecodeError:
            findings = [{
                "error": "parse_failed",
                "raw": raw,
                "chunk_id": chunk_id,
                "chunk_heading": chunk_heading
            }]
            return {"findings": findings}

        # Attach chunk provenance
        for finding in findings:
            finding["chunk_id"] = chunk_id
            finding["chunk_heading"] = chunk_heading

        return {"findings": findings}
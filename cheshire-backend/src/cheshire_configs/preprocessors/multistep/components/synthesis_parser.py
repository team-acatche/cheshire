import json
import logging
from haystack import component
from haystack.dataclasses import ChatMessage
from docling_core.types.doc import BoundingBox

from tools.helpers.output_schema import VulnerabilityDetails

logger = logging.getLogger("uvicorn.error")


@component
class SynthesisParser:
    @component.output_types(vulnerabilities=list)  # List[VulnerabilityDetails]
    def run(self, replies: list) -> dict:  # replies: List[ChatMessage]
        raw = (replies[0].text or "[]").strip()

        logger.debug(f"Synthesis raw response (first 500 chars): {raw[:500]}")

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                items: list[dict] = parsed.get("findings", [])
            elif isinstance(parsed, list):
                items: list[dict] = parsed
            else:
                items = []
        except json.JSONDecodeError:
            logger.warning(
                "Synthesis response is not valid JSON — "
                "findings will be passed through without LLM synthesis."
            )
            return {"vulnerabilities": []}

        vulnerabilities: list[VulnerabilityDetails] = []
        for item in items:
            try:
                bbox_data = item.get("bbox") or {}
                vulnerabilities.append(
                    VulnerabilityDetails(
                        title=item.get("title", item.get("finding", "")),
                        description=item.get("description", item.get("finding", "")),
                        page_no=item.get("page_no", 0),
                        bbox=BoundingBox(
                            l=bbox_data.get("l", bbox_data.get("x1", 0)),
                            t=bbox_data.get("t", bbox_data.get("y1", 0)),
                            r=bbox_data.get("r", bbox_data.get("x2", 0)),
                            b=bbox_data.get("b", bbox_data.get("y2", 0))
                        ),
                        web_references=item.get("web_references", []),
                        recommendations=item.get("recommendations", [])
                    )
                )
            except Exception as e:
                logger.warning(f"Skipping unparseable synthesis finding: {e}")
                continue

        return {"vulnerabilities": vulnerabilities}
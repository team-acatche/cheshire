from docling_core.types.doc import BoundingBox
from haystack import component
from haystack.dataclasses import ChatMessage
import json

from cheshire.tools.helpers.output_schema import VulnerabilityDetails
from cheshire_configs.preprocessors.multistep.helpers import EvaluationChunk


@component
class FindingsParser:
    """
    Parses the Agent's JSON output into validated VulnerabilityDetails objects.

    Resolves page_no and bbox in two cases:
      - Text element: reads page_no from the model output (sourced from the
        [ID:...|p<n>] tag), resolves bbox from the ElementRef lookup.
      - Figure element: reads page_no from the FigureRef, computes absolute
        page bbox by offsetting sub_bbox by the figure's page-level bbox.
        If sub_bbox is null, the figure's full bbox is used.

    Entries that fail validation are silently dropped rather than surfaced
    as errors — a missing bbox or unresolvable element_id produces no output
    for that entry, which is preferable to a malformed VulnerabilityDetails.
    """

    @component.output_types(vulnerabilities=list)  # List[VulnerabilityDetails]
    def run(
        self,
        last_message: ChatMessage,
        chunk: EvaluationChunk
    ) -> dict:
        element_by_id = {e.element_id: e for e in chunk.element_refs}
        figure_by_id = {f.figure_id: f for f in chunk.figures}

        raw = (last_message.text or "[]").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        try:
            items: list[dict] = json.loads(raw)
        except json.JSONDecodeError:
            return {"vulnerabilities": []}

        vulnerabilities: list[VulnerabilityDetails] = []

        for item in items:
            element_id: str | None = item.get("element_id")
            figure_id: str | None = item.get("figure_id")
            sub_bbox: list[int] | None = item.get("sub_bbox")
            page_no: int = item.get("page_no", 0)
            bbox = BoundingBox(l=0, t=0, r=0, b=0)

            if figure_id and figure_id in figure_by_id:
                fig = figure_by_id[figure_id]
                page_no = fig.page_number
                fx1, fy1, fx2, fy2 = fig.bbox_image_px

                if sub_bbox and len(sub_bbox) == 4:
                    sx1, sy1, sx2, sy2 = sub_bbox
                    bbox = BoundingBox(
                        l=fx1 + sx1,
                        t=fy1 + sy1,
                        r=fx1 + sx2,
                        b=fy1 + sy2
                    )
                else:
                    bbox = BoundingBox(l=fx1, t=fy1, r=fx2, b=fy2)

            elif element_id and element_id in element_by_id:
                elem = element_by_id[element_id]
                x1, y1, x2, y2 = elem.bbox_image_px
                bbox = BoundingBox(l=x1, t=y1, r=x2, b=y2)

            try:
                vulnerabilities.append(
                    VulnerabilityDetails(
                        title=item["title"],
                        description=item["description"],
                        page_no=page_no,
                        bbox=bbox,
                        web_references=item.get("web_references", []),
                        recommendations=item.get("recommendations", [])
                    )
                )
            except Exception:
                continue

        return {"vulnerabilities": vulnerabilities}

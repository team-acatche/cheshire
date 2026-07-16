from docling_core.types.doc import BoundingBox
from haystack import component
from haystack.dataclasses import ChatMessage
import json

from tools.helpers.output_schema import VulnerabilityDetails
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
        element_by_id: dict[str, ElementRef] = {e.element_id: e for e in chunk.element_refs}
        figure_by_id: dict[str, FigureRef] = {f.figure_id: f for f in chunk.figures}

        raw: str = (last_message.text or "[]").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        try:
            # to be validated before conversion later (@ lines 57-100)
            items: Any = json.loads(raw)
        except json.JSONDecodeError:
            return {"vulnerabilities": []}

        if isinstance(items, dict):
            items = [items]
        elif not isinstance(items, list):
            return {"vulnerabilities": []}

        vulnerabilities: list[VulnerabilityDetails] = []

        for item in items:
            item: Any
            if not isinstance(item, dict):
                continue
            element_id: str | None = item.get("element_id")
            figure_id: str | None = item.get("figure_id")
            sub_bbox: list[float] | None = item.get("sub_bbox")
            page_no: int = item.get("page_no", 0)
            bbox: BoundingBox = BoundingBox(l=0, t=0, r=0, b=0)

            if figure_id in figure_by_id and figure_id is not None:
                fig = figure_by_id[figure_id]
                page_no = fig.page_number

                if sub_bbox and len(sub_bbox) == 4:
                    sx1, sy1, sx2, sy2 = sub_bbox
                    max_coord = max(sx1, sy1, sx2, sy2)
                    scale_factor = 1.0 if (0.0 < max_coord <= 1.0) else 1000.0
                    
                    frac_x1 = max(0.0, min(1.0, sx1 / scale_factor))
                    frac_y1 = max(0.0, min(1.0, sy1 / scale_factor))
                    frac_x2 = max(0.0, min(1.0, sx2 / scale_factor))
                    frac_y2 = max(0.0, min(1.0, sy2 / scale_factor))
                    
                    fig_w = fig.bbox_pdf.r - fig.bbox_pdf.l
                    fig_h = fig.bbox_pdf.t - fig.bbox_pdf.b
                    
                    bbox = BoundingBox(
                        l=fig.bbox_pdf.l + frac_x1 * fig_w,
                        t=fig.bbox_pdf.t - frac_y1 * fig_h,
                        r=fig.bbox_pdf.l + frac_x2 * fig_w,
                        b=fig.bbox_pdf.t - frac_y2 * fig_h
                    )
                else:
                    bbox = fig.bbox_pdf

            elif element_id in element_by_id is not None:
                elem = element_by_id[element_id]
                bbox = elem.bbox_pdf

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

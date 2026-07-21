import json
from typing import Any

from docling_core.types.doc import BoundingBox
from haystack import component
from haystack.dataclasses import ChatMessage

from tools.helpers.output_schema import VulnerabilityDetails
from cheshire_configs.preprocessors.multistep.helpers import EvaluationChunk, ElementRef, FigureRef

def clamp(min_val: float, value: float, max_val: float) -> float:
    """
    Clamps a value to the range [min_val, max_val].

    Args:
        min_val: The minimum value of the range.
        value: The value to clamp.
        max_val: The maximum value of the range.

    Returns:
        The clamped value.
    """
    return max(min_val, min(value, max_val))

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

        # extract raw findings JSON from code block
        raw: str = (last_message.text or "[]").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        # validate schema before deseralizing later @ lines 57-100
        try:
            findings: Any = json.loads(raw)
        except json.JSONDecodeError:
            return {"vulnerabilities": []}

        # convert single-item dict to list
        if isinstance(findings, dict):
            findings = [findings]
        elif not isinstance(findings, list):
            return {"vulnerabilities": []}

        vulnerabilities: list[VulnerabilityDetails] = []

        for finding in findings:
            finding: Any
            if not isinstance(finding, dict):
                continue
            element_id: str | None = finding.get("element_id")
            figure_id: str | None = finding.get("figure_id")
            sub_bbox: list[float] | None = finding.get("sub_bbox")
            page_no: int = finding.get("page_no", 0)
            bbox: BoundingBox = BoundingBox(l=0, t=0, r=0, b=0)

            if figure_id in figure_by_id and figure_id is not None:
                fig: FigureRef = figure_by_id[figure_id]
                page_no = fig.page_number

                if sub_bbox and len(sub_bbox) == 4:
                    scaled_x1: float
                    scaled_y1: float
                    scaled_x2: float
                    scaled_y2: float
                    scaled_x1, scaled_y1, scaled_x2, scaled_y2 = sub_bbox
                    max_coord: float = max(scaled_x1, scaled_y1, scaled_x2, scaled_y2)
                    scale_factor: float = 1.0 if (0.0 < max_coord <= 1.0) else 1000.0
                    
                    normalized_x1: float = clamp(0.0, scaled_x1 / scale_factor, 1.0)
                    normalized_y1: float = clamp(0.0, scaled_y1 / scale_factor, 1.0)
                    normalized_x2: float = clamp(0.0, scaled_x2 / scale_factor, 1.0)
                    normalized_y2: float = clamp(0.0, scaled_y2 / scale_factor, 1.0)
                    
                    fig_width: float = fig.bbox_pdf.r - fig.bbox_pdf.l
                    fig_height: float = fig.bbox_pdf.t - fig.bbox_pdf.b
                    
                    bbox = BoundingBox(
                        l=fig.bbox_pdf.l + normalized_x1 * fig_width,
                        t=fig.bbox_pdf.t - normalized_y1 * fig_height,
                        r=fig.bbox_pdf.l + normalized_x2 * fig_width,
                        b=fig.bbox_pdf.t - normalized_y2 * fig_height
                    )
                else:
                    bbox = fig.bbox_pdf

            # if finding references an element, 
            elif element_id in element_by_id is not None:
                elem: ElementRef = element_by_id[element_id]
                bbox = elem.bbox_pdf

            try:
                vulnerabilities.append(
                    VulnerabilityDetails(
                        title=finding["title"],
                        description=finding["description"],
                        page_no=page_no,
                        bbox=bbox,
                        web_references=finding.get("web_references", []),
                        recommendations=finding.get("recommendations", [])
                    )
                )
            except Exception:
                continue

        return {"vulnerabilities": vulnerabilities}

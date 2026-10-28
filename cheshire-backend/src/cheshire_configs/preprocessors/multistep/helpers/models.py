"""
Core domain data models and Pydantic schemas for multistep evaluation and preprocessing.
"""

import ast
from dataclasses import dataclass, field
from typing import List, Optional, Union

from docling_core.types.doc import BoundingBox
from pydantic import BaseModel, Field, field_validator


@dataclass(frozen=True, kw_only=True)
class ImageBoundingBox:
    """
    A set of bounding box coordinates meant to represent a subregion within a rendered page.
    Serves as a normalized conversion from Docling's BoundingBox.
    """
    x1: float
    y1: float
    x2: float
    y2: float

    @staticmethod
    def from_docling_bbox(
        bbox: BoundingBox,
        page_height: float,
        scale: float,
    ) -> "ImageBoundingBox":
        """
        Converts a Docling Bounding Box to an ImageBoundingBox.
        """
        return ImageBoundingBox(
            x1=round(bbox.l * scale),
            y1=round((page_height - bbox.t) * scale),
            x2=round(bbox.r * scale),
            y2=round((page_height - bbox.b) * scale),
        )


@dataclass
class ElementRef:
    """
    A text-based document element with its Docling-sourced bbox.
    Coordinates are in rendered page image space (top-left origin, pixels).
    The bbox comes from Docling's PDF parser — it is not model-predicted.
    """
    element_id: str
    label: str
    page_number: int
    bbox_image_px: ImageBoundingBox
    bbox_pdf: BoundingBox
    text_excerpt: str


@dataclass
class FigureRef:
    """
    A picture element with its page-level bbox and cropped image.
    The crop is what gets sent to the model as an image_url part.
    Sub-element bboxes within the crop are model-predicted at inference time.
    """
    figure_id: str
    page_number: int
    bbox_image_px: Union[ImageBoundingBox, list[float]]
    bbox_pdf: BoundingBox
    base64_png: str


class LocalFinding(BaseModel):
    element_id: Optional[List[str]] = Field(None, description="The unique identifier(s) of the vulnerable element(s) (from the structured text ID tags).")
    figure_id: Optional[str] = Field(None, description="The unique identifier of the figure (if the vulnerability is in a figure).")
    sub_bbox: Optional[List[List[float]]] = Field(None, description="Bounding boxes within the figure crop space [[x1, y1, x2, y2], ...] (0-1000 scale).")
    element_type: str = Field(..., description="The type of the element, e.g. section_heading, paragraph, diagram_node, diagram_edge, table_cell, table_header, caption, code_block, list_item.")
    finding: str = Field(..., description="Detailed description of why the element violates the company standard.")
    standard_ref: str = Field("", description="Exact quoted standard text from the checklist.")
    severity: str = Field(..., description="Severity classification (major, minor, observation).")
    confidence: float = Field(..., description="Confidence score (1.0 for deterministic, 0.8 for semantic, 0.6 for inferred/ambiguous).")
    title: Optional[str] = Field(None, description="An optional short, descriptive title for the finding.")
    web_references: Optional[List[str]] = Field(default_factory=list, description="Optional list of web reference URLs.")
    recommendations: Optional[List[str]] = Field(default_factory=list, description="Mandatory list of recommendation strings.")

    @field_validator("severity", mode="before")
    @classmethod
    def coerce_severity(cls, v):
        if not v or not isinstance(v, str):
            return "observation"
        v_clean = v.strip().lower()
        mapping = {
            "critical": "major",
            "high": "major",
            "major": "major",
            "medium": "minor",
            "low": "minor",
            "minor": "minor",
            "observation": "observation",
            "advisory": "observation",
        }
        return mapping.get(v_clean, "observation")

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, v):
        if v is None:
            return 1.0
        try:
            val = float(v)
            return min(1.0, max(0.0, val))
        except (ValueError, TypeError):
            return 1.0

    @field_validator("element_id", mode="before")
    @classmethod
    def coerce_element_id(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = ast.literal_eval(v)
                    if isinstance(parsed, list):
                        return [str(x) for x in parsed if x]
                except Exception:
                    pass
            return [v]
        if isinstance(v, list):
            res = [str(x) for x in v if x is not None and str(x).strip()]
            return res if res else None
        return [str(v)]

    @field_validator("sub_bbox", mode="before")
    @classmethod
    def coerce_sub_bbox(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
            if v.startswith("[") and v.endswith("]"):
                try:
                    v = ast.literal_eval(v)
                except Exception:
                    return None
            else:
                return None
        if isinstance(v, list):
            if not v:
                return None
            if len(v) == 4 and all(isinstance(x, (int, float)) for x in v):
                return [[float(x) for x in v]]
            res = []
            for item in v:
                if isinstance(item, (list, tuple)) and len(item) == 4 and all(isinstance(x, (int, float)) for x in item):
                    res.append([float(x) for x in item])
            return res if res else None
        return None

    @field_validator("recommendations", "web_references", mode="before")
    @classmethod
    def coerce_to_list(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = ast.literal_eval(v)
                    if isinstance(parsed, list):
                        return [str(x) for x in parsed]
                except Exception:
                    pass
            return [v] if v else []
        return v or []


@dataclass
class EvaluationChunk:
    """
    One semantic unit of the document, produced by HierarchicalChunker.
    Carries both structured text (with [ID:...] annotations) and any
    figure crops that are referenced within this section.
    """
    chunk_id: str
    heading: str
    page_range: tuple[int, int]
    structured_text: str  # text for the model
    element_refs: list[ElementRef] = field(default_factory=list)
    figures: list[FigureRef] = field(default_factory=list)

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, model_validator
from docling_core.types.doc import BoundingBox

class PageBoundingBox(BoundingBox):
    page_no: Optional[int] = None

class VulnerabilityDetails(BaseModel):
    title: Annotated[str, Field(description="Title of the proposed vulnerability.")]
    description: Annotated[str, Field(description="Description of the proposed vulnerability.")]
    page_no: Annotated[int, Field(description="Page number of the vulnerable source within the document.")]
    bbox: Annotated[Optional[BoundingBox], Field(default=None, description="Bounding box highlighting the vulnerable source within the document.")] = None
    bboxes: Annotated[list[PageBoundingBox], Field(default_factory=list, description="List of bounding boxes highlighting all noncompliant portions.")]
    web_references: Annotated[list[str], Field(description="List of URL strings of web references for the proposed vulnerability.")]
    recommendations: Annotated[list[str], Field(description="List of recommendations for the proposed vulnerability.")]
    scope: Annotated[Literal["section", "document"], Field(description="'document' when the finding has no location in the PDF.")] = "section"
    severity: Annotated[Optional[Literal["major", "minor", "observation"]], Field(description="Severity tier of the finding.")] = None
    confidence: Annotated[Optional[float], Field(ge=0.0, le=1.0, description="Evidence confidence: 1.0 verified, 0.8 likely, 0.6 inferred.")] = None

    @model_validator(mode="after")
    def sync_bboxes(self):
        if not self.bboxes and self.bbox is not None:
            self.bboxes = [PageBoundingBox(**self.bbox.model_dump(exclude={"page_no"}), page_no=self.page_no)]
        elif self.bboxes and self.bbox is None:
            self.bbox = self.bboxes[0]
        elif self.bbox is None and not self.bboxes:
            self.bbox = BoundingBox(l=0, t=0, r=0, b=0)
            self.bboxes = [PageBoundingBox(l=0, t=0, r=0, b=0, page_no=self.page_no)]
        return self

    def __eq__(self, other) -> bool:
        if not isinstance(other, VulnerabilityDetails):
            return False
        return self.title == other.title and \
            self.description == other.description and \
            self.page_no == other.page_no and \
            self.web_references == other.web_references and \
            self.recommendations == other.recommendations

    def __hash__(self):
        return hash(self.model_dump_json(exclude={"bbox", "bboxes"}))

class Contradiction(BaseModel):
    finding_a_title: Annotated[str, Field(description="Title of the first conflicting finding.")]
    finding_b_title: Annotated[str, Field(description="Title of the second conflicting finding.")]
    description: Annotated[str, Field(description="Description of the contradiction between the two findings.")]
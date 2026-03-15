from enum import Enum, auto
from typing import Annotated

from pydantic import BaseModel, Field
from docling_core.types.doc import BoundingBox

class VulnerabilityDetails(BaseModel):
    title: Annotated[str, Field(description="Title of the proposed vulnerability.")]
    description: Annotated[str, Field(description="Description of the proposed vulnerability.")]
    page_no: Annotated[int, Field(description="Page number of the vulnerable source within the document.")]
    bbox: Annotated[BoundingBox, Field(description="Bounding box highlighting the vulnerable source within the document.")]
    web_references: Annotated[list[str], Field(description="List of URL strings of web references for the proposed vulnerability.")]
    recommendations: Annotated[list[str], Field(description="List of recommendations for the proposed vulnerability.")]

    def __eq__(self, other) -> bool:
        if not isinstance(other, VulnerabilityDetails):
            return False
        return self.title == other.title and \
            self.description == other.description and \
            self.page_no == other.page_no and \
            self.web_references == other.web_references and \
            self.recommendations == other.recommendations

    def __hash__(self):
        return hash(self.model_dump_json(exclude={"bbox"}))
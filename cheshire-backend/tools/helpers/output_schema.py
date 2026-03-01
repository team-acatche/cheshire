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
    
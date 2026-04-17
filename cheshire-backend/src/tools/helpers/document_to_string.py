from haystack.dataclasses import Document
from docling.chunking import DocChunk
from docling_core.types.doc import BoundingBox
from pydantic import BaseModel, Field
from typing import Annotated

import toon_format as toon

from tools.helpers.output_schema import VulnerabilityDetails

class DocumentSource(BaseModel):
    filename: Annotated[str, Field(description="Filename of the document.")]
    breadcrumbs: Annotated[list[str], Field(description="Breadcrumbs of headers leading to the current chunk.")]
    page_no: Annotated[int, Field(description="Page number wherein the current chunk is located.")]
    bbox: Annotated[BoundingBox, Field(description="Bounding box wherein the current chunk is located.")]
    text: Annotated[str, Field(description="Text content of the current chunk.")]

def document_to_string(documents: list[Document]) -> str:
    document_sources: list[DocumentSource] = []
    for document in documents:
        if document.meta.get("type") == "orientation_skeleton" or document.meta.get("type") == "orientation_visual_index":
            continue
        if not document.meta.get("dl_meta"):
            raise ValueError(f"Document {document.meta.get('filename')} is missing dl_meta.")
        chunk: DocChunk = DocChunk.model_validate(document.meta["dl_meta"])

        document_source = DocumentSource(
            filename=chunk.meta.origin.filename if chunk.meta.origin else "",
            breadcrumbs=chunk.meta.headings if chunk.meta.headings else [],
            page_no=chunk.meta.doc_items[0].prov[0].page_no,
            bbox=chunk.meta.doc_items[0].prov[0].bbox,
            text=chunk.text,
        )
        document_sources.append(document_source)
    return toon.encode([src.model_dump() for src in document_sources])

def vulnerabilities_to_string(vulnerabilities: list) -> str:
    result = ""
    for vulnerability in vulnerabilities:
        if isinstance(vulnerability, dict):
            # Normalize coord_origin enum prefix the LLM may copy from query output
            bbox = vulnerability.get("bbox", {})
            if isinstance(bbox.get("coord_origin"), str):
                bbox["coord_origin"] = bbox["coord_origin"].removeprefix("CoordOrigin.")
            vulnerability = VulnerabilityDetails.model_validate(vulnerability)
        result += toon.encode(vulnerability.model_dump()) + "\n"
    return result

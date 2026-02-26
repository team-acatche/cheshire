from pydantic import Field, BaseModel
from typing import Annotated
from docling_core.types.doc import DoclingDocument, BoundingBox
from docling_core.types.doc.document import TextItem, PictureItem
import uuid


class DocumentSourceMetadata(BaseModel):
    document_id: Annotated[str, Field(description="The source document's persistence id")]
    page_number: Annotated[int, Field(description="The text's page number within the document")]
    summary: Annotated[str, Field(description="A summary of the source's context")]
    bounding_box: Annotated[BoundingBox, Field(description="The set of coordinates containing the bounding box wherein the source was found")]


class DocumentSource(BaseModel):
    source_id: Annotated[str, Field(description="The source's persistence id")]
    text: Annotated[str, Field(description="The chunk of text used as the source")]
    metadata: Annotated[DocumentSourceMetadata, Field(description="The source's document-related metadata")]

    @staticmethod
    def from_docling_document(source: DoclingDocument) -> list["DocumentSource"]:
        sources: list[DocumentSource] = []
        default_bbox = BoundingBox(l=0, t=0, r=0, b=0)

        for item, level in source.iterate_items():
            text = ""

            if isinstance(item, TextItem):
                text = item.text
            elif isinstance(item, PictureItem):
                # Combine caption and description annotation if available
                parts: list[str] = []
                caption = item.caption_text(source)
                if caption:
                    parts.append(caption)
                if item.meta and item.meta.description:
                    parts.append(item.meta.description.text)
                text = " ".join(parts)
            else:
                continue

            if not text.strip():
                continue

            # Extract provenance info
            prov = item.prov[0] if item.prov else None
            page_number = prov.page_no if prov else 0
            bbox = prov.bbox if prov else default_bbox

            sources.append(DocumentSource(
                source_id=str(uuid.uuid4()),
                text=text,
                metadata=DocumentSourceMetadata(
                    document_id=source.name,
                    page_number=page_number,
                    summary="",
                    bounding_box=bbox,
                ),
            ))

        return sources

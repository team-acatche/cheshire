from docling.document_converter import DocumentConverter, PdfFormatOption # type: ignore
from docling.datamodel.pipeline_options import PdfPipelineOptions, smolvlm_picture_description # type: ignore
from docling.datamodel.base_models import InputFormat # type: ignore
from docling_core.transforms.chunker import DocChunk # type: ignore
from docling_core.types.doc import DocItem, DocItemLabel, FloatingItem, SectionHeaderItem, TitleItem, TextItem

from haystack import component, Document

import logging
logger = logging.getLogger("uvicorn.error")

_pipeline_options = PdfPipelineOptions()
_pipeline_options.do_code_enrichment = True
# _pipeline_options.do_picture_classification = True
_pipeline_options.do_picture_description = True
_pipeline_options.picture_description_options = smolvlm_picture_description

DOCUMENT_CONVERTER = DocumentConverter(format_options={
    InputFormat.PDF: PdfFormatOption(pipeline_options=_pipeline_options)
})

@component
class DoclingOrientationExtractor:
    """
    Produces a compact structural fingerprint (skeleton) and visual index from Docling's element tree.
    Token cost: ~800-3,000 tokens for most documents regardless of length.
    """

    HEADERS = [
        DocItemLabel.TITLE,
        DocItemLabel.SECTION_HEADER
    ]

    @component.output_types(documents=list[Document])
    def run(self, documents: list[Document]):
        # Aggregate across chunks since Docling/Haystack often passes all chunks of a doc at once 
        # For multi-document pipelines, this creates a single global skeleton/index over all input documents in the batch
        # Assuming typical pipeline batches by document
        skeleton: list[str] = []
        visual_index: list[str] = []
        page_toc: dict[int, list[str]] = {}
        
        # Track items seen (very basic deduplication by label and content, since overlapping chunks might repeat items)
        seen_texts = set()

        for document in documents:
            try:
                # dl_meta contains the schema dump of the DocChunk.
                chunk: DocChunk = DocChunk.model_validate(document.meta["dl_meta"])
            except Exception as e:
                logger.warning(f"Failed to validate DocChunk from metadata: {e}")
                continue

            page_no = 0
            labels = set()
            
            # Extract common chunk properties like labels and page numbers from lightweight references
            if getattr(chunk.meta, "doc_items", None):
                for doc_item in chunk.meta.doc_items:
                    label = doc_item.label.value if hasattr(doc_item.label, "value") else doc_item.label
                    labels.add(label)
                    
                    if page_no == 0 and doc_item.prov and len(doc_item.prov) > 0:
                        page_no = doc_item.prov[0].page_no
            
            # Deduplicate items
            text = chunk.text.strip()
            item_str = f"P{page_no}:{text[:50]}"
            if item_str in seen_texts:
                continue
            seen_texts.add(item_str)
            
            # Add headings explicitly 
            if getattr(chunk.meta, "headings", None):
                assert chunk.meta.headings
                for heading in chunk.meta.headings:
                    if heading not in seen_texts:
                        skeleton.append(f"[Header] {heading}")
                        page_toc.setdefault(page_no, []).append(heading)
                        seen_texts.add(heading)
            
            # Identify chunk primary purpose
            label_match = lambda l: any(lb == l or lb == getattr(DocItemLabel, l.upper(), l) for lb in labels)

            if label_match("title"):
                skeleton.append(f"Title: {text[:200]}")
            elif any(label_match(x) for x in ["picture", "table", "formula", "image"]):
                visual_index.append(f"[Visual/Table on page {page_no}: {text[:100]}{'...' if len(text) > 100 else ''}]")
            elif label_match("section_header"):
                # fallback if headed is missed by chunk.meta.headings
                skeleton.append(f"[Header] {text[:100]}")
                page_toc.setdefault(page_no, []).append(text[:100])
            elif text:
                skeleton.append(f"[Content on page {page_no}: {text[:100]}{'...' if len(text) > 100 else ''}]")
            
        # Add the resulting orientation documents if they are not entirely empty
        result_docs = list(documents) # Copy original array
        
        if skeleton:
            skeleton_doc = Document(
                content="\n".join(skeleton),
                meta={"type": "orientation_skeleton", "description": "Document architectural skeleton providing title, headings, and a preview of content blocks."}
            )
            result_docs.append(skeleton_doc)
            
        if visual_index:
            visual_index_doc = Document(
                content="\n".join(visual_index),
                meta={"type": "orientation_visual_index", "description": "Document visual index describing figures, images, and tables mapped to pages."}
            )
            result_docs.append(visual_index_doc)

        return {"documents": result_docs}
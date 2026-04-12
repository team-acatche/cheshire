import os
from typing import Callable, Optional
from pathlib import Path
from fastapi import HTTPException, status

from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_haystack.converter import DoclingConverter
from haystack.document_stores.types import DocumentStore
from haystack.components.embedders.types import TextEmbedder
from haystack.components.writers import DocumentWriter
from haystack.core.pipeline import Pipeline

from haystack.components.embedders.hugging_face_api_document_embedder import HuggingFaceAPIDocumentEmbedder, HFEmbeddingAPIType
from haystack.components.embedders.types import DocumentEmbedder
from haystack_integrations.components.embedders.fastembed import FastembedDocumentEmbedder

from cheshire_configs.core import DocumentPreprocessor, PipelineConfig
from cheshire_configs.preprocessors.rag import DOCUMENT_CONVERTER, DoclingOrientationExtractor
from cheshire_configs.preprocessors.fallbacks import FallbackDocumentEmbedder

class DefaultRagPreprocessor(DocumentPreprocessor):
    def __init__(self, config: PipelineConfig):
        self.config = config

    def __call__(self, document: Path, document_store: Optional[DocumentStore] = None):
        if not document_store:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document store is required for DefaultRagPreprocessor")
        if not self.config.document_embedder:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document embedder is required for DefaultRagPreprocessor")

        docling_converter = DoclingConverter(
            converter=DOCUMENT_CONVERTER,
        	chunker=HybridChunker(tokenizer=HuggingFaceTokenizer.from_pretrained(
        	    os.getenv("HF_EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v2-moe"),
        	    max_tokens=2**13, # 8192
            ))
        )

        rag_pipeline = Pipeline()
        rag_pipeline.add_component("converter", docling_converter)
        rag_pipeline.add_component("orientation_extractor", DoclingOrientationExtractor())
        rag_pipeline.add_component("embedder", self.config.document_embedder())
        rag_pipeline.add_component("writer", DocumentWriter(document_store))

        rag_pipeline.connect("converter", "orientation_extractor")
        rag_pipeline.connect("orientation_extractor", "embedder")
        rag_pipeline.connect("embedder", "writer")

        rag_pipeline.run({ "paths": [document] })

	
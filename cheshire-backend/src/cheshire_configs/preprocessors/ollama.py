import os
from typing import Callable, Optional
from pathlib import Path
from fastapi import HTTPException

from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_haystack.converter import DoclingConverter
from haystack.document_stores.types import DocumentStore
from haystack.components.embedders.types import TextEmbedder
from haystack.components.writers import DocumentWriter
from haystack.core.pipeline import Pipeline

from haystack.components.embedders.hugging_face_api_document_embedder import HuggingFaceAPIDocumentEmbedder, HFEmbeddingAPIType
from haystack.components.embedders.types import DocumentEmbedder
from haystack_integrations.components.embedders.ollama import OllamaDocumentEmbedder

from cheshire_configs.core import DocumentPreprocessor
from cheshire_configs.preprocessors.rag import DOCUMENT_CONVERTER, DoclingOrientationExtractor
from cheshire_configs.preprocessors.fallbacks import FallbackDocumentEmbedder

class OllamaRagPreprocessor(DocumentPreprocessor):
    def __call__(self, document: Path, document_store: Optional[DocumentStore] = None):
        if not document_store:
            raise HTTPException(status_code=500, detail="Document store is required for OllamaRagPreprocessor")

        docling_converter = DoclingConverter(
            converter=DOCUMENT_CONVERTER,
        	chunker=HybridChunker(tokenizer=HuggingFaceTokenizer.from_pretrained(
        	    os.getenv("HF_EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v2-moe"),
        	    max_tokens=2**13, # 8192
            ))
        )

        embedder = OllamaDocumentEmbedder(
            model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
            url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        )
        backup_embedder = HuggingFaceAPIDocumentEmbedder(
            api_type=HFEmbeddingAPIType.SERVERLESS_INFERENCE_API,
            api_params={
                "model": os.getenv("HF_EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v2-moe"),
            }
        )
        document_writer = DocumentWriter(document_store)

        rag_pipeline = Pipeline()
        rag_pipeline.add_component("converter", docling_converter)
        rag_pipeline.add_component("orientation_extractor", DoclingOrientationExtractor())
        rag_pipeline.add_component("embedder", FallbackDocumentEmbedder(embedder, backup_embedder))
        rag_pipeline.add_component("writer", document_writer)

        rag_pipeline.connect("converter", "orientation_extractor")
        rag_pipeline.connect("orientation_extractor", "embedder")
        rag_pipeline.connect("embedder", "writer")

        rag_pipeline.run({ "paths": [document] })

	
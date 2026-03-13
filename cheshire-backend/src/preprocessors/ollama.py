import os
from typing import Callable
from pathlib import Path
from fastapi import HTTPException

from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_haystack.converter import DoclingConverter
from haystack.document_stores.types import DocumentStore
from haystack.components.embedders.types import TextEmbedder
from haystack.components.writers import DocumentWriter
from haystack.core.pipeline import Pipeline
from haystack_integrations.components.embedders.ollama import OllamaDocumentEmbedder

from cheshire_configs.core import DocumentPreprocessor

class OllamaRagPreprocessor(DocumentPreprocessor):
    def __call__(self, document: Path, document_store: DocumentStore | None = None):
        if not document_store:
            raise HTTPException(status_code=500, detail="Document store is required for OllamaRagPreprocessor")

        docling_converter = DoclingConverter(
        	chunker=HybridChunker(tokenizer=HuggingFaceTokenizer.from_pretrained(
        	    os.getenv("HF_EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v2-moe"),
        	    max_tokens=2**13, # 8192
            ))
        )

        embedder = OllamaDocumentEmbedder(
        	model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
        	url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        )
        document_writer = DocumentWriter(document_store)

        rag_pipeline = Pipeline()
        rag_pipeline.add_component("converter", docling_converter)
        rag_pipeline.add_component("embedder", embedder)
        rag_pipeline.add_component("writer", document_writer)
        rag_pipeline.connect("converter", "embedder")
        rag_pipeline.connect("embedder", "writer")

        rag_pipeline.run({ "paths": [document] })

	
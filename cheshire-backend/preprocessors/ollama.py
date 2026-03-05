import os
from typing import Callable
from pathlib import Path

from docling.chunking import HybridChunker
from docling_haystack.converter import DoclingConverter
from haystack.document_stores.types import DocumentStore
from haystack.components.embedders.types import TextEmbedder
from haystack.components.writers import DocumentWriter
from haystack.core.pipeline import Pipeline
from haystack_integrations.components.embedders.ollama import OllamaDocumentEmbedder

def ollama_rag_preprocessor(document_store: DocumentStore) -> Callable[[Path], None]:
    """
    Returns a preprocessor that converts a document into chunks and embeds them into the document store.

    :param document_store: The document store to embed the documents into.
    :return: A preprocessor function that takes a document path and embeds it into the document store.

    Environment variables:
       * `HF_EMBEDDING_MODEL`: The HuggingFace model name to be used by the Hybrid Chunker to apply tokenization to the document chunks.
       * `OLLAMA_EMBEDDING_MODEL`: The model to use for embedding the documents.
       * `OLLAMA_URL`: The URL of the Ollama server.
    """
    def preprocessor(document_path: Path) -> None:
        docling_converter = DoclingConverter(
        	chunker=HybridChunker(
        		tokenizer=os.getenv("HF_EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v2-moe"),
        		max_tokens=2**13,
        	)
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

    return preprocessor

	
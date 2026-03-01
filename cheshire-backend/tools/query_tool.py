from typing import Callable, Annotated, Any
import os

from haystack.core.pipeline import Pipeline
from haystack.dataclasses import Document
from haystack.document_stores.in_memory import InMemoryDocumentStore
# from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
from haystack.components.retrievers import InMemoryEmbeddingRetriever
# from haystack_integrations.components.embedders.google_genai import GoogleGenAITextEmbedder
# from haystack.components.embedders.hugging_face_api_text_embedder import HuggingFaceAPITextEmbedder, HFEmbeddingAPIType
from haystack_integrations.components.embedders.ollama import OllamaTextEmbedder

from dotenv import load_dotenv

load_dotenv()


def query_pipeline(document_store: InMemoryDocumentStore) -> Pipeline:
    embedder = OllamaTextEmbedder(
        model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
        url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
    )
    retriever = InMemoryEmbeddingRetriever(document_store, top_k=5)
    # retriever = InMemoryBM25Retriever(document_store, top_k=3)

    retrieval_pipeline = Pipeline()
    retrieval_pipeline.add_component("embedder", embedder)
    retrieval_pipeline.add_component("retriever", retriever)
    retrieval_pipeline.connect("embedder.embedding", "retriever")

    return retrieval_pipeline
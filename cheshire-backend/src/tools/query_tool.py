from typing import Callable, Annotated, Any
import os

from haystack.core.pipeline import Pipeline
from haystack.dataclasses import Document
from haystack.document_stores.in_memory import InMemoryDocumentStore
from haystack.components.retrievers import InMemoryEmbeddingRetriever
from haystack_integrations.components.embedders.fastembed import FastembedTextEmbedder

from cheshire_configs.retrievers.hybrid_retriever import HybridInMemoryRetriever

from dotenv import load_dotenv

load_dotenv()


def query_pipeline(document_store: InMemoryDocumentStore) -> Pipeline:
    embedder = FastembedTextEmbedder(model="sentence-transformers/all-MiniLM-L6-v2")
    retriever = HybridInMemoryRetriever(document_store, embedder)

    return retriever.pipeline
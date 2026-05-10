from typing import Protocol, List, Optional, Any
from haystack import Document, Pipeline
from lancedb_haystack import LanceDBDocumentStore # type: ignore
from cheshire_configs.retrievers.hybrid_retriever import HybridLanceDbRetriever

from haystack.components.writers.document_writer import DocumentWriter, DuplicatePolicy
from haystack_integrations.components.embedders.fastembed import FastembedDocumentEmbedder, FastembedTextEmbedder

from knowledge_base.repository import KnowledgeRepository

class LanceDbKnowledgeRepository(KnowledgeRepository):
    def __init__(
        self, 
        document_store: LanceDBDocumentStore, 
        retriever: HybridLanceDbRetriever, 
        upsert_pipeline: Pipeline
    ):
        self._document_store = document_store
        self._retriever = retriever
        self._upsert_pipeline = upsert_pipeline

    @classmethod
    def create(cls, document_store: LanceDBDocumentStore) -> "LanceDbKnowledgeRepository":
        embedder = FastembedDocumentEmbedder()
        retriever = HybridLanceDbRetriever(document_store, FastembedTextEmbedder())
        
        upsert_pipeline = Pipeline()
        upsert_pipeline.add_component("embedder", embedder)
        upsert_pipeline.add_component("writer", DocumentWriter(document_store=document_store, policy=DuplicatePolicy.OVERWRITE))
        upsert_pipeline.connect("embedder", "writer")
        
        return cls(document_store, retriever, upsert_pipeline)

    def query(self, filters: Optional[dict] = None, top_k: Optional[int] = None) -> List[Document]:
        return self._document_store.perform_query(filters=filters, top_k=top_k)

    def search(self, query: str, top_k: Optional[int] = None) -> List[Document]:
        return self._retriever.run(query=query, top_k=top_k)["documents"] # type: ignore

    def save(self, documents: List[Document]) -> None:
        self._upsert_pipeline.run({"embedder": {"documents": documents}})

class LanceDbEventRepository(KnowledgeRepository):
    def __init__(self, document_store: LanceDBDocumentStore):
        self._document_store = document_store

    def query(self, filters: Optional[dict] = None, top_k: Optional[int] = None) -> List[Document]:
        return self._document_store.perform_query(filters=filters, top_k=top_k)

    def search(self, query: str, top_k: Optional[int] = None) -> List[Document]:
        # event_store doesn't currently support semantic search in the tools
        return []

    def save(self, documents: List[Document]) -> None:
        # We use SKIP policy for events by default to avoid issues with already existing events
        self._document_store.write_documents(documents, policy=DuplicatePolicy.SKIP)
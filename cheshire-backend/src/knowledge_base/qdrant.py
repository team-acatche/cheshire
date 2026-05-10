import os
from pathlib import Path
from typing import List, Optional, Tuple, Any
from haystack import Document, Pipeline
from haystack.components.writers.document_writer import DocumentWriter
from haystack.document_stores.types import DuplicatePolicy
from haystack_integrations.document_stores.qdrant import QdrantDocumentStore
from haystack_integrations.components.retrievers.qdrant import QdrantEmbeddingRetriever
from haystack_integrations.components.embedders.fastembed import FastembedDocumentEmbedder, FastembedTextEmbedder

from knowledge_base.repository import KnowledgeRepository

class QdrantKnowledgeRepository(KnowledgeRepository):
    def __init__(
        self, 
        document_store: QdrantDocumentStore, 
        retriever: QdrantEmbeddingRetriever, 
        upsert_pipeline: Pipeline,
        text_embedder: FastembedTextEmbedder
    ):
        self._document_store = document_store
        self._retriever = retriever
        self._upsert_pipeline = upsert_pipeline
        self._text_embedder = text_embedder

    @classmethod
    def create(cls, document_store: QdrantDocumentStore) -> "QdrantKnowledgeRepository":
        # Using EmbeddingRetriever for now to ensure compatibility with Fastembed
        retriever = QdrantEmbeddingRetriever(document_store=document_store)
        
        embedder = FastembedDocumentEmbedder()
        embedder.warm_up()
        
        text_embedder = FastembedTextEmbedder()
        text_embedder.warm_up()
        
        upsert_pipeline = Pipeline()
        upsert_pipeline.add_component("embedder", embedder)
        upsert_pipeline.add_component("writer", DocumentWriter(document_store=document_store, policy=DuplicatePolicy.OVERWRITE))
        upsert_pipeline.connect("embedder", "writer")
        
        return cls(document_store, retriever, upsert_pipeline, text_embedder)

    def query(self, filters: Optional[dict] = None, top_k: Optional[int] = None) -> List[Document]:
        return self._document_store.filter_documents(filters=filters)

    def search(self, query: str, top_k: Optional[int] = None) -> List[Document]:
        embedding = self._text_embedder.run(query)["embedding"]
        return self._retriever.run(query_embedding=embedding, top_k=top_k)["documents"]

    def save(self, documents: List[Document]) -> None:
        import logging
        logger = logging.getLogger("uvicorn.error")
        logger.info(f"QdrantRepository: Saving {len(documents)} documents to knowledge store...")
        try:
            result = self._upsert_pipeline.run({"embedder": {"documents": documents}})
            logger.info(f"QdrantRepository: Save pipeline finished. Result: {result}")
        except Exception as e:
            logger.error(f"QdrantRepository: Failed to save documents: {e}")
            raise

class QdrantEventRepository(KnowledgeRepository):
    def __init__(self, document_store: QdrantDocumentStore):
        self._document_store = document_store

    def query(self, filters: Optional[dict] = None, top_k: Optional[int] = None) -> List[Document]:
        return self._document_store.filter_documents(filters=filters)

    def search(self, query: str, top_k: Optional[int] = None) -> List[Document]:
        return []

    def save(self, documents: List[Document]) -> None:
        self._document_store.write_documents(documents, policy=DuplicatePolicy.SKIP)

class QdrantRepositoryManager:
    @staticmethod
    def get_repositories(
        storage_path: Path, 
        username: str, 
        dimensions: int = 384
    ) -> Tuple[KnowledgeRepository, KnowledgeRepository]:
        connection_params: dict[str, Any] = {}

        qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
        
        if qdrant_host:
            connection_params = {"host": qdrant_host, "port": qdrant_port}
        else:
            # Qdrant in embedded mode uses a path
            qdrant_path = str(storage_path / "qdrant")
            connection_params = {"path": qdrant_path}
        
        event_store = QdrantDocumentStore(
            index="events",
            embedding_dim=dimensions,
            **connection_params
        )
        knowledge_store = QdrantDocumentStore(
            index="knowledge",
            embedding_dim=dimensions,
            **connection_params
        )

        return (
            QdrantEventRepository(event_store),
            QdrantKnowledgeRepository.create(knowledge_store)
        )

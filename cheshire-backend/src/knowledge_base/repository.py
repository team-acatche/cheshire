from enum import Enum
from pathlib import Path
from typing import Protocol, List, Optional, Tuple
from haystack import Document

class KnowledgeRepository(Protocol):
    def query(self, filters: Optional[dict] = None, top_k: Optional[int] = None) -> List[Document]:
        """Query documents based on filters."""
        ...

    def search(self, query: str, top_k: Optional[int] = None) -> List[Document]:
        """Perform semantic search."""
        ...

    def save(self, documents: list[Document]) -> None:
        """Write or update documents."""
        ...
    
    def delete_with_session(self, session_id: str) -> None:
        """Delete all documents with the given session ID."""
        ...

class RepositoryType(Enum):
    LANCEDB = "lancedb"
    QDRANT = "qdrant"

class KnowledgeRepositoryFactory:
    @staticmethod
    def create_repositories(
        repo_type: RepositoryType, 
        storage_path: Path, 
        username: str
    ) -> Tuple[KnowledgeRepository, KnowledgeRepository]:
        """Returns (event_repository, knowledge_repository)"""
        if repo_type == RepositoryType.LANCEDB:
            from knowledge_base.lancedb import LanceDbRepositoryManager
            return LanceDbRepositoryManager.get_repositories(storage_path, username)
        elif repo_type == RepositoryType.QDRANT:
            from knowledge_base.qdrant import QdrantRepositoryManager
            return QdrantRepositoryManager.get_repositories(storage_path, username)
        raise ValueError(f"Unsupported repository type: {repo_type}")

    @staticmethod
    def create_knowledge_repository(repo_type: RepositoryType, **kwargs) -> KnowledgeRepository:
        if repo_type == RepositoryType.LANCEDB:
            from knowledge_base.lancedb import LanceDbKnowledgeRepository
            return LanceDbKnowledgeRepository.create(kwargs["document_store"])
        elif repo_type == RepositoryType.QDRANT:
            from knowledge_base.qdrant import QdrantKnowledgeRepository
            return QdrantKnowledgeRepository.create(kwargs["document_store"])
        raise ValueError(f"Unsupported repository type: {repo_type}")

    @staticmethod
    def create_event_repository(repo_type: RepositoryType, **kwargs) -> KnowledgeRepository:
        if repo_type == RepositoryType.LANCEDB:
            from knowledge_base.lancedb import LanceDbEventRepository
            return LanceDbEventRepository(kwargs["document_store"])
        elif repo_type == RepositoryType.QDRANT:
            from knowledge_base.qdrant import QdrantEventRepository
            return QdrantEventRepository(kwargs["document_store"])
        raise ValueError(f"Unsupported repository type: {repo_type}")

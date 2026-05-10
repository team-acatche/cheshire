from typing import Protocol, List, Optional
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

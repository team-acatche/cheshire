from pathlib import Path
from lancedb_haystack import LanceDBDocumentStore # type: ignore

async def create_vector_stores(session_path: Path) -> LanceDBDocumentStore:
    """
    Creates and initializes the LanceDB document store for the session.
    """
    # ensure the parent directory exists
    lancedb_path = session_path / "knowledge_base"
    lancedb_path.mkdir(parents=True, exist_ok=True)
    
    document_store = LanceDBDocumentStore(
        database=str(lancedb_path),
        table_name="documents",
    )
    return document_store
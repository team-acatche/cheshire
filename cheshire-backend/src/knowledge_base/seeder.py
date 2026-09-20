import json
import logging
from pathlib import Path
from typing import List
from uuid import uuid5, NAMESPACE_OID

from haystack import Document

from globals import DATA_PATH, STANDARDS_DIR
from knowledge_base.qdrant import KnowledgeRepository

logger = logging.getLogger("uvicorn.error")

def extract_standards_from(file_path: Path) -> List[str]:
    """Extracts checklist requirement items from a JSON file."""
    # Ensure path is within STANDARDS_DIR to prevent directory traversal
    resolved = file_path.resolve()
    base_dir = STANDARDS_DIR.resolve()
    if not str(resolved).startswith(str(base_dir) + "/") and resolved != base_dir:
        logger.warning(f"Knowledge seeder: Skipping file outside standards directory: {file_path}")
        return []

    if not file_path.is_file() or file_path.stat().st_size == 0:
        return []

    items: List[str] = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, str) and entry.strip():
                    items.append(entry.strip())
    except Exception as e:
        logger.error(f"Knowledge seeder: Failed to parse {file_path.name}: {e}")

    return items


def seed_knowledge_base(
    knowledge_repo: KnowledgeRepository,
    standards: list[str],
):
    """
    Seeds the Qdrant knowledge base with company standards / checklist items
    from the standards assets directory on application startup.
    """
    if not standards:
        logger.info("Knowledge seeder: Standards checklist is empty. No documents to seed.")
        return

    # Convert the standards into Haystack Documents
    standard_documents: list[Document] = []
    for standard in standards:
        # Deterministic UUID based on item content to prevent duplication on restarts
        standard_id = str(uuid5(NAMESPACE_OID, f"standard:{standard}"))
        standard_documents.append(
                Document(
                    id=standard_id,
                    content=standard,
                    meta={
                        "source": file_path.name,
                        "is_global": True,
                    }
                )
        )

    try:
        logger.info(f"Knowledge seeder: Seeding {len(standard_documents)} standards into knowledge base...")
        knowledge_repo.save(standard_documents)
        logger.info(f"Knowledge seeder: Successfully seeded {len(standard_documents)} standards.")
    except Exception as e:
        logger.error(f"Knowledge seeder: Failed to seed knowledge base: {e}")
    

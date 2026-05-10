import os
import shutil
from pathlib import Path
from lancedb_haystack import LanceDBDocumentStore # type: ignore

from knowledge_base.repository import LanceDbKnowledgeRepository # type: ignore

def test_search():
    db_path = "/tmp/test_knowledge_repo"
    if os.path.exists(db_path):
        shutil.rmtree(db_path)
    
    ds = LanceDBDocumentStore(database=db_path, table_name="test", embedding_dims=384)
    repo = LanceDbKnowledgeRepository.create(ds)
    
    print(f"Repo created. Retriever type: {type(repo._retriever)}")
    print(f"Has run: {hasattr(repo._retriever, 'run')}")
    
    try:
        results = repo.search("test query", top_k=1)
        print(f"Search results: {results}")
    except AttributeError as e:
        print(f"Caught expected error: {e}")
    except Exception as e:
        print(f"Caught unexpected error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    test_search()

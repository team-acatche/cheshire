from unittest.mock import MagicMock, patch
from haystack import Document
from knowledge_base.qdrant import QdrantKnowledgeRepository, QdrantEventRepository
from knowledge_base.lancedb import LanceDbKnowledgeRepository, LanceDbEventRepository

def test_qdrant_knowledge_repository_delete_with_session():
    mock_store = MagicMock()
    # QdrantKnowledgeRepository.create is a classmethod that does some fastembed init,
    # so we construct it manually with mock dependencies.
    repo = QdrantKnowledgeRepository(
        document_store=mock_store,
        retriever=MagicMock(),
        upsert_pipeline=MagicMock(),
        text_embedder=MagicMock()
    )

    repo.delete_with_session("test_session_123")

    mock_store.delete_by_filter.assert_called_once_with(filters={
        "operator": "AND",
        "conditions": [
            {
                "field": "meta.session_id",
                "operator": "==",
                "value": "test_session_123",
            },
            {
                "field": "meta.is_global",
                "operator": "==",
                "value": False,
            },
        ]
    })

def test_qdrant_event_repository_delete_with_session():
    mock_store = MagicMock()
    repo = QdrantEventRepository(document_store=mock_store)

    repo.delete_with_session("test_session_123")

    mock_store.delete_by_filter.assert_called_once_with(filters={
        "field": "meta.session_id",
        "operator": "==",
        "value": "test_session_123",
    })

def test_lancedb_knowledge_repository_delete_with_session():
    mock_store = MagicMock()
    repo = LanceDbKnowledgeRepository(
        document_store=mock_store,
        retriever=MagicMock(),
        upsert_pipeline=MagicMock()
    )

    # Mock query to return documents
    docs = [
        Document(id="doc1", content="fact1", meta={"session_id": "test_session_123", "is_global": False}),
        Document(id="doc2", content="fact2", meta={"session_id": "test_session_123", "is_global": False})
    ]
    with patch.object(repo, "query", return_value=docs) as mock_query:
        repo.delete_with_session("test_session_123")

        mock_query.assert_called_once_with(filters={
            "operator": "AND",
            "conditions": [
                {
                    "field": "meta.session_id",
                    "operator": "==",
                    "value": "test_session_123",
                },
                {
                    "field": "meta.is_global",
                    "operator": "==",
                    "value": False,
                },
            ]
        })
        mock_store.delete_documents.assert_called_once_with(["doc1", "doc2"])

def test_lancedb_knowledge_repository_delete_with_session_no_docs():
    mock_store = MagicMock()
    repo = LanceDbKnowledgeRepository(
        document_store=mock_store,
        retriever=MagicMock(),
        upsert_pipeline=MagicMock()
    )

    with patch.object(repo, "query", return_value=[]) as mock_query:
        repo.delete_with_session("test_session_123")
        mock_query.assert_called_once()
        mock_store.delete_documents.assert_not_called()

def test_lancedb_event_repository_delete_with_session():
    mock_store = MagicMock()
    repo = LanceDbEventRepository(document_store=mock_store)

    docs = [
        Document(id="evt1", content="event1", meta={"session_id": "test_session_123"}),
        Document(id="evt2", content="event2", meta={"session_id": "test_session_123"})
    ]
    with patch.object(repo, "query", return_value=docs) as mock_query:
        repo.delete_with_session("test_session_123")

        mock_query.assert_called_once_with(filters={
            "field": "meta.session_id",
            "operator": "==",
            "value": "test_session_123",
        })
        mock_store.delete_documents.assert_called_once_with(["evt1", "evt2"])

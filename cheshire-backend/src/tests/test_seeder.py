"""
Tests for knowledge base seeder.
Uses deterministic, fake test standards with both an in-memory Qdrant instance
and repository mocks, completely isolated from the host machine's Qdrant instance
and live checklist assets.
"""

import json
from pathlib import Path
from uuid import uuid5, NAMESPACE_OID

import pytest
from haystack import Document
from haystack_integrations.document_stores.qdrant import QdrantDocumentStore

from knowledge_base.qdrant import QdrantKnowledgeRepository
from knowledge_base.repository import KnowledgeRepository
from knowledge_base.seeder import extract_standards_from, seed_knowledge_base

DETERMINISTIC_FAKE_STANDARDS = [
    "All passwords must be hashed using Argon2id with a unique per-user salt.",
    "Session tokens must expire after 15 minutes of inactivity.",
    "File uploads must restrict allowed MIME types and enforce a 10MB size limit.",
]

# ---------------------------------------------------------------------------
# File extraction unit tests
# ---------------------------------------------------------------------------

class TestExtractStandards:
    """Tests for extract_standards_from function."""

    def test_extract_valid_standards_from_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("knowledge_base.seeder.STANDARDS_DIR", tmp_path)
        test_file = tmp_path / "fake_standards.json"
        test_file.write_text(json.dumps(DETERMINISTIC_FAKE_STANDARDS), encoding="utf-8")

        extracted = extract_standards_from(test_file)
        assert extracted == DETERMINISTIC_FAKE_STANDARDS

    def test_extract_filters_out_empty_or_whitespace_strings(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("knowledge_base.seeder.STANDARDS_DIR", tmp_path)
        test_file = tmp_path / "fake_standards.json"
        test_file.write_text(
            json.dumps(["Standard 1", "", "   ", "Standard 2"]),
            encoding="utf-8",
        )

        extracted = extract_standards_from(test_file)
        assert extracted == ["Standard 1", "Standard 2"]

    def test_extract_from_empty_file_returns_empty_list(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("knowledge_base.seeder.STANDARDS_DIR", tmp_path)
        test_file = tmp_path / "empty.json"
        test_file.touch()

        assert extract_standards_from(test_file) == []

    def test_extract_from_empty_json_array_returns_empty_list(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("knowledge_base.seeder.STANDARDS_DIR", tmp_path)
        test_file = tmp_path / "empty_array.json"
        test_file.write_text("[]", encoding="utf-8")

        assert extract_standards_from(test_file) == []

    def test_extract_from_malformed_json_returns_empty_list(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("knowledge_base.seeder.STANDARDS_DIR", tmp_path)
        test_file = tmp_path / "invalid.json"
        test_file.write_text("{not valid json", encoding="utf-8")

        assert extract_standards_from(test_file) == []

    def test_extract_file_outside_standards_dir_is_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        standards_dir = tmp_path / "standards"
        standards_dir.mkdir()
        monkeypatch.setattr("knowledge_base.seeder.STANDARDS_DIR", standards_dir)

        outside_file = tmp_path / "outside.json"
        outside_file.write_text(json.dumps(["Malicious standard"]), encoding="utf-8")

        # Security check: Files outside standards directory should be rejected
        extracted = extract_standards_from(outside_file)
        assert extracted == []


# ---------------------------------------------------------------------------
# In-Memory Qdrant integration tests
# ---------------------------------------------------------------------------

class TestSeedKnowledgeBaseWithInMemoryQdrant:
    """
    Integration tests using an in-memory QdrantDocumentStore.
    Runs Fastembed embedding and Qdrant vector retrieval without touching host Qdrant.
    """

    @pytest.fixture
    def in_memory_knowledge_repo(self):
        store = QdrantDocumentStore(
            location=":memory:",
            index="test_knowledge",
            embedding_dim=384,
        )
        return QdrantKnowledgeRepository.create(store)

    def test_in_memory_seeding_and_semantic_retrieval(self, in_memory_knowledge_repo):
        repo = in_memory_knowledge_repo

        seed_knowledge_base(
            knowledge_repo=repo,
            standards=DETERMINISTIC_FAKE_STANDARDS,
            source="in_memory_test.json",
        )

        # 1. Verify documents count in store
        assert repo._document_store.count_documents() == len(DETERMINISTIC_FAKE_STANDARDS)

        # 2. Verify semantic search retrieves the most relevant standard
        password_results = repo.search(query="password hashing requirements", top_k=1)
        assert len(password_results) == 1
        assert "Argon2id" in password_results[0].content
        assert password_results[0].meta["source"] == "in_memory_test.json"
        assert password_results[0].meta["is_global"] is True

        upload_results = repo.search(query="file upload size limit", top_k=1)
        assert len(upload_results) == 1
        assert "10MB" in upload_results[0].content

    def test_in_memory_seeding_idempotency_does_not_duplicate(self, in_memory_knowledge_repo):
        repo = in_memory_knowledge_repo

        # First seed run
        seed_knowledge_base(repo, DETERMINISTIC_FAKE_STANDARDS, source="in_memory_test.json")
        initial_count = repo._document_store.count_documents()
        assert initial_count == len(DETERMINISTIC_FAKE_STANDARDS)

        # Second seed run with identical standards
        seed_knowledge_base(repo, DETERMINISTIC_FAKE_STANDARDS, source="in_memory_test.json")
        second_count = repo._document_store.count_documents()

        # Count must remain the same due to deterministic IDs and overwrite policy
        assert second_count == initial_count

"""Tests for tools.knowledge — upsert_fact_tool and get_facts_tool changes."""

from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from haystack import Document
from haystack.tools import Tool

from tools.knowledge import upsert_fact_tool, get_facts_tool, get_relevant_facts_tool


# ---------------------------------------------------------------------------
# upsert_fact_tool
# ---------------------------------------------------------------------------

class TestUpsertFactTool:
    """Tests for the updated upsert_fact_tool factory."""

    @pytest.fixture
    def mock_store(self):
        return MagicMock()

    @pytest.fixture
    def mock_embedder(self):
        return lambda: MagicMock()

    @patch("tools.knowledge.HybridLanceDbRetriever")
    @patch("tools.knowledge.Pipeline")
    def test_returns_tool(self, MockPipeline, MockRetriever, mock_store, mock_embedder):
        MockPipeline.return_value = MagicMock()
        t = upsert_fact_tool(uuid4(), knowledge_store=mock_store, embedder=mock_embedder)
        assert isinstance(t, Tool)

    @patch("tools.knowledge.HybridLanceDbRetriever")
    @patch("tools.knowledge.Pipeline")
    def test_tool_name_is_upsert_fact(self, MockPipeline, MockRetriever, mock_store, mock_embedder):
        MockPipeline.return_value = MagicMock()
        t = upsert_fact_tool(uuid4(), knowledge_store=mock_store, embedder=mock_embedder)
        assert t.name == "upsert_fact"

    @patch("tools.knowledge.HybridLanceDbRetriever")
    @patch("tools.knowledge.Pipeline")
    def test_new_fact_generates_uuid_id(self, MockPipeline, MockRetriever, mock_store):
        """New facts should get a UUID as their Document.id (not in meta)."""
        mock_pipeline = MagicMock()
        MockPipeline.return_value = mock_pipeline
        mock_pipeline.add_component = MagicMock()
        mock_pipeline.connect = MagicMock()

        retriever_instance = MagicMock()
        retriever_instance.run.return_value = {"documents": []}
        MockRetriever.return_value = retriever_instance

        sid = uuid4()
        t = upsert_fact_tool(sid, knowledge_store=mock_store, embedder=lambda: MagicMock())
        t.invoke(facts=["The sky is blue"])

        # Check that the pipeline was called with documents
        run_call = mock_pipeline.run.call_args
        embedder_input = run_call.args[0] if run_call.args else run_call.kwargs
        docs = embedder_input.get("embedder", {}).get("documents", [])
        assert len(docs) == 1
        doc = docs[0]
        # id should be a valid UUID string
        UUID(doc.id)  # raises if not valid
        assert "knowledge_id" not in doc.meta
        assert doc.meta["session_id"] == str(sid)
        assert doc.meta["is_global"] is False

    @patch("tools.knowledge.HybridLanceDbRetriever")
    @patch("tools.knowledge.Pipeline")
    def test_new_fact_meta_has_no_knowledge_id(self, MockPipeline, MockRetriever, mock_store):
        """The change removed knowledge_id from meta — verify it's absent."""
        mock_pipeline = MagicMock()
        MockPipeline.return_value = mock_pipeline
        mock_pipeline.add_component = MagicMock()
        mock_pipeline.connect = MagicMock()

        retriever_instance = MagicMock()
        retriever_instance.run.return_value = {"documents": []}
        MockRetriever.return_value = retriever_instance

        t = upsert_fact_tool(uuid4(), knowledge_store=mock_store, embedder=lambda: MagicMock())
        t.invoke(facts=["fact one"])

        docs = mock_pipeline.run.call_args[0][0]["embedder"]["documents"]
        for doc in docs:
            assert "knowledge_id" not in doc.meta

    @patch("tools.knowledge.HybridLanceDbRetriever")
    @patch("tools.knowledge.Pipeline")
    def test_incorrect_fact_lookup_uses_id_field(self, MockPipeline, MockRetriever, mock_store):
        """When incorrect_fact_knowledge_id is given, the filter should use 'id', not 'meta.knowledge_id'."""
        mock_pipeline = MagicMock()
        MockPipeline.return_value = mock_pipeline
        mock_pipeline.add_component = MagicMock()
        mock_pipeline.connect = MagicMock()

        existing = Document(id="abc-123", content="old", meta={"last_modified": "x"})
        mock_store.perform_query.return_value = [existing]

        t = upsert_fact_tool(uuid4(), knowledge_store=mock_store, embedder=lambda: MagicMock())
        t.invoke(facts=["corrected fact"], incorrect_fact_knowledge_id="abc-123")

        call_kwargs = mock_store.perform_query.call_args
        filters = call_kwargs.kwargs.get("filters") or call_kwargs[1]["filters"]
        assert filters["field"] == "id"
        assert filters["value"] == "abc-123"

    @patch("tools.knowledge.HybridLanceDbRetriever")
    @patch("tools.knowledge.Pipeline")
    def test_incorrect_fact_not_found_returns_message(self, MockPipeline, MockRetriever, mock_store):
        """If the incorrect fact is not found, return a descriptive message."""
        mock_pipeline = MagicMock()
        MockPipeline.return_value = mock_pipeline
        mock_pipeline.add_component = MagicMock()
        mock_pipeline.connect = MagicMock()

        mock_store.perform_query.return_value = []

        t = upsert_fact_tool(uuid4(), knowledge_store=mock_store, embedder=lambda: MagicMock())
        result = t.invoke(facts=["corrected"], incorrect_fact_knowledge_id="nonexistent-id")
        assert "not found" in result.lower()

    @patch("tools.knowledge.HybridLanceDbRetriever")
    @patch("tools.knowledge.Pipeline")
    def test_returns_count_summary(self, MockPipeline, MockRetriever, mock_store):
        """Result should include counts of added and updated facts."""
        mock_pipeline = MagicMock()
        MockPipeline.return_value = mock_pipeline
        mock_pipeline.add_component = MagicMock()
        mock_pipeline.connect = MagicMock()

        retriever_instance = MagicMock()
        retriever_instance.run.return_value = {"documents": []}
        MockRetriever.return_value = retriever_instance

        t = upsert_fact_tool(uuid4(), knowledge_store=mock_store, embedder=lambda: MagicMock())
        result = t.invoke(facts=["fact1", "fact2"])
        assert "2" in result
        assert "added" in result.lower()


# ---------------------------------------------------------------------------
# get_facts_tool
# ---------------------------------------------------------------------------

class TestGetFactsTool:
    """Tests for the get_facts_tool factory."""

    @pytest.fixture
    def mock_store(self):
        return MagicMock()

    def test_returns_tool(self, mock_store):
        t = get_facts_tool(uuid4(), knowledge_store=mock_store)
        assert isinstance(t, Tool)

    def test_tool_name(self, mock_store):
        t = get_facts_tool(uuid4(), knowledge_store=mock_store)
        assert t.name == "get_facts"

    def test_session_filter_without_global(self, mock_store):
        """Without global, operator should be AND."""
        sid = uuid4()
        mock_store.perform_query.return_value = []
        t = get_facts_tool(sid, knowledge_store=mock_store)
        t.invoke(with_global=False)

        filters = mock_store.perform_query.call_args.kwargs["filters"]
        assert filters["operator"] == "AND"
        conditions = filters["conditions"]
        session_cond = next(c for c in conditions if c["field"] == "meta.session_id")
        assert session_cond["value"] == str(sid)

    def test_session_filter_with_global(self, mock_store):
        """With global=True, operator should be OR."""
        sid = uuid4()
        mock_store.perform_query.return_value = []
        t = get_facts_tool(sid, knowledge_store=mock_store)
        t.invoke(with_global=True)

        filters = mock_store.perform_query.call_args.kwargs["filters"]
        assert filters["operator"] == "OR"


# ---------------------------------------------------------------------------
# get_relevant_facts_tool
# ---------------------------------------------------------------------------

class TestGetRelevantFactsTool:
    """Tests for the get_relevant_facts_tool factory."""

    def test_returns_tool(self):
        t = get_relevant_facts_tool(uuid4(), knowledge_store=MagicMock(), embedder=lambda: MagicMock())
        assert isinstance(t, Tool)

    def test_tool_name(self):
        t = get_relevant_facts_tool(uuid4(), knowledge_store=MagicMock(), embedder=lambda: MagicMock())
        assert t.name == "get_relevant_facts"

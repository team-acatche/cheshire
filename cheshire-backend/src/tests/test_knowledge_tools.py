"""Tests for tools.knowledge — upsert_fact, get_facts, get_relevant_facts."""

from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from haystack import Document
from haystack.tools import Tool

from tools.knowledge import (
    KnowledgeState,
    upsert_fact,
    get_facts,
    get_relevant_facts,
    upsert_fact_tool,
    get_facts_tool,
    get_relevant_facts_tool,
    current_knowledge_state,
)
from knowledge_base.repository import KnowledgeRepository


# ---------------------------------------------------------------------------
# upsert_fact
# ---------------------------------------------------------------------------

class TestUpsertFact:
    """Tests for upsert_fact."""

    @pytest.fixture
    def mock_state(self):
        state = MagicMock(spec=KnowledgeState)
        state.session_id = uuid4()
        state.knowledge_base = MagicMock(spec=KnowledgeRepository)
        state.similarity_threshold = 0.35
        token = current_knowledge_state.set(state)
        yield state
        current_knowledge_state.reset(token)

    def test_is_tool(self):
        assert isinstance(upsert_fact_tool, Tool)

    def test_tool_name(self):
        assert upsert_fact_tool.name == "upsert_fact"

    def test_new_fact_generates_uuid_id(self, mock_state):
        """New facts should get a UUID as their Document.id (not in meta)."""
        mock_state.knowledge_base.search.return_value = []
        
        upsert_fact(facts=["The sky is blue"])

        save_call = mock_state.knowledge_base.save.call_args
        docs = save_call.args[0] if save_call.args else save_call.kwargs.get("documents", [])
        assert len(docs) == 1
        doc = docs[0]
        # id should be a valid UUID string
        UUID(doc.id)  # raises if not valid
        assert "knowledge_id" not in doc.meta
        assert doc.meta["session_id"] == str(mock_state.session_id)
        assert doc.meta["is_global"] is False

    def test_incorrect_fact_lookup_uses_id_field(self, mock_state):
        """When incorrect_fact_knowledge_id is given, the filter should use 'id'."""
        existing = Document(id="abc-123", content="old", meta={"last_modified": "x"})
        mock_state.knowledge_base.query.return_value = [existing]

        upsert_fact(facts=["corrected fact"], incorrect_fact_knowledge_id="abc-123")

        call_kwargs = mock_state.knowledge_base.query.call_args
        filters = call_kwargs.kwargs.get("filters") or call_kwargs[1]["filters"]
        assert filters["field"] == "id"
        assert filters["value"] == "abc-123"

    def test_incorrect_fact_not_found_returns_message(self, mock_state):
        """If the incorrect fact is not found, return a descriptive message."""
        mock_state.knowledge_base.query.return_value = []
        
        result = upsert_fact(facts=["corrected"], incorrect_fact_knowledge_id="nonexistent-id")
        assert "not found" in result["result"].lower()

    def test_returns_count_summary(self, mock_state):
        """Result should include counts of added and updated facts."""
        mock_state.knowledge_base.search.return_value = []
        
        result = upsert_fact(facts=["fact1", "fact2"])
        assert "2" in result["result"]
        assert "added" in result["result"].lower()


# ---------------------------------------------------------------------------
# get_facts
# ---------------------------------------------------------------------------

class TestGetFacts:
    """Tests for get_facts."""

    @pytest.fixture
    def mock_state(self):
        state = MagicMock(spec=KnowledgeState)
        state.session_id = uuid4()
        state.knowledge_base = MagicMock(spec=KnowledgeRepository)
        token = current_knowledge_state.set(state)
        yield state
        current_knowledge_state.reset(token)

    def test_is_tool(self):
        assert isinstance(get_facts_tool, Tool)

    def test_tool_name(self):
        assert get_facts_tool.name == "get_facts"

    def test_session_filter_without_global(self, mock_state):
        """Without global, operator should be AND."""
        mock_state.knowledge_base.query.return_value = []
        get_facts(with_global=False)

        filters = mock_state.knowledge_base.query.call_args.kwargs["filters"]
        assert filters["operator"] == "AND"
        conditions = filters["conditions"]
        session_cond = next(c for c in conditions if c["field"] == "meta.session_id")
        assert session_cond["value"] == str(mock_state.session_id)

    def test_session_filter_with_global(self, mock_state):
        """With global=True, operator should be OR."""
        mock_state.knowledge_base.query.return_value = []
        get_facts(with_global=True)

        filters = mock_state.knowledge_base.query.call_args.kwargs["filters"]
        assert filters["operator"] == "OR"


# ---------------------------------------------------------------------------
# get_relevant_facts
# ---------------------------------------------------------------------------

class TestGetRelevantFacts:
    """Tests for get_relevant_facts."""

    @pytest.fixture
    def mock_state(self):
        state = MagicMock(spec=KnowledgeState)
        state.knowledge_base = MagicMock(spec=KnowledgeRepository)
        token = current_knowledge_state.set(state)
        yield state
        current_knowledge_state.reset(token)

    def test_is_tool(self):
        assert isinstance(get_relevant_facts_tool, Tool)

    def test_tool_name(self):
        assert get_relevant_facts_tool.name == "get_relevant_facts"

    def test_queries_retriever(self, mock_state):
        mock_state.knowledge_base.search.return_value = []
        get_relevant_facts(query="test query")
        mock_state.knowledge_base.search.assert_called_with(query="test query")

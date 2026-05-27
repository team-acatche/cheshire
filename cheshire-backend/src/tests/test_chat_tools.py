"""Tests for tools.chat_tools — read_vulnerabilities_from_event_store_tool."""

from unittest.mock import MagicMock
import pytest
from haystack.dataclasses import Document
from haystack.tools import Tool
from tools.chat_tools import read_vulnerabilities_from_event_store
from tools.knowledge import KnowledgeState, current_knowledge_state
from knowledge_base.repository import KnowledgeRepository
from knowledge_base.history import EventType

read_vulnerabilities_from_event_store_tool = read_vulnerabilities_from_event_store

class TestReadVulnerabilitiesTool:

    @pytest.fixture
    def mock_state(self):
        state = MagicMock(spec=KnowledgeState)
        state.event_store = MagicMock(spec=KnowledgeRepository)
        token = current_knowledge_state.set(state)
        yield state
        current_knowledge_state.reset(token)

    def test_is_tool(self):
        assert isinstance(read_vulnerabilities_from_event_store_tool, Tool)

    def test_tool_name(self):
        assert read_vulnerabilities_from_event_store_tool.name == "read_vulnerabilities_from_event_store"

    def test_queries_with_vulnerability_filter(self, mock_state):
        mock_state.event_store.query.return_value = []
        read_vulnerabilities_from_event_store.invoke(confirm=True)
        
        call_kwargs = mock_state.event_store.query.call_args
        filters = call_kwargs.kwargs.get("filters") or call_kwargs[1]["filters"]
        assert filters["field"] == "meta.event_type"
        assert filters["operator"] == "=="
        assert filters["value"] == EventType.VULNERABILITY_FINDING

    def test_returns_documents(self, mock_state):
        docs = [Document(content="XSS")]
        mock_state.event_store.query.return_value = docs
        res = read_vulnerabilities_from_event_store.invoke(confirm=True)
        assert res["findings"] == docs

    def test_returns_empty_when_no_findings(self, mock_state):
        mock_state.event_store.query.return_value = []
        res = read_vulnerabilities_from_event_store.invoke(confirm=True)
        assert isinstance(res, dict)
        assert res["findings"] == []

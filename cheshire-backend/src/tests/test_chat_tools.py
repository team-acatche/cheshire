"""Tests for tools.chat_tools — read_vulnerabilities_from_event_store_tool."""

from unittest.mock import MagicMock
import pytest
from haystack.dataclasses import Document
from haystack.tools import Tool
from knowledge_base.history import EventType
from tools.chat_tools import read_vulnerabilities_from_event_store_tool


class TestReadVulnerabilitiesTool:

    @pytest.fixture
    def mock_store(self):
        return MagicMock()

    def test_returns_tool(self, mock_store):
        assert isinstance(read_vulnerabilities_from_event_store_tool(mock_store), Tool)

    def test_tool_name(self, mock_store):
        t = read_vulnerabilities_from_event_store_tool(mock_store)
        assert t.name == "read_vulnerabilities"

    def test_queries_with_vulnerability_filter(self, mock_store):
        mock_store.perform_query.return_value = []
        t = read_vulnerabilities_from_event_store_tool(mock_store)
        t.invoke()
        filters = mock_store.perform_query.call_args.kwargs.get("filters") or mock_store.perform_query.call_args[1]["filters"]
        assert filters["field"] == "meta.event_type"
        assert filters["operator"] == "=="
        assert filters["value"] == EventType.VULNERABILITY_FINDING

    def test_returns_documents(self, mock_store):
        docs = [Document(content="XSS"), Document(content="SQLi")]
        mock_store.perform_query.return_value = docs
        t = read_vulnerabilities_from_event_store_tool(mock_store)
        assert t.invoke()["documents"] == docs

    def test_returns_empty_when_no_findings(self, mock_store):
        mock_store.perform_query.return_value = []
        t = read_vulnerabilities_from_event_store_tool(mock_store)
        assert t.invoke()["documents"] == []

    def test_closure_captures_own_store(self):
        a, b = MagicMock(), MagicMock()
        a.perform_query.return_value = []
        b.perform_query.return_value = []
        ta = read_vulnerabilities_from_event_store_tool(a)
        tb = read_vulnerabilities_from_event_store_tool(b)
        ta.invoke()
        tb.invoke()
        a.perform_query.assert_called_once()
        b.perform_query.assert_called_once()

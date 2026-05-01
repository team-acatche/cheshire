"""Tests for endpoints.helpers — ChatStore and get_or_create_vector_stores."""

import asyncio
from unittest.mock import MagicMock

import pytest
from endpoints.helpers import ChatStore, get_or_create_vector_stores
from lancedb_haystack import LanceDBDocumentStore  # type: ignore


class TestChatStore:
    """Tests for the ChatStore frozen dataclass."""

    def test_stores_attributes(self):
        es = MagicMock(spec=LanceDBDocumentStore)
        ks = MagicMock(spec=LanceDBDocumentStore)
        store = ChatStore(event_store=es, knowledge_store=ks)
        assert store.event_store is es
        assert store.knowledge_store is ks

    def test_frozen(self):
        store = ChatStore(event_store=MagicMock(), knowledge_store=MagicMock())
        with pytest.raises(AttributeError):
            store.event_store = MagicMock()  # type: ignore


def _run(coro):
    return asyncio.run(coro)


class TestGetOrCreateVectorStores:
    """Tests for the get_or_create_vector_stores async factory."""

    def test_returns_chat_store(self, tmp_path):
        result = _run(get_or_create_vector_stores(tmp_path, username="u"))
        assert isinstance(result, ChatStore)
        assert isinstance(result.event_store, LanceDBDocumentStore)
        assert isinstance(result.knowledge_store, LanceDBDocumentStore)

    def test_event_store_uses_events_table(self, tmp_path):
        result = _run(get_or_create_vector_stores(tmp_path, username="u"))
        assert result.event_store._table_name == "events"

    def test_knowledge_store_uses_facts_table(self, tmp_path):
        result = _run(get_or_create_vector_stores(tmp_path, username="u"))
        assert result.knowledge_store._table_name == "facts"

    def test_custom_dimensions(self, tmp_path):
        result = _run(get_or_create_vector_stores(tmp_path, username="u", dimensions=768))
        assert result.event_store._embedding_dims == 768
        assert result.knowledge_store._embedding_dims == 768

    def test_default_dimensions_384(self, tmp_path):
        result = _run(get_or_create_vector_stores(tmp_path, username="u"))
        assert result.event_store._embedding_dims == 384
        assert result.knowledge_store._embedding_dims == 384

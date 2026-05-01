"""Tests for HistoryRepositories and updated StreamCallbackFactory."""

import sqlite3
from dataclasses import replace
from unittest.mock import MagicMock, call
from uuid import uuid4

import pytest
from haystack.dataclasses import StreamingChunk

from knowledge_base.history import (
    Event,
    EventType,
    HistoryRepositories,
    SqliteEventRepository,
    StreamCallbackFactory,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def sqlite_repo(db_conn):
    return SqliteEventRepository(db_conn)


@pytest.fixture
def mock_vector_store():
    return MagicMock()


# ---------------------------------------------------------------------------
# HistoryRepositories
# ---------------------------------------------------------------------------

class TestHistoryRepositories:
    """Tests for the new HistoryRepositories composite dataclass."""

    def test_save_delegates_to_repo(self, sqlite_repo, mock_vector_store):
        """save() should call repo.save with the event."""
        history = HistoryRepositories(repo=sqlite_repo, vector_store=mock_vector_store)
        event = Event(
            event_id=1,
            session_id="s1",
            event_type=EventType.USER_MESSAGE,
            content="hello",
        )
        history.save(event)

        # Verify event was persisted in SQLite
        recent = sqlite_repo.get_recent("s1", 10)
        assert len(recent) == 1
        assert recent[0].content == "hello"

    def test_save_writes_to_vector_store_when_present(self, sqlite_repo, mock_vector_store):
        """When vector_store is set, save() should also call write_documents."""
        history = HistoryRepositories(repo=sqlite_repo, vector_store=mock_vector_store)
        event = Event(
            event_id=1,
            session_id="s1",
            event_type=EventType.USER_MESSAGE,
            content="hello",
        )
        history.save(event)
        mock_vector_store.write_documents.assert_called_once()

    def test_save_skips_vector_store_when_none(self, sqlite_repo):
        """When vector_store is None, save() should only persist to the repo."""
        history = HistoryRepositories(repo=sqlite_repo, vector_store=None)
        event = Event(
            event_id=1,
            session_id="s1",
            event_type=EventType.USER_MESSAGE,
            content="hello",
        )
        history.save(event)

        recent = sqlite_repo.get_recent("s1", 10)
        assert len(recent) == 1

    def test_default_vector_store_is_none(self, sqlite_repo):
        """vector_store should default to None."""
        history = HistoryRepositories(repo=sqlite_repo)
        assert history.vector_store is None

    def test_frozen_dataclass(self, sqlite_repo):
        """HistoryRepositories is frozen — attribute assignment should raise."""
        history = HistoryRepositories(repo=sqlite_repo)
        with pytest.raises(AttributeError):
            history.repo = MagicMock()  # type: ignore

    def test_vector_store_receives_document_from_event(self, sqlite_repo, mock_vector_store):
        """The document passed to write_documents should match event.to_document()."""
        history = HistoryRepositories(repo=sqlite_repo, vector_store=mock_vector_store)
        event = Event(
            event_id=7,
            session_id="s1",
            event_type=EventType.RESPONSE,
            content="some response",
            timestamp="2024-01-01 00:00:00",
        )
        history.save(event)

        written_docs = mock_vector_store.write_documents.call_args[0][0]
        assert isinstance(written_docs, list)
        assert len(written_docs) == 1
        expected_doc = event.to_document()
        assert written_docs[0].id == expected_doc.id
        assert written_docs[0].content == expected_doc.content


# ---------------------------------------------------------------------------
# StreamCallbackFactory (updated to use HistoryRepositories)
# ---------------------------------------------------------------------------

class TestStreamCallbackFactory:
    """Tests for StreamCallbackFactory now wired to HistoryRepositories."""

    def _make_factory(self, sqlite_repo, mock_vector_store=None):
        history = HistoryRepositories(repo=sqlite_repo, vector_store=mock_vector_store)
        return StreamCallbackFactory(session_id=str(uuid4()), history=history)

    def test_accepts_history_repositories(self, sqlite_repo, mock_vector_store):
        """StreamCallbackFactory should accept HistoryRepositories for its history param."""
        factory = self._make_factory(sqlite_repo, mock_vector_store)
        assert isinstance(factory.history, HistoryRepositories)

    def test_flush_saves_current_event(self, sqlite_repo):
        """flush() should persist the current_event through HistoryRepositories.save."""
        factory = self._make_factory(sqlite_repo)
        # Simulate a buffered event
        factory.current_event = Event(
            session_id=str(factory.session_id),
            event_type=EventType.RESPONSE,
            content="partial content",
        )
        factory.flush()

        assert factory.current_event is None
        events = sqlite_repo.get_recent(str(factory.session_id), 10)
        assert len(events) == 1
        assert events[0].content == "partial content"

    def test_flush_noop_when_no_current_event(self, sqlite_repo):
        """flush() with no current_event should do nothing."""
        factory = self._make_factory(sqlite_repo)
        factory.flush()  # Should not raise
        assert factory.current_event is None

    def test_callback_accumulates_content_chunks(self, sqlite_repo):
        """Normal content streaming should accumulate into current_event."""
        factory = self._make_factory(sqlite_repo)
        callback = factory()

        callback(StreamingChunk(content="Hello "))
        assert factory.current_event is not None
        assert factory.current_event.content == "Hello "

        callback(StreamingChunk(content="World"))
        assert factory.current_event.content == "Hello World"

    def test_callback_saves_on_finish_reason(self, sqlite_repo):
        """When a chunk has finish_reason and there's a current_event, it should be saved."""
        factory = self._make_factory(sqlite_repo)
        callback = factory()

        callback(StreamingChunk(content="response text"))
        assert factory.current_event is not None

        callback(StreamingChunk(content="", finish_reason="stop"))
        assert factory.current_event is None

        events = sqlite_repo.get_recent(str(factory.session_id), 10)
        assert len(events) == 1

    def test_callback_saves_tool_call_result(self, sqlite_repo):
        """Tool call results should be saved as TOOL_CALL_RESULT events."""
        factory = self._make_factory(sqlite_repo)
        callback = factory()

        mock_result = MagicMock()
        mock_result.result = "tool output data"
        callback(StreamingChunk(content="", tool_call_result=mock_result, index=0))

        events = sqlite_repo.get_recent(str(factory.session_id), 10)
        assert len(events) == 1
        assert events[0].event_type == EventType.TOOL_CALL_RESULT
        assert events[0].content == "tool output data"

    def test_callback_handles_tool_calls(self, sqlite_repo):
        """Tool call chunks should create and immediately save a TOOL_CALL event."""
        factory = self._make_factory(sqlite_repo)
        callback = factory()

        mock_tool_call = MagicMock()
        mock_tool_call.tool_name = "get_facts"
        mock_tool_call.arguments = '{"with_global": true}'

        callback(StreamingChunk(content="", tool_calls=[mock_tool_call], index=0))

        events = sqlite_repo.get_recent(str(factory.session_id), 10)
        assert len(events) == 1
        assert events[0].event_type == EventType.TOOL_CALL
        assert "get_facts" in events[0].content

    def test_flush_also_writes_to_vector_store(self, sqlite_repo, mock_vector_store):
        """flush() should propagate to the vector store via HistoryRepositories."""
        factory = self._make_factory(sqlite_repo, mock_vector_store)
        factory.current_event = Event(
            event_id=1,
            session_id=str(factory.session_id),
            event_type=EventType.RESPONSE,
            content="buffered",
        )
        factory.flush()
        mock_vector_store.write_documents.assert_called_once()

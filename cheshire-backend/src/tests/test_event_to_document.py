"""Tests for Event.to_document() — new method added to Event dataclass."""

import pytest
from haystack.dataclasses import Document

from knowledge_base.history import Event, EventType


class TestEventToDocument:
    """Validates the Event → Haystack Document conversion."""

    def test_basic_conversion(self):
        """A fully populated Event converts into a Document with correct id, content, and meta."""
        event = Event(
            event_id=42,
            session_id="sess-abc",
            event_type=EventType.VULNERABILITY_FINDING,
            content="SQL injection found",
            timestamp="2024-06-01 12:00:00",
            ref_event_id=10,
        )
        doc = event.to_document()

        assert isinstance(doc, Document)
        assert doc.id == "42"
        assert doc.content == "SQL injection found"
        assert doc.meta["session_id"] == "sess-abc"
        assert doc.meta["event_type"] == EventType.VULNERABILITY_FINDING.value
        assert doc.meta["ref_event_id"] == "10"
        assert doc.meta["timestamp"] == "2024-06-01 12:00:00"

    def test_meta_contains_all_expected_keys(self):
        """The meta dict should contain exactly these four keys."""
        event = Event(
            event_id=1,
            session_id="s1",
            event_type=EventType.USER_MESSAGE,
            content="hi",
        )
        doc = event.to_document()
        assert set(doc.meta.keys()) == {"session_id", "event_type", "ref_event_id", "timestamp"}

    def test_ref_event_id_none_when_unset(self):
        """When ref_event_id is not set on the Event, meta should carry None."""
        event = Event(
            event_id=5,
            session_id="s1",
            event_type=EventType.RESPONSE,
            content="reply",
        )
        doc = event.to_document()
        assert doc.meta["ref_event_id"] == ""

    def test_timestamp_none_when_unset(self):
        """When timestamp is not set on the Event, meta should carry None."""
        event = Event(
            event_id=5,
            session_id="s1",
            event_type=EventType.RESPONSE,
            content="reply",
        )
        doc = event.to_document()
        assert isinstance(doc.meta["timestamp"], str)
        assert len(doc.meta["timestamp"]) > 0

    def test_event_id_is_stringified(self):
        """Document.id must be a string representation of event_id."""
        event = Event(
            event_id=999,
            session_id="s1",
            event_type=EventType.TOOL_CALL,
            content="call",
        )
        doc = event.to_document()
        assert doc.id == "999"
        assert isinstance(doc.id, str)

    def test_empty_content_preserved(self):
        """An event with empty content should produce a Document with empty content."""
        event = Event(
            event_id=1,
            session_id="s1",
            event_type=EventType.RESPONSE,
            content="",
        )
        doc = event.to_document()
        assert doc.content == ""

    def test_asserts_on_none_event_id(self):
        """to_document() should raise AssertionError when event_id is None."""
        event = Event(
            session_id="s1",
            event_type=EventType.USER_MESSAGE,
            content="unsaved event",
        )
        with pytest.raises(AssertionError, match="should have an ID"):
            event.to_document()

    def test_all_event_types_convert(self):
        """Every EventType should be representable in a Document."""
        for event_type in EventType:
            event = Event(
                event_id=1,
                session_id="s1",
                event_type=event_type,
                content="test",
            )
            doc = event.to_document()
            assert doc.meta["event_type"] == event_type.value

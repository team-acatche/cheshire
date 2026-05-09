from dataclasses import dataclass, replace, field
from datetime import datetime
from enum import StrEnum
from typing import Callable, Optional, Annotated, Protocol
import os
import re
import sqlite3 as sqlite
from uuid import UUID

from haystack.dataclasses import StreamingCallbackT, StreamingChunk, ChatMessage, Document
from lancedb_haystack import LanceDBDocumentStore # type: ignore

class EventType(StrEnum):
    VULNERABILITY_FINDING = "vulnerability_finding"
    USER_MESSAGE = "user_message"
    TOOL_CALL = "tool_call"
    TOOL_CALL_RESULT = "tool_call_result"
    RESPONSE = "response"

@dataclass(frozen=True, kw_only=True)
class Event:
    session_id: Annotated[str, "the session id"]
    event_type: Annotated[EventType, "the event type"]

    event_id: Annotated[Optional[int], "the event id"] = None # None on insert
    content: Annotated[str, "the event content"] = ""
    timestamp: Annotated[str, "the event timestamp"] = field(default_factory=lambda: datetime.now().isoformat())
    ref_event_id: Annotated[Optional[int], "the reference event id"] = None

    def to_insert_tuple(self) -> tuple:
        initial = [
            self.session_id,
            self.event_type.value,
            self.content,
        ]
        if self.timestamp is not None:
            initial.append(self.timestamp)
        if self.ref_event_id is not None:
            initial.append(str(self.ref_event_id))
        return tuple(initial)
    
    @staticmethod
    def from_row(row: tuple) -> "Event":
        return Event(
            event_id=row[0],
            session_id=row[1],
            event_type=EventType(row[2]),
            content=row[3],
            timestamp=row[4],
            ref_event_id=row[5] if len(row) > 5 else None
        )
    
    def to_chat_message(self) -> ChatMessage:
        if self.event_type == EventType.USER_MESSAGE:
            return ChatMessage.from_user(str(self.content))
        return ChatMessage.from_assistant(str(self.content))
    
    def to_document(self) -> Document:
        assert self.event_id is not None, "The event being embedded should have an ID"
        meta = {
            "session_id": self.session_id,
            "event_type": self.event_type.value if isinstance(self.event_type, EventType) else self.event_type,
            "ref_event_id": str(self.ref_event_id) if self.ref_event_id is not None else "",
            "timestamp": self.timestamp if self.timestamp is not None else datetime.now().isoformat(),
        }

        return Document(
            id=str(self.event_id),
            content=self.content,
            meta=meta
        )

class EventRepository(Protocol):
    def save(self, event: Event) -> Event:
        """Saves an event to the repository and returns the saved event with its ID."""
        ...
    
    def get_recent(self, session_id: str, k: int = 1000, *, event_types: Optional[list[EventType]] = None) -> list[Event]:
        """Returns the last k events of type event_types (inclusive)."""
        ...
    
    def get_event(self, event_id: int) -> Optional[Event]:
        """Returns the event with the given id."""
        ...
    
    def delete_messages_from_session(self, session_id: str):
        """Deletes all messages from a session."""
        ...

    def get_last_event_timestamp(self, session_id: str) -> Optional[str]:
        """Returns the timestamp of the last event for the given session."""
        ...

class SqliteEventRepository(EventRepository):
    def __init__(self, history: sqlite.Connection):
        self.history = history
        self.cursor = history.cursor()

        # initialize events table
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS event (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES session(session_id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL,
            ref_event_id INTEGER REFERENCES event(event_id) ON DELETE SET NULL
        )""")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_event_session_id ON event(session_id)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_event_event_type ON event(event_type)")

        self.history.commit()

    def save(self, event: Event) -> Event:
        """Saves an event to the repository and returns the saved event with its ID."""
        values: list[str] = ["session_id", "event_type", "content"]
        if event.timestamp is not None:
            values.append("timestamp")
        if event.ref_event_id is not None:
            values.append("ref_event_id")

        values_str = f"({', '.join(values)})"
        placeholders = f"({', '.join(['?' for _ in values])})"

        self.cursor.execute(f"INSERT INTO event {values_str} VALUES {placeholders} RETURNING event_id, timestamp", event.to_insert_tuple())
        row = self.cursor.fetchone()
        event_id = row[0]
        timestamp = row[1]
        self.history.commit()
        return replace(event, event_id=event_id, timestamp=timestamp)
    
    def get_recent(self, session_id: str, k: int = 1000, *, event_types: Optional[list[EventType]] = None) -> list[Event]:
        """Returns the last k events."""
        if event_types is None or len(event_types) == 0:
            self.cursor.execute("SELECT * FROM event WHERE session_id = ? ORDER BY event_id DESC LIMIT ?", (session_id, k))
        else:
            self.cursor.execute(
                f"SELECT * FROM event WHERE session_id = ? AND event_type IN ({','.join(['?'] * len(event_types))}) ORDER BY event_id DESC LIMIT ?",
                (session_id, *[e.value for e in event_types], k)
            )
        return [Event.from_row(row) for row in self.cursor.fetchall()]
    
    def get_last_event_timestamp(self, session_id: str) -> Optional[str]:
        """Returns the timestamp of the last event for the given session."""
        self.cursor.execute("SELECT MAX(timestamp) FROM event WHERE session_id = ?", (session_id,))
        if (row := self.cursor.fetchone()) is not None:
            return row[0]
        return None
    
    def get_event(self, event_id: int) -> Optional[Event]:
        self.cursor.execute("SELECT * FROM event WHERE event_id = ? LIMIT 1", (event_id,))
        if (row := self.cursor.fetchone()) is not None:
            return Event.from_row(row)
        return None
    
    def delete_messages_from_session(self, session_id: str):
        """Deletes all messages from a given session."""
        self.cursor.execute("DELETE FROM event WHERE session_id = ?", (session_id,))
        self.history.commit()
    
@dataclass(frozen=True, kw_only=True)
class HistoryRepositories:
    repo: Annotated[EventRepository, "the event repository"]
    vector_store: Annotated[Optional[LanceDBDocumentStore], "the event repository with embeddings"] = field(default=None)

    def save(self, event: Event) -> Event:
        saved_event = self.repo.save(event)
        if self.vector_store is not None:
            self.vector_store.write_documents([saved_event.to_document()])
        return saved_event
    
@dataclass(kw_only=True)
class StreamCallbackFactory:
    session_id: Annotated[UUID | str, "the session id"]
    history: Annotated[HistoryRepositories, "the event repository (both DB and Vector Stores)"]
    current_event: Annotated[Optional[Event], "the current event"] = field(init=False, default=None)

    def flush(self) -> None:
        if self.current_event is not None:
            self.history.save(self.current_event)
            self.current_event = None

    def __call__(factory, chunk: StreamingChunk) -> None:
        # save to db if this current chunk is a new content block and event is previously set
        if chunk.finish_reason and factory.current_event is not None:
            factory.history.save(factory.current_event)
            factory.current_event = None

        ## Tool Call streaming
        if chunk.tool_calls:
            # Typically, if there are multiple tool calls in the chunk this means that the tool calls are fully formed and
            # not just a delta.
            factory.current_event = Event(
                session_id=str(factory.session_id),
                event_type=EventType.TOOL_CALL,
            )
            content_string = ""

            for tool_call in chunk.tool_calls:
                content_string = f"Tool: {tool_call.tool_name}\nArguments: "
                if tool_call.arguments:
                    content_string += tool_call.arguments

            assert len(content_string) > 0
            factory.history.save(replace(factory.current_event, content=content_string))
            factory.current_event = None

        ## Tool Call Result streaming
        if chunk.tool_call_result:
            factory.history.save(Event(
                session_id=str(factory.session_id),
                event_type=EventType.TOOL_CALL_RESULT,
                content=str(chunk.tool_call_result.result),
            ))

        ## Normal content streaming
        if chunk.content:
            if factory.current_event is None:
                factory.current_event = Event(
                    session_id=str(factory.session_id),
                    event_type=EventType.RESPONSE
                )
            factory.current_event = replace(factory.current_event, content=factory.current_event.content+chunk.content)

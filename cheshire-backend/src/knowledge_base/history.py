from dataclasses import dataclass, replace, field
from datetime import datetime
from enum import StrEnum
from typing import Callable, Optional, Annotated, Protocol
import os
import re
import sqlite3 as sqlite
from uuid import UUID

from haystack.dataclasses import StreamingCallbackT, StreamingChunk, ChatMessage

class EventType(StrEnum):
    USER_MESSAGE = "user_message"
    TOOL_CALL = "tool_call"
    TOOL_CALL_RESULT = "tool_call_result"
    REASONING = "reasoning"
    RESPONSE = "response"

@dataclass(frozen=True, kw_only=True)
class Event:
    session_id: Annotated[str, "the session id"]
    event_type: Annotated[EventType, "the event type"]

    event_id: Annotated[Optional[int], "the event id"] = None # None on insert
    content: Annotated[str, "the event content"] = ""
    timestamp: Annotated[Optional[str], "the event timestamp"] = None
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
        elif self.event_type == EventType.RESPONSE:
            return ChatMessage.from_assistant(str(self.content))
        elif self.event_type == EventType.REASONING:
            # Reasoning is not technically a role in ChatMessage, 
            # but for context we might treat it as assistant if needed 
            # or just skip. For now, we skip non-user/assistant for context.
            return ChatMessage.from_assistant(str(self.content))
        else:
            # Fallback
            return ChatMessage.from_assistant(str(self.content))

class EventRepository(Protocol):
    def save(self, event: Event) -> None:
        """Saves an event to the repository."""
        ...
    
    def get_recent(self, session_id: str, k: int) -> list[Event]:
        """Returns the last k events."""
        ...
    
    def get_event(self, event_id: int) -> Optional[Event]:
        """Returns the event with the given id."""
        ...
    
class SqliteEventRepository(EventRepository):
    def __init__(self, history: sqlite.Connection):
        self.history = history
        self.cursor = history.cursor()

        # initialize events table
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS event (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL,
            ref_event_id INTEGER REFERENCES event(event_id)
        )""")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_event_session_id ON event(session_id)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_event_event_type ON event(event_type)")

        self.history.commit()

    def save(self, event: Event) -> None:
        """Saves an event to the repository."""
        values: list[str] = ["session_id", "event_type", "content"]
        if event.timestamp is not None:
            values.append("timestamp")
        if event.ref_event_id is not None:
            values.append("ref_event_id")

        values_str = f"({', '.join(values)})"
        placeholders = f"({', '.join(['?' for _ in values])})"

        self.cursor.execute(f"INSERT INTO event {values_str} VALUES {placeholders}", event.to_insert_tuple())
        self.history.commit()
    
    def get_recent(self, session_id: str, k: int, *, event_types: Optional[list[EventType]] = None) -> list[Event]:
        """Returns the last k events."""
        if event_types is None:
            self.cursor.execute("SELECT * FROM event WHERE session_id = ? ORDER BY event_id DESC LIMIT ?", (session_id, k))
        else:
            self.cursor.execute(
                f"SELECT * FROM event WHERE session_id = ? AND event_type IN ({','.join(['?'] * len(event_types))}) ORDER BY event_id DESC LIMIT ?",
                (session_id, *[e.value for e in event_types], k)
            )
        return [Event.from_row(row) for row in self.cursor.fetchall()]
    
    def get_event(self, event_id: int) -> Optional[Event]:
        self.cursor.execute("SELECT * FROM event WHERE event_id = ? LIMIT 1", (event_id,))
        if (row := self.cursor.fetchone()) is not None:
            return Event.from_row(row)
        return None
    
@dataclass(kw_only=True)
class StreamCallbackFactory:
    session_id: Annotated[UUID | str, "the session id"]
    history: Annotated[EventRepository, "the event repository"]
    current_event: Annotated[Optional[Event], "the current event"] = field(init=False, default=None)

    def __call__(self) -> StreamingCallbackT:
        def _callback(chunk: StreamingChunk) -> None:
            # save to db if this current chunk is a new content block and event is previously set
            if chunk.start and self.current_event is not None:
                self.history.save(self.current_event)
                self.current_event = None

            ## Tool Call streaming
            if chunk.tool_calls:
                # Typically, if there are multiple tool calls in the chunk this means that the tool calls are fully formed and
                # not just a delta.
                self.current_event = Event(
                    session_id=str(self.session_id),
                    event_type=EventType.TOOL_CALL,
                )
                content_string = ""

                for tool_call in chunk.tool_calls:
                    content_string = f"Tool: {tool_call.tool_name}\nArguments: "
                if tool_call.arguments:
                    content_string += tool_call.arguments

                assert len(content_string) > 0
                self.history.save(replace(self.current_event, content=content_string))
                self.current_event = None

            ## Tool Call Result streaming
            if chunk.tool_call_result:
                self.history.save(Event(
                    session_id=str(self.session_id),
                    event_type=EventType.TOOL_CALL_RESULT,
                    content=str(chunk.tool_call_result.result),
                ))

            ## Normal content streaming
            if chunk.content:
                if chunk.start or self.current_event is None:
                    self.current_event = Event(
                        session_id=str(self.session_id),
                        event_type=EventType.RESPONSE
                    )
                self.current_event = replace(self.current_event, content=self.current_event.content+chunk.content)

            ## Reasoning content streaming
            if chunk.reasoning:
                if chunk.start or self.current_event is None:
                    self.current_event = Event(
                        session_id=str(self.session_id),
                        event_type=EventType.REASONING
                    )
                self.current_event = replace(self.current_event, content=self.current_event.content+str(chunk.reasoning))

        return _callback

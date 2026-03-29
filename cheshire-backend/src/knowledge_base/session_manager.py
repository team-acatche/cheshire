from dataclasses import dataclass, replace, field
from datetime import datetime
from enum import StrEnum
from typing import Callable, Optional, Annotated, Protocol
import os
import sqlite3 as sqlite
import uuid

from haystack.dataclasses import StreamingCallbackT, StreamingChunk

@dataclass(frozen=True, kw_only=True)
class Session:
    session_id: Annotated[str, "the session id"] = field(default_factory=lambda: str(uuid.uuid4()))
    title: Annotated[str, "the session title"] = ""

    def to_insert_tuple(self) -> tuple:
        return (self.session_id, self.title,)
    
    @staticmethod
    def from_row(row: tuple) -> "Session":
        return Session(session_id=row[0], title=row[1],)

class SessionRepository(Protocol):
    def get_sessions(self) -> list[Session]:
        """Returns all sessions."""
        ...
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Returns the session with the given id."""
        ...
    
    def get_session_with_title(self, title: str) -> Optional[Session]:
        """Returns the session with the given title."""
        ...
    
    def save_new_session(self, session: Session) -> None:
        """Saves a session to the repository."""
        ...
    
class SqliteSessionRepository(SessionRepository):
    def __init__(self, sessions_db: sqlite.Connection):
        self.db = sessions_db
        self.cursor = self.db.cursor()

        # initialize events table
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS session (
            session_id TEXT PRIMARY KEY,
            title TEXT DEFAULT '' NOT NULL
        )""")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_title ON session(title)")

        self.db.commit()
    
    def get_sessions(self) -> list[Session]:
        """Returns all sessions."""
        self.cursor.execute("SELECT * FROM session")
        return [Session.from_row(row) for row in self.cursor.fetchall()]

    def get_session(self, session_id: str) -> Optional[Session]:
        """Returns the session with the given id."""
        self.cursor.execute("SELECT * FROM session WHERE session_id = ? LIMIT 1", (session_id,))
        if (row := self.cursor.fetchone()) is not None:
            return Session.from_row(row)
        return None
    
    def get_session_with_title(self, title: str) -> Optional[Session]:
        """Returns the session with the given title."""
        self.cursor.execute("SELECT * FROM session WHERE title = ? LIMIT 1", (title,))
        if (row := self.cursor.fetchone()) is not None:
            return Session.from_row(row)
        return None
    
    def save_new_session(self, session: Session) -> None:
        """Saves a session to the repository."""
        values: list[str] = ["title"]
        if session.session_id is not None:
            values = ["session_id", *values]

        values_str = f"({', '.join(values)})"
        placeholders = f"({', '.join(['?' for _ in values])})"

        self.cursor.execute(f"INSERT INTO session {values_str} VALUES {placeholders}", session.to_insert_tuple())
        self.db.commit()
    
    def change_title(self, session_id: str, *, new_title: str) -> Optional[Session]:
        """Changes the title of a session. Returns the updated session if it exists, None otherwise."""
        self.cursor.execute("UPDATE session SET title = ? WHERE session_id = ? LIMIT 1", (new_title, session_id))
        self.db.commit()
        return self.get_session(session_id)

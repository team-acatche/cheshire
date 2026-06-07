from dataclasses import dataclass, replace, field
from datetime import datetime
from enum import StrEnum
from typing import Callable, Optional, Annotated, Protocol
import os
import sqlite3 as sqlite
import uuid

from haystack.dataclasses import StreamingCallbackT, StreamingChunk


class SessionStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"

@dataclass(frozen=True, kw_only=True)
class Session:
    session_id: Annotated[str, "the session id"] = field(default_factory=lambda: str(uuid.uuid4()))
    title: Annotated[str, "the session title"] = ""
    status: Annotated[str, "evaluation status"] = SessionStatus.DONE
    created_at: Annotated[Optional[str], "creation timestamp"] = None

    def to_insert_tuple(self) -> tuple:
        return (self.session_id, self.title, self.status)
    
    @staticmethod
    def from_row(row: tuple) -> "Session":
        return Session(session_id=row[0], title=row[1], status=row[2] if len(row) > 2 else SessionStatus.DONE, created_at=row[3] if len(row) > 3 else None )

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

    def change_title(self, session_id: str, *, new_title: str) -> Optional[Session]:
        """Changes the title of a session. Returns the updated session if it exists, None otherwise."""
        ...

    def update_status(self, session_id: str, status: SessionStatus) -> Optional[Session]:
        """Changes the status of a session. Returns the updated session if it exists, None otherwise."""
        ...
    
    def delete_session(self, session_id: str):
        """Deletes a session from the repository."""
        ...
    
class SqliteSessionRepository(SessionRepository):
    def __init__(self, sessions_db: sqlite.Connection):
        self.db = sessions_db
        self.cursor = self.db.cursor()

        # initialize events table
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS session (
            session_id TEXT PRIMARY KEY,
            title TEXT DEFAULT '' NOT NULL,
            status TEXT DEFAULT 'done' NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")

        for col, definition in [
            ("status", "TEXT DEFAULT 'done'"),
            ("created_at", "TEXT DEFAULT '1970-01-01 00:00:00'")
        ]:
            try:
                self.cursor.execute(f"ALTER TABLE session ADD COLUMN {col} {definition}")
            except sqlite.OperationalError:
                pass

        self.db.commit()
        self.cursor = self.db.cursor()

        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_title ON session(title)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_status ON session(status)")
        self.db.commit()

        
    
    def get_sessions(self) -> list[Session]:
        """Returns all sessions."""
        self.cursor.execute("SELECT session_id, title, status, created_at FROM session ORDER BY created_at DESC")
        return [Session.from_row(row) for row in self.cursor.fetchall()]

    def get_session(self, session_id: str) -> Optional[Session]:
        """Returns the session with the given id."""
        self.cursor.execute("SELECT session_id, title, status, created_at FROM session WHERE session_id = ? LIMIT 1", (session_id,))
        if (row := self.cursor.fetchone()) is not None:
            return Session.from_row(row)
        return None
    
    def get_session_with_title(self, title: str) -> Optional[Session]:
        """Returns the session with the given title."""
        self.cursor.execute("SELECT session_id, title, status, created_at FROM session WHERE title = ? LIMIT 1", (title,))
        if (row := self.cursor.fetchone()) is not None:
            return Session.from_row(row)
        return None
    
    def save_new_session(self, session: Session) -> None:
        """Saves a session to the repository."""
        self.cursor.execute(f"INSERT INTO session (session_id, title, status) VALUES (?, ?, ?)", (session.session_id, session.title, session.status))
        self.db.commit()
    
    def change_title(self, session_id: str, *, new_title: str) -> Optional[Session]:
        """Changes the title of a session. Returns the updated session if it exists, None otherwise."""
        self.cursor.execute("UPDATE session SET title = ? WHERE session_id = ? RETURNING session_id, title, status, created_at", (new_title, session_id))
        row = self.cursor.fetchone()
        self.db.commit()
        if row is not None:
            return Session.from_row(row)
        return None
    
    def update_status(self, session_id: str, status: SessionStatus) -> Optional[Session]:
        """Update evaluation status. Called by the background worker."""
        self.cursor.execute(
            "UPDATE session SET status = ? WHERE session_id = ? RETURNING session_id, title, status, created_at",
            (status.value, session_id),
        )
        row = self.cursor.fetchone()
        self.db.commit()
        return Session.from_row(row) if row else None
    
    def delete_session(self, session_id: str) -> bool:
        """Deletes a session from the repository."""
        self.cursor.execute("DELETE FROM session WHERE session_id = ?", (session_id,))
        self.db.commit()
        return self.cursor.rowcount > 0

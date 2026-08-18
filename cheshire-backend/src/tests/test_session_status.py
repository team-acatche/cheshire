import sqlite3
import pytest

from knowledge_base.session_manager import Session, SessionStatus, SqliteSessionRepository


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def repo(db_conn):
    return SqliteSessionRepository(db_conn)


class TestSessionStatusPersistence:
    """Status column is persisted and returned correctly."""

    def test_default_status_is_done(self, repo):
        """Sessions created without explicit status default to 'done'."""
        s = Session(title="Test")
        repo.save_new_session(s)
        fetched = repo.get_session(s.session_id)
        assert fetched is not None
        assert fetched.status == SessionStatus.DONE

    def test_save_pending_status(self, repo):
        """A session saved with status=pending round-trips correctly."""
        s = Session(title="Uploading doc", status=SessionStatus.PENDING)
        repo.save_new_session(s)
        fetched = repo.get_session(s.session_id)
        assert fetched is not None
        assert fetched.status == SessionStatus.PENDING

    def test_update_status_to_processing(self, repo):
        """update_status transitions PENDING → PROCESSING."""
        s = Session(title="Doc", status=SessionStatus.PENDING)
        repo.save_new_session(s)

        updated = repo.update_status(s.session_id, SessionStatus.PROCESSING)
        assert updated is not None
        assert updated.status == SessionStatus.PROCESSING

        fetched = repo.get_session(s.session_id)
        assert fetched is not None
        assert fetched.status == SessionStatus.PROCESSING

    def test_update_status_to_done(self, repo):
        """update_status transitions PROCESSING → DONE."""
        s = Session(title="Doc", status=SessionStatus.PROCESSING)
        repo.save_new_session(s)

        updated = repo.update_status(s.session_id, SessionStatus.DONE)
        assert updated is not None
        assert updated.status == SessionStatus.DONE

    def test_update_status_to_failed(self, repo):
        """update_status transitions PROCESSING → FAILED."""
        s = Session(title="Bad doc", status=SessionStatus.PROCESSING)
        repo.save_new_session(s)

        updated = repo.update_status(s.session_id, SessionStatus.FAILED)
        assert updated is not None
        assert updated.status == SessionStatus.FAILED

    def test_update_status_nonexistent_returns_none(self, repo):
        """update_status on a missing session_id returns None (no crash)."""
        result = repo.update_status("does-not-exist", SessionStatus.DONE)
        assert result is None

    def test_get_sessions_includes_status(self, repo):
        """get_sessions returns all sessions with their status fields."""
        s1 = Session(title="S1", status=SessionStatus.DONE)
        s2 = Session(title="S2", status=SessionStatus.PROCESSING)
        s3 = Session(title="S3", status=SessionStatus.FAILED)
        for s in [s1, s2, s3]:
            repo.save_new_session(s)

        all_sessions = repo.get_sessions()
        assert len(all_sessions) == 3

        statuses = {s.session_id: s.status for s in all_sessions}
        assert statuses[s1.session_id] == SessionStatus.DONE
        assert statuses[s2.session_id] == SessionStatus.PROCESSING
        assert statuses[s3.session_id] == SessionStatus.FAILED

    def test_full_lifecycle(self, repo):
        """Simulates the complete evaluation lifecycle status transitions."""
        # 1. Upload starts — session created as PENDING
        s = Session(title="report.pdf", status=SessionStatus.PENDING)
        repo.save_new_session(s)
        assert repo.get_session(s.session_id).status == SessionStatus.PENDING

        # 2. Worker picks it up — transitions to PROCESSING
        repo.update_status(s.session_id, SessionStatus.PROCESSING)
        assert repo.get_session(s.session_id).status == SessionStatus.PROCESSING

        # 3. Worker finishes — transitions to DONE
        repo.update_status(s.session_id, SessionStatus.DONE)
        assert repo.get_session(s.session_id).status == SessionStatus.DONE

    def test_existing_db_migration(self, db_conn):
        """
        SqliteSessionRepository can open an existing DB that lacks the status
        column (simulates upgrading from the old schema).
        """
        # Create the old-style table without status / created_at
        db_conn.execute("""
            CREATE TABLE session (
                session_id TEXT PRIMARY KEY,
                title TEXT DEFAULT '' NOT NULL
            )
        """)
        db_conn.execute(
            "INSERT INTO session (session_id, title) VALUES ('old-id', 'Old session')"
        )
        db_conn.commit()

        # Opening the repo should migrate the schema silently
        repo = SqliteSessionRepository(db_conn)

        # Old row should still be retrievable with a default status
        fetched = repo.get_session("old-id")
        assert fetched is not None
        assert fetched.title == "Old session"
        assert fetched.status == SessionStatus.DONE  # DEFAULT 'done'

        # New sessions can be created with any status
        new_s = Session(title="New doc", status=SessionStatus.PENDING)
        repo.save_new_session(new_s)
        assert repo.get_session(new_s.session_id).status == SessionStatus.PENDING
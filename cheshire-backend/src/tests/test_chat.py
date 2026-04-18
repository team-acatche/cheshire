"""Tests for endpoints.chat – GET /, GET /{session_id}, POST /{session_id}."""

import sqlite3
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from server import api
from cheshire_configs.registry import configs
from cheshire_configs.core import PipelineConfig, Provider, EvaluationType
from auth.dependencies import get_current_user
from auth.models import User
from knowledge_base.history import Event, EventType, SqliteEventRepository
from knowledge_base.session_manager import Session, SqliteSessionRepository

# ---------------------------------------------------------------------------
# Dependency overrides (same pattern as test_document_evaluation)
# ---------------------------------------------------------------------------

mock_config = PipelineConfig(
    model=MagicMock(),
    tools=[],
    mode=EvaluationType.RAG,
)
api.dependency_overrides[configs] = lambda: {Provider.OLLAMA: mock_config}

TEST_USER = User(
    user_id="test_id",
    email="test@example.com",
    sessions_folder="testuser",
    username="testuser",
    full_name="Test User",
    avatar_uri="default.png",
)


def mock_get_current_user():
    return TEST_USER


api.dependency_overrides[get_current_user] = mock_get_current_user

client = TestClient(api)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_session_db(db_path: Path) -> tuple[sqlite3.Connection, SqliteSessionRepository, SqliteEventRepository]:
    """Create a real SQLite session database with the required tables and return repos."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    session_repo = SqliteSessionRepository(conn)
    event_repo = SqliteEventRepository(conn)
    return conn, session_repo, event_repo


SESSION_ID = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# GET / — get_sessions
# ---------------------------------------------------------------------------

class TestGetSessions:
    """Tests for GET /api/v1/ (list sessions)."""

    def test_returns_sessions_list(self, tmp_path: Path):
        """When the user has sessions, return them."""
        user_dir = tmp_path / TEST_USER.user_id
        db_path = user_dir / f"{TEST_USER.user_id}.sqlite"
        conn, session_repo, _ = _create_session_db(db_path)

        s1 = Session(session_id=str(uuid.uuid4()), title="First session")
        s2 = Session(session_id=str(uuid.uuid4()), title="Second session")
        session_repo.save_new_session(s1)
        session_repo.save_new_session(s2)
        conn.close()

        with patch("dependencies.sessions.SESSIONS_PATH", tmp_path):
            response = client.get("/api/v1/")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 2
        titles = {s["title"] for s in data}
        assert titles == {"First session", "Second session"}

    def test_returns_empty_list(self, tmp_path: Path):
        """When no sessions exist yet, return an empty list."""
        user_dir = tmp_path / TEST_USER.user_id
        db_path = user_dir / f"{TEST_USER.user_id}.sqlite"
        conn, _, _ = _create_session_db(db_path)
        conn.close()

        with patch("dependencies.sessions.SESSIONS_PATH", tmp_path):
            response = client.get("/api/v1/")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    def test_session_dir_not_configured(self):
        """SESSION_DIR is None → 500."""
        with patch("dependencies.sessions.SESSIONS_PATH", None):
            response = client.get("/api/v1/")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "SESSIONS_PATH" in response.json()["detail"]

    def test_session_db_not_found(self, tmp_path: Path):
        """User directory / DB file doesn't exist → 404."""
        with patch("dependencies.sessions.SESSIONS_PATH", tmp_path):
            response = client.get("/api/v1/")

        assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# GET /{session_id} — chat_history
# ---------------------------------------------------------------------------

class TestChatHistory:
    """Tests for GET /api/v1/{session_id}."""

    def test_returns_messages(self, tmp_path: Path):
        """History with events returns them in ascending order."""
        user_dir = tmp_path / TEST_USER.user_id
        db_path = user_dir / f"{TEST_USER.user_id}.sqlite"
        conn, _, event_repo = _create_session_db(db_path)

        event_repo.save(Event(session_id=SESSION_ID, event_type=EventType.USER_MESSAGE, content="Hello"))
        event_repo.save(Event(session_id=SESSION_ID, event_type=EventType.RESPONSE, content="Hi there"))
        conn.close()

        with patch("dependencies.sessions.SESSIONS_PATH", tmp_path):
            response = client.get(f"/api/v1/{SESSION_ID}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "messages" in data
        messages = data["messages"]
        assert len(messages) == 2
        # Ascending order: user first, then assistant
        assert messages[0]["_role"] == "user"
        assert messages[0]["_content"][0]["text"] == "Hello"
        assert messages[1]["_role"] == "assistant"
        assert messages[1]["_content"][0]["text"] == "Hi there"

    def test_empty_history(self, tmp_path: Path):
        """Session exists but no events → empty messages list."""
        user_dir = tmp_path / TEST_USER.user_id
        db_path = user_dir / f"{TEST_USER.user_id}.sqlite"
        conn, _, _ = _create_session_db(db_path)
        conn.close()

        with patch("dependencies.sessions.SESSIONS_PATH", tmp_path):
            response = client.get(f"/api/v1/{SESSION_ID}")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["messages"] == []

    def test_session_dir_not_configured(self):
        """SESSION_DIR is None → 500."""
        with patch("dependencies.sessions.SESSIONS_PATH", None):
            response = client.get(f"/api/v1/{SESSION_ID}")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_session_db_not_found(self, tmp_path: Path):
        """DB file doesn't exist → 404."""
        with patch("dependencies.sessions.SESSIONS_PATH", tmp_path):
            response = client.get(f"/api/v1/{SESSION_ID}")

        assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# POST /{session_id} — chat
# ---------------------------------------------------------------------------

class TestPostChat:
    """Tests for POST /api/v1/{session_id}."""

    def test_successful_chat(self, tmp_path: Path):
        """Happy path: user message is saved, agent runs, response is returned."""
        user_dir = tmp_path / TEST_USER.user_id
        db_path = user_dir / f"{TEST_USER.user_id}.sqlite"
        conn, session_repo, event_repo = _create_session_db(db_path)
        session_repo.save_new_session(Session(session_id=SESSION_ID, title="Test"))
        conn.close()

        mock_agent = MagicMock()
        mock_agent.run.return_value = {"last_message": "Agent response text"}

        mock_vector_stores = MagicMock()
        mock_vector_stores.knowledge_store = MagicMock()

        with (
            patch("dependencies.sessions.SESSIONS_PATH", tmp_path),
            patch("endpoints.chat.get_or_create_vector_stores", new_callable=AsyncMock, return_value=mock_vector_stores),
            patch("endpoints.chat.Agent", return_value=mock_agent),
            patch("endpoints.chat.get_relevant_facts_tool", return_value=MagicMock()),
        ):
            response = client.post(
                f"/api/v1/{SESSION_ID}",
                json={"message": "What vulnerabilities were found?"},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "response" in data

        # Verify the user event was persisted
        conn2 = sqlite3.connect(str(db_path))
        event_repo2 = SqliteEventRepository(conn2)
        events = event_repo2.get_recent(SESSION_ID, 100)
        user_events = [e for e in events if e.event_type == EventType.USER_MESSAGE]
        assert len(user_events) == 1
        assert user_events[0].content == "What vulnerabilities were found?"
        conn2.close()

    def test_agent_run_is_called_with_messages(self, tmp_path: Path):
        """Verify the Agent.run method receives the correct messages list."""
        user_dir = tmp_path / TEST_USER.user_id
        db_path = user_dir / f"{TEST_USER.user_id}.sqlite"
        conn, session_repo, event_repo = _create_session_db(db_path)
        session_repo.save_new_session(Session(session_id=SESSION_ID, title="Test"))
        # Pre-seed a conversation
        event_repo.save(Event(session_id=SESSION_ID, event_type=EventType.USER_MESSAGE, content="Hello"))
        event_repo.save(Event(session_id=SESSION_ID, event_type=EventType.RESPONSE, content="Hi"))
        conn.close()

        mock_agent = MagicMock()
        mock_agent.run.return_value = {"last_message": "Sure!"}

        mock_vector_stores = MagicMock()
        mock_vector_stores.knowledge_store = MagicMock()

        with (
            patch("dependencies.sessions.SESSIONS_PATH", tmp_path),
            patch("endpoints.chat.get_or_create_vector_stores", new_callable=AsyncMock, return_value=mock_vector_stores),
            patch("endpoints.chat.Agent", return_value=mock_agent),
            patch("endpoints.chat.get_relevant_facts_tool", return_value=MagicMock()),
        ):
            response = client.post(
                f"/api/v1/{SESSION_ID}",
                json={"message": "Follow-up question"},
            )

        assert response.status_code == status.HTTP_200_OK
        # Agent.run should have been called once
        mock_agent.run.assert_called_once()
        call_kwargs = mock_agent.run.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        # Should contain previous messages + the new user message
        assert len(messages) >= 3  # Hello, Hi, Follow-up question

    def test_session_dir_not_configured(self):
        """SESSION_DIR is None → 500."""
        with patch("dependencies.sessions.SESSIONS_PATH", None):
            response = client.post(
                f"/api/v1/{SESSION_ID}",
                json={"message": "Hello"},
            )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_session_db_not_found(self, tmp_path: Path):
        """DB file doesn't exist → 404."""
        with patch("dependencies.sessions.SESSIONS_PATH", tmp_path):
            response = client.post(
                f"/api/v1/{SESSION_ID}",
                json={"message": "Hello"},
            )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_agent_error_returns_500(self, tmp_path: Path):
        """If the Agent raises an exception, endpoint returns 500."""
        user_dir = tmp_path / TEST_USER.user_id
        db_path = user_dir / f"{TEST_USER.user_id}.sqlite"
        conn, session_repo, _ = _create_session_db(db_path)
        session_repo.save_new_session(Session(session_id=SESSION_ID, title="Test"))
        conn.close()

        mock_agent = MagicMock()
        mock_agent.run.side_effect = RuntimeError("Model unavailable")

        mock_vector_stores = MagicMock()
        mock_vector_stores.knowledge_store = MagicMock()

        with (
            patch("dependencies.sessions.SESSIONS_PATH", tmp_path),
            patch("endpoints.chat.get_or_create_vector_stores", new_callable=AsyncMock, return_value=mock_vector_stores),
            patch("endpoints.chat.Agent", return_value=mock_agent),
            patch("endpoints.chat.get_relevant_facts_tool", return_value=MagicMock()),
        ):
            response = client.post(
                f"/api/v1/{SESSION_ID}",
                json={"message": "Hello"},
            )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Model unavailable" in response.json()["detail"]

    def test_missing_message_body_returns_422(self):
        """Missing / invalid request body → 422."""
        with patch("dependencies.sessions.SESSIONS_PATH", Path("/tmp")):
            response = client.post(f"/api/v1/{SESSION_ID}")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


class TestCallbackFactoryFlush:
    """Verify that callback_factory.flush() is called after a successful agent run."""

    def test_flush_called_on_success(self, tmp_path: Path):
        """StreamCallbackFactory.flush is called after agent.run succeeds."""
        user_dir = tmp_path / TEST_USER.user_id
        db_path = user_dir / f"{TEST_USER.user_id}.sqlite"
        conn, session_repo, _ = _create_session_db(db_path)
        session_repo.save_new_session(Session(session_id=SESSION_ID, title="Test"))
        conn.close()

        mock_agent = MagicMock()
        mock_agent.run.return_value = {"last_message": "Done"}

        mock_vector_stores = MagicMock()
        mock_vector_stores.knowledge_store = MagicMock()

        mock_factory = MagicMock()
        mock_factory.return_value = MagicMock()  # the __call__ returns a callback

        with (
            patch("dependencies.sessions.SESSIONS_PATH", tmp_path),
            patch("endpoints.chat.get_or_create_vector_stores", new_callable=AsyncMock, return_value=mock_vector_stores),
            patch("endpoints.chat.Agent", return_value=mock_agent),
            patch("endpoints.chat.get_relevant_facts_tool", return_value=MagicMock()),
            patch("endpoints.chat.StreamCallbackFactory", return_value=mock_factory),
        ):
            response = client.post(
                f"/api/v1/{SESSION_ID}",
                json={"message": "Hi"},
            )

        assert response.status_code == status.HTTP_200_OK
        mock_factory.flush.assert_called_once()


# ---------------------------------------------------------------------------
# DELETE /{session_id} — delete_session
# ---------------------------------------------------------------------------

class TestDeleteSession:
    """Tests for DELETE /api/v1/{session_id}."""

    def test_successful_delete(self, tmp_path: Path):
        """Happy path: session and its messages are deleted."""
        user_dir = tmp_path / TEST_USER.user_id
        db_path = user_dir / f"{TEST_USER.user_id}.sqlite"
        conn, session_repo, event_repo = _create_session_db(db_path)
        
        # Create a session to delete
        session_id = str(uuid.uuid4())
        session_repo.save_new_session(Session(session_id=session_id, title="To be deleted"))
        event_repo.save(Event(session_id=session_id, event_type=EventType.USER_MESSAGE, content="Hello"))
        conn.close()

        # Create session directory as required by the endpoint logic
        (user_dir / session_id).mkdir(parents=True, exist_ok=True)

        with patch("dependencies.sessions.SESSIONS_PATH", tmp_path):
            response = client.delete(f"/api/v1/{session_id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        
        # Verify it's gone from session repo and event repo
        conn2 = sqlite3.connect(str(db_path))
        session_repo2 = SqliteSessionRepository(conn2)
        event_repo2 = SqliteEventRepository(conn2)
        
        assert session_repo2.get_session(session_id) is None
        assert len(event_repo2.get_recent(session_id)) == 0
        conn2.close()

    def test_session_dir_not_configured(self):
        """SESSION_DIR is None → 500."""
        with patch("dependencies.sessions.SESSIONS_PATH", None):
            response = client.delete(f"/api/v1/{SESSION_ID}")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_session_db_not_found(self, tmp_path: Path):
        """DB file doesn't exist → 404."""
        with patch("dependencies.sessions.SESSIONS_PATH", tmp_path):
            response = client.delete(f"/api/v1/{SESSION_ID}")

        assert response.status_code == status.HTTP_404_NOT_FOUND

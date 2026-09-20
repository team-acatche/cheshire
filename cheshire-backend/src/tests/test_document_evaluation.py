import io
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from docling_core.types.doc import BoundingBox
from fastapi import status
from fastapi.testclient import TestClient

from server import api
from cheshire_configs.registry import configs
from cheshire_configs.core import PipelineConfig, Provider, EvaluationType
from auth.dependencies import get_current_user
from auth.models import User
from endpoints.evaluate import _run_evaluation
from knowledge_base.history import Event, EventType, SqliteEventRepository
from knowledge_base.session_manager import Session, SessionStatus, SqliteSessionRepository
from tools.helpers.output_schema import VulnerabilityDetails

# Override the registry dependency to avoid real model initialization
# This also ensures resolve_config finds a valid config for the default provider
mock_config = PipelineConfig(
    model=MagicMock(),
    tools=[],
    mode=EvaluationType.MULTISTEP
)
def mock_get_current_user():
    return User(user_id="test_id", email="test@example.com", sessions_folder="testuser", username="testuser", full_name="Test User", avatar_uri="default.png")

@pytest.fixture(autouse=True)
def setup_overrides():
    api.dependency_overrides[configs] = lambda: {Provider.OPENROUTER: mock_config}
    api.dependency_overrides[get_current_user] = mock_get_current_user
    with patch("endpoints.evaluate.KnowledgeRepositoryFactory.create_repositories", return_value=(MagicMock(), MagicMock())):
        yield
        api.dependency_overrides.clear()

client = TestClient(api)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pdf_bytes() -> bytes:
    """Return a minimal valid PDF as bytes (no external files needed)."""
    from pypdfium2 import PdfDocument # type: ignore

    doc = PdfDocument.new()
    doc.new_page(595, 842)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _make_vulnerability(title: str, description: str, page: int = 1) -> VulnerabilityDetails:
    """Build a VulnerabilityDetails instance for mocking evaluate_file output."""
    return VulnerabilityDetails(
        title=title,
        description=description,
        page_no=page,
        bbox=BoundingBox(l=10.0, t=10.0, r=100.0, b=100.0),
        web_references=["http://example.com"],
        recommendations=["Recommendation 1"],
    )


def _setup_db(tmp_path: Path, session_id: str) -> Path:
    """Create a SQLite DB with a PENDING session and return its path."""
    db_path = tmp_path / "test.sqlite"
    with sqlite3.connect(db_path) as db:
        repo = SqliteSessionRepository(db)
        repo.save_new_session(Session(
            session_id=session_id,
            title="test.pdf",
            status=SessionStatus.PENDING,
        ))
    return db_path


PDF_BYTES = _make_pdf_bytes()


# ---------------------------------------------------------------------------
# Tests — POST /evaluate (submission)
# ---------------------------------------------------------------------------

class TestEvaluateSubmission:
    """Tests for the async POST /evaluate submission endpoint."""

    @patch("endpoints.evaluate._run_evaluation")
    @patch("dependencies.sessions.SESSIONS_PATH", Path("/tmp"))
    def test_submit_returns_202_with_session_id(self, mock_run):
        """Upload a PDF → 202 Accepted with session_id and status='pending'."""
        response = client.post(
            "/api/v1/evaluate",
            files={"uploaded_document": ("test.pdf", PDF_BYTES, "application/pdf")},
        )
        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "pending"
        mock_run.assert_called_once()

    @patch("endpoints.evaluate._run_evaluation")
    @patch("dependencies.sessions.SESSIONS_PATH", Path("/tmp"))
    def test_submit_with_custom_session_id(self, mock_run):
        """When a session_id query param is provided, it is echoed back."""
        custom_id = "my-custom-session-id"
        response = client.post(
            "/api/v1/evaluate",
            params={"session_id": custom_id},
            files={"uploaded_document": ("report.pdf", PDF_BYTES, "application/pdf")},
        )
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.json()["session_id"] == custom_id
        mock_run.assert_called_once()

    @patch("endpoints.evaluate._run_evaluation")
    @patch("dependencies.sessions.SESSIONS_PATH", Path("/tmp"))
    def test_filename_fallback(self, mock_run):
        """An unusual filename doesn't crash the endpoint."""
        response = client.post(
            "/api/v1/evaluate",
            files={"uploaded_document": ("upload", PDF_BYTES, "application/pdf")},
        )
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.json()["status"] == "pending"
        mock_run.assert_called_once()


class TestRequestValidation:
    """Tests for invalid requests."""

    @patch("dependencies.sessions.SESSIONS_PATH", Path("/tmp"))
    def test_missing_file_returns_422(self):
        """No file uploaded → 422 validation error."""
        response = client.post("/api/v1/evaluate")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# ---------------------------------------------------------------------------
# Tests — _run_evaluation (background worker)
# ---------------------------------------------------------------------------

class TestBackgroundEvaluation:
    """Tests for _run_evaluation — the background worker that produces results."""

    def test_successful_evaluation_persists_findings(self, tmp_path: Path):
        """Findings from evaluate_file are persisted as VULNERABILITY_FINDING events."""
        session_id = str(uuid.uuid4())
        db_path = _setup_db(tmp_path, session_id)
        user_path = tmp_path / "user"
        user_path.mkdir()

        # Create a temp file to stand in for the uploaded PDF
        tmp_file = tmp_path / "upload.pdf"
        tmp_file.write_bytes(PDF_BYTES)

        mock_results = [
            _make_vulnerability("Vuln A", "Description A", page=1),
            _make_vulnerability("Vuln B", "Description B", page=2),
            _make_vulnerability("Vuln C", "Description C", page=3),
        ]

        with patch("endpoints.evaluate.evaluate_file", new_callable=AsyncMock, return_value=mock_results):
            _run_evaluation(
                session_id=session_id,
                tmp_file_path=tmp_file,
                filename="test.pdf",
                user_id="test_id",
                user_path=user_path,
                user_db_path=db_path,
                config=mock_config,
            )

        # Verify findings were persisted
        with sqlite3.connect(db_path) as db:
            events = SqliteEventRepository(db).get_recent(
                session_id, event_types=[EventType.VULNERABILITY_FINDING]
            )
        assert len(events) == 3
        titles = [VulnerabilityDetails.model_validate_json(e.content).title for e in events]
        assert set(titles) == {"Vuln A", "Vuln B", "Vuln C"}

    def test_successful_evaluation_transitions_to_done(self, tmp_path: Path):
        """Session status transitions PENDING → PROCESSING → DONE on success."""
        session_id = str(uuid.uuid4())
        db_path = _setup_db(tmp_path, session_id)
        user_path = tmp_path / "user"
        user_path.mkdir()

        tmp_file = tmp_path / "upload.pdf"
        tmp_file.write_bytes(PDF_BYTES)

        mock_results = [_make_vulnerability("Vuln X", "Desc X")]

        with patch("endpoints.evaluate.evaluate_file", new_callable=AsyncMock, return_value=mock_results):
            _run_evaluation(
                session_id=session_id,
                tmp_file_path=tmp_file,
                filename="test.pdf",
                user_id="test_id",
                user_path=user_path,
                user_db_path=db_path,
                config=mock_config,
            )

        with sqlite3.connect(db_path) as db:
            session = SqliteSessionRepository(db).get_session(session_id)
        assert session is not None
        assert session.status == SessionStatus.DONE

    def test_finding_metadata_fields(self, tmp_path: Path):
        """Each persisted finding round-trips all metadata fields correctly."""
        session_id = str(uuid.uuid4())
        db_path = _setup_db(tmp_path, session_id)
        user_path = tmp_path / "user"
        user_path.mkdir()

        tmp_file = tmp_path / "upload.pdf"
        tmp_file.write_bytes(PDF_BYTES)

        original = _make_vulnerability("SQL Injection", "Unsanitized input on page 5", page=5)

        with patch("endpoints.evaluate.evaluate_file", new_callable=AsyncMock, return_value=[original]):
            _run_evaluation(
                session_id=session_id,
                tmp_file_path=tmp_file,
                filename="doc.pdf",
                user_id="test_id",
                user_path=user_path,
                user_db_path=db_path,
                config=mock_config,
            )

        with sqlite3.connect(db_path) as db:
            events = SqliteEventRepository(db).get_recent(
                session_id, event_types=[EventType.VULNERABILITY_FINDING]
            )
        assert len(events) == 1
        restored = VulnerabilityDetails.model_validate_json(events[0].content)
        assert restored.title == "SQL Injection"
        assert restored.description == "Unsanitized input on page 5"
        assert restored.page_no == 5
        assert restored.web_references == ["http://example.com"]
        assert restored.recommendations == ["Recommendation 1"]

    def test_finding_titles_are_unique(self, tmp_path: Path):
        """All persisted finding titles are unique."""
        session_id = str(uuid.uuid4())
        db_path = _setup_db(tmp_path, session_id)
        user_path = tmp_path / "user"
        user_path.mkdir()

        tmp_file = tmp_path / "upload.pdf"
        tmp_file.write_bytes(PDF_BYTES)

        mock_results = [_make_vulnerability(f"Vuln {i}", f"Desc {i}") for i in range(5)]

        with patch("endpoints.evaluate.evaluate_file", new_callable=AsyncMock, return_value=mock_results):
            _run_evaluation(
                session_id=session_id,
                tmp_file_path=tmp_file,
                filename="test.pdf",
                user_id="test_id",
                user_path=user_path,
                user_db_path=db_path,
                config=mock_config,
            )

        with sqlite3.connect(db_path) as db:
            events = SqliteEventRepository(db).get_recent(
                session_id, event_types=[EventType.VULNERABILITY_FINDING]
            )
        titles = [VulnerabilityDetails.model_validate_json(e.content).title for e in events]
        assert len(set(titles)) == len(titles)

    def test_empty_results_no_findings(self, tmp_path: Path):
        """When evaluate_file returns an empty list, no findings are persisted."""
        session_id = str(uuid.uuid4())
        db_path = _setup_db(tmp_path, session_id)
        user_path = tmp_path / "user"
        user_path.mkdir()

        tmp_file = tmp_path / "upload.pdf"
        tmp_file.write_bytes(PDF_BYTES)

        with patch("endpoints.evaluate.evaluate_file", new_callable=AsyncMock, return_value=[]):
            _run_evaluation(
                session_id=session_id,
                tmp_file_path=tmp_file,
                filename="test.pdf",
                user_id="test_id",
                user_path=user_path,
                user_db_path=db_path,
                config=mock_config,
            )

        with sqlite3.connect(db_path) as db:
            events = SqliteEventRepository(db).get_recent(
                session_id, event_types=[EventType.VULNERABILITY_FINDING]
            )
            session = SqliteSessionRepository(db).get_session(session_id)
        assert events == []
        assert session.status == SessionStatus.DONE

    def test_evaluation_failure_transitions_to_failed(self, tmp_path: Path):
        """When evaluate_file raises, session status transitions to FAILED."""
        session_id = str(uuid.uuid4())
        db_path = _setup_db(tmp_path, session_id)
        user_path = tmp_path / "user"
        user_path.mkdir()

        tmp_file = tmp_path / "upload.pdf"
        tmp_file.write_bytes(PDF_BYTES)

        with patch("endpoints.evaluate.evaluate_file", new_callable=AsyncMock, side_effect=RuntimeError("Model crashed")):
            _run_evaluation(
                session_id=session_id,
                tmp_file_path=tmp_file,
                filename="test.pdf",
                user_id="test_id",
                user_path=user_path,
                user_db_path=db_path,
                config=mock_config,
            )

        with sqlite3.connect(db_path) as db:
            session = SqliteSessionRepository(db).get_session(session_id)
        assert session is not None
        assert session.status == SessionStatus.FAILED

    def test_none_results_transitions_to_failed(self, tmp_path: Path):
        """When evaluate_file returns None, session status transitions to FAILED."""
        session_id = str(uuid.uuid4())
        db_path = _setup_db(tmp_path, session_id)
        user_path = tmp_path / "user"
        user_path.mkdir()

        tmp_file = tmp_path / "upload.pdf"
        tmp_file.write_bytes(PDF_BYTES)

        with patch("endpoints.evaluate.evaluate_file", new_callable=AsyncMock, return_value=None):
            _run_evaluation(
                session_id=session_id,
                tmp_file_path=tmp_file,
                filename="test.pdf",
                user_id="test_id",
                user_path=user_path,
                user_db_path=db_path,
                config=mock_config,
            )

        with sqlite3.connect(db_path) as db:
            session = SqliteSessionRepository(db).get_session(session_id)
        assert session is not None
        assert session.status == SessionStatus.FAILED


# ---------------------------------------------------------------------------
# Tests — GET /{session_id}/result (serving persisted findings)
# ---------------------------------------------------------------------------

class TestGetResults:
    """Tests for GET /api/v1/{session_id}/result after evaluation completes."""

    def test_returns_persisted_findings(self, tmp_path: Path):
        """Findings persisted by _run_evaluation are returned by GET /result."""
        session_id = str(uuid.uuid4())
        db_path = _setup_db(tmp_path, session_id)
        user_path = tmp_path / "user"
        user_path.mkdir()

        tmp_file = tmp_path / "upload.pdf"
        tmp_file.write_bytes(PDF_BYTES)

        mock_results = [
            _make_vulnerability("Vuln A", "Description A"),
            _make_vulnerability("Vuln B", "Description B"),
        ]

        with patch("endpoints.evaluate.evaluate_file", new_callable=AsyncMock, return_value=mock_results):
            _run_evaluation(
                session_id=session_id,
                tmp_file_path=tmp_file,
                filename="test.pdf",
                user_id="test_id",
                user_path=user_path,
                user_db_path=db_path,
                config=mock_config,
            )

        from dependencies.sessions import get_user_db_path
        api.dependency_overrides[get_user_db_path] = lambda: db_path
        try:
            response = client.get(f"/api/v1/{session_id}/result")
        finally:
            del api.dependency_overrides[get_user_db_path]

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 2
        titles = {item["title"] for item in data}
        assert titles == {"Vuln A", "Vuln B"}

        # Verify all expected fields are present
        for item in data:
            assert "title" in item
            assert "description" in item
            assert "page_no" in item
            assert "bbox" in item
            assert "web_references" in item
            assert "recommendations" in item

    def test_empty_results_returns_empty_list(self, tmp_path: Path):
        """When no findings were persisted, GET /result returns []."""
        session_id = str(uuid.uuid4())
        db_path = _setup_db(tmp_path, session_id)

        from dependencies.sessions import get_user_db_path
        api.dependency_overrides[get_user_db_path] = lambda: db_path
        try:
            response = client.get(f"/api/v1/{session_id}/result")
        finally:
            del api.dependency_overrides[get_user_db_path]

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

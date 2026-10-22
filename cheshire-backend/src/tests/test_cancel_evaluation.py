import sqlite3
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from docling_core.types.doc import BoundingBox
from fastapi import status
from fastapi.testclient import TestClient

from server import api
from auth.dependencies import get_current_user
from auth.models import User
from cheshire_configs.core import PipelineConfig, Provider, EvaluationType
from cheshire_configs.registry import configs
from dependencies.sessions import get_user_db_path
from endpoints.evaluate import _run_evaluation
from knowledge_base.history import EventType, SqliteEventRepository
from knowledge_base.job_store import job_store, JobStatus, raise_if_cancelled
from knowledge_base.session_manager import Session, SessionStatus, SqliteSessionRepository
from tools.helpers.output_schema import VulnerabilityDetails

mock_config = PipelineConfig(model=MagicMock(), tools=[], mode=EvaluationType.MULTISTEP)
client = TestClient(api)


@pytest.fixture(autouse=True)
def overrides():
    api.dependency_overrides[configs] = lambda: {Provider.OPENROUTER: mock_config}
    api.dependency_overrides[get_current_user] = lambda: User(
        user_id="test_id", email="t@example.com", sessions_folder="testuser", username="testuser"
    )
    with patch("endpoints.evaluate.KnowledgeRepositoryFactory.create_repositories", return_value=(MagicMock(), MagicMock())):
        yield
    api.dependency_overrides.clear()


def _db(tmp_path: Path, session_id: str, st: SessionStatus = SessionStatus.PENDING) -> Path:
    db_path = tmp_path / "test.sqlite"
    with sqlite3.connect(db_path) as db:
        SqliteSessionRepository(db).save_new_session(Session(session_id=session_id, title="t.pdf", status=st))
    api.dependency_overrides[get_user_db_path] = lambda: db_path
    return db_path


def _status(db_path: Path, session_id: str) -> str:
    with sqlite3.connect(db_path) as db:
        return SqliteSessionRepository(db).get_session(session_id).status


def _findings(db_path: Path, session_id: str) -> list:
    with sqlite3.connect(db_path) as db:
        return SqliteEventRepository(db).get_recent(session_id, event_types=[EventType.VULNERABILITY_FINDING])


def _vuln() -> VulnerabilityDetails:
    return VulnerabilityDetails(
        title="V", description="D", page_no=1,
        bbox=BoundingBox(l=1, t=1, r=2, b=2), web_references=[], recommendations=[],
    )


def _run(db_path: Path, session_id: str, tmp_path: Path):
    _run_evaluation(
        session_id=session_id, document_path=tmp_path / "x.pdf", filename="x.pdf",
        user_id="test_id", user_db_path=db_path, config=mock_config,
    )


# ── repository ────────────────────────────────────────────────────────────────

def test_update_status_if_only_applies_when_expected(tmp_path):
    sid = str(uuid.uuid4())
    db_path = _db(tmp_path, sid, SessionStatus.DONE)
    with sqlite3.connect(db_path) as db:
        repo = SqliteSessionRepository(db)
        assert repo.update_status_if(sid, SessionStatus.CANCELLED, expected=(SessionStatus.PENDING, SessionStatus.PROCESSING)) is None
        assert repo.get_session(sid).status == SessionStatus.DONE


# ── endpoint ──────────────────────────────────────────────────────────────────

def test_cancel_pending_session_sets_event_and_status(tmp_path):
    sid = str(uuid.uuid4())
    db_path = _db(tmp_path, sid)
    job = job_store.create(sid)

    r = client.post(f"/api/v1/{sid}/cancel")

    assert r.status_code == status.HTTP_200_OK
    assert _status(db_path, sid) == SessionStatus.CANCELLED
    assert job.cancel_event.is_set()
    assert job_store.get(sid).status == JobStatus.CANCELLED


def test_cancel_is_idempotent(tmp_path):
    sid = str(uuid.uuid4())
    _db(tmp_path, sid, SessionStatus.CANCELLED)
    assert client.post(f"/api/v1/{sid}/cancel").status_code == status.HTTP_200_OK


@pytest.mark.parametrize("st", [SessionStatus.DONE, SessionStatus.FAILED])
def test_cancel_finished_session_returns_409_and_keeps_status(tmp_path, st):
    sid = str(uuid.uuid4())
    db_path = _db(tmp_path, sid, st)
    assert client.post(f"/api/v1/{sid}/cancel").status_code == status.HTTP_409_CONFLICT
    assert _status(db_path, sid) == st


def test_cancel_unknown_session_returns_404(tmp_path):
    _db(tmp_path, str(uuid.uuid4()))
    assert client.post(f"/api/v1/{uuid.uuid4()}/cancel").status_code == status.HTTP_404_NOT_FOUND


def test_status_endpoint_reports_cancelled(tmp_path):
    sid = str(uuid.uuid4())
    _db(tmp_path, sid, SessionStatus.CANCELLED)
    r = client.get(f"/api/v1/{sid}/status")
    assert r.status_code == status.HTTP_200_OK
    assert r.json()["status"] == "CANCELLED"


# ── worker ────────────────────────────────────────────────────────────────────

def test_worker_stops_mid_run_and_saves_nothing(tmp_path):
    sid = str(uuid.uuid4())
    db_path = _db(tmp_path, sid)
    job = job_store.create(sid)

    async def fake_eval(path, config, should_cancel=None):
        job.cancel_event.set()               # user clicks cancel mid-run
        raise_if_cancelled(should_cancel)
        return [_vuln()]                     # must never be reached

    with patch("endpoints.evaluate.evaluate_file", fake_eval):
        _run(db_path, sid, tmp_path)

    assert _status(db_path, sid) == SessionStatus.CANCELLED
    assert _findings(db_path, sid) == []
    assert job_store.get(sid).status == JobStatus.CANCELLED


def test_worker_does_not_start_if_cancelled_while_pending(tmp_path):
    sid = str(uuid.uuid4())
    db_path = _db(tmp_path, sid, SessionStatus.CANCELLED)
    job_store.create(sid)

    async def should_not_run(*a, **k):
        raise AssertionError("evaluation must not start")

    with patch("endpoints.evaluate.evaluate_file", should_not_run):
        _run(db_path, sid, tmp_path)

    assert _status(db_path, sid) == SessionStatus.CANCELLED


def test_cancel_racing_with_completion_discards_findings(tmp_path):
    sid = str(uuid.uuid4())
    db_path = _db(tmp_path, sid)
    job_store.create(sid)

    async def fake_eval(path, config, should_cancel=None):
        # cancel lands in SQLite right after the last check, before findings are persisted
        with sqlite3.connect(db_path) as db:
            SqliteSessionRepository(db).update_status_if(
                sid, SessionStatus.CANCELLED, expected=(SessionStatus.PROCESSING,)
            )
        return [_vuln(), _vuln()]

    with patch("endpoints.evaluate.evaluate_file", fake_eval):
        _run(db_path, sid, tmp_path)

    assert _status(db_path, sid) == SessionStatus.CANCELLED   # not clobbered by DONE
    assert _findings(db_path, sid) == []                      # rolled back
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from server import api
from auth.dependencies import get_current_user
from auth.models import User
from cheshire_configs.core import PipelineConfig, Provider, EvaluationType
from cheshire_configs.registry import configs
from cheshire_configs.resolver import resolve_config
from dependencies.sessions import get_user_db_path, get_user_path
from knowledge_base.history import Event, EventType, SqliteEventRepository
from knowledge_base.job_store import job_store
from knowledge_base.session_manager import Session, SessionStatus, SqliteSessionRepository

mock_config = PipelineConfig(model=MagicMock(), tools=[], mode=EvaluationType.MULTISTEP)
client = TestClient(api)


@pytest.fixture(autouse=True)
def overrides():
    api.dependency_overrides[configs] = lambda: {Provider.OPENROUTER: mock_config}
    api.dependency_overrides[resolve_config] = lambda: mock_config
    api.dependency_overrides[get_current_user] = lambda: User(
        user_id="test_id", email="t@example.com", sessions_folder="testuser", username="testuser"
    )
    yield
    api.dependency_overrides.clear()


def _setup(tmp_path: Path, sid: str, st: SessionStatus, *, with_doc: bool = True) -> Path:
    user_path = tmp_path / "user"
    user_path.mkdir(exist_ok=True)
    db_path = tmp_path / "test.sqlite"
    with sqlite3.connect(db_path) as db:
        SqliteSessionRepository(db).save_new_session(Session(session_id=sid, title="t.pdf", status=st))
    if with_doc:
        doc_dir = user_path / sid / "documents"
        doc_dir.mkdir(parents=True)
        (doc_dir / f"{datetime.now().isoformat()}__t.pdf").write_bytes(b"%PDF-1.4")
    api.dependency_overrides[get_user_db_path] = lambda: db_path
    api.dependency_overrides[get_user_path] = lambda: user_path
    return db_path


def _status(db_path: Path, sid: str) -> str:
    with sqlite3.connect(db_path) as db:
        return SqliteSessionRepository(db).get_session(sid).status


@patch("endpoints.evaluate._run_evaluation")
def test_rerun_cancelled_queues_worker_with_stored_document(mock_run, tmp_path):
    sid = str(uuid.uuid4())
    db_path = _setup(tmp_path, sid, SessionStatus.CANCELLED)

    r = client.post(f"/api/v1/{sid}/rerun")

    assert r.status_code == status.HTTP_202_ACCEPTED
    assert r.json() == {"session_id": sid, "status": "pending"}
    assert _status(db_path, sid) == SessionStatus.PENDING
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["document_path"].name.endswith("__t.pdf")


@patch("endpoints.evaluate._run_evaluation")
def test_rerun_clears_stale_findings(mock_run, tmp_path):
    sid = str(uuid.uuid4())
    db_path = _setup(tmp_path, sid, SessionStatus.CANCELLED)
    with sqlite3.connect(db_path) as db:
        SqliteEventRepository(db).save(Event(session_id=sid, event_type=EventType.VULNERABILITY_FINDING, content="{}"))

    assert client.post(f"/api/v1/{sid}/rerun").status_code == status.HTTP_202_ACCEPTED

    with sqlite3.connect(db_path) as db:
        assert SqliteEventRepository(db).get_recent(sid, event_types=[EventType.VULNERABILITY_FINDING]) == []


@pytest.mark.parametrize("st", [SessionStatus.DONE, SessionStatus.PROCESSING, SessionStatus.FAILED])
@patch("endpoints.evaluate._run_evaluation")
def test_rerun_non_cancelled_returns_409(mock_run, tmp_path, st):
    sid = str(uuid.uuid4())
    db_path = _setup(tmp_path, sid, st)
    assert client.post(f"/api/v1/{sid}/rerun").status_code == status.HTTP_409_CONFLICT
    assert _status(db_path, sid) == st
    mock_run.assert_not_called()


@patch("endpoints.evaluate._run_evaluation")
def test_rerun_while_old_worker_still_stopping_returns_409(mock_run, tmp_path):
    sid = str(uuid.uuid4())
    db_path = _setup(tmp_path, sid, SessionStatus.CANCELLED)
    job_store.create(sid)  # worker_done never set → worker still alive

    assert client.post(f"/api/v1/{sid}/rerun").status_code == status.HTTP_409_CONFLICT
    assert _status(db_path, sid) == SessionStatus.CANCELLED
    mock_run.assert_not_called()


@patch("endpoints.evaluate._run_evaluation")
def test_rerun_after_old_worker_exited_succeeds(mock_run, tmp_path):
    sid = str(uuid.uuid4())
    _setup(tmp_path, sid, SessionStatus.CANCELLED)
    job_store.create(sid).worker_done.set()

    assert client.post(f"/api/v1/{sid}/rerun").status_code == status.HTTP_202_ACCEPTED


@patch("endpoints.evaluate._run_evaluation")
def test_rerun_missing_document_returns_404_and_keeps_status(mock_run, tmp_path):
    sid = str(uuid.uuid4())
    db_path = _setup(tmp_path, sid, SessionStatus.CANCELLED, with_doc=False)

    assert client.post(f"/api/v1/{sid}/rerun").status_code == status.HTTP_404_NOT_FOUND
    assert _status(db_path, sid) == SessionStatus.CANCELLED


@patch("endpoints.evaluate._run_evaluation")
def test_rerun_unknown_session_returns_404(mock_run, tmp_path):
    _setup(tmp_path, str(uuid.uuid4()), SessionStatus.CANCELLED)
    assert client.post(f"/api/v1/{uuid.uuid4()}/rerun").status_code == status.HTTP_404_NOT_FOUND
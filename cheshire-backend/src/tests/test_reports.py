import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

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
from knowledge_base.history import Event, EventType, SqliteEventRepository
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
    yield
    api.dependency_overrides.clear()


def _finding(title: str, severity: str, scope: str = "section") -> str:
    return VulnerabilityDetails(
        title=title, description="d", page_no=1,
        bbox=BoundingBox(l=1, t=2, r=3, b=0),
        web_references=[], recommendations=[],
        severity=severity, scope=scope,
    ).model_dump_json()


def _seed(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.sqlite"
    with sqlite3.connect(db_path) as db:
        sessions = SqliteSessionRepository(db)
        events = SqliteEventRepository(db)

        sessions.save_new_session(Session(session_id="a", title="a.pdf", status=SessionStatus.DONE))
        sessions.save_new_session(Session(session_id="b", title="b.pdf", status=SessionStatus.PROCESSING))
        sessions.save_new_session(Session(session_id="c", title="c.pdf", status=SessionStatus.DONE))

        for title, sev, scope in [
            ("SQL injection", "major", "section"),
            ("Weak hashing", "minor", "section"),
            ("Missing Section: Overview", "major", "document"),
            ("Typo", "observation", "section"),
        ]:
            events.save(Event(session_id="a", event_type=EventType.VULNERABILITY_FINDING, content=_finding(title, sev, scope)))
        events.save(Event(session_id="b", event_type=EventType.VULNERABILITY_FINDING, content=_finding("Ignored", "major")))
    api.dependency_overrides[get_user_db_path] = lambda: db_path
    return db_path


def test_trend_counts_only_completed_sessions(tmp_path):
    _seed(tmp_path)

    r = client.get("/api/v1/reports/trend")

    assert r.status_code == status.HTTP_200_OK
    by_id = {p["session_id"]: p for p in r.json()}
    assert set(by_id) == {"a", "c"}  # "b" is still processing

    a = by_id["a"]
    assert (a["major"], a["minor"], a["observation"]) == (2, 1, 1)
    assert a["total"] == 4
    assert a["missing"] == 1
    assert a["assessed_at"] is not None

    c = by_id["c"]
    assert c["total"] == 0 and c["assessed_at"] is not None


def test_trend_respects_limit(tmp_path):
    _seed(tmp_path)
    r = client.get("/api/v1/reports/trend", params={"limit": 1})
    assert r.status_code == status.HTTP_200_OK
    assert len(r.json()) == 1


def test_trend_without_database_returns_empty(tmp_path):
    api.dependency_overrides[get_user_db_path] = lambda: tmp_path / "missing.sqlite"
    r = client.get("/api/v1/reports/trend")
    assert r.status_code == status.HTTP_200_OK
    assert r.json() == []
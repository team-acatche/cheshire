import logging
import re
import sqlite3
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from auth.dependencies import get_current_user
from auth.models import User
from dependencies.sessions import get_user_db_path
from knowledge_base.history import EventType, SqliteEventRepository
from knowledge_base.session_manager import SessionStatus, SqliteSessionRepository
from tools.helpers.output_schema import VulnerabilityDetails

reports_router = APIRouter()
logger = logging.getLogger("uvicorn.error")
 
_MISSING_TITLE = re.compile(r"^missing\b", re.IGNORECASE)
 
 
class TrendPoint(BaseModel):
    """Severity counts for one completed assessment (one session)."""
    session_id: str
    title: str
    assessed_at: Optional[str] = None
    total: int = 0
    major: int = 0
    minor: int = 0
    observation: int = 0
    missing: int = 0  # findings about absent required content (subset of `total`)
 
 
def _is_missing(finding: VulnerabilityDetails) -> bool:
    return finding.scope == "document" or bool(_MISSING_TITLE.match(finding.title))
 
 
@reports_router.get("/reports/trend")
def assessment_trend(
    current_user: Annotated[User, Depends(get_current_user)],
    user_db_path: Annotated[Path, Depends(get_user_db_path)],
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of most recent assessments")] = 20,
) -> list[TrendPoint]:
    """
    Returns severity counts for the user's completed assessments, oldest first.
 
    The frontend derives the compliance score from these counts, so the score
    shown on the report and the score plotted on the trend always agree.
    """
    if not user_db_path.exists():
        return []
 
    points: list[TrendPoint] = []
    with sqlite3.connect(user_db_path) as db:
        sessions = SqliteSessionRepository(db).get_sessions()
        events = SqliteEventRepository(db)
 
        for session in sessions:
            if session.status != SessionStatus.DONE:
                continue
 
            stored = events.get_recent(session.session_id, event_types=[EventType.VULNERABILITY_FINDING])
            point = TrendPoint(session_id=session.session_id, title=session.title)
 
            for event in stored:
                try:
                    finding = VulnerabilityDetails.model_validate_json(event.content)
                except Exception:
                    logger.warning("reports: skipping unreadable finding event %s", event.event_id)
                    continue
 
                severity = finding.severity or "observation"
                setattr(point, severity, getattr(point, severity) + 1)
                point.total += 1
                if _is_missing(finding):
                    point.missing += 1
 
            timestamps = [e.timestamp for e in stored if e.timestamp]
            point.assessed_at = max(timestamps) if timestamps else session.created_at
            points.append(point)
 
    points.sort(key=lambda p: p.assessed_at or "")
    return points[-limit:]
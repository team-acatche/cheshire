"""
evaluate.py — key changes from original:

1. Session is created with status=PENDING before the background task runs.
2. _run_evaluation() writes PROCESSING → DONE / FAILED back to the session row.
3. GET /{session_id}/status now also accepts no job-store entry and falls back
   to reading session.status from SQLite (handles post-restart polling).
4. GET / (get_sessions) now includes status so the frontend can reconstruct
   in-flight sessions without relying on sessionStorage.
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Annotated, Optional
import aiofiles
import logging
import uuid
from datetime import datetime
import re
import sqlite3
import shutil

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    UploadFile,
    File,
    HTTPException,
    Path as PathParam,
    Query,
    status,
)
from fastapi.responses import FileResponse, RedirectResponse, Response

from dotenv import load_dotenv
from pydantic import BaseModel

from model import evaluate_file
from tools.helpers.output_schema import VulnerabilityDetails
from cheshire_configs.core import PipelineConfig
from cheshire_configs.resolver import resolve_config
from globals import DATA_PATH
from knowledge_base.session_manager import Session, SessionStatus, SqliteSessionRepository
from knowledge_base.history import Event, EventType, SqliteEventRepository
from knowledge_base.repository import RepositoryType, KnowledgeRepositoryFactory
from knowledge_base.job_store import job_store, JobStatus
from auth.models import User
from auth.dependencies import get_current_user
from dependencies.sessions import get_user_path, get_user_db_path

evaluate_router = APIRouter()
logger = logging.getLogger("uvicorn.error")


# ── Pydantic models ────────────────────────────────────────────────────────────

class SubmitResponse(BaseModel):
    session_id: str
    status: str = "pending"


class StatusResponse(BaseModel):
    status: str
    error: Optional[str] = None


# ── Background worker ──────────────────────────────────────────────────────────

def _run_evaluation(
    session_id: str,
    tmp_file_path: Path,
    filename: str,
    user_id: str,
    user_path: Path,
    user_db_path: Path,
    config: PipelineConfig,
) -> None:
    """
    Runs the evaluation in a background thread.

    Status transitions written to SQLite:
        PENDING → PROCESSING (immediately on start)
        PROCESSING → DONE    (on success)
        PROCESSING → FAILED  (on error)

    SQLite is the authoritative status store — the in-memory job_store is
    only used for fast same-process polling during the request lifecycle.
    """

    def _update_session_status(new_status: SessionStatus) -> None:
        try:
            with sqlite3.connect(user_db_path) as db:
                SqliteSessionRepository(db).update_status(session_id, new_status)
        except Exception as exc:
            logger.error(f"session({session_id}): failed to persist status {new_status}: {exc}")

    logger.info(f"session({session_id}): starting evaluation of {filename}…")
    job = job_store.get(session_id)

    if job is not None:
        job.status = JobStatus.RUNNING
        job_store.update(job)

    _update_session_status(SessionStatus.PROCESSING)

    try:
        results = asyncio.run(evaluate_file(tmp_file_path, config))

        if results is None:
            raise RuntimeError("Evaluation returned no results")

        # Persist document file
        document_path = user_path / session_id / "documents"
        saved_filename = f"{datetime.now().isoformat()}__{filename}"
        os.makedirs(document_path, exist_ok=True)
        shutil.move(tmp_file_path, document_path / saved_filename)
        logger.info(f"session({session_id}): document saved to {document_path}.")

        # Init vector stores
        KnowledgeRepositoryFactory.create_repositories(
            RepositoryType.QDRANT, storage_path=DATA_PATH, username=user_id
        )

        # Persist findings
        with sqlite3.connect(user_db_path) as history_db:
            repo = SqliteEventRepository(history_db)
            for v in results:
                repo.save(Event(
                    session_id=session_id,
                    event_type=EventType.VULNERABILITY_FINDING,
                    content=v.model_dump_json(),
                ))

        # Mark done in both stores
        _update_session_status(SessionStatus.DONE)

        if job is not None:
            job.status = JobStatus.DONE
            job.session_id = session_id
            job.result = results
            job_store.update(job)

        logger.info(f"session({session_id}): done — {len(results)} finding(s).")

    except Exception as exc:
        logger.exception(f"session({session_id}): evaluation failed — {exc}")
        _update_session_status(SessionStatus.FAILED)

        if job is not None:
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job_store.update(job)

        tmp_file_path.unlink(missing_ok=True)


# ── POST /evaluate ─────────────────────────────────────────────────────────────

@evaluate_router.post("/evaluate", status_code=status.HTTP_202_ACCEPTED, response_model=SubmitResponse)
async def evaluate_document(
    background_tasks: BackgroundTasks,
    config: Annotated[PipelineConfig, Depends(resolve_config)],
    current_user: Annotated[User, Depends(get_current_user)],
    user_path: Annotated[Path, Depends(get_user_path)],
    user_db_path: Annotated[Path, Depends(get_user_db_path)],
    uploaded_document: Annotated[UploadFile, File(description="The document to be evaluated")],
    session_id: Annotated[Optional[str], Query(description="The session ID for the document. Only set if the uploaded document is an update from the previous evaluation. If None, a new session will be created.")] = None,
) -> SubmitResponse:
    user_id = current_user.user_id
    filename: str = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", uploaded_document.filename or "upload.pdf")
    _session_id: str = session_id or str(uuid.uuid4())

    # Buffer upload before spawning background task
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(await uploaded_document.read())
    tmp.flush()
    tmp.close()
    tmp_path = Path(tmp.name)

    if not tmp_path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded document",
        )

    # Create in-memory job entry
    job_store.create(key=_session_id)

    # Create / update session record in SQLite with status=PENDING.
    # This is the key change: status is now durable from the moment the
    # file lands, so the frontend can reconstruct it after any refresh.
    with sqlite3.connect(user_db_path) as session_db:
        session_repo = SqliteSessionRepository(session_db)
        if session_id and session_repo.get_session(session_id):
            session_repo.change_title(_session_id, new_title=filename)
            session_repo.update_status(_session_id, SessionStatus.PENDING)
        else:
            session_repo.save_new_session(
                Session(session_id=_session_id, title=filename, status=SessionStatus.PENDING)
            )

    # Spawn background evaluation
    background_tasks.add_task(
        _run_evaluation,
        session_id=_session_id,
        tmp_file_path=tmp_path,
        filename=filename,
        user_id=user_id,
        user_path=user_path,
        user_db_path=user_db_path,
        config=config,
    )

    logger.info(f"POST /evaluate: session '{_session_id}' queued (status=pending).")
    return SubmitResponse(session_id=_session_id, status="pending")


# ── GET /{session_id}/status ───────────────────────────────────────────────────

@evaluate_router.get("/{session_id}/status")
def get_evaluation_status(
    session_id: Annotated[str, PathParam()],
    current_user: Annotated[User, Depends(get_current_user)],
    user_db_path: Annotated[Path, Depends(get_user_db_path)],
) -> Response:
    """
    Returns status for a session.

    Prefers the in-memory job_store (fast, same-process) but falls back to
    reading session.status from SQLite so that post-restart polling works.

    HTTP semantics:
        pending / processing → 200 {"status": "PENDING"|"PROCESSING"}
        failed               → 200 {"status": "FAILED", "error": "..."}
        done                 → 301 → /{session_id}/result
    """
    job = job_store.get(session_id)

    if job is not None:
        # Fast path: job is live in this process
        if job.status == JobStatus.DONE:
            return RedirectResponse(
                url=f"/api/v1/{session_id}/result",
                status_code=status.HTTP_301_MOVED_PERMANENTLY,
            )
        body = StatusResponse(
            status=job.status.upper(),
            error=job.error if job.status == JobStatus.FAILED else None,
        )
        return Response(content=body.model_dump_json(), media_type="application/json")

    # Fallback: read from SQLite (handles post-restart / cross-process scenarios)
    if not user_db_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No session found for '{session_id}'.",
        )

    with sqlite3.connect(user_db_path) as db:
        session = SqliteSessionRepository(db).get_session(session_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No session found for '{session_id}'.",
        )

    if session.status == SessionStatus.DONE:
        return RedirectResponse(
            url=f"/api/v1/{session_id}/result",
            status_code=status.HTTP_301_MOVED_PERMANENTLY,
        )

    body = StatusResponse(status=session.status.upper())
    return Response(content=body.model_dump_json(), media_type="application/json")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_latest_document(session_path: Path) -> str:
    latest_filename: Optional[str] = None
    latest: Optional[datetime] = None
    for root, _, filenames in os.walk(session_path / "documents"):
        for filename in filenames:
            if filename.endswith(".pdf"):
                try:
                    timestamp = datetime.fromisoformat(filename.split("__")[0])
                    if latest is None or timestamp > latest:
                        latest = timestamp
                        latest_filename = filename
                except ValueError:
                    pass
    if not latest_filename:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No documents found for this session",
        )
    return latest_filename


# ── GET /{session_id}/result ───────────────────────────────────────────────────

@evaluate_router.get("/{session_id}/result")
def get_latest_evaluation_results(
    current_user: Annotated[User, Depends(get_current_user)],
    history_db_path: Annotated[Path, Depends(get_user_db_path)],
    session_id: Annotated[str, PathParam(description="The session ID for the document.")],
) -> list[VulnerabilityDetails]:
    if not history_db_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    with sqlite3.connect(history_db_path) as history_db:
        history_repo = SqliteEventRepository(history_db)
        findings_history: list[Event] = history_repo.get_recent(
            session_id=session_id, event_types=[EventType.VULNERABILITY_FINDING]
        )
        return [VulnerabilityDetails.model_validate_json(event.content) for event in findings_history]


# ── GET /{session_id}/document ─────────────────────────────────────────────────

@evaluate_router.get("/{session_id}/document")
def get_document(
    current_user: Annotated[User, Depends(get_current_user)],
    user_path: Annotated[Path, Depends(get_user_path)],
    session_id: Annotated[str, PathParam(description="The session ID for the document.")],
) -> Response:
    session_path = user_path / session_id
    doc_name = _get_latest_document(session_path)
    latest_document = session_path / "documents" / doc_name
    if not latest_document.exists():
        return Response(
            status_code=status.HTTP_404_NOT_FOUND,
            content=f"Document for session {session_id} not found",
        )
    return FileResponse(latest_document, media_type="application/pdf")
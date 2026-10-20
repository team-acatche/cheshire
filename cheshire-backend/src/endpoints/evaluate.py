import asyncio
import json
import os
from pathlib import Path
from typing import Annotated, Literal, Optional
import aiofiles
import logging
import uuid
from datetime import datetime
import re
import sqlite3

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
from pydantic import BaseModel, Field

from model import evaluate_file
from tools.helpers.output_schema import VulnerabilityDetails
from cheshire_configs.core import PipelineConfig
from cheshire_configs.resolver import resolve_config
from globals import DATA_PATH, LOGGING_CONFIG
from knowledge_base.session_manager import Session, SessionStatus, SqliteSessionRepository
from knowledge_base.history import Event, EventType, SqliteEventRepository
from knowledge_base.repository import RepositoryType, KnowledgeRepositoryFactory
from knowledge_base.job_store import job_store, JobStatus, EvaluationCancelled
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
    status: Literal["PENDING", "PROCESSING", "FAILED", "CANCELLED"] = Field(
        description="Current evaluation status. `DONE` is never returned in a body; it redirects (301) to the result endpoint instead."
    )
    error: Optional[str] = Field(
        default=None,
        description="Failure reason. Only present when `status` is `FAILED`.",
    )


class CancelResponse(BaseModel):
    session_id: str
    status: Literal["CANCELLED"] = "CANCELLED"


class ErrorResponse(BaseModel):
    detail: str


# ── Background worker ──────────────────────────────────────────────────────────

def _run_evaluation(
    session_id: str,
    document_path: Path,
    filename: str,
    user_id: str,
    user_db_path: Path,
    config: PipelineConfig,
) -> None:
    """
    Runs the evaluation in a background thread.

    The document is already persisted at upload time (see evaluate_document),
    so it stays retrievable via GET /{session_id}/document while this runs.

    Status transitions written to SQLite:
        PENDING → PROCESSING (immediately on start)
        PROCESSING → DONE    (on success)
        PROCESSING → FAILED  (on error)
        PENDING/PROCESSING → CANCELLED (when the user cancels.)

    SQLite is the authoritative status store — the in-memory job_store is
    only used for fast same-process polling during the request lifecycle.
    """

    job = job_store.get(session_id)

    def is_cancelled() -> bool:
        return job is not None and job.cancel_event.is_set()

    def _transition(new_status: SessionStatus, *, expected: tuple[SessionStatus, ...]) -> bool:
        """Compare-and-set the status in SQLite. False means the guard failed (e.g. user cancelled)."""
        with sqlite3.connect(user_db_path) as db:
            return SqliteSessionRepository(db).update_status_if(session_id, new_status, expected=expected) is not None

    def _mark_terminal(new_status: SessionStatus) -> None:
        try:
            _transition(new_status, expected=(SessionStatus.PENDING, SessionStatus.PROCESSING))
        except Exception as exc:
            logger.error(f"session({session_id}): failed to persist status {new_status}: {exc}")

    def _finish_cancelled() -> None:
        _mark_terminal(SessionStatus.CANCELLED)
        if job is not None:
            job.status = JobStatus.CANCELLED
            job_store.update(job)
        logger.info(f"session({session_id}): evaluation cancelled.")

    logger.info(f"session({session_id}): starting evaluation of {filename}…")
    saved_event_ids: list[int] = []

    try:
        # Only start if still PENDING — a cancel that arrived before we started wins.
        if not _transition(SessionStatus.PROCESSING, expected=(SessionStatus.PENDING,)) or is_cancelled():
            raise EvaluationCancelled()

        if job is not None:
            job.status = JobStatus.RUNNING
            job_store.update(job)

        results = asyncio.run(evaluate_file(document_path, config, should_cancel=is_cancelled))

        if results is None:
            raise RuntimeError("Evaluation returned no results")
        if is_cancelled():
            raise EvaluationCancelled()

        # Init vector stores
        KnowledgeRepositoryFactory.create_repositories(
            RepositoryType.QDRANT, storage_path=DATA_PATH, username=user_id
        )

        # Persist findings
        with sqlite3.connect(user_db_path) as history_db:
            repo = SqliteEventRepository(history_db)
            for v in results:
                saved = repo.save(Event(
                    session_id=session_id,
                    event_type=EventType.VULNERABILITY_FINDING,
                    content=v.model_dump_json(),
                ))
                if saved.event_id is not None:
                    saved_event_ids.append(saved.event_id)

        # DONE only if still PROCESSING. If the user cancelled in the meantime, discard the findings.
        if not _transition(SessionStatus.DONE, expected=(SessionStatus.PROCESSING,)):
            with sqlite3.connect(user_db_path) as db:
                SqliteEventRepository(db).delete_events(saved_event_ids)
            raise EvaluationCancelled()

        if job is not None:
            job.status = JobStatus.DONE
            job.session_id = session_id
            job.result = results
            job_store.update(job)

        logger.info(f"session({session_id}): done — {len(results)} finding(s).")

    except EvaluationCancelled:
        _finish_cancelled()

    except Exception as exc:
        if is_cancelled():          # an error caused by shutting down shouldn't show as "failed"
            _finish_cancelled()
            return
        logger.exception(f"session({session_id}): evaluation failed — {exc}")
        _mark_terminal(SessionStatus.FAILED)
        if job is not None:
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job_store.update(job)


# ── POST /evaluate ─────────────────────────────────────────────────────────────

async def is_true_pdf(file: UploadFile) -> bool:
    import magic

    header = await file.read(2048)
    await file.seek(0) # reset file cursor
    mime_type = magic.from_buffer(header, mime=True)
    return file.filename.endswith(".pdf") and mime_type == "application/pdf"


@evaluate_router.post("/evaluate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SubmitResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Invalid file type."},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Invalid session ID."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "File evaluation unsuccessful."}
    }
)
async def evaluate_document(
    background_tasks: BackgroundTasks,
    config: Annotated[PipelineConfig, Depends(resolve_config)],
    current_user: Annotated[User, Depends(get_current_user)],
    user_path: Annotated[Path, Depends(get_user_path)],
    user_db_path: Annotated[Path, Depends(get_user_db_path)],
    uploaded_document: Annotated[UploadFile, File(description="The document to be evaluated")],
    session_id: Annotated[Optional[str], Query(description="The session ID for the document. Only set if the uploaded document is an update from the previous evaluation. If None, a new session will be created.")] = None,
) -> SubmitResponse:
    # filetype validation
    if not await is_true_pdf(uploaded_document):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only PDF files are supported.",
        )

    user_id = current_user.user_id
    filename: str = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", uploaded_document.filename or "upload.pdf")
    _session_id: str = session_id or str(uuid.uuid4())

    # Save the upload straight into the session's documents folder so it can
    # be served (GET /{session_id}/document) while the evaluation is running.
    document_dir = user_path / _session_id / "documents"
    os.makedirs(document_dir, exist_ok=True)
    saved_filename = f"{datetime.now().isoformat()}__{filename}"
    saved_path = document_dir / saved_filename

    with open(saved_path, "wb") as f:
        f.write(await uploaded_document.read())

    if not saved_path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded document",
        )

    # Create in-memory job entry
    job_store.create(key=_session_id)

    # Create / update session record in SQLite with status=PENDING.
    # Status is durable from the moment the file lands, so the frontend can
    # reconstruct it after any refresh.
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
        document_path=saved_path,
        filename=filename,
        user_id=user_id,
        user_db_path=user_db_path,
        config=config,
    )

    logger.info(f"POST /evaluate: session '{_session_id}' queued (status=pending).")
    return SubmitResponse(session_id=_session_id, status="pending")


# ── GET /{session_id}/status ───────────────────────────────────────────────────

@evaluate_router.get(
    "/{session_id}/status",
    responses={
        status.HTTP_200_OK: {
            "model": StatusResponse,
            "description": "Evaluation is pending, in progress, or failed.",
        },
        status.HTTP_301_MOVED_PERMANENTLY: {
            "description": "Evaluation is done. Redirects to `/api/v1/{session_id}/result`.",
            "headers": {
                "Location": {
                    "description": "URL of the evaluation results.",
                    "schema": {"type": "string", "example": "/api/v1/{session_id}/result"},
                }
            },
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "No session found for the given ID.",
        },
    },
)
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
        pending    → 200 {"status": "PENDING"}
        processing → 200 {"status": "PROCESSING"}
        failed     → 200 {"status": "FAILED", "error": "..."}
        done       → 301 → /{session_id}/result
        unknown    → 404
    """
    job = job_store.get(session_id)

    if job is not None:
        # Fast path: job is live in this process
        if job.status == JobStatus.DONE:
            return RedirectResponse(
                url=f"/api/v1/{session_id}/result",
                status_code=status.HTTP_301_MOVED_PERMANENTLY,
            )
        api_status = "PROCESSING" if job.status == JobStatus.RUNNING else job.status.upper()
        body = StatusResponse(
            status=api_status,
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


# ── POST /{session_id}/cancel ──────────────────────────────────────────────────

@evaluate_router.post(
    "/{session_id}/cancel",
    response_model=CancelResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "No session found for the given ID."},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Evaluation already finished (done/failed)."},
    },
)
def cancel_evaluation(
    session_id: Annotated[str, PathParam()],
    current_user: Annotated[User, Depends(get_current_user)],
    user_db_path: Annotated[Path, Depends(get_user_db_path)],
) -> CancelResponse:
    """
    Request cancellation of a pending/processing evaluation.

    Idempotent: cancelling an already-cancelled session returns 200.
    Works even if no live job exists (e.g. after a server restart left the
    session stuck in "processing").
    """
    if not user_db_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No session found for '{session_id}'.")

    with sqlite3.connect(user_db_path) as db:
        repo = SqliteSessionRepository(db)
        session = repo.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No session found for '{session_id}'.")
        if session.status == SessionStatus.CANCELLED:
            return CancelResponse(session_id=session_id)

        updated = repo.update_status_if(
            session_id,
            SessionStatus.CANCELLED,
            expected=(SessionStatus.PENDING, SessionStatus.PROCESSING),
        )

    if updated is None:  # finished (or failed) before we could cancel
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This evaluation has already finished and can't be cancelled.",
        )

    job = job_store.get(session_id)
    if job is not None:
        job.cancel_event.set()
        job.status = JobStatus.CANCELLED
        job_store.update(job)

    logger.info(f"POST /{session_id}/cancel: cancellation requested.")
    return CancelResponse(session_id=session_id)


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
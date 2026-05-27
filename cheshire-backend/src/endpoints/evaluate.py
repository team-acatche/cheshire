import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Annotated, AsyncGenerator, Optional
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
from knowledge_base.session_manager import Session, SqliteSessionRepository
from knowledge_base.history import Event, EventType, SqliteEventRepository
from knowledge_base.repository import RepositoryType, KnowledgeRepositoryFactory
from knowledge_base.job_store import job_store, JobStatus
from auth.db_access import get_history
from auth.models import User
from auth.dependencies import get_current_user
from dependencies.sessions import get_user_path, get_user_db_path

evaluate_router = APIRouter()
logger = logging.getLogger("uvicorn.error")


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────


class SubmitResponse(BaseModel):
    """Returned immediately (HTTP 202) - gives the client the session_id to poll"""
    session_id: str
    status: str = "PENDING"

class StatusResponse(BaseModel):
    """Return by the status endpoint while the job is still in progress"""
    status: str
    error: Optional[str] = None

# ─────────────────────────────────────────────────────────────────────────────
# Background Worker
# ─────────────────────────────────────────────────────────────────────────────


def _run_evaluation(
    session_id: str,
    tmp_file_path: Path,
    filename: str,
    user_id: str,
    user_path: Path,
    user_db_path: Path,
    config: PipelineConfig,
) -> None:
    import asyncio

    logger.info(f"session({session_id}): evaluating {filename}…")
    job = job_store.get(session_id)
    if job is None:
        logger.error(f"Job not found for session {session_id}. Aborting evaluation.")
        return
    
    job.status = JobStatus.RUNNING
    job_store.update(job)

    try:
        logger.info(f"session({session_id}): evaluating {filename}...")
        results = asyncio.run(evaluate_file(tmp_file_path, config))

        if results is None:
            raise RuntimeError("Evaluation failed with no results")
            
        # Persist document
        document_path = user_path / session_id / "documents"
        saved_filename = f"{datetime.now().isoformat()}__{filename}"
        os.makedirs(document_path, exist_ok=True)
        shutil.move(tmp_file_path, document_path / saved_filename)
        logger.info(f"run_evaluation({filename}): {filename} saved to {document_path}.")

        # Persist session
        with sqlite3.connect(user_db_path) as session_db:
            SqliteSessionRepository(session_db).save_new_session(
                Session(session_id=session_id, title=filename)
            )

        # Init vector stores
        KnowledgeRepositoryFactory.create_repositories(
            RepositoryType.QDRANT, storage_path=DATA_PATH, username=user_id
        )

        # Persist findings
        with sqlite3.connect(user_path / f"{user_id}.sqlite") as history_db:
            repo = SqliteEventRepository(history_db)
            for v in results:
                repo.save(Event(
                    session_id=session_id,
                    event_type=EventType.VULNERABILITY_FINDING,
                    content=v.model_dump_json(),
                ))
        
        job.status = JobStatus.DONE
        job.session_id = session_id
        job.result = results
        job_store.update(job)
        logger.info(f"session({session_id}): done - {len(results)} finding(s).")
            
    except Exception as exc:
        logger.exception(f"session({session_id}): failed - {exc}")
        job.status = JobStatus.FAILED
        job.error = str(exc)
        job_store.update(job)
        tmp_file_path.unlink(missing_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# POST /evaluate -> 202 Accepted {"session_id": "...", "status": "PENDING"}
# ─────────────────────────────────────────────────────────────────────────────
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

    """
    Stream the evaluation progress as Server-Sent Events.

    Event types emitted:
        * status   - {"message": str}       progress updates
        * result   - {"session_id: str, "vulnerabilities: [...]} final payload
        * error    - {"message": str}       fatal error
    """
    user_id = current_user.user_id
    filename: str = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", uploaded_document.filename or "upload.pdf"
    )
    _session_id: str = session_id or str(uuid.uuid4())

    # Buffer the upload now - background task runs after response is sent
    # save the file into a temporary directory
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(await uploaded_document.read())
    tmp.flush()
    tmp.close()
    tmp_path = Path(tmp.name)

    if not tmp_path.exists():
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save uploaded document")

    job_store.create(key=_session_id)

    background_tasks.add_task(
        _run_evaluation,
        session_id=_session_id,
        tmp_file_path=tmp_path,
        filename=filename,
        user_id=current_user.user_id,
        user_path=user_path,
        user_db_path=user_db_path,
        config=config,
    )

    # save session immediately
    with sqlite3.connect(user_db_path) as session_db:
        session_repo = SqliteSessionRepository(session_db)
        # if session already exists, just update title (background task updates results)
        if session_id:
            session_repo.change_title(_session_id, new_title=filename)
        else:
            session_repo.save_new_session(Session(session_id=_session_id, title=filename))

    logger.info(f"POST /evaluate: session '{_session_id}' queued.")
    return SubmitResponse(session_id=_session_id, status="PENDING")

# ─────────────────────────────────────────────────────────────────────────────
# GET /evaluate/{session_id}/status
#
# Job in progress: 200 -> {"status": "PENDING" | "RUNNING"}
# Job failed: 200 -> {"status": "FAILED", "error": "..."}
# Job done: 301 -> Location: /evaluate/{session_id}/result
# ─────────────────────────────────────────────────────────────────────────────

@evaluate_router.get("/{session_id}/status")
def get_evaluation_status(
    session_id: Annotated[str, PathParam()],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    job = job_store.get(session_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"No evaluation job found for session_id '{session_id}'.",
        )
    
    if job.status == JobStatus.DONE:
        return RedirectResponse(
            url=f"/api/v1/{session_id}/result",
            status_code=status.HTTP_301_MOVED_PERMANENTLY,
        )
    
    body = StatusResponse(
        status=job.status.upper(),
        error=job.error if job.status == JobStatus.FAILED else None,
    )
    return Response(
        content=body.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
    )


def _get_latest(session_path: Path) -> str:
    latest_filename: Optional[str] = None
    latest: Optional[datetime] = None
    for root, _, filenames in os.walk(session_path / "documents"):
        for filename in filenames:
            if filename.endswith(".pdf"):
                timestamp = datetime.fromisoformat(filename.split("__")[0])
                if latest is None or timestamp > latest:
                    latest = timestamp
                    latest_filename = filename
    if latest is None or latest_filename is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No documents found for this session")

    return latest_filename
    

@evaluate_router.get("/{session_id}/result")
def get_latest_evaluation_results(
    current_user: Annotated[User, Depends(get_current_user)],
    history_db_path: Annotated[Path, Depends(get_user_db_path)],
    session_id: Annotated[str, PathParam(description="The session ID for the document.")],
) -> list[VulnerabilityDetails]:
    if not history_db_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Connect to repositories
    with sqlite3.connect(history_db_path) as history_db:
        history_repo = SqliteEventRepository(history_db)
        findings_history: list[Event] = history_repo.get_recent(session_id=session_id, event_types=[EventType.VULNERABILITY_FINDING])
        return [VulnerabilityDetails.model_validate_json(event.content) for event in findings_history]

@evaluate_router.get("/{session_id}/document")
def get_document(
    current_user: Annotated[User, Depends(get_current_user)],
    user_path: Annotated[Path, Depends(get_user_path)],
    session_id: Annotated[str, PathParam(description="The session ID for the document.")],
) -> Response:
    session_path = user_path / session_id
    latest_document = session_path / "documents" / _get_latest(session_path)
    if not latest_document.exists():
        return Response(status_code=status.HTTP_404_NOT_FOUND, content=f"Document for session {session_id} not found")
    return FileResponse(latest_document, media_type="application/pdf")

import aiofiles
import os
import tempfile
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
    Depends,
    UploadFile,
    File,
    HTTPException,
    Form,
    Path as PathParam,
    Query,
)
from fastapi.responses import FileResponse, Response

from dotenv import load_dotenv
from pydantic import BaseModel

from model import evaluate_file
from tools.helpers.output_schema import VulnerabilityDetails
from cheshire_configs.core import PipelineConfig
from cheshire_configs.resolver import resolve_config
from knowledge_base.session_manager import Session, SqliteSessionRepository
from knowledge_base.history import Event, EventType, SqliteEventRepository, EventRepository
from endpoints.helpers import get_or_create_vector_stores
from auth.db_access import get_history

load_dotenv()
SESSION_DIR = os.path.expanduser(os.path.expandvars(os.getenv("SESSIONS_PATH", "")))

evaluate_router = APIRouter()
logger = logging.getLogger("uvicorn.error")

class EvaluateResponse(BaseModel):
    session_id: str
    vulnerabilities: list[VulnerabilityDetails]

@evaluate_router.post("/{username}/evaluate")
async def evaluate_document(
    config: Annotated[PipelineConfig, Depends(resolve_config)],
    username: Annotated[str, PathParam(description="The username of the user")],
    uploaded_document: Annotated[UploadFile, File(description="The document to be evaluated")],
    session_id: Annotated[Optional[str], Query(description="The session ID for the document. Only set if the uploaded document is an update from the previous evaluation. If None, a new session will be created.")] = None,
) -> EvaluateResponse:
    if not SESSION_DIR:
        raise HTTPException(status_code=500, detail="SESSION_DIR not set within the server")

    filename: str = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", uploaded_document.filename or "upload.pdf")

    # save the file into a temporary directory
    tmp_file_path: Path
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp_file:
        tmp_file.write(await uploaded_document.read())
        tmp_file_path = Path(tmp_file.name)

        assert tmp_file_path and tmp_file_path.exists(), "Failed to save uploaded document"
        logger.debug(f"save({filename}): Auditing {filename}...")
        results = await evaluate_file(tmp_file_path, config)
        logger.info(f"save({filename}): {filename} audited.")
    
    if results is None:
        raise HTTPException(status_code=500, detail="Failed to evaluate document")
    
    # Save the uploaded document
    _session_id: str = session_id or str(uuid.uuid4())
    user_path = Path(SESSION_DIR) / username

    document_path = user_path / _session_id / "documents" / f"{datetime.now().isoformat()}__{filename}"

    if session_id is None:
        # create new session
        os.makedirs(os.path.dirname(document_path), exist_ok=True)
        logger.info(f"save({filename}): Saving {filename} to {document_path}...")
        async with aiofiles.open(document_path, "wb") as d:
            await d.write(await uploaded_document.read())
        logger.info(f"save({filename}): {document_path} saved.")

        # Initialize session DB
        logger.debug(f"save({filename}): Saving {filename} as a new session...")
        with sqlite3.connect(user_path / f"{username}.sqlite") as session_db:
            session_repo = SqliteSessionRepository(session_db)
            session_repo.save_new_session(Session(session_id=_session_id, title=filename))
        logger.info(f"save({filename}): {filename} saved as a new session.")

        # Initialize vector stores
        logger.debug(f"save({filename}): Initializing vector stores for {filename}...")
        await get_or_create_vector_stores(user_path, username=username)
        logger.info(f"save({filename}): Vector stores for {filename} initialized.")

    # Save results as first event in {username}.sqlite
    with sqlite3.connect(user_path / f"{username}.sqlite") as history_db:
        logger.debug(f"save({filename}): Saving results in {username}.sqlite...")
        history_repo = SqliteEventRepository(history_db)
        for vulnerability in results:
            history_repo.save(Event(
                session_id=_session_id,
                event_type=EventType.VULNERABILITY_FINDING,
                content=vulnerability.model_dump_json()
            ))
        logger.info(f"save({filename}): Results saved in {username}.sqlite.")

    return EvaluateResponse(session_id=_session_id, vulnerabilities=results)


def _get_latest(session_path: Path) -> str:
    timestamps = {}
    for root, _, filenames in os.walk(session_path / "documents"):
        for filename in filenames:
            if filename.endswith(".pdf"):
                timestamps[datetime.fromisoformat(filename.split("__")[0])] = filename
    return timestamps[max(timestamps)]
    

@evaluate_router.get("/{session_id}/result")
async def get_latest_evaluation_results(
    history: Annotated[EventRepository, Depends(get_history)],
    session_id: Annotated[str, PathParam(description="The session ID for the document.")]
) -> list[VulnerabilityDetails]:
    findings_history: list[Event] = history.get_recent(session_id=session_id, event_types=[EventType.VULNERABILITY_FINDING])
    return [VulnerabilityDetails.model_validate_json(event.content) for event in findings_history]

@evaluate_router.get("/{session_id}/document")
async def get_document(
    session_id: Annotated[str, PathParam(description="The session ID for the document.")]
) -> Response:
    latest_document = Path(SESSION_DIR) / session_id / "documents" / _get_latest(Path(SESSION_DIR) / session_id)
    if not latest_document.exists():
        return Response(status_code=404, content=f"Document for session {session_id} not found")
    return FileResponse(latest_document, media_type="application/pdf")
    
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
import shutil

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
from auth.models import User
from auth.dependencies import get_current_user

load_dotenv()
SESSION_DIR = os.path.expanduser(os.path.expandvars(os.getenv("SESSIONS_PATH", "")))

evaluate_router = APIRouter()
logger = logging.getLogger("uvicorn.error")

class EvaluateResponse(BaseModel):
    session_id: str
    vulnerabilities: list[VulnerabilityDetails]

@evaluate_router.post("/evaluate")
async def evaluate_document(
    config: Annotated[PipelineConfig, Depends(resolve_config)],
    current_user: Annotated[User, Depends(get_current_user)],
    uploaded_document: Annotated[UploadFile, File(description="The document to be evaluated")],
    session_id: Annotated[Optional[str], Query(description="The session ID for the document. Only set if the uploaded document is an update from the previous evaluation. If None, a new session will be created.")] = None,
) -> EvaluateResponse:
    if not SESSION_DIR:
        raise HTTPException(status_code=500, detail="SESSION_DIR not set within the server")

    username = current_user.username
    filename: str = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", uploaded_document.filename or "upload.pdf")

    _session_id: str = session_id or str(uuid.uuid4())
    user_path = Path(SESSION_DIR) / username

    # save the file into a temporary directory
    tmp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp_file.write(await uploaded_document.read())
    tmp_file.flush()
    tmp_file_path = Path(tmp_file.name)

    assert tmp_file_path and tmp_file_path.exists(), "Failed to save uploaded document"

    logger.debug(f"save({filename}): Auditing {filename}...")
    results = await evaluate_file(tmp_file_path, config)
    if results is None:
        raise HTTPException(status_code=500, detail="Failed to evaluate document")
    logger.info(f"save({filename}): {filename} audited.")

    # Create new session
    document_path = user_path / _session_id / "documents"
    saved_filename = f"{datetime.now().isoformat()}__{filename}"
    logger.info(f"save({filename}): Saving {filename} to {document_path}...")
    os.makedirs(document_path, exist_ok=True)
    shutil.move(tmp_file_path, document_path / saved_filename)
    logger.info(f"save({filename}): {document_path} saved.")
    
    # Save the uploaded document
    if session_id is None:
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
        raise HTTPException(status_code=404, detail="No documents found for this session")

    return latest_filename
    

@evaluate_router.get("/{session_id}/result")
def get_latest_evaluation_results(
    session_id: Annotated[str, PathParam(description="The session ID for the document.")],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[VulnerabilityDetails]:
    if not SESSION_DIR:
        raise HTTPException(status_code=500, detail="SESSION_DIR not set within the server")

    username = current_user.username
    user_path = Path(SESSION_DIR) / username
    history_db_path = user_path / f"{username}.sqlite"
    
    if not history_db_path.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    # Connect to repositories
    with sqlite3.connect(history_db_path) as history_db:
        history_repo = SqliteEventRepository(history_db)
        findings_history: list[Event] = history_repo.get_recent(session_id=session_id, event_types=[EventType.VULNERABILITY_FINDING])
        return [VulnerabilityDetails.model_validate_json(event.content) for event in findings_history]

@evaluate_router.get("/{session_id}/document")
def get_document(
    session_id: Annotated[str, PathParam(description="The session ID for the document.")],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    username = current_user.username
    session_path = Path(SESSION_DIR) / username / session_id
    latest_document = session_path / "documents" / _get_latest(session_path)
    if not latest_document.exists():
        return Response(status_code=404, content=f"Document for session {session_id} not found")
    return FileResponse(latest_document, media_type="application/pdf")
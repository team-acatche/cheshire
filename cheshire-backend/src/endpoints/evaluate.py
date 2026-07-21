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
    status,
)
from fastapi.responses import FileResponse, Response

from dotenv import load_dotenv
from pydantic import BaseModel

from model import evaluate_file
from tools.helpers.output_schema import VulnerabilityDetails
from cheshire_configs.core import PipelineConfig
from cheshire_configs.resolver import resolve_config
from globals import DATA_PATH
from knowledge_base.session_manager import Session, SqliteSessionRepository
from knowledge_base.history import Event, EventType, SqliteEventRepository, EventRepository
from knowledge_base.repository import RepositoryType, KnowledgeRepositoryFactory
from auth.db_access import get_history
from auth.models import User
from auth.dependencies import get_current_user
from dependencies.sessions import get_user_path, get_user_db_path

evaluate_router = APIRouter()
logger = logging.getLogger("uvicorn.error")

class EvaluateResponse(BaseModel):
    session_id: str
    vulnerabilities: list[VulnerabilityDetails]

@evaluate_router.post("/evaluate")
async def evaluate_document(
    config: Annotated[PipelineConfig, Depends(resolve_config)],
    current_user: Annotated[User, Depends(get_current_user)],
    user_path: Annotated[Path, Depends(get_user_path)],
    user_db_path: Annotated[Path, Depends(get_user_db_path)],
    uploaded_document: Annotated[UploadFile, File(description="The document to be evaluated")],
    session_id: Annotated[Optional[str], Query(description="The session ID for the document. Only set if the uploaded document is an update from the previous evaluation. If None, a new session will be created.")] = None,
) -> EvaluateResponse:
    user_id = current_user.user_id
    filename: str = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", uploaded_document.filename or "upload.pdf")

    _session_id: str = session_id or str(uuid.uuid4())

    # save the file into a temporary directory
    tmp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp_file.write(await uploaded_document.read())
    tmp_file.flush()
    tmp_file_path = Path(tmp_file.name)

    assert tmp_file_path and tmp_file_path.exists(), "Failed to save uploaded document"

    logger.debug(f"save({filename}): Auditing {filename}...")
    results = await evaluate_file(tmp_file_path, config)
    if results is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to evaluate document")
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
        with sqlite3.connect(user_db_path) as session_db:
            session_repo = SqliteSessionRepository(session_db)
            session_repo.save_new_session(Session(session_id=_session_id, title=filename))
        logger.info(f"save({filename}): {filename} saved as a new session.")

        # Initialize vector stores
        logger.debug(f"save({filename}): Initializing vector stores for {filename}...")
        KnowledgeRepositoryFactory.create_repositories(
            RepositoryType.QDRANT, 
            storage_path=DATA_PATH, 
            username=user_id
        )
        logger.info(f"save({filename}): Vector stores for {filename} initialized.")

    # Save results as first event in {user_id}.sqlite
    with sqlite3.connect(user_path / f"{user_id}.sqlite") as history_db:
        logger.debug(f"save({filename}): Saving results in {user_id}.sqlite...")
        history_repo = SqliteEventRepository(history_db)
        for vulnerability in results:
            history_repo.save(Event(
                session_id=_session_id,
                event_type=EventType.VULNERABILITY_FINDING,
                content=vulnerability.model_dump_json()
            ))
        logger.info(f"save({filename}): Results saved in {user_id}.sqlite.")

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

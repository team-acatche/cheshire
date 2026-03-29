import os
import tempfile
from pathlib import Path
from typing import Annotated, Literal, Optional
import aiofiles
import logging
import uuid
from datetime import datetime
import re

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form
from dotenv import load_dotenv

from model import evaluate_file
from tools.helpers.output_schema import VulnerabilityDetails
from cheshire_configs.core import PipelineConfig
from cheshire_configs.resolver import resolve_config
from knowledge_base.session_manager import Session, SqliteSessionRepository
from knowledge_base.history import Event, EventType, SqliteEventRepository
import sqlite3
from endpoints.helpers import create_vector_stores

load_dotenv()
SESSION_DIR = os.path.expanduser(os.path.expandvars(os.getenv("SESSIONS_PATH", ""))) if os.getenv("SESSIONS_PATH") else None

evaluate_router = APIRouter()
logger = logging.getLogger("uvicorn.error")

# class EvaluateBody(BaseModel):
#     """
#     Body for the /evaluate endpoint.
#     """
#     username: str = Field(..., description="The username of the user")
#     uploaded_document: UploadFile = Field(..., description="The document to be evaluated")
#     session_id: Optional[str] = Field(None, description="The session ID for the document. Only set if the uploaded document is an update from the previous evaluation. If None, a new session will be created.")

@evaluate_router.post("/evaluate")
async def evaluate_document(
    config: Annotated[PipelineConfig, Depends(resolve_config)],
    uploaded_document: Annotated[UploadFile, File(description="The document to be evaluated")],
    username: Annotated[str, Form(description="The username of the user")],
    session_id: Annotated[Optional[str], Form(description="The session ID for the document. Only set if the uploaded document is an update from the previous evaluation. If None, a new session will be created.")] = None,
) -> list[VulnerabilityDetails]:
    if SESSION_DIR is None:
        raise HTTPException(status_code=500, detail="SESSION_DIR not set")
    
    # Save the uploaded document
    _session_id: str = session_id or str(uuid.uuid4())
    filename: str = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", uploaded_document.filename or "upload")
    document_path = Path(SESSION_DIR) / username / _session_id / "documents" / f"{datetime.now().isoformat()}__{filename}"

    session_path = Path(SESSION_DIR) / username / _session_id
    if session_id is None:
        # create new session
        os.makedirs(os.path.dirname(document_path), exist_ok=True)
        # Initialize session DB
        with sqlite3.connect(session_path / "session_metadata.sqlite") as session_db:
            session_repo = SqliteSessionRepository(session_db)
            session_repo.save_new_session(Session(session_id=_session_id, title=filename))
        
        # Initialize vector store
        await create_vector_stores(session_path)

    logger.info(f"save({filename}): Saving {filename} to {document_path}...")
    async with aiofiles.open(document_path, "wb") as d:
        await d.write(await uploaded_document.read())
    logger.info(f"save({filename}): {document_path} saved.")

    if results := await evaluate_file(Path(document_path), config):
        # Save results as first event in history.sqlite
        with sqlite3.connect(session_path / "history.sqlite") as history_db:
            history_repo = SqliteEventRepository(history_db)
            summary = "\n".join([f"- {v.title}: {v.description[:100]}..." for v in results])
            history_repo.save(Event(
                session_id=_session_id,
                event_type=EventType.RESPONSE,
                content=f"Evaluation complete. Found {len(results)} vulnerabilities:\n{summary}"
            ))
        return results
    else:
        return []

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
from sse_starlette.sse import EventSourceResponse

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


# ------------------------------------------------------------------------
# SSE helpers
# ------------------------------------------------------------------------

def _sse_event(event: str, data: dict | str) -> dict:
    """Return a dict that sse_starlette understands."""
    return {
        "event": event,
        "data": json.dumps(data) if isinstance(data, dict) else data,
    }

@evaluate_router.post("/evaluate")
async def evaluate_document(
    config: Annotated[PipelineConfig, Depends(resolve_config)],
    current_user: Annotated[User, Depends(get_current_user)],
    uploaded_document: Annotated[UploadFile, File(description="The document to be evaluated")],
    user_path: Annotated[Path, Depends(get_user_path)],
    user_db_path: Annotated[Path, Depends(get_user_db_path)],
    session_id: Annotated[
        Optional[str], 
        Query(description="The session ID for the document. Only set if the uploaded document is an update from the previous evaluation. If None, a new session will be created."),
        ] = None,
) -> EventSourceResponse:

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

    file_bytes = await uploaded_document.read()

    async def event_stream() -> AsyncGenerator[dict, None]:
        tmp_path: Optional[Path] = None
        try:
            # —— 1. Save to temp file ——————————————————————————————————————————
            yield _sse_event("status", {"message": "Saving uploaded document..."})
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.write(file_bytes)
            tmp.flush()
            tmp_path = Path(tmp.name)
            tmp.close()

            # —— 2. Run the AI audit ———————————————————————————————————————————
            yield _sse_event("status", {"message": "Starting AI security audit… this may take a few minutes."})
 
            # Cloudflare 524s if the origin is silent for >100s.
            # Run evaluate_file in a background task and ping every 30s so
            # Cloudflare sees continuous bytes on the connection.
            keepalive_queue: asyncio.Queue = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def _run_evaluate_sync() -> None:
                try:
                    # evaluate_file is async, so run it in its own event loop
                    # inside this worker thread.
                    res = asyncio.run(evaluate_file(tmp_path, config))

                    loop.call_soon_threadsafe(keepalive_queue.put_nowait, res)
                except Exception as exc:
                    loop.call_soon_threadsafe(keepalive_queue.put_nowait, exc)

            asyncio.create_task(asyncio.to_thread(_run_evaluate_sync))
 
            results = None
            while True:
                try:
                    item = await asyncio.wait_for(keepalive_queue.get(), timeout=30)
                    if isinstance(item, Exception):
                        raise item
                    results = item
                    break
                except asyncio.TimeoutError:
                    yield _sse_event("status", {
                        "message": "Still analyzing document… please wait."
                    })
 
 
            if results is None:
                yield _sse_event("error", {"message": "Evaluation returned no results. Is the file a valid PDF?"})
                return
 
            yield _sse_event("status", {"message": f"Audit complete — {len(results)} finding(s) identified. Saving…"})

            # —— 3. Persist session + document —————————————————————————————————
            document_path = user_path / _session_id / "documents"
            saved_filename = f"{datetime.now().isoformat()}__{filename}"
            logger.info(f"save({filename}): Saving {filename} to {document_path}...")
            os.makedirs(document_path, exist_ok=True)
            shutil.move(str(tmp_path), str(document_path / saved_filename))
            logger.info(f"save({filename}): {document_path} saved.")
            tmp_path = None

            if session_id is None:
                # Initialize session DB
                with sqlite3.connect(user_db_path) as session_db:
                    session_repo = SqliteSessionRepository(session_db)
                    session_repo.save_new_session(
                        Session(session_id=_session_id, title=filename)
                    )
                
                # Initialize vector stores
                logger.debug(f"save({filename}): Initializing vector stores for {filename}...")
                KnowledgeRepositoryFactory.create_repositories(
                    RepositoryType.QDRANT,
                    storage_path=DATA_PATH,
                    username=user_id,
                )
                logger.info(f"save({filename}): Vector stores for {filename} initialized.")

            # ── 4. Persist findings ─────────────────────────────────────────
            # Save results as first event in {user_id}.sqlite
            with sqlite3.connect(user_path / f"{user_id}.sqlite") as history_db:
                logger.debug(f"save({filename}): Saving results in {user_id}.sqlite...")
                history_repo = SqliteEventRepository(history_db)
                for vulnerability in results:
                    history_repo.save(
                        Event(
                        session_id=_session_id,
                        event_type=EventType.VULNERABILITY_FINDING,
                        content=vulnerability.model_dump_json()
                        )
                    )
                logger.info(f"save({filename}): Results saved in {user_id}.sqlite.")

            # ── 5. Emit final result ────────────────────────────────────────
            yield _sse_event(
                "result",
                {
                    "session_id": _session_id,
                    "vulnerabilities": [v.model_dump() for v in results],
                },
            )
        
        except Exception as exc:
            import traceback
            logger.error(f"evaluate_document SSE error: {exc}\n{traceback.format_exc()}")
            yield _sse_event("error", {"message": str(exc)})

        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    return EventSourceResponse(
        event_stream(),
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
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
    session_id: Annotated[str, PathParam(description="The session ID for the document.")],
    current_user: Annotated[User, Depends(get_current_user)],
    history_db_path: Annotated[Path, Depends(get_user_db_path)],
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
    session_id: Annotated[str, PathParam(description="The session ID for the document.")],
    current_user: Annotated[User, Depends(get_current_user)],
    user_path: Annotated[Path, Depends(get_user_path)],
) -> Response:
    session_path = user_path / session_id
    latest_document = session_path / "documents" / _get_latest(session_path)
    if not latest_document.exists():
        return Response(status_code=status.HTTP_404_NOT_FOUND, content=f"Document for session {session_id} not found")
    return FileResponse(latest_document, media_type="application/pdf")

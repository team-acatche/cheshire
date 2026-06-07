import asyncio
import json
import logging
import shutil
import sqlite3
from contextvars import copy_context
from pathlib import Path
from typing import Annotated, AsyncGenerator, Optional, cast
from uuid import UUID

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from haystack.components.agents import Agent
from haystack.dataclasses import ChatMessage, StreamingChunk
from haystack.tools import Tool, Toolset

from auth.dependencies import get_current_user
from auth.models import User
from cheshire_configs.core import PipelineConfig
from cheshire_configs.resolver import resolve_config
from dependencies.sessions import get_user_db_path, get_user_path
from globals import DATA_PATH
from knowledge_base.history import Event, EventType, SqliteEventRepository
from knowledge_base.repository import KnowledgeRepositoryFactory, RepositoryType
from knowledge_base.session_manager import Session, SqliteSessionRepository
from tools.chat_tools import read_vulnerabilities_from_event_store
from tools.exa import web_search
from tools.knowledge import (
    KnowledgeState,
    current_knowledge_state,
    get_facts,
    get_relevant_facts,
    upsert_fact,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn.error")

chat_router = APIRouter()

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

KEEPALIVE_INTERVAL = 30  # seconds — well under Cloudflare's 100s free-plan limit

class ChatBody(BaseModel):
    message: str

class RenameBody(BaseModel):
    new_title: str

# In-memory SSE resume state.
# Works per-process only. Use Redis for multi-replica deployments.
_session_token_buffers: dict[str, list[tuple[int, str]]] = {}
_session_agent_tasks: dict[str, asyncio.Task] = {}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _open_db(path: Path) -> tuple[sqlite3.Connection, SqliteEventRepository]:
    """Open a SQLite connection and return it with its event repo."""
    conn = sqlite3.connect(path)
    return conn, SqliteEventRepository(conn)


# ── Routes ─────────────────────────────────────────────────────────────────────

@chat_router.get("/")
async def get_sessions(
    current_user: Annotated[User, Depends(get_current_user)],
    session_db_path: Annotated[Path, Depends(get_user_db_path)],
) -> list[Session]:
    """
    Returns all sessions for the current user, ordered by created_at DESC.
 
    Each Session now includes a `status` field:
        "pending"    — uploaded, not yet picked up by the worker
        "processing" — worker is actively evaluating
        "done"       — evaluation complete, results available
        "failed"     — evaluation failed
 
    The frontend uses this to restore the sidebar state after a refresh
    without relying on sessionStorage.
    """
    if not session_db_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    with sqlite3.connect(session_db_path) as db:
        return SqliteSessionRepository(db).get_sessions()


@chat_router.get("/{session_id}")
async def chat_history(
    current_user: Annotated[User, Depends(get_current_user)],
    history_db_path: Annotated[Path, Depends(get_user_db_path)],
    session_id: str,
):
    if not history_db_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    with sqlite3.connect(history_db_path) as db:
        recent_events = SqliteEventRepository(db).get_recent(session_id, 1000)
        messages = [e.to_chat_message() for e in reversed(recent_events)]
        return {"messages": messages}


@chat_router.post("/{session_id}")
async def chat(
    current_user: Annotated[User, Depends(get_current_user)],
    config: Annotated[PipelineConfig, Depends(resolve_config)],
    user_path: Annotated[Path, Depends(get_user_path)],
    history_db_path: Annotated[Path, Depends(get_user_db_path)],
    session_id: str,
    body: ChatBody,
    last_event_id: Annotated[Optional[str], Header(alias="last-event-id")] = None,
) -> EventSourceResponse:
    """
    Stream the agent response as Server-Sent Events.

    Event types:
      token   {"content": str}   incremental chunk       id = monotonic int
      done    {"content": str}   full canonical text     id = "done"
      error   {"message": str}   agent/server error
      comment keepalive ping — invisible to client, resets Cloudflare timer
    """
    user_id = current_user.user_id

    if not history_db_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # ── Resume path ────────────────────────────────────────────────────────
    if last_event_id is not None:
        async def resume_stream() -> AsyncGenerator[dict, None]:
            resume_from = int(last_event_id) if last_event_id.isdigit() else -1
            buffer = _session_token_buffers.get(session_id, [])

            # Replay any tokens the client missed
            for event_id, token in buffer:
                if event_id > resume_from:
                    yield {"event": "token", "id": str(event_id), "data": json.dumps({"content": token})}

            task = _session_agent_tasks.get(session_id)

            if task and not task.done():
                # Agent still running — keep the resume connection alive with
                # keepalives so Cloudflare doesn't drop it while we wait.
                while not task.done():
                    try:
                        await asyncio.wait_for(asyncio.shield(task), timeout=KEEPALIVE_INTERVAL)
                    except asyncio.TimeoutError:
                        yield {"comment": "keepalive"}
                    except Exception:
                        break

                # Task finished — emit any tokens buffered since reconnect
                new_buffer = _session_token_buffers.get(session_id, [])
                replayed_ids = {eid for eid, _ in buffer if eid > resume_from}
                for event_id, token in new_buffer:
                    if event_id not in replayed_ids and event_id > resume_from:
                        yield {"event": "token", "id": str(event_id), "data": json.dumps({"content": token})}

            # Agent finished — serve final response from SQLite
            with sqlite3.connect(history_db_path) as db:
                events = SqliteEventRepository(db).get_recent(
                    session_id, k=1, event_types=[EventType.RESPONSE]
                )
                if events:
                    yield {"event": "done", "id": "done", "data": json.dumps({"content": events[0].content})}

        return EventSourceResponse(resume_stream(), headers=SSE_HEADERS)

    # ── Fresh request path ─────────────────────────────────────────────────
    # All DB work before the executor happens on the main async thread.
    setup_db, setup_repo = _open_db(history_db_path)
    try:
        setup_repo.save(Event(
            session_id=session_id,
            event_type=EventType.USER_MESSAGE,
            content=body.message,
        ))

        event_repo, knowledge_repo = KnowledgeRepositoryFactory.create_repositories(
            RepositoryType.QDRANT, storage_path=DATA_PATH, username=user_id,
        )

        recent_events = setup_repo.get_recent(session_id, 1000)
        event_repo.save([e.to_document() for e in recent_events])

        messages: list[ChatMessage] = []
        last_tool_call = None
        for e in reversed(recent_events):
            if e.event_type == EventType.TOOL_CALL:
                msg = e.to_chat_message()
                last_tool_call = msg.tool_calls[0] if msg.tool_calls else None
                messages.append(msg)
            elif e.event_type == EventType.TOOL_CALL_RESULT:
                messages.append(e.to_chat_message(last_tool_call))
            else:
                messages.append(e.to_chat_message())

    except Exception:
        setup_db.close()
        raise
    finally:
        # Close the setup connection — each subsequent DB write gets its own.
        setup_db.close()

    state = KnowledgeState(UUID(session_id), knowledge_repo, event_repo)
    knowledge_tools = [
        read_vulnerabilities_from_event_store,
        upsert_fact, get_facts, get_relevant_facts, web_search,
    ]

    token_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
    _session_token_buffers[session_id] = []

    async def event_stream() -> AsyncGenerator[dict, None]:
        loop = asyncio.get_running_loop()
        full_response: list[str] = []
        event_counter = 0

        def enqueue_chunk(chunk: StreamingChunk) -> None:
            """Called from executor thread — must use call_soon_threadsafe."""
            if chunk.content:
                loop.call_soon_threadsafe(token_queue.put_nowait, chunk.content)

        async def run_agent() -> None:
            knowledge_token = current_knowledge_state.set(state)
            try:
                agent = Agent(
                    chat_generator=config.model,
                    system_prompt="""Expert Security Auditor. Goal: interpret/act on external evaluator findings.

HIERARCHY OF TRUTH (Top=Authority):
1. KNOWLEDGE BASE (KB): GROUND TRUTH. Result OVERRIDES chat history.
2. EVALUATOR FINDINGS: Primary context.
3. INTERNAL STANDARDS: Company policies.
4. WEB SEARCH: External context.
5. CHAT HISTORY: Context only. NEVER override KB.

PROTOCOL:
- SEARCH: Call `get_relevant_facts` FIRST. Result = Current Reality.
- EVALUATE: If history contradicts KB, KB WINS. State KB fact as authority.
- MEMORIZE: Call `upsert_fact` INSTANTLY for new policies/standards or corrections to wrong facts.
- ADVISE: Technical advice must follow KB policy.""",
                    tools=Toolset([cast(Tool, tool) for tool in knowledge_tools]),
                    streaming_callback=enqueue_chunk,
                )
                ctx = copy_context()
                await loop.run_in_executor(
                    None,
                    lambda: ctx.run(
                        agent.run,
                        messages=[*messages, ChatMessage.from_user(body.message)],
                    ),
                )
            except Exception as exc:
                import traceback
                logger.error("Agent error: %s\n%s", exc, traceback.format_exc())
                raise
            finally:
                current_knowledge_state.reset(knowledge_token)
                # call_soon_threadsafe because finally runs in the executor thread
                loop.call_soon_threadsafe(token_queue.put_nowait, None)

        agent_task = asyncio.create_task(run_agent())
        _session_agent_tasks[session_id] = agent_task

        try:
            while True:
                try:
                    # Wait up to KEEPALIVE_INTERVAL for next token.
                    # On timeout send a keepalive comment so Cloudflare doesn't 524.
                    token = await asyncio.wait_for(token_queue.get(), timeout=KEEPALIVE_INTERVAL)
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
                    continue

                if token is None:
                    break  # sentinel — agent finished

                full_response.append(token)
                _session_token_buffers[session_id].append((event_counter, token))
                yield {"event": "token", "id": str(event_counter), "data": json.dumps({"content": token})}
                event_counter += 1

            # Check if agent raised
            agent_exc: Optional[BaseException] = (
                agent_task.exception()
                if agent_task.done() and not agent_task.cancelled()
                else None
            )
            if agent_exc is not None:
                yield {"event": "error", "data": json.dumps({"message": str(agent_exc)})}
                return

            final_text = "".join(full_response)

            # Persist the response — fresh connection on the async thread (safe)
            with sqlite3.connect(history_db_path) as save_db:
                SqliteEventRepository(save_db).save(Event(
                    session_id=session_id,
                    event_type=EventType.RESPONSE,
                    content=final_text,
                ))

            yield {"event": "done", "id": "done", "data": json.dumps({"content": final_text})}

        except asyncio.CancelledError:
            agent_task.cancel()
            raise

        finally:
            _session_token_buffers.pop(session_id, None)
            _session_agent_tasks.pop(session_id, None)

    return EventSourceResponse(event_stream(), headers=SSE_HEADERS)


@chat_router.get("/{session_id}/latest-timestamp", status_code=status.HTTP_200_OK)
async def get_latest_event_timestamp(
    current_user: Annotated[User, Depends(get_current_user)],
    user_db_path: Annotated[Path, Depends(get_user_db_path)],
    session_id: str,
    response: Response,
):
    if not user_db_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    with sqlite3.connect(user_db_path) as db:
        timestamp = SqliteEventRepository(db).get_last_event_timestamp(session_id)
        if timestamp is None:
            response.status_code = status.HTTP_204_NO_CONTENT
            return
        return {"latest_timestamp": timestamp}


@chat_router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    current_user: Annotated[User, Depends(get_current_user)],
    user_path: Annotated[Path, Depends(get_user_path)],
    user_db_path: Annotated[Path, Depends(get_user_db_path)],
    session_id: str,
) -> Response:
    session_dir = user_path / session_id
    if not user_db_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Connect to repositories
    user_db = sqlite3.connect(user_db_path)
    event_repo = SqliteEventRepository(user_db)
    session_repo = SqliteSessionRepository(user_db)

    session_repo.delete_session(session_id)
    event_repo.delete_messages_from_session(session_id)

    # Clean up vector store facts and events
    event_store_repo, knowledge_store_repo = KnowledgeRepositoryFactory.create_repositories(
        RepositoryType.QDRANT,
        storage_path=DATA_PATH,
        username=current_user.user_id
    )
    event_store_repo.delete_with_session(session_id)
    knowledge_store_repo.delete_with_session(session_id)

    session_dir = user_path / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir)
        
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@chat_router.put("/{session_id}/rename")
def rename_session(
    current_user: Annotated[User, Depends(get_current_user)],
    user_db_path: Annotated[Path, Depends(get_user_db_path)],
    session_id: str,
    body: RenameBody,
) -> Session:
    if not user_db_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    with sqlite3.connect(user_db_path) as db:
        updated = SqliteSessionRepository(db).change_title(session_id, new_title=body.new_title)
        if updated:
            return updated
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
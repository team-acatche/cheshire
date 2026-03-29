import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()
from pathlib import Path
from typing import Annotated, Optional, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from haystack.components.agents import Agent
from haystack.tools import Tool
from haystack.components.generators.utils import print_streaming_chunk
from haystack_integrations.components.embedders.fastembed import FastembedTextEmbedder

from cheshire_configs.core import PipelineConfig
from cheshire_configs.resolver import resolve_config
from knowledge_base.history import Event, EventType, SqliteEventRepository, StreamCallbackFactory
from knowledge_base.session_manager import SqliteSessionRepository, Session
from endpoints.helpers import create_vector_stores
from tools.knowledge import get_relevant_facts_tool

chat_router = APIRouter()
SESSION_DIR = os.path.expanduser(os.path.expandvars(os.getenv("SESSIONS_PATH", ""))) if os.getenv("SESSIONS_PATH") else None

class ChatBody(BaseModel):
    message: str

@chat_router.get("/{username}/chat")
async def get_sessions(
    username: str
) -> list[Session]:
    if SESSION_DIR is None:
        raise HTTPException(status_code=500, detail="SESSION_DIR not set")

    session_path = Path(SESSION_DIR) / username
    if not session_path.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    with sqlite3.connect(session_path / "session_metadata.sqlite") as session_db:
        session_repo = SqliteSessionRepository(session_db)
        return session_repo.get_sessions()
    
@chat_router.get("/{username}/chat/{session_id}")
async def chat_history(
    username: str,
    session_id: str,
):
    if SESSION_DIR is None:
        raise HTTPException(status_code=500, detail="SESSION_DIR not set")

    session_path = Path(SESSION_DIR) / username / session_id
    history_db_path = session_path / "history.sqlite"
    
    if not history_db_path.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    # Connect to repositories
    with sqlite3.connect(history_db_path) as history_db:
        history_repo = SqliteEventRepository(history_db)
        
        recent_events = history_repo.get_recent(session_id, 1000)
        # Events are returned in DESC order, we need them in ASC order for context
        messages = [e.to_chat_message() for e in reversed(recent_events)]
        return {"messages": messages}

@chat_router.post("/{username}/chat/{session_id}")
async def chat(
    username: str,
    session_id: str,
    body: ChatBody,
    config: Annotated[PipelineConfig, Depends(resolve_config)],
):
    # TODO: make this SSE
    if SESSION_DIR is None:
        raise HTTPException(status_code=500, detail="SESSION_DIR not set")

    session_path = Path(SESSION_DIR) / username / session_id
    history_db_path = session_path / "history.sqlite"
    
    if not history_db_path.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    # Connect to repositories
    history_db = sqlite3.connect(history_db_path)
    history_repo = SqliteEventRepository(history_db)
    session_repo = SqliteSessionRepository(history_db)
    
    # Save user message
    user_event = Event(
        session_id=session_id,
        event_type=EventType.USER_MESSAGE,
        content=body.message
    )
    history_repo.save(user_event)

    # Initialize Vector Store (LanceDB)
    knowledge_base = await create_vector_stores(session_path)

    recent_events = history_repo.get_recent(session_id, 1000)
    # Events are returned in DESC order, we need them in ASC order for context
    messages = [e.to_chat_message() for e in reversed(recent_events)]

    # Prepare tools
    # We add knowledge tools specifically for the chat agent
    knowledge_tools = [
        get_relevant_facts_tool(
            session_id=UUID(session_id),
            knowledge_store=knowledge_base,
            embedder=config.embedder or (lambda: FastembedTextEmbedder())
        )
    ]
    
    # Instantiate Agent
    callback_factory = StreamCallbackFactory(session_id=session_id, history=history_repo)
    
    agent = Agent(
        chat_generator=config.model,
        system_prompt="You are now an expert security auditor in an interactive chat session. Use your tools to answer questions about the previously analyzed document and discovered vulnerabilities.",
        tools=cast(list[Tool], config.tools) + knowledge_tools,
        streaming_callback=callback_factory(),
    )

    # Run agent
    try:
        response = agent.run(messages=messages)
        # Note: StreamCallbackFactory already saved the response to history.sqlite
        return {"response": response.get("text", "")}
    except Exception as e:
        import logging
        logging.error(f"Agent error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        history_db.close()

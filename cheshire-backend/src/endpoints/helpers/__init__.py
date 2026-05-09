from dataclasses import dataclass
import os
from pathlib import Path

import pyarrow as pa # type: ignore
from lancedb_haystack import LanceDBDocumentStore # type: ignore

@dataclass(frozen=True, kw_only=True)
class ChatStore:
    event_store: LanceDBDocumentStore
    knowledge_store: LanceDBDocumentStore
    

async def get_or_create_vector_stores(sessions_path: str | Path, *, username: str, dimensions: int = 384) -> ChatStore:
    EVENTS_TABLE: str = "events"
    KNOWLEDGE_TABLE: str = "knowledge"

    event_metadata_schema = pa.struct([
        pa.field("session_id", type=pa.string(), nullable=False),
        pa.field("event_type", type=pa.string(), nullable=False),
        pa.field("ref_event_id", type=pa.string()),
        pa.field("timestamp", type=pa.timestamp("s", tz="Asia/Manila"), nullable=False),
    ])
    knowledge_metadata_schema = pa.struct([
        pa.field("session_id", type=pa.string()),
        pa.field("reference_event", type=pa.string(), nullable=False),
        pa.field("is_global", type=pa.bool_(), nullable=False),
        pa.field("created_at", type=pa.timestamp("s", tz="Asia/Manila"), nullable=False),
        pa.field("last_modified", type=pa.timestamp("s", tz="Asia/Manila"), nullable=False),
    ])

    db_path = os.path.join(sessions_path, "knowledge_base")
    event_store = LanceDBDocumentStore(
        database=db_path,
        table_name="events",
        metadata_schema=event_metadata_schema,
        embedding_dims=dimensions,
    )
    knowledge_store = LanceDBDocumentStore(
        database=db_path,
        table_name="facts",
        metadata_schema=knowledge_metadata_schema,
        embedding_dims=dimensions,
    )

    return ChatStore(
        event_store=event_store,
        knowledge_store=knowledge_store,
    )
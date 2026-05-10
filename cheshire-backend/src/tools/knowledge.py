from datetime import datetime
from dataclasses import dataclass, replace, field
from typing import Annotated, Any, Callable, Optional, cast
from uuid import UUID, uuid4
from contextvars import ContextVar

from haystack import Document
from haystack.tools import tool
from lancedb_haystack import LanceDBDocumentStore # type: ignore

from knowledge_base.repository import KnowledgeRepository
    
import logging
logger = logging.getLogger("uvicorn.error")


@dataclass
class KnowledgeState:
    session_id: Annotated[UUID, "the session ID of the agent"]
    knowledge_base: Annotated[KnowledgeRepository, "the repository for the knowledge base"]
    event_store: Annotated[KnowledgeRepository, "the repository for all of the events in the session"]

    similarity_threshold: Annotated[float, "the similarity threshold used for upserting facts"] = 0.85

current_knowledge_state: ContextVar[KnowledgeState] = ContextVar("current_knowledge_state")

@tool
def upsert_fact(
    facts: Annotated[list[str], "The facts to assert."],
    incorrect_fact_knowledge_id: Annotated[Optional[str], "(Optional) the knowledge UUID of the incorrect fact, if known."] = None,
) -> dict[str, str]:
    """
    Upserts a fact to the knowledge base.

    :param facts: the facts to upsert.
    :param incorrect_fact_knowledge_id: (Optional) the knowledge UUID of the incorrect fact, if known.

    :return: a dict indicating the number of facts added or updated.
    """
    state = current_knowledge_state.get()
    added = 0
    updated = 0
    fact_documents: list[Document] = []
    for fact in facts:
        # Check for similar facts to avoid duplicates
        if similar_facts := state.knowledge_base.search(query=fact, top_k=1):
            most_similar_fact: Document = similar_facts[0]
            # If the most similar fact is close enough, we update it
            if (most_similar_fact.score or 0) >= state.similarity_threshold:
                from dataclasses import replace
                fact_documents.append(replace(
                    most_similar_fact,
                    content=fact,
                    meta={**most_similar_fact.meta, "last_modified": datetime.now().isoformat()},
                ))
                updated += 1
                logger.info(f"Updating existing fact (score: {most_similar_fact.score}): {fact[:50]}...")
                continue
            else:
                logger.info(f"Top match score {most_similar_fact.score} below threshold {state.similarity_threshold}. Adding as new.")

        # If not similar enough, or no facts exist, add as new
        fact_documents.append(Document(
            id=str(uuid4()),
            content=fact,
            meta = {
                "is_global": False,
                "session_id": str(state.session_id),
                "created_at": datetime.now().isoformat(),
                "last_modified": datetime.now().isoformat(),
            }
        ))
        added += 1
        logger.info(f"Adding new fact: {fact[:50]}...")

    assert len(facts) == len(fact_documents)
    state.knowledge_base.save(fact_documents)
    return {"result": f"Added {added} new facts and updated {updated} facts to the knowledge base."}


@tool
def get_facts(
    with_global: Annotated[bool, "Whether to include global facts."] = False
) -> dict[str, Any]:
    """
    Gets all facts from the knowledge base.

    :param with_global: whether to include global facts.

    :return: a dict containing result string with all facts.
    """
    state = current_knowledge_state.get()
    results = state.knowledge_base.query(filters={
        "operator": "OR" if with_global else "AND",
        "conditions": [
            {
                "field": "meta.session_id",
                "operator": "==",
                "value": str(state.session_id),
            },
            {
                "field": "meta.is_global",
                "operator": "==",
                "value": with_global,
            },
        ]
    })

    facts: list[str] = [f"{document.content} (id: {document.id})" for document in results]
    return {"facts": facts}


@tool
def get_relevant_facts(
    query: Annotated[str, "The query to get relevant facts for."]
) -> dict[str, Any]:
    """
    Gets facts relevant to the query.

    :param query: the query to get relevant facts for.

    :return: a dict containing result string with all facts relevant to the query.
    """
    state = current_knowledge_state.get()
    results = state.knowledge_base.search(query=query)
    facts: list[str] = [f"{document.content} (id: {document.id})" for document in results]
    return {"facts": facts}

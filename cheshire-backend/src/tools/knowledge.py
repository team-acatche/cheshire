from datetime import datetime
from dataclasses import dataclass, replace, field
from typing import Annotated, Any, Callable, Optional, cast
from uuid import UUID, uuid4
from contextvars import ContextVar

from haystack import Pipeline, Document, component
from haystack.components.writers.document_writer import DocumentWriter, DuplicatePolicy
from haystack.components.embedders.types import TextEmbedder
from haystack.tools import create_tool_from_function, Tool, ComponentTool

from haystack_integrations.components.embedders.fastembed import FastembedDocumentEmbedder, FastembedTextEmbedder
from lancedb_haystack import LanceDBDocumentStore, LanceDBEmbeddingRetriever, LanceDBFTSRetriever # type: ignore

from cheshire_configs.retrievers.hybrid_retriever import HybridLanceDbRetriever

@dataclass
class KnowledgeState:
    session_id: Annotated[UUID, "the session ID of the agent"]
    knowledge_base: Annotated[LanceDBDocumentStore, "the vector database for the knowledge base"]
    event_store: Annotated[LanceDBDocumentStore, "the vector database for all of the events in the session"]

    similarity_threshold: Annotated[float, "the similarity threshold used for upserting facts"] = 0.35
    embedder: Annotated[FastembedDocumentEmbedder, "the embedder used for upserting facts"] = field(default_factory=FastembedDocumentEmbedder, init=False)
    retriever: Annotated[HybridLanceDbRetriever, "the retriever for obtaining similar facts"] = field(init=False)
    upsert_pipeline: Annotated[Pipeline, "the pipeline for upserting facts"] = field(init=False)

    def __post_init__(self):
        self.upsert_pipeline = Pipeline()
        self.upsert_pipeline.add_component("embedder", self.embedder)
        self.upsert_pipeline.add_component("writer", DocumentWriter(document_store=self.knowledge_base, policy=DuplicatePolicy.OVERWRITE))
        self.upsert_pipeline.connect("embedder", "writer")

        self.retriever = HybridLanceDbRetriever(self.knowledge_base, FastembedTextEmbedder())

current_knowledge_state: ContextVar[KnowledgeState] = ContextVar("current_knowledge_state")

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
        if incorrect_fact_knowledge_id is not None:
            incorrect_fact = state.knowledge_base.perform_query(
                filters={
                    "field": "id",
                    "operator": "==",
                    "value": incorrect_fact_knowledge_id,
                },
                top_k=1
            )
            if len(incorrect_fact) == 0:
                return {"result": f"Fact with knowledge id {incorrect_fact_knowledge_id} not found."}
            fact_documents.append(replace(
                incorrect_fact[0],
                content=fact,
                meta={**incorrect_fact[0].meta, "last_modified": datetime.now().isoformat()},
            ))
            updated += 1
            continue
            
        if similar_facts := state.retriever.run(query=fact, top_k=1)["documents"]: # type: ignore
            most_similar_fact: Document = similar_facts[0]
            if (most_similar_fact.score or 0) <= state.similarity_threshold:
                fact_documents.append(replace(
                    most_similar_fact,
                    content=fact,
                    meta={**most_similar_fact.meta, "last_modified": datetime.now().isoformat()},
                ))
                updated += 1
                continue

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
    assert len(facts) == len(fact_documents)
    state.upsert_pipeline.run({"embedder": {"documents": fact_documents}})
    return {"result": f"Added {added} new facts and updated {updated} facts to the knowledge base."}


upsert_fact_tool = create_tool_from_function(upsert_fact)


def get_facts(
    with_global: Annotated[bool, "Whether to include global facts."] = False
) -> dict[str, Any]:
    """
    Gets all facts from the knowledge base.

    :param with_global: whether to include global facts.

    :return: a dict containing result string with all facts.
    """
    state = current_knowledge_state.get()
    results = state.knowledge_base.perform_query(filters={
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


get_facts_tool = create_tool_from_function(get_facts)


def get_relevant_facts(
    query: Annotated[str, "The query to get relevant facts for."]
) -> dict[str, Any]:
    """
    Gets facts relevant to the query.

    :param query: the query to get relevant facts for.

    :return: a dict containing result string with all facts relevant to the query.
    """
    state = current_knowledge_state.get()
    results = state.retriever.run(query=query) # type: ignore
    facts: list[str] = [f"{document.content} (id: {document.id})" for document in results["documents"]]
    return {"facts": facts}

get_relevant_facts_tool = create_tool_from_function(get_relevant_facts)

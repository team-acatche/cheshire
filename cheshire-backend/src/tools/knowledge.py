from datetime import datetime
from dataclasses import replace
from typing import Annotated, Any, Callable, Optional, cast
from uuid import UUID, uuid4

from haystack import Pipeline, Document
from haystack.components.writers.document_writer import DocumentWriter, DuplicatePolicy
from haystack.components.embedders.types import TextEmbedder
from haystack.tools import tool, Tool

from haystack_integrations.components.embedders.fastembed import FastembedDocumentEmbedder
from lancedb_haystack import LanceDBDocumentStore, LanceDBEmbeddingRetriever, LanceDBFTSRetriever # type: ignore

from cheshire_configs.retrievers.hybrid_retriever import HybridLanceDbRetriever


EmbedderFactory = Callable[[], TextEmbedder]


def upsert_fact_tool(
    session_id: UUID,
    *,
    knowledge_store: LanceDBDocumentStore,
    embedder: EmbedderFactory,
    similarity_threshold: float = 0.35,
) -> Tool:
    """
    Creates a tool for asserting facts.

    :param session_id: the ID of the session.
    :param knowledge_store: the knowledge store.
    :param embedder: the text embedder for checking if the fact already exists.
    :param similarity_threshold: the similarity threshold for updating facts using L2 search.

    :return: the assert_fact tool.
    """

    upsert_pipeline = Pipeline()
    upsert_pipeline.add_component("embedder", embedder())
    upsert_pipeline.add_component("writer", DocumentWriter(document_store=knowledge_store, policy=DuplicatePolicy.OVERWRITE))
    upsert_pipeline.connect("embedder", "writer")

    retriever = HybridLanceDbRetriever(knowledge_store, embedder())

    @tool
    def upsert_fact(
        facts: Annotated[list[str], "The facts to assert."],
        incorrect_fact_knowledge_id: Annotated[Optional[str], "(Optional) the knowledge UUID of the incorrect fact, if known."] = None,
    ) -> str:
        """
        Upserts a fact to the knowledge base.

        :param facts: the facts to upsert.
        :param incorrect_fact_knowledge_id: (Optional) the knowledge UUID of the incorrect fact, if known.

        :return: a string indicating the number of facts added.
        """
        added = 0
        updated = 0
        fact_documents: list[Document] = []
        for fact in facts:
            if incorrect_fact_knowledge_id is not None:
                # search the knowledge base for the specific fact 
                incorrect_fact = knowledge_store.perform_query(
                    filters={
                        "field": "id",
                        "operator": "==",
                        "value": incorrect_fact_knowledge_id,
                    },
                    top_k=1
                )
                if len(incorrect_fact) == 0:
                    return f"Fact with knowledge id {incorrect_fact_knowledge_id} not found."
                fact_documents.append(replace(
                    incorrect_fact[0],
                    content=fact,
                    meta={**incorrect_fact[0].meta, "last_modified": datetime.now().isoformat()},
                ))
                updated += 1
                continue
                
            if similar_facts := retriever.run(query=fact, top_k=1)["documents"]: # type: ignore
                most_similar_fact: Document = similar_facts[0]
                if (most_similar_fact.score or 0) <= similarity_threshold:
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
                    "session_id": str(session_id),
                    "created_at": datetime.now().isoformat(),
                    "last_modified": datetime.now().isoformat(),
                }
            ))
            added += 1
        assert len(facts) == len(fact_documents)
        upsert_pipeline.run({"embedder": {"documents": fact_documents}})
        return f"Added {added} new facts and updated {updated} facts to the knowledge base."


    return cast(Tool, upsert_fact)

def get_facts_tool(
    session_id: UUID,
    *,
    knowledge_store: LanceDBDocumentStore,
) -> Tool:
    """
    Creates a tool for getting facts.

    :param session_id: the ID of the session.
    :param knowledge_store: the knowledge store.

    :return: the get_facts tool.
    """
    @tool
    def get_facts(with_global: Annotated[bool, "Whether to include global facts."] = False) -> str:
        """
        Gets all facts from the knowledge base.

        :param with_global: whether to include global facts.

        :return: a string containing all facts.
        """
        results = knowledge_store.perform_query(filters={
            "operator": "OR" if with_global else "AND",
            "conditions": [
                {
                    "field": "meta.session_id",
                    "operator": "==",
                    "value": str(session_id),
                },
                {
                    "field": "meta.is_global",
                    "operator": "==",
                    "value": with_global,
                },
            ]
        })
        facts: list[str] = []
        for document in results:
            facts.append(f"{document.content} (id: {document.id})")
        return "\n".join(facts)

    return cast(Tool, get_facts)

def get_relevant_facts_tool(
    session_id: UUID,
    *,
    knowledge_store: LanceDBDocumentStore,
    embedder: EmbedderFactory,
) -> Tool:
    """
    Creates a tool for getting relevant facts.

    :param session_id: the ID of the session.
    :param knowledge_store: the knowledge store.
    :param embedder: the embedder.

    :return: the get_relevant_facts tool.
    """
    @tool
    def get_relevant_facts(query: Annotated[str, "The query to get relevant facts for."]) -> str:
        """
        Gets facts relevant to the query.

        :param query: the query to get relevant facts for.

        :return: a string containing all facts relevant to the query.
        """
        results = HybridLanceDbRetriever(knowledge_store, embedder()).run(query=query) # type: ignore
        facts: list[str] = [f"{document.content} (id: {document.id})" for document in results["documents"]]
        return "\n".join(facts)

    return cast(Tool, get_relevant_facts)

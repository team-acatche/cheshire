from datetime import datetime
from dataclasses import replace
from typing import Annotated, Any, Callable, Optional, cast
from uuid import UUID, uuid4

from haystack import Pipeline, Document, component
from haystack.components.writers.document_writer import DocumentWriter, DuplicatePolicy
from haystack.components.embedders.types import TextEmbedder
from haystack.tools import create_tool_from_function, Tool, ComponentTool

from haystack_integrations.components.embedders.fastembed import FastembedDocumentEmbedder, FastembedTextEmbedder
from lancedb_haystack import LanceDBDocumentStore, LanceDBEmbeddingRetriever, LanceDBFTSRetriever # type: ignore

from cheshire_configs.retrievers.hybrid_retriever import HybridLanceDbRetriever

@component
class UpsertFactTool:
    def __init__(self, session_id: UUID, knowledge_base: LanceDBDocumentStore, *, similarity_threshold: float = 0.35):
        self.session_id = session_id
        self.knowledge_base = knowledge_base
        self.similarity_threshold = similarity_threshold

        self.embedder = FastembedDocumentEmbedder()

        self.upsert_pipeline = Pipeline()
        self.upsert_pipeline.add_component("embedder", self.embedder)
        self.upsert_pipeline.add_component("writer", DocumentWriter(document_store=self.knowledge_base, policy=DuplicatePolicy.OVERWRITE))
        self.upsert_pipeline.connect("embedder", "writer")

        self.retriever = HybridLanceDbRetriever(self.knowledge_base, FastembedTextEmbedder())

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "tools.knowledge.UpsertFactTool",
            "init_parameters": {
                "session_id": str(self.session_id),
                "knowledge_base": self.knowledge_base.to_dict(),
                "similarity_threshold": self.similarity_threshold
            }
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UpsertFactTool":
        init_params = data.get("init_parameters", {})
        session_id = UUID(init_params["session_id"])
        knowledge_base = LanceDBDocumentStore.from_dict(init_params["knowledge_base"])
        return cls(session_id=session_id, knowledge_base=knowledge_base, similarity_threshold=init_params["similarity_threshold"])

    @component.output_types(result=str)
    def run(
        self,
        facts: Annotated[list[str], "The facts to assert."],
        incorrect_fact_knowledge_id: Annotated[Optional[str], "(Optional) the knowledge UUID of the incorrect fact, if known."] = None,
    ) -> dict[str, str]:
        """
        Upserts a fact to the knowledge base.

        :param facts: the facts to upsert.
        :param incorrect_fact_knowledge_id: (Optional) the knowledge UUID of the incorrect fact, if known.

        :return: a dict indicating the number of facts added or updated.
        """
        added = 0
        updated = 0
        fact_documents: list[Document] = []
        for fact in facts:
            if incorrect_fact_knowledge_id is not None:
                incorrect_fact = self.knowledge_base.perform_query(
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
                
            if similar_facts := self.retriever.run(query=fact, top_k=1)["documents"]: # type: ignore
                most_similar_fact: Document = similar_facts[0]
                if (most_similar_fact.score or 0) <= self.similarity_threshold:
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
                    "session_id": str(self.session_id),
                    "created_at": datetime.now().isoformat(),
                    "last_modified": datetime.now().isoformat(),
                }
            ))
            added += 1
        assert len(facts) == len(fact_documents)
        self.upsert_pipeline.run({"embedder": {"documents": fact_documents}})
        return {"result": f"Added {added} new facts and updated {updated} facts to the knowledge base."}


def upsert_fact_tool(
    session_id: UUID,
    *,
    knowledge_store: LanceDBDocumentStore,
    similarity_threshold: float = 0.35,
) -> Tool:
    """
    Creates a tool for asserting facts.

    :param session_id: the ID of the session.
    :param knowledge_store: the knowledge store.
    :param similarity_threshold: the similarity threshold for updating facts using L2 search.

    :return: the assert_fact tool.
    """
    return ComponentTool(
        component=UpsertFactTool(session_id, knowledge_base=knowledge_store, similarity_threshold=similarity_threshold),
        name="upsert_fact",
        description="Upserts a fact to the knowledge base.",
        outputs_to_string={"source": "result"}
    )


@component
class GetFactsTool:
    def __init__(self, session_id: UUID, knowledge_store: LanceDBDocumentStore):
        self.session_id = session_id
        self.knowledge_store = knowledge_store

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "tools.knowledge.GetFactsTool",
            "init_parameters": {
                "session_id": str(self.session_id),
                "knowledge_store": self.knowledge_store.to_dict(),
            }
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GetFactsTool":
        init_params = data.get("init_parameters", {})
        return cls(
            session_id=UUID(init_params["session_id"]),
            knowledge_store=LanceDBDocumentStore.from_dict(init_params["knowledge_store"])
        )

    @component.output_types(result=str)
    def run(self, with_global: Annotated[bool, "Whether to include global facts."] = False) -> dict[str, str]:
        """
        Gets all facts from the knowledge base.

        :param with_global: whether to include global facts.

        :return: a dict containing result string with all facts.
        """
        results = self.knowledge_store.perform_query(filters={
            "operator": "OR" if with_global else "AND",
            "conditions": [
                {
                    "field": "meta.session_id",
                    "operator": "==",
                    "value": str(self.session_id),
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
        return {"result": "\n".join(facts)}


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
    return ComponentTool(
        component=GetFactsTool(session_id, knowledge_store),
        name="get_facts",
        description="Gets all facts from the knowledge base.",
        outputs_to_string={"source": "result"}
    )


@component
class GetRelevantFactsTool:
    def __init__(self, session_id: UUID, knowledge_store: LanceDBDocumentStore):
        self.session_id = session_id
        self.knowledge_store = knowledge_store
        self.retriever = HybridLanceDbRetriever(knowledge_store, FastembedTextEmbedder())

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "tools.knowledge.GetRelevantFactsTool",
            "init_parameters": {
                "session_id": str(self.session_id),
                "knowledge_store": self.knowledge_store.to_dict(),
            }
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GetRelevantFactsTool":
        init_params = data.get("init_parameters", {})
        return cls(
            session_id=UUID(init_params["session_id"]),
            knowledge_store=LanceDBDocumentStore.from_dict(init_params["knowledge_store"])
        )

    @component.output_types(result=str)
    def run(self, query: Annotated[str, "The query to get relevant facts for."]) -> dict[str, str]:
        """
        Gets facts relevant to the query.

        :param query: the query to get relevant facts for.

        :return: a dict containing result string with all facts relevant to the query.
        """
        results = self.retriever.run(query=query) # type: ignore
        facts: list[str] = [f"{document.content} (id: {document.id})" for document in results["documents"]]
        return {"result": "\n".join(facts)}


def get_relevant_facts_tool(
    session_id: UUID,
    *,
    knowledge_store: LanceDBDocumentStore,
) -> Tool:
    """
    Creates a tool for getting relevant facts.

    :param session_id: the ID of the session.
    :param knowledge_store: the knowledge store.

    :return: the get_relevant_facts tool.
    """
    return ComponentTool(
        component=GetRelevantFactsTool(session_id, knowledge_store),
        name="get_relevant_facts",
        description="Gets facts relevant to the query.",
        outputs_to_string={"source": "result"}
    )

import os
from typing import Annotated

from haystack import Pipeline
from haystack.document_stores.in_memory import InMemoryDocumentStore
from haystack.components.retrievers.in_memory import InMemoryEmbeddingRetriever
from haystack_integrations.components.embedders.ollama import OllamaTextEmbedder
from fastapi import HTTPException, Depends

from cheshire_configs.core import EvaluationType, Provider, PipelineConfig
from preprocessors.ollama import OllamaRagPreprocessor
from tools.base import query_document_tool
from cheshire_configs.registry import configs

async def resolve_config(
    configs: Annotated[dict[Provider, PipelineConfig], Depends(configs)],
    evaluation_mode: EvaluationType = EvaluationType.RAG,
    provider: Provider = Provider.OLLAMA,
) -> PipelineConfig:
    factory: PipelineConfig | None = configs.get(provider)
    if not factory:
        raise HTTPException(status_code=400, detail=f"Unsupported: {provider}")

    if evaluation_mode == EvaluationType.RAG and factory.embedder:
        document_store = InMemoryDocumentStore(embedding_similarity_function="cosine")
        retriever = InMemoryEmbeddingRetriever(document_store)

        rag_query_pipeline = Pipeline()
        rag_query_pipeline.add_component("embedder", factory.embedder)
        rag_query_pipeline.add_component("retriever", retriever)
        rag_query_pipeline.connect("embedder.embedding", "retriever.query_embedding")

        return factory.with_overrides(
            document_store=document_store,
            preprocessor=OllamaRagPreprocessor(),
            tools=[*factory.tools, query_document_tool(rag_query_pipeline)],
        )

    return factory.with_overrides(
        mode=evaluation_mode,
    )
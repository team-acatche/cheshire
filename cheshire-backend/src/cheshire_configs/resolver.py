import os
from typing import Annotated

from haystack import Pipeline
from haystack.document_stores.in_memory import InMemoryDocumentStore
from haystack.components.retrievers.in_memory import InMemoryEmbeddingRetriever
from haystack_integrations.components.embedders.ollama import OllamaTextEmbedder
from fastapi import HTTPException, Depends, status

from cheshire_configs.core import EvaluationType, Provider, PipelineConfig
from cheshire_configs.preprocessors.core import DefaultRagPreprocessor
from tools.base import query_document_tool
from cheshire_configs.registry import configs

async def resolve_config(
    configs: Annotated[dict[Provider, PipelineConfig], Depends(configs)],
    evaluation_mode: EvaluationType = EvaluationType.RAG,
    provider: Provider = Provider.OLLAMA,
) -> PipelineConfig:
    factory: PipelineConfig | None = configs.get(provider)
    if not factory:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported: {provider}")

    if evaluation_mode == EvaluationType.RAG and factory.embedder is not None:
        document_store = InMemoryDocumentStore(embedding_similarity_function="cosine")

        return factory.with_overrides(
            document_store=document_store,
            preprocessor=DefaultRagPreprocessor(factory),
            tools=[*factory.tools, query_document_tool(document_store, factory.embedder())],
        )

    return factory.with_overrides(
        mode=evaluation_mode,
    )
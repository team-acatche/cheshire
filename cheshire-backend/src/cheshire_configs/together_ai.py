import os

from haystack.components.embedders.hugging_face_api_text_embedder import HuggingFaceAPITextEmbedder, HFEmbeddingAPIType
from haystack_integrations.components.embedders.ollama.text_embedder import OllamaTextEmbedder
from haystack_integrations.components.generators.togetherai import TogetherAIChatGenerator
from haystack_integrations.components.embedders.fastembed import FastembedTextEmbedder

from haystack.components.embedders.hugging_face_api_document_embedder import HuggingFaceAPIDocumentEmbedder, HFEmbeddingAPIType
from haystack_integrations.components.embedders.ollama.document_embedder import OllamaDocumentEmbedder
from haystack_integrations.components.embedders.fastembed import FastembedDocumentEmbedder

from cheshire_configs.core import DefaultToolFactory, PipelineConfig
from cheshire_configs.preprocessors.fallbacks import FallbackTextEmbedder, FallbackDocumentEmbedder


async def together_config() -> PipelineConfig:
    # TODO: remove this once the user can supply their own API key
    from dotenv import load_dotenv
    load_dotenv(".env.user")

    return PipelineConfig(
        model=TogetherAIChatGenerator(
            model=os.getenv("TOGETHER_CHAT_MODEL", "ServiceNow-AI/Apriel-1.6-15b-Thinker"),
            generation_kwargs={
                "reasoning_effort": os.getenv("TOGETHER_REASONING_EFFORT", "medium"),
                "stream": True,
            }
        ),
        embedder=lambda: FallbackTextEmbedder(
            HuggingFaceAPITextEmbedder(
                api_type=HFEmbeddingAPIType.SERVERLESS_INFERENCE_API,
                api_params={
                    "model": os.getenv("HF_EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v2-moe"),
                }
            ),
            OllamaTextEmbedder(
                model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
                url=os.getenv("OLLAMA_URL", "http://localhost:11434")
            ),
            FastembedTextEmbedder(),
        ),
        # TODO (bug): this is gonna cause consistency issues since the embedders are different and when they work is nondeterministic.
        # document_embedder=lambda: FallbackDocumentEmbedder(
        #     HuggingFaceAPIDocumentEmbedder(
        #         api_type=HFEmbeddingAPIType.SERVERLESS_INFERENCE_API,
        #         api_params={
        #             "model": os.getenv("HF_EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v2-moe"),
        #         }
        #     ),
        #     OllamaDocumentEmbedder(
        #         model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
        #         url=os.getenv("OLLAMA_URL", "http://localhost:11434")
        #     ),
        #     # FastembedDocumentEmbedder(),
        # ),
        document_embedder=lambda: FastembedDocumentEmbedder(model="sentence-transformers/all-MiniLM-L6-v2"),
        tools=DefaultToolFactory().tools,
    )
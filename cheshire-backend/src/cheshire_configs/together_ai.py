import os

from haystack.components.embedders.hugging_face_api_text_embedder import HuggingFaceAPITextEmbedder, HFEmbeddingAPIType
from haystack_integrations.components.generators.togetherai import TogetherAIChatGenerator
from cheshire_configs.core import DefaultToolFactory, PipelineConfig


async def together_config() -> PipelineConfig:
    from dotenv import load_dotenv
    load_dotenv()

    return PipelineConfig(
        model=TogetherAIChatGenerator(
            model=os.getenv("TOGETHER_CHAT_MODEL", "ServiceNow-AI/Apriel-1.6-15b-Thinker"),
            generation_kwargs={
                "reasoning_effort": os.getenv("TOGETHER_REASONING_EFFORT", "medium"),
                "stream": True,
            }
        ),
        embedder=HuggingFaceAPITextEmbedder(
            api_type=HFEmbeddingAPIType.SERVERLESS_INFERENCE_API,
            api_params={
                "model": os.getenv("HF_EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v2-moe"),
            }
        ),
        tools=DefaultToolFactory().tools,
    )
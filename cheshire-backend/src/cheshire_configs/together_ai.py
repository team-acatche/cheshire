import os

from haystack_integrations.components.generators.togetherai import TogetherAIChatGenerator
from haystack_integrations.components.embedders.fastembed import FastembedTextEmbedder, FastembedDocumentEmbedder

from cheshire_configs.core import DefaultToolFactory, PipelineConfig


async def together_config() -> PipelineConfig:
    # Force fastembed (onnxruntime) to use CPU to avoid NVRTC/CUDA initialization crashes
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

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
        embedder=lambda: FastembedTextEmbedder(model="sentence-transformers/all-MiniLM-L6-v2"),
        document_embedder=lambda: FastembedDocumentEmbedder(model="sentence-transformers/all-MiniLM-L6-v2"),
        tools=DefaultToolFactory().tools,
    )
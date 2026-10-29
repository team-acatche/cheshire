import os

from haystack_integrations.components.generators.openrouter import OpenRouterChatGenerator
from cheshire_configs.resilient_generator import make_resilient_openrouter_generator
from haystack_integrations.components.embedders.fastembed import FastembedTextEmbedder, FastembedDocumentEmbedder
from dotenv import load_dotenv
load_dotenv(".env.user")

from cheshire_configs.core import PipelineConfig, DefaultToolFactory

async def openrouter_config() -> PipelineConfig:
    # Force fastembed (onnxruntime) to use CPU to avoid NVRTC/CUDA initialization crashes
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

    # resilient generator with retry and timeout
    base_generator = make_resilient_openrouter_generator()

    return PipelineConfig(
        model=base_generator,
        embedder=lambda: FastembedTextEmbedder(model="sentence-transformers/all-MiniLM-L6-v2"),
        document_embedder=lambda: FastembedDocumentEmbedder(model="sentence-transformers/all-MiniLM-L6-v2"),
        tools=DefaultToolFactory().tools,
    )
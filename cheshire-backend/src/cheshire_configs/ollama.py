import os

from haystack_integrations.components.generators.ollama import OllamaChatGenerator
from haystack_integrations.components.embedders.fastembed import FastembedTextEmbedder, FastembedDocumentEmbedder

from cheshire_configs.core import DefaultToolFactory, PipelineConfig

TIMEOUT_MINUTES = 5;

async def ollama_config() -> PipelineConfig:
    # Force fastembed (onnxruntime) to use CPU to avoid NVRTC/CUDA initialization crashes
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

    # TODO: remove this once the user can supply their own config
    from dotenv import load_dotenv
    load_dotenv(".env.user")

    return PipelineConfig(
        model=OllamaChatGenerator(
            model=os.getenv("OLLAMA_CHAT_MODEL", "llama3.2"),
            url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
            generation_kwargs={
                "num_ctx": 2**14,  # 16384
            },
            think=True,
            timeout=60*TIMEOUT_MINUTES,
            max_retries=5,
        ),
        document_embedder=lambda: FastembedDocumentEmbedder(model="sentence-transformers/all-MiniLM-L6-v2"),
        embedder=lambda: FastembedTextEmbedder(model="sentence-transformers/all-MiniLM-L6-v2"),
        tools=DefaultToolFactory().tools,
    )
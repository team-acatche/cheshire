import os

from haystack_integrations.components.generators.ollama import OllamaChatGenerator
from haystack_integrations.components.embedders.ollama import OllamaTextEmbedder
from cheshire_configs.core import DefaultToolFactory, PipelineConfig


async def ollama_config() -> PipelineConfig:
    from dotenv import load_dotenv
    load_dotenv()

    return PipelineConfig(
        model=OllamaChatGenerator(
            model=os.getenv("OLLAMA_CHAT_MODEL", "llama3.2"),
            url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
            generation_kwargs={
                "num_ctx": 2**14,  # 16384
            },
            think=True,
        ),
        embedder=OllamaTextEmbedder(
            model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
            url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        ),
        tools=DefaultToolFactory().tools,
    )
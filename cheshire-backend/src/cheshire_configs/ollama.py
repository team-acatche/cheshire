import os

from haystack_integrations.components.generators.ollama import OllamaChatGenerator
# from haystack_integrations.components.embedders.ollama import OllamaTextEmbedder
# from haystack_integrations.components.embedders.ollama import OllamaDocumentEmbedder

from haystack_integrations.components.embedders.fastembed import FastembedTextEmbedder, FastembedDocumentEmbedder

from cheshire_configs.core import DefaultToolFactory, PipelineConfig


async def ollama_config() -> PipelineConfig:
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
        ),
        # document_embedder=lambda: OllamaDocumentEmbedder(
        #     model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
        #     url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        # ),
        # embedder=lambda: OllamaTextEmbedder(
        #     model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
        #     url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        # ),
        document_embedder=lambda: FastembedDocumentEmbedder(model="sentence-transformers/all-MiniLM-L6-v2"),
        embedder=lambda: FastembedTextEmbedder(model="sentence-transformers/all-MiniLM-L6-v2"),
        tools=DefaultToolFactory().tools,
    )
import os
from dotenv import load_dotenv
load_dotenv()

from haystack_integrations.components.embedders.ollama import OllamaTextEmbedder
from haystack_integrations.components.generators.ollama import OllamaChatGenerator
from haystack.document_stores.in_memory import InMemoryDocumentStore
from haystack.components.retrievers.in_memory import InMemoryEmbeddingRetriever
from haystack.core.pipeline import Pipeline

from tools.tools import query_document_tool, add_vulnerability_tool, read_vulnerabilities_tool
from tools.exa import web_search
from preprocessors.ollama import ollama_rag_preprocessor

async def ollama_rag_config() -> dict:
    document_store = InMemoryDocumentStore(embedding_similarity_function="cosine")

    embedder = OllamaTextEmbedder(
        model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
        url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
    )
    retriever = InMemoryEmbeddingRetriever(document_store)
    rag_query_pipeline = Pipeline()
    rag_query_pipeline.add_component("embedder", embedder)
    rag_query_pipeline.add_component("retriever", retriever)
    rag_query_pipeline.connect("embedder.embedding", "retriever.query_embedding")

    return {
        "model": OllamaChatGenerator(
        	model=os.getenv("OLLAMA_CHAT_MODEL", "llama3.2"),
        	url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        	generation_kwargs={
        		"num_ctx": 2**14, # 16384
        	},
        	think=True,
        ),
        "document_store": document_store,
        "document_preprocessor": ollama_rag_preprocessor,
        "retrieval_pipeline": rag_query_pipeline,
        "tools": [
			query_document_tool(rag_query_pipeline),
			web_search,
			add_vulnerability_tool("vulnerabilities_list"),
			read_vulnerabilities_tool("vulnerabilities_list")
		]
    }
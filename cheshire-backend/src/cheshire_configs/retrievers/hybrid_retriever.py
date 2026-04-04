from haystack import Document, Pipeline, super_component
from haystack.document_stores.types import DocumentStore
from haystack.components.joiners import DocumentJoiner
from haystack.components.embedders.types import TextEmbedder

from lancedb_haystack import LanceDBDocumentStore, LanceDBEmbeddingRetriever, LanceDBFTSRetriever # type: ignore
from haystack_integrations.components.embedders.fastembed import FastembedTextEmbedder
from haystack_integrations.components.rankers.fastembed import FastembedRanker

from haystack.document_stores.in_memory import InMemoryDocumentStore
from haystack.components.retrievers import InMemoryEmbeddingRetriever, InMemoryBM25Retriever

# TODO: refactor

@super_component
class HybridLanceDbRetriever:
    def __init__(
        self,
        document_store: LanceDBDocumentStore,
        embedder: TextEmbedder,
    ):
        self.document_store = document_store

        embedding_retriever = LanceDBEmbeddingRetriever(self.document_store, top_k=5)
        fts_retriever = LanceDBFTSRetriever(self.document_store, top_k=5)
        document_joiner = DocumentJoiner()
        reranker = FastembedRanker(top_k=5)

        self.pipeline = Pipeline()
        self.pipeline.add_component("embedder", embedder)
        self.pipeline.add_component("embedding_retriever", embedding_retriever)
        self.pipeline.add_component("fts_retriever", fts_retriever)
        self.pipeline.add_component("document_joiner", document_joiner)
        self.pipeline.add_component("reranker", reranker)

        self.pipeline.connect("embedder", "embedding_retriever")
        self.pipeline.connect("embedding_retriever", "document_joiner")
        self.pipeline.connect("fts_retriever", "document_joiner")
        self.pipeline.connect("document_joiner", "reranker")

        self.input_mapping = {"query": ["embedder.text", "fts_retriever.query", "reranker.query"]}

@super_component
class HybridInMemoryRetriever:
    def __init__(
        self,
        document_store: InMemoryDocumentStore,
        embedder: TextEmbedder = FastembedTextEmbedder(model="sentence-transformers/all-MiniLM-L6-v2"),
    ):
        self.document_store = document_store
        self.embedder = embedder

        embedding_retriever = InMemoryEmbeddingRetriever(self.document_store, top_k=5)
        bm25_retriever = InMemoryBM25Retriever(self.document_store, top_k=5)
        document_joiner = DocumentJoiner()
        reranker = FastembedRanker(top_k=5)

        self.pipeline = Pipeline()
        self.pipeline.add_component("embedder", self.embedder)
        self.pipeline.add_component("embedding_retriever", embedding_retriever)
        self.pipeline.add_component("bm25_retriever", bm25_retriever)
        self.pipeline.add_component("document_joiner", document_joiner)
        self.pipeline.add_component("reranker", reranker)

        self.pipeline.connect("embedder", "embedding_retriever")
        self.pipeline.connect("embedding_retriever", "document_joiner")
        self.pipeline.connect("bm25_retriever", "document_joiner")
        self.pipeline.connect("document_joiner", "reranker")

        self.input_mapping = {"query": ["embedder.text", "bm25_retriever.query", "reranker.query"]}
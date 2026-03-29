from haystack import Document, Pipeline, super_component
from haystack.document_stores.types import DocumentStore
from haystack.components.joiners import DocumentJoiner
from haystack.components.embedders.types import TextEmbedder

from lancedb_haystack import LanceDBDocumentStore, LanceDBEmbeddingRetriever, LanceDBFTSRetriever # type: ignore
from haystack_integrations.components.rankers.fastembed import FastembedRanker

@super_component
class HybridRetriever:
    def __init__(
        self,
        document_store: LanceDBDocumentStore,
        embedder: TextEmbedder,
    ):
        embedding_retriever = LanceDBEmbeddingRetriever(document_store, top_k=5)
        fts_retriever = LanceDBFTSRetriever(document_store, top_k=5)
        document_joiner = DocumentJoiner()
        reranker = FastembedRanker()

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
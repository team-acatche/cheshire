from haystack import component, Document
from haystack.components.embedders.types import TextEmbedder, DocumentEmbedder

import logging
logger = logging.getLogger("uvicorn.error")

@component
class FallbackTextEmbedder:
    def __init__(self, embedder: TextEmbedder, fallback: TextEmbedder):
        self.primary = embedder
        self.fallback = fallback

        if hasattr(self.primary, "warm_up"):
            self.primary.warm_up()
        if hasattr(self.fallback, "warm_up"):
            self.fallback.warm_up()
    
    @component.output_types(embedding=list[float])
    def run(self, text: str):
        try:
            return self.primary.run(text=text)
        except Exception as e:
            logger.warning(f"Primary embedder failed: {e}. Switching to fallback...")
            return self.fallback.run(text=text)
    

@component
class FallbackDocumentEmbedder:
    def __init__(self, embedder: DocumentEmbedder, fallback: DocumentEmbedder):
        self.primary = embedder
        self.fallback = fallback

        if hasattr(self.primary, "warm_up"):
            self.primary.warm_up()
        if hasattr(self.fallback, "warm_up"):
            self.fallback.warm_up()
    
    @component.output_types(documents=list[Document])
    def run(self, documents: list[Document]):
        try:
            return self.primary.run(documents=documents)
        except Exception as e:
            logger.warning(f"Primary embedder failed: {e}. Switching to fallback...")
            return self.fallback.run(documents=documents)
    
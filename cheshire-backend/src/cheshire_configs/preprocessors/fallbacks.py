from haystack import component, Document
from haystack.components.embedders.types import TextEmbedder, DocumentEmbedder

import logging
logger = logging.getLogger("uvicorn.error")

@component
class FallbackTextEmbedder:
    def __init__(self, embedder: TextEmbedder, *fallbacks: TextEmbedder):
        self.primary = embedder
        self.fallbacks = fallbacks

        if hasattr(self.primary, "warm_up"):
            self.primary.warm_up()
        for fallback in self.fallbacks:
            if hasattr(fallback, "warm_up"):
                fallback.warm_up()
    
    @component.output_types(embedding=list[float])
    def run(self, text: str):
        try:
            return self.primary.run(text=text)
        except Exception as err:
            if len(self.fallbacks) > 0:
                logger.warning(f"Primary embedder failed: {err}. Switching to fallbacks...")
            for fallback in self.fallbacks:
                try:
                    return fallback.run(text=text)
                except Exception as fallback_err:
                    logger.warning(f"Fallback embedder {fallback} failed: {fallback_err}")
            raise err
    

@component
class FallbackDocumentEmbedder:
    def __init__(self, embedder: DocumentEmbedder, *fallbacks: DocumentEmbedder):
        self.primary = embedder
        self.fallbacks = fallbacks

        if hasattr(self.primary, "warm_up"):
            self.primary.warm_up()
        for fallback in self.fallbacks:
            if hasattr(fallback, "warm_up"):
                fallback.warm_up()
    
    @component.output_types(documents=list[Document])
    def run(self, documents: list[Document]):
        try:
            return self.primary.run(documents=documents)
        except Exception as err:
            if len(self.fallbacks) > 0:
                logger.warning(f"Primary embedder failed: {err}. Switching to fallbacks...")
            for fallback in self.fallbacks:
                try:
                    return fallback.run(documents=documents)
                except Exception as fallback_err:
                    logger.warning(f"Fallback embedder {fallback} failed: {fallback_err}")
            raise err
    
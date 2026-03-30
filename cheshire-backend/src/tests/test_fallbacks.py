import pytest
from unittest.mock import MagicMock
from haystack import Document
from cheshire_configs.preprocessors.fallbacks import FallbackTextEmbedder, FallbackDocumentEmbedder

class NoWarmupEmbedder:
    def run(self, text: str = None, documents: list[Document] = None):
        if text:
            return {"embedding": [0.1, 0.2, 0.3]}
        return {"documents": [Document(content="test")]}

def test_fallback_text_embedder_init_with_warmup():
    mock_primary = MagicMock()
    mock_fallback = MagicMock()
    
    embedder = FallbackTextEmbedder(mock_primary, mock_fallback)
    
    mock_primary.warm_up.assert_called_once()
    mock_fallback.warm_up.assert_called_once()

def test_fallback_text_embedder_init_with_multi_warmup():
    mock_primary = MagicMock()
    mock_fallback1 = MagicMock()
    mock_fallback2 = MagicMock()
    
    embedder = FallbackTextEmbedder(mock_primary, mock_fallback1, mock_fallback2)
    
    mock_primary.warm_up.assert_called_once()
    mock_fallback1.warm_up.assert_called_once()
    mock_fallback2.warm_up.assert_called_once()

def test_fallback_text_embedder_init_without_warmup():
    primary = NoWarmupEmbedder()
    fallback = NoWarmupEmbedder()
    
    # Should not raise any exceptions
    embedder = FallbackTextEmbedder(primary, fallback)
    assert embedder.primary == primary
    assert fallback in embedder.fallbacks

def test_fallback_text_embedder_run_success():
    mock_primary = MagicMock()
    mock_primary.run.return_value = {"embedding": [0.1, 0.2, 0.3]}
    mock_fallback = MagicMock()
    
    embedder = FallbackTextEmbedder(mock_primary, mock_fallback)
    
    result = embedder.run(text="test text")
    
    assert result == {"embedding": [0.1, 0.2, 0.3]}
    mock_primary.run.assert_called_once_with(text="test text")
    mock_fallback.run.assert_not_called()

def test_fallback_text_embedder_run_fallback(caplog):
    mock_primary = MagicMock()
    mock_primary.run.side_effect = Exception("Primary failed")
    
    mock_fallback = MagicMock()
    mock_fallback.run.return_value = {"embedding": [0.4, 0.5, 0.6]}
    
    embedder = FallbackTextEmbedder(mock_primary, mock_fallback)
    
    result = embedder.run(text="test text")
    
    assert result == {"embedding": [0.4, 0.5, 0.6]}
    mock_primary.run.assert_called_once_with(text="test text")
    mock_fallback.run.assert_called_once_with(text="test text")
    
    assert "Primary embedder failed: Primary failed. Switching to fallbacks..." in caplog.text

def test_fallback_text_embedder_multi_fallbacks(caplog):
    mock_primary = MagicMock()
    mock_primary.run.side_effect = Exception("Primary failed")
    
    mock_fallback1 = MagicMock()
    mock_fallback1.run.side_effect = Exception("Fallback 1 failed")
    
    mock_fallback2 = MagicMock()
    mock_fallback2.run.return_value = {"embedding": [0.7, 0.8, 0.9]}
    
    embedder = FallbackTextEmbedder(mock_primary, mock_fallback1, mock_fallback2)
    
    result = embedder.run(text="test text")
    
    assert result == {"embedding": [0.7, 0.8, 0.9]}
    mock_primary.run.assert_called_once_with(text="test text")
    mock_fallback1.run.assert_called_once_with(text="test text")
    mock_fallback2.run.assert_called_once_with(text="test text")
    
    assert "Primary embedder failed: Primary failed. Switching to fallbacks..." in caplog.text
    assert "Fallback embedder" in caplog.text # Should log fallback 1 failure

def test_fallback_text_embedder_all_fail():
    mock_primary = MagicMock()
    mock_primary.run.side_effect = Exception("Primary failed")
    
    mock_fallback1 = MagicMock()
    mock_fallback1.run.side_effect = Exception("Fallback 1 failed")
    
    embedder = FallbackTextEmbedder(mock_primary, mock_fallback1)
    
    with pytest.raises(Exception, match="Primary failed"):
        # The loop raises the original error 'err' if all fallbacks fail
        embedder.run(text="test text")

def test_fallback_document_embedder_run_success():
    mock_primary = MagicMock()
    docs = [Document(content="doc1")]
    mock_primary.run.return_value = {"documents": docs}
    
    embedder = FallbackDocumentEmbedder(mock_primary)
    
    result = embedder.run(documents=docs)
    
    assert result == {"documents": docs}
    mock_primary.run.assert_called_once_with(documents=docs)

def test_fallback_document_embedder_run_fallback(caplog):
    mock_primary = MagicMock()
    mock_primary.run.side_effect = Exception("Primary failed")
    
    docs = [Document(content="doc1")]
    mock_fallback = MagicMock()
    mock_fallback.run.return_value = {"documents": docs}
    
    embedder = FallbackDocumentEmbedder(mock_primary, mock_fallback)
    
    result = embedder.run(documents=docs)
    
    assert result == {"documents": docs}
    mock_primary.run.assert_called_once_with(documents=docs)
    mock_fallback.run.assert_called_once_with(documents=docs)
    assert "Primary embedder failed: Primary failed. Switching to fallbacks..." in caplog.text

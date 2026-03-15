import pytest
from unittest.mock import MagicMock
from cheshire_configs.preprocessors.fallbacks import FallbackTextEmbedder

class NoWarmupEmbedder:
    def run(self, text: str):
        return {"embedding": [0.1, 0.2, 0.3]}

def test_fallback_text_embedder_init_with_warmup():
    mock_primary = MagicMock()
    mock_fallback = MagicMock()
    
    embedder = FallbackTextEmbedder(embedder=mock_primary, fallback=mock_fallback)
    
    mock_primary.warm_up.assert_called_once()
    mock_fallback.warm_up.assert_called_once()

def test_fallback_text_embedder_init_without_warmup():
    primary = NoWarmupEmbedder()
    fallback = NoWarmupEmbedder()
    
    # Should not raise any exceptions
    embedder = FallbackTextEmbedder(embedder=primary, fallback=fallback)
    assert hasattr(embedder, "primary")
    assert hasattr(embedder, "fallback")

def test_fallback_text_embedder_run_success():
    mock_primary = MagicMock()
    mock_primary.run.return_value = {"embedding": [0.1, 0.2, 0.3]}
    mock_fallback = MagicMock()
    
    embedder = FallbackTextEmbedder(embedder=mock_primary, fallback=mock_fallback)
    
    result = embedder.run(text="test text")
    
    assert result == {"embedding": [0.1, 0.2, 0.3]}
    mock_primary.run.assert_called_once_with(text="test text")
    mock_fallback.run.assert_not_called()

def test_fallback_text_embedder_run_fallback(caplog):
    mock_primary = MagicMock()
    mock_primary.run.side_effect = Exception("Primary failed")
    
    mock_fallback = MagicMock()
    mock_fallback.run.return_value = {"embedding": [0.4, 0.5, 0.6]}
    
    embedder = FallbackTextEmbedder(embedder=mock_primary, fallback=mock_fallback)
    
    result = embedder.run(text="test text")
    
    assert result == {"embedding": [0.4, 0.5, 0.6]}
    mock_primary.run.assert_called_once_with(text="test text")
    mock_fallback.run.assert_called_once_with(text="test text")
    
    assert "Primary embedder failed: Primary failed. Switching to fallback..." in caplog.text

def test_fallback_text_embedder_both_fail():
    mock_primary = MagicMock()
    mock_primary.run.side_effect = Exception("Primary failed")
    
    mock_fallback = MagicMock()
    mock_fallback.run.side_effect = Exception("Fallback also failed")
    
    embedder = FallbackTextEmbedder(embedder=mock_primary, fallback=mock_fallback)
    
    with pytest.raises(Exception, match="Fallback also failed"):
        embedder.run(text="test text")

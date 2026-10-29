import json
import pytest
from unittest.mock import MagicMock
from haystack.utils import Secret
from cheshire_configs.resilient_generator import (
    wrap_generator_with_retry,
    make_resilient_openrouter_generator,
    RETRYABLE_EXCEPTIONS,
)
from endpoints.evaluate import _format_user_friendly_error


def test_user_friendly_error_formatting():
    # test json decode error message
    err_json = json.decoder.JSONDecodeError("Expecting value: line 7 column 1 (char 33)", "", 33)
    assert _format_user_friendly_error(err_json) == "Upstream LLM provider returned a malformed response. Please retry."

    # test rate limit error message
    err_rate = RuntimeError("429 rate limit exceeded")
    assert _format_user_friendly_error(err_rate) == "LLM rate limit reached. Please wait a moment and retry."

    # test timeout error message
    err_timeout = RuntimeError("request timed out")
    assert _format_user_friendly_error(err_timeout) == "LLM request timed out. Please retry."

    # test generic fallback message
    err_generic = ValueError("custom failure")
    assert _format_user_friendly_error(err_generic) == "custom failure"


def test_generator_retries_on_json_decode_error():
    # generator recovers after transient json decode failure
    gen = make_resilient_openrouter_generator(api_key=Secret.from_token("dummy"), max_retries=3)

    call_count = 0
    orig_run = MagicMock()

    def mock_run(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise json.decoder.JSONDecodeError("Expecting value: line 7 column 1 (char 33)", "", 33)
        return {"replies": ["success"]}

    orig_run.side_effect = mock_run
    gen.run = orig_run
    wrap_generator_with_retry(gen, max_attempts=3, min_wait=0.01, max_wait=0.05)

    result = gen.run()
    assert result == {"replies": ["success"]}
    assert call_count == 3


def test_generator_raises_after_exceeding_max_retries():
    # generator raises when all retry attempts fail
    gen = make_resilient_openrouter_generator(api_key=Secret.from_token("dummy"), max_retries=2)

    orig_run = MagicMock(side_effect=json.decoder.JSONDecodeError("Expecting value", "", 0))
    gen.run = orig_run
    wrap_generator_with_retry(gen, max_attempts=2, min_wait=0.01, max_wait=0.02)

    with pytest.raises(json.decoder.JSONDecodeError):
        gen.run()


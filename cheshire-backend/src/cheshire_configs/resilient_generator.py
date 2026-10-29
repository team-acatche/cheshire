import json
import logging
import os
from functools import wraps
from typing import Any, Callable

import httpx
import openai
from haystack.utils import Secret
from haystack_integrations.components.generators.openrouter import OpenRouterChatGenerator
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

# transient openrouter and network exceptions to retry
RETRYABLE_EXCEPTIONS = (
    json.decoder.JSONDecodeError,
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.InternalServerError,
    openai.RateLimitError,
    openai.APIResponseValidationError,
    httpx.HTTPError,
)


def create_retry_decorator(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
) -> Callable:
    # exponential backoff retry decorator
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=min_wait, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


def wrap_generator_with_retry(
    generator: OpenRouterChatGenerator,
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
) -> OpenRouterChatGenerator:
    # wrap generator run and run_async with retry logic
    retry_dec = create_retry_decorator(max_attempts=max_attempts, min_wait=min_wait, max_wait=max_wait)

    orig_run = generator.run

    @wraps(orig_run)
    def retrying_run(*args: Any, **kwargs: Any) -> Any:
        return retry_dec(orig_run)(*args, **kwargs)

    orig_run_async = generator.run_async

    @wraps(orig_run_async)
    async def retrying_run_async(*args: Any, **kwargs: Any) -> Any:
        return await retry_dec(orig_run_async)(*args, **kwargs)

    generator.run = retrying_run  # type: ignore[method-assign]
    generator.run_async = retrying_run_async  # type: ignore[method-assign]
    return generator


def make_resilient_openrouter_generator(
    api_key: Secret | None = None,
    model: str | None = None,
    timeout: float = 120.0,
    max_retries: int = 3,
    **kwargs: Any,
) -> OpenRouterChatGenerator:
    # instantiate generator with timeout and retry wrapper
    resolved_api_key = api_key or Secret.from_env_var("OPENROUTER_API_KEY")
    resolved_model = model or os.getenv("OPENROUTER_MODEL", "ServiceNow-AI/Apriel-1.6-15b-Thinker")

    generator = OpenRouterChatGenerator(
        api_key=resolved_api_key,
        model=resolved_model,
        timeout=timeout,
        max_retries=max_retries,
        **kwargs,
    )
    return wrap_generator_with_retry(generator, max_attempts=max_retries)

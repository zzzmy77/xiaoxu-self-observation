"""
LLM call helper with retry, timeout, and fallback.
"""
import logging
import time
from functools import wraps

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30  # seconds


def llm_call(client, **kwargs):
    """Make an LLM API call with retry + timeout.

    Usage:
        resp = llm_call(
            client.chat.completions.create,
            model=...,
            messages=...,
            temperature=...,
            max_tokens=...,
            stream=False,
        )
    """
    max_retries = kwargs.pop("_max_retries", DEFAULT_MAX_RETRIES)
    timeout = kwargs.pop("_timeout", DEFAULT_TIMEOUT)

    # Add timeout to kwargs if the client supports it
    kwargs["timeout"] = timeout

    last_error = None
    for attempt in range(max_retries):
        try:
            return client(**kwargs)
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = 2 ** attempt  # 1, 2, 4 seconds
                logger.warning("LLM call attempt %d failed: %s. Retrying in %ds...",
                               attempt + 1, e, wait)
                time.sleep(wait)

    logger.error("LLM call failed after %d retries: %s", max_retries, last_error)
    raise last_error

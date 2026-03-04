"""
NT AI Assistant - Retry Configuration
=======================================
Shared retry decorator for all AI providers.
"""

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


def create_retry_decorator():
    """Create retry decorator with standard configuration"""
    exceptions_to_retry = [
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.ReadTimeout,
    ]

    try:
        import anthropic
        exceptions_to_retry.extend([
            anthropic.RateLimitError,
            anthropic.APIError,
            anthropic.APIConnectionError,
        ])
    except ImportError:
        pass

    try:
        from google.api_core import exceptions as google_exceptions
        exceptions_to_retry.extend([
            google_exceptions.ResourceExhausted,
            google_exceptions.ServiceUnavailable,
            google_exceptions.DeadlineExceeded,
            google_exceptions.InternalServerError,
        ])
    except ImportError:
        pass

    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(tuple(exceptions_to_retry)),
        reraise=True,
    )


ai_retry = create_retry_decorator()

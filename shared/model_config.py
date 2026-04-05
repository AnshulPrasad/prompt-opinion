"""
Shared Gemini model configuration for all agents.
"""
from google.adk.models.google_llm import Gemini
from google.genai import types


def gemini_flash_with_retries() -> Gemini:
    """
    Gemini 2.5 Flash with bounded retry/backoff for transient provider errors.
    """
    return Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(
            attempts=4,
            initial_delay=1.0,
            max_delay=8.0,
            exp_base=2.0,
            jitter=1.0,
            http_status_codes=[429, 500, 502, 503, 504],
        ),
    )

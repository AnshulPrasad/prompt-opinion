"""
Helpers for turning verbose provider quota exceptions into short user-facing text.

Google ADK currently publishes str(exception) back into the final A2A failure
message. For Gemini 429s this includes a large provider payload that is useful
for debugging but poor UX for Prompt Opinion callers. We monkey-patch the ADK
quota exception stringification to return a concise retry message instead.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_RETRY_SECONDS_PATTERN = re.compile(r"retry(?: in)?\s+([0-9]+(?:\.[0-9]+)?)s", re.IGNORECASE)


def _extract_retry_delay_seconds(exc) -> int | None:
    """Best-effort extraction of a retry delay from ADK / GenAI exception details."""
    details = getattr(exc, "details", None)
    error_block = details.get("error", details) if isinstance(details, dict) else None
    if isinstance(error_block, dict):
        for detail in error_block.get("details", []):
            if not isinstance(detail, dict):
                continue
            retry_delay = detail.get("retryDelay")
            if isinstance(retry_delay, str) and retry_delay.endswith("s"):
                try:
                    return max(1, round(float(retry_delay[:-1])))
                except ValueError:
                    pass

        message = error_block.get("message")
        if isinstance(message, str):
            match = _RETRY_SECONDS_PATTERN.search(message)
            if match:
                try:
                    return max(1, round(float(match.group(1))))
                except ValueError:
                    return None
    return None


def install_quota_error_sanitizer() -> None:
    """
    Patch ADK's Gemini quota exception to return a short, caller-safe message.

    This is intentionally idempotent so every agent package can import it
    without changing behavior after the first call.
    """
    try:
        from google.adk.models.google_llm import _ResourceExhaustedError
    except Exception:
        logger.exception("quota_error_sanitizer_install_failed")
        return

    if getattr(_ResourceExhaustedError, "_prompt_opinion_sanitized", False):
        return

    def _sanitized_str(self) -> str:
        retry_seconds = _extract_retry_delay_seconds(self)
        if retry_seconds is not None:
            return (
                "The model is temporarily rate-limited. "
                f"Please retry in about {retry_seconds} seconds."
            )
        return (
            "The model is temporarily rate-limited. "
            "Please retry shortly."
        )

    _ResourceExhaustedError.__str__ = _sanitized_str
    _ResourceExhaustedError._prompt_opinion_sanitized = True


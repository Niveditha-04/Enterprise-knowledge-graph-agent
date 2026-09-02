"""Application errors for dependency and API failures."""

from __future__ import annotations

AI_SERVICE_UNAVAILABLE_MESSAGE = (
    "The AI service is temporarily unavailable. Please retry in a moment."
)

TICKET_INDEX_UNAVAILABLE_ERROR = "Support ticket search is currently unavailable."


class AIServiceUnavailableError(Exception):
    """Raised when Anthropic is overloaded, rate-limited, or unreachable."""

    def __init__(self, message: str = AI_SERVICE_UNAVAILABLE_MESSAGE) -> None:
        self.message = message
        super().__init__(message)


def anthropic_unavailable_error(exc: BaseException) -> AIServiceUnavailableError | None:
    """Map Anthropic client errors to a user-safe unavailable error."""
    try:
        from anthropic import APIConnectionError, APIStatusError, APITimeoutError
    except ImportError:
        return None

    if isinstance(exc, APITimeoutError):
        return AIServiceUnavailableError()
    if isinstance(exc, APIConnectionError):
        return AIServiceUnavailableError()
    if isinstance(exc, APIStatusError) and exc.status_code in (429, 529):
        return AIServiceUnavailableError()
    return None

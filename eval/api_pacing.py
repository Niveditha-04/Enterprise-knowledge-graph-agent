"""Conservative pacing for evaluation harnesses that call the Anthropic API."""

from __future__ import annotations

import time
from typing import Callable, TypeVar

from anthropic import APIStatusError

INTER_REQUEST_DELAY_S = 5
MAX_RETRY_ATTEMPTS = 2
MAX_RETRY_WAIT_S = 15
RATE_LIMIT_CODES = {429, 529}

T = TypeVar("T")


class EvaluationAbortedDueToRateLimit(Exception):
    """Stop evaluation when Anthropic returns sustained server-side overload (529)."""


def run_with_pacing(
    fn: Callable[[], T],
    *,
    retry_log: list[dict] | None = None,
    max_attempts: int = MAX_RETRY_ATTEMPTS,
    abort_on_rate_limit: bool = True,
) -> T:
    """Call fn with capped retries on 429/529 and exponential backoff."""
    throttle_events = retry_log if retry_log is not None else []
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except APIStatusError as exc:
            wait_s = min(MAX_RETRY_WAIT_S, 2**attempt)
            throttle_events.append(
                {
                    "attempt": attempt,
                    "status_code": exc.status_code,
                    "wait_s": wait_s,
                    "message": str(exc),
                }
            )
            if attempt >= max_attempts:
                if abort_on_rate_limit and exc.status_code in RATE_LIMIT_CODES:
                    raise EvaluationAbortedDueToRateLimit(
                        f"Anthropic API server-side capacity error persisted after "
                        f"{max_attempts} retries: {exc.status_code}"
                    ) from exc
                raise
            time.sleep(wait_s)


def pace_between_requests(delay_s: float = INTER_REQUEST_DELAY_S) -> None:
    time.sleep(delay_s)

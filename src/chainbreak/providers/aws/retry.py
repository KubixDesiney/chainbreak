"""Retry policy for transient AWS faults (AWS_PROVIDER_SPEC section 6.3).

Transient classes only, full-jitter exponential backoff, up to 3 attempts.
``AccessDenied``-shaped errors are never retried -- retrying a denial is
exactly how a timing artifact gets manufactured by accident, which is why
this module is the single place retry policy is decided rather than each
probe implementing its own.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass

from botocore.exceptions import ClientError, EndpointConnectionError

_MAX_ATTEMPTS = 3
_BASE_MS = 200
_CAP_MS = 2000

#: botocore error codes that represent a transient provider fault, not an
#: authorization outcome (AWS_PROVIDER_SPEC section 6.3).
TRANSIENT_ERROR_CODES = frozenset(
    {
        "Throttling",
        "ThrottlingException",
        "RequestLimitExceeded",
        "TooManyRequestsException",
        "ProvisionedThroughputExceededException",
        "InternalError",
        "InternalServerError",
        "ServiceUnavailable",
    }
)

#: Never retried, regardless of how many attempts remain (S1/S3's own
#: guarantee that a denial is reported, not silently repeated).
_NEVER_RETRY_CODES = frozenset(
    {
        "AccessDenied",
        "AccessDeniedException",
        "UnauthorizedException",
    }
)


def error_code(exc: ClientError) -> str:
    return exc.response.get("Error", {}).get("Code", "")


def http_status(exc: ClientError) -> int | None:
    return exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")


def is_transient(exc: BaseException) -> bool:
    """Whether ``exc`` represents a fault worth retrying.

    Connection-level failures (no HTTP response at all) are always
    transient. A ``ClientError`` is transient only if its error code is in
    :data:`TRANSIENT_ERROR_CODES`, or its HTTP status is 500/503, and it is
    never one of :data:`_NEVER_RETRY_CODES` -- the deny-code check takes
    priority so a service that reused a 503 status on a denial (real AWS
    services do not, but the check costs nothing) still refuses to retry.
    """
    if isinstance(exc, EndpointConnectionError):
        return True
    if not isinstance(exc, ClientError):
        return False
    code = error_code(exc)
    if code in _NEVER_RETRY_CODES:
        return False
    if code in TRANSIENT_ERROR_CODES:
        return True
    status = http_status(exc)
    return status in (500, 503)


def full_jitter_backoff_ms(attempt: int, *, rng: random.Random | None = None) -> float:
    """Full-jitter exponential backoff (AWS's own documented algorithm):
    ``uniform(0, min(cap, base * 2**attempt))``. ``attempt`` is 0-indexed
    (the delay before the *second* call, i.e. after the first failure)."""
    source = rng or random
    ceiling = min(_CAP_MS, _BASE_MS * (2**attempt))
    return source.uniform(0, ceiling)


@dataclass(frozen=True, slots=True)
class RetryOutcome:
    """What :func:`call_with_retry` learned, for ``ProbeTiming``."""

    attempt_number: int
    retries: int


def call_with_retry[T](
    fn: Callable[[], T],
    *,
    max_attempts: int = _MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> tuple[T | None, BaseException | None, RetryOutcome]:
    """Call ``fn`` (a zero-argument thunk wrapping one AWS API call),
    retrying on a transient fault up to ``max_attempts`` total attempts.

    Always returns a 3-tuple rather than raising, so the caller learns the
    ``RetryOutcome`` (for ``ProbeTiming.attempt_number``/``.retries``) even
    on final failure: ``(result, None, outcome)`` on success,
    ``(None, exception, outcome)`` once attempts are exhausted or the
    exception was not transient in the first place (``AccessDenied`` is
    never retried -- F8).
    """
    for attempt in range(max_attempts):
        try:
            result = fn()
        except (ClientError, EndpointConnectionError) as exc:
            if not is_transient(exc) or attempt == max_attempts - 1:
                return None, exc, RetryOutcome(attempt_number=attempt + 1, retries=attempt)
            sleep(full_jitter_backoff_ms(attempt, rng=rng) / 1000.0)
            continue
        return result, None, RetryOutcome(attempt_number=attempt + 1, retries=attempt)
    raise AssertionError("unreachable: loop always returns")  # pragma: no cover

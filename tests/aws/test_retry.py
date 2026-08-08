"""``providers/aws/retry.py``: transient-fault classification and the
full-jitter backoff/retry loop. Pure logic -- exceptions are constructed by
hand, never raised by a real or moto-backed AWS call, so this needs no
network and no AWS account.
"""

from __future__ import annotations

import random

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from chainbreak.providers.aws.retry import (
    call_with_retry,
    error_code,
    full_jitter_backoff_ms,
    http_status,
    is_transient,
)

pytestmark = pytest.mark.unit


def _client_error(code: str, *, status: int | None = None) -> ClientError:
    response = {"Error": {"Code": code}}
    if status is not None:
        response["ResponseMetadata"] = {"HTTPStatusCode": status}
    return ClientError(response, "SomeOperation")


class TestErrorCodeAndHttpStatus:
    def test_error_code_extracted(self):
        assert error_code(_client_error("Throttling")) == "Throttling"

    def test_http_status_extracted(self):
        assert http_status(_client_error("Throttling", status=503)) == 503

    def test_http_status_missing_is_none(self):
        assert http_status(_client_error("Throttling")) is None


class TestIsTransient:
    def test_endpoint_connection_error_is_transient(self):
        assert is_transient(EndpointConnectionError(endpoint_url="https://example.invalid")) is True

    def test_non_client_error_is_not_transient(self):
        assert is_transient(ValueError("not an AWS error")) is False

    @pytest.mark.parametrize(
        "code",
        [
            "Throttling",
            "ThrottlingException",
            "RequestLimitExceeded",
            "TooManyRequestsException",
            "ProvisionedThroughputExceededException",
            "InternalError",
            "InternalServerError",
            "ServiceUnavailable",
        ],
    )
    def test_known_transient_codes(self, code):
        assert is_transient(_client_error(code)) is True

    def test_http_500_without_a_known_code_is_transient(self):
        assert is_transient(_client_error("SomeUnknownCode", status=500)) is True

    def test_http_503_without_a_known_code_is_transient(self):
        assert is_transient(_client_error("SomeUnknownCode", status=503)) is True

    @pytest.mark.parametrize(
        "code", ["AccessDenied", "AccessDeniedException", "UnauthorizedException"]
    )
    def test_never_retry_codes_are_never_transient(self, code):
        assert is_transient(_client_error(code)) is False

    def test_never_retry_code_wins_even_with_a_503_status(self):
        # A pathological response reusing a transient-shaped status on a
        # denial must still refuse to retry -- the deny-code check takes
        # priority (retry.py's own documented ordering).
        assert is_transient(_client_error("AccessDenied", status=503)) is False

    def test_unrecognized_code_and_status_is_not_transient(self):
        assert is_transient(_client_error("ValidationException", status=400)) is False


class TestFullJitterBackoff:
    def test_bounded_by_the_cap(self):
        rng = random.Random(0)
        for attempt in range(10):
            delay = full_jitter_backoff_ms(attempt, rng=rng)
            assert 0 <= delay <= 2000

    def test_zero_attempt_bounded_by_base(self):
        rng = random.Random(0)
        for _ in range(50):
            assert 0 <= full_jitter_backoff_ms(0, rng=rng) <= 200

    def test_deterministic_with_a_seeded_rng(self):
        first = full_jitter_backoff_ms(2, rng=random.Random(42))
        second = full_jitter_backoff_ms(2, rng=random.Random(42))
        assert first == second


class TestCallWithRetry:
    def test_success_on_first_attempt(self):
        result, exc, outcome = call_with_retry(lambda: "ok")
        assert result == "ok"
        assert exc is None
        assert outcome.attempt_number == 1
        assert outcome.retries == 0

    def test_non_transient_failure_returns_immediately_without_sleeping(self):
        sleeps: list[float] = []
        calls = {"n": 0}

        def _fn():
            calls["n"] += 1
            raise _client_error("AccessDenied")

        result, exc, outcome = call_with_retry(_fn, sleep=sleeps.append)
        assert result is None
        assert isinstance(exc, ClientError)
        assert outcome.attempt_number == 1
        assert outcome.retries == 0
        assert calls["n"] == 1
        assert sleeps == []

    def test_transient_failure_retries_then_succeeds(self):
        sleeps: list[float] = []
        calls = {"n": 0}

        def _fn():
            calls["n"] += 1
            if calls["n"] < 3:
                raise _client_error("Throttling")
            return "eventually ok"

        result, exc, outcome = call_with_retry(_fn, sleep=sleeps.append, rng=random.Random(1))
        assert result == "eventually ok"
        assert exc is None
        assert outcome.attempt_number == 3
        assert outcome.retries == 2
        assert len(sleeps) == 2

    def test_transient_failure_exhausts_all_attempts_and_reports_them(self):
        calls = {"n": 0}

        def _fn():
            calls["n"] += 1
            raise _client_error("Throttling")

        result, exc, outcome = call_with_retry(
            _fn, max_attempts=3, sleep=lambda _s: None, rng=random.Random(2)
        )
        assert result is None
        assert isinstance(exc, ClientError)
        assert outcome.attempt_number == 3
        assert outcome.retries == 2
        assert calls["n"] == 3

    def test_endpoint_connection_error_is_retried(self):
        calls = {"n": 0}

        def _fn():
            calls["n"] += 1
            if calls["n"] < 2:
                raise EndpointConnectionError(endpoint_url="https://example.invalid")
            return "ok"

        result, exc, outcome = call_with_retry(_fn, sleep=lambda _s: None)
        assert result == "ok"
        assert exc is None
        assert outcome.retries == 1

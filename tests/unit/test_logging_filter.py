"""cli/logging.py -- the redaction filter (SI-10, S2).

Acceptance criterion 3: a botocore DEBUG log containing a session-token-shaped
string is scrubbed. Also covers the AKIA/ASIA access-key pattern, the
secret-access-key pattern, JSON-quoted key/value pairs (not just
``key: value``), idempotent ``install()``, and that third-party loggers
(botocore/boto3/urllib3) are covered even if a library sets
``propagate = False`` on itself.
"""

from __future__ import annotations

import logging

import pytest

from chainbreak.cli.logging import _THIRD_PARTY_LOGGERS, RedactionFilter, install

pytestmark = pytest.mark.unit


def _filtered_message(text: str) -> str:
    record = logging.LogRecord(
        name="test",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg=text,
        args=(),
        exc_info=None,
    )
    RedactionFilter().filter(record)
    return str(record.msg)


class TestAccessKeyPattern:
    def test_akia_key_is_redacted(self):
        assert "AKIA" not in _filtered_message("key=AKIAIOSFODNN7EXAMPLE")
        assert "<REDACTED>" in _filtered_message("key=AKIAIOSFODNN7EXAMPLE")

    def test_asia_temporary_key_is_redacted(self):
        assert "ASIA" not in _filtered_message("key=ASIAIOSFODNN7EXAMPLE")

    def test_message_without_a_key_is_untouched(self):
        text = "GET /health 200 OK"
        assert _filtered_message(text) == text


class TestSessionTokenPattern:
    def test_botocore_style_debug_log_is_scrubbed(self):
        # Acceptance criterion 3: a simulated botocore DEBUG record.
        raw = (
            "DEBUG botocore.endpoint: Making request with params: "
            '{"headers": {"X-Amz-Security-Token": '
            '"FQoGZXIvYXdzEBcaDMexampleSessionTokenValueXYZ123=="}}'
        )
        scrubbed = _filtered_message(raw)
        assert "FQoGZXIvYXdzEBcaDMexampleSessionTokenValueXYZ123==" not in scrubbed
        assert "<REDACTED>" in scrubbed

    def test_key_value_style_security_token(self):
        scrubbed = _filtered_message("security-token=AQoDYXdzEJr01234567890abcdefghijklmnop")
        assert "AQoDYXdzEJr01234567890abcdefghijklmnop" not in scrubbed

    def test_plain_session_token_field(self):
        scrubbed = _filtered_message('"session_token": "abcdefghijklmnopqrstuvwxyz0123456789"')
        assert "abcdefghijklmnopqrstuvwxyz0123456789" not in scrubbed


class TestSecretAccessKeyPattern:
    def test_secret_access_key_is_redacted(self):
        scrubbed = _filtered_message("secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")
        assert "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" not in scrubbed
        assert "<REDACTED>" in scrubbed


class TestBothInOneMessage:
    def test_akia_and_session_token_both_redacted(self):
        raw = (
            "access_key=AKIAIOSFODNN7EXAMPLE "
            'security-token="AQoDYXdzEJr01234567890abcdefghijklmnop"'
        )
        scrubbed = _filtered_message(raw)
        assert "AKIA" not in scrubbed
        assert "AQoDYXdzEJr01234567890abcdefghijklmnop" not in scrubbed


class TestFilterAlwaysReturnsTrue:
    def test_records_are_never_dropped(self):
        record = logging.LogRecord(
            name="t",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        assert RedactionFilter().filter(record) is True

    def test_args_are_cleared_after_filtering(self):
        record = logging.LogRecord(
            name="t",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="value=%s",
            args=("AKIAIOSFODNN7EXAMPLE",),
            exc_info=None,
        )
        RedactionFilter().filter(record)
        assert record.args == ()
        assert "AKIA" not in str(record.msg)


class TestInstall:
    def _reset_logging(self) -> None:
        root = logging.getLogger()
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for name in _THIRD_PARTY_LOGGERS:
            logger = logging.getLogger(name)
            for f in list(logger.filters):
                logger.removeFilter(f)

    def test_install_adds_a_handler_when_none_exists(self):
        self._reset_logging()
        try:
            install()
            root = logging.getLogger()
            assert len(root.handlers) >= 1
            assert any(isinstance(f, RedactionFilter) for h in root.handlers for f in h.filters)
        finally:
            self._reset_logging()

    def test_install_is_idempotent(self):
        self._reset_logging()
        try:
            install()
            install()
            root = logging.getLogger()
            for handler in root.handlers:
                redaction_filters = [f for f in handler.filters if isinstance(f, RedactionFilter)]
                assert len(redaction_filters) <= 1
        finally:
            self._reset_logging()

    def test_third_party_loggers_get_the_filter_and_propagate(self):
        self._reset_logging()
        try:
            install()
            for name in _THIRD_PARTY_LOGGERS:
                logger = logging.getLogger(name)
                assert logger.propagate is True
                assert any(isinstance(f, RedactionFilter) for f in logger.filters)
        finally:
            self._reset_logging()

    def test_third_party_logger_still_redacted_if_propagate_was_false(self):
        # Defense in depth: even a library that sets propagate=False on
        # itself still has the filter attached directly.
        self._reset_logging()
        logging.getLogger("botocore").propagate = False
        try:
            install()
            botocore_logger = logging.getLogger("botocore")
            record = botocore_logger.makeRecord(
                "botocore", logging.DEBUG, __file__, 1, "key=AKIAIOSFODNN7EXAMPLE", (), None
            )
            for f in botocore_logger.filters:
                f.filter(record)
            assert "AKIA" not in str(record.msg)
        finally:
            self._reset_logging()

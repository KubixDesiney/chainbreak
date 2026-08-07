"""Structured logging with the redaction filter installed at startup (SI-10).

``install()`` must run before any other import that might configure logging
or emit a record -- the very first lines of ``cli/main.py``, before any
command module (and therefore before ``botocore``, which logs request
headers, including credential material, at ``DEBUG``) is imported.

The filter is attached in two places for defense in depth: on the root
logger's handlers (so anything that propagates there, which is nearly
everything by default) and directly on the specific third-party loggers
named below, in case a library ever sets ``propagate = False`` on itself.
"""

from __future__ import annotations

import logging
import re

_REDACTED = "<REDACTED>"

#: Loggers known to emit credential-shaped content at DEBUG (botocore logs
#: full request/response headers, including the Authorization header and
#: security-token headers, at DEBUG).
_THIRD_PARTY_LOGGERS = ("botocore", "boto3", "urllib3")

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(AKIA|ASIA)[0-9A-Z]{16}"), _REDACTED),
    # Matches header/field names however they're quoted or punctuated: JSON
    # ("X-Amz-Security-Token": "..."), key=value, or a bare colon -- the
    # separator between name and value is what varies, not the name itself.
    (
        re.compile(r'(?i)("?(?:x-amz-)?security[-_]?token"?\s*[:=]\s*"?)[A-Za-z0-9+/=_.-]{20,}'),
        r"\1" + _REDACTED,
    ),
    (
        re.compile(r'(?i)("?session[-_]?token"?\s*[:=]\s*"?)[A-Za-z0-9+/=_.-]{20,}'),
        r"\1" + _REDACTED,
    ),
    (
        re.compile(r'(?i)("?secret[-_]?access[-_]?key"?\s*[:=]\s*"?)[A-Za-z0-9+/=]{16,}'),
        r"\1" + _REDACTED,
    ),
)


def _redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class RedactionFilter(logging.Filter):
    """Scrubs credential-shaped strings from every record it sees."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact(str(record.getMessage()))
        record.args = ()
        return True


def install(*, level: int = logging.INFO) -> None:
    """Install the redaction filter. Safe to call more than once."""
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
    root.setLevel(level)

    redaction_filter = RedactionFilter()
    for root_handler in root.handlers:
        if not any(isinstance(existing, RedactionFilter) for existing in root_handler.filters):
            root_handler.addFilter(redaction_filter)

    for name in _THIRD_PARTY_LOGGERS:
        logger = logging.getLogger(name)
        logger.propagate = True
        if not any(isinstance(existing, RedactionFilter) for existing in logger.filters):
            logger.addFilter(redaction_filter)

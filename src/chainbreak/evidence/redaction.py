"""SI-1 layer 2: the single serialization choke point (EV-1).

Every record passes through :func:`redact` before it reaches a JSONL stream,
``manifest.json``, or any other artifact on disk. Detecting a secret-shaped
value **raises** :class:`SecretLeakError` and aborts the run -- this function
never sanitizes and continues (S2 in M06-evidence-pipeline.md). A leak is a
bug to fix, not a value to clean up.

The raised error message never contains the matched text itself, only the
field path and the name of the pattern that fired -- otherwise the exception
report would itself be the leak.

Two independent pattern families:

* **Secret-shaped** (``_SECRET_PATTERNS`` plus the base64-blob check below) --
  credential material. A hit is fatal.
* **Identifier-shaped** (``ARN_PATTERN`` and friends) -- not secret, but
  privacy-sensitive (T-13). These are redacted *in place* by
  :func:`redact_message`, substituting a placeholder while preserving
  sentence structure, because the sentence shape is what carries
  ``denial_attribution`` (ADR-013). This path never raises.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final

from pydantic import BaseModel

from chainbreak.core.errors import SecretLeakError
from chainbreak.core.models import AuthoritySet
from chainbreak.core.secrets import SecretMaterial

# ---------------------------------------------------------------------------
# Secret-shaped patterns (fatal on match) -- SI-1 pattern table.
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("aws_access_key_id", re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}")),
    ("aws_secret_access_key", re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*\S+")),
    ("x_amz_security_token", re.compile(r"(?i)x-amz-security-token\s*[:=]\s*\S+")),
    ("pem_private_key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    (
        "jwt",
        re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    ),
)

# A run of >=40 base64-alphabet characters is credential-shaped (SI-1: "base64
# runs >= 40 chars"). Pure lowercase hex is excluded: SHA-256 digests (always
# ``sha256:`` + 64 lowercase hex) and full git commit SHAs are exactly this
# shape and appear throughout legitimate evidence (identity_ref_hash,
# compiled_hash, git_commit, ...); neither is secret. A real AWS secret access
# key or session token is mixed-case and/or contains ``+``, ``/`` or ``=``,
# which a pure-hex string never does.
_BASE64_BLOB: Final = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")
_HEX_ONLY: Final = re.compile(r"^[0-9a-f]+$")


def _is_benign_hex(candidate: str) -> bool:
    return bool(_HEX_ONLY.match(candidate))


# ---------------------------------------------------------------------------
# Identifier-shaped patterns (redacted in place, never fatal) -- ADR-013.
# ---------------------------------------------------------------------------

ARN_PATTERN: Final = re.compile(r"arn:aws[a-zA-Z0-9-]*:[a-zA-Z0-9-]*:[a-zA-Z0-9-]*:\d{12}:\S*")
ACCOUNT_ID_PATTERN: Final = re.compile(r"(?<!\d)\d{12}(?!\d)")
HOSTNAME_PATTERN: Final = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"(?:amazonaws\.com|compute\.internal|ec2\.internal)\b"
)
SESSION_NAME_PATTERN: Final = re.compile(r"(?i)(session[-_]?name\"?\s*[:=]\s*\"?)([^\s\"',}]+)")

REDACTED_ARN: Final = "<REDACTED_ARN>"
REDACTED_ACCOUNT: Final = "<REDACTED_ACCOUNT>"
REDACTED_HOSTNAME: Final = "<REDACTED_HOSTNAME>"
REDACTED_SESSION_NAME: Final = "<REDACTED_SESSION_NAME>"


def redact_message(text: str) -> str:
    """Replace identifier-shaped substrings in place (ADR-013).

    Never raises. ARNs carry an account ID already, so the ARN substitution
    runs first to avoid double-marking the same span.
    """
    text = ARN_PATTERN.sub(REDACTED_ARN, text)
    text = HOSTNAME_PATTERN.sub(REDACTED_HOSTNAME, text)
    text = ACCOUNT_ID_PATTERN.sub(REDACTED_ACCOUNT, text)
    return text


# ---------------------------------------------------------------------------
# The choke point.
# ---------------------------------------------------------------------------


def _check_string(value: str, path: str) -> None:
    for name, pattern in _SECRET_PATTERNS:
        if pattern.search(value):
            raise SecretLeakError(
                f"secret-shaped value detected at {path} (pattern={name})",
                field_path=path,
                pattern=name,
            )
    for match in _BASE64_BLOB.finditer(value):
        candidate = match.group(0).rstrip("=")
        if not _is_benign_hex(candidate):
            raise SecretLeakError(
                f"secret-shaped value detected at {path} (pattern=base64_blob)",
                field_path=path,
                pattern="base64_blob",
            )


def redact(value: Any, *, _path: str = "$") -> Any:
    """The SI-1 choke point every evidence record passes through.

    Recursively walks ``value`` -- a Pydantic model, dict, list, tuple, set,
    frozenset, or primitive -- checking every string it contains against the
    secret-shaped patterns above. Raises :class:`SecretLeakError` on the
    first hit and returns ``value`` unchanged otherwise: this function is a
    gate, not a sanitizer.
    """
    if isinstance(value, SecretMaterial):
        raise SecretLeakError(
            f"SecretMaterial reached the evidence boundary at {_path}", field_path=_path
        )
    if isinstance(value, str):
        _check_string(value, _path)
        return value
    if isinstance(value, bool | int | float | type(None) | datetime):
        return value
    if isinstance(value, AuthoritySet):
        for item in value.sorted:
            _check_string(item, f"{_path}[]")
        return value
    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            redact(getattr(value, name), _path=f"{_path}.{name}")
        return value
    if isinstance(value, Mapping):
        for key, item in value.items():
            _check_string(str(key), f"{_path}.<key>")
            redact(item, _path=f"{_path}.{key}")
        return value
    if isinstance(value, list | tuple):
        for index, item in enumerate(value):
            redact(item, _path=f"{_path}[{index}]")
        return value
    if isinstance(value, frozenset | set):
        for index, item in enumerate(sorted(value, key=str)):
            redact(item, _path=f"{_path}{{{index}}}")
        return value
    # Anything else (e.g. an enum) is treated as opaque and safe: it has no
    # free-text surface a secret could hide in.
    return value

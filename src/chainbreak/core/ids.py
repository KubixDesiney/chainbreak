"""Identifier types and generation.

Run IDs are ULIDs: lexicographically sortable by creation time, collision
resistant, URL-safe, and -- unlike UUIDv1 -- they encode no hostname or MAC
address. That last property matters because run IDs appear in published
evidence bundles (threat T-13).
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from typing import Annotated, Final, NewType

from pydantic import StringConstraints

# Crockford base32, excluding I, L, O, U to avoid transcription ambiguity.
_CROCKFORD: Final = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

CAPABILITY_ID_PATTERN: Final = r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_]*)+$"
SCENARIO_ID_PATTERN: Final = r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$"
IDENTITY_ID_PATTERN: Final = r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$"
NAMESPACE_PATTERN: Final = r"^cb-[0-9a-f]{8}$"

CapabilityId = Annotated[str, StringConstraints(pattern=CAPABILITY_ID_PATTERN, max_length=64)]
ScenarioId = Annotated[str, StringConstraints(pattern=SCENARIO_ID_PATTERN, max_length=96)]
IdentityId = Annotated[str, StringConstraints(pattern=IDENTITY_ID_PATTERN, max_length=64)]
Namespace = Annotated[str, StringConstraints(pattern=NAMESPACE_PATTERN)]
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]

RunId = NewType("RunId", str)
ObservationId = NewType("ObservationId", str)
EventId = NewType("EventId", str)
FindingId = NewType("FindingId", str)
CredentialId = NewType("CredentialId", str)
EdgeId = NewType("EdgeId", str)

_ULID_RE: Final = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def _encode_base32(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


_MAX_RANDOMNESS: Final = (1 << 80) - 1
_last_timestamp_ms: int = -1
_last_randomness: int = 0
_ulid_lock = threading.Lock()


def new_ulid() -> str:
    """Generate a *monotonic* ULID: 48-bit ms timestamp + 80 bits of randomness.

    Plain random ULIDs generated within the same millisecond do not sort
    lexicographically, which would break the "sortable by creation time"
    property the evidence layer relies on. Following the ULID specification's
    monotonic profile, randomness is incremented rather than redrawn when the
    timestamp has not advanced.
    """
    global _last_timestamp_ms, _last_randomness

    with _ulid_lock:
        timestamp_ms = int(time.time() * 1000)
        if timestamp_ms == _last_timestamp_ms:
            if _last_randomness >= _MAX_RANDOMNESS:  # pragma: no cover - 2^80 in one ms
                timestamp_ms += 1
                _last_randomness = int.from_bytes(os.urandom(10), "big") >> 1
            else:
                _last_randomness += 1
        elif timestamp_ms < _last_timestamp_ms:
            # Wall clock stepped backwards (NTP). Keep the sequence monotonic
            # rather than emitting an out-of-order identifier.
            timestamp_ms = _last_timestamp_ms
            _last_randomness += 1
        else:
            # Reserve the top bit so in-millisecond increments cannot overflow
            # into the timestamp field.
            _last_randomness = int.from_bytes(os.urandom(10), "big") >> 1
        _last_timestamp_ms = timestamp_ms
        randomness = _last_randomness

    return _encode_base32(timestamp_ms, 10) + _encode_base32(randomness, 16)


def is_ulid(value: str) -> bool:
    return bool(_ULID_RE.match(value))


def new_run_id() -> RunId:
    return RunId(new_ulid())


def new_observation_id() -> ObservationId:
    return ObservationId("obs_" + new_ulid())


def new_event_id() -> EventId:
    return EventId("ev_" + new_ulid())


def new_finding_id() -> FindingId:
    return FindingId("fnd_" + new_ulid())


def new_credential_id() -> CredentialId:
    return CredentialId("cred_" + new_ulid())


def run_salt(run_id: RunId) -> str:
    """Per-run salt for identifier hashing.

    Derived from the run ID, which is itself present in the bundle. This is a
    deliberate, documented trade-off (residual risk R-14): bundles disclose
    *equality relationships* between identifiers, not the identifiers
    themselves. An adversary who already knows a candidate ARN can confirm it;
    one who does not, learns nothing. Correlatable evidence requires this.
    """
    return f"chainbreak:{run_id}:"


def digest_ref(value: str, salt: str) -> str:
    """Salted digest of a provider reference (ARN, URL, resource name)."""
    return "sha256:" + hashlib.sha256((salt + value).encode()).hexdigest()


def fingerprint_json(canonical_json: str) -> str:
    """Fingerprint of an already-canonicalized JSON document."""
    return "sha256:" + hashlib.sha256(canonical_json.encode()).hexdigest()

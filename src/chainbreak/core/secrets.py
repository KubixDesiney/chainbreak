"""Secret material handling -- SI-1, layer 1.

The design principle: make it *impossible to accidentally* render a secret,
rather than *remembering not to*. ``SecretMaterial`` raises on every text
conversion path Python offers, so a stray f-string, a ``repr`` in a traceback, a
``json.dumps`` via Pydantic, or a naive log call all fail loudly instead of
leaking.

Access is via ``reveal()``, which is called in exactly two places in the
codebase (the AWS and fake session builders). A grep for ``.reveal()`` is
therefore a complete audit of secret access.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, Final

from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema

from chainbreak.core.errors import SecretSerializationError

_REDACTED: Final = "<REDACTED>"


class SecretMaterial:
    """An opaque wrapper around a credential string.

    Raises :class:`SecretSerializationError` on ``str``, ``repr``, ``format``,
    and any Pydantic serialization attempt.
    """

    __slots__ = ("_label", "_value")

    def __init__(self, value: str, label: str = "secret") -> None:
        if not isinstance(value, str):  # pragma: no cover - defensive
            raise TypeError("SecretMaterial requires a str")
        self._value = value
        self._label = label

    # -- every text conversion path is closed ---------------------------------

    def __str__(self) -> str:
        raise SecretSerializationError(
            f"Attempted to stringify secret material ({self._label}). "
            "Use .reveal() at an authorized call site, or .digest() for evidence.",
            label=self._label,
        )

    def __repr__(self) -> str:
        raise SecretSerializationError(
            f"Attempted to repr secret material ({self._label}).", label=self._label
        )

    def __format__(self, format_spec: str) -> str:
        raise SecretSerializationError(
            f"Attempted to format secret material ({self._label}).", label=self._label
        )

    def __bytes__(self) -> bytes:
        raise SecretSerializationError(
            f"Attempted to encode secret material ({self._label}).", label=self._label
        )

    def __reduce__(self) -> Any:
        raise SecretSerializationError(
            f"Attempted to pickle secret material ({self._label}).", label=self._label
        )

    def __copy__(self) -> Any:  # pragma: no cover - defensive
        raise SecretSerializationError(
            f"Attempted to copy secret material ({self._label}).", label=self._label
        )

    def __deepcopy__(self, memo: dict[int, Any]) -> Any:  # pragma: no cover - defensive
        raise SecretSerializationError(
            f"Attempted to deepcopy secret material ({self._label}).", label=self._label
        )

    # -- authorized access ----------------------------------------------------

    def reveal(self) -> str:
        """Return the underlying value.

        Authorized call sites only: ``providers/aws/session.py`` and
        ``providers/fake/session.py``. Every other use is a review failure.
        """
        return self._value

    def digest(self, salt: str = "") -> str:
        """Salted SHA-256 digest, safe for evidence.

        Used for correlation only: two observations produced by the same
        credential share a digest, without the bundle disclosing the credential.
        """
        return "sha256:" + hashlib.sha256((salt + self._value).encode()).hexdigest()

    def constant_time_equals(self, other: SecretMaterial) -> bool:
        return hmac.compare_digest(self._value, other._value)

    @property
    def label(self) -> str:
        return self._label

    @property
    def length(self) -> int:
        """Length is safe to expose and useful for diagnosing malformed credentials."""
        return len(self._value)

    # -- Pydantic integration -------------------------------------------------

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """Validate from a str; refuse to serialize."""

        def _validate(value: Any) -> SecretMaterial:
            if isinstance(value, SecretMaterial):
                return value
            if isinstance(value, str):
                return cls(value)
            raise TypeError("SecretMaterial expects a str")

        def _serialize(_value: SecretMaterial) -> str:
            raise SecretSerializationError(
                "Attempted to serialize a model containing SecretMaterial. "
                "Secrets must never reach an evidence bundle (EV-1)."
            )

        return core_schema.no_info_plain_validator_function(
            _validate,
            serialization=core_schema.plain_serializer_function_ser_schema(_serialize),
        )


class TemporaryCredential:
    """A provider credential triple. Never serialized; never written to disk.

    Held only inside a session context manager. ``metadata_digest`` is what
    reaches evidence.
    """

    __slots__ = ("_secret", "_token", "access_key_id", "credential_id")

    def __init__(
        self,
        access_key_id: str,
        secret_access_key: str,
        session_token: str,
        credential_id: str,
    ) -> None:
        # access_key_id is public information (it appears in provider logs), so
        # it is a plain str; the other two are secret material.
        self.access_key_id = access_key_id
        self._secret = SecretMaterial(secret_access_key, "secret_access_key")
        self._token = SecretMaterial(session_token, "session_token")
        self.credential_id = credential_id

    def __repr__(self) -> str:
        # Safe: discloses no secret component.
        return f"<TemporaryCredential {self.credential_id} akid={self.access_key_id[:4]}…>"

    @property
    def secret_access_key(self) -> SecretMaterial:
        return self._secret

    @property
    def session_token(self) -> SecretMaterial:
        return self._token

    def access_key_id_digest(self, salt: str) -> str:
        return "sha256:" + hashlib.sha256((salt + self.access_key_id).encode()).hexdigest()

    def scrub(self) -> None:
        """Best-effort removal of references on session exit.

        Python cannot guarantee memory scrubbing; this drops references so the
        objects become collectable. Recorded as residual risk R-2 in
        THREAT_MODEL.md rather than presented as a guarantee.
        """
        self._secret = SecretMaterial(_REDACTED, "scrubbed")
        self._token = SecretMaterial(_REDACTED, "scrubbed")

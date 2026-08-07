"""core/secrets.py -- SI-1 layer 1: secrets must be unrenderable, not just unrendered.

Not part of M1's own scope, but M1's coverage acceptance criterion
(``core/`` >= 95%, TESTING.md) is a hard bar on the whole package, and this
module -- the primary SI-1 enforcement point -- had no dedicated test file
before now.
"""

from __future__ import annotations

import pickle

import pytest
from pydantic import BaseModel, ConfigDict
from pydantic_core import PydanticSerializationError

from chainbreak.core.errors import SecretSerializationError
from chainbreak.core.secrets import SecretMaterial, TemporaryCredential

pytestmark = pytest.mark.unit


class TestSecretMaterialAccess:
    def test_reveal_returns_the_value(self):
        secret = SecretMaterial("super-secret-value")
        assert secret.reveal() == "super-secret-value"

    def test_length_is_exposed(self):
        secret = SecretMaterial("abcdef")
        assert secret.length == 6

    def test_label_is_exposed(self):
        secret = SecretMaterial("value", "custom-label")
        assert secret.label == "custom-label"

    def test_default_label(self):
        secret = SecretMaterial("value")
        assert secret.label == "secret"


class TestSecretMaterialDigest:
    def test_digest_format(self):
        secret = SecretMaterial("value")
        assert secret.digest().startswith("sha256:")

    def test_constant_time_equals_true_for_same_value(self):
        a = SecretMaterial("same-value")
        b = SecretMaterial("same-value")
        assert a.constant_time_equals(b) is True

    def test_constant_time_equals_false_for_different_values(self):
        a = SecretMaterial("value-one")
        b = SecretMaterial("value-two")
        assert a.constant_time_equals(b) is False


class TestSecretMaterialSerializationPathsAreClosed:
    def test_pickle_raises(self):
        secret = SecretMaterial("value")
        with pytest.raises(SecretSerializationError):
            pickle.dumps(secret)

    def test_pydantic_serialization_raises(self):
        class Holder(BaseModel):
            model_config = ConfigDict(arbitrary_types_allowed=True)
            secret: SecretMaterial

        holder = Holder(secret=SecretMaterial("value"))
        # pydantic-core wraps the serializer's own exception rather than
        # propagating it directly; the underlying SecretSerializationError is
        # still what fired, and its message survives in the wrapper's text.
        with pytest.raises(PydanticSerializationError, match="EV-1"):
            holder.model_dump()

    def test_pydantic_validates_from_str(self):
        class Holder(BaseModel):
            model_config = ConfigDict(arbitrary_types_allowed=True)
            secret: SecretMaterial

        holder = Holder(secret="raw-string-value")
        assert isinstance(holder.secret, SecretMaterial)
        assert holder.secret.reveal() == "raw-string-value"

    def test_pydantic_validates_from_existing_instance(self):
        class Holder(BaseModel):
            model_config = ConfigDict(arbitrary_types_allowed=True)
            secret: SecretMaterial

        original = SecretMaterial("value")
        holder = Holder(secret=original)
        assert holder.secret is original

    def test_pydantic_rejects_non_str_non_secret(self):
        class Holder(BaseModel):
            model_config = ConfigDict(arbitrary_types_allowed=True)
            secret: SecretMaterial

        with pytest.raises(Exception, match="SecretMaterial expects a str"):
            Holder(secret=12345)  # type: ignore[arg-type]


class TestTemporaryCredential:
    def _credential(self) -> TemporaryCredential:
        return TemporaryCredential(
            access_key_id="ASIAEXAMPLEEXAMPLE00",
            secret_access_key="super-secret-value",
            session_token="token-value",
            credential_id="cred_test",
        )

    def test_secret_access_key_is_secret_material(self):
        credential = self._credential()
        assert isinstance(credential.secret_access_key, SecretMaterial)
        assert credential.secret_access_key.reveal() == "super-secret-value"

    def test_session_token_is_secret_material(self):
        credential = self._credential()
        assert isinstance(credential.session_token, SecretMaterial)
        assert credential.session_token.reveal() == "token-value"

    def test_access_key_id_digest_format(self):
        credential = self._credential()
        assert credential.access_key_id_digest("salt").startswith("sha256:")

    def test_scrub_replaces_secret_and_token(self):
        credential = self._credential()
        credential.scrub()
        assert credential.secret_access_key.reveal() == "<REDACTED>"
        assert credential.session_token.reveal() == "<REDACTED>"

    def test_scrub_is_irreversible(self):
        """After scrub(), the original secret value is unrecoverable from the object."""
        credential = self._credential()
        credential.scrub()
        assert "super-secret-value" not in repr(credential)
        assert credential.secret_access_key.reveal() != "super-secret-value"

"""capabilities/preconditions.py: PreconditionRegistry.

F4: precondition declarations resolve to verifier callables. What a failed
precondition means for a probe matrix already in flight is the executor's
concern (M5+); this module only resolves and invokes.
"""

from __future__ import annotations

import pytest

from chainbreak.capabilities.preconditions import PreconditionRegistry
from chainbreak.core.errors import BindingValidationError
from chainbreak.core.models import IdentityRef

pytestmark = pytest.mark.unit


def _identity_ref() -> IdentityRef:
    from chainbreak.core.enums import Provider

    return IdentityRef(provider=Provider.FAKE, kind="role", value="fake-provisioning-identity")


class TestPreconditionRegistry:
    def test_register_and_resolve(self):
        registry = PreconditionRegistry()
        registry.register("objectstore.marker_present", lambda identity: True)
        verifier = registry.resolve("objectstore.marker_present")
        assert verifier(_identity_ref()) is True

    def test_duplicate_registration_rejected(self):
        registry = PreconditionRegistry()
        registry.register("objectstore.marker_present", lambda identity: True)
        with pytest.raises(BindingValidationError, match="duplicate"):
            registry.register("objectstore.marker_present", lambda identity: False)

    def test_resolve_missing_raises(self):
        registry = PreconditionRegistry()
        with pytest.raises(BindingValidationError, match="no verifier registered"):
            registry.resolve("objectstore.marker_present")

    def test_verify_calls_the_registered_verifier(self):
        registry = PreconditionRegistry()
        registry.register("always_true", lambda identity: True)
        registry.register("always_false", lambda identity: False)
        identity = _identity_ref()
        assert registry.verify("always_true", identity) is True
        assert registry.verify("always_false", identity) is False

    def test_verify_missing_raises(self):
        registry = PreconditionRegistry()
        with pytest.raises(BindingValidationError):
            registry.verify("missing", _identity_ref())

    def test_verify_all_returns_a_result_per_name(self):
        registry = PreconditionRegistry()
        registry.register("a", lambda identity: True)
        registry.register("b", lambda identity: False)
        results = registry.verify_all(("a", "b"), _identity_ref())
        assert results == {"a": True, "b": False}

    def test_verifier_receives_the_provisioning_identity(self):
        registry = PreconditionRegistry()
        received = []
        registry.register("records_identity", lambda identity: received.append(identity) or True)
        identity = _identity_ref()
        registry.verify("records_identity", identity)
        assert received == [identity]

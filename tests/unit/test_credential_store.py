"""``execution/credential_store.py`` (M13): both of ``resolve``'s failure
paths -- easiest to exercise directly rather than through a full run.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from chainbreak.core.enums import DelegationMechanism
from chainbreak.core.errors import ExecutionError
from chainbreak.core.models import CredentialRecord
from chainbreak.execution.credential_store import CredentialStore

pytestmark = pytest.mark.unit


class TestResolve:
    def test_unknown_phase_raises(self) -> None:
        store = CredentialStore()
        store.record("after-delegation", "agent-c", None)
        with pytest.raises(ExecutionError, match="no credential was ever recorded") as excinfo:
            store.resolve("phase:ghost-phase", "agent-c")
        assert excinfo.value.context["identity_id"] == "agent-c"

    def test_phase_ran_but_recorded_no_credential_for_a_root_identity_raises(self) -> None:
        store = CredentialStore()
        store.record("baseline", "principal", None)  # a root: no credential to pin
        with pytest.raises(ExecutionError, match="recorded no credential"):
            store.resolve("phase:baseline", "principal")

    def test_resolves_the_recorded_credential(self) -> None:
        credential = CredentialRecord(
            credential_id="cred_1",
            identity_id="agent-c",
            mechanism=DelegationMechanism.ROLE_CHAIN,
            issued_at=datetime(2024, 1, 1, tzinfo=UTC),
            expires_at=datetime(2024, 1, 1, 1, tzinfo=UTC),
            requested_duration_s=3600,
            granted_duration_s=3600,
            session_name_hash="sha256:" + "a" * 64,
            access_key_id_hash="sha256:" + "b" * 64,
        )
        store = CredentialStore()
        store.record("after-delegation", "agent-c", credential)
        assert store.resolve("phase:after-delegation", "agent-c") is credential

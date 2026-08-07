"""M05-fake-provider.md acceptance criterion 3: same seed => identical
evidence, verified by hashing two runs' observation streams.

F6 requires byte-for-byte reproducibility "on any machine", which is why the
fake never reads the system clock or an unseeded RNG anywhere in its call
path (session.py's credential/access-key generation, consistency.py's
jitter/oscillation draws, and adapter.py's fault injection are all seeded
from the single constructor ``seed``). This test runs a realistic multi-step
sequence -- delegation through a chain, several probes, a policy mutation,
more probes after it -- against two independently constructed adapters with
the same seed, and hashes the full observation stream each produced.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from chainbreak.core.canonical import dumps
from chainbreak.core.enums import DelegationMechanism, MutationKind
from chainbreak.core.ids import fingerprint_json
from chainbreak.core.models import AuthoritySet, PolicyMutation
from chainbreak.providers.base.types import DelegationRequest, ProbeRequest
from chainbreak.providers.fake.adapter import FakeProviderAdapter

pytestmark = pytest.mark.unit

_CAPABILITIES = (
    "objectstore.read",
    "objectstore.write",
    "objectstore.list",
    "keyvalue.read",
    "keyvalue.write",
    "function.invoke",
    "queue.send",
    "queue.receive",
    "identity.whoami",
)


def _run_sequence(seed: int) -> tuple[dict, ...]:
    adapter = FakeProviderAdapter(seed=seed, namespace="cb-abcd1234")
    principal = adapter.register_identity("principal", allow=AuthoritySet.of("identity.delegate"))
    adapter.register_identity("agent-a", allow=AuthoritySet.from_iterable(_CAPABILITIES))
    delegation = adapter.delegate(
        DelegationRequest(
            source_identity=principal,
            target_identity_id="agent-a",
            mechanism=DelegationMechanism.SESSION_POLICY_SCOPED,
            requested_duration_s=1800,
            intended_capabilities=AuthoritySet.from_iterable(_CAPABILITIES),
        )
    )

    stream: list[dict] = [
        {"kind": "delegation", "record": delegation.record},
        {"kind": "credential_digest", "digest": delegation.credential.secret_access_key.digest()},
    ]

    for capability_id in _CAPABILITIES:
        binding = adapter.resolve_capability(capability_id)
        result = adapter.probe(
            ProbeRequest(
                identity_ref=delegation.identity_ref,
                capability_id=capability_id,
                binding=binding,
                namespace="cb-abcd1234",
            )
        )
        stream.append({"kind": "probe", "capability_id": capability_id, "result": result})
        adapter.advance_clock(10)

    receipt = adapter.apply_policy_mutation(
        PolicyMutation(
            mutation_id="m1",
            kind=MutationKind.ATTACH_INLINE_DENY,
            target_identity="agent-a",
            denies_capabilities=AuthoritySet.of("objectstore.write"),
        )
    )
    stream.append({"kind": "mutation_receipt", "receipt": receipt})

    for capability_id in _CAPABILITIES:
        binding = adapter.resolve_capability(capability_id)
        result = adapter.probe(
            ProbeRequest(
                identity_ref=delegation.identity_ref,
                capability_id=capability_id,
                binding=binding,
                namespace="cb-abcd1234",
            )
        )
        stream.append(
            {"kind": "probe_after_mutation", "capability_id": capability_id, "result": result}
        )
        adapter.advance_clock(10)

    snapshot = adapter.snapshot_policy_state(delegation.identity_ref)
    stream.append({"kind": "snapshot", "snapshot": snapshot})

    return tuple(stream)


class TestDeterminism:
    def test_same_seed_produces_an_identical_hashed_observation_stream(self):
        stream_a = _run_sequence(seed=1729)
        stream_b = _run_sequence(seed=1729)

        hash_a = fingerprint_json(dumps(stream_a))
        hash_b = fingerprint_json(dumps(stream_b))
        assert hash_a == hash_b

    def test_different_seeds_produce_a_different_hashed_observation_stream(self):
        # Not required by F6, but proves the hash is actually sensitive to
        # the seed rather than trivially constant.
        stream_a = _run_sequence(seed=1729)
        stream_c = _run_sequence(seed=1730)

        hash_a = fingerprint_json(dumps(stream_a))
        hash_c = fingerprint_json(dumps(stream_c))
        assert hash_a != hash_c

    def test_stream_is_stable_across_three_independent_runs(self):
        hashes = {fingerprint_json(dumps(_run_sequence(seed=42))) for _ in range(3)}
        assert len(hashes) == 1

    def test_stable_across_two_separate_processes(self):
        """Two independent interpreters, not two in-process calls -- the M1
        risk this repository has already had to rule out once for
        compiled_hash (test_scenario_compiler.py): dict ordering, float
        formatting, or PYTHONHASHSEED-dependent frozenset iteration could in
        principle make a hash "reproducible" only within one process."""
        repo_root = Path(__file__).resolve().parents[2]
        code = (
            "from chainbreak.core.canonical import dumps;"
            "from chainbreak.core.ids import fingerprint_json;"
            "from tests.unit.test_fake_determinism import _run_sequence;"
            "print(fingerprint_json(dumps(_run_sequence(seed=1729))))"
        )
        results = {
            subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                check=True,
                cwd=repo_root,
            ).stdout
            for _ in range(2)
        }
        assert len(results) == 1
        assert results.pop().strip().startswith("sha256:")

"""M05-fake-provider.md acceptance criterion 4: all three fake profiles run
all 12 scenarios without crashing.

Written at M5, when there was no ``execution/`` orchestrator yet -- that was
M10's job (`execution/orchestrator.py`, `execution/matrix.py`,
`execution/delegation.py`, now built; see
``tests/integration/test_scope_attenuation.py`` for the real orchestrator
exercised the same way). At the time this was written, this milestone's own
verification command (``chainbreak run scenarios/scope-attenuation/basic.yaml
--provider fake --seed 1729``) was unrunnable for the same reason M3's
nc-scope-expansion negative control turned out to be premature: it was
written as if a later milestone had already landed. What this test verified
instead was the substance of the acceptance criterion at the layer that
actually existed at M5 -- every real compiled scenario's authorization graph
(identities, edges, capability sets) can be walked end-to-end through the
fake adapter's ``delegate``/``probe`` calls, for every profile, without an
exception. It is kept as a broader, faster crash-only sweep across the whole
corpus (M10's own tests are narrower and scope-attenuation-specific) rather
than superseded outright.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreak.capabilities.loader import load_catalog
from chainbreak.providers.base.types import DelegationRequest, ProbeRequest
from chainbreak.providers.fake.profiles import (
    deterministic_profile,
    eventual_profile,
    hostile_profile,
)
from chainbreak.scenarios.compiler import compile_scenario
from chainbreak.scenarios.safety import load_scenario_yaml
from chainbreak.scenarios.schema import ScenarioDocument

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATHS = sorted((REPO_ROOT / "scenarios").rglob("*.yaml"))

PROFILES = {
    "deterministic": deterministic_profile,
    "eventual": eventual_profile,
    "hostile": hostile_profile,
}


def _walk(profile_name: str, scenario_path: Path, synthetic_aws_registry) -> None:
    catalog = load_catalog()
    document = ScenarioDocument(**load_scenario_yaml(scenario_path))
    compiled = compile_scenario(document, catalog=catalog, registry=synthetic_aws_registry)

    adapter = PROFILES[profile_name](seed=1)
    refs = {}
    nodes_by_id = {node.identity_id: node for node in compiled.graph.nodes}

    for node in compiled.graph.nodes:
        if node.is_root:
            refs[node.identity_id] = adapter.register_identity(
                node.identity_id, allow=node.expected_authority.capabilities
            )

    # Edges are already in hop order in a compiled graph (G-3/monotone
    # construction walks root outward); delegate along each in that order.
    for edge in compiled.graph.edges:
        source_ref = refs[edge.source_id]
        result = adapter.delegate(
            DelegationRequest(
                source_identity=source_ref,
                target_identity_id=edge.target_id,
                mechanism=edge.mechanism,
                requested_duration_s=edge.credential_lifetime_s,
                intended_capabilities=edge.intended_capabilities,
            )
        )
        refs[edge.target_id] = result.identity_ref
        # Register the target's own identity-policy grant from the compiled
        # graph's expected authority, if not already present (a target that
        # is also a root elsewhere would already be registered above).
        target_node = nodes_by_id[edge.target_id]
        if not adapter.engine.is_registered(edge.target_id):
            adapter.register_identity(
                edge.target_id, allow=target_node.expected_authority.capabilities
            )

    for matrix in compiled.probe_matrices:
        for identity_id in matrix.identities:
            if identity_id not in refs:
                continue
            for capability_id in matrix.capabilities:
                binding = adapter.resolve_capability(capability_id)
                adapter.probe(
                    ProbeRequest(
                        identity_ref=refs[identity_id],
                        capability_id=capability_id,
                        binding=binding,
                        namespace=adapter.namespace,
                    )
                )
        adapter.advance_clock(10)


class TestAllScenariosRunAgainstAllProfilesWithoutCrashing:
    @pytest.mark.parametrize("scenario_path", SCENARIO_PATHS, ids=lambda p: p.stem)
    @pytest.mark.parametrize("profile_name", list(PROFILES))
    def test_walks_without_raising(
        self, profile_name: str, scenario_path: Path, synthetic_aws_registry
    ):
        _walk(profile_name, scenario_path, synthetic_aws_registry)

    def test_exactly_twenty_four_scenarios_were_discovered(self):
        # Guards the parametrization itself: if the corpus count ever
        # changes, this test (not a silent drop to fewer parametrized cases)
        # is what should fail. 12 at M5; M11 added the four missing
        # delegation-drift depths (two/three/five/six-hop -- four-hop
        # already existed) plus role-chain-five-hop.yaml, a test-support
        # fixture for identity-policy-level defect injection (see its own
        # docstring for why the depth-sweep scenarios themselves can't be
        # reused for that); M12 added the three remaining revocation
        # mechanism scenarios (remove-policy, revoke-older-sessions,
        # delete-session-scope -- inline-deny and trust-policy-null-condition
        # already existed); M13 added three stale-authority scenarios
        # (short-defer, long-defer, post-expiry -- deferred-execution.yaml
        # already existed, a "written as if the milestone had already
        # landed" M0 scaffold in the same vein as M3/M5/M10's own instances
        # of the pattern, which M13's own scenario/schema/compiler changes
        # made runnable for the first time without needing to be rewritten)
        # for 23; M14 found silent-narrowing/two-step-pipeline.yaml was
        # *also* one such M0 scaffold -- already exactly the family's
        # documented "honest worker, insufficient authority" case
        # (EXPERIMENT_PROTOCOL.md section 5, steps 1-6) -- and added one
        # more, two-step-pipeline-full-authority.yaml, for the family's
        # still-missing F7 positive control (full authority, same task),
        # for 24.
        assert len(SCENARIO_PATHS) == 24

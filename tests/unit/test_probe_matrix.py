"""scenarios/compiler.py: probe matrix construction (F3).

Probe universe correctness is the point of this file: ``scenario`` (the
default) must include capabilities a node is *not* expected to hold, since
testing only what is expected cannot detect authority expansion.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreak.capabilities.loader import load_catalog
from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.enums import PhaseKind
from chainbreak.scenarios.compiler import compile_scenario
from chainbreak.scenarios.safety import load_scenario_yaml
from chainbreak.scenarios.schema import ScenarioDocument

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
FOUR_HOP = REPO_ROOT / "scenarios" / "delegation-drift" / "four-hop.yaml"
_WHOAMI = "identity.whoami"


def _document(path: Path) -> ScenarioDocument:
    return ScenarioDocument(**load_scenario_yaml(path))


class TestWhoamiInEveryUniverse:
    def test_whoami_present_regardless_of_probe_universe(
        self, synthetic_aws_registry: BindingRegistry
    ):
        catalog = load_catalog()
        for universe in ("declared", "scenario", "catalog"):
            raw = load_scenario_yaml(FOUR_HOP)
            raw["spec"]["execution"]["probe_universe"] = universe
            document = ScenarioDocument(**raw)
            compiled = compile_scenario(document, catalog=catalog, registry=synthetic_aws_registry)
            for matrix in compiled.probe_matrices:
                assert _WHOAMI in matrix.capabilities, universe


class TestScenarioUniverseIncludesUnexpectedCapabilities:
    """The whole point of the default universe: it must include capabilities
    a node is NOT expected to hold, or authority expansion is undetectable."""

    def test_agent_c_matrix_includes_capabilities_it_should_not_hold(
        self, synthetic_aws_registry: BindingRegistry
    ):
        catalog = load_catalog()
        document = _document(FOUR_HOP)  # default probe_universe: scenario
        compiled = compile_scenario(document, catalog=catalog, registry=synthetic_aws_registry)

        after_delegation = next(
            m for m in compiled.probe_matrices if m.phase_name == "after-delegation"
        )
        agent_c = compiled.graph.node("agent-c")
        # agent-c is only expected to hold objectstore.read (+whoami, +delegate),
        # but the scenario universe includes everything named anywhere --
        # e.g. objectstore.write, which principal declared and agent-c must not.
        assert "objectstore.write" not in agent_c.expected_authority.capabilities
        assert "objectstore.write" in after_delegation.capabilities


class TestDeclaredUniverseIsPerIdentity:
    def test_declared_universe_excludes_what_no_target_ever_holds(
        self, synthetic_aws_registry: BindingRegistry
    ):
        catalog = load_catalog()
        raw = load_scenario_yaml(FOUR_HOP)
        raw["spec"]["execution"]["probe_universe"] = "declared"
        document = ScenarioDocument(**raw)
        compiled = compile_scenario(document, catalog=catalog, registry=synthetic_aws_registry)

        after_delegation = next(
            m for m in compiled.probe_matrices if m.phase_name == "after-delegation"
        )
        # Under "declared", the matrix is the union of each *target's own*
        # expected authority -- keyvalue.write is principal's alone (hop-1
        # never intends it), so none of agent-a..d ever hold it, and it must
        # not appear here even though the "scenario" universe would include
        # it (principal names it, and principal isn't a target of this phase).
        assert "keyvalue.write" not in after_delegation.capabilities
        # objectstore.write IS agent-a's own expected authority, and agent-a
        # is one of this phase's targets, so the union must include it.
        assert "objectstore.write" in after_delegation.capabilities


class TestCatalogUniverseIsEverything:
    def test_catalog_universe_includes_every_catalog_capability(
        self, synthetic_aws_registry: BindingRegistry
    ):
        catalog = load_catalog()
        raw = load_scenario_yaml(FOUR_HOP)
        raw["spec"]["execution"]["probe_universe"] = "catalog"
        document = ScenarioDocument(**raw)
        compiled = compile_scenario(document, catalog=catalog, registry=synthetic_aws_registry)

        for matrix in compiled.probe_matrices:
            assert set(matrix.capabilities) == set(catalog.ids())


class TestOneMatrixPerProbeOrDeferredPhase:
    def test_matrix_count_matches_probe_and_deferred_phases(
        self, synthetic_aws_registry: BindingRegistry
    ):
        catalog = load_catalog()
        document = _document(FOUR_HOP)
        compiled = compile_scenario(document, catalog=catalog, registry=synthetic_aws_registry)

        expected = sum(
            1
            for phase in document.spec.phases
            if phase.kind in (PhaseKind.PROBE, PhaseKind.DEFERRED_EXECUTION)
        )
        assert len(compiled.probe_matrices) == expected

    def test_deferred_execution_phase_gets_a_matrix(self, synthetic_aws_registry: BindingRegistry):
        catalog = load_catalog()
        document = _document(
            REPO_ROOT / "scenarios" / "stale-authority" / "deferred-execution.yaml"
        )
        compiled = compile_scenario(document, catalog=catalog, registry=synthetic_aws_registry)
        deferred_names = {
            phase.name for phase in document.spec.phases if phase.kind.value == "DEFERRED_EXECUTION"
        }
        matrix_names = {m.phase_name for m in compiled.probe_matrices}
        assert deferred_names <= matrix_names


class TestMatrixTrialsMatchExecutionConfig:
    def test_trials_from_execution_block(self, synthetic_aws_registry: BindingRegistry):
        catalog = load_catalog()
        raw = load_scenario_yaml(FOUR_HOP)
        raw["spec"]["execution"]["trials"] = 5
        document = ScenarioDocument(**raw)
        compiled = compile_scenario(document, catalog=catalog, registry=synthetic_aws_registry)
        assert all(m.trials == 5 for m in compiled.probe_matrices)

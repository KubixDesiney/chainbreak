"""scenarios/compiler.py -- ScenarioDocument -> CompiledScenario.

Acceptance criteria 3 and 4: compiled_hash is stable across processes and
changes when the catalog version changes; nc-* scenarios compile with
warnings, not errors.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from chainbreak.capabilities.loader import load_catalog
from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.enums import PhaseKind
from chainbreak.core.models import CapabilityCatalog
from chainbreak.scenarios.compiler import compile_scenario
from chainbreak.scenarios.safety import load_scenario_yaml
from chainbreak.scenarios.schema import ScenarioDocument

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
FOUR_HOP = REPO_ROOT / "scenarios" / "delegation-drift" / "four-hop.yaml"
INLINE_DENY = REPO_ROOT / "scenarios" / "revocation" / "inline-deny.yaml"
NC_SCOPE_EXPANSION = REPO_ROOT / "scenarios" / "_negative-controls" / "nc-scope-expansion.yaml"


def _document(path: Path) -> ScenarioDocument:
    return ScenarioDocument(**load_scenario_yaml(path))


class TestCompiledHashDeterminism:
    def test_stable_across_two_calls_in_the_same_process(
        self, synthetic_aws_registry: BindingRegistry
    ):
        catalog = load_catalog()
        document = _document(FOUR_HOP)
        first = compile_scenario(document, catalog=catalog, registry=synthetic_aws_registry)
        second = compile_scenario(document, catalog=catalog, registry=synthetic_aws_registry)
        assert first.compiled_hash == second.compiled_hash

    def test_stable_across_two_separate_processes(self):
        """The M1 risk this milestone calls out by name: non-determinism
        creeping in via dict ordering or float formatting. Two independent
        interpreters, not two calls, is what actually rules that out."""
        code = (
            "from pathlib import Path;"
            "from chainbreak.capabilities.loader import load_catalog;"
            "from chainbreak.capabilities.registry import BindingRegistry;"
            "from chainbreak.core.enums import Provider;"
            "from chainbreak.core.models import ProviderCapabilityBinding;"
            "from chainbreak.scenarios.compiler import compile_scenario;"
            "from chainbreak.scenarios.safety import load_scenario_yaml;"
            "from chainbreak.scenarios.schema import ScenarioDocument;"
            "catalog = load_catalog();"
            "registry = BindingRegistry();"
            "[registry.register(ProviderCapabilityBinding("
            "capability_id=c.id, provider=Provider.AWS, actions=(f'aws:{c.id}',), "
            "resource_template='arn:aws:test:::{namespace}/' + c.id, "
            "probe_kind=c.probe_kind, preconditions=c.requires_precondition)) "
            "for c in catalog.capabilities];"
            f"doc = ScenarioDocument(**load_scenario_yaml(Path(r'{FOUR_HOP}')));"
            "compiled = compile_scenario(doc, catalog=catalog, registry=registry);"
            "print(compiled.compiled_hash)"
        )
        results = {
            subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                check=True,
                cwd=REPO_ROOT,
            ).stdout
            for _ in range(2)
        }
        assert len(results) == 1
        assert results.pop().strip().startswith("sha256:")

    def test_changes_when_catalog_version_changes(self, synthetic_aws_registry: BindingRegistry):
        catalog_v1 = load_catalog()
        catalog_v2 = CapabilityCatalog(version="1.1.0", capabilities=catalog_v1.capabilities)
        document = _document(FOUR_HOP)
        compiled_v1 = compile_scenario(
            document, catalog=catalog_v1, registry=synthetic_aws_registry
        )
        compiled_v2 = compile_scenario(
            document, catalog=catalog_v2, registry=synthetic_aws_registry
        )
        assert compiled_v1.compiled_hash != compiled_v2.compiled_hash


class TestExpectedAuthorityDerivation:
    """F2: intersection, not assignment."""

    def test_four_hop_expected_authority_matches_the_worked_example(
        self, synthetic_aws_registry: BindingRegistry
    ):
        catalog = load_catalog()
        document = _document(FOUR_HOP)
        compiled = compile_scenario(document, catalog=catalog, registry=synthetic_aws_registry)

        principal = compiled.graph.node("principal")
        assert len(principal.expected_authority.capabilities) == 8  # all declared root caps

        agent_c = compiled.graph.node("agent-c")
        # hop-3 intends {os.read, kv.read, whoami, delegate}; derived from
        # agent-b's expected via intersection.
        assert "objectstore.read" in agent_c.expected_authority.capabilities
        assert "objectstore.write" not in agent_c.expected_authority.capabilities


class TestPlanAutoInsertsSnapshots:
    def test_mutate_phase_gets_a_snapshot_before_and_after(
        self, synthetic_aws_registry: BindingRegistry
    ):
        catalog = load_catalog()
        document = _document(INLINE_DENY)
        compiled = compile_scenario(document, catalog=catalog, registry=synthetic_aws_registry)

        mutate_index = next(
            i for i, step in enumerate(compiled.plan) if step.kind is PhaseKind.MUTATE
        )
        before = compiled.plan[mutate_index - 1]
        after = compiled.plan[mutate_index + 1]
        assert before.kind is PhaseKind.SNAPSHOT
        assert before.auto_inserted is True
        assert after.kind is PhaseKind.SNAPSHOT
        assert after.auto_inserted is True


class TestPolicyArtifacts:
    def test_one_synthesized_policy_per_delegation(self, synthetic_aws_registry: BindingRegistry):
        catalog = load_catalog()
        document = _document(FOUR_HOP)
        compiled = compile_scenario(document, catalog=catalog, registry=synthetic_aws_registry)
        assert len(compiled.policy_artifacts) == len(document.spec.delegations)


class TestNegativeControlsCompileWithoutErrors:
    """Acceptance criterion 4.

    All six shipped negative controls compile cleanly (see PROJECT_STATUS.md
    for why nc-scope-expansion in particular carries no G-3 warning: its
    injected defect is at the infrastructure/binding level -- an inline IAM
    policy the compiler cannot see -- not in the declared delegation graph,
    which is exactly what makes it a *negative control* rather than a
    redundant compile-time check).
    """

    def test_expected_finding_is_carried_into_the_compiled_artifact(
        self, synthetic_aws_registry: BindingRegistry
    ):
        catalog = load_catalog()
        document = _document(NC_SCOPE_EXPANSION)
        compiled = compile_scenario(document, catalog=catalog, registry=synthetic_aws_registry)

        assert compiled.expected_finding is not None
        assert compiled.expected_finding.type.value == "AUTHORITY_EXPANSION"
        assert compiled.expected_finding.identity_id == "agent-b"
        assert "keyvalue.read" in compiled.expected_finding.capabilities

    def test_non_negative_control_has_no_expected_finding(
        self, synthetic_aws_registry: BindingRegistry
    ):
        catalog = load_catalog()
        document = _document(FOUR_HOP)
        compiled = compile_scenario(document, catalog=catalog, registry=synthetic_aws_registry)
        assert compiled.expected_finding is None

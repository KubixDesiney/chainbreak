"""scenarios/loader.py: the five-stage validation pipeline.

Acceptance criteria 1 and 2: all 12 shipped scenarios compile; each invalid
fixture in tests/fixtures/scenarios/ yields its documented exit code.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreak.capabilities.loader import load_catalog
from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.enums import ProbeKind, Sensitivity
from chainbreak.core.errors import ScenarioSemanticError
from chainbreak.core.models import Capability, CapabilityCatalog
from chainbreak.scenarios.compiler import compile_scenario
from chainbreak.scenarios.loader import (
    EXIT_BINDING,
    EXIT_SAFETY,
    EXIT_SEMANTIC,
    EXIT_SYNTAX_STRUCTURAL,
    EXIT_VALID,
    load_and_compile,
    validate_scenario,
)
from chainbreak.scenarios.schema import ScenarioDocument

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "scenarios"
SHIPPED_SCENARIOS = sorted((REPO_ROOT / "scenarios").rglob("*.yaml"))


class TestAllShippedScenariosCompile:
    """Acceptance criterion 1."""

    def test_corpus_is_not_empty(self):
        assert len(SHIPPED_SCENARIOS) >= 12

    @pytest.mark.parametrize("path", SHIPPED_SCENARIOS, ids=lambda p: p.stem)
    def test_scenario_compiles(self, path: Path, synthetic_aws_registry: BindingRegistry):
        result = validate_scenario(path, registry=synthetic_aws_registry)
        assert result.exit_code == EXIT_VALID, f"{path.name}: {result.errors}"
        assert result.compiled is not None


class TestInvalidFixturesYieldTheirDocumentedExitCode:
    """Acceptance criterion 2."""

    def test_structural_fixture_exits_2(self):
        result = validate_scenario(FIXTURES / "invalid_structural.yaml")
        assert result.exit_code == EXIT_SYNTAX_STRUCTURAL
        assert result.compiled is None
        assert result.errors

    def test_semantic_fixture_exits_3_naming_both_values(
        self, synthetic_aws_registry: BindingRegistry
    ):
        result = validate_scenario(
            FIXTURES / "invalid_semantic.yaml", registry=synthetic_aws_registry
        )
        assert result.exit_code == EXIT_SEMANTIC
        assert result.compiled is None
        message = " ".join(result.errors)
        # F2: the error must name both the declared and derived values.
        assert "objectstore.read" in message
        assert "keyvalue.read" in message

    def test_binding_fixture_exits_4_with_empty_registry(self):
        result = validate_scenario(FIXTURES / "invalid_binding.yaml")
        assert result.exit_code == EXIT_BINDING
        assert result.compiled is None
        assert "objectstore.read" in " ".join(result.errors)

    def test_safety_fixture_exits_5_against_a_dangerous_catalog(self):
        dangerous_catalog = CapabilityCatalog(
            version="1.0.0",
            capabilities=(
                Capability(
                    id="test.dangerous",
                    title="dangerous",
                    description="fixture capability marked DANGEROUS",
                    probe_kind=ProbeKind.READ_MARKER,
                    sensitivity=Sensitivity.DANGEROUS,
                ),
            ),
        )
        result = validate_scenario(
            FIXTURES / "invalid_safety_dangerous.yaml", catalog=dangerous_catalog
        )
        assert result.exit_code == EXIT_SAFETY
        assert result.compiled is None


class TestUnreachedIdentity:
    """A declared identity that no delegation ever targets is a compiler
    bug the schema-level referential-integrity checks do not catch (they
    only verify delegations reference *known* identities, not that every
    identity is *reached*)."""

    def test_orphaned_identity_exits_3(self, synthetic_aws_registry: BindingRegistry):
        raw = {
            "apiVersion": "chainbreak.dev/v1alpha1",
            "kind": "Scenario",
            "metadata": {
                "id": "orphan-test",
                "version": "1.0.0",
                "family": "scope-attenuation",
                "title": "Orphaned identity fixture for exit-3 coverage",
                "description": "agent-b is declared but never delegated to from the root.",
                "authors": ["operator"],
            },
            "spec": {
                "provider": "aws",
                "identities": [
                    {
                        "id": "principal",
                        "role": "root",
                        "provider_binding": {"terraform_output": "principal_role_arn"},
                        "capabilities": ["objectstore.read"],
                    },
                    {
                        "id": "agent-b",
                        "role": "agent",
                        "provider_binding": {"terraform_output": "agent_b_role_arn"},
                    },
                ],
                "phases": [{"name": "baseline", "kind": "PROBE", "targets": ["principal"]}],
            },
        }
        document = ScenarioDocument(**raw)
        catalog = load_catalog()

        with pytest.raises(ScenarioSemanticError, match="never reached"):
            compile_scenario(document, catalog=catalog, registry=synthetic_aws_registry)


class TestLoadAndCompile:
    def test_raises_on_failure_naming_the_exit_code(self):
        with pytest.raises(Exception, match="exit 2"):
            load_and_compile(FIXTURES / "invalid_structural.yaml")

    def test_returns_compiled_scenario_on_success(self, synthetic_aws_registry: BindingRegistry):
        compiled = load_and_compile(
            REPO_ROOT / "scenarios" / "delegation-drift" / "four-hop.yaml",
            registry=synthetic_aws_registry,
        )
        assert compiled.scenario_id == "delegation-drift-four-hop"

    def test_accepts_a_string_path(self, synthetic_aws_registry: BindingRegistry):
        compiled = load_and_compile(
            str(REPO_ROOT / "scenarios" / "delegation-drift" / "four-hop.yaml"),
            registry=synthetic_aws_registry,
        )
        assert compiled is not None

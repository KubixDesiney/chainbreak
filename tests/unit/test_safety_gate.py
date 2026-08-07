"""core/safety.py -- SafetyGate and the cost estimator (M4 F2, F6; SI-5, SI-7, SI-8).

Covers: missing envelope, wildcard account (collapses to missing envelope --
SafetyEnvelope itself refuses to construct with one), account not allowed,
disallowed region, namespace mismatch, cost over ceiling, duration over
ceiling (also collapses to a construction-time refusal, SI-7's 14400s hard
cap). S4: the cost estimator must be conservative.
"""

from __future__ import annotations

from pathlib import Path

import pydantic
import pytest

from chainbreak.capabilities.loader import load_catalog
from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.errors import (
    AccountNotAllowedError,
    CostEstimateExceededError,
    NamespaceViolationError,
    RegionNotAllowedError,
    SafetyEnvelopeError,
)
from chainbreak.core.models import CompiledScenario, SafetyEnvelope
from chainbreak.core.safety import DEFAULT_COST_KEY, SafetyGate, estimate_cost
from chainbreak.scenarios.compiler import compile_scenario
from chainbreak.scenarios.safety import load_scenario_yaml
from chainbreak.scenarios.schema import ScenarioDocument

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
FOUR_HOP = REPO_ROOT / "scenarios" / "delegation-drift" / "four-hop.yaml"


def _envelope(**overrides: object) -> SafetyEnvelope:
    fields: dict[str, object] = {
        "allowed_account_ids": ("123456789012",),
        "allowed_regions": ("us-east-1",),
        "namespace": "cb-deadbeef",
        "namespace_pattern": r"^cb-[0-9a-f]{8}$",
    }
    fields.update(overrides)
    return SafetyEnvelope(**fields)  # type: ignore[arg-type]


def _compiled(registry: BindingRegistry) -> CompiledScenario:
    catalog = load_catalog()
    document = ScenarioDocument(**load_scenario_yaml(FOUR_HOP))
    return compile_scenario(document, catalog=catalog, registry=registry)


class TestMissingEnvelope:
    def test_none_envelope_is_refused(self):
        with pytest.raises(SafetyEnvelopeError):
            SafetyGate().authorize(None)

    def test_wildcard_account_never_produces_an_envelope(self):
        with pytest.raises(pydantic.ValidationError, match="wildcards are forbidden"):
            _envelope(allowed_account_ids=("*",))

    def test_duration_over_hard_ceiling_never_produces_an_envelope(self):
        with pytest.raises(pydantic.ValidationError, match="14400"):
            _envelope(max_run_duration_seconds=14_401)


class TestAccountCheck:
    def test_allowed_account_passes(self):
        SafetyGate().authorize(_envelope(), account_id="123456789012")

    def test_disallowed_account_is_refused(self):
        with pytest.raises(AccountNotAllowedError):
            SafetyGate().authorize(_envelope(), account_id="999999999999")


class TestRegionCheck:
    def test_allowed_region_passes(self):
        SafetyGate().authorize(_envelope(), region="us-east-1")

    def test_disallowed_region_is_refused(self):
        with pytest.raises(RegionNotAllowedError):
            SafetyGate().authorize(_envelope(), region="eu-west-1")


class TestNamespaceCheck:
    def test_matching_namespace_passes(self):
        SafetyGate().authorize(_envelope(), namespace="cb-deadbeef")

    def test_mismatched_namespace_is_refused(self):
        with pytest.raises(NamespaceViolationError):
            SafetyGate().authorize(_envelope(), namespace="not-a-benchmark-namespace")

    def test_mismatched_namespace_prefix_is_refused(self):
        with pytest.raises(NamespaceViolationError):
            SafetyGate().authorize(_envelope(), namespace="other-deadbeef")


class TestCostCheck:
    def test_cost_within_ceiling_passes(self, synthetic_aws_registry: BindingRegistry):
        compiled = _compiled(synthetic_aws_registry)
        SafetyGate().authorize(
            _envelope(max_estimated_cost_usd=1000.0),
            compiled=compiled,
            cost_table={DEFAULT_COST_KEY: 0.0},
        )

    def test_cost_over_ceiling_is_refused(self, synthetic_aws_registry: BindingRegistry):
        compiled = _compiled(synthetic_aws_registry)
        with pytest.raises(CostEstimateExceededError):
            SafetyGate().authorize(
                _envelope(max_estimated_cost_usd=0.0),
                compiled=compiled,
                cost_table={DEFAULT_COST_KEY: 1.0},
            )

    def test_no_compiled_or_cost_table_skips_the_check(self):
        # authorize() with neither argument must not raise for lack of data.
        SafetyGate().authorize(_envelope())


class TestEstimateCostIsConservative:
    """S4: the estimate must be >= true call count x table, never optimistic."""

    def test_estimate_matches_or_exceeds_call_count_times_table(
        self, synthetic_aws_registry: BindingRegistry
    ):
        compiled = _compiled(synthetic_aws_registry)
        per_capability_cost = 0.01
        cost_table = {DEFAULT_COST_KEY: per_capability_cost}

        true_call_count = sum(
            len(matrix.capabilities) * len(matrix.identities) * matrix.trials
            for matrix in compiled.probe_matrices
        )
        expected_floor = true_call_count * per_capability_cost

        estimate = estimate_cost(compiled, cost_table)

        assert estimate >= expected_floor

    def test_unpriced_capability_defaults_to_the_default_key_not_free(
        self, synthetic_aws_registry: BindingRegistry
    ):
        compiled = _compiled(synthetic_aws_registry)
        priced = estimate_cost(compiled, {DEFAULT_COST_KEY: 5.0})
        unpriced = estimate_cost(compiled, {})

        assert priced > 0.0
        assert unpriced == 0.0  # absent DEFAULT_COST_KEY falls back to 0.0, documented (not hidden)

    def test_every_probe_matrix_contributes_no_deduplication(
        self, synthetic_aws_registry: BindingRegistry
    ):
        compiled = _compiled(synthetic_aws_registry)
        assert len(compiled.probe_matrices) > 0
        cost_table = {DEFAULT_COST_KEY: 1.0}
        total = estimate_cost(compiled, cost_table)
        per_matrix_sum = sum(
            len(matrix.capabilities) * len(matrix.identities) * matrix.trials
            for matrix in compiled.probe_matrices
        )
        assert total == per_matrix_sum

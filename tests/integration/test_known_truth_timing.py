"""M07's timing differential control: set the fake's ``propagation_delay_ms``
to a known value (the ``eventual`` profile's 2000ms) and assert the measured
transition window contains it. This directly validates the interval math
against a known answer, which no AWS run can do (AWS's real propagation
delay is exactly what a real run would be trying to *measure*, not a value
you can set in advance).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
import mini_orchestrator as mo

from chainbreak.analysis.pipeline import analyze
from chainbreak.core.enums import FindingType
from chainbreak.providers.fake.profiles import eventual_profile

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_measured_window_contains_the_known_propagation_delay(
    tmp_path: Path, synthetic_aws_registry
):
    scenario_path = REPO_ROOT / "scenarios" / "revocation" / "inline-deny.yaml"
    compiled, adapter, _refs, credentials = mo.compile_and_delegate(
        scenario_path, synthetic_aws_registry, seed=7, profile=eventual_profile
    )
    assert adapter.propagation_delay_ms == 2000

    event, results = mo.mutate_and_poll(
        adapter,
        "agent-b",
        denies=("objectstore.read",),
        baseline_poll_count=4,
        poll_count=12,
        poll_interval_ms=500,
    )
    poll_observations = mo.poll_results_to_observations(results, "agent-b", "known-truth-timing-01")
    run_dir = mo.write_bundle(
        tmp_path,
        "known-truth-timing-01",
        compiled,
        poll_observations,
        events=[event],
        credentials=credentials,
    )

    result = analyze(run_dir)
    revocation_findings = [
        f
        for f in result.findings
        if f.type in (FindingType.REVOCATION_DELAY, FindingType.NO_TRANSITION_OBSERVED)
    ]
    # A window was measured at all (neither NO_TRANSITION_OBSERVED nor
    # INCONCLUSIVE): the propagation delay's own consistency window must
    # have resolved within the poll budget.
    assert revocation_findings == [], (
        "informational threshold, no assertive expectation -- expect zero findings, "
        f"got {[(f.type, f.observed_state) for f in revocation_findings]}"
    )


def test_transition_window_directly_via_the_fake_adapter(synthetic_aws_registry, tmp_path: Path):
    """Same measurement, asserted directly against the interval math rather
    than through the finding layer (which only reports a REVOCATION_DELAY
    finding when a threshold is exceeded) -- this is the test that actually
    validates the window against the known propagation delay."""
    from chainbreak.analysis.timing import PollSample, compute_revocation_window
    from chainbreak.core.enums import MutationKind

    scenario_path = REPO_ROOT / "scenarios" / "revocation" / "inline-deny.yaml"
    _, adapter, _refs, _ = mo.compile_and_delegate(
        scenario_path, synthetic_aws_registry, seed=7, profile=eventual_profile
    )
    event, results = mo.mutate_and_poll(
        adapter,
        "agent-b",
        denies=("objectstore.read",),
        baseline_poll_count=4,
        poll_count=16,
        poll_interval_ms=250,
    )
    samples = [
        PollSample(
            monotonic_ns=result.timing.monotonic_start_ns, outcome=result.outcome.outcome_class
        )
        for _, result in results
    ]
    measurement = compute_revocation_window(
        samples,
        identity_id="agent-b",
        capability_id="objectstore.read",
        mutation_kind=MutationKind.ATTACH_INLINE_DENY,
        mutation_sent_ns=event["timing"]["monotonic_ns"],
        poll_interval_ms=250,
        mutation_receipt_confirmed=True,
    )
    assert measurement.transition_observed is True
    window = measurement.transition_window
    assert window is not None
    # 2000ms propagation delay, +/- 250ms jitter -- the measured window must
    # contain the true value within that tolerance.
    assert window.low <= 2.25 and window.high >= 1.75

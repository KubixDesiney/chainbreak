"""Every shipped scenario must validate, and every capability it names must resolve.

This is the corpus test: it fails if a scenario drifts away from the schema, or
if a scenario references a capability the catalog does not define (G-4).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreak.capabilities.loader import load_catalog
from chainbreak.scenarios.safety import load_scenario_yaml
from chainbreak.scenarios.schema import ScenarioDocument

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_FILES = sorted((REPO_ROOT / "scenarios").rglob("*.yaml"))


def _capabilities_used(document: ScenarioDocument) -> set[str]:
    used: set[str] = set()
    for identity in document.spec.identities:
        used |= set(identity.capabilities or ())
        used |= set(identity.expect_capabilities or ())
    for delegation in document.spec.delegations:
        used |= set(delegation.intended_capabilities)
    for phase in document.spec.phases:
        if phase.capability:
            used.add(phase.capability)
        if phase.mutation:
            used |= set(phase.mutation.denies) | set(phase.mutation.grants)
    for task in document.spec.tasks:
        used |= set(task.requires_capabilities) | {step.use for step in task.steps}
    for expectation in document.spec.expectations:
        used |= set(expectation.allow) | set(expectation.deny)
        if expectation.capability:
            used.add(expectation.capability)
    return used


def test_corpus_is_not_empty() -> None:
    """Guards against the corpus tests passing vacuously."""
    assert len(SCENARIO_FILES) >= 12


@pytest.mark.parametrize("path", SCENARIO_FILES, ids=lambda p: p.stem)
def test_scenario_validates(path: Path) -> None:
    ScenarioDocument.model_validate(load_scenario_yaml(path))


@pytest.mark.parametrize("path", SCENARIO_FILES, ids=lambda p: p.stem)
def test_capability_closure(path: Path) -> None:
    """G-4: every capability named anywhere resolves in the catalog."""
    document = ScenarioDocument.model_validate(load_scenario_yaml(path))
    catalog = set(load_catalog().ids().sorted)
    unknown = _capabilities_used(document) - catalog
    assert not unknown, f"{path.name} references unknown capabilities: {sorted(unknown)}"


def test_negative_controls_live_in_their_own_directory() -> None:
    """A reviewer must never mistake a negative control for a health check."""
    for path in SCENARIO_FILES:
        document = ScenarioDocument.model_validate(load_scenario_yaml(path))
        is_control = document.spec.negative_control is not None
        in_control_dir = path.parent.name == "_negative-controls"
        assert is_control == in_control_dir, (
            f"{path}: negative_control={is_control} but directory says {in_control_dir}"
        )


def test_every_negative_control_kind_is_covered() -> None:
    """A detector without a negative control is an unproven detector."""
    from chainbreak.core.enums import NegativeControlKind

    covered = set()
    for path in SCENARIO_FILES:
        document = ScenarioDocument.model_validate(load_scenario_yaml(path))
        if document.spec.negative_control:
            covered.add(document.spec.negative_control.kind)
    assert covered == set(NegativeControlKind), (
        f"uncovered negative-control kinds: {sorted(set(NegativeControlKind) - covered)}"
    )


def test_every_family_has_at_least_one_scenario() -> None:
    from chainbreak.core.enums import BenchmarkFamily

    families = {
        ScenarioDocument.model_validate(load_scenario_yaml(p)).metadata.family
        for p in SCENARIO_FILES
    }
    assert families == set(BenchmarkFamily)

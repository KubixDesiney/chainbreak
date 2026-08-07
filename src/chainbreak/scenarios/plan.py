"""Execution plan ordering (SCENARIO_SPECIFICATION.md section 10, F4).

Turns a scenario's declared phase list -- document order is execution order,
``PhaseSpec`` carries no separate ordering field -- into a fully ordered
:class:`PlanStep` sequence, auto-inserting a ``SNAPSHOT`` phase immediately
before and immediately after every ``MUTATE``. The snapshot pair is what lets
a revocation measurement anchor its transition window to a policy state
actually observed on both sides of the mutation, rather than assumed.
"""

from __future__ import annotations

from collections.abc import Sequence

from chainbreak.core.enums import PhaseKind
from chainbreak.core.models import PlanStep
from chainbreak.scenarios.schema import PhaseSpec


def build_plan(phases: Sequence[PhaseSpec]) -> tuple[PlanStep, ...]:
    steps: list[PlanStep] = []
    order = 0

    for phase in phases:
        if phase.kind is PhaseKind.MUTATE:
            steps.append(
                PlanStep(
                    order=order,
                    phase_name=f"{phase.name}-pre-snapshot",
                    kind=PhaseKind.SNAPSHOT,
                    auto_inserted=True,
                )
            )
            order += 1

        steps.append(PlanStep(order=order, phase_name=phase.name, kind=phase.kind))
        order += 1

        if phase.kind is PhaseKind.MUTATE:
            steps.append(
                PlanStep(
                    order=order,
                    phase_name=f"{phase.name}-post-snapshot",
                    kind=PhaseKind.SNAPSHOT,
                    auto_inserted=True,
                )
            )
            order += 1

    return tuple(steps)

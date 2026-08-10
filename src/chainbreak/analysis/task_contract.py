"""Compares each recorded :class:`~chainbreak.core.models.TaskOutcome`
against its scenario-declared ``completion_contract`` (M14). Three checks,
up to three genuinely distinct findings per task -- silent narrowing,
capability substitution, redelegation attempt -- never collapsed into one
(the milestone's own explicit requirement).

``analysis/rules.py`` already implements the three predicates
(``rule_silent_narrowing`` from M7, ``rule_capability_substituted``/
``rule_redelegation_attempted`` new at M14); this module is what actually
extracts ``TaskOutcome`` records from a bundle's evidence stream and gates
the two new checks by each task's own declared contract, the same
"measurement layer already existed, execution/analysis wiring is the
milestone's own contribution" pattern M12/M13 both followed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from chainbreak.analysis.rules import (
    rule_capability_substituted,
    rule_redelegation_attempted,
    rule_silent_narrowing,
)
from chainbreak.core.models import Finding, TaskOutcome, TaskPlan

__all__ = ["extract_task_outcomes", "task_contract_findings"]


def extract_task_outcomes(events: Sequence[dict[str, Any]]) -> list[TaskOutcome]:
    return [
        TaskOutcome.model_validate(event["task_outcome"])
        for event in events
        if event.get("kind") == "TASK_OUTCOME_RECORDED" and "task_outcome" in event
    ]


def task_contract_findings(
    outcomes: Sequence[TaskOutcome], task_plans: Sequence[TaskPlan]
) -> list[Finding]:
    plans_by_task_id = {plan.task_id: plan for plan in task_plans}
    findings: list[Finding] = []
    for outcome in outcomes:
        plan = plans_by_task_id.get(outcome.task_id)
        # A task outcome with no matching plan (should not happen against a
        # bundle the real compiler/orchestrator produced) is conservative,
        # not permissive: both contract checks default to active rather
        # than silently skipped.
        must_not_substitute = True if plan is None else plan.must_not_substitute
        must_not_redelegate = True if plan is None else plan.must_not_redelegate

        narrowing = rule_silent_narrowing(outcome)
        if narrowing is not None:
            findings.append(narrowing)

        substituted = rule_capability_substituted(outcome, must_not_substitute=must_not_substitute)
        if substituted is not None:
            findings.append(substituted)

        redelegated = rule_redelegation_attempted(outcome, must_not_redelegate=must_not_redelegate)
        if redelegated is not None:
            findings.append(redelegated)

    return findings

"""The confidence gate, exactly as AUTHORIZATION_MODEL.md section 6 (F3).

```
confidence = HIGH   if coverage == 1.0
                    and all contributing cells unanimous across trials
                    and no ERROR_* outcomes in the matrix
                    and policy state snapshot succeeded before and after
           = MEDIUM if coverage >= 0.9 and no INDETERMINATE in contributing cells
           = LOW    if coverage >= 0.7
           = INSUFFICIENT otherwise -> finding type becomes INCONCLUSIVE
```

A candidate backed by zero contributing cells is always ``INSUFFICIENT``,
regardless of what a caller passes as ``coverage`` -- a finding with no
observations behind it cannot be ``HIGH`` by construction, not by trusting
the caller to compute ``coverage`` consistently.
"""

from __future__ import annotations

from collections.abc import Iterable

from chainbreak.core.enums import Confidence, OutcomeClass
from chainbreak.core.models import ProbeCellResult


def gate_confidence(
    *,
    coverage: float,
    cells: Iterable[ProbeCellResult],
    policy_snapshot_ok: bool = True,
) -> Confidence:
    cells = list(cells)
    if not cells:
        return Confidence.INSUFFICIENT

    all_unanimous = all(cell.unanimous for cell in cells)
    has_error_outcome = any(trial.is_error for cell in cells for trial in cell.trials)
    has_indeterminate = any(cell.resolved is OutcomeClass.INDETERMINATE for cell in cells)

    if coverage >= 1.0 and all_unanimous and not has_error_outcome and policy_snapshot_ok:
        return Confidence.HIGH
    if coverage >= 0.9 and not has_indeterminate:
        return Confidence.MEDIUM
    if coverage >= 0.7:
        return Confidence.LOW
    return Confidence.INSUFFICIENT


def confidence_rationale(
    *,
    coverage: float,
    cells: Iterable[ProbeCellResult],
    policy_snapshot_ok: bool = True,
) -> str:
    """A short, human-readable justification -- the ``confidence_rationale``
    field EVIDENCE_SCHEMA.md's ``findings.json`` example shows alongside
    every finding, e.g. ``"coverage=1.0; 3/3 trials unanimous; no ERROR
    outcomes; policy snapshots succeeded before and after"``."""
    cells = list(cells)
    if not cells:
        return "no contributing observations"

    total_trials = sum(len(cell.trials) for cell in cells)
    unanimous_cells = sum(1 for cell in cells if cell.unanimous)
    has_error_outcome = any(trial.is_error for cell in cells for trial in cell.trials)

    parts = [
        f"coverage={coverage:.2f}",
        f"{unanimous_cells}/{len(cells)} cells unanimous ({total_trials} trials total)",
        "no ERROR outcomes" if not has_error_outcome else "ERROR outcomes present",
    ]
    parts.append(
        "policy snapshots succeeded before and after"
        if policy_snapshot_ok
        else "policy snapshot missing or failed"
    )
    return "; ".join(parts)

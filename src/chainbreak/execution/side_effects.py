"""Independent side-effect verification (M14, F4): after a task runs, the
**bootstrap** identity checks whether the output marker it claims to have
written actually exists. The worker's self-report
(:class:`~chainbreak.core.models.TaskOutcome.output_marker_written`) is
never trusted for this -- it is exactly the field this check exists to
verify or refute.

This is the milestone's own stated core requirement, restated from
EXPERIMENT_PROTOCOL.md section 5, step 5: "a task that reports COMPLETE
while its output marker is absent is the purest possible instance of
silent failure, and it is verified by the benchmark rather than trusted
from the worker's self-report."

For the fake provider, verification reads
``FakeProviderAdapter.scratch_marker_exists`` -- the same store
``execution/task_runner.py`` wrote to on a real, successful invocation of
the task's declared last step, never on the worker's claim. A real,
future-provider adapter (M17) would instead make an actual read call
*as the bootstrap identity* against the same location the task was asked to
write to; the ``provisioning_ref`` parameter exists for that future call's
sake even though the fake's own escape hatch does not need it.
"""

from __future__ import annotations

from chainbreak.core.models import IdentityRef
from chainbreak.providers.base.protocol import ProviderAdapter

__all__ = ["marker_id_for", "verify_output_marker"]


def marker_id_for(run_id: str, task_id: str) -> str:
    """The one scratch-marker identity a task's designated output write is
    recorded and verified under -- shared between ``execution/task_runner.py``
    (the write side) and this module (the independent read side)."""
    return f"{run_id}:{task_id}"


def verify_output_marker(
    adapter: ProviderAdapter,
    provisioning_ref: IdentityRef,
    *,
    run_id: str,
    task_id: str,
    output_capability: str | None = None,
) -> bool:
    """F4: never trusts ``TaskOutcome.output_marker_written``. Returns
    ``False`` (never a guess) if the adapter has no way to check at all."""
    live_checker = getattr(adapter, "verify_output_marker", None)
    if live_checker is not None:
        return bool(
            live_checker(
                provisioning_ref,
                run_id=run_id,
                task_id=task_id,
                output_capability=output_capability,
            )
        )
    checker = getattr(adapter, "scratch_marker_exists", None)
    if checker is None:
        return False
    return bool(checker(marker_id_for(run_id, task_id)))

"""The SafetyGate -- the single choke point every run passes through before
anything happens (SI-5).

Not bypassable by construction: there is no flag anywhere in the CLI that
disables it. That claim is proved by ``tests/unit/test_cli_surface.py``,
which introspects every Typer command's options, not by convention or code
review -- a bypass flag added later for "convenience" fails that test the
moment it exists.

``SafetyGate.authorize`` is deliberately provider-agnostic: real account
identity verification (SI-6) needs a live provider session and arrives with
the AWS adapter (M8); this gate checks everything that can be known before
one exists -- that an envelope was resolved at all, that a caller-supplied
account/region matches its allowlist, that a caller-supplied namespace
matches the envelope's pattern (SI-2), and that a compiled scenario's
estimated cost stays under the envelope's ceiling (SI-8). The duration
ceiling (SI-7) is enforced structurally: ``SafetyEnvelope`` itself refuses
to construct with ``max_run_duration_seconds`` above the 14400s hard cap,
so a run with an over-ceiling duration never reaches ``authorize`` with a
non-``None`` envelope in the first place.
"""

from __future__ import annotations

import re

from chainbreak.core.errors import (
    AccountNotAllowedError,
    CostEstimateExceededError,
    NamespaceViolationError,
    RegionNotAllowedError,
    SafetyEnvelopeError,
)
from chainbreak.core.models import CompiledScenario, SafetyEnvelope

DEFAULT_COST_KEY = "__default__"


def estimate_cost(compiled: CompiledScenario, cost_table: dict[str, float]) -> float:
    """Static per-capability cost table x compiled plan call count (SI-8).

    Deliberately conservative (S4): a capability with no cost-table entry is
    priced at ``cost_table[DEFAULT_COST_KEY]`` (0.0 if absent) rather than
    silently treated as free-and-uncounted, and every probe cell in a matrix
    is charged for every trial -- there is no deduplication across identities
    or phases that could make the estimate optimistic.
    """
    default = cost_table.get(DEFAULT_COST_KEY, 0.0)
    total = 0.0
    for matrix in compiled.probe_matrices:
        per_call = sum(cost_table.get(capability, default) for capability in matrix.capabilities)
        total += per_call * len(matrix.identities) * matrix.trials
    return total


class SafetyGate:
    """Authorizes a run. Raises rather than returning a boolean: a rejected
    run must never be mistaken for an authorized one by a caller that forgot
    to check a return value."""

    def authorize(
        self,
        envelope: SafetyEnvelope | None,
        *,
        account_id: str | None = None,
        region: str | None = None,
        namespace: str | None = None,
        compiled: CompiledScenario | None = None,
        cost_table: dict[str, float] | None = None,
    ) -> None:
        if envelope is None:
            raise SafetyEnvelopeError(
                "no resolved safety envelope; a run cannot proceed without one"
            )

        if account_id is not None and account_id not in envelope.allowed_account_ids:
            raise AccountNotAllowedError(
                f"account {account_id} is not in the allowlist",
                account_id=account_id,
                allowed_account_ids=list(envelope.allowed_account_ids),
            )

        if region is not None and region not in envelope.allowed_regions:
            raise RegionNotAllowedError(
                f"region {region} is not in the allowlist",
                region=region,
                allowed_regions=list(envelope.allowed_regions),
            )

        if namespace is not None and not re.fullmatch(envelope.namespace_pattern, namespace):
            raise NamespaceViolationError(
                f"namespace {namespace!r} does not match pattern {envelope.namespace_pattern!r}",
                namespace=namespace,
                namespace_pattern=envelope.namespace_pattern,
            )

        if compiled is not None and cost_table is not None:
            estimate = estimate_cost(compiled, cost_table)
            if estimate > envelope.max_estimated_cost_usd:
                raise CostEstimateExceededError(
                    f"estimated cost ${estimate:.4f} exceeds ceiling "
                    f"${envelope.max_estimated_cost_usd:.4f}",
                    estimate_usd=estimate,
                    ceiling_usd=envelope.max_estimated_cost_usd,
                )

"""Category-level confidence: the minimum across every contributing signal,
never an average (M15 F4, SCORING_MODEL.md section 3).

``core/models.py::min_confidence`` already implements the aggregation
primitive (``analysis/rules.py``'s per-finding confidence gate is not built
on it -- that gate produces a *single* finding's confidence from its own
contributing probe cells -- but the *category* level needs to combine
several already-computed ``Finding.confidence`` values, which is exactly
what ``min_confidence`` is for). This module adds the one piece that does
not exist yet: folding the category's own measurement coverage in as an
additional contributor, via the same three-tier gate
``analysis/confidence.py::gate_confidence`` applies to a single finding,
generalized to a whole category.
"""

from __future__ import annotations

from collections.abc import Iterable

from chainbreak.core.enums import Confidence
from chainbreak.core.models import Finding, min_confidence

__all__ = ["category_confidence", "coverage_baseline_confidence"]


def coverage_baseline_confidence(coverage: float) -> Confidence:
    """The category's own coverage, read through the same three-tier gate
    ``analysis/confidence.py::gate_confidence`` uses per finding
    (AUTHORIZATION_MODEL.md section 6), generalized to a whole category:
    full coverage can be ``HIGH``, but nothing below 0.7 exceeds ``LOW``."""
    if coverage >= 1.0:
        return Confidence.HIGH
    if coverage >= 0.9:
        return Confidence.MEDIUM
    if coverage >= 0.7:
        return Confidence.LOW
    return Confidence.INSUFFICIENT


def category_confidence(*, coverage: float, contributing: Iterable[Finding]) -> Confidence:
    """``min()`` across the coverage baseline and every contributing
    finding's own confidence (F4) -- one ``LOW``-confidence finding makes
    the whole category ``LOW``, never averaged away by a pile of easy
    measurements alongside it."""
    return min_confidence(
        (coverage_baseline_confidence(coverage), *(f.confidence for f in contributing))
    )

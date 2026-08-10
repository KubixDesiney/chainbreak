"""Coverage = measured applicable cells / total applicable cells
(SCORING_MODEL.md section 3, M15 F2/F3).

Two decisions live here, kept out of ``scoring/categories.py`` so all six
category evaluators apply them identically rather than each reinventing the
edge cases:

- **Zero applicable cells is not zero coverage.** A scenario that never
  declared a ``MUTATE``/``POLL`` phase has nothing to measure for Revocation
  Responsiveness at all -- that is ``NOT_MEASURED``, never a ``CONSISTENT``
  or ``DIVERGENT`` verdict computed over an empty set (F2). ``is_exercised``
  is the single gate every evaluator checks before computing a status.
- **coverage < 0.7 forces PARTIAL regardless of what the measured cells
  showed** (F3). ``CategoryResult`` itself already enforces this as a model
  validator (``core/models.py``) -- not duplicated here as a second source
  of truth -- so this module only computes the ratio; the forcing itself is
  the model's job.
"""

from __future__ import annotations

__all__ = ["coverage_ratio", "is_exercised"]

#: F3's own threshold, named here so a reader does not have to go hunting
#: through ``core/models.py`` to find the number this module's callers are
#: implicitly building toward.
PARTIAL_COVERAGE_THRESHOLD = 0.7


def coverage_ratio(*, measured: int, applicable: int) -> float:
    """``measured`` / ``applicable``. Callers are expected to have already
    checked :func:`is_exercised` -- an ``applicable`` of zero returns 0.0
    here rather than raising, since a caller building a ``NOT_MEASURED``
    result still wants *some* coverage value to construct with."""
    if applicable <= 0:
        return 0.0
    if measured < 0 or measured > applicable:
        raise ValueError(f"measured ({measured}) out of range for applicable ({applicable})")
    return measured / applicable


def is_exercised(*, applicable: int, measured: int) -> bool:
    """F2: a category the scenario never exercised at all is ``NOT_MEASURED``,
    never ``CONSISTENT`` -- true only when there is at least one applicable
    cell *and* at least one of them was actually measured. A category with
    applicable cells but zero measured ones (e.g. the run aborted before a
    single poll landed) is not "not exercised by the scenario" -- the
    scenario declared it -- so that case is left to fall through to a
    coverage-forced ``PARTIAL``, not ``NOT_MEASURED``."""
    return applicable > 0 and measured > 0

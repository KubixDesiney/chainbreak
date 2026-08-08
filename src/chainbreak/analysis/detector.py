"""Negative-control assertion (F7): did the run's findings actually contain
the one a negative control declares it must?

``DETECTOR_FAILURE`` is the most important entry in the finding-type table
(AUTHORIZATION_MODEL.md section 6): it is the only type that says something
about CHAINBREAK's own detectors rather than about the system under test,
and it is why negative controls exist at all. A block containing one
invalidates every positive result produced alongside it.
"""

from __future__ import annotations

from collections.abc import Sequence

from chainbreak.core.models import AuthoritySet, CompiledExpectedFinding, DetectorCheck, Finding


def _capabilities_satisfied(finding: Finding, expected_capabilities: AuthoritySet) -> bool:
    """Not every finding type carries a per-capability ``delta`` (timing and
    task findings don't); when a finding type has none, identity + type is
    the only signal available and capability matching is vacuously
    satisfied rather than forcing a spurious failure."""
    if not expected_capabilities:
        return True
    mentioned: set[str] = set()
    for values in finding.delta.values():
        mentioned.update(values)
    if not mentioned:
        return True
    return set(expected_capabilities) <= mentioned


def check_negative_control(
    expected: CompiledExpectedFinding,
    findings: Sequence[Finding],
    *,
    negative_control_id: str,
) -> DetectorCheck:
    for finding in findings:
        if finding.type != expected.type:
            continue
        if expected.identity_id and finding.identity_id != expected.identity_id:
            continue
        if not _capabilities_satisfied(finding, expected.capabilities):
            continue
        if finding.confidence.rank < expected.min_confidence.rank:
            continue
        return DetectorCheck(
            negative_control_id=negative_control_id,
            expected_type=expected.type,
            produced=True,
            result="DETECTOR_OK",
        )
    return DetectorCheck(
        negative_control_id=negative_control_id,
        expected_type=expected.type,
        produced=False,
        result="DETECTOR_FAILURE",
    )

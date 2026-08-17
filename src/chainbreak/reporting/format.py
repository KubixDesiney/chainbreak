"""Shared text formatting for timing results, used identically by
``terminal.py``, ``markdown.py`` and ``html.py`` so EXPERIMENT_PROTOCOL §7's
"every timing result carries n, an interval, the mechanism, and the region"
requirement is satisfied by one function all three renderers call, rather
than three independently-maintained format strings that could drift apart.
"""

from __future__ import annotations

from chainbreak.core.models import Interval

__all__ = ["LIMITATIONS", "REGION_NOT_CAPTURED", "format_timing_result"]

#: F5, shared by every renderer so the exact wording -- and therefore
#: ``language.py::LIMITATIONS_TERMS``'s substring match against it -- can
#: never drift between formats. Each sentence deliberately contains its
#: corresponding required term as a literal substring.
LIMITATIONS: tuple[str, ...] = (
    "Single account: real-AWS bundles cover one account; fake-provider bundles use one "
    "synthetic account and are apparatus checks.",
    "Single region: real-AWS bundles cover one region; fake-provider bundles use one "
    "synthetic region and are apparatus checks.",
    "Simple policies: the shipped scenarios exercise a small number of statements per "
    "identity, not production-scale policy complexity.",
    "Deterministic worker: v0.1's task worker is a deterministic, synthetic implementation "
    "of the TaskWorker Protocol, not a real agent.",
    "Small n: trial counts and cross-run sample sizes are both modest (see coverage/"
    "confidence per category and n reported with every timing result).",
)

#: The evidence bundle schema does not currently record which region a run
#: executed against (``Manifest.provenance`` has no ``region`` key -- see
#: PROJECT_STATUS.md's "Known issues"). Rendering this placeholder rather
#: than inventing a value keeps the field present (satisfying the language
#: rule's structural requirement) while staying honest about what the
#: bundle actually captured -- the same "prefer omission/an honest label
#: over a confident wrong number" rule ``analysis/stale.py`` already applies
#: to ``stale_window_seconds``.
REGION_NOT_CAPTURED = "not captured in bundle (single-region design; see Limitations)"


def format_timing_result(
    label: str, value: Interval, *, n: int, mechanism: str, region: str = REGION_NOT_CAPTURED
) -> str:
    # ASCII-only (a plain hyphen, not an en-dash): a report printed to a
    # native Windows console without a UTF-8 code page raises
    # UnicodeEncodeError on anything outside cp1252 -- reproduced directly
    # against this function's own output before switching characters.
    return (
        f"{label}: {value.low:.2f}-{value.high:.2f}{value.unit} "
        f"(n={n}, mechanism={mechanism}, region={region})"
    )

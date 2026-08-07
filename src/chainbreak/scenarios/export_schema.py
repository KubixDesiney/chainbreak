"""Export JSON Schemas from the Pydantic models.

The Pydantic models are the single source of truth; ``schemas/*.json`` are
generated artifacts committed for external consumers (editors, CI, third
parties validating a bundle they received). CI regenerates and diffs them, so a
model change that is not reflected in the committed schema fails the build.

Run:  python -m chainbreak.scenarios.export_schema [output_dir]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from chainbreak.core.models import (
    CategoryResult,
    CredentialRecord,
    DetectorCheck,
    ExperimentRun,
    Finding,
    Observation,
    PolicyStateSnapshot,
    RevocationMeasurement,
    StaleAuthorityMeasurement,
    TaskOutcome,
)
from chainbreak.scenarios.schema import ScenarioDocument

_BASE_ID = "https://chainbreak.dev/schemas"

_EXPORTS: dict[str, tuple[type[BaseModel], str]] = {
    "scenario.v1alpha1": (
        ScenarioDocument,
        "Declarative authorization experiment definition. Semantic checks (graph "
        "invariants G-1..G-5) and safety checks (SI-11) are not expressible in JSON "
        "Schema and are enforced by the loader; passing this schema is necessary but "
        "not sufficient.",
    ),
    "observation.v1": (
        Observation,
        "One probe attempt. The atom of the evidence model. Contains no secret material "
        "and no unhashed provider identifier (EV-1, T-13).",
    ),
    "finding.v1": (
        Finding,
        "A conclusion derived from observations. Observation and security interpretation "
        "are separate fields and are rendered under separate headings (ADR-006).",
    ),
    "credential.v1": (
        CredentialRecord,
        "Credential metadata. Never contains a secret access key, session token, or any "
        "truncation or encryption thereof (EV-1).",
    ),
    "policy-state.v1": (PolicyStateSnapshot, "Policy fingerprints at a point in time."),
    "task-outcome.v1": (TaskOutcome, "Result of a workload execution under constrained authority."),
    "revocation-measurement.v1": (
        RevocationMeasurement,
        "A revocation transition measurement. Always an interval, never a scalar.",
    ),
    "stale-authority-measurement.v1": (
        StaleAuthorityMeasurement,
        "Execution-time authority classification, including the paired fresh-credential "
        "outcome that disambiguates it.",
    ),
    "category-result.v1": (
        CategoryResult,
        "Per-category result. There is no composite score (ADR-010).",
    ),
    "detector-check.v1": (
        DetectorCheck,
        "Negative-control verification. A DETECTOR_FAILURE invalidates the block's "
        "positive results.",
    ),
    "experiment-run.v1": (ExperimentRun, "Run identity, provenance and safety envelope."),
}


def build(name: str, model: type[BaseModel], description: str) -> dict[str, Any]:
    schema = model.model_json_schema(by_alias=True, mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{_BASE_ID}/{name}.schema.json"
    schema["description"] = (
        f"{description} Generated from the Pydantic model -- do not hand-edit. "
        "Regenerate with `python -m chainbreak.scenarios.export_schema`."
    )
    return schema


def main(argv: list[str]) -> int:
    output_dir = Path(argv[1]) if len(argv) > 1 else Path("schemas")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, (model, description) in _EXPORTS.items():
        target = output_dir / f"{name}.schema.json"
        target.write_text(
            json.dumps(build(name, model, description), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))

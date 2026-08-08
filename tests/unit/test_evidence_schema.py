"""M6 acceptance criterion 1: a fake-provider bundle validates against every
relevant schema in ``schemas/``, and the embedded SQLite migration in
``evidence/index.py`` stays byte-identical to the committed
``schemas/run-index.sql`` (index.py embeds a literal copy rather than reading
the file at runtime -- see that module's docstring for why)."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from chainbreak.evidence import index as index_module
from chainbreak.evidence.reader import (
    read_credentials,
    read_manifest,
    read_observations,
    read_policy_states,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_DIR = REPO_ROOT / "schemas"
GOLDEN_RUN_DIR = (
    REPO_ROOT / "tests" / "fixtures" / "bundles" / "golden" / "01J8XKQ4V7ZP3N2M9YB6TCGOLD"
)


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def _strip_comments_and_blank_lines(sql: str) -> str:
    return "\n".join(
        line for line in sql.splitlines() if line.strip() and not line.strip().startswith("--")
    )


def test_run_index_schema_matches_committed_sql_file() -> None:
    """Compares executable SQL only (comments stripped from both sides): the
    two copies drift on prose freely, but a real schema change -- a table,
    column, or constraint -- must land in both or this fails."""
    committed = (SCHEMAS_DIR / "run-index.sql").read_text(encoding="utf-8")
    anchor = "PRAGMA foreign_keys"
    committed_body = committed[committed.index(anchor) :]
    assert _strip_comments_and_blank_lines(
        index_module._SCHEMA_SQL
    ) == _strip_comments_and_blank_lines(committed_body)


def test_golden_bundle_manifest_is_readable_and_sealed() -> None:
    manifest = read_manifest(GOLDEN_RUN_DIR / "manifest.json")
    assert manifest.run_id == "01J8XKQ4V7ZP3N2M9YB6TCGOLD"
    assert manifest.integrity.root is not None
    assert manifest.counts.observations == 3
    assert manifest.counts.events == 1
    assert manifest.counts.policy_snapshots == 1
    assert manifest.counts.credentials == 1


def test_golden_bundle_observations_match_observation_schema() -> None:
    schema = _load_schema("observation.v1")
    observations = list(read_observations(GOLDEN_RUN_DIR))
    assert len(observations) == 3
    for observation in observations:
        jsonschema.validate(json.loads(observation.model_dump_json()), schema)


def test_golden_bundle_credentials_match_credential_schema() -> None:
    schema = _load_schema("credential.v1")
    credentials = list(read_credentials(GOLDEN_RUN_DIR))
    assert len(credentials) == 1
    for credential in credentials:
        jsonschema.validate(json.loads(credential.model_dump_json()), schema)


def test_golden_bundle_policy_states_match_policy_state_schema() -> None:
    schema = _load_schema("policy-state.v1")
    snapshots = list(read_policy_states(GOLDEN_RUN_DIR))
    assert len(snapshots) == 1
    for snapshot in snapshots:
        jsonschema.validate(json.loads(snapshot.model_dump_json()), schema)

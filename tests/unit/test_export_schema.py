"""scenarios/export_schema.py -- JSON Schema generation from the Pydantic models.

Exercised via `python -m chainbreak.scenarios.export_schema` in CI's `schemas`
job (a subprocess, so it earns no pytest coverage credit there); this file
calls the same functions directly so the module has a dedicated unit test
rather than relying entirely on a CI subprocess step.
"""

from __future__ import annotations

import json

import jsonschema
import pytest

from chainbreak.core.models import Observation
from chainbreak.scenarios.export_schema import _EXPORTS, build, main

pytestmark = pytest.mark.unit


class TestBuild:
    def test_build_produces_a_valid_draft_2020_12_schema(self):
        schema = build("observation.v1", Observation, "test description")
        jsonschema.Draft202012Validator.check_schema(schema)

    def test_build_sets_id_and_schema_fields(self):
        schema = build("observation.v1", Observation, "test description")
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"].endswith("/observation.v1.schema.json")

    def test_build_description_includes_the_regeneration_note(self):
        schema = build("observation.v1", Observation, "test description")
        assert "test description" in schema["description"]
        assert "do not hand-edit" in schema["description"]

    def test_every_registered_export_builds_a_valid_schema(self):
        for name, (model, description) in _EXPORTS.items():
            schema = build(name, model, description)
            jsonschema.Draft202012Validator.check_schema(schema)


class TestMain:
    def test_writes_one_file_per_export(self, tmp_path):
        exit_code = main(["export_schema", str(tmp_path)])
        assert exit_code == 0
        written = {p.name for p in tmp_path.glob("*.schema.json")}
        assert written == {f"{name}.schema.json" for name in _EXPORTS}

    def test_written_files_are_valid_json(self, tmp_path):
        main(["export_schema", str(tmp_path)])
        for path in tmp_path.glob("*.schema.json"):
            json.loads(path.read_text(encoding="utf-8"))

    def test_defaults_to_schemas_directory_argument_form(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        exit_code = main(["export_schema"])
        assert exit_code == 0
        assert (tmp_path / "schemas").is_dir()
        assert list((tmp_path / "schemas").glob("*.schema.json"))

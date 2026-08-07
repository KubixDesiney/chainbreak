"""scenarios/safety.py -- SI-11 stage 5, the restricted loader and document bounds.

Runs even in --offline mode and cannot be skipped: this is what makes an
untrusted scenario file a *parsing* problem rather than a security problem.
"""

from __future__ import annotations

import pytest

from chainbreak.core.errors import ScenarioSafetyError, ScenarioSyntaxError
from chainbreak.scenarios.safety import (
    MAX_DOCUMENT_BYTES,
    MAX_NESTING_DEPTH,
    MAX_NODE_COUNT,
    assert_no_literal_infrastructure,
    load_scenario_yaml,
)

pytestmark = pytest.mark.unit


def _write(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


class TestLiteralInfrastructureRejection:
    def test_literal_arn_rejected(self):
        with pytest.raises(ScenarioSafetyError, match="must not name real infrastructure"):
            assert_no_literal_infrastructure("value: arn:aws:iam::x:role/x", source="test")

    def test_literal_account_id_rejected(self):
        with pytest.raises(ScenarioSafetyError):
            assert_no_literal_infrastructure("value: '123456789012'", source="test")

    def test_literal_region_rejected(self):
        with pytest.raises(ScenarioSafetyError):
            assert_no_literal_infrastructure("region: us-east-1", source="test")

    def test_external_url_rejected(self):
        with pytest.raises(ScenarioSafetyError):
            assert_no_literal_infrastructure("url: https://evil.example-host.net/x", source="test")

    def test_example_and_localhost_urls_are_allowed(self):
        assert_no_literal_infrastructure(
            "a: https://example.com\nb: https://localhost:8080", source="test"
        )

    def test_clean_document_passes(self):
        assert_no_literal_infrastructure("id: foo\nname: bar\n", source="test")

    def test_comment_only_line_is_not_scanned(self):
        """The ARN pattern in a comment describing the check itself must not
        trip the check -- otherwise this very test file's docstrings would."""
        assert_no_literal_infrastructure(
            "# arn:aws:iam::123456789012:role/example is what we reject\nreal: value",
            source="test",
        )


class TestLoadScenarioYaml:
    def test_load_valid_document(self, tmp_path):
        path = _write(tmp_path, "s.yaml", "a: 1\nb: two\n")
        assert load_scenario_yaml(path) == {"a": 1, "b": "two"}

    def test_oversized_document_rejected(self, tmp_path):
        path = _write(tmp_path, "s.yaml", "a: " + "x" * (MAX_DOCUMENT_BYTES + 1))
        with pytest.raises(ScenarioSafetyError, match="exceeds"):
            load_scenario_yaml(path)

    def test_custom_tag_rejected(self, tmp_path):
        path = _write(tmp_path, "s.yaml", "a: !custom_tag value\n")
        with pytest.raises(ScenarioSafetyError, match="unsupported YAML tag"):
            load_scenario_yaml(path)

    def test_python_object_tag_rejected(self, tmp_path):
        path = _write(tmp_path, "s.yaml", "a: !!python/object:builtins.list []\n")
        with pytest.raises(ScenarioSafetyError):
            load_scenario_yaml(path)

    def test_invalid_yaml_syntax_rejected(self, tmp_path):
        path = _write(tmp_path, "s.yaml", "a: [unclosed\n")
        with pytest.raises(ScenarioSyntaxError, match="invalid YAML"):
            load_scenario_yaml(path)

    def test_non_mapping_document_rejected(self, tmp_path):
        path = _write(tmp_path, "s.yaml", "- just\n- a\n- list\n")
        with pytest.raises(ScenarioSyntaxError, match="must be a mapping"):
            load_scenario_yaml(path)

    def test_excessive_node_count_rejected(self, tmp_path):
        items = "\n".join(f"  - {i}" for i in range(MAX_NODE_COUNT + 1))
        path = _write(tmp_path, "s.yaml", f"items:\n{items}\n")
        with pytest.raises(ScenarioSafetyError, match="nodes"):
            load_scenario_yaml(path)

    def test_excessive_nesting_rejected(self, tmp_path):
        nested = "a"
        for _ in range(MAX_NESTING_DEPTH + 2):
            nested = f"[{nested}]"
        path = _write(tmp_path, "s.yaml", f"root: {nested}\n")
        with pytest.raises(ScenarioSafetyError, match="nesting"):
            load_scenario_yaml(path)

"""config/settings.py -- layered resolution (F1) and config/fingerprint.py.

Layer order: defaults -> repo chainbreak.toml -> user config -> CHAINBREAK_*
env -> CLI overrides, later wins, field by field. Each layer combination gets
its own test: a partial later layer must not clobber fields it did not
mention (settings.py's own stated invariant).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreak.config.fingerprint import fingerprint_settings
from chainbreak.config.settings import Settings, resolve_safety_envelope, resolve_settings
from chainbreak.core.errors import SafetyEnvelopeError

pytestmark = pytest.mark.unit


def _write_toml(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


class TestDefaultsOnly:
    def test_no_layers_returns_pure_defaults(self):
        settings = resolve_settings()
        assert settings == Settings()


class TestRepoLayer:
    def test_repo_toml_overrides_defaults(self, tmp_path: Path):
        repo_path = _write_toml(
            tmp_path / "chainbreak.toml",
            """
            [safety]
            allowed_account_ids = ["123456789012"]
            max_estimated_cost_usd = 2.5
            """,
        )
        settings = resolve_settings(repo_config_path=repo_path)
        assert settings.allowed_account_ids == ("123456789012",)
        assert settings.max_estimated_cost_usd == 2.5
        # Fields the repo layer never mentioned keep their defaults.
        assert settings.namespace_prefix == "cb"

    def test_missing_repo_file_is_not_an_error(self, tmp_path: Path):
        settings = resolve_settings(repo_config_path=tmp_path / "does-not-exist.toml")
        assert settings == Settings()

    def test_provider_default_table_maps_to_default_provider_field(self, tmp_path: Path):
        repo_path = _write_toml(
            tmp_path / "chainbreak.toml",
            """
            [provider]
            default = "aws"
            """,
        )
        settings = resolve_settings(repo_config_path=repo_path)
        assert settings.default_provider == "aws"


class TestUserLayerOverridesRepoLayer:
    def test_user_layer_wins_over_repo_layer_for_shared_field(self, tmp_path: Path):
        repo_path = _write_toml(
            tmp_path / "repo.toml",
            """
            [safety]
            max_estimated_cost_usd = 1.0
            allowed_regions = ["us-east-1"]
            """,
        )
        user_path = _write_toml(
            tmp_path / "user.toml",
            """
            [safety]
            max_estimated_cost_usd = 9.0
            """,
        )
        settings = resolve_settings(repo_config_path=repo_path, user_config_path=user_path)
        assert settings.max_estimated_cost_usd == 9.0
        # Field only the repo layer set survives an unrelated user override.
        assert settings.allowed_regions == ("us-east-1",)


class TestEnvLayerOverridesFileLayers:
    def test_env_wins_over_repo_and_user(self, tmp_path: Path):
        repo_path = _write_toml(
            tmp_path / "repo.toml",
            """
            [safety]
            max_estimated_cost_usd = 1.0
            """,
        )
        settings = resolve_settings(
            repo_config_path=repo_path,
            env={"CHAINBREAK_MAX_ESTIMATED_COST_USD": "42.0"},
        )
        assert settings.max_estimated_cost_usd == 42.0

    def test_env_tuple_field_is_comma_split(self):
        settings = resolve_settings(
            env={"CHAINBREAK_ALLOWED_REGIONS": "us-east-1, us-west-2 ,eu-west-1"}
        )
        assert settings.allowed_regions == ("us-east-1", "us-west-2", "eu-west-1")

    def test_env_bool_field_accepts_common_truthy_spellings(self):
        for spelling in ("1", "true", "TRUE", "yes", "on"):
            settings = resolve_settings(env={"CHAINBREAK_ALLOW_DANGEROUS_CAPABILITIES": spelling})
            assert settings.allow_dangerous_capabilities is True

    def test_env_bool_field_false_for_other_values(self):
        settings = resolve_settings(env={"CHAINBREAK_ALLOW_DANGEROUS_CAPABILITIES": "no"})
        assert settings.allow_dangerous_capabilities is False

    def test_env_int_field(self):
        settings = resolve_settings(env={"CHAINBREAK_MAX_DELEGATION_DEPTH": "3"})
        assert settings.max_delegation_depth == 3

    def test_unrelated_env_vars_are_ignored(self):
        settings = resolve_settings(env={"PATH": "/usr/bin", "HOME": "/home/x"})
        assert settings == Settings()


class TestCliOverridesWinOverEverything:
    def test_cli_override_wins_over_env(self):
        settings = resolve_settings(
            env={"CHAINBREAK_MAX_ESTIMATED_COST_USD": "5.0"},
            cli_overrides={"max_estimated_cost_usd": 100.0},
        )
        assert settings.max_estimated_cost_usd == 100.0

    def test_cli_override_of_none_does_not_clobber_earlier_layers(self):
        # A CLI flag the user did not pass surfaces as None from the parser,
        # not as an override -- resolve_settings must skip it, not overwrite
        # an earlier layer's value with None.
        settings = resolve_settings(
            env={"CHAINBREAK_MAX_ESTIMATED_COST_USD": "5.0"},
            cli_overrides={"max_estimated_cost_usd": None},
        )
        assert settings.max_estimated_cost_usd == 5.0


class TestFullLayerStack:
    def test_all_four_layers_each_contribute_a_distinct_field(self, tmp_path: Path):
        repo_path = _write_toml(
            tmp_path / "repo.toml",
            """
            [safety]
            allowed_regions = ["us-east-1"]
            """,
        )
        user_path = _write_toml(
            tmp_path / "user.toml",
            """
            [safety]
            namespace_prefix = "zz"
            """,
        )
        settings = resolve_settings(
            repo_config_path=repo_path,
            user_config_path=user_path,
            env={"CHAINBREAK_MAX_DELEGATION_DEPTH": "9"},
            cli_overrides={"max_estimated_cost_usd": 3.5},
        )
        assert settings.allowed_regions == ("us-east-1",)
        assert settings.namespace_prefix == "zz"
        assert settings.max_delegation_depth == 9
        assert settings.max_estimated_cost_usd == 3.5


class TestResolveSafetyEnvelope:
    def test_valid_settings_produce_an_envelope(self):
        settings = Settings(
            allowed_account_ids=("123456789012",),
            allowed_regions=("us-east-1",),
        )
        envelope = resolve_safety_envelope(settings, namespace="cb-deadbeef")
        assert envelope.allowed_account_ids == ("123456789012",)
        assert envelope.namespace_pattern == "^cb-[0-9a-f]{8}$"

    def test_invalid_settings_raise_safety_envelope_error(self):
        settings = Settings(allowed_account_ids=(), allowed_regions=("us-east-1",))
        with pytest.raises(SafetyEnvelopeError):
            resolve_safety_envelope(settings, namespace="cb-deadbeef")


class TestFingerprint:
    def test_fingerprint_is_deterministic(self):
        settings = Settings(allowed_account_ids=("123456789012",))
        assert fingerprint_settings(settings) == fingerprint_settings(settings)

    def test_fingerprint_changes_with_settings(self):
        a = Settings(max_estimated_cost_usd=1.0)
        b = Settings(max_estimated_cost_usd=2.0)
        assert fingerprint_settings(a) != fingerprint_settings(b)

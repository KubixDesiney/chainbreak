"""``providers/aws/policy_synthesis.py``: session-policy JSON document
synthesis. Pure logic against real ``ProviderCapabilityBinding`` objects --
no AWS needed.
"""

from __future__ import annotations

import json

import pytest

from chainbreak.capabilities.loader import load_catalog
from chainbreak.core.errors import ConfigurationError
from chainbreak.core.models import AuthoritySet
from chainbreak.providers.aws.bindings import build_aws_bindings
from chainbreak.providers.aws.policy_synthesis import (
    MAX_SESSION_POLICY_CHARS,
    synthesize_session_policy,
)

pytestmark = pytest.mark.unit

_NAMESPACE = "cb-a1b2c3d4"


def _bindings():
    catalog = load_catalog()
    return {
        b.capability_id: b
        for b in build_aws_bindings(catalog, account_id="123456789012", region="us-east-1")
    }


class TestSynthesizeSessionPolicy:
    def test_always_includes_the_whoami_statement(self):
        document = synthesize_session_policy(
            AuthoritySet.of("objectstore.read"), _bindings(), namespace=_NAMESPACE
        )
        parsed = json.loads(document)
        sids = {s["Sid"] for s in parsed["Statement"]}
        assert "CbAlwaysWhoami" in sids

    def test_does_not_duplicate_whoami_when_explicitly_requested(self):
        document = synthesize_session_policy(
            AuthoritySet.of("identity.whoami", "objectstore.read"),
            _bindings(),
            namespace=_NAMESPACE,
        )
        parsed = json.loads(document)
        whoami_statements = [s for s in parsed["Statement"] if s["Sid"] == "CbAlwaysWhoami"]
        assert len(whoami_statements) == 1

    def test_one_statement_per_intended_capability_plus_whoami(self):
        document = synthesize_session_policy(
            AuthoritySet.of("objectstore.read", "queue.send"), _bindings(), namespace=_NAMESPACE
        )
        parsed = json.loads(document)
        assert len(parsed["Statement"]) == 3

    def test_empty_intended_capabilities_still_grants_whoami(self):
        document = synthesize_session_policy(AuthoritySet.of(), _bindings(), namespace=_NAMESPACE)
        parsed = json.loads(document)
        assert len(parsed["Statement"]) == 1
        assert parsed["Statement"][0]["Sid"] == "CbAlwaysWhoami"

    def test_exceeding_the_2048_char_limit_raises_configuration_error(self):
        bindings = dict(_bindings())
        long_id = "objectstore.read"
        # Inflate the resource template so the synthesized document blows
        # past STS's real limit -- exercised directly rather than by
        # constructing 20+ real capabilities.
        binding = bindings[long_id]
        bindings[long_id] = binding.model_copy(
            update={"resource_template": "arn:aws:s3:::" + "x" * MAX_SESSION_POLICY_CHARS}
        )
        with pytest.raises(ConfigurationError, match="exceeds"):
            synthesize_session_policy(AuthoritySet.of(long_id), bindings, namespace=_NAMESPACE)

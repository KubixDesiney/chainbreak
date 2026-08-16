"""``providers/aws/disambiguation.py``: pure message/response-shape
classification, pinned against literal, hand-copied AWS message strings.

This is the canary AWS_PROVIDER_SPEC's own "Risks" section names: if AWS
ever changes its denial message wording, these exact fixtures are what
would stop matching and force a loud failure here, rather than a silent
degradation into ``DENIED_UNATTRIBUTED`` everywhere in production.

No AWS account, no network, no ``ClientError`` construction needed --
every classifier under test is a pure function of already-fetched strings.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chainbreak.core.enums import DenialAttribution, OutcomeClass
from chainbreak.providers.aws.disambiguation import (
    classify_denial_message,
    is_access_denied_code,
    is_lambda_function_fault,
    is_s3_object_missing,
)
from chainbreak.providers.aws.probes import _redact_aws_identifier_message

pytestmark = pytest.mark.unit

_FIXTURES = json.loads(
    (
        Path(__file__).parents[1]
        / "fixtures"
        / "provider_responses"
        / "aws-response-shapes.json"
    ).read_text(encoding="utf-8")
)["fixtures"]
_BY_ID = {fixture["id"]: fixture for fixture in _FIXTURES}


class TestClassifyDenialMessage:
    def test_provider_messages_redact_arns_before_evidence_gate(self):
        message = (
            "User: arn:aws:sts::123456789012:assumed-role/cb-deadbeef-agent-a/session "
            "is not authorized to perform: s3:GetObject on resource: "
            "arn:aws:s3:::cb-deadbeef-objectstore/cb-deadbeef/markers/marker.json"
        )
        scrubbed = _redact_aws_identifier_message(message)
        assert "123456789012" not in scrubbed
        assert "arn:aws" not in scrubbed
        assert "is not authorized to perform" in scrubbed

    def test_explicit_deny_identity_based_policy(self):
        message = _BY_ID["s3-explicit-deny-identity-policy"]["response"]["message"]
        outcome, attribution = classify_denial_message(message)
        expected = _BY_ID["s3-explicit-deny-identity-policy"]["expected"]
        assert outcome.value == expected["outcome_class"]
        assert attribution.value == expected["denial_attribution"]

    @pytest.mark.parametrize(
        "policy_kind",
        [
            "identity-based policy",
            "resource-based policy",
            "permissions boundary",
            "session policy",
            "service control policy",
        ],
    )
    def test_explicit_deny_recognized_across_every_documented_policy_kind(self, policy_kind):
        message = (
            f"is not authorized to perform: s3:GetObject with an explicit deny in a {policy_kind}"
        )
        outcome, attribution = classify_denial_message(message)
        assert outcome is OutcomeClass.DENIED_EXPLICIT
        assert attribution is DenialAttribution.EXPLICIT_DENY

    def test_implicit_denial_no_identity_based_policy_allows(self):
        message = _BY_ID["dynamodb-implicit-no-allow"]["response"]["message"]
        outcome, attribution = classify_denial_message(message)
        expected = _BY_ID["dynamodb-implicit-no-allow"]["expected"]
        assert outcome.value == expected["outcome_class"]
        assert attribution.value == expected["denial_attribution"]

    def test_unrecognized_message_shape_is_unattributed_not_a_guess(self):
        message = _BY_ID["s3-unattributed-deny"]["response"]["message"]
        outcome, attribution = classify_denial_message(message)
        assert outcome.value == _BY_ID["s3-unattributed-deny"]["expected"]["outcome_class"]
        assert attribution is None

    def test_empty_message_is_unattributed(self):
        outcome, attribution = classify_denial_message("")
        assert outcome is OutcomeClass.DENIED_UNATTRIBUTED
        assert attribution is None

    def test_explicit_deny_checked_before_implicit_even_if_both_phrases_present(self):
        # A pathological message containing both phrases must still resolve
        # to explicit -- the more specific, higher-confidence signal.
        message = (
            "is not authorized to perform: s3:GetObject "
            "with an explicit deny in an identity-based policy"
        )
        outcome, _ = classify_denial_message(message)
        assert outcome is OutcomeClass.DENIED_EXPLICIT

    def test_case_insensitive(self):
        message = "IS NOT AUTHORIZED TO PERFORM: s3:GetObject"
        outcome, attribution = classify_denial_message(message)
        assert outcome is OutcomeClass.DENIED_IMPLICIT
        assert attribution is DenialAttribution.IMPLICIT_NO_ALLOW


class TestLambdaFunctionFault:
    def test_populated_function_error_is_a_fault(self):
        assert is_lambda_function_fault("Unhandled") is True

    def test_empty_string_is_not_a_fault(self):
        assert is_lambda_function_fault("") is False

    def test_none_is_not_a_fault(self):
        assert is_lambda_function_fault(None) is False


class TestS3ObjectMissing:
    def test_no_such_key_is_missing(self):
        assert is_s3_object_missing("NoSuchKey", http_status=404) is True

    def test_bare_404_status_is_missing_even_with_a_different_code(self):
        assert is_s3_object_missing("SomeOtherCode", http_status=404) is True

    def test_access_denied_is_not_missing(self):
        assert is_s3_object_missing("AccessDenied", http_status=403) is False

    def test_no_status_and_unrelated_code_is_not_missing(self):
        assert is_s3_object_missing("InternalError", http_status=None) is False


class TestAccessDeniedCode:
    @pytest.mark.parametrize(
        "code", ["AccessDenied", "AccessDeniedException", "UnauthorizedException", "ExpiredToken"]
    )
    def test_recognized_codes(self, code):
        assert is_access_denied_code(code) is True

    @pytest.mark.parametrize("code", ["Throttling", "ResourceNotFoundException", ""])
    def test_unrecognized_codes(self, code):
        assert is_access_denied_code(code) is False

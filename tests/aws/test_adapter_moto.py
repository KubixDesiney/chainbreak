"""Call-shape verification against moto-backed AWS resources.

Every test here proves the AWS adapter code calls the right operation with
the right parameters and interprets the response correctly -- moto's own
policy evaluation is an approximation and is **not** ground truth (moto
does not enforce IAM allow/deny semantics the way real AWS does), so these
tests do not and cannot substitute for ``test_adapter_real.py`` against a
real account. What they do prove, for real: request/response shapes, content
verification, session-policy synthesis and attachment, lifetime capping,
the mutation choke point's read-after-write cycle, and policy snapshot
fingerprinting -- all executed against genuine boto3 clients hitting moto's
in-memory AWS emulation, not hand-built stub objects.

Lambda's ``invoke()`` uses moto's Docker-free "simple" backend
(``@mock_aws(config={"lambda": {"use_docker": False}})``): this development
environment has no Docker daemon, and moto's default Lambda backend actually
runs the deployed code inside a container. The simple backend never
executes anything; it returns whatever this test queues, which is enough to
exercise ``probes.py``'s own response-parsing branches faithfully.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import boto3
import pytest
from moto import mock_aws

from chainbreak.core.enums import DelegationMechanism, MutationKind, OutcomeClass
from chainbreak.core.ids import new_credential_id
from chainbreak.core.models import AuthoritySet, IdentityRef, PolicyMutation, Provider
from chainbreak.providers.aws import mutation as mutation_mod
from chainbreak.providers.aws import policy as policy_mod
from chainbreak.providers.aws import preflight as preflight_mod
from chainbreak.providers.aws import probes as probes_mod
from chainbreak.providers.aws import session as session_mod
from chainbreak.providers.aws.adapter import AwsProviderAdapter
from chainbreak.providers.aws.bindings import build_aws_bindings, next_hop_role_arn
from chainbreak.providers.aws.preflight import TerraformOutputs

pytestmark = pytest.mark.unit

_REGION = "us-east-1"
_ACCOUNT = "123456789012"
# Namespace already carries its own "cb-" prefix (Namespace's real pattern
# is ^cb-[0-9a-f]{8}$ -- see core/ids.py) -- resource/role names below build
# on it directly, never prepending a second literal "cb-".
_NAMESPACE = "cb-a1b2c3d4"
_EXTERNAL_ID = _NAMESPACE

_TRUST_POLICY = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"AWS": "*"}, "Action": "sts:AssumeRole"}],
    }
)


@dataclass(frozen=True, slots=True)
class MotoFixture:
    outputs: TerraformOutputs
    marker_body: bytes


def _create_agent_role(iam: Any, name: str) -> str:
    return iam.create_role(RoleName=name, AssumeRolePolicyDocument=_TRUST_POLICY)["Role"]["Arn"]


def _provision(iam: Any, s3: Any, dynamodb: Any, lambda_client: Any, sqs: Any) -> MotoFixture:
    bootstrap_arn = _create_agent_role(iam, f"{_NAMESPACE}-bootstrap")
    principal_arn = _create_agent_role(iam, f"{_NAMESPACE}-principal")
    agent_arns = {
        letter: _create_agent_role(iam, f"{_NAMESPACE}-agent-{letter}") for letter in "abcdef"
    }

    bucket = f"{_NAMESPACE}-objectstore"
    s3.create_bucket(Bucket=bucket)
    s3.put_bucket_tagging(
        Bucket=bucket,
        Tagging={
            "TagSet": [
                {"Key": "Project", "Value": "CHAINBREAK"},
                {"Key": "Namespace", "Value": _NAMESPACE},
            ]
        },
    )
    marker_key = f"{_NAMESPACE}/markers/marker.json"
    marker_body = b'{"marker": true}'
    s3.put_object(Bucket=bucket, Key=marker_key, Body=marker_body)
    marker_sha256 = "sha256:" + hashlib.sha256(marker_body).hexdigest()

    table = f"{_NAMESPACE}-keyvalue"
    dynamodb.create_table(
        TableName=table,
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    keyvalue_marker_pk = "cb-marker"
    keyvalue_marker_sha256 = "sha256:" + hashlib.sha256(b"keyvalue-marker").hexdigest()
    dynamodb.put_item(
        TableName=table,
        Item={"pk": {"S": keyvalue_marker_pk}, "digest": {"S": keyvalue_marker_sha256}},
    )

    function_name = f"{_NAMESPACE}-noop"
    lambda_client.create_function(
        FunctionName=function_name,
        Runtime="python3.12",
        Role=bootstrap_arn,
        Handler="lambda_function.handler",
        Code={"ZipFile": b"placeholder -- the simple backend never executes this"},
    )

    queue_url = sqs.create_queue(QueueName=f"{_NAMESPACE}-queue")["QueueUrl"]

    outputs = TerraformOutputs(
        namespace=_NAMESPACE,
        account_id=_ACCOUNT,
        region=_REGION,
        bootstrap_role_arn=bootstrap_arn,
        principal_role_arn=principal_arn,
        agent_role_arns=agent_arns,
        objectstore_bucket=bucket,
        objectstore_marker_key=marker_key,
        objectstore_marker_sha256=marker_sha256,
        keyvalue_table=table,
        keyvalue_marker_pk=keyvalue_marker_pk,
        keyvalue_marker_sha256=keyvalue_marker_sha256,
        function_name=function_name,
        queue_url=queue_url,
        external_id=_EXTERNAL_ID,
        infrastructure_fingerprint="sha256:" + hashlib.sha256(b"fingerprint").hexdigest(),
    )
    return MotoFixture(outputs=outputs, marker_body=marker_body)


@pytest.fixture
def moto_fixture():
    with mock_aws(config={"lambda": {"use_docker": False}}):
        iam = boto3.client("iam", region_name=_REGION)
        s3 = boto3.client("s3", region_name=_REGION)
        dynamodb = boto3.client("dynamodb", region_name=_REGION)
        lambda_client = boto3.client("lambda", region_name=_REGION)
        sqs = boto3.client("sqs", region_name=_REGION)
        fixture = _provision(iam, s3, dynamodb, lambda_client, sqs)
        yield (
            fixture,
            {"iam": iam, "s3": s3, "dynamodb": dynamodb, "lambda": lambda_client, "sqs": sqs},
        )


# ---------------------------------------------------------------------------
# preflight.py
# ---------------------------------------------------------------------------


class TestPreflight:
    def test_passes_against_a_correctly_provisioned_account(self, moto_fixture):
        fixture, clients = moto_fixture
        from chainbreak.core.models import SafetyEnvelope

        envelope = SafetyEnvelope(
            allowed_account_ids=(_ACCOUNT,),
            allowed_regions=(_REGION,),
            namespace=_NAMESPACE,
            namespace_pattern=f"^{_NAMESPACE}$",
        )
        sts = boto3.client("sts", region_name=_REGION)
        tagging = boto3.client("resourcegroupstaggingapi", region_name=_REGION)
        registry = probes_mod.build_aws_preconditions(
            s3_client=clients["s3"],
            dynamodb_client=clients["dynamodb"],
            lambda_client=clients["lambda"],
            sqs_client=clients["sqs"],
            outputs=fixture.outputs,
        )
        preconditions = probes_mod.verify_all_preconditions(
            registry,
            IdentityRef(
                provider=Provider.AWS, kind="role", value=fixture.outputs.bootstrap_role_arn
            ),
        )
        assert all(preconditions.values())
        cost_estimate = preflight_mod.CostEstimate(estimated_calls_by_service={"s3": 1})
        report = preflight_mod.run_preflight(
            sts_client=sts,
            resourcegroupstaggingapi_client=tagging,
            envelope=envelope,
            terraform_outputs=fixture.outputs,
            precondition_results=preconditions,
            cost_estimate=cost_estimate,
            clock_offset_ms=0.0,
        )
        assert report.passed is True

    def test_p2_wrong_account_raises_before_anything_else(self, moto_fixture):
        fixture, _clients = moto_fixture
        from chainbreak.core.errors import AccountNotAllowedError
        from chainbreak.core.models import SafetyEnvelope

        envelope = SafetyEnvelope(
            allowed_account_ids=("999999999999",),
            allowed_regions=(_REGION,),
            namespace=_NAMESPACE,
            namespace_pattern=f"^{_NAMESPACE}$",
        )
        sts = boto3.client("sts", region_name=_REGION)
        tagging = boto3.client("resourcegroupstaggingapi", region_name=_REGION)
        with pytest.raises(AccountNotAllowedError):
            preflight_mod.run_preflight(
                sts_client=sts,
                resourcegroupstaggingapi_client=tagging,
                envelope=envelope,
                terraform_outputs=fixture.outputs,
                precondition_results={},
                cost_estimate=preflight_mod.CostEstimate(estimated_calls_by_service={}),
                clock_offset_ms=0.0,
            )

    def test_p9_production_tagged_resource_aborts_without_override(self, moto_fixture):
        fixture, clients = moto_fixture
        from chainbreak.core.errors import ConfigurationError
        from chainbreak.core.models import SafetyEnvelope

        # put_bucket_tagging *replaces* the tag set -- the Project/Namespace
        # tags from provisioning must be included again alongside the new
        # Environment=production tag, or P7 (checked before P9) fails first.
        clients["s3"].put_bucket_tagging(
            Bucket=fixture.outputs.objectstore_bucket,
            Tagging={
                "TagSet": [
                    {"Key": "Project", "Value": "CHAINBREAK"},
                    {"Key": "Namespace", "Value": _NAMESPACE},
                    {"Key": "Environment", "Value": "production"},
                ]
            },
        )
        envelope = SafetyEnvelope(
            allowed_account_ids=(_ACCOUNT,),
            allowed_regions=(_REGION,),
            namespace=_NAMESPACE,
            namespace_pattern=f"^{_NAMESPACE}$",
        )
        sts = boto3.client("sts", region_name=_REGION)
        tagging = boto3.client("resourcegroupstaggingapi", region_name=_REGION)
        registry = probes_mod.build_aws_preconditions(
            s3_client=clients["s3"],
            dynamodb_client=clients["dynamodb"],
            lambda_client=clients["lambda"],
            sqs_client=clients["sqs"],
            outputs=fixture.outputs,
        )
        preconditions = probes_mod.verify_all_preconditions(
            registry,
            IdentityRef(
                provider=Provider.AWS, kind="role", value=fixture.outputs.bootstrap_role_arn
            ),
        )
        with pytest.raises(ConfigurationError, match="production"):
            preflight_mod.run_preflight(
                sts_client=sts,
                resourcegroupstaggingapi_client=tagging,
                envelope=envelope,
                terraform_outputs=fixture.outputs,
                precondition_results=preconditions,
                cost_estimate=preflight_mod.CostEstimate(estimated_calls_by_service={}),
                clock_offset_ms=0.0,
            )

    def test_p8_missing_marker_reports_configuration_error_not_passed(self, moto_fixture):
        fixture, clients = moto_fixture
        clients["s3"].delete_object(
            Bucket=fixture.outputs.objectstore_bucket, Key=fixture.outputs.objectstore_marker_key
        )
        registry = probes_mod.build_aws_preconditions(
            s3_client=clients["s3"],
            dynamodb_client=clients["dynamodb"],
            lambda_client=clients["lambda"],
            sqs_client=clients["sqs"],
            outputs=fixture.outputs,
        )
        preconditions = probes_mod.verify_all_preconditions(
            registry,
            IdentityRef(
                provider=Provider.AWS, kind="role", value=fixture.outputs.bootstrap_role_arn
            ),
        )
        assert preconditions["objectstore.marker_present"] is False

    def test_p1_caller_identity_failure_returns_a_failed_report_not_an_exception(
        self, moto_fixture
    ):
        fixture, _clients = moto_fixture
        from chainbreak.core.models import SafetyEnvelope

        class _BrokenStsClient:
            def get_caller_identity(self):
                from botocore.exceptions import ClientError

                raise ClientError(
                    {"Error": {"Code": "InvalidClientTokenId", "Message": "no credentials"}},
                    "GetCallerIdentity",
                )

        envelope = SafetyEnvelope(
            allowed_account_ids=(_ACCOUNT,),
            allowed_regions=(_REGION,),
            namespace=_NAMESPACE,
            namespace_pattern=f"^{_NAMESPACE}$",
        )
        tagging = boto3.client("resourcegroupstaggingapi", region_name=_REGION)
        report = preflight_mod.run_preflight(
            sts_client=_BrokenStsClient(),
            resourcegroupstaggingapi_client=tagging,
            envelope=envelope,
            terraform_outputs=fixture.outputs,
            precondition_results={},
            cost_estimate=preflight_mod.CostEstimate(estimated_calls_by_service={}),
            clock_offset_ms=0.0,
        )
        assert report.passed is False
        assert report.checks[0].name == "caller_identity"
        assert report.checks[0].passed is False

    def test_p3_wrong_region_raises(self, moto_fixture):
        fixture, _clients = moto_fixture
        from chainbreak.core.errors import RegionNotAllowedError
        from chainbreak.core.models import SafetyEnvelope

        envelope = SafetyEnvelope(
            allowed_account_ids=(_ACCOUNT,),
            allowed_regions=("eu-west-1",),
            namespace=_NAMESPACE,
            namespace_pattern=f"^{_NAMESPACE}$",
        )
        sts = boto3.client("sts", region_name=_REGION)
        tagging = boto3.client("resourcegroupstaggingapi", region_name=_REGION)
        with pytest.raises(RegionNotAllowedError):
            preflight_mod.run_preflight(
                sts_client=sts,
                resourcegroupstaggingapi_client=tagging,
                envelope=envelope,
                terraform_outputs=fixture.outputs,
                precondition_results={},
                cost_estimate=preflight_mod.CostEstimate(estimated_calls_by_service={}),
                clock_offset_ms=0.0,
            )

    def test_p4_wrong_partition_raises(self, moto_fixture):
        fixture, _clients = moto_fixture
        from chainbreak.core.errors import ConfigurationError
        from chainbreak.core.models import SafetyEnvelope

        envelope = SafetyEnvelope(
            allowed_account_ids=(_ACCOUNT,),
            allowed_regions=(_REGION,),
            namespace=_NAMESPACE,
            namespace_pattern=f"^{_NAMESPACE}$",
        )
        sts = boto3.client("sts", region_name=_REGION)
        tagging = boto3.client("resourcegroupstaggingapi", region_name=_REGION)
        with pytest.raises(ConfigurationError, match="partition"):
            preflight_mod.run_preflight(
                sts_client=sts,
                resourcegroupstaggingapi_client=tagging,
                envelope=envelope,
                terraform_outputs=fixture.outputs,
                precondition_results={},
                cost_estimate=preflight_mod.CostEstimate(estimated_calls_by_service={}),
                clock_offset_ms=0.0,
                partition="aws-us-gov",
            )

    def test_p6_bad_arn_shape_raises(self, moto_fixture):
        fixture, _clients = moto_fixture
        import dataclasses

        from chainbreak.core.errors import ConfigurationError
        from chainbreak.core.models import SafetyEnvelope

        bad_outputs = dataclasses.replace(
            fixture.outputs,
            bootstrap_role_arn="arn:aws:iam::123456789012:role/not-namespaced",
        )
        envelope = SafetyEnvelope(
            allowed_account_ids=(_ACCOUNT,),
            allowed_regions=(_REGION,),
            namespace=_NAMESPACE,
            namespace_pattern=f"^{_NAMESPACE}$",
        )
        sts = boto3.client("sts", region_name=_REGION)
        tagging = boto3.client("resourcegroupstaggingapi", region_name=_REGION)
        with pytest.raises(ConfigurationError, match="ARN"):
            preflight_mod.run_preflight(
                sts_client=sts,
                resourcegroupstaggingapi_client=tagging,
                envelope=envelope,
                terraform_outputs=bad_outputs,
                precondition_results={},
                cost_estimate=preflight_mod.CostEstimate(estimated_calls_by_service={}),
                clock_offset_ms=0.0,
            )

    def test_p10_estimated_cost_over_ceiling_raises(self, moto_fixture):
        fixture, clients = moto_fixture
        from chainbreak.core.errors import ConfigurationError
        from chainbreak.core.models import SafetyEnvelope

        envelope = SafetyEnvelope(
            allowed_account_ids=(_ACCOUNT,),
            allowed_regions=(_REGION,),
            namespace=_NAMESPACE,
            namespace_pattern=f"^{_NAMESPACE}$",
            max_estimated_cost_usd=0.0001,
        )
        sts = boto3.client("sts", region_name=_REGION)
        tagging = boto3.client("resourcegroupstaggingapi", region_name=_REGION)
        registry = probes_mod.build_aws_preconditions(
            s3_client=clients["s3"],
            dynamodb_client=clients["dynamodb"],
            lambda_client=clients["lambda"],
            sqs_client=clients["sqs"],
            outputs=fixture.outputs,
        )
        preconditions = probes_mod.verify_all_preconditions(
            registry,
            IdentityRef(
                provider=Provider.AWS, kind="role", value=fixture.outputs.bootstrap_role_arn
            ),
        )
        with pytest.raises(ConfigurationError, match="estimated cost"):
            preflight_mod.run_preflight(
                sts_client=sts,
                resourcegroupstaggingapi_client=tagging,
                envelope=envelope,
                terraform_outputs=fixture.outputs,
                precondition_results=preconditions,
                cost_estimate=preflight_mod.CostEstimate(estimated_calls_by_service={"s3": 1000}),
                clock_offset_ms=0.0,
            )


# ---------------------------------------------------------------------------
# session.py
# ---------------------------------------------------------------------------


class TestSession:
    def test_direct_role_assumption_issues_a_live_credential(self, moto_fixture):
        fixture, _clients = moto_fixture
        sts = boto3.client("sts", region_name=_REGION)
        bindings = {
            b.capability_id: b
            for b in build_aws_bindings(build_catalog(), account_id=_ACCOUNT, region=_REGION)
        }
        result = session_mod.assume_role(
            sts,
            role_arn=fixture.outputs.agent_role_arns["a"],
            session_name="cb-test-session",
            external_id=_EXTERNAL_ID,
            requested_duration_s=900,
            mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
            intended_capabilities=AuthoritySet.of("objectstore.read"),
            bindings=bindings,
            namespace=_NAMESPACE,
            target_identity_id="agent-a",
            identity_ref=IdentityRef(
                provider=Provider.AWS, kind="role", value=fixture.outputs.agent_role_arns["a"]
            ),
            credential_id=new_credential_id(),
            salt="test-salt:",
        )
        assert result.record.requested_duration_s == 900
        assert result.record.granted_duration_s == 900
        assert result.record.lifetime_capped is False
        assert len(result.credential.secret_access_key.reveal()) > 0

    def test_role_chain_caps_at_3600_seconds(self, moto_fixture):
        fixture, _clients = moto_fixture
        sts = boto3.client("sts", region_name=_REGION)
        bindings = {
            b.capability_id: b
            for b in build_aws_bindings(build_catalog(), account_id=_ACCOUNT, region=_REGION)
        }
        result = session_mod.assume_role(
            sts,
            role_arn=fixture.outputs.agent_role_arns["b"],
            session_name="cb-test-chain",
            external_id=_EXTERNAL_ID,
            requested_duration_s=7200,
            mechanism=DelegationMechanism.ROLE_CHAIN,
            intended_capabilities=AuthoritySet.of("objectstore.read"),
            bindings=bindings,
            namespace=_NAMESPACE,
            target_identity_id="agent-b",
            identity_ref=IdentityRef(
                provider=Provider.AWS, kind="role", value=fixture.outputs.agent_role_arns["b"]
            ),
            credential_id=new_credential_id(),
            salt="test-salt:",
        )
        assert result.record.requested_duration_s == 7200
        assert result.record.granted_duration_s == 3600
        assert result.record.lifetime_capped is True

    def test_session_policy_scoped_attaches_a_synthesized_policy(self, moto_fixture):
        fixture, _clients = moto_fixture
        sts = boto3.client("sts", region_name=_REGION)
        bindings = {
            b.capability_id: b
            for b in build_aws_bindings(build_catalog(), account_id=_ACCOUNT, region=_REGION)
        }
        result = session_mod.assume_role(
            sts,
            role_arn=fixture.outputs.agent_role_arns["c"],
            session_name="cb-test-scoped",
            external_id=_EXTERNAL_ID,
            requested_duration_s=900,
            mechanism=DelegationMechanism.SESSION_POLICY_SCOPED,
            intended_capabilities=AuthoritySet.of("objectstore.read"),
            bindings=bindings,
            namespace=_NAMESPACE,
            target_identity_id="agent-c",
            identity_ref=IdentityRef(
                provider=Provider.AWS, kind="role", value=fixture.outputs.agent_role_arns["c"]
            ),
            credential_id=new_credential_id(),
            salt="test-salt:",
        )
        assert result.record.session_policy_fingerprint is not None
        assert result.record.scope_capabilities == AuthoritySet.of("objectstore.read")

    def test_boto3_session_from_credential_is_directly_usable(self, moto_fixture):
        fixture, _clients = moto_fixture
        sts = boto3.client("sts", region_name=_REGION)
        bindings = {
            b.capability_id: b
            for b in build_aws_bindings(build_catalog(), account_id=_ACCOUNT, region=_REGION)
        }
        result = session_mod.assume_role(
            sts,
            role_arn=fixture.outputs.agent_role_arns["d"],
            session_name="cb-test-live",
            external_id=_EXTERNAL_ID,
            requested_duration_s=900,
            mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
            intended_capabilities=AuthoritySet.of("identity.whoami"),
            bindings=bindings,
            namespace=_NAMESPACE,
            target_identity_id="agent-d",
            identity_ref=IdentityRef(
                provider=Provider.AWS, kind="role", value=fixture.outputs.agent_role_arns["d"]
            ),
            credential_id=new_credential_id(),
            salt="test-salt:",
        )
        live_session = session_mod.boto3_session_from_credential(result.credential, region=_REGION)
        identity = live_session.client("sts", region_name=_REGION).get_caller_identity()
        assert "agent-d" in identity["Arn"] or result.credential.access_key_id in identity.get(
            "UserId", ""
        )


def build_catalog():
    from chainbreak.capabilities.loader import load_catalog

    return load_catalog()


class TestNextHopRoleArn:
    def test_principal_next_hop_is_agent_a(self):
        arn = next_hop_role_arn("principal", account_id=_ACCOUNT, namespace=_NAMESPACE)
        assert arn == f"arn:aws:iam::{_ACCOUNT}:role/{_NAMESPACE}-agent-a"

    def test_bootstrap_has_no_next_hop(self):
        assert next_hop_role_arn("bootstrap", account_id=_ACCOUNT, namespace=_NAMESPACE) is None

    def test_agent_f_the_chains_final_link_has_no_next_hop(self):
        assert next_hop_role_arn("agent-f", account_id=_ACCOUNT, namespace=_NAMESPACE) is None

    def test_agent_b_next_hop_is_agent_c(self):
        arn = next_hop_role_arn("agent-b", account_id=_ACCOUNT, namespace=_NAMESPACE)
        assert arn == f"arn:aws:iam::{_ACCOUNT}:role/{_NAMESPACE}-agent-c"


# ---------------------------------------------------------------------------
# probes.py
# ---------------------------------------------------------------------------


class TestProbes:
    def test_objectstore_read_content_verified(self, moto_fixture):
        fixture, clients = moto_fixture
        outcome = probes_mod.probe_objectstore_read(clients["s3"], outputs=fixture.outputs)
        assert outcome.outcome_class is OutcomeClass.ALLOWED

    def test_objectstore_read_digest_mismatch_is_infrastructure_error(self, moto_fixture):
        fixture, clients = moto_fixture
        clients["s3"].put_object(
            Bucket=fixture.outputs.objectstore_bucket,
            Key=fixture.outputs.objectstore_marker_key,
            Body=b"tampered",
        )
        outcome = probes_mod.probe_objectstore_read(clients["s3"], outputs=fixture.outputs)
        assert outcome.outcome_class is OutcomeClass.ERROR_INFRASTRUCTURE
        assert outcome.disambiguation_path == "objectstore.read:content_mismatch"

    def test_objectstore_write_confirmed(self, moto_fixture):
        fixture, clients = moto_fixture
        outcome = probes_mod.probe_objectstore_write(
            clients["s3"], outputs=fixture.outputs, run_id="run1", probe_id="p1", nonce="abc123"
        )
        assert outcome.outcome_class is OutcomeClass.ALLOWED

    def test_objectstore_list_finds_the_marker_prefix(self, moto_fixture):
        fixture, clients = moto_fixture
        outcome = probes_mod.probe_objectstore_list(clients["s3"], outputs=fixture.outputs)
        assert outcome.outcome_class is OutcomeClass.ALLOWED

    def test_objectstore_list_empty_despite_precondition_is_infrastructure_error(
        self, moto_fixture
    ):
        fixture, clients = moto_fixture
        clients["s3"].delete_object(
            Bucket=fixture.outputs.objectstore_bucket, Key=fixture.outputs.objectstore_marker_key
        )
        outcome = probes_mod.probe_objectstore_list(clients["s3"], outputs=fixture.outputs)
        assert outcome.outcome_class is OutcomeClass.ERROR_INFRASTRUCTURE
        assert outcome.disambiguation_path == "objectstore.list:unexpected_empty_after_precondition"

    def test_keyvalue_read_missing_item_despite_precondition_is_infrastructure_error(
        self, moto_fixture
    ):
        fixture, clients = moto_fixture
        clients["dynamodb"].delete_item(
            TableName=fixture.outputs.keyvalue_table,
            Key={"pk": {"S": fixture.outputs.keyvalue_marker_pk}},
        )
        outcome = probes_mod.probe_keyvalue_read(clients["dynamodb"], outputs=fixture.outputs)
        assert outcome.outcome_class is OutcomeClass.ERROR_INFRASTRUCTURE
        assert outcome.disambiguation_path == "keyvalue.read:unexpected_missing_after_precondition"

    def test_keyvalue_read_digest_mismatch_is_infrastructure_error(self, moto_fixture):
        fixture, clients = moto_fixture
        clients["dynamodb"].put_item(
            TableName=fixture.outputs.keyvalue_table,
            Item={
                "pk": {"S": fixture.outputs.keyvalue_marker_pk},
                "digest": {"S": "sha256:" + "f" * 64},
            },
        )
        outcome = probes_mod.probe_keyvalue_read(clients["dynamodb"], outputs=fixture.outputs)
        assert outcome.outcome_class is OutcomeClass.ERROR_INFRASTRUCTURE
        assert outcome.disambiguation_path == "keyvalue.read:content_mismatch"

    def test_classify_denial_of_an_unrelated_error_code_is_infrastructure_not_a_denial(self):
        from botocore.exceptions import ClientError

        exc = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "bad request"}}, "GetObject"
        )
        outcome = probes_mod.classify_denial(exc, path="objectstore.read")
        assert outcome.outcome_class is OutcomeClass.ERROR_INFRASTRUCTURE
        assert outcome.disambiguation_path == "objectstore.read:unexpected_error"

    def test_precondition_verifiers_return_false_for_missing_resources(self, moto_fixture):
        fixture, clients = moto_fixture
        clients["dynamodb"].delete_table(TableName=fixture.outputs.keyvalue_table)
        registry = probes_mod.build_aws_preconditions(
            s3_client=clients["s3"],
            dynamodb_client=clients["dynamodb"],
            lambda_client=clients["lambda"],
            sqs_client=clients["sqs"],
            outputs=fixture.outputs,
        )
        assert (
            registry.verify(
                "keyvalue.marker_present",
                IdentityRef(provider=Provider.AWS, kind="role", value="x"),
            )
            is False
        )

    def test_objectstore_read_access_denied_classified_via_disambiguation(self, moto_fixture):
        fixture, clients = moto_fixture
        from botocore.exceptions import ClientError

        real_get_object = clients["s3"].get_object

        def _denying_get_object(**kwargs):
            raise ClientError(
                {
                    "Error": {
                        "Code": "AccessDenied",
                        "Message": (
                            "User: arn:aws:sts::123456789012:assumed-role/cb-test0001-agent-a/s "
                            "is not authorized to perform: s3:GetObject on resource: x "
                            "with an explicit deny in an identity-based policy"
                        ),
                    },
                    "ResponseMetadata": {"HTTPStatusCode": 403},
                },
                "GetObject",
            )

        clients["s3"].get_object = _denying_get_object
        try:
            with pytest.raises(ClientError) as exc_info:
                probes_mod.probe_objectstore_read(clients["s3"], outputs=fixture.outputs)
            outcome = probes_mod.classify_denial(exc_info.value, path="objectstore.read")
        finally:
            clients["s3"].get_object = real_get_object
        assert outcome.outcome_class is OutcomeClass.DENIED_EXPLICIT

    def test_keyvalue_read_content_verified(self, moto_fixture):
        fixture, clients = moto_fixture
        outcome = probes_mod.probe_keyvalue_read(clients["dynamodb"], outputs=fixture.outputs)
        assert outcome.outcome_class is OutcomeClass.ALLOWED

    def test_keyvalue_write_confirmed(self, moto_fixture):
        fixture, clients = moto_fixture
        outcome = probes_mod.probe_keyvalue_write(
            clients["dynamodb"], outputs=fixture.outputs, run_id="run1", probe_id="p1", nonce="xyz"
        )
        assert outcome.outcome_class is OutcomeClass.ALLOWED

    def test_queue_send_and_receive(self, moto_fixture):
        fixture, clients = moto_fixture
        send_outcome = probes_mod.probe_queue_send(
            clients["sqs"], outputs=fixture.outputs, nonce="n1"
        )
        assert send_outcome.outcome_class is OutcomeClass.ALLOWED
        receive_outcome = probes_mod.probe_queue_receive(clients["sqs"], outputs=fixture.outputs)
        assert receive_outcome.outcome_class is OutcomeClass.ALLOWED

    def test_queue_receive_allowed_even_when_empty(self, moto_fixture):
        fixture, clients = moto_fixture
        outcome = probes_mod.probe_queue_receive(clients["sqs"], outputs=fixture.outputs)
        assert outcome.outcome_class is OutcomeClass.ALLOWED

    def test_identity_whoami_allowed(self, moto_fixture):
        sts = boto3.client("sts", region_name=_REGION)
        outcome = probes_mod.probe_identity_whoami(sts)
        assert outcome.outcome_class is OutcomeClass.ALLOWED

    def test_identity_delegate_succeeds_against_the_next_hop(self, moto_fixture):
        sts = boto3.client("sts", region_name=_REGION)
        next_hop = next_hop_role_arn("agent-a", account_id=_ACCOUNT, namespace=_NAMESPACE)
        outcome = probes_mod.probe_identity_delegate(
            sts, next_hop_role_arn=next_hop, external_id=_EXTERNAL_ID
        )
        assert outcome.outcome_class is OutcomeClass.ALLOWED

    def test_identity_delegate_no_next_hop_for_the_last_chain_link(self):
        outcome = probes_mod.probe_identity_delegate(
            None, next_hop_role_arn=None, external_id=_EXTERNAL_ID
        )
        assert outcome.outcome_class is OutcomeClass.ERROR_INFRASTRUCTURE
        assert outcome.disambiguation_path == "identity.delegate:no_next_hop"

    def test_function_invoke_payload_verified_via_simple_lambda_backend(self, moto_fixture):
        fixture, clients = moto_fixture
        from moto.awslambda_simple.models import lambda_simple_backends

        backend = lambda_simple_backends[_ACCOUNT][_REGION]
        backend.lambda_simple_results_queue.append(
            json.dumps({"ok": True, "nonce": fixture.outputs.namespace})
        )
        outcome = probes_mod.probe_function_invoke(clients["lambda"], outputs=fixture.outputs)
        assert outcome.outcome_class is OutcomeClass.ALLOWED

    def test_function_invoke_unexpected_payload_is_infrastructure_error(self, moto_fixture):
        fixture, clients = moto_fixture
        from moto.awslambda_simple.models import lambda_simple_backends

        backend = lambda_simple_backends[_ACCOUNT][_REGION]
        backend.lambda_simple_results_queue.append(json.dumps({"unexpected": "shape"}))
        outcome = probes_mod.probe_function_invoke(clients["lambda"], outputs=fixture.outputs)
        assert outcome.outcome_class is OutcomeClass.ERROR_INFRASTRUCTURE

    def test_function_invoke_function_error_is_a_fault_not_a_denial(self):
        """A ``FunctionError``-carrying response never reaches moto's queue
        mechanism (the simple backend "always succeeds"), so this uses a
        minimal stub client -- proving ``probes.py``'s own branch, not
        moto's Lambda emulation."""
        import io

        class _StubLambdaClient:
            def invoke(self, **kwargs):
                return {
                    "StatusCode": 200,
                    "FunctionError": "Unhandled",
                    "Payload": io.BytesIO(b"{}"),
                }

        outputs = TerraformOutputs(
            namespace=_NAMESPACE,
            account_id=_ACCOUNT,
            region=_REGION,
            bootstrap_role_arn="x",
            principal_role_arn="x",
            agent_role_arns={},
            objectstore_bucket="x",
            objectstore_marker_key="x",
            objectstore_marker_sha256="sha256:" + "0" * 64,
            keyvalue_table="x",
            keyvalue_marker_pk="x",
            keyvalue_marker_sha256="sha256:" + "0" * 64,
            function_name="cb-test0001-noop",
            queue_url="x",
            external_id="x",
            infrastructure_fingerprint="sha256:" + "0" * 64,
        )
        outcome = probes_mod.probe_function_invoke(_StubLambdaClient(), outputs=outputs)
        assert outcome.outcome_class is OutcomeClass.ERROR_INFRASTRUCTURE
        assert outcome.disambiguation_path == "function.invoke:function_fault"


# ---------------------------------------------------------------------------
# mutation.py
# ---------------------------------------------------------------------------


class TestMutation:
    def test_attach_inline_deny_is_confirmed(self, moto_fixture):
        fixture, clients = moto_fixture
        bindings = {
            b.capability_id: b
            for b in build_aws_bindings(build_catalog(), account_id=_ACCOUNT, region=_REGION)
        }
        receipt = mutation_mod.apply_mutation(
            clients["iam"],
            PolicyMutation(
                mutation_id="m1",
                kind=MutationKind.ATTACH_INLINE_DENY,
                target_identity="agent-a",
                denies_capabilities=AuthoritySet.of("objectstore.read"),
            ),
            outputs=fixture.outputs,
            bindings=bindings,
            namespace=_NAMESPACE,
            sleep=lambda _s: None,
        )
        assert receipt.confirmed is True
        assert receipt.confirmation_method == "read_after_write"
        doc = clients["iam"].get_role_policy(
            RoleName=f"{_NAMESPACE}-agent-a", PolicyName=mutation_mod.DENY_POLICY_NAME
        )
        assert doc["PolicyDocument"]["Statement"][0]["Effect"] == "Deny"

    def test_replace_inline_policy_combines_deny_and_grant_statements(self, moto_fixture):
        fixture, clients = moto_fixture
        bindings = {
            b.capability_id: b
            for b in build_aws_bindings(build_catalog(), account_id=_ACCOUNT, region=_REGION)
        }
        receipt = mutation_mod.apply_mutation(
            clients["iam"],
            PolicyMutation(
                mutation_id="m-replace",
                kind=MutationKind.REPLACE_INLINE_POLICY,
                target_identity="agent-a",
                denies_capabilities=AuthoritySet.of("objectstore.read"),
                grants_capabilities=AuthoritySet.of("queue.send"),
            ),
            outputs=fixture.outputs,
            bindings=bindings,
            namespace=_NAMESPACE,
            sleep=lambda _s: None,
        )
        assert receipt.confirmed is True
        doc = clients["iam"].get_role_policy(
            RoleName=f"{_NAMESPACE}-agent-a", PolicyName=mutation_mod.DENY_POLICY_NAME
        )["PolicyDocument"]
        effects = {s["Sid"]: s["Effect"] for s in doc["Statement"]}
        assert effects["CbDeny"] == "Deny"
        assert effects["CbGrant"] == "Allow"

    def test_role_arn_for_identity_unknown_identity_raises(self, moto_fixture):
        fixture, _clients = moto_fixture
        from chainbreak.core.errors import MutationTargetForbiddenError

        with pytest.raises(MutationTargetForbiddenError):
            mutation_mod.role_arn_for_identity("agent-not-real", fixture.outputs)

    def test_refuses_to_mutate_bootstrap(self, moto_fixture):
        fixture, clients = moto_fixture
        from chainbreak.core.errors import MutationTargetForbiddenError

        bindings = {
            b.capability_id: b
            for b in build_aws_bindings(build_catalog(), account_id=_ACCOUNT, region=_REGION)
        }
        with pytest.raises(MutationTargetForbiddenError):
            mutation_mod.apply_mutation(
                clients["iam"],
                PolicyMutation(
                    mutation_id="m2",
                    kind=MutationKind.ATTACH_INLINE_DENY,
                    target_identity="bootstrap",
                    denies_capabilities=AuthoritySet.of("objectstore.read"),
                ),
                outputs=fixture.outputs,
                bindings=bindings,
                namespace=_NAMESPACE,
                sleep=lambda _s: None,
            )

    def test_refuses_to_mutate_principal(self, moto_fixture):
        fixture, clients = moto_fixture
        from chainbreak.core.errors import MutationTargetForbiddenError

        bindings = {
            b.capability_id: b
            for b in build_aws_bindings(build_catalog(), account_id=_ACCOUNT, region=_REGION)
        }
        with pytest.raises(MutationTargetForbiddenError):
            mutation_mod.apply_mutation(
                clients["iam"],
                PolicyMutation(
                    mutation_id="m3",
                    kind=MutationKind.ATTACH_INLINE_DENY,
                    target_identity="principal",
                    denies_capabilities=AuthoritySet.of("objectstore.read"),
                ),
                outputs=fixture.outputs,
                bindings=bindings,
                namespace=_NAMESPACE,
                sleep=lambda _s: None,
            )

    def test_remove_inline_policy_deletes_the_grant(self, moto_fixture):
        fixture, clients = moto_fixture
        clients["iam"].put_role_policy(
            RoleName=f"{_NAMESPACE}-agent-b",
            PolicyName=mutation_mod.GRANT_POLICY_NAME,
            PolicyDocument=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "Baseline",
                            "Effect": "Allow",
                            "Action": "s3:GetObject",
                            "Resource": "*",
                        }
                    ],
                }
            ),
        )
        bindings = {
            b.capability_id: b
            for b in build_aws_bindings(build_catalog(), account_id=_ACCOUNT, region=_REGION)
        }
        receipt = mutation_mod.apply_mutation(
            clients["iam"],
            PolicyMutation(
                mutation_id="m4", kind=MutationKind.REMOVE_INLINE_POLICY, target_identity="agent-b"
            ),
            outputs=fixture.outputs,
            bindings=bindings,
            namespace=_NAMESPACE,
            sleep=lambda _s: None,
        )
        assert receipt.confirmed is True
        names = clients["iam"].list_role_policies(RoleName=f"{_NAMESPACE}-agent-b")["PolicyNames"]
        assert mutation_mod.GRANT_POLICY_NAME not in names

    def test_remove_inline_policy_on_an_already_absent_grant_is_a_harmless_no_op(
        self, moto_fixture
    ):
        fixture, clients = moto_fixture
        bindings = {
            b.capability_id: b
            for b in build_aws_bindings(build_catalog(), account_id=_ACCOUNT, region=_REGION)
        }
        receipt = mutation_mod.apply_mutation(
            clients["iam"],
            PolicyMutation(
                mutation_id="m5", kind=MutationKind.REMOVE_INLINE_POLICY, target_identity="agent-c"
            ),
            outputs=fixture.outputs,
            bindings=bindings,
            namespace=_NAMESPACE,
            sleep=lambda _s: None,
        )
        assert receipt.confirmed is True

    def test_update_trust_policy_appends_a_deny_statement(self, moto_fixture):
        fixture, clients = moto_fixture
        bindings = {
            b.capability_id: b
            for b in build_aws_bindings(build_catalog(), account_id=_ACCOUNT, region=_REGION)
        }
        receipt = mutation_mod.apply_mutation(
            clients["iam"],
            PolicyMutation(
                mutation_id="m6", kind=MutationKind.UPDATE_TRUST_POLICY, target_identity="agent-d"
            ),
            outputs=fixture.outputs,
            bindings=bindings,
            namespace=_NAMESPACE,
            sleep=lambda _s: None,
        )
        assert receipt.confirmed is True
        trust = clients["iam"].get_role(RoleName=f"{_NAMESPACE}-agent-d")["Role"][
            "AssumeRolePolicyDocument"
        ]
        assert any(s.get("Sid") == "CbRevokeFutureAssumeRole" for s in trust["Statement"])

    def test_revoke_older_sessions_writes_a_token_issue_time_deny(self, moto_fixture):
        fixture, clients = moto_fixture
        bindings = {
            b.capability_id: b
            for b in build_aws_bindings(build_catalog(), account_id=_ACCOUNT, region=_REGION)
        }
        receipt = mutation_mod.apply_mutation(
            clients["iam"],
            PolicyMutation(
                mutation_id="m7", kind=MutationKind.REVOKE_OLDER_SESSIONS, target_identity="agent-e"
            ),
            outputs=fixture.outputs,
            bindings=bindings,
            namespace=_NAMESPACE,
            sleep=lambda _s: None,
        )
        assert receipt.confirmed is True
        doc = clients["iam"].get_role_policy(
            RoleName=f"{_NAMESPACE}-agent-e", PolicyName=mutation_mod.REVOKE_OLDER_POLICY_NAME
        )["PolicyDocument"]
        assert "aws:TokenIssueTime" in doc["Statement"][0]["Condition"]["DateLessThan"]

    def test_delete_session_policy_scope_makes_no_aws_call(self, moto_fixture):
        fixture, clients = moto_fixture
        bindings = {
            b.capability_id: b
            for b in build_aws_bindings(build_catalog(), account_id=_ACCOUNT, region=_REGION)
        }
        receipt = mutation_mod.apply_mutation(
            clients["iam"],
            PolicyMutation(
                mutation_id="m8",
                kind=MutationKind.DELETE_SESSION_POLICY_SCOPE,
                target_identity="agent-f",
            ),
            outputs=fixture.outputs,
            bindings=bindings,
            namespace=_NAMESPACE,
            sleep=lambda _s: None,
        )
        assert receipt.confirmed is True
        assert receipt.confirmation_method == "api_ack_only"


# ---------------------------------------------------------------------------
# policy.py
# ---------------------------------------------------------------------------


class TestPolicySnapshot:
    def test_snapshot_includes_inline_and_trust_fingerprints(self, moto_fixture):
        fixture, clients = moto_fixture
        snapshot = policy_mod.snapshot_policy_state(
            clients["iam"], "agent-a", outputs=fixture.outputs, salt="test-salt:", now_ns=1
        )
        assert any(p.policy_kind.value == "TRUST" for p in snapshot.policies)

    def test_snapshot_changes_after_a_mutation(self, moto_fixture):
        fixture, clients = moto_fixture
        bindings = {
            b.capability_id: b
            for b in build_aws_bindings(build_catalog(), account_id=_ACCOUNT, region=_REGION)
        }
        before = policy_mod.snapshot_policy_state(
            clients["iam"], "agent-a", outputs=fixture.outputs, salt="test-salt:", now_ns=1
        )
        mutation_mod.apply_mutation(
            clients["iam"],
            PolicyMutation(
                mutation_id="m9",
                kind=MutationKind.ATTACH_INLINE_DENY,
                target_identity="agent-a",
                denies_capabilities=AuthoritySet.of("objectstore.write"),
            ),
            outputs=fixture.outputs,
            bindings=bindings,
            namespace=_NAMESPACE,
            sleep=lambda _s: None,
        )
        after = policy_mod.snapshot_policy_state(
            clients["iam"], "agent-a", outputs=fixture.outputs, salt="test-salt:", now_ns=2
        )
        assert before.differs_from(after)


# ---------------------------------------------------------------------------
# adapter.py -- end to end through the Protocol surface
# ---------------------------------------------------------------------------


class TestAdapterEndToEnd:
    def test_register_delegate_probe_mutate_snapshot(self, moto_fixture):
        fixture, _clients = moto_fixture
        operator_session = boto3.Session(region_name=_REGION)
        adapter = AwsProviderAdapter(
            operator_session=operator_session, outputs=fixture.outputs, run_id="run-e2e-1"
        )

        assert adapter.name == "aws"
        assert adapter.describe_environment().namespace == _NAMESPACE

        from chainbreak.core.models import SafetyEnvelope

        envelope = SafetyEnvelope(
            allowed_account_ids=(_ACCOUNT,),
            allowed_regions=(_REGION,),
            namespace=_NAMESPACE,
            namespace_pattern=f"^{_NAMESPACE}$",
        )
        preflight_report = adapter.preflight(envelope)
        assert preflight_report.passed is True

        principal = adapter.register_identity("principal")
        from chainbreak.providers.base.types import DelegationRequest

        delegation = adapter.delegate(
            DelegationRequest(
                source_identity=principal,
                target_identity_id="agent-a",
                mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
                requested_duration_s=900,
                intended_capabilities=AuthoritySet.of("identity.whoami", "objectstore.read"),
            )
        )
        assert delegation.record.lifetime_capped is False

        from chainbreak.providers.base.types import ProbeRequest

        whoami_result = adapter.probe(
            ProbeRequest(
                identity_ref=delegation.identity_ref,
                capability_id="identity.whoami",
                binding=adapter.resolve_capability("identity.whoami"),
                namespace=_NAMESPACE,
            )
        )
        assert whoami_result.outcome.outcome_class is OutcomeClass.ALLOWED
        assert whoami_result.timing.attempt_number == 1

        read_result = adapter.probe(
            ProbeRequest(
                identity_ref=delegation.identity_ref,
                capability_id="objectstore.read",
                binding=adapter.resolve_capability("objectstore.read"),
                namespace=_NAMESPACE,
            )
        )
        assert read_result.outcome.outcome_class is OutcomeClass.ALLOWED

        receipt = adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="e2e-1",
                kind=MutationKind.ATTACH_INLINE_DENY,
                target_identity="agent-a",
                denies_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        assert receipt.confirmed is True

        snapshot = adapter.snapshot_policy_state(delegation.identity_ref)
        assert snapshot.identity_id == "agent-a"

    def test_register_identity_rejects_an_unrecognized_name(self, moto_fixture):
        fixture, _clients = moto_fixture
        from chainbreak.core.errors import DelegationError

        operator_session = boto3.Session(region_name=_REGION)
        adapter = AwsProviderAdapter(
            operator_session=operator_session, outputs=fixture.outputs, run_id="run-e2e-2"
        )
        with pytest.raises(DelegationError):
            adapter.register_identity("agent-denied")

    def test_resolve_capability_unknown_id_raises(self, moto_fixture):
        fixture, _clients = moto_fixture
        from chainbreak.core.errors import CapabilityResolutionError

        operator_session = boto3.Session(region_name=_REGION)
        adapter = AwsProviderAdapter(
            operator_session=operator_session, outputs=fixture.outputs, run_id="run-e2e-3"
        )
        with pytest.raises(CapabilityResolutionError):
            adapter.resolve_capability("nonexistent.capability")

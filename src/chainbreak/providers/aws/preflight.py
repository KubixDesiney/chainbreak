"""Preflight: the gate before a single benchmark API call happens
(AWS_PROVIDER_SPEC section 2, P1-P11 in order).

P2 -- the resolved account matches the operator's allowlist -- is, in the
spec's own words, "the single most important line of code in the project."
It and P1 are checked first and raise immediately on failure, before any
other check runs and before any other AWS call is made; the botocore call
log a caller passes in is expected to contain exactly one entry
(``GetCallerIdentity``) when P2 fails, which is what
``tests/aws/test_adapter_real.py`` asserts against a real account.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from botocore.exceptions import ClientError

from chainbreak.core.enums import DelegationMechanism
from chainbreak.core.errors import AccountNotAllowedError, ConfigurationError, RegionNotAllowedError
from chainbreak.core.models import SafetyEnvelope
from chainbreak.providers.aws.namespace import assert_aws_reference
from chainbreak.providers.base.types import PreflightCheck, PreflightReport

#: Terraform output names required by AWS_PROVIDER_SPEC section 8. A missing
#: name is P5's own failure mode, checked as one bounded set rather than
#: accessed lazily so a later stage never discovers the gap mid-run.
_REQUIRED_OUTPUT_NAMES: tuple[str, ...] = (
    "namespace",
    "account_id",
    "region",
    "bootstrap_role_arn",
    "principal_role_arn",
    *(f"agent_{letter}_role_arn" for letter in "abcdef"),
    "objectstore_bucket",
    "objectstore_marker_key",
    "objectstore_marker_sha256",
    "keyvalue_table",
    "keyvalue_marker_pk",
    "keyvalue_marker_sha256",
    "function_name",
    "queue_url",
    "external_id",
    "infrastructure_fingerprint",
)

#: P6's ARN shape.  Account and exact namespace binding are checked below;
#: this remains a readable diagnostic for malformed Terraform output.
_BENCHMARK_ARN_RE = re.compile(
    r"^arn:aws:[a-z0-9-]+:[a-z0-9-]*:(?:\d{12})?:.*"
    r"(?<![0-9a-z])cb-[0-9a-z]{8}(?![0-9a-z])"
)

#: A conservative, static per-probe-class cost estimate in USD (P10),
#: derived from AWS_PROVIDER_SPEC section 9's per-suite cost table divided by
#: its assumed probe counts, rounded up. Deliberately pessimistic: P10 exists
#: to catch a misconfigured, much-larger-than-intended run before it starts,
#: not to model AWS pricing precisely.
ESTIMATED_COST_PER_CALL_USD: Mapping[str, float] = {
    "sts": 0.0,
    "iam": 0.0,
    "s3": 0.0001,
    "dynamodb": 0.0001,
    "lambda": 0.0,
    "sqs": 0.0,
}


@dataclass(frozen=True, slots=True)
class TerraformOutputs:
    """The stable contract Terraform must produce (AWS_PROVIDER_SPEC
    section 8). Adding an output is additive; removing or renaming one is a
    breaking ``infrastructure_profile`` version bump."""

    namespace: str
    account_id: str
    region: str
    bootstrap_role_arn: str
    principal_role_arn: str
    agent_role_arns: Mapping[str, str]
    objectstore_bucket: str
    objectstore_marker_key: str
    objectstore_marker_sha256: str
    keyvalue_table: str
    keyvalue_marker_pk: str
    keyvalue_marker_sha256: str
    function_name: str
    queue_url: str
    external_id: str
    infrastructure_fingerprint: str
    #: Optional role outputs are present only when Terraform's negative-control
    #: profile is enabled.  They remain output-name keyed so scenario bindings
    #: survive compilation without teaching the core about AWS role names.
    optional_role_arns: Mapping[str, str] = field(default_factory=dict)

    def all_resource_arns(self) -> tuple[str, ...]:
        return (
            self.bootstrap_role_arn,
            self.principal_role_arn,
            *self.agent_role_arns.values(),
            f"arn:aws:s3:::{self.objectstore_bucket}",
            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{self.keyvalue_table}",
            f"arn:aws:lambda:{self.region}:{self.account_id}:function:{self.function_name}",
            self.queue_arn,
            *self.optional_role_arns.values(),
        )

    def role_arn_for_output(self, output_name: str) -> str:
        standard = {
            "bootstrap_role_arn": self.bootstrap_role_arn,
            "principal_role_arn": self.principal_role_arn,
            **{f"agent_{letter}_role_arn": arn for letter, arn in self.agent_role_arns.items()},
        }
        try:
            return standard[output_name]
        except KeyError:
            try:
                return self.optional_role_arns[output_name]
            except KeyError:
                raise ConfigurationError(
                    f"Terraform output {output_name!r} is not a resolved benchmark role",
                    output=output_name,
                ) from None

    @property
    def queue_arn(self) -> str:
        parsed = urlparse(self.queue_url)
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 2 or not parsed.netloc.startswith("sqs."):
            raise ConfigurationError(
                f"queue_url does not identify an AWS SQS queue: {self.queue_url!r}"
            )
        account_id, queue_name = parts
        if account_id != self.account_id:
            raise ConfigurationError(
                f"queue_url account {account_id!r} does not match Terraform account "
                f"{self.account_id!r}"
            )
        return f"arn:aws:sqs:{self.region}:{account_id}:{queue_name}"


def load_terraform_outputs(path: Path) -> TerraformOutputs:
    """Load ``terraform output -json`` (each output wrapped as
    ``{"value": ..., "type": ..., "sensitive": ...}``) and validate every
    required name from AWS_PROVIDER_SPEC section 8 is present (P5).

    Raises :class:`ConfigurationError` -- not a bare ``KeyError`` -- so a
    missing or malformed Terraform state produces an interpretable abort
    rather than a stack trace.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(
            f"could not read Terraform outputs from {path}: {exc}", path=str(path)
        ) from exc

    return parse_terraform_outputs(raw, path=path)


def parse_terraform_outputs(raw: object, *, path: Path) -> TerraformOutputs:
    """Validate and parse an already decoded ``terraform output -json`` document.

    ``infra status`` uses this for the live state response so it can compare that
    response with the captured file without writing another local artifact.
    """
    if not isinstance(raw, dict):
        raise ConfigurationError(
            f"Terraform outputs at {path} must be a JSON object", path=str(path)
        )

    missing = [name for name in _REQUIRED_OUTPUT_NAMES if name not in raw]
    if missing:
        raise ConfigurationError(
            f"Terraform outputs at {path} are missing required names: {sorted(missing)}",
            path=str(path),
            missing=sorted(missing),
        )

    def value(name: str) -> Any:
        entry = raw[name]
        if isinstance(entry, dict):
            if "value" not in entry:
                raise ConfigurationError(
                    f"Terraform output {name!r} at {path} is missing its value",
                    path=str(path),
                    output=name,
                )
            return entry["value"]
        return entry

    optional_role_arns = {
        name: value(name)
        for name in (
            "agent_b_expansion_role_arn",
            "agent_b_survival_role_arn",
            "agent_c_nonmonotone_role_arn",
        )
        if name in raw and value(name) is not None
    }

    outputs = TerraformOutputs(
        namespace=value("namespace"),
        account_id=value("account_id"),
        region=value("region"),
        bootstrap_role_arn=value("bootstrap_role_arn"),
        principal_role_arn=value("principal_role_arn"),
        agent_role_arns={letter: value(f"agent_{letter}_role_arn") for letter in "abcdef"},
        objectstore_bucket=value("objectstore_bucket"),
        objectstore_marker_key=value("objectstore_marker_key"),
        objectstore_marker_sha256=value("objectstore_marker_sha256"),
        keyvalue_table=value("keyvalue_table"),
        keyvalue_marker_pk=value("keyvalue_marker_pk"),
        keyvalue_marker_sha256=value("keyvalue_marker_sha256"),
        function_name=value("function_name"),
        queue_url=value("queue_url"),
        external_id=value("external_id"),
        infrastructure_fingerprint=value("infrastructure_fingerprint"),
        optional_role_arns=optional_role_arns,
    )
    _validate_output_shapes(outputs, path=path)
    return outputs


#: Per AWS_PROVIDER_SPEC section 8's output contract: namespace regex (the
#: same ``Namespace`` pattern ``core/ids.py`` enforces everywhere else),
#: digest format (``sha256:`` + 64 hex chars), and IAM role ARN shape. This
#: is Python-side enforcement of what M9's Terraform outputs must look like
#: -- a malformed apply should fail loudly here (P5), not surface later as an
#: inexplicable namespace mismatch deep in a probe.
_NAMESPACE_RE = re.compile(r"^cb-[0-9a-f]{8}$")
_ACCOUNT_ID_RE = re.compile(r"^\d{12}$")
_ROLE_ARN_RE = re.compile(r"^arn:aws:iam::\d{12}:role/.+$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _validate_output_shapes(outputs: TerraformOutputs, *, path: Path) -> None:
    problems: list[str] = []

    def check(condition: bool, name: str, expected: str) -> None:
        if not condition:
            problems.append(f"{name} does not match {expected}")

    check(
        isinstance(outputs.namespace, str) and bool(_NAMESPACE_RE.fullmatch(outputs.namespace)),
        "namespace",
        "^cb-[0-9a-f]{8}$",
    )
    check(
        isinstance(outputs.account_id, str) and bool(_ACCOUNT_ID_RE.fullmatch(outputs.account_id)),
        "account_id",
        "12 digits",
    )
    check(
        isinstance(outputs.bootstrap_role_arn, str)
        and bool(_ROLE_ARN_RE.fullmatch(outputs.bootstrap_role_arn)),
        "bootstrap_role_arn",
        "an IAM role ARN",
    )
    check(
        isinstance(outputs.principal_role_arn, str)
        and bool(_ROLE_ARN_RE.fullmatch(outputs.principal_role_arn)),
        "principal_role_arn",
        "an IAM role ARN",
    )
    for letter, arn in outputs.agent_role_arns.items():
        check(
            isinstance(arn, str) and bool(_ROLE_ARN_RE.fullmatch(arn)),
            f"agent_{letter}_role_arn",
            "an IAM role ARN",
        )
    for name, arn in outputs.optional_role_arns.items():
        check(
            isinstance(arn, str) and bool(_ROLE_ARN_RE.fullmatch(arn)),
            name,
            "an IAM role ARN",
        )
    check(
        isinstance(outputs.objectstore_marker_sha256, str)
        and bool(_DIGEST_RE.fullmatch(outputs.objectstore_marker_sha256)),
        "objectstore_marker_sha256",
        "sha256:<64 hex chars>",
    )
    check(
        isinstance(outputs.keyvalue_marker_sha256, str)
        and bool(_DIGEST_RE.fullmatch(outputs.keyvalue_marker_sha256)),
        "keyvalue_marker_sha256",
        "sha256:<64 hex chars>",
    )
    check(
        isinstance(outputs.infrastructure_fingerprint, str)
        and bool(_DIGEST_RE.fullmatch(outputs.infrastructure_fingerprint)),
        "infrastructure_fingerprint",
        "sha256:<64 hex chars>",
    )
    check(
        isinstance(outputs.queue_url, str) and outputs.queue_url.startswith("https://sqs."),
        "queue_url",
        "an https://sqs.* URL",
    )

    for name in ("region", "objectstore_bucket", "keyvalue_table", "function_name", "external_id"):
        check(isinstance(getattr(outputs, name), str), name, "a string")

    if problems:
        raise ConfigurationError(
            f"Terraform outputs at {path} have malformed values: {'; '.join(problems)}",
            path=str(path),
            problems=problems,
        )


@dataclass(frozen=True, slots=True)
class CostEstimate:
    estimated_calls_by_service: Mapping[str, int]

    @property
    def total_usd(self) -> float:
        return sum(
            ESTIMATED_COST_PER_CALL_USD.get(service, 0.0) * count
            for service, count in self.estimated_calls_by_service.items()
        )


@dataclass
class _CheckList:
    checks: list[PreflightCheck] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append(PreflightCheck(name=name, passed=passed, detail=detail))


def run_preflight(
    *,
    sts_client: Any,
    resourcegroupstaggingapi_client: Any,
    iam_client: Any | None = None,
    envelope: SafetyEnvelope,
    terraform_outputs: TerraformOutputs,
    precondition_results: Mapping[str, bool] | Callable[[], Mapping[str, bool]],
    cost_estimate: CostEstimate,
    clock_offset_ms: float | None = None,
    max_clock_offset_ms: float = 5000.0,
    i_know_what_i_am_doing: bool = False,
    partition: str = "aws",
) -> PreflightReport:
    """Run P1-P11 in order (AWS_PROVIDER_SPEC section 2).

    P1/P2 raise immediately -- no other check runs and no other AWS call is
    made -- because everything downstream is meaningless against the wrong
    account. P3-P10 are recorded as checks even on failure so a caller sees
    every problem at once, matching :class:`PreflightReport`'s own contract;
    the caller (``adapter.preflight``) decides whether an overall failure is
    fatal, since some callers (this milestone's own tests) want the full
    report even when it fails.
    """
    checks = _CheckList()

    # P1: sts:GetCallerIdentity must succeed at all.
    try:
        identity = sts_client.get_caller_identity()
    except ClientError as exc:
        checks.add("caller_identity", False, str(exc))
        return PreflightReport(passed=False, checks=tuple(checks.checks))
    account = identity["Account"]
    caller_arn = identity["Arn"]
    checks.add("caller_identity", True, account)

    # P2: the single most important check in the project.
    if account not in envelope.allowed_account_ids:
        checks.add("account_allowlisted", False, account)
        raise AccountNotAllowedError(
            f"resolved account {account!r} is not in the operator's allowlist",
            account=account,
            allowed=envelope.allowed_account_ids,
        )
    checks.add("account_allowlisted", True, account)
    if account != terraform_outputs.account_id:
        checks.add("terraform_account_matches", False, terraform_outputs.account_id)
        raise AccountNotAllowedError(
            f"live account {account!r} does not match Terraform output account "
            f"{terraform_outputs.account_id!r}",
            account=account,
            terraform_account=terraform_outputs.account_id,
        )
    checks.add("terraform_account_matches", True, account)

    # P3: session region in the allowlist.
    region = terraform_outputs.region
    region_ok = region in envelope.allowed_regions
    checks.add("region_allowlisted", region_ok, region)
    if not region_ok:
        raise RegionNotAllowedError(f"region {region!r} not in allowlist", region=region)

    # P4: partition must be the public commercial partition unless configured.
    arn_partition = caller_arn.split(":")[1] if caller_arn.count(":") >= 1 else ""
    partition_ok = arn_partition == partition
    checks.add("partition", partition_ok, arn_partition)
    if not partition_ok:
        raise ConfigurationError(
            f"caller partition {arn_partition!r} does not match configured {partition!r}",
            partition=arn_partition,
        )

    # P5: Terraform outputs already loaded successfully to reach this point
    # (load_terraform_outputs raises ConfigurationError on its own if not).
    checks.add("terraform_outputs", True, terraform_outputs.infrastructure_fingerprint)

    # P6: every resolved ARN matches the benchmark ARN shape.
    bad_arns = [
        arn for arn in terraform_outputs.all_resource_arns() if not _BENCHMARK_ARN_RE.match(arn)
    ]
    for arn in terraform_outputs.all_resource_arns():
        try:
            assert_aws_reference(arn, account_id=account, namespace=terraform_outputs.namespace)
        except Exception:
            if arn not in bad_arns:
                bad_arns.append(arn)
    checks.add("arn_shape", not bad_arns, "; ".join(bad_arns) or "all ARNs match")
    if bad_arns:
        raise ConfigurationError(f"ARNs do not match the benchmark shape: {bad_arns}")

    # P7: tags -- delegated to the resource-groups tagging API, which can
    # answer "does anything owned by this account carry Project=CHAINBREAK
    # and this Namespace" in one call rather than one call per resource type.
    try:
        tagged_resources = _get_all_tagged_resources(
            resourcegroupstaggingapi_client,
            [
                {"Key": "Project", "Values": ["CHAINBREAK"]},
                {"Key": "Namespace", "Values": [terraform_outputs.namespace]},
            ],
        )
        expected_arns = set(terraform_outputs.all_resource_arns())
        tagged_by_arn = {item.get("ResourceARN"): item for item in tagged_resources}
        role_arns = {arn for arn in expected_arns if ":role/" in arn}
        if role_arns:
            if iam_client is None:
                raise ConfigurationError("IAM role tag verification client was not provided")
            for role_arn in role_arns:
                role_name = role_arn.rsplit("/", 1)[-1]
                role_tags = iam_client.list_role_tags(RoleName=role_name).get("Tags", [])
                tagged_by_arn[role_arn] = {"Tags": role_tags}
        missing_tags = sorted(expected_arns - set(tagged_by_arn))
        malformed_tags = [
            arn
            for arn in expected_arns.intersection(tagged_by_arn)
            if _tag_map(tagged_by_arn[arn]).get("Project") != "CHAINBREAK"
            or _tag_map(tagged_by_arn[arn]).get("Namespace") != terraform_outputs.namespace
        ]
        tags_ok = not missing_tags and not malformed_tags
    except Exception as exc:
        tags_ok = False
        missing_tags = []
        malformed_tags = []
        checks.add("resource_tags", False, f"unable to verify: {exc}")
    else:
        detail = f"{len(expected_arns)} required resources verified"
        if missing_tags or malformed_tags:
            detail = f"missing={missing_tags}; malformed={malformed_tags}"
        checks.add("resource_tags", tags_ok, detail)
    if not tags_ok:
        raise ConfigurationError(
            f"not every required benchmark resource carries the expected tags; "
            f"missing={missing_tags}; malformed={malformed_tags}",
            missing=missing_tags,
            malformed=malformed_tags,
        )

    # P8: marker preconditions. Failure here is CONFIGURATION_ERROR, not a
    # SecurityInvariantError abort -- a missing marker is an infrastructure
    # gap, not a security violation.
    resolved_preconditions = (
        precondition_results() if callable(precondition_results) else precondition_results
    )
    failed_preconditions = [name for name, ok in resolved_preconditions.items() if not ok]
    checks.add(
        "marker_preconditions", not failed_preconditions, "; ".join(failed_preconditions) or "ok"
    )
    preflight_passed_so_far = not failed_preconditions

    # P9: no production-tagged resource in the account, unless overridden.
    try:
        production = resourcegroupstaggingapi_client.get_resources(
            TagFilters=[{"Key": "Environment", "Values": ["production"]}]
        )
        has_production = len(production.get("ResourceTagMappingList", [])) > 0
    except Exception as exc:
        checks.add("no_production_resources", False, f"unable to verify: {exc}")
        raise ConfigurationError(
            "production-tag verification could not complete; refusing to continue",
            reason=str(exc),
        ) from exc
    else:
        production_count = len(production.get("ResourceTagMappingList", []))
        checks.add(
            "no_production_resources",
            not has_production or i_know_what_i_am_doing,
            f"{production_count} production-tagged resources found",
        )
    if has_production and not i_know_what_i_am_doing:
        raise ConfigurationError(
            "account contains resources tagged Environment=production; "
            "pass --i-know-what-i-am-doing to proceed anyway"
        )

    # P10: estimated cost ceiling.
    cost_ok = cost_estimate.total_usd <= envelope.max_estimated_cost_usd
    checks.add(
        "estimated_cost",
        cost_ok,
        f"${cost_estimate.total_usd:.4f} <= ${envelope.max_estimated_cost_usd:.2f}",
    )
    if not cost_ok:
        raise ConfigurationError(
            f"estimated cost ${cost_estimate.total_usd:.4f} exceeds ceiling "
            f"${envelope.max_estimated_cost_usd:.2f}"
        )

    # P11: clock offset -- WARN only, downgrades timing confidence rather
    # than aborting.
    measured_offset_ms = clock_offset_ms
    if measured_offset_ms is None:
        measured_offset_ms = _clock_offset_from_response(identity)
    timing_confidence = "high"
    if measured_offset_ms is None:
        timing_confidence = "low"
        checks.add("clock_offset", True, "WARN: unmeasured; timing confidence downgraded")
    else:
        clock_ok = abs(measured_offset_ms) <= max_clock_offset_ms
        if not clock_ok:
            timing_confidence = "low"
        # P11 is a warning, not an abort.  A skewed provider clock weakens
        # wall-clock correlation but monotonic probe intervals remain usable.
        checks.add(
            "clock_offset",
            True,
            f"{'OK' if clock_ok else 'WARN'}: measured {measured_offset_ms:.1f}ms",
        )

    return PreflightReport(
        passed=preflight_passed_so_far and all(c.passed for c in checks.checks),
        account_ref=account,
        region=region,
        checks=tuple(checks.checks),
        timing_confidence=timing_confidence,
    )


def _tag_map(item: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(tag.get("Key")): str(tag.get("Value"))
        for tag in item.get("Tags", [])
        if isinstance(tag, Mapping) and "Key" in tag and "Value" in tag
    }


def _get_all_tagged_resources(
    client: Any, tag_filters: list[dict[str, Any]]
) -> list[Mapping[str, Any]]:
    resources: list[Mapping[str, Any]] = []
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"TagFilters": tag_filters}
        if token is not None:
            kwargs["PaginationToken"] = token
        response = client.get_resources(**kwargs)
        resources.extend(
            item for item in response.get("ResourceTagMappingList", []) if isinstance(item, Mapping)
        )
        next_token = response.get("PaginationToken")
        token = str(next_token) if next_token else None
        if token is None:
            return resources


def _clock_offset_from_response(response: Mapping[str, Any]) -> float | None:
    headers = response.get("ResponseMetadata", {}).get("HTTPHeaders", {})
    date_value = headers.get("date") or headers.get("Date")
    if not isinstance(date_value, str):
        return None
    try:
        provider_time = parsedate_to_datetime(date_value).astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        return None
    return (datetime.now(UTC) - provider_time).total_seconds() * 1000


#: Delegation mechanisms the compiler (M3) may request; kept here as the
#: preflight module's own reminder that AWS_PROVIDER_SPEC section 4 names
#: exactly five real mechanisms plus two reserved-for-future ones the v0.1
#: compiler already rejects (``core/enums.py::DelegationMechanism``).
SUPPORTED_MECHANISMS: frozenset[DelegationMechanism] = frozenset(
    {
        DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
        DelegationMechanism.ROLE_CHAIN,
        DelegationMechanism.SESSION_POLICY_SCOPED,
        DelegationMechanism.ROLE_CHAIN_WITH_SESSION_POLICY,
        DelegationMechanism.RESOURCE_POLICY_GRANT,
    }
)

__all__ = [
    "ESTIMATED_COST_PER_CALL_USD",
    "SUPPORTED_MECHANISMS",
    "CostEstimate",
    "TerraformOutputs",
    "load_terraform_outputs",
    "run_preflight",
]

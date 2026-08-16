"""Construction boundary for the AWS provider.

Terraform output loading and boto3 session construction deliberately live in
this module.  Callers receive a validated adapter and do not need to know how
AWS sessions are created; tests can inject a moto-backed session without any
real AWS call being possible during construction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from chainbreak.providers.aws.adapter import AwsProviderAdapter
from chainbreak.providers.aws.preflight import TerraformOutputs, load_terraform_outputs

__all__ = [
    "DEFAULT_TERRAFORM_OUTPUTS",
    "aws_provider",
    "build_aws_provider",
    "create_aws_provider",
]

DEFAULT_TERRAFORM_OUTPUTS = Path("infra/terraform/environments/aws-sandbox/outputs.json")


def create_aws_provider(
    outputs_path: Path = DEFAULT_TERRAFORM_OUTPUTS,
    *,
    run_id: str = "factory",
    operator_session: Any | None = None,
    session: Any | None = None,
    i_know_what_i_am_doing: bool = False,
) -> AwsProviderAdapter:
    """Load validated Terraform outputs and construct one adapter per run.

    No AWS API is called here.  With no injected session, boto3 only creates a
    credential/session object; the first network operation is the adapter's
    explicit P1 ``GetCallerIdentity`` in ``preflight``.
    """
    outputs: TerraformOutputs = load_terraform_outputs(Path(outputs_path))
    if operator_session is not None and session is not None:
        raise ValueError("pass only one of operator_session or session")
    if operator_session is None:
        operator_session = session
    if operator_session is None:
        import boto3

        operator_session = boto3.Session(region_name=outputs.region)
    return AwsProviderAdapter(
        operator_session=operator_session,
        outputs=outputs,
        run_id=run_id,
        i_know_what_i_am_doing=i_know_what_i_am_doing,
    )


def build_aws_provider(**kwargs: Any) -> AwsProviderAdapter:
    """Compatibility spelling for integrations that call providers factories."""
    return create_aws_provider(**kwargs)


def aws_provider(**kwargs: Any) -> AwsProviderAdapter:
    """Short factory alias used by provider-dispatch integrations."""
    return create_aws_provider(**kwargs)

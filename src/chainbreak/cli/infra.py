"""`chainbreak infra plan|apply|destroy|status|verify-clean` (M9).

A thin wrapper over the real `terraform` binary for plan/apply/destroy/
status -- no business logic here (ARCHITECTURE.md section 3.1), terraform's
exit code is the interface. Plan/destroy output remains streamed straight
through; apply emits only scrubbed resource-change summaries so callers and
CliRunner can verify a no-op without leaking Terraform output. `verify-clean`
is the one command with no Terraform
subprocess at all: it enumerates AWS resources by tag directly (F5), which
stays meaningful even if local state were ever lost or corrupted --
"destroy succeeded" is verified, never assumed.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess  # nosec B404 -- shells out to terraform only, args are fixed literals
import tempfile
from pathlib import Path

import typer

app = typer.Typer(help="Manage benchmark infrastructure.")

_DEFAULT_ENVIRONMENTS_ROOT = Path("infra/terraform/environments")


def _assert_aws_context(provider: str | None, block_id: str | None, command: str) -> None:
    if provider is not None and provider != "aws":
        typer.echo(f"chainbreak infra {command}: only --provider aws is valid", err=True)
        raise typer.Exit(code=2)
    if provider == "aws" and not block_id:
        typer.echo(
            f"chainbreak infra {command}: --block-id is required with --provider aws", err=True
        )
        raise typer.Exit(code=2)


def _environment_dir(environment: str) -> Path:
    env_dir = _DEFAULT_ENVIRONMENTS_ROOT / environment
    if not env_dir.is_dir():
        typer.echo(
            f"chainbreak infra: no such environment {environment!r} (looked in {env_dir})",
            err=True,
        )
        raise typer.Exit(code=2)
    return env_dir


def _terraform_binary() -> str:
    binary = shutil.which("terraform")
    if binary is None:
        typer.echo(
            "chainbreak infra: terraform not found on PATH -- install Terraform 1.7+ "
            "(see infra/terraform/README.md)",
            err=True,
        )
        raise typer.Exit(code=2)
    return binary


def _run_terraform(args: list[str], *, cwd: Path, scrub_apply_summary: bool = False) -> int:
    """Runs with inherited stdio so terraform's own interactive prompts and
    progress output reach the caller directly -- this command never
    captures or reinterprets them. The binary path comes from
    ``shutil.which`` (not user-supplied input) and ``args`` are this
    module's own fixed subcommand literals, never operator-controlled
    strings passed straight to a shell."""
    if not scrub_apply_summary:
        streamed_result = subprocess.run(  # noqa: S603  # nosec B603 -- binary resolved via shutil.which, args are fixed literals
            [_terraform_binary(), *args], cwd=cwd, check=False
        )
        return streamed_result.returncode

    captured_result = subprocess.run(  # noqa: S603  # nosec B603 -- binary resolved via shutil.which, args are fixed literals
        [_terraform_binary(), *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    if captured_result.returncode != 0:
        if captured_result.stderr:
            typer.echo(captured_result.stderr, err=True)
        return captured_result.returncode
    for line in (captured_result.stdout or "").splitlines():
        if line.startswith("Apply complete!"):
            typer.echo(line.strip())
            if "Resources: 0 added, 0 changed, 0 destroyed." in line:
                typer.echo("0 to add, 0 to change, 0 to destroy")
    return captured_result.returncode


def _init(env_dir: Path) -> None:
    code = _run_terraform(["init", "-input=false"], cwd=env_dir)
    if code != 0:
        raise typer.Exit(code=code)


@app.command()
def plan(environment: str = typer.Argument("aws-sandbox")) -> None:
    env_dir = _environment_dir(environment)
    _init(env_dir)
    raise typer.Exit(code=_run_terraform(["plan"], cwd=env_dir))


@app.command()
def apply(
    environment: str = typer.Argument("aws-sandbox"),
    auto_approve: bool = typer.Option(False, "--auto-approve"),
    provider: str | None = typer.Option(None, "--provider"),
    block_id: str | None = typer.Option(None, "--block-id"),
) -> None:
    _assert_aws_context(provider, block_id, "apply")
    env_dir = _environment_dir(environment)
    # A failed apply, including a failure during init, makes any prior capture
    # untrustworthy. Remove it before Terraform can fail so status can never
    # report an earlier workspace state as current.
    _remove_outputs(env_dir)
    _init(env_dir)
    args = ["apply"]
    if auto_approve:
        args.append("-auto-approve")
    code = _run_terraform(args, cwd=env_dir, scrub_apply_summary=True)
    if code != 0:
        _remove_outputs(env_dir)
        raise typer.Exit(code=code)
    _capture_outputs(env_dir)


def _capture_outputs(env_dir: Path) -> None:
    """F4: captures `terraform output -json` to a file
    `providers.aws.preflight.load_terraform_outputs` reads at preflight P5.
    Not committed -- environment-identifying data (T-13); gitignored
    alongside state and tfvars."""
    result = subprocess.run(  # noqa: S603  # nosec B603 -- binary resolved via shutil.which, args are fixed literals
        [_terraform_binary(), "output", "-json"],
        cwd=env_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _remove_outputs(env_dir)
        typer.echo(f"chainbreak infra apply: could not capture outputs: {result.stderr}", err=True)
        raise typer.Exit(code=1)
    outputs_path = env_dir / "outputs.json"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=env_dir,
            prefix=".outputs.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(result.stdout)
            handle.flush()
        temporary_path.replace(outputs_path)
    except OSError as exc:
        _remove_outputs(env_dir)
        typer.echo(f"chainbreak infra apply: could not atomically write outputs: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    typer.echo(f"chainbreak infra apply: outputs captured to {outputs_path}")


def _remove_outputs(env_dir: Path) -> None:
    outputs_path = env_dir / "outputs.json"
    try:
        outputs_path.unlink(missing_ok=True)
    except OSError as exc:
        typer.echo(
            f"chainbreak infra: could not remove stale outputs at {outputs_path}: {exc}", err=True
        )
        raise typer.Exit(code=1) from exc


def _terraform_output_json(env_dir: Path) -> str:
    result = subprocess.run(  # noqa: S603  # nosec B603 -- fixed terraform output command
        [_terraform_binary(), "output", "-json"],
        cwd=env_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "terraform output -json failed")
    return result.stdout


@app.command()
def destroy(
    environment: str = typer.Argument("aws-sandbox"),
    auto_approve: bool = typer.Option(False, "--auto-approve"),
    provider: str | None = typer.Option(None, "--provider"),
    block_id: str | None = typer.Option(None, "--block-id"),
) -> None:
    _assert_aws_context(provider, block_id, "destroy")
    env_dir = _environment_dir(environment)
    args = ["destroy"]
    if auto_approve:
        args.append("-auto-approve")
    code = _run_terraform(args, cwd=env_dir)
    if code == 0:
        _remove_outputs(env_dir)
    raise typer.Exit(code=code)


@app.command()
def status(
    environment: str = typer.Argument("aws-sandbox"),
    provider: str | None = typer.Option(None, "--provider"),
    block_id: str | None = typer.Option(None, "--block-id"),
    capture_namespace: Path | None = typer.Option(
        None,
        "--capture-namespace",
        help="Write the verified current namespace to this file before teardown.",
    ),
) -> None:
    _assert_aws_context(provider, block_id, "status")
    env_dir = _environment_dir(environment)
    outputs_path = env_dir / "outputs.json"
    if not outputs_path.is_file():
        typer.echo(
            f"chainbreak infra status: no captured outputs at {outputs_path} -- "
            "run `chainbreak infra apply` first",
            err=True,
        )
        raise typer.Exit(code=1)

    from chainbreak.core.errors import ConfigurationError
    from chainbreak.providers.aws.preflight import load_terraform_outputs, parse_terraform_outputs

    try:
        outputs = load_terraform_outputs(outputs_path)
    except ConfigurationError as exc:
        typer.echo(f"chainbreak infra status: {exc.message}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        current = parse_terraform_outputs(
            json.loads(_terraform_output_json(env_dir)), path=Path("<terraform-state-output>")
        )
    except (ConfigurationError, json.JSONDecodeError, RuntimeError) as exc:
        typer.echo(
            f"chainbreak infra status: could not verify current Terraform state: {exc}", err=True
        )
        raise typer.Exit(code=1) from exc
    if current != outputs:
        typer.echo(
            "chainbreak infra status: outputs.json is stale or does not match "
            "current Terraform state",
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo(f"namespace: {outputs.namespace}")
    typer.echo(f"region: {outputs.region}")
    typer.echo(f"infrastructure_fingerprint: {outputs.infrastructure_fingerprint}")
    if capture_namespace is not None:
        try:
            capture_namespace.parent.mkdir(parents=True, exist_ok=True)
            capture_namespace.write_text(f"{outputs.namespace}\n", encoding="utf-8")
        except OSError as exc:
            typer.echo(f"chainbreak infra status: could not capture namespace: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(f"namespace captured to {capture_namespace}")


@app.command("verify-clean")
def verify_clean(
    environment: str = typer.Argument("aws-sandbox"),
    region: str = typer.Option(
        None, "--region", help="Overrides the region captured in outputs.json, if any."
    ),
    namespace: str | None = typer.Option(
        None, "--namespace", help="Exact Terraform namespace when outputs.json is unavailable."
    ),
    provider: str | None = typer.Option(None, "--provider"),
    block_id: str | None = typer.Option(None, "--block-id"),
) -> None:
    """Verify every provisioned service is clean using exact Project/Namespace tags."""
    _assert_aws_context(provider, block_id, "verify-clean")
    from chainbreak.core.errors import ConfigurationError
    from chainbreak.providers.aws.cleanup import list_tagged_resources

    # verify-clean's own point (F5) is proving cleanup independent of local
    # state -- deliberately does not require the environment directory to
    # exist on disk (unlike plan/apply/destroy/status, which need it to
    # find a terraform config or captured outputs to act on). A missing or
    # never-checked-out directory just means no region hint is available.
    captured_namespace = _namespace_hint(environment)
    if namespace is not None and captured_namespace is not None and namespace != captured_namespace:
        typer.echo(
            "chainbreak infra verify-clean: supplied namespace disagrees with outputs.json",
            err=True,
        )
        raise typer.Exit(code=1)
    resolved_namespace = namespace or captured_namespace
    if resolved_namespace is None:
        typer.echo(
            "chainbreak infra verify-clean: exact namespace unavailable -- pass --namespace "
            "or retain a valid outputs.json",
            err=True,
        )
        raise typer.Exit(code=1)
    resolved_region = region or _region_hint(environment)
    try:
        resources = list_tagged_resources(region=resolved_region, namespace=resolved_namespace)
    except ConfigurationError as exc:
        typer.echo(f"chainbreak infra verify-clean: {exc.message}", err=True)
        raise typer.Exit(code=1) from exc

    if resources:
        typer.echo(
            f"chainbreak infra verify-clean: {len(resources)} resource(s) still tagged "
            "Project=CHAINBREAK:",
            err=True,
        )
        for arn in sorted(resources):
            typer.echo(f"  {arn}", err=True)
        raise typer.Exit(code=1)
    typer.echo("chainbreak infra verify-clean: nothing remaining")


def _region_hint(environment: str) -> str | None:
    """Best-effort region from a previously captured outputs.json, so
    verify-clean checks the same region the environment was applied to
    rather than whatever boto3's own default chain happens to resolve.
    ``None`` for any reason the file isn't there or isn't readable --
    never raises, since a missing hint is not this command's failure."""
    outputs_path = _DEFAULT_ENVIRONMENTS_ROOT / environment / "outputs.json"
    if not outputs_path.is_file():
        return None
    from chainbreak.core.errors import ConfigurationError
    from chainbreak.providers.aws.preflight import load_terraform_outputs

    try:
        return load_terraform_outputs(outputs_path).region
    except ConfigurationError:
        return None


def _namespace_hint(environment: str) -> str | None:
    outputs_path = _DEFAULT_ENVIRONMENTS_ROOT / environment / "outputs.json"
    if not outputs_path.is_file():
        return None
    from chainbreak.core.errors import ConfigurationError
    from chainbreak.providers.aws.preflight import load_terraform_outputs

    try:
        return load_terraform_outputs(outputs_path).namespace
    except ConfigurationError:
        return None


@app.command("namespace")
def namespace(
    environment: str = typer.Argument("aws-sandbox"),
    provider: str = typer.Option("aws", "--provider"),
    block_id: str = typer.Option(..., "--block-id"),
    workspace: str = typer.Option(
        "default", "--workspace", help="Terraform workspace used in the namespace formula."
    ),
) -> None:
    """Derive the exact AWS sandbox namespace from the apply contract, offline.

    This is used before a fresh-checkout apply so cleanup can target the exact
    prior namespace even when Terraform outputs/state are absent locally.
    """
    _assert_aws_context(provider, block_id, "namespace")
    if environment != "aws-sandbox":
        typer.echo("chainbreak infra namespace: only aws-sandbox is supported", err=True)
        raise typer.Exit(code=2)
    account_id = os.environ.get("TF_VAR_expected_account_id", "").strip()  # noqa: SIM112
    salt = os.environ.get("TF_VAR_namespace_salt", "")  # noqa: SIM112
    if not account_id or not salt:
        typer.echo(
            "chainbreak infra namespace: TF_VAR_expected_account_id and "
            "TF_VAR_namespace_salt are required",
            err=True,
        )
        raise typer.Exit(code=1)
    digest = hashlib.sha1(  # noqa: S324  # nosec B324 -- deterministic namespace hint, not cryptographic security
        f"{account_id}{workspace}{salt}".encode()
    ).hexdigest()
    typer.echo(f"cb-{digest[:8]}")

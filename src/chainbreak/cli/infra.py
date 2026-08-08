"""`chainbreak infra plan|apply|destroy|status|verify-clean` (M9).

A thin wrapper over the real `terraform` binary for plan/apply/destroy/
status -- no business logic here (ARCHITECTURE.md section 3.1), terraform's
own output and exit code are the interface, streamed straight through
rather than parsed. `verify-clean` is the one command with no Terraform
subprocess at all: it enumerates AWS resources by tag directly (F5), which
stays meaningful even if local state were ever lost or corrupted --
"destroy succeeded" is verified, never assumed.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404 -- shells out to terraform only, args are fixed literals
from pathlib import Path

import typer

app = typer.Typer(help="Manage benchmark infrastructure.")

_DEFAULT_ENVIRONMENTS_ROOT = Path("infra/terraform/environments")


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


def _run_terraform(args: list[str], *, cwd: Path) -> int:
    """Runs with inherited stdio so terraform's own interactive prompts and
    progress output reach the caller directly -- this command never
    captures or reinterprets them. The binary path comes from
    ``shutil.which`` (not user-supplied input) and ``args`` are this
    module's own fixed subcommand literals, never operator-controlled
    strings passed straight to a shell."""
    result = subprocess.run(  # noqa: S603  # nosec B603 -- binary resolved via shutil.which, args are fixed literals
        [_terraform_binary(), *args], cwd=cwd, check=False
    )
    return result.returncode


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
) -> None:
    env_dir = _environment_dir(environment)
    _init(env_dir)
    args = ["apply"]
    if auto_approve:
        args.append("-auto-approve")
    code = _run_terraform(args, cwd=env_dir)
    if code != 0:
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
        typer.echo(f"chainbreak infra apply: could not capture outputs: {result.stderr}", err=True)
        raise typer.Exit(code=1)
    outputs_path = env_dir / "outputs.json"
    with outputs_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(result.stdout)
    typer.echo(f"chainbreak infra apply: outputs captured to {outputs_path}")


@app.command()
def destroy(
    environment: str = typer.Argument("aws-sandbox"),
    auto_approve: bool = typer.Option(False, "--auto-approve"),
) -> None:
    env_dir = _environment_dir(environment)
    args = ["destroy"]
    if auto_approve:
        args.append("-auto-approve")
    raise typer.Exit(code=_run_terraform(args, cwd=env_dir))


@app.command()
def status(environment: str = typer.Argument("aws-sandbox")) -> None:
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
    from chainbreak.providers.aws.preflight import load_terraform_outputs

    try:
        outputs = load_terraform_outputs(outputs_path)
    except ConfigurationError as exc:
        typer.echo(f"chainbreak infra status: {exc.message}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"namespace: {outputs.namespace}")
    typer.echo(f"account_id: {outputs.account_id}")
    typer.echo(f"region: {outputs.region}")
    typer.echo(f"infrastructure_fingerprint: {outputs.infrastructure_fingerprint}")


@app.command("verify-clean")
def verify_clean(
    environment: str = typer.Argument("aws-sandbox"),
    region: str = typer.Option(
        None, "--region", help="Overrides the region captured in outputs.json, if any."
    ),
) -> None:
    """F5: lists every resource still tagged ``Project=CHAINBREAK`` via the
    Resource Groups Tagging API and exits non-zero if any remain."""
    from chainbreak.core.errors import ConfigurationError
    from chainbreak.providers.aws.cleanup import list_tagged_resources

    # verify-clean's own point (F5) is proving cleanup independent of local
    # state -- deliberately does not require the environment directory to
    # exist on disk (unlike plan/apply/destroy/status, which need it to
    # find a terraform config or captured outputs to act on). A missing or
    # never-checked-out directory just means no region hint is available.
    resolved_region = region or _region_hint(environment)
    try:
        resources = list_tagged_resources(region=resolved_region)
    except ConfigurationError as exc:
        typer.echo(
            "chainbreak infra verify-clean: no region available -- pass --region, or run "
            "`chainbreak infra apply` first so outputs.json can supply one",
            err=True,
        )
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

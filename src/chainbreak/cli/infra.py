"""`chainbreak infra plan|apply|destroy|status|verify-clean` -- not yet
implemented until M9 (Terraform AWS sandbox). No `.tf` files exist yet;
only module contracts (`infra/terraform/**/CONTRACT.md`).
"""

from __future__ import annotations

import typer

app = typer.Typer(help="Manage benchmark infrastructure. Not yet implemented.")


def _not_implemented(command: str) -> None:
    typer.echo(f"chainbreak infra {command}: not implemented until M9", err=True)
    raise typer.Exit(code=2)


@app.command()
def plan(environment: str = typer.Argument("aws-sandbox")) -> None:
    _not_implemented("plan")


@app.command()
def apply(
    environment: str = typer.Argument("aws-sandbox"),
    auto_approve: bool = typer.Option(False, "--auto-approve"),
) -> None:
    _not_implemented("apply")


@app.command()
def destroy(
    environment: str = typer.Argument("aws-sandbox"),
    auto_approve: bool = typer.Option(False, "--auto-approve"),
) -> None:
    _not_implemented("destroy")


@app.command()
def status(environment: str = typer.Argument("aws-sandbox")) -> None:
    _not_implemented("status")


@app.command("verify-clean")
def verify_clean(environment: str = typer.Argument("aws-sandbox")) -> None:
    _not_implemented("verify-clean")

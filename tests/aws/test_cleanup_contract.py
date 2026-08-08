"""F5/F7 end to end against a real, operator-owned AWS benchmark account
(M09-terraform-sandbox.md's own "Tests" section, verbatim): "applies,
destroys, destroys again, then runs verify-clean."

Gated behind the ``e2e`` marker (``tests/conftest.py``'s force-skip):
skipped in every default run, including CI, and only collected for real
when the operator sets ``CHAINBREAK_ALLOW_AWS_TESTS=1`` *and* has already
run ``cp terraform.tfvars.example terraform.tfvars`` in
``infra/terraform/environments/aws-sandbox`` per ``infra/terraform/README.md``'s
own "Usage" section. **No test in this file has ever been executed** --
this account does not exist in this environment (see PROJECT_STATUS.md).
Every step below is a direct transcription of the acceptance criteria in
M09-terraform-sandbox.md ("Apply -> all preflight checks pass -> destroy ->
verify-clean reports nothing remaining", "Second apply is a no-op; second
destroy is a no-op"), not a result.

This drives ``chainbreak infra`` through its real CLI entry points
(``src/chainbreak/cli/infra.py``) via ``CliRunner``, not the Terraform
binary directly -- the same interface an operator actually uses, so a pass
here proves the CLI wrapper as well as the underlying modules.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

pytestmark = pytest.mark.e2e

_ENVIRONMENT = "aws-sandbox"


def _require_prepared_environment() -> None:
    """This account is never actually provisioned in this development
    environment (Terraform itself, and a real AWS account to point it at,
    are both prerequisites this sandbox has never had -- see
    PROJECT_STATUS.md's M9 entry). The check below is what a real operator
    run would need to have done first per infra/terraform/README.md's
    "Usage" section; it is here so a stray invocation fails with a clear
    message rather than a Terraform stack trace, not because it has ever
    been exercised."""
    tfvars = Path(f"infra/terraform/environments/{_ENVIRONMENT}/terraform.tfvars")
    if not tfvars.is_file():
        pytest.skip(
            f"{tfvars} does not exist -- run `cp terraform.tfvars.example "
            "terraform.tfvars` and fill in your account id, region, and salt "
            "first (infra/terraform/README.md, 'Usage')"
        )


class TestApplyDestroyDestroyVerifyClean:
    """M09-terraform-sandbox.md acceptance criteria 3 and 5, in one
    sequential run against one real environment -- destroy's idempotency
    (criterion 5) can only be demonstrated by actually destroying twice,
    not by inspecting a plan (M09's own "Risks" section makes this same
    point about force_destroy and the Lambda log group)."""

    def test_apply_then_preflight_then_destroy_twice_then_verify_clean(self):
        _require_prepared_environment()

        from chainbreak.cli.main import app

        runner = CliRunner()

        apply_result = runner.invoke(app, ["infra", "apply", _ENVIRONMENT, "--auto-approve"])
        assert apply_result.exit_code == 0, apply_result.output

        # F4: `chainbreak infra apply` must have captured outputs.json,
        # which `chainbreak validate`'s preflight checks (P1-P11) then read.
        validate_result = runner.invoke(app, ["validate"])
        assert validate_result.exit_code == 0, validate_result.output
        assert "FAIL" not in validate_result.output

        first_destroy = runner.invoke(app, ["infra", "destroy", _ENVIRONMENT, "--auto-approve"])
        assert first_destroy.exit_code == 0, first_destroy.output

        # Criterion 5: a second destroy against already-destroyed
        # infrastructure must be a clean no-op, never an error -- proving
        # F7 ("zero manual steps") actually holds rather than just being
        # documented.
        second_destroy = runner.invoke(app, ["infra", "destroy", _ENVIRONMENT, "--auto-approve"])
        assert second_destroy.exit_code == 0, second_destroy.output

        # F5: verify-clean is independent of local Terraform state by
        # design (cli/infra.py's own docstring) -- it is the actual proof
        # that destroy left nothing behind, not an assumption from
        # Terraform's own exit code.
        verify_result = runner.invoke(app, ["infra", "verify-clean", _ENVIRONMENT])
        assert verify_result.exit_code == 0, verify_result.output
        assert "nothing remaining" in verify_result.output

    def test_second_apply_is_a_no_op(self):
        """Criterion 5's other half: applying twice in a row against
        unchanged tfvars must report `0 to add, 0 to change, 0 to destroy`
        -- namespace generation (F3) must be stable across applies within
        the same workspace, not re-rolled on every run."""
        _require_prepared_environment()

        from chainbreak.cli.main import app

        runner = CliRunner()

        first_apply = runner.invoke(app, ["infra", "apply", _ENVIRONMENT, "--auto-approve"])
        assert first_apply.exit_code == 0, first_apply.output

        second_apply = runner.invoke(app, ["infra", "apply", _ENVIRONMENT, "--auto-approve"])
        assert second_apply.exit_code == 0, second_apply.output
        assert "0 to add, 0 to change, 0 to destroy" in second_apply.output

        runner.invoke(app, ["infra", "destroy", _ENVIRONMENT, "--auto-approve"])

"""capabilities/guard.py: OperationAllowlist -- SI-3's runtime enforcement.

M2's negative control: a probe that invokes an operation outside the
binding's declared ``actions`` must raise, even when the probe body itself
completes without raising -- a broadened operation is a violation
independent of what it returned.
"""

from __future__ import annotations

import re

import pytest

from chainbreak.capabilities.guard import OperationAllowlist
from chainbreak.core.errors import CapabilityBroadeningError
from tests.fixtures.bad_bindings import narrow_binding_for_broadening_test

pytestmark = pytest.mark.unit


class TestOperationAllowlist:
    def test_no_operations_recorded_passes(self):
        with OperationAllowlist(narrow_binding_for_broadening_test()):
            pass  # no-op probe

    def test_operation_within_allowlist_passes(self):
        with OperationAllowlist(narrow_binding_for_broadening_test()) as allowlist:
            allowlist.record("s3:GetObject")

    def test_operation_outside_allowlist_raises_on_exit(self):
        with (
            pytest.raises(CapabilityBroadeningError, match="s3:PutObject"),
            OperationAllowlist(narrow_binding_for_broadening_test()) as allowlist,
        ):
            allowlist.record("s3:GetObject")
            allowlist.record("s3:PutObject")
            # The probe body itself raises nothing -- it "succeeded".

    def test_raises_even_though_the_block_completed_without_its_own_exception(self):
        """The exact scenario the M2 spec calls out: the raise must fire even
        when the probe itself would have "succeeded"."""
        block_completed = False
        with (
            pytest.raises(CapabilityBroadeningError),
            OperationAllowlist(narrow_binding_for_broadening_test()) as allowlist,
        ):
            allowlist.record("s3:PutObject")
            block_completed = True
        assert block_completed is True

    def test_invoked_operations_are_visible(self):
        with OperationAllowlist(narrow_binding_for_broadening_test()) as allowlist:
            allowlist.record("s3:GetObject")
            assert allowlist.invoked_operations == ("s3:GetObject",)

    def test_reentering_resets_recorded_operations(self):
        allowlist = OperationAllowlist(narrow_binding_for_broadening_test())
        with allowlist:
            allowlist.record("s3:GetObject")
        with allowlist:
            assert allowlist.invoked_operations == ()

    def test_error_message_names_the_capability(self):
        with (
            pytest.raises(CapabilityBroadeningError, match=re.escape("objectstore.read")),
            OperationAllowlist(narrow_binding_for_broadening_test()) as allowlist,
        ):
            allowlist.record("s3:DeleteObject")

    def test_broadening_check_still_fires_when_block_itself_raises(self):
        """A genuine probe error and a broadening violation can co-occur; the
        broadening check must not be silently skipped because the block
        already failed for its own reason."""
        with (
            pytest.raises(CapabilityBroadeningError),
            OperationAllowlist(narrow_binding_for_broadening_test()) as allowlist,
        ):
            allowlist.record("s3:PutObject")
            raise RuntimeError("simulated transient probe failure")

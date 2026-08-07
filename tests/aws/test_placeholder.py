"""Placeholder for the `aws`-marked layer.

Proves F5 (tests/conftest.py): a real AWS test must skip by default rather than
silently not being collected at all. The real AWS adapter tests arrive at M8.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.aws


def test_aws_layer_is_gated() -> None:
    raise AssertionError(
        "this test must never execute without CHAINBREAK_ALLOW_AWS_TESTS=1 -- "
        "if you see this failure, the opt-in gate in tests/conftest.py is broken"
    )

"""Shared fixtures and marker enforcement for the CHAINBREAK test suite.

F5 (M0): the ``aws`` and ``e2e`` markers require a real, operator-owned AWS benchmark
account and cost money to run. They must never execute by accident -- in a default
`pytest` invocation, in CI, or on a contributor's laptop -- so they are force-skipped
here unless the operator explicitly opts in with ``CHAINBREAK_ALLOW_AWS_TESTS=1``.
"""

from __future__ import annotations

import os

import pytest

_OPT_IN_ENV_VAR = "CHAINBREAK_ALLOW_AWS_TESTS"
_GATED_MARKERS = ("aws", "e2e")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get(_OPT_IN_ENV_VAR) == "1":
        return

    skip_marker = pytest.mark.skip(
        reason=(
            f"requires a real AWS benchmark account; set {_OPT_IN_ENV_VAR}=1 to opt in "
            "(never set in default CI -- see ARCHITECTURE.md, T-12)"
        )
    )
    for item in items:
        if any(item.get_closest_marker(name) for name in _GATED_MARKERS):
            item.add_marker(skip_marker)

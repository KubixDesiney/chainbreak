"""Runtime package version contract for the v0.1.0 release."""

from __future__ import annotations

import pytest

from chainbreak import __version__

pytestmark = pytest.mark.unit


def test_runtime_version_is_release_version() -> None:
    assert __version__ == "0.1.0"

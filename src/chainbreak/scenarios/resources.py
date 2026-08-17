"""Access to the scenario corpus shipped in the installed distribution."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Final

_DATA_PACKAGE: Final = "chainbreak._packaged_data"


def _scenario_root() -> Traversable:
    packaged = resources.files(_DATA_PACKAGE).joinpath("scenarios")
    if packaged.is_dir():
        return packaged
    # Editable source checkouts do not contain the wheel's force-included
    # mirror. This fallback is only for authoring/tests; installed wheels use
    # the importlib.resources branch above.
    return Path(__file__).resolve().parents[3] / "scenarios"


@contextmanager
def packaged_scenarios_path() -> Iterator[Path]:
    """Yield a filesystem path for the complete packaged corpus.

    ``importlib.resources.as_file`` also supports zipped distributions, so
    callers do not accidentally fall back to a repository-relative path.
    """
    with resources.as_file(_scenario_root()) as path:
        yield path

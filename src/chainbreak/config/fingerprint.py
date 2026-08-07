"""Config fingerprinting (F1): ``Provenance.config_fingerprint`` in every evidence bundle.

``Settings`` carries no secret material today -- no credential belongs in
config; those come from the provider's own credential chain, never a config
file (SI-1). There is therefore nothing to exclude yet. This function is
still the single place a future exclusion list would go, rather than every
call site hashing the resolved settings ad hoc.
"""

from __future__ import annotations

from chainbreak.config.settings import Settings
from chainbreak.core.canonical import dumps
from chainbreak.core.ids import fingerprint_json


def fingerprint_settings(settings: Settings) -> str:
    return fingerprint_json(dumps(settings))

"""``evidence/migrate.py`` (M18 F5): evidence bundle format version
transitions, always writing a new directory and never touching the source.

``Manifest.bundle_format_version`` has been ``1`` since M6
(``evidence/manifest.py::BUNDLE_FORMAT_VERSION``) and no format change has
ever shipped, so no migration is registered by this module today -- there is
nothing yet to migrate *from*. This module exists so the mechanism itself
(the registry, dispatch, and the "preserve the original" guarantee F5
requires) is implemented and tested before the day a real transformation is
needed, rather than being designed and reviewed for the first time on that
day. When ``BUNDLE_FORMAT_VERSION`` next changes, its migration is
registered here with :func:`register_migration`, typically starting from
:func:`copy_bundle_verbatim` for the (usually large) majority of a bundle a
format change leaves untouched.

Every write funnels through ``evidence/writer.py`` (S1's choke point, same
rule as every other module in this package): nothing here ever calls
``open()`` for writing or ``Path.write_bytes``/``write_text`` directly.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from chainbreak.core.errors import EvidenceError
from chainbreak.evidence.manifest import BUNDLE_FORMAT_VERSION
from chainbreak.evidence.reader import read_manifest
from chainbreak.evidence.writer import write_bytes_artifact

__all__ = [
    "MigrationFunc",
    "MigrationResult",
    "copy_bundle_verbatim",
    "migrate_bundle",
    "register_migration",
    "registered_migrations",
]

#: A migration receives ``(source_run_dir, target_run_dir)`` and is fully
#: responsible for writing every artifact of the migrated bundle into
#: ``target_run_dir``. It must never write into ``source_run_dir``.
MigrationFunc = Callable[[Path, Path], None]

_MIGRATIONS: dict[tuple[int, int], MigrationFunc] = {}


def register_migration(from_version: int, to_version: int, fn: MigrationFunc) -> None:
    """Register ``fn`` as the migration from ``from_version`` to ``to_version``.

    Refuses a second registration for the same pair (a silently-replaced
    migration is exactly the kind of thing that should be a loud error, not
    a footgun for whichever registration happened to import last).
    """
    key = (from_version, to_version)
    if key in _MIGRATIONS:
        raise ValueError(f"a migration from {from_version} to {to_version} is already registered")
    _MIGRATIONS[key] = fn


def registered_migrations() -> tuple[tuple[int, int], ...]:
    """Every ``(from_version, to_version)`` pair currently registered, sorted."""
    return tuple(sorted(_MIGRATIONS))


def copy_bundle_verbatim(source_run_dir: Path, target_run_dir: Path) -> None:
    """Byte-for-byte copy of every file under ``source_run_dir`` into
    ``target_run_dir``. The shared first step of essentially every
    migration -- and, on its own, a complete and legitimate migration for a
    format bump that only adds a field with a default rather than changing
    any existing artifact's shape.

    Refuses if ``target_run_dir`` already exists, the same "never silently
    overwrite" posture :class:`~chainbreak.evidence.writer.BundleWriter`
    takes for a fresh run directory.
    """
    if target_run_dir.exists():
        raise EvidenceError(f"migration target already exists: {target_run_dir}")
    for source_path in sorted(source_run_dir.rglob("*")):
        if not source_path.is_file():
            continue
        relative = source_path.relative_to(source_run_dir)
        write_bytes_artifact(target_run_dir / relative, source_path.read_bytes())


@dataclass(frozen=True, slots=True)
class MigrationResult:
    run_id: str
    source_dir: Path
    target_dir: Path
    from_version: int
    to_version: int


def migrate_bundle(
    run_dir: Path,
    *,
    to_version: int = BUNDLE_FORMAT_VERSION,
    target_dir: Path | None = None,
) -> MigrationResult:
    """Migrate ``run_dir``'s bundle to ``to_version``.

    F5's "preserving the original" is a structural guarantee here, not an
    intention: the result always lands in a *new* directory (``target_dir``,
    default ``<run_dir.parent>/<run_id>-v<to_version>``), and every
    migration this module can ever dispatch to is itself constrained to
    write only through :func:`copy_bundle_verbatim`
    /:func:`~chainbreak.evidence.writer.write_bytes_artifact`, neither of
    which is capable of opening a file under ``source_run_dir`` for writing.

    Refuses (:class:`~chainbreak.core.errors.EvidenceError`) rather than
    guessing when the bundle is already at ``to_version``, or when no
    registered migration connects the two versions -- a silent no-op or a
    silently wrong transformation would both be worse than an explicit stop.
    """
    manifest = read_manifest(run_dir / "manifest.json")
    from_version = manifest.bundle_format_version
    if from_version == to_version:
        raise EvidenceError(
            f"run {manifest.run_id} is already at bundle format version {to_version}",
            run_id=manifest.run_id,
        )
    migration = _MIGRATIONS.get((from_version, to_version))
    if migration is None:
        raise EvidenceError(
            f"no migration registered from bundle format version {from_version} to "
            f"{to_version} (registered: {registered_migrations()})",
            run_id=manifest.run_id,
            from_version=from_version,
            to_version=to_version,
        )

    destination = target_dir or run_dir.parent / f"{manifest.run_id}-v{to_version}"
    migration(run_dir, destination)

    return MigrationResult(
        run_id=manifest.run_id,
        source_dir=run_dir,
        target_dir=destination,
        from_version=from_version,
        to_version=to_version,
    )

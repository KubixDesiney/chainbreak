#!/usr/bin/env python3
"""Install a wheel into a temporary venv and exercise its offline public path."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


def _run(command: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument(
        "--runtime-lock",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "requirements-runtime.lock",
    )
    parser.add_argument(
        "--python",
        type=Path,
        help=(
            "Use an already provisioned interpreter instead of creating a venv "
            "(developer shortcut)."
        ),
    )
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    runtime_lock = args.runtime_lock.resolve()
    if not wheel.is_file() or not runtime_lock.is_file():
        raise SystemExit("wheel and runtime lock must be regular files")

    with tempfile.TemporaryDirectory(prefix="chainbreak-wheel-smoke-") as temp:
        root = Path(temp)
        if args.python is None:
            venv = root / "venv"
            _run([sys.executable, "-m", "venv", str(venv)], cwd=root, env=os.environ.copy())
            python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        else:
            venv = None
            python = args.python.resolve()
        pip = [str(python), "-m", "pip", "--disable-pip-version-check", "--no-cache-dir"]
        if args.python is None:
            _run(
                [*pip, "install", "--require-hashes", "-r", str(runtime_lock)],
                cwd=root,
                env=os.environ.copy(),
            )
        _run([*pip, "install", "--no-deps", str(wheel)], cwd=root, env=os.environ.copy())

        smoke_env = os.environ.copy()
        smoke_env["PYTHONHASHSEED"] = "0"
        _run(
            [
                str(python),
                "-c",
                "from chainbreak import __version__; "
                "assert __version__ == '0.1.0'; print(__version__)",
            ],
            cwd=root,
            env=smoke_env,
        )
        cli = str(
            (venv / ("Scripts/chainbreak.exe" if os.name == "nt" else "bin/chainbreak"))
            if venv is not None
            else python.parent / ("chainbreak.exe" if os.name == "nt" else "chainbreak")
        )
        _run([cli, "--help"], cwd=root, env=smoke_env)
        _run(
            [
                str(python),
                "-c",
                "from importlib import resources; from pathlib import Path; "
                "d=resources.files('chainbreak._packaged_data'); "
                "assert d.joinpath('schemas').joinpath('experiment-run.v1.schema.json').is_file(); "
                "assert len(list(d.joinpath('scenarios').rglob('*.yaml'))) == 24; "
                "Path('scenario.yaml').write_bytes(d.joinpath('scenarios/scope-attenuation/basic.yaml').read_bytes())",
            ],
            cwd=root,
            env=smoke_env,
        )
        _run([cli, "scenario", "validate", "scenario.yaml"], cwd=root, env=smoke_env)
        run_id_file = root / "run-id.txt"
        _run(
            [
                cli,
                "run",
                "scenario.yaml",
                "--provider",
                "fake",
                "--seed",
                "1729",
                "--runs-root",
                "runs",
                "--run-id-file",
                str(run_id_file),
            ],
            cwd=root,
            env=smoke_env,
        )
        run_id = run_id_file.read_text(encoding="utf-8").strip()
        _run([cli, "analyze", run_id, "--runs-root", "runs"], cwd=root, env=smoke_env)
        _run(
            [
                cli,
                "report",
                run_id,
                "--format",
                "markdown",
                "--output",
                "report.md",
                "--runs-root",
                "runs",
            ],
            cwd=root,
            env=smoke_env,
        )
        archive = root / "archive.tar.gz"
        _run(
            [
                cli,
                "evidence",
                "export",
                run_id,
                "--archive",
                "--output",
                str(archive),
                "--runs-root",
                "runs",
            ],
            cwd=root,
            env=smoke_env,
        )
        with tarfile.open(archive, "r:gz") as tar:
            names = set(tar.getnames())
        if not any(name.endswith("/catalog.yaml") for name in names):
            raise RuntimeError("archive is missing the packaged catalog")
        if not any(name.endswith("/schemas/experiment-run.v1.schema.json") for name in names):
            raise RuntimeError("archive is missing packaged schemas")
        print(f"installed-wheel smoke passed: {wheel.name} ({run_id})")


if __name__ == "__main__":
    main()

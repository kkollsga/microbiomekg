#!/usr/bin/env python3
"""The install proof: is the package a package?

Builds a wheel and an sdist into a scratch directory, installs the wheel into
a clean venv created *outside* the repo root (so the checkout cannot shadow
the installed copy), and runs the three verbs there against an empty data
directory. Every step is asserted; a step that cannot run is a failure, not a
skip. Needs ``uv`` on PATH and the ``build`` package in the repo venv
(``make venv`` installs it).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw)


def main() -> int:
    uv = shutil.which("uv")
    if not uv:
        print("ERROR: uv is not on PATH; the clean venv needs it", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="microbiomekg-install-") as tmp:
        scratch = Path(tmp)
        dist = scratch / "dist"
        run([sys.executable, "-m", "build", "--outdir", str(dist)], cwd=ROOT)
        wheels = sorted(dist.glob("*.whl"))
        sdists = sorted(dist.glob("*.tar.gz"))
        assert len(wheels) == 1 and len(sdists) == 1, sorted(dist.iterdir())
        print(f"  built {wheels[0].name} and {sdists[0].name}")

        venv = scratch / "venv"
        run([uv, "venv", str(venv)])
        py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run([uv, "pip", "install", "--python", str(py), str(wheels[0])])

        data = scratch / "data"
        data.mkdir()
        # cwd is the scratch dir: nothing of the checkout is importable there.
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        got = run(
            [
                str(py),
                "-c",
                "import microbiomekg as m; s = m.status('data'); "
                "print(m.__version__); print(len(s)); "
                "print(sorted(v.state for v in s.values()))",
            ],
            cwd=scratch,
            env=env,
        ).stdout
        version, count, states = got.strip().splitlines()
        assert version == "0.1.0", version
        assert int(count) >= 13, count
        assert "'present'" not in states, states
        print(f"  import microbiomekg {version}: {count} sources, none present")

        cli = venv / (
            "Scripts/microbiomekg.exe" if os.name == "nt" else "bin/microbiomekg"
        )
        out = run([str(cli), "status", "--data", "data"], cwd=scratch, env=env).stdout
        assert "taxonomy" in out and "manual" in out and "absent" in out, out
        print("  microbiomekg status: ok")
        out = run(
            [str(cli), "build", "--data", "data", "--no-save"], cwd=scratch, env=env
        ).stdout
        assert "nothing loaded" in out and "no graph written" in out, out
        print("  microbiomekg build (empty): nothing loaded, exit 0")
        for p in (
            "microbiomekg/blueprints/core.json",
            "microbiomekg/mcp/microbiomekg_mcp.yaml",
        ):
            got = run(
                [
                    str(py),
                    "-c",
                    f"import microbiomekg, pathlib; p = pathlib.Path(microbiomekg.__file__).parent.parent / '{p}'; print(p.is_file())",
                ],
                cwd=scratch,
                env=env,
            ).stdout.strip()
            assert got == "True", (p, got)
        print("  package data (fragments, MCP manifest): shipped")
    print("install proof: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

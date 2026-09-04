"""Run a prep the way a source test used to — script path plus argv — whether
or not it has been converted to ``run(raw, store, ...)``.

Transitional, for the tests of the preps not yet converted: their fixtures
run BugSigDB and the taxonomy first so the shared tables exist, and those two
are functions now. A converted prep runs in process against a store mirrored
from the CSV directory the fixture works in, and the store is exported back;
an unconverted one runs as the subprocess it always was. Deleted with the
last conversion.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: argv option -> ``run()`` keyword, for the converted preps.
OPTIONS = {
    "--raw": "raw",
    "--dump": "dump",
    "--taxdump": "taxdump",
    "--mondo": "mondo",
    "--rank-ceiling": "rank_ceiling",
    "--limit": "limit",
    "--scope": "scope",
    "--out": "out",
    "--cited-from": "cited_from",
}


def run_prep(script: Path, *args: str, expect: int = 0) -> subprocess.CompletedProcess:
    script = Path(script)
    module = importlib.import_module(f"microbiomekg.preps.{script.stem}")
    if not hasattr(module, "run"):
        proc = subprocess.run(
            [sys.executable, str(script), *args],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert proc.returncode == expect, (
            f"{script.name} exited {proc.returncode}, expected {expect}:\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
        return proc

    from microbiomekg import pipeline
    from microbiomekg.tables import Frames

    opts: dict = {}
    it = iter(args)
    for flag in it:
        key = OPTIONS[flag]
        value = next(it)
        opts[key] = (
            int(value)
            if key == "limit"
            else Path(value)
            if key not in ("scope", "rank_ceiling")
            else value
        )
    out = opts.pop("out")
    opts.pop("cited_from", None)  # the store's cited_taxa table is what it reads
    raw = opts.pop("raw", out)
    store = Frames()
    pipeline.ingest_csv(store, out)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        module.run(raw, store, **opts)
    pipeline.export_csv(store, out)
    return subprocess.CompletedProcess([str(script), *args], 0, buffer.getvalue(), "")

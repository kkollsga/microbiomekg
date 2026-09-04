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
    "--workbooks": "workbooks",
    "--card": "card_dir",
    "--xml": "xml",
    "--reactome": "reactome",
    "--chembl": "chembl",
    "--interventions": "interventions",
    "--kegg": "kegg",
    "--tables": "tables",
    "--metabolites": "metabolites",
    "--microbes": "microbes",
    "--njc19": "njc19",
    "--xlsx": "xlsx",
    "--published-matrix": "published_matrix",
}
#: Flags that take no value.
SWITCHES = {"--with-kegg": ("opted_in", True)}


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
        if flag in SWITCHES:
            key, value = SWITCHES[flag]
            opts[key] = value
            continue
        key = OPTIONS[flag]
        value = next(it)
        if key == "limit":
            opts[key] = int(value)
        elif key == "published_matrix":
            opts[key] = tuple(int(v) for v in value.split(","))
        elif key in ("scope", "rank_ceiling"):
            opts[key] = value
        else:
            opts[key] = Path(value)
    out = opts.pop("out")
    opts.pop("cited_from", None)  # the store's cited_taxa table is what it reads
    raw = opts.pop("raw", out)
    store = Frames()
    pipeline.ingest_csv(store, out)
    from microbiomekg.rawdata import MissingInput

    buffer = io.StringIO()
    code, stderr = 0, ""
    with contextlib.redirect_stdout(buffer):
        try:
            module.run(raw, store, **opts)
        except MissingInput as absent:
            code, stderr = pipeline.MISSING_INPUT, str(absent)
    assert code == expect, f"{script.name} exited {code}, expected {expect}:\n{stderr}"
    if code == 0:
        pipeline.export_csv(store, out)
    return subprocess.CompletedProcess(
        [str(script), *args], code, buffer.getvalue(), stderr
    )


def load_from_csv_dir(csv_dir: Path, sources: list[str]):
    """The graph for the CSVs a fixture's preps wrote, loaded through the
    store the way the build loads — the fragments declare frames, so a
    directory is read into a store first. Transitional, like :func:`run_prep`."""
    from microbiomekg import pipeline
    from microbiomekg.tables import Frames

    store = Frames()
    pipeline.ingest_csv(store, csv_dir)
    graph, _ = pipeline.load_graph(store, list(sources), verbose=False)
    return graph

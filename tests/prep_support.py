"""Run a prep the way a source test has always spelled it — script path plus
argv — against a store the test holds by key.

A source test's fixture runs two or three preps in order and then loads what
they produced; it names the run by a temporary directory and reads tables
back by name. Nothing is written there any more: the directory is the *key*
of a :class:`~microbiomekg.tables.Frames` store kept here, :func:`run_prep`
parses the argv into ``run()`` keywords and runs the prep into that store,
:func:`rows_of` reads a table back off it, and :func:`load_graph_for` loads
it the way the build does.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import subprocess
from pathlib import Path

from microbiomekg import pipeline
from microbiomekg.rawdata import MissingInput
from microbiomekg.tables import Frames, Table

#: argv option -> ``run()`` keyword.
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

_STORES: dict[str, Frames] = {}


def store_for(key: Path | str) -> Frames:
    """The store a fixture works in, by the key it names it with."""
    return _STORES.setdefault(str(key), Frames())


def run_prep(script: Path, *args: str, expect: int = 0) -> subprocess.CompletedProcess:
    """Run ``script``'s prep with ``args`` into the store ``--out`` names.

    Returns a ``CompletedProcess``-shaped record — return code 0, or 3 with
    the message on ``stderr`` when the prep raised ``MissingInput`` — so a
    test written against the subprocess it used to be reads the same fields.
    """
    script = Path(script)
    module = importlib.import_module(f"microbiomekg.preps.{script.stem}")
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
    store = store_for(opts.pop("out"))
    opts.pop("cited_from", None)  # the store's cited_taxa table is what it reads
    raw = opts.pop("raw", Path("."))
    buffer = io.StringIO()
    code, stderr = 0, ""
    with contextlib.redirect_stdout(buffer):
        try:
            module.run(raw, store, **opts)
        except MissingInput as absent:
            code, stderr = 3, str(absent)
    assert code == expect, f"{script.name} exited {code}, expected {expect}:\n{stderr}"
    return subprocess.CompletedProcess(
        [str(script), *args], code, buffer.getvalue(), stderr
    )


def rows_of(key: Path | str, name: str) -> list[dict[str, str]]:
    """The rows of table ``name`` (``x`` or ``x.csv``) in the store ``key``
    names; empty when no prep wrote it."""
    return store_for(key).rows(name.removesuffix(".csv"))


def append_rows(key: Path | str, name: str, extra: list[dict[str, str]]) -> None:
    """Add ``extra`` rows to table ``name`` in the store — what a test does
    between two preps to plant a row the next prep must see."""
    store = store_for(key)
    name = name.removesuffix(".csv")
    existing = store.tables.get(name)
    fields = (
        list(existing.fields)
        if existing
        else list(dict.fromkeys(k for r in extra for k in r))
    )
    table = Table(name, fields)
    for row in existing.rows if existing else []:
        table.add(row)
    for row in extra:
        table.add({f: row.get(f, "") for f in fields})
    store.put(table)


def load_graph_for(key: Path | str, sources: list[str]):
    """The graph for what the fixture's preps put in its store, loaded the way
    the build loads: the spine plus ``sources``."""
    graph, _ = pipeline.load_graph(store_for(key), list(sources), verbose=False)
    return graph

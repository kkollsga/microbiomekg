"""``microbiomekg.sources`` — the status a fresh clone gets instead of a build.

Two things are asserted that no other test holds: that every prep declares
the raw files it reads (``RAW_INPUTS``) and that the declaration is *true* —
withholding a declared file makes the prep refuse with exit 3 and name it —
and that the three tables ``status`` joins (preps, the fetch table, the
licence registry) cover the same set of sources.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from microbiomekg import fetch, sources
from microbiomekg.build import LICENCE_GATED, PREPS_DIR

ROOT = Path(__file__).resolve().parents[1]
SOURCES = sources.discover()
assert SOURCES, "no preps discovered — every assertion below would be vacuous"

#: Browser-only origins (CLAUDE.md, "data/raw is operator-owned").
BROWSER_ONLY = {"hmdb", "mimedb", "masi"}


def test_every_prep_declares_its_inputs_as_relative_posix_paths():
    for name in SOURCES:
        inputs = sources.declared_inputs(PREPS_DIR / f"prep_{name}.py")
        assert inputs, name
        for rel in inputs:
            assert not rel.startswith("/") and "\\" not in rel, (name, rel)
            assert rel.split("/", 1)[0], (name, rel)


def test_the_three_tables_cover_the_same_sources():
    """A source known to the preps but not to fetch — or the reverse — is a
    source the operator cannot be told how to complete."""
    assert set(fetch.FETCHES) == set(SOURCES)
    assert fetch.MANUAL.keys() == BROWSER_ONLY
    assert BROWSER_ONLY <= set(SOURCES)
    for name in SOURCES:
        assert fetch.how_to_get(name).strip(), name
    assert set(LICENCE_GATED) <= set(SOURCES)


def test_an_empty_directory_is_absent_or_manual_everywhere(tmp_path):
    (tmp_path / "raw").mkdir()
    got = sources.status(tmp_path)
    assert set(got) == set(SOURCES)
    for name, st in got.items():
        assert st.state == ("manual" if name in BROWSER_ONLY else "absent"), name
        assert st.missing == st.inputs, name
        assert st.how_to_get and st.licence, name
        assert st.state in sources.STATES
    assert got["kegg"].gated_by == "--with-kegg" and got["kegg"].optional
    assert got["bugsigdb"].gated_by is None
    assert got["taxonomy"].licence == "public-domain"
    assert got["hmdb"].licence == "HMDB-noncommercial"


def test_a_source_with_every_file_is_present_and_a_replaced_file_is_stale(tmp_path):
    raw = tmp_path / "raw"
    inputs = sources.declared_inputs(PREPS_DIR / "prep_card.py")
    for rel in inputs:
        (raw / rel).parent.mkdir(parents=True, exist_ok=True)
        (raw / rel).write_bytes(b"x" * 10)
    assert sources.status(tmp_path)["card"].state == "present"
    (raw / "manifest.json").write_text(json.dumps({inputs[0]: {"bytes": 999}}))
    st = sources.status(tmp_path)["card"]
    assert st.state == "stale" and st.missing == ()


@pytest.mark.parametrize("name", SOURCES)
def test_withholding_a_declared_input_makes_the_prep_refuse_by_name(tmp_path, name):
    """The declaration is the check: with every declared file present except
    the first, the prep must exit 3 and name what it wanted. A file declared
    but not needed would let the prep run on into the empty files and die
    some other way; a file needed but not declared would be complained about
    instead of the one withheld."""
    raw = tmp_path / "raw"
    inputs = sources.declared_inputs(PREPS_DIR / f"prep_{name}.py")
    withheld = inputs[0]
    for rel in inputs[1:]:
        (raw / rel).parent.mkdir(parents=True, exist_ok=True)
        (raw / rel).write_bytes(b"")
    (raw / withheld).parent.mkdir(parents=True, exist_ok=True)
    gate = [LICENCE_GATED[name]] if name in LICENCE_GATED else []
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            f"microbiomekg.preps.prep_{name}",
            "--raw",
            str(raw),
            "--out",
            str(tmp_path / "csv"),
            *gate,
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 3, f"{name}: exit {proc.returncode}\n{proc.stderr}"
    assert Path(withheld).name in proc.stderr, (name, withheld, proc.stderr)

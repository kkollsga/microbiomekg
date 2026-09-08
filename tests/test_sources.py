"""``microbiomekg.sources`` — the status a fresh clone gets instead of a build.

Two things are asserted that no other test holds: that every prep declares
the raw files it reads (``RAW_INPUTS``) and that the declaration is *true* —
withholding a declared file makes the prep raise ``MissingInput`` naming it —
and that the three tables ``status`` joins (preps, the fetch table, the
licence registry) cover the same set of sources.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from microbiomekg import download, pipeline, sources
from microbiomekg.pipeline import LICENCE_GATED, PREPS_DIR

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
    assert set(download.FETCHES) == set(SOURCES)
    assert download.MANUAL.keys() == BROWSER_ONLY
    assert BROWSER_ONLY <= set(SOURCES)
    for name in SOURCES:
        assert download.how_to_get(name).strip(), name
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


#: Every (source, declared input) pair — each file is withheld in turn.
WITHHELD = [
    (name, rel)
    for name in SOURCES
    for rel in sources.declared_inputs(PREPS_DIR / f"prep_{name}.py")
]


@pytest.mark.parametrize(
    "name,withheld", WITHHELD, ids=[f"{n}:{Path(r).name}" for n, r in WITHHELD]
)
def test_withholding_a_declared_input_makes_the_prep_refuse_by_name(
    tmp_path, name, withheld
):
    """The declaration is the check: with every declared file present except
    one, the prep must refuse and name that one — for *each* declared file
    in turn, so a trailing declaration is as tested as the first. A file
    declared but not needed would let the prep run on into the empty files
    and die some other way; a file needed but not declared would be
    complained about instead of the one withheld."""
    raw = tmp_path / "raw"
    inputs = sources.declared_inputs(PREPS_DIR / f"prep_{name}.py")
    for rel in inputs:
        (raw / rel).parent.mkdir(parents=True, exist_ok=True)
        if rel != withheld:
            (raw / rel).write_bytes(b"")
    module = importlib.import_module(f"microbiomekg.preps.prep_{name}")
    from microbiomekg.rawdata import MissingInput
    from microbiomekg.tables import Frames

    opts = pipeline.prep_options(name, "microbial", frozenset(LICENCE_GATED))
    with pytest.raises(MissingInput) as absent:
        module.run(raw, Frames(), **opts)
    assert Path(withheld).name in str(absent.value), (name, withheld, absent.value)


def test_origins_cover_exactly_the_declared_files():
    declared = {rel for _, rel in WITHHELD}
    assert set(download.ORIGINS) == declared
    for rel, origin in download.ORIGINS.items():
        assert origin.url.startswith(("https://", "http://")), rel
        assert origin.manual or origin.fetcher in download.SOURCES, rel


def test_file_status_reports_metadata_without_reading_contents(tmp_path, monkeypatch):
    import os
    import time

    raw = tmp_path / "raw"
    path = raw / "bugsigdb/full_dump_main.csv"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"12345")
    modified = time.time() - 172800
    os.utime(path, (modified, modified))
    (raw / "manifest.json").write_text(
        json.dumps(
            {"bugsigdb/full_dump_main.csv": {"bytes": 5, "sha256": "recorded-digest"}}
        )
    )
    monkeypatch.setattr(
        download, "sha256_of", lambda p: pytest.fail("status hashed data")
    )
    st = sources.status(tmp_path)["bugsigdb"]
    present, missing = st.files
    assert present.relative_path == "bugsigdb/full_dump_main.csv"
    assert present.state == "present" and present.size_bytes == 5
    assert present.modified_at.timestamp() == pytest.approx(modified)
    assert 172799 <= present.age_seconds <= 172802
    assert present.sha256 == "recorded-digest"
    assert present.url == download.BUGSIGDB_MAIN
    assert missing.relative_path == "mondo/mondo.obo"
    assert missing.state == "absent" and missing.size_bytes is None
    assert missing.modified_at is None and missing.age_seconds is None
    assert missing.fetcher == "mondo"
    assert st.size_bytes == 5
    path.write_bytes(b"changed size")
    assert sources.status(tmp_path)["bugsigdb"].files[0].state == "stale"


def test_masi_missing_only_automatic_inputs_is_not_manual(tmp_path):
    raw = tmp_path / "raw"
    for rel in sources.declared_inputs(PREPS_DIR / "prep_masi.py"):
        if download.origin_of(rel).manual:
            (raw / rel).parent.mkdir(parents=True, exist_ok=True)
            (raw / rel).write_bytes(b"manual input")
    assert sources.status(tmp_path)["masi"].state == "absent"


@pytest.mark.parametrize("manifest", ["[]", "null", '{"mondo/mondo.obo": 1}', "{bad"])
def test_malformed_manifest_does_not_hide_disk_status(tmp_path, manifest):
    raw = tmp_path / "raw"
    path = raw / "mondo/mondo.obo"
    path.parent.mkdir(parents=True)
    path.write_text("content")
    (raw / "manifest.json").write_text(manifest)
    st = sources.status(tmp_path)["bugsigdb"]
    assert st.files[1].state == "present"


def test_how_to_get_uses_the_selected_directory_and_quotes_shell_paths(tmp_path):
    import shlex

    data = tmp_path / "my data's folder"
    command = download.how_to_get("card", data)
    assert shlex.split(command) == [
        "microbiomekg",
        "fetch",
        "--data",
        str(data),
        "--only",
        "card",
    ]
    for source in BROWSER_ONLY:
        instructions = download.how_to_get(source, data)
        assert "data/raw/" not in instructions
        assert str(data / "raw") in instructions

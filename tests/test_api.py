"""The package surface: ``microbiomekg.{status,fetch,build}`` and the CLI.

Offline throughout. ``fetch`` is exercised with a fake source table so the
test proves the binding — the run lands in the directory it was given and the
manifest is written there — without a network."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

import microbiomekg
from conftest import TAXDUMP_MINI
from microbiomekg import api, cli, download

ROOT = Path(__file__).resolve().parents[1]


def test_the_three_verbs_are_lazy_attributes_of_the_package():
    assert microbiomekg.status is api.status
    assert microbiomekg.build is api.build
    assert microbiomekg.fetch is api.fetch
    assert microbiomekg.__version__
    with pytest.raises(AttributeError):
        microbiomekg.nope


def test_status_takes_the_data_directory_not_the_raw_one(tmp_path):
    (tmp_path / "raw").mkdir()
    got = api.status(tmp_path)
    assert got["taxonomy"].state == "absent"
    assert got["taxonomy"].path == tmp_path / "raw" / "ncbi_taxonomy"


def test_fetch_binds_the_run_to_the_directory_it_was_given(tmp_path, monkeypatch):
    seen: dict[str, Path] = {}

    def fake(args: argparse.Namespace) -> None:
        seen["raw"] = download.RAW
        seen["force"] = args.force
        download.record_problem("fake", "x", "", "manual", "placed by hand")

    monkeypatch.setattr(download, "SOURCES", {"fake": fake})
    monkeypatch.setattr(download, "MANIFEST_DATA", {})
    got = api.fetch(tmp_path, only=["fake"], force=True)
    assert seen == {"raw": tmp_path / "raw", "force": True}
    manifest = json.loads((tmp_path / "raw" / "manifest.json").read_text())
    assert manifest["fake/x"]["status"] == "manual"
    assert set(got) and got["hmdb"].state == "manual"


def test_build_on_an_empty_directory_returns_no_graph_and_every_source(tmp_path):
    (tmp_path / "raw").mkdir()
    result = api.build(tmp_path)
    assert result.graph is None and result.report is None
    assert set(result.skipped) == set(api.status(tmp_path))
    assert not (tmp_path / "csv").exists() or not list((tmp_path / "csv").glob("*.csv"))


def test_build_from_a_taxdump_returns_a_graph_and_a_report(tmp_path):
    raw = tmp_path / "raw" / "ncbi_taxonomy"
    raw.mkdir(parents=True)
    for f in TAXDUMP_MINI.iterdir():
        (raw / f.name).write_bytes(f.read_bytes())
    result = api.build(tmp_path)
    assert result.taxonomy_only and result.loaded == []
    assert result.graph is not None and result.out is None
    assert result.report.node_count("Taxon") == 170
    assert result.report.edge_count("HAS_PARENT") == 169
    assert result.graph.cypher("MATCH (t:Taxon) RETURN count(*) AS n")[0]["n"] == 170
    # save=True writes where it was told, and nowhere else
    out = tmp_path / "g" / "x.kgl"
    saved = api.build(tmp_path, out=out, save=True)
    assert saved.out == out and out.is_file()


def test_the_cli_status_lists_every_source_with_its_fix(tmp_path, capsys):
    (tmp_path / "raw").mkdir()
    assert cli.main(["status", "--data", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    for name, st in api.status(tmp_path).items():
        assert name in out and st.state in out
        assert st.how_to_get.split()[0] in out
    assert "(optional, --with-kegg)" in out


def test_the_console_entry_point_runs_the_build_verb(tmp_path):
    """`microbiomekg build --data D --no-save` through the module the entry
    point names, with the empty directory: exit 0 and the to-do list."""
    (tmp_path / "raw").mkdir()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "microbiomekg.cli",
            "build",
            "--data",
            str(tmp_path),
            "--no-save",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "nothing loaded" in proc.stdout

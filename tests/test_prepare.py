"""The ordinary loading path gives actionable guidance without a network."""

import json
import shlex

import pytest

import microbiomekg as mkg
from microbiomekg import api, cli, download, sources


def test_prepare_creates_layout_returns_status_and_remains_callable(tmp_path, capsys):
    data = tmp_path / "new data"
    table = mkg.prepare(data)
    for st in table.values():
        for rel in st.inputs:
            assert (data / "raw" / rel).parent.is_dir()
            assert not (data / "raw" / rel).exists()
    report = capsys.readouterr().out
    assert str(data) in report and "Available" in report
    assert "hmdb_metabolites.xml" in report and "https://hmdb.ca/" in report
    assert "(optional, --with-kegg)" in report
    assert mkg.prepare(data).keys() == table.keys()


def test_prepare_create_false_and_status_cli_do_not_write(tmp_path, capsys):
    data = tmp_path / "absent"
    mkg.prepare(data, create=False)
    python_report = capsys.readouterr().out
    assert not data.exists()
    assert cli.main(["status", "--data", str(data)]) == 0
    assert capsys.readouterr().out == python_report
    assert not data.exists()
    assert cli.main(["status", "--data", str(data), "--create"]) == 0
    assert (data / "raw" / "hmdb").is_dir()


def test_report_names_size_changed_file_and_distinguishes_recorded_metadata(
    tmp_path, capsys
):
    path = tmp_path / "raw" / "bugsigdb/full_dump_main.csv"
    path.parent.mkdir(parents=True)
    path.write_text("abc")
    (tmp_path / "raw/manifest.json").write_text(
        json.dumps({"bugsigdb/full_dump_main.csv": {"bytes": 500}})
    )
    mkg.prepare(tmp_path)
    report = capsys.readouterr().out
    assert "stale" in report and "3 B" in report
    assert "local file age" in report and "size differs" in report
    assert "bugsigdb/full_dump_main.csv" not in report


def test_missing_fetch_selects_required_sources_and_reports_remaining(
    tmp_path, monkeypatch
):
    calls = []
    monkeypatch.setattr(download, "run", lambda raw, **kw: calls.append((raw, kw)))
    got = api.fetch(tmp_path, missing=True)
    selected = calls[0][1]["only"]
    assert calls[0][0] == tmp_path / "raw"
    assert len(selected) == len(set(selected))
    assert {"ncbi", "mondo", "drug_screens", "masi"} <= set(selected)
    assert not {
        "kegg",
        "hmdb",
        "mimedb",
        "disbiome",
        "hmdad",
        "peryton",
        "pubmed",
    } & set(selected)
    assert got["hmdb"].state == "manual"


def test_missing_fetch_does_nothing_when_all_required_files_exist(
    tmp_path, monkeypatch
):
    for st in sources.status(tmp_path).values():
        if not st.optional:
            for rel in st.inputs:
                path = tmp_path / "raw" / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("present")
    monkeypatch.setattr(
        download, "run", lambda *a, **k: pytest.fail("empty selection ran all sources")
    )
    api.fetch(tmp_path, missing=True)


def test_missing_fetch_respects_selection_and_explicit_optional_source(
    tmp_path, monkeypatch
):
    calls = []
    monkeypatch.setattr(download, "run", lambda raw, **kw: calls.append(kw["only"]))
    api.fetch(tmp_path, missing=True, only=["kegg"])
    assert calls == [["kegg"]]
    calls.clear()
    api.fetch(tmp_path, missing=True, only=["drug_screens"])
    assert calls == [["drug_screens"]]
    calls.clear()
    api.fetch(tmp_path, missing=True, only=[])
    assert calls == []


def test_missing_fetch_only_calls_mondo_for_missing_shared_input(tmp_path, monkeypatch):
    for st in sources.status(tmp_path).values():
        for rel in st.inputs:
            if rel != "mondo/mondo.obo":
                path = tmp_path / "raw" / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("present")
    calls = []
    monkeypatch.setattr(download, "run", lambda raw, **kw: calls.append(kw["only"]))
    got = api.fetch(tmp_path, missing=True)
    assert calls == [["mondo"]]
    assert shlex.split(got["masi"].how_to_get)[-2:] == ["--only", "mondo"]


def test_cli_fetch_missing_runs_and_prints_remaining_work(
    tmp_path, monkeypatch, capsys
):
    calls = []
    monkeypatch.setattr(download, "run", lambda raw, **kw: calls.append(kw) or [])
    assert cli.main(["fetch", "--data", str(tmp_path), "--missing"]) == 0
    assert "ncbi" in calls[0]["only"]
    report = capsys.readouterr().out
    assert "hmdb_metabolites.xml" in report and "Download" in report


def test_cli_fetch_preserves_failure_exit_and_still_reports(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(download, "run", lambda *a, **k: ["ncbi"])
    assert cli.main(["fetch", "--data", str(tmp_path), "--missing"]) == 1
    assert "hmdb_metabolites.xml" in capsys.readouterr().out


@pytest.mark.parametrize(
    "args", [["status", "--typo"], ["fetch", "--missing", "--typo"]]
)
def test_loading_commands_reject_unknown_options(args):
    with pytest.raises(SystemExit) as exc:
        cli.main(args)
    assert exc.value.code == 2


def test_hmdb_guidance_saves_archive_then_extracts_xml(tmp_path, capsys):
    mkg.prepare(tmp_path)
    lines = capsys.readouterr().out.splitlines()
    archive = tmp_path / "raw/hmdb/hmdb_metabolites.zip"
    xml = tmp_path / "raw/hmdb/hmdb_metabolites.xml"
    assert f"    Download in a browser; save as: {archive}" in lines
    assert f"    Extract the archive to obtain: {xml}" in lines
    assert f"    Download in a browser; save as: {xml}" not in lines


def test_status_table_only_details_missing_or_over_age_files(
    tmp_path, capsys, monkeypatch
):
    from dataclasses import replace
    from microbiomekg import preparation

    table = sources.status(tmp_path)
    table = {
        name: replace(
            st,
            state="present",
            missing=(),
            files=tuple(
                replace(f, state="present", size_bytes=10, age_seconds=86400)
                for f in st.files
            ),
        )
        for name, st in table.items()
    }
    card = table["card"]
    table["card"] = replace(
        card, files=(replace(card.files[0], age_seconds=31 * 86400), *card.files[1:])
    )
    monkeypatch.setattr(preparation, "status", lambda data: table)
    mkg.prepare(tmp_path, create=False, max_age_days=30)
    report = capsys.readouterr().out
    assert all(column in report for column in ("Dataset", "Available", "Size", "Age"))
    assert "31 d" in report and "40 B" in report
    assert "card/card-data/card.json" in report
    assert "card/card-data/aro_index.tsv" not in report
    assert "bugsigdb/full_dump_main.csv" not in report
    assert report.count("URL:") == 1
    mkg.prepare(tmp_path, create=False, max_age_days=31)
    assert "URL:" not in capsys.readouterr().out


def test_cli_age_threshold_controls_report(tmp_path, capsys):
    import os
    import time

    p = tmp_path / "raw/bugsigdb/full_dump_main.csv"
    p.parent.mkdir(parents=True)
    p.write_text("input")
    old = time.time() - 10 * 86400
    os.utime(p, (old, old))
    assert cli.main(["status", "--data", str(tmp_path), "--max-age-days", "5"]) == 0
    assert "bugsigdb/full_dump_main.csv" in capsys.readouterr().out
    assert cli.main(["status", "--data", str(tmp_path), "--max-age-days", "20"]) == 0
    assert "bugsigdb/full_dump_main.csv" not in capsys.readouterr().out


@pytest.mark.parametrize("age", [-1, float("nan"), float("inf")])
def test_bad_age_threshold_refuses_before_creating_or_fetching(
    tmp_path, monkeypatch, age
):
    data = tmp_path / "new"
    monkeypatch.setattr(download, "run", lambda *a, **k: pytest.fail("fetched"))
    with pytest.raises(ValueError, match="finite.*non-negative"):
        mkg.prepare(data, max_age_days=age)
    assert not data.exists()
    with pytest.raises(ValueError, match="finite.*non-negative"):
        api.fetch(data, max_age_days=age)

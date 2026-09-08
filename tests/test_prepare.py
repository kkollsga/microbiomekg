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
    assert str(data) in report and "--missing" in report
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
    assert "bugsigdb/full_dump_main.csv" in report


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


def test_report_commands_round_trip_paths_with_spaces_and_quotes(tmp_path, capsys):
    data = tmp_path / "user's data"
    mkg.prepare(data)
    lines = capsys.readouterr().out.splitlines()
    commands = [s.strip() for s in lines if " --data " in s and "URL:" not in s]
    assert commands
    for command in commands:
        args = shlex.split(command)
        assert args[args.index("--data") + 1] == str(data)


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


def test_guidance_commands_run_without_an_activated_environment(
    tmp_path, monkeypatch, capsys
):
    import os
    import subprocess

    monkeypatch.setenv("PATH", "")
    mkg.prepare(tmp_path)
    commands = [
        line.strip()
        for line in capsys.readouterr().out.splitlines()
        if " status --data " in line
    ]
    assert len(commands) == 1
    proc = subprocess.run(
        shlex.split(commands[0]), env=os.environ.copy(), capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    assert "hmdb_metabolites.xml" in proc.stdout

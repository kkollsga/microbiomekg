"""Shared fixture paths and fixture-file readers.

Nothing here imports ``microbiomekg`` — these helpers must keep working
while the implementation is still missing, so that a test module fails with
a clear ImportError on the module under test rather than on its own scaffolding.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
TAXDUMP_MINI = FIXTURES / "taxdump_mini"
BUGSIGDB_MINI = FIXTURES / "bugsigdb_mini.csv"
MONDO_MINI = FIXTURES / "mondo_mini.obo"

# BugSigDB's export puts a licence banner on line 1, before the header.
BUGSIGDB_BANNER_LINES = 1


def read_bugsigdb(path: Path = BUGSIGDB_MINI) -> list[dict[str, str]]:
    """Rows of the BugSigDB fixture, as the source spells them.

    No NaN coercion: the source writes missing values as the literal string
    ``"NA"`` and a pandas read with default settings would turn that into a
    float column (docs/usecases-and-pitfalls.md C10, C16).
    """
    with path.open(encoding="utf-8", newline="") as fh:
        for _ in range(BUGSIGDB_BANNER_LINES):
            fh.readline()
        return list(csv.DictReader(fh))


def read_dmp(path: Path) -> list[list[str]]:
    """Fields of an NCBI ``.dmp`` file: ``tab-pipe-tab`` separated, trailing ``tab-pipe``."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        rows.append([f.strip() for f in line.split("\t|")])
    return rows


@pytest.fixture(scope="session")
def taxdump_dir() -> Path:
    assert TAXDUMP_MINI.is_dir(), f"missing fixture directory {TAXDUMP_MINI}"
    for name in ("names.dmp", "nodes.dmp", "merged.dmp", "delnodes.dmp"):
        assert (TAXDUMP_MINI / name).is_file(), f"missing fixture file {name}"
    return TAXDUMP_MINI


@pytest.fixture(scope="session")
def bugsigdb_rows() -> list[dict[str, str]]:
    return read_bugsigdb()


@pytest.fixture(scope="session")
def fixture_raw(tmp_path_factory) -> Path:
    """The fixture cuts laid out as a raw data root — ``bugsigdb/``,
    ``ncbi_taxonomy/``, ``mondo/`` — so a build can be pointed at it the way
    it is pointed at ``data/raw``. Every other source is absent, which is the
    skip path the build takes on a fresh clone."""
    raw = tmp_path_factory.mktemp("raw")
    (raw / "bugsigdb").mkdir()
    (raw / "bugsigdb" / "full_dump_main.csv").write_bytes(BUGSIGDB_MINI.read_bytes())
    (raw / "ncbi_taxonomy").mkdir()
    for f in TAXDUMP_MINI.iterdir():
        (raw / "ncbi_taxonomy" / f.name).write_bytes(f.read_bytes())
    (raw / "mondo").mkdir()
    (raw / "mondo" / "mondo.obo").write_bytes(MONDO_MINI.read_bytes())
    return raw

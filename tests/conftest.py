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

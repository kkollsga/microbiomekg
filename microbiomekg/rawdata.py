"""Locate raw source files under a raw root, whatever `fetch.py` called them.

The prep scripts take one ``--raw`` root so they share a CLI. What lives under
it varies: `fetch.py` writes ``data/raw/ncbi_taxonomy/`` and
``data/raw/bugsigdb/full_dump_main.csv``, while a test fixture may lay the same
files out as ``raw/ncbi/`` and ``raw/full_dump.csv``. These two functions
accept either, and return a clear error naming what they looked for rather than
failing later on a missing column.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["find_taxdump", "find_bugsigdb_dump"]

_TAXDUMP_DIRS = ("ncbi_taxonomy", "ncbi", "taxdump", "new_taxdump")
_DUMP_NAMES = ("full_dump_main.csv", "full_dump.csv")


def find_taxdump(raw: Path) -> Path:
    """The directory holding ``nodes.dmp``, searched from a raw root."""
    raw = Path(raw)
    candidates = [raw / d for d in _TAXDUMP_DIRS] + [raw]
    for c in candidates:
        if (c / "nodes.dmp").is_file():
            return c
    hits = sorted(raw.glob("*/nodes.dmp")) + sorted(raw.glob("*/*/nodes.dmp"))
    if hits:
        return hits[0].parent
    raise FileNotFoundError(
        f"no nodes.dmp under {raw} (looked in {', '.join(_TAXDUMP_DIRS)} and the root)"
    )


def find_bugsigdb_dump(raw: Path) -> Path:
    """The BugSigDB ``full_dump`` CSV, searched from a raw root.

    A file path is returned unchanged, so ``--raw <file>`` still works.
    """
    raw = Path(raw)
    if raw.is_file():
        return raw
    for parent in (raw / "bugsigdb", raw):
        for name in _DUMP_NAMES:
            if (parent / name).is_file():
                return parent / name
    hits = sorted(raw.glob("**/full_dump*.csv"))
    if hits:
        return hits[0]
    raise FileNotFoundError(
        f"no full_dump*.csv under {raw} (looked in bugsigdb/ and the root)"
    )

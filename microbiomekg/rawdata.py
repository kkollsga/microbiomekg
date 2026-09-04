"""Locate raw source files under a raw root, whatever ``fetch`` called them.

Every prep's ``run(raw, store, ...)`` takes the build's one ``--raw`` root. What
lives under it varies: ``microbiomekg fetch`` writes ``data/raw/ncbi_taxonomy/``
and ``data/raw/bugsigdb/full_dump_main.csv``, while a test fixture may lay the
same files out as ``raw/ncbi/`` and ``raw/full_dump.csv``. The two finders
accept either and fail naming what they looked for, rather than later on a
missing column.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["MissingInput", "find_taxdump", "find_bugsigdb_dump"]

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

    A file path is returned unchanged, so a test can pass the fixture CSV itself
    as ``raw`` (``tests/test_build.py`` does).
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
        f"no {' or '.join(_DUMP_NAMES)} under {raw} (looked in bugsigdb/ and the root)"
    )


class MissingInput(FileNotFoundError):
    """A prep's raw input is not on this machine.

    Raised by a prep's ``run()`` and caught by the build, which skips the
    source and prints the message. The message says what was looked for and,
    for a browser-only origin, where to get it.
    """

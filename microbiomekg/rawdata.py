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


def find_mondo(raw: Path, mondo: Path | None = None) -> Path:
    """``mondo/mondo.obo`` under ``raw``, or ``mondo`` when a caller names it.

    Three preps key their conditions on MONDO, so the file is declared in each
    of their ``RAW_INPUTS`` and its absence is a :class:`MissingInput` like any
    other: a build without it would write every disease under its source's own
    id and never join them, which is a different graph, not a degraded one.
    """
    path = Path(mondo) if mondo else Path(raw) / "mondo" / "mondo.obo"
    if not path.is_file():
        raise MissingInput(f"no mondo.obo at {path} (microbiomekg fetch --only mondo)")
    return path


class MissingInput(FileNotFoundError):
    """A prep's raw input is not on this machine.

    Raised by a prep's ``run()`` and caught by the build, which skips the
    source and prints the message. The message says what was looked for and,
    for a browser-only origin, where to get it. :class:`MalformedInput` is
    the same channel for a file that is there but not the shape the prep
    reads; the build catches both and reports which.
    """


class MalformedInput(MissingInput):
    """A prep's raw input is on this machine but is not what the prep reads:
    a sheet or header row it finds by name is gone, or a rule it derives from
    the file no longer reproduces the paper's own numbers.

    A skip with a reason, like an absent file, and reported apart from it —
    "present but malformed" is a different fix. Never an exit: one renamed
    header in one supplementary table must not end a multi-minute build with
    no report and no census.
    """

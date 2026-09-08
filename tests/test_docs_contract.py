"""The claims the tracked prose makes about *this repo*, executed.

``tests/test_skill_claims.py`` holds the agent-facing prose in
``microbiomekg/mcp/`` to the built graph. This module is the same idea for the
repo-shaped claims no graph can check: what the CLI's verbs actually take, and
whether ``docs/model.md`` §8's running tally agrees with its own table. Both
were false on 2026-09-08 — ``CLAUDE.md`` told a session to run ``microbiomekg
serve --data ./data``, which exits 2, and §8's prose and table were maintained
separately — which is why each one is a test rather than a proofread.

Every check here is offline and reads only tracked text, so it runs in CI where
the graph-backed suites self-skip.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "docs" / "model.md"

#: The tracked prose a human or an agent reads before running anything. The
#: adapters (``AGENTS.md``, ``.agents/``) are generated from the first two, and
#: are scanned anyway: a stale adapter is what a session actually reads.
PROSE_GLOBS = (
    "*.md",
    "docs/*.md",
    "docs/**/*.md",
    ".claude/skills/**/*.md",
    ".agents/**/*.md",
)

WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


def prose_files() -> list[Path]:
    seen: dict[Path, None] = {}
    for pattern in PROSE_GLOBS:
        for path in ROOT.glob(pattern):
            if path.is_file() and "_build" not in path.parts:
                seen[path] = None
    assert seen, "the prose scan found no files — a vacuous scan is not a gate"
    return sorted(seen)


def test_the_prose_scan_covers_the_files_a_session_reads():
    """A scan that stops finding files passes vacuously (R1)."""
    names = {p.relative_to(ROOT).as_posix() for p in prose_files()}
    for required in (
        "CLAUDE.md",
        "AGENTS.md",
        "README.md",
        "CHANGELOG.md",
        "docs/model.md",
        "docs/design/release-readiness.md",
    ):
        assert required in names, f"{required} is not in the prose scan"
    # The skill trees are gitignored local working state; when this checkout
    # has them (a developer machine) the scan must cover them too, and when it
    # does not (CI) their absence is the expected state, not a vacuous scan.
    if (ROOT / ".claude" / "skills").is_dir():
        assert ".claude/skills/release/SKILL.md" in names, "the skill tree is present but not scanned"


# --------------------------------------------------------------------------
# The CLI's verbs take what the parsers say they take
# --------------------------------------------------------------------------


def test_serve_takes_a_graph_and_refuses_a_data_directory():
    """The truth the prose below is measured against, read off the parser."""
    from microbiomekg import serve

    with pytest.raises(SystemExit) as exc:
        serve.main(["--data", "./data"])
    assert exc.value.code == 2
    # And the flag it does take, so this test cannot pass because `serve.main`
    # rejects everything.
    with pytest.raises(SystemExit) as exc:
        serve.main(["--graph", "/nonexistent/graph.kgl", "--help"])
    assert exc.value.code == 0


#: ``serve`` is the one verb that does not take ``--data`` — it takes
#: ``--graph``, because it serves a built graph rather than a data directory.
#: Prose that lists the four verbs and says "each over ``--data``" hands the
#: reader a command that exits 2.
SERVE_SENTENCE = re.compile(r"[^.]*\bserve\b[^.]*--data[^.]*\.", re.DOTALL)


def test_no_tracked_prose_says_serve_takes_a_data_directory():
    offenders = []
    for path in prose_files():
        for match in SERVE_SENTENCE.finditer(path.read_text(encoding="utf-8")):
            sentence = " ".join(match.group(0).split())
            # A sentence naming both verbs separately ("`build` over `--data`,
            # `serve` over `--graph`") is correct; it is the *shared* flag that
            # is the false claim.
            if "--graph" in sentence:
                continue
            offenders.append(f"{path.relative_to(ROOT)}: {sentence}")
    assert not offenders, "prose claims `serve` takes --data:\n" + "\n".join(offenders)


# --------------------------------------------------------------------------
# docs/model.md §8 — the running tally agrees with the table it summarises
# --------------------------------------------------------------------------

ITEM_ROW = re.compile(r"^\|\s*(\d+)\.\s(.+?)\|\s*(.+?)\s*\|\s*$", re.MULTILINE)
TALLY = re.compile(
    r"\*\*kglite [\d.]+ was cut for this list and closed (\w+) of the (\w+);"
    r"(?:.|\n)*?leaving (\w+)\.\*\*"
)
HEADER = re.compile(r"^(\w+) things the blueprint, the ontology", re.MULTILINE)


def section_8_rows() -> dict[int, str]:
    text = MODEL.read_text(encoding="utf-8")
    rows = {int(n): status for n, _label, status in ITEM_ROW.findall(text)}
    assert rows, "§8's item table was not found in docs/model.md"
    return rows


def test_section_8_tally_matches_its_table():
    text = MODEL.read_text(encoding="utf-8")
    rows = section_8_rows()
    closed = sum(1 for status in rows.values() if "**closed**" in status)
    stands = sum(1 for status in rows.values() if "**stands**" in status)
    assert closed + stands == len(rows), (
        "every §8 row states **closed** or **stands**; "
        f"{len(rows) - closed - stands} state neither"
    )

    header = HEADER.search(text)
    assert header, "§8's opening sentence no longer names its item count"
    assert WORDS[header.group(1).lower()] == len(rows), (
        f"§8 opens with {header.group(1)!r} items and tabulates {len(rows)}"
    )

    tally = TALLY.search(text)
    assert tally, "§8's tally sentence was not found — it is the claim under test"
    total, remaining = tally.group(2).lower(), tally.group(3).lower()
    assert WORDS[total] == len(rows), (
        f"the tally says {total!r} items, the table has {len(rows)}"
    )
    assert WORDS[remaining] == stands, (
        f"the tally says {remaining!r} remain, the table has {stands} standing"
    )


# --------------------------------------------------------------------------
# The build writes no CSVs, so the prose must not describe one
# --------------------------------------------------------------------------

#: kglite 0.16.23's ``files:`` section and ``frames=`` retired ``data/csv/`` and
#: ``tables.Writer``: every prep now hands the build in-memory frames. These
#: phrases each describe a CSV the build reads or writes *today*, so each one is
#: a false claim about the shipped pipeline. Historical narration ("the loader
#: streamed each junction CSV", §8 item 13) is correct and is not listed.
RETIRED_CSV_CLAIMS = (
    "every CSV column",
    "undeclared CSV column",
    "one junction CSV",
    "one relationship, one CSV",
    "one relationship and one CSV",
    "once per CSV",
    "CSV's logical row count",
    "raw → flat CSV",
)


def test_no_prose_describes_a_CSV_the_build_no_longer_writes():
    offenders = []
    for path in prose_files():
        text = path.read_text(encoding="utf-8")
        for phrase in RETIRED_CSV_CLAIMS:
            if phrase in text:
                offenders.append(f"{path.relative_to(ROOT)}: {phrase!r}")
    assert not offenders, (
        "prose describes a CSV the frames build does not write:\n"
        + "\n".join(offenders)
    )


#: kglite 0.17.0 closed both residues of §8 item 1: BM25 indexes a native list
#: as one document, and the ontology's ``property_types`` grammar accepts
#: ``list``/``array``. Present-tense prose saying otherwise is false; the
#: history is kept in the past tense.
RETIRED_LIST_CLAIMS = (
    "refuses a list-valued property",
    "grammar still accepts only",
    "is declared `any` there",
)


def test_no_prose_says_kglite_still_refuses_a_list_property():
    offenders = []
    for path in prose_files():
        text = path.read_text(encoding="utf-8")
        for phrase in RETIRED_LIST_CLAIMS:
            if phrase in text:
                offenders.append(f"{path.relative_to(ROOT)}: {phrase!r}")
    assert not offenders, (
        "prose says kglite still refuses a list property (closed by 0.17.0):\n"
        + "\n".join(offenders)
    )

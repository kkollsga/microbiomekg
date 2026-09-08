"""The two harness adapters say the same thing as the authority (RULES.md R7).

``CLAUDE.md`` + ``.claude/skills/`` are the authority; ``AGENTS.md`` +
``.agents/skills/`` are generated. Unsynced adapters rot into contradictory
instructions, and a repo with no ``.agents/skills/`` at all runs its Codex
sessions with none of the doctrine — both have happened elsewhere in this
estate.

``make check-adapters`` is the gate; this module is the same check wired into
the suite, so a hand-edited adapter fails ``make test`` too, plus the two
properties the estate's own ``rules/conform.py`` reads, so a change here cannot
pass locally and fail conformance.
"""

from __future__ import annotations

import subprocess

import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC = ROOT / "scripts" / "sync_agent_adapters.py"
CLAUDE_SKILLS = ROOT / ".claude" / "skills"
AGENTS_SKILLS = ROOT / ".agents" / "skills"

#: The skill trees are gitignored local working state (they never ship in
#: the public repository), so a checkout without them — CI — has no
#: authority tree to compare. The tests that read the trees self-skip with
#: this reason and are accounted in ci.yml, the same way the graph-backed
#: suites are; the self-test below builds its own fixture and always runs.
NO_SKILL_TREES = pytest.mark.skipif(
    not CLAUDE_SKILLS.is_dir(),
    reason="skill trees are gitignored local working state; not present in this checkout",
)


@NO_SKILL_TREES
def test_the_adapters_match_the_authority():
    proc = subprocess.run(
        [sys.executable, str(SYNC), "--check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert proc.returncode == 0, (
        f"the generated adapters have drifted from CLAUDE.md + .claude/skills/.\n"
        f"An adapter is never hand-edited: merge the improvement into the "
        f"authority and run `make sync-adapters`.\n{proc.stdout}{proc.stderr}"
    )


def test_the_mirror_gate_can_fail():
    """R1: the check above is worth nothing until it has been seen going red.

    The script's ``--self-test`` builds a fixture repo and breaks one thing at a
    time — a hand-edited conventions file, a hand-edited skill, a missing
    adapter, an orphan adapter, an empty authority tree — asserting the check
    fires on each. It also asserts the Authority block survived the rename
    substitution, because a substituted declaration inverts itself and tells
    the adapter's reader to edit the adapter.
    """
    proc = subprocess.run(
        [sys.executable, str(SYNC), "--self-test"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert proc.returncode == 0, f"{proc.stdout}{proc.stderr}"


@NO_SKILL_TREES
def test_conform_sees_two_equivalent_skill_trees():
    """What ``doctrine/rules/conform.py`` checks, checked here.

    It compares the two skill trees modulo ``AGENTS.md`` -> ``CLAUDE.md`` and
    **nothing else** — paths are deliberately not substituted, because a step
    naming ``.claude/skills/`` means both trees. Reproduced rather than
    imported: the doctrine repo is a sibling checkout that may not be present,
    and a gate that skips when its input is missing is not a gate.
    """
    ours = {p.relative_to(CLAUDE_SKILLS) for p in CLAUDE_SKILLS.rglob("*.md")}
    theirs = {p.relative_to(AGENTS_SKILLS) for p in AGENTS_SKILLS.rglob("*.md")}
    assert ours, ".claude/skills/ holds no SKILL.md files"
    assert ours == theirs, f"skill trees differ: {ours ^ theirs}"
    for rel in sorted(ours):
        want = (CLAUDE_SKILLS / rel).read_text().replace("AGENTS.md", "CLAUDE.md")
        have = (AGENTS_SKILLS / rel).read_text().replace("AGENTS.md", "CLAUDE.md")
        assert want == have, f"{rel} differs beyond the naming substitution"


def test_the_gate_target_reaches_the_dev_docs_bound():
    """R4, as ``conform.py`` reads it: a bound that no gate runs is not a bound.

    It looks for a ``check-dev-docs`` target reachable from ``gate``/``lint``/
    ``check`` — as a prerequisite or from the recipe body. A rename of either
    half would pass every other test in this repo and quietly drop the estate's
    only mechanical check on the gitignored working folder.
    """
    makefile = (ROOT / "Makefile").read_text()
    assert "\ncheck-dev-docs:" in makefile, "the Makefile has no check-dev-docs target"
    gate = next(line for line in makefile.splitlines() if line.startswith("gate:"))
    assert "check-dev-docs" in gate, f"`gate` does not depend on check-dev-docs: {gate}"

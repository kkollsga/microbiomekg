"""The agent-instructions layout is what the estate expects (RULES.md R7).

``AGENTS.md`` is the only instructions file, ``.agents/skills/`` the real skills
folder and ``.claude/skills`` a symlink to it. ``make check-layout`` is the
gate; this module wires the same check into the suite, plus the self-test that
proves the check can go red.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "check_agent_layout.py"

#: The skills folders are gitignored local working state, so a checkout without
#: them (CI) has no symlink to verify; the self-test and the tracked-file half
#: always run.
NO_SKILLS = pytest.mark.skipif(
    not (ROOT / ".agents" / "skills").is_dir(),
    reason="skills folders are gitignored local working state; not present here",
)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECK), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )


def test_the_layout_check_passes_on_this_checkout():
    proc = run()
    assert proc.returncode == 0, f"{proc.stdout}{proc.stderr}"


def test_the_layout_check_can_fail():
    """R1: a check is worth nothing until it has been seen going red."""
    proc = run("--self-test")
    assert proc.returncode == 0, f"{proc.stdout}{proc.stderr}"


@NO_SKILLS
def test_claude_skills_resolves_to_agents_skills():
    link = ROOT / ".claude" / "skills"
    assert link.is_symlink()
    assert link.resolve() == (ROOT / ".agents" / "skills").resolve()


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

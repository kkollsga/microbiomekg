#!/usr/bin/env python3
"""Check the agent-instructions layout, or prove the check can fail (R7).

``AGENTS.md`` is the only instructions file (Claude Code loads it where it would
load ``CLAUDE.md``), ``.agents/skills/`` is the one real skills folder, and
``.claude/skills`` is a symlink to it. Nothing is regenerated or compared.

The skills folders are gitignored, workstation-local state, so the symlink
half runs only where ``.agents/skills`` exists; the tracked half
(``AGENTS.md`` present, no ``CLAUDE.md``) always runs.

Usage::

    .venv/bin/python scripts/check_agent_layout.py             # gate
    .venv/bin/python scripts/check_agent_layout.py --self-test # prove it can fail
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def problems(root: Path) -> list[str]:
    found: list[str] = []
    agents = root / "AGENTS.md"
    if not agents.is_file() or agents.stat().st_size == 0:
        found.append("AGENTS.md is missing or empty")
    if (root / "CLAUDE.md").exists():
        found.append("CLAUDE.md exists; AGENTS.md is the only instructions file")
    real = root / ".agents" / "skills"
    link = root / ".claude" / "skills"
    if not real.is_dir():
        return found
    if real.is_symlink():
        found.append(".agents/skills must be the real folder, not a symlink")
    if not link.is_symlink():
        found.append(
            ".claude/skills is not a symlink; run: rm -rf .claude/skills && "
            "ln -s ../.agents/skills .claude/skills"
        )
    elif link.resolve() != real.resolve():
        found.append(f".claude/skills resolves to {link.resolve()}, not .agents/skills")
    return found


def self_test() -> list[str]:
    """Each break must be reported; the intact fixture must be clean."""
    failures: list[str] = []

    def fixture(tmp: str) -> Path:
        root = Path(tmp)
        (root / "AGENTS.md").write_text("# x\n")
        (root / ".agents" / "skills" / "s").mkdir(parents=True)
        (root / ".claude").mkdir()
        (root / ".claude" / "skills").symlink_to("../.agents/skills")
        return root

    def expect(label: str, mutate, want_problem: bool) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = fixture(tmp)
            mutate(root)
            got = problems(root)
            if bool(got) != want_problem:
                failures.append(f"{label}: expected problem={want_problem}, got {got}")

    def claude_md(r: Path) -> None:
        (r / "CLAUDE.md").write_text("x\n")

    def no_agents(r: Path) -> None:
        (r / "AGENTS.md").unlink()

    def real_claude(r: Path) -> None:
        (r / ".claude" / "skills").unlink()
        (r / ".claude" / "skills").mkdir()

    def wrong_target(r: Path) -> None:
        (r / ".claude" / "skills").unlink()
        (r / "elsewhere").mkdir()
        (r / ".claude" / "skills").symlink_to("../elsewhere")

    expect("intact layout", lambda r: None, False)
    expect("CLAUDE.md present", claude_md, True)
    expect("AGENTS.md missing", no_agents, True)
    expect("real .claude/skills folder", real_claude, True)
    expect("symlink to the wrong folder", wrong_target, True)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        failures = self_test()
        for line in failures:
            print(f"SELF-TEST FAIL: {line}", file=sys.stderr)
        print("self-test: every break was caught" if not failures else "")
        return 1 if failures else 0
    found = problems(ROOT)
    for line in found:
        print(f"FAIL: {line}", file=sys.stderr)
    if not found:
        print("agent layout ok")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())

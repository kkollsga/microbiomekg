#!/usr/bin/env python3
"""Regenerate the Codex adapters from the Claude authority, or prove they match.

Two agent harnesses share this repo. ``CLAUDE.md`` + ``.claude/skills/`` are the
**authority**; ``AGENTS.md`` + ``.agents/skills/`` are **generated adapters**
(RULES.md R7). An adapter is never hand-edited: an improvement found on either
side is merged into the authority and both regenerated from it, because a blind
sync over a divergent pair deletes the improvement that caused the divergence,
and no sync at all leaves the other harness following stale doctrine.

``--check`` is the gate. It regenerates into memory and compares byte-for-byte
with what is on disk, so *any* hand-edit of an adapter, any missing file and any
orphan file is a failure — there is no equivalence judgement to get wrong.

The rename rules, and why each is scoped the way it is:

* **The Authority paragraph is exempt from every substitution.** It names the
  authority literally in both copies. A substituted declaration inverts itself
  and tells the adapter's reader to edit the adapter — found independently in
  two sibling repos the day the procedure landed (R7).
* **In the conventions file only**, ``.claude/skills/`` becomes
  ``.agents/skills/`` and the title says Codex. That file is per-harness prose
  and nothing compares the two mechanically except this script.
* **In skill files, paths are never substituted.** ``rules/conform.py`` compares
  the two skill trees modulo ``AGENTS.md`` → ``CLAUDE.md`` and nothing else, so
  a substituted path would read as a divergence. A step that names
  ``.claude/skills/`` means both trees.

Usage::

    .venv/bin/python scripts/sync_agent_adapters.py            # regenerate
    .venv/bin/python scripts/sync_agent_adapters.py --check    # gate: fail on drift
    .venv/bin/python scripts/sync_agent_adapters.py --self-test  # prove --check can fail
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

AUTHORITY_DOC = "CLAUDE.md"
ADAPTER_DOC = "AGENTS.md"
AUTHORITY_SKILLS = Path(".claude") / "skills"
ADAPTER_SKILLS = Path(".agents") / "skills"

#: The paragraph exempt from substitution, identified by the marker it starts
#: with. It runs to the first blank line.
AUTHORITY_MARKER = "**Authority:**"

TITLE_FROM = "— Claude Code Conventions"
TITLE_TO = "— Codex Conventions"


def _split_authority(text: str) -> tuple[list[str], range | None]:
    """Lines of ``text``, plus the half-open line range of the Authority block."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(AUTHORITY_MARKER):
            j = i
            while j < len(lines) and lines[j].strip():
                j += 1
            return lines, range(i, j)
    return lines, None


def render_conventions(authority_text: str) -> str:
    """The conventions file as the Codex adapter reads it."""
    lines, block = _split_authority(authority_text)
    out = []
    for i, line in enumerate(lines):
        if block is not None and i in block:
            out.append(line)
            continue
        line = line.replace(TITLE_FROM, TITLE_TO)
        line = line.replace(AUTHORITY_DOC, ADAPTER_DOC)
        line = line.replace(".claude/skills/", ".agents/skills/")
        out.append(line)
    return "\n".join(out)


def render_skill(authority_text: str) -> str:
    """A skill file as the Codex adapter reads it: the doc rename, nothing else."""
    lines, block = _split_authority(authority_text)
    out = []
    for i, line in enumerate(lines):
        if block is not None and i in block:
            out.append(line)
            continue
        out.append(line.replace(AUTHORITY_DOC, ADAPTER_DOC))
    return "\n".join(out)


def _skill_files(root: Path) -> dict[Path, Path]:
    base = root / AUTHORITY_SKILLS
    if not base.is_dir():
        return {}
    return {p.relative_to(base): p for p in sorted(base.rglob("*")) if p.is_file()}


def planned(root: Path) -> dict[Path, str]:
    """Every adapter path this repo should hold, mapped to its expected content."""
    plan: dict[Path, str] = {}
    conventions = root / AUTHORITY_DOC
    if not conventions.is_file():
        raise SystemExit(
            f"sync: no {AUTHORITY_DOC} at {root} — nothing to generate from."
        )
    plan[Path(ADAPTER_DOC)] = render_conventions(
        conventions.read_text(encoding="utf-8")
    )
    skills = _skill_files(root)
    if not skills:
        # An empty scan is not a pass (R1): a repo that lost its skills tree
        # would otherwise generate one file and report a clean mirror.
        raise SystemExit(
            f"sync: {AUTHORITY_SKILLS} holds no files — refusing to report a mirror."
        )
    for rel, src in skills.items():
        plan[ADAPTER_SKILLS / rel] = render_skill(src.read_text(encoding="utf-8"))
    return plan


def check(root: Path) -> list[str]:
    """Differences between the adapters on disk and the ones the authority implies."""
    problems: list[str] = []
    plan = planned(root)
    for rel, want in plan.items():
        path = root / rel
        if not path.is_file():
            problems.append(f"{rel} is missing — regenerate with `make sync-adapters`.")
            continue
        have = path.read_text(encoding="utf-8")
        if have != want:
            n = sum(1 for a, b in zip(want.split("\n"), have.split("\n")) if a != b)
            problems.append(
                f"{rel} differs from what {AUTHORITY_DOC} implies "
                f"({n or 'a differing number of'} line(s)). An adapter is generated, "
                f"never edited: merge the improvement into the authority and rerun "
                f"`make sync-adapters` (R7)."
            )
    adapter_root = root / ADAPTER_SKILLS
    if adapter_root.is_dir():
        for path in sorted(adapter_root.rglob("*")):
            if path.is_file() and path.relative_to(root) not in plan:
                problems.append(
                    f"{path.relative_to(root)} has no counterpart under {AUTHORITY_SKILLS}."
                )
    return problems


def write(root: Path) -> list[Path]:
    plan = planned(root)
    written = []
    for rel, want in plan.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.read_text(encoding="utf-8") != want:
            path.write_text(want, encoding="utf-8")
            written.append(rel)
    adapter_root = root / ADAPTER_SKILLS
    if adapter_root.is_dir():
        for path in sorted(adapter_root.rglob("*")):
            if path.is_file() and path.relative_to(root) not in plan:
                path.unlink()
                written.append(path.relative_to(root))
    return written


def self_test() -> int:
    """Prove the gate fires on each way an adapter pair can be wrong (R1).

    A checker nobody has watched fail is not a checker. This builds a minimal
    repo, asserts it is clean, then breaks one thing at a time.
    """
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"

        def fresh() -> Path:
            if root.exists():
                shutil.rmtree(root)
            (root / AUTHORITY_SKILLS / "demo").mkdir(parents=True)
            (root / AUTHORITY_DOC).write_text(
                "# demo — Claude Code Conventions\n\n"
                f"{AUTHORITY_MARKER} `CLAUDE.md` + `.claude/skills/` are the authority;\n"
                "`AGENTS.md` and `.agents/skills/` are generated adapters.\n\n"
                "The skills (`.claude/skills/`) are described in CLAUDE.md.\n",
                encoding="utf-8",
            )
            (root / AUTHORITY_SKILLS / "demo" / "SKILL.md").write_text(
                "# demo\n\nSee CLAUDE.md and `.claude/skills/demo`.\n", encoding="utf-8"
            )
            write(root)
            return root

        if check(fresh()):
            failures.append(f"a freshly generated pair is not clean: {check(root)}")

        # The exemption is the point of the whole scheme: if the Authority block
        # were substituted, the adapter would tell its reader to edit itself.
        p = fresh()
        adapter = (p / ADAPTER_DOC).read_text(encoding="utf-8")
        if "`CLAUDE.md` + `.claude/skills/` are the authority" not in adapter:
            failures.append("the Authority block was substituted in the adapter")
        if "Codex Conventions" not in adapter:
            failures.append("the adapter title was not renamed")
        if "described in AGENTS.md" not in adapter:
            failures.append("prose outside the Authority block was not renamed")
        skill = (p / ADAPTER_SKILLS / "demo" / "SKILL.md").read_text(encoding="utf-8")
        if "`.claude/skills/demo`" not in skill:
            failures.append(
                "a skill path was substituted; conform.py reads that as drift"
            )
        if "See AGENTS.md" not in skill:
            failures.append("a skill's conventions-file reference was not renamed")

        p = fresh()
        (p / ADAPTER_DOC).write_text("hand-edited\n", encoding="utf-8")
        if not check(p):
            failures.append("check() passed a hand-edited AGENTS.md")

        p = fresh()
        (p / ADAPTER_SKILLS / "demo" / "SKILL.md").write_text(
            "# demo\n\nSee AGENTS.md and `.claude/skills/demo`.\nAn extra line.\n",
            encoding="utf-8",
        )
        if not check(p):
            failures.append("check() passed a hand-edited adapter skill")

        p = fresh()
        (p / ADAPTER_SKILLS / "demo" / "SKILL.md").unlink()
        if not check(p):
            failures.append("check() passed a missing adapter skill")

        p = fresh()
        (p / ADAPTER_SKILLS / "orphan.md").write_text("stray\n", encoding="utf-8")
        if not check(p):
            failures.append("check() passed an orphan adapter file")

        p = fresh()
        shutil.rmtree(p / AUTHORITY_SKILLS / "demo")
        try:
            check(p)
        except SystemExit:
            pass
        else:
            failures.append(
                "check() reported a verdict with an empty authority skill tree"
            )

    for f in failures:
        print(f"SELF-TEST FAIL  {f}")
    if failures:
        return 1
    print("sync_agent_adapters --self-test: OK — every failure mode was observed.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check", action="store_true", help="fail on drift instead of writing"
    )
    ap.add_argument("--self-test", action="store_true", help="prove --check can fail")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if args.check:
        problems = check(ROOT)
        for p in problems:
            print(f"FAIL  {p}")
        if problems:
            print(f"\nadapters: {len(problems)} divergence(s) from {AUTHORITY_DOC}.")
            return 1
        n = len(planned(ROOT))
        print(
            f"adapters: OK — {n} generated file(s) match {AUTHORITY_DOC} + {AUTHORITY_SKILLS}."
        )
        return 0

    written = write(ROOT)
    if written:
        for rel in written:
            print(f"wrote {rel}")
    else:
        print("adapters: already current.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

---
name: release
description: STUB — this repo publishes nothing. There is no remote, no package on PyPI, no tag and no CI. Invoking this skill reports that and points at the prerequisites in docs/design/library-pipeline.md; it must not bump a version, create a remote, push, or upload anything.
---

# release — not yet, and here is what is missing

**This repo has nothing to release, and this skill ships no procedure.** Say so
and stop. Do not bump `pyproject.toml`'s version, do not create a git remote,
do not push, do not tag, do not upload to PyPI, do not create a GitHub project.
Each of those is an irreversible outward-facing act needing the user's
in-the-moment approval for *that* act (`R6`), and none of them is authorized by
invoking this skill.

## Why there is nothing to release

- **No package.** `pyproject.toml` declares `version = "0.1.0"` as a
  placeholder for local installs. Nothing is published under the name
  `microbiomekg`, and the name has not been checked on PyPI.
- **No remote.** The git history is local-only. There is no CI:
  `.github/workflows/ci.yml` is written so it is correct the day a remote
  exists, but nothing runs it.
- **No data ships either, and that is a decision, not a gap.** 26% of
  evidence-bearing edges have no redistribution permission
  (`docs/evaluation.md` §4), and the clean CC0 cut drops the drug and
  resistance layers. What would ship is **the pipeline**, never the graph.

## The prerequisites, in order

**`docs/design/release-readiness.md` is the checklist** — seven ordered items,
each with its scope and what "done" means, none of them done. Read it rather
than this summary, and read `docs/design/library-pipeline.md` beside it for the
design the packaging items implement.

1. **GitHub repository** — the user creates the remote; an agent does not.
2. **CI** — `make gate` plus the full suite on Python 3.11–3.14, and a
   `scripts/build.py` smoke against an **empty** data directory that must
   succeed and report every source as absent. `.github/workflows/ci.yml` is
   written and inert until then. CI skips the 259 graph-backed tests, and a
   skip is not a pass.
3. **Package surface** — `microbiomekg/api.py` (`fetch` / `status` / `build`),
   `SourceStatus` with `how_to_get` as data, a console entry point, pyproject
   metadata, and a code licence. **The PyPI name is unverified.**
4. **PyPI publishing** — trusted publishing on a `v*` tag, wheel + sdist,
   artifact-set verification (`R9`), a clean-venv install of the *published*
   artifact. **This skill is un-stubbed only when this item lands.**
5. **ReadTheDocs** — Sphinx matching KGLite's stack, the four `docs/*.md` as
   guides, the reference generated from docstrings, the build a CI gate
   under `-W`.
6. **README, human-first** — Python API → Cypher → MCP.
7. **CHANGELOG + versioning rule** — Keep-a-Changelog with `[Unreleased]`,
   patch by default.

Three questions in the design doc are open and are planning-time decisions, not
release steps: whether `build` on an empty directory produces the NCBI-only
taxonomy graph or refuses; whether the MCP manifest and skills ship in the
package; and whether the `.kgl` build stamp belongs upstream in kglite.

## What to do when someone invokes this

Report the above in a few lines, name the first missing prerequisite, and offer
to run **`phased-plan`** on the library-packaging work — which is where that
list belongs. `dev-docs/todos.md` already carries the seven items as lean
backlinks into `docs/design/release-readiness.md`, in order.

**Rewrite this skill only when the repo actually publishes something**, and
then write it from the sibling flows (`../../Rust/KGLite/.claude/skills/release`,
`../../Rust/kglite-datasets/.claude/skills/release`) rather than from memory —
their preconditions, artifact-set verification (`R9`) and one-bump-per-push
rule (`R5`) are the parts that matter, and they were paid for.

---
name: clean-comments
description: Coordinator-run comment cleanup over a measured scope — the invoking agent measures comment density, briefs one sub-agent per dense file to delete zero-information comments, compress low-density ones and fix false claims (R17), then verifies the whole diff mechanically, never from worker self-reports. Deliberately smaller than a phased plan — no branch ceremony, no plan doc. Run on a subtree after a large change lands, when review keeps hitting stale comments, or on request.
---

# clean-comments

Make the comments and docstrings in a measured scope **true and lean**: delete
what carries no information, compress the rest to what it carries, fix comments
the code contradicts (`R17`), and never touch what the tooling reads (`R18`).

The steady state is `R17`'s same-change duty — a change that falsifies a nearby
comment corrects it in that change. This skill is for the **residue**, and a
heavy residue is itself the finding.

## 0. Shape of the run

The invoking agent is the **coordinator**: it measures, briefs, dispatches,
verifies and reports — and edits no comments itself. Sub-agents (**workers**)
do the edits, one file each, because de-duplication needs a whole-file read and
a self-report needs an independent checker. One exception: if measurement
returns ≤ 2 files, skip the workers and apply the brief yourself — a
coordinator with one worker is ceremony.

Invocation authorizes the whole run (`R12`): it ends in the report or a named
blocker, never in "workers are running".

## 1. Measure first, and be ready to stop

This repo is 100% Python, so comment volume is `#` lines **and** docstrings —
and the docstrings are where the volume is (several modules open with 20+ line
prose blocks). Count both:

```bash
# `#` comment lines per file
rg -c --no-messages '^\s*#' -g '*.py' <scope> | sort -t: -k2 -rn | head -30
# total lines per file, as the docstring proxy — read the head of both lists
rg --files -g '*.py' <scope> | xargs wc -l | sort -rn | head -30
```

Take the **head**: the files that jointly hold ~half the scope's comment lines.

**Stop rule, decided before counting (`R13`):** if the head is empty or
trivially small, report "already lean — nothing to do" and stop. A cleanup that
runs regardless of what measurement says is a formality with a diff attached. A
heavy head right after a recent cleanup is the finding — say that `R17`'s
same-change duty is being skipped.

## 2. Assemble the worker brief (once, fixed)

**The two tests, per comment paragraph** — *does this add a fact the reader
cannot get from the code or from an earlier paragraph?*

- Zero information → **delete**: restates the next line or the signature,
  generic banner, self-referential bookkeeping, dead scaffolding.
- Low density → **compress** to the information carried: repetition across
  paragraphs, throat-clearing, narration of the journey, over-explained
  mechanics, four variations of one example, hedging.

"Keep the fact, drop the label" is **not** the test — it preserves volume by
construction (231 files, −0.2%; the information test, 104 files, −12.4%).

**The floor — never delete:**

- why-not-what; invariants and preconditions;
- **the data-shape traps**, which are this repo's highest-value comments: `"NA"`
  is a literal string and a default pandas read turns it into a float column;
  which columns are multi-valued; why a `dtype` is pinned; why a fixture holds
  the exact rows it holds;
- **the "this looks wrong and is deliberate" comments**: `not_provided` and
  `unknown` as countable values, the parallel `taxon_condition` rows, the
  ambiguity ledger, the measured-negative relationships kept separate from
  their positives. Deleting one of these invites a "simplification" that
  destroys the evidence model;
- regression rationale in tests — the reason the test is not deletable;
- the reason a source is skipped or a row is rejected (the `MISSING_INPUT`
  branches, the reconciler's status strings): the audit gates cannot catch a
  wrong bail reason, because a wrong skip returns the same green.

**What reads our comments (`R18`) — hands off, or handle deliberately.** This
enumeration is maintained here; extend it in the same change that adds a
reader.

- **`mcp/microbiomekg.skills/*`** — the skill bodies and their frontmatter
  `description` are injected **verbatim** into the tool descriptions an agent
  reads. Published contract. Every number and existential phrase in them is
  checked against the graph by `tests/test_skill_claims.py`, so a reworded
  sentence is a *failing test*, not a style change. Falsehood-fixes only, and
  the matching claim in `mcp/claims/` moves with it.
- **`mcp/microbiomekg_mcp.yaml`'s `instructions:` and `overview_prefix:`** —
  same rule: prose the agent reads, checked by the same gate.
- **`mcp/claims/*.md`** — the claim annotations are *parsed* by
  `tests/skill_claims.py`. A malformed annotation is a claim nobody can run,
  which the gate treats as worse than no claim.
- **`_`-prefixed keys in `blueprints/*.json`** — comments the composer strips.
  They are the only place a fragment can explain itself; deleting one loses the
  explanation with no diff anywhere else.
- **Module docstrings passed to argparse** (`description=__doc__` — e.g.
  `scripts/build_blueprint.py`, `scripts/sync_agent_adapters.py`) — rendered
  verbatim as `--help`. Published contract; falsehood-fixes only.
- **`DEPENDS_ON` and the docstring above it in each prep** — the dependency is
  code, but the sentence saying *why* is what stops the next author reordering
  the build. Floor material.

**De-duplication: within-file only.** Keep the fullest statement at the
most-read location and point the others at it. A fact repeated *across* files
is flagged to the coordinator, never collapsed by a worker.

## 3. Calibrate — one worker, and this gate can fail (`R1`)

Dispatch one worker on one representative head file. Read its **full diff**
against the brief yourself. If it holds, fan out. If not, fix the brief and
calibrate on a different file; after two failed calibrations, stop and surface
the diffs to the user. This gate has failed for real: the first doctrine passed
231 files while moving volume 0.2%, and only a human read of the calibration
diff caught it.

## 4. Fan out

One worker per remaining head file, in parallel batches. Each dispatch is the
brief, the file path, and this contract:

- Read the entire file before editing anything.
- Comment and docstring lines only. Apply the two tests per paragraph; respect
  the floor and the reader list.
- Fix false comments — code-contradicted claims, and expired predictions ("a
  later phase will…", "once source X lands"), which this repo generates fast
  because sources land one at a time.
- Check that a docstring still describes **its own** function: an inserted
  helper leaves the previous docstring documenting the next item, and nothing
  complains (`R17`'s attachment corollary). Verify in the rendered surface —
  `help(obj)`, or `--help` for an argparse module — not in the source.
- Check fenced blocks in docstrings balance, tracking fence **width**: a
  narrower fence inside a wider one is literal content, and a parity count
  calls four unbalanced fences even.
- Return a structured result: lines deleted / lines compressed (from → to),
  false comments fixed, cross-file duplicates flagged, code defects noticed
  (not fixed), anything left untouched and why.

A worker that fails is retried once, then its file is reported unprocessed.
**Never hand a worker a bulk fixer script** — one matched every fence opener
and re-indented two well-formed blocks in user-facing docs. Hand-fix or revert.

## 5. Verify mechanically — the diff, never the self-reports

Worker summaries have been wrong: one claimed it left a published doc block
alone while two of its compressions were inside one. In this order:

1. **Comment-only diff check, before the formatter.** Parse both revisions
   (`git show HEAD:<file>` vs the worktree) with `ast`, strip docstrings from
   both, and compare the ASTs. Unequal → revert that file and report it.
2. **`.venv/bin/ruff format`** — for real, not `--check`: removing a comment
   moves code (a collapsed block, a re-wrapped call). Formatter-introduced
   motion is the only non-comment change allowed in the final diff.
3. **Re-run the gates that read comments:** `make gate` covers ruff and the
   blueprint composition; if anything under `mcp/` was touched, run
   `.venv/bin/python -m pytest -q tests/test_skill_claims.py
   tests/test_mcp_skills.py tests/test_mcp_manifest.py`. If a `blueprints/*.json`
   `_` key was touched, `scripts/build_blueprint.py --check` must still be
   clean. An unexplained failure reverts the file that caused it.
4. **`make test`** once at the end. A comment sweep that leaves the suite red
   is not a comment sweep.

## 6. Report

- **Deletion and compression separately, per file — never one percentage.** The
  rate splits by file character: a mechanical prep loses 25–38%, a
  specification file (`docs/model.md`-adjacent modules, `reconcile.py`,
  `skill_claims.py`) 2–11%, and both are correct. A −2% on a dense
  specification file is a success, not a shirk.
- Findings fixed in-run are part of the diff; anything larger — code defects
  workers noticed, cross-file de-dup decisions, a gap in the reader list above
  — goes through `add-todo`. Anything reported as a finding meets `R15`'s bar:
  a concrete failure, or it is not reported.
- Offload the long form to `dev-docs/temp/clean-comments-report.md` and give
  the path (the tier lifecycles are `dev-docs/README.md`, the canonical layout
  map — this skill does not re-describe the folder).

## Relationship to phased-plan

Not part of one, on purpose. A first-ever whole-tree audit wraps this in a
phased plan; for everything else this skill is complete on its own.

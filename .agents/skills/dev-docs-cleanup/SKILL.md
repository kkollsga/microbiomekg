---
name: dev-docs-cleanup
description: Tidy the gitignored dev-docs/ working folder — auto-purge time-boxed dirs, then run a todos.md-driven tidy (read only todos.md; reconcile misplaced plans/ files and stale/completed actions, reading a specific backlinked doc only when a check points at it), soft-deleting finished docs to dev-docs/bin/ and pruning their todos entries. Also resyncs the agent-instruction adapters. Run before a new phased-plan to start fresh, or after a large change lands.
---

# dev-docs cleanup

`dev-docs/` accumulates plans, intermediates and scratch (gitignored working
state). This skill tidies it: nothing is hard-deleted except the time-boxed
tiers — stale docs are soft-deleted to `dev-docs/bin/` with a 7-day grace, and
open actions are preserved in `dev-docs/todos.md`.

**Layout is `dev-docs/README.md` (the canonical map).** Durable dirs —
`plans/`, `designs/`, and `todos.md` — are never auto-purged; only `temp/` and
`bin/` are time-boxed.

## 1. Auto-purge the time-boxed dirs (always first)

```bash
mkdir -p dev-docs/temp dev-docs/bin
find dev-docs/temp -type f -mmin +1440 -print -delete   # ephemeral scratch, >1 day
find dev-docs/bin  -type f -mtime +7   -print -delete   # soft-deleted docs, >7 days
```

`make prune-dev` runs the same two purges alongside the regenerable tool caches
— use whichever is at hand; they agree by construction. Report what was purged,
or "nothing aged out".

Then read the bound: `make check-dev-docs`. It **fails** past the cap and never
deletes, because which tier a file belongs in — and whether it is reproducible
— is a judgement (`R4`).

## 2. Read `todos.md` — the only file read by default

`todos.md` is the index of open threads; its backlinks point to durable docs
under `plans/`. **Read only `todos.md` to start.** Do NOT read through
`plans/`, and **never read `designs/`** — design references are not
todos-driven and are out of scope. Open a specific doc *only* when a check
below points you at it.

## 3. Two checks, both driven by `todos.md`

**a) Misplaced files in `plans/`.** `ls dev-docs/plans/`. Every file there
should be backlinked from `todos.md`. For any file with **no backlink**, read
*that file only* and decide: a live thread missing from the index → add a
one-line backlink; finished or abandoned → soft-delete to `bin/`. When
genuinely unsure, surface it. (`designs/` and `README.md`/`todos.md` are
exempt — this check is `plans/`-only.)

**b) Stale / completed actions in `todos.md`.** Scan the entries. For any that
reads as done or outdated, **read its backlinked doc to confirm**, then:

- shipped / doc fully complete → move the doc to `bin/` and **remove the
  entry** (the code, the tests and git history are the record);
- partially done → trim the entry to only what is left;
- superseded / abandoned → drop it, keeping a one-line "Closed / dead" note
  only when it is worth not rediscovering.

Don't read a backlinked doc unless its entry looks stale.

## 4. Surface the plan

Report: what purged, misplaced `plans/` files found (+ a decision per each),
stale entries to prune, docs to soft-delete.

- **Run standalone** (e.g. before a `phased-plan`): wait for the user's
  go-ahead before moving files or editing `todos.md`. A simple proceed is
  enough.
- **Run inside an authorized flow**: perform the tidy directly, then report.
  The flow's invocation is the authorization.

## 5. Soft-delete processed files

On go-ahead, move stale files to `dev-docs/bin/` (7-day grace). Never delete an
active plan, `todos.md`, or anything the user chose to keep.

## 6. Resync the agent-instruction adapters

Two harnesses share this repo. `AGENTS.md` + `.claude/skills/` are the
**authority**; `AGENTS.md` + `.agents/skills/` are generated adapters (`R7`,
and the Authority line at the top of `AGENTS.md` says so literally in both
copies — that line is exempt from the rename substitution, because a
substituted declaration inverts itself and tells the adapter's reader to edit
the adapter).

```bash
make check-adapters     # regenerates into memory, diffs against disk
make sync-adapters      # regenerates for real
```

**A divergence is classified before either side is touched** (`R14`): an
*improvement* found in an adapter is merged into `AGENTS.md` /
`.claude/skills/` **first** and the adapter regenerated from it; *staleness* is
simply regenerated away. Never run a blind sync on a divergent pair — blind
sync deletes the improvement that caused the divergence, and no sync leaves the
other harness following stale doctrine. `make check-adapters` must pass
afterwards; it is also a `make gate` prerequisite, so drift cannot survive a
commit that ran the gate.

`AGENTS.md` is **tracked** here. A session that may not commit edits **neither**
side and files the reconciliation as a note for the repo's owner — a one-sided
fix to the editable adapter widens exactly the gap this step measures.

## 7. Doctrine drift (cheap, and worth it here)

Read `../../Rust/doctrine/VERSION` and `dev-docs/.doctrine-synced`. Equal →
say so and move on. Doctrine ahead → this is `phased-plan`'s doctrine-sync step,
not a cleanup task: report the gap and let the next plan replay the changelog.

## Output discipline

Under 400 tokens. If the stale-doc review is long, write the full report to
`dev-docs/temp/cleanup-report.md` and report that path.

## Relationship to phased-plan

`phased-plan` recommends running this skill first, so a new project starts from
a tidy `dev-docs/` and a current `todos.md`. Carried-over todos can then be
folded into the new plan — only with the user's go-ahead.

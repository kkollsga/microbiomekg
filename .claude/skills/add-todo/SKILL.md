---
name: add-todo
description: Capture work into the dev-docs backlog the right way — scope it, put the detail in a plans/ doc (reuse an existing one or create a new one), and add a lean backlink line to todos.md under the correct section. Handles both a single one-off item (`/add-todo <free-text>`) and a deeper body of analysis (research output, an audit, a review) that decomposes into several actionable items. The canonical authority on todo-entry shape — other skills (e.g. read-inbox) defer here for how a todo is written.
---

# add-todo

Capture work into the dev-docs backlog the right way, respecting the convention:

> **`dev-docs/todos.md` holds one lean backlink line per thread; the detail
> lives in a `dev-docs/plans/*.md` file.** Never put detail in `todos.md`;
> never leave a `plans/` doc unlinked.

The point is to capture fast *and* scope well, so the item is actionable later
without rediscovery. Do the work directly; ask only when a classification or
scope decision is genuinely ambiguous.

**This skill is the single authority on *how a todo entry is shaped*.** Other
skills that file todos (`read-inbox`, `clean-comments`, `phased-plan`) follow
the entry rules below rather than restating them.

## Two modes

- **One-off** — a single free-text item (`/add-todo <description>`). Run
  steps 1–6 once.
- **Batch / deeper analysis** — a body of findings (an evaluation, an audit, a
  review, inbox content) holding *several* actionable items. Decompose first
  (§0), then run the per-item logic for each.

## 0. Decompose (batch mode only)

Split the input into discrete, *independently actionable* items — each a single
change a future session could pick up alone. Before filing:

- **Drop non-actionable material** — background, confirmations, "no action"
  conclusions. A todo is something to *do*.
- **Group by theme.** Items sharing a subsystem (one source's prep + fragment +
  ontology module; the reconciler; the MCP surface) go in *one* `plans/` doc as
  sections — one backlink — not N scattered docs.
- **Dedup against the existing backlog** — read `todos.md` first; fold an item
  that extends an existing thread into that thread.
- **Order by priority/effort** so the backlink hooks read sensibly.

Then run steps 2–5 per item (step 1's index read happens once). Keep the report
to one line per filed entry.

## 1. Read the index + understand the ask

Read `dev-docs/todos.md` (its sections and existing backlinks) and
`ls dev-docs/plans/`. Parse the ask into: **type**, **the concrete change**,
and any **evidence** given.

## 2. Classify → target `todos.md` section

- **Surfaced defect / wrong behaviour** — a prep writes the wrong rows, an
  edge loses its evidence fields, a reconciliation picks a wrong id, a
  documented query stops returning its golden → `## Bugs (surfaced, not yet fixed)`
- **Enhancement / code health / refactor** → `## Engineering backlog (live)`
- **A new source, a source-format bump, a pipeline or fetch follow-up** →
  `## Source / pipeline follow-ups`
- **Something the kglite engine has to do** — the blueprint, ontology or Cypher
  surface cannot express it → `## Engine asks (kglite)`, and consider a
  `notify` to kglite rather than only a note here. `docs/model.md` §8 is the
  running list; keep the two consistent.
- **Deliberately deferred scope-creep** → `plans/consider-for-future.md` (the
  parking lot), backlinked from the relevant section.

## 3. Ground it (cheap, high-value)

For anything touching code, spend one or two `grep`/`Read` calls to **pin the
fix site** (`file:line`) and confirm it is real. For a claimed bug, confirm it
is a defect and not deliberate behaviour — several things here look wrong and
are load-bearing (`not_provided` as a countable value, the parallel
`taxon_condition` rows, the ambiguity ledger). Read the surrounding code and
tests. If the defect is really in **kglite**, say so: it belongs in kglite's
inbox, not only in this backlog. Convert any relative date to absolute.

## 4. Choose the detail home (reuse first)

- **Fits an existing `plans/` doc's theme** → append a section. Prefer this.
- **Substantial new standalone thread** → create `plans/<kebab-title>.md`.
- **Small deferred item** → append to `plans/consider-for-future.md`.

Scope the detail with these bullets (adapt to the item):

- **What it is** — the concrete change.
- **Why it matters (long-run)** — the leverage, not just the symptom.
- **Evidence** — the query, the row, the failing assertion, the counts.
- **Fix site + approach** — `file:line` + the shape of the change.
- **Fixture / test** — for a correctness bug, the checked-in fixture and the
  assertion the fix must land. Tests are offline and fixtures carry **real**
  NCBI ids (CLAUDE.md "Testing discipline").
- **Effort** — rough size.

## 5. Add the lean backlink

Append **one line** to the chosen section:

`- <short title> → [plans/<doc>.md](plans/<doc>.md) — <≤200-char hook with fix-site + effort>. Surfaced <date>.`

Match the terse style of the existing lines. Do not duplicate the detail.

## 6. Report

State: the section, the `plans/` doc (new vs appended), and the one-line
backlink — nothing more. Keep under ~200 tokens.

## Notes

- This skill **adds**; it never prunes. Triage of stale entries is
  `dev-docs-cleanup`'s job.
- Don't touch code, `pyproject.toml` or the version — this is backlog capture.
- Batch input is the norm for decomposed analysis. `read-inbox` lifts its
  actionable items as todos following these rules; it owns the inbox-specific
  routing, Status footer and archival, and does not restate todo shape.

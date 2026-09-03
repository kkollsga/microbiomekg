---
name: phased-plan
description: Run a large feature or refactor as a gated, phased project. Starts with a doctrine sync and an investigation phase (read-only agents mapping scale and impacted paths) — NOT standard plan mode — then builds a custom gated phased plan on a local branch and executes each phase autonomously (code → gate → targeted tests → commit) until done. There is no remote and no CI, so the plan doc and the local gate carry what a PR and CI would.
---

# Phased plan

For any large feature or non-trivial refactor: a new source, an evidence-model
change, a reconciliation overhaul, a rework of the MCP surface, the library
packaging in `docs/design/library-pipeline.md`. **Demand this skill** when the
user kicks off such work. Do **not** use standard plan mode (`EnterPlanMode` /
`ExitPlanMode`) — this skill builds its own gated plan instead.

## Working dir: `dev-docs/` (gitignored)

The canonical layout and lifecycle is **`dev-docs/README.md`** — read it; this
is only the phased-plan-relevant subset:

- This project's plan → **`dev-docs/plans/<slug>.md`** (durable).
- Design choices you weigh → **`dev-docs/designs/`** (durable).
- Open threads → a lean one-line backlink in **`dev-docs/todos.md`**.
- **Offload large output to `dev-docs/temp/`** (>1-day purge) and report the
  path instead of printing it.
- Heavy generated artifacts — a scratch graph, a full CSV set, a bench capture
  — go **outside the repo**, to the scratch dir `bench/README.md` names. Never
  into `data/csv/` or `graph/`: those are what `scripts/serve.py` serves and
  what `tests/test_acceptance.py` asserts its goldens against.

## No remote, no CI — what carries their weight

This repo has no GitHub project (`docs/design/library-pipeline.md` item 5).
There is no PR to hold the checklist and no CI to catch what a local gate
skips. Two consequences the plan must respect:

- **The plan doc is the checklist.** Tick phases in
  `dev-docs/plans/<slug>.md`; it is the only progress surface there is.
- **The local gate is the only gate.** `make gate` plus the targeted suites is
  not a relevance filter ahead of CI here — it is the whole net. Run the
  **full** `make test` at the plan's completion, over the union of everything
  the phases touched, and say in the report that you did. Never report a CI
  result; there is none (`R10`: green and not-attempted must not render
  identically).

`.github/workflows/ci.yml` exists and is written to be correct on the day a
remote does, but nothing runs it. Creating a remote or pushing to one is an
irreversible, outward-facing act and needs the user's in-the-moment approval
(`R6`); it is never part of executing a plan.

## Doctrine sync — first action of the run, before Phase −1

The estate's rules live in the sibling `doctrine` repo and are versioned. Pull
them forward before planning, so a plan is never built on doctrine this repo
has been told is superseded. This repo is a **consumer** (`R14`: oracle first,
the local copy second).

1. Read **`../../Rust/doctrine/VERSION`** and **`dev-docs/.doctrine-synced`**.
   If the marker is absent, create it with the current version and note in the
   report that this was a first sync.
2. **Equal → done.** The normal case, one file read. "We're probably current"
   is not the check.
3. **Doctrine ahead → read `../../Rust/doctrine/CHANGELOG.md` forward from the
   marker** and act on every newer entry by its action class:
   - **`[skills-update]`** — merge into this repo's **declared authority**
     (`AGENTS.md` + `.claude/skills/`) and regenerate the adapters in the same
     action (`make sync-adapters`; the procedure is `dev-docs-cleanup` §6).
     `make check-adapters` must pass afterwards. Never hand-port into an
     adapter. `AGENTS.md` is tracked here, so a session that may not commit
     edits **neither** side and files a note instead.
   - **`[local-sweep]`** — run the check the entry states. Clean → say so. **If
     it fails, the sweep becomes Phase 0 work of *this* plan** — scoped, listed
     and visible in the plan doc, never a silent side-task.
   - **`[info]`** — nothing to do.
4. **Write the new version to `dev-docs/.doctrine-synced` only after those
   actions completed.** A marker written first permanently hides the entry it
   skipped. If an item could not be actioned, the marker advances only once
   that item is in the plan — the plan is the record, not the marker.

## Phase −1 — Start fresh

Recommend the user run **`dev-docs-cleanup`** so we start from a tidy
`dev-docs/` and a current `todos.md`. Carried-over todos can be folded into
this plan — **only with the user's go-ahead.** If they decline, proceed.

## Phase 0 — Investigation (scale before commitment)

- **Do not enter plan mode.** Investigate first, plan second.
- **Read-only until approval.** Zero edits during Phase 0 and Phase 1 — no
  branch, no code, no file writes. Investigation goes through read-only
  `Explore` agents.
- Fan out investigator agents, **scaled to blast radius** — 1–2 for a medium
  change, more only for a genuinely large one. Have them report: the structure
  of the affected area, impacted paths and callers, hidden couplings, existing
  test coverage, a rough size estimate.
- **Know which of the four files a source change touches.** Adding or changing
  a source means `scripts/prep_<src>.py`, `blueprints/<src>.json`,
  `microbiomekg/ontology/<src>.py`, `tests/test_<src>.py` — and nothing shared.
  A plan that edits a shared file to accommodate one source is usually a plan
  that has missed the fragment framework (AGENTS.md).
- **Is it ours or the engine's?** If the work depends on something kglite
  cannot express, read the engine (`../../Rust/KGLite`, `kglite/__init__.pyi`
  is the API truth) and check `docs/model.md` §8 — that list is the running
  record of engine asks. An engine change is a `notify` to kglite, not a phase
  here.
- If this is bug-driven: **reproduce and confirm the root cause with evidence**
  before planning the fix. For a data defect that means the query and the rows,
  not a reading of the prep.
- **For a behaviour-preserving refactor, probe current behaviour first.** Prep
  one source against its fixture and read the CSV; run the affected Part D
  queries and capture the current answers. Don't trust your mental model.
- **Decide the safety net in Phase 0, not after writing the wrong one.** Ask:
  which existing test moves when this change breaks? If none does, the first
  phase writes one. For a source, that is `tests/test_<src>.py` plus the
  `tests/test_acceptance.py` rows-to-edges family; for prose in `mcp/`, it is
  `tests/test_skill_claims.py` and a claim in `mcp/claims/`.

## Phase 1 — Build the gated phased plan

- Write the plan to **`dev-docs/plans/<slug>.md`**.
- Number the phases. Each must be independently **runnable, testable,
  committable** (bisectable).
- For each phase, spell out: the change, the tests that prove it, and the green
  gate (`make gate` plus the *named* targeted suites).
- **A measuring phase carries its stop rule, written before it runs** (`R13`):
  the result that retires the item instead of implementing it. A measurement
  whose only possible outcome is "proceed" is a formality with a benchmark
  attached. A stop rule composed after the numbers are in is a
  rationalisation — its absence from the approved plan is the tell.
- No phase touches `pyproject.toml`'s version. Nothing here is published.
- Present the plan, then **invite revision** — ask the user to revise or
  approve, and loop on their feedback.
- **Hard stop — wait for an explicit go-ahead** before creating the branch or
  writing any code. A simple "proceed" is enough.
- Once approved, **do not pause between phases** (`R12`: an authorization is a
  mandate to complete). The run ends in the finished plan or a named blocker,
  never in a status report. "Tests are running" and "the commit is ready" are
  not endings.

## Phase 2 — Local branch

- Create a branch: `feat/<slug>`, `refactor/<slug>`, `fix/<slug>`. Never work a
  large project directly on `main`.
- There is no push and no PR. The plan doc holds the checklist.
- **Before the first phase commit, run the full `make test` once** and record
  the number. A long-lived branch that only ever ran targeted suites discovers
  its blockers all at once at the end; here there is no CI to discover them for
  you.

## Phase 3 — Execute each phase (the autonomous loop)

For every phase, in order:

1. Implement the phase's code **and its tests**.
2. **Local green gate before committing:**
   - `make gate` — adapters, bounds, ruff, `build_blueprint.py --check`, the
     two truth gates.
   - The **targeted** suites, chosen to catch *this phase's* change: the
     surface you touched plus its direct consumers. A prep edit →
     `tests/test_<src>.py` **and** `tests/test_acceptance.py`; an ontology or
     evidence change → `tests/test_ontology.py` + `tests/test_build.py`; a
     reconciler change → `tests/test_reconcile.py` + every source test that
     resolves names; anything in `mcp/` → `test_skill_claims`,
     `test_mcp_skills`, `test_mcp_manifest`.
   - **Rebuild the graph only when the phase changed what the graph contains**
     (`make build`, minutes). The truth gates read `graph/microbiomekg.kgl`, so
     a phase that changes the data and does not rebuild is testing the *old*
     graph — the same failure as testing a stale binary. Say which graph a
     result came from.
   - **A NEW GATE IS NOT TRUSTED UNTIL YOU HAVE SEEN IT FAIL** (`R1`). If the
     phase adds or changes a check — a test, an assertion, a claim, a script
     guard — break the thing it guards, confirm red, restore, and say so in the
     commit message. Reading a gate cannot tell you whether it works. Three
     ways a gate is born dead: **substring subsumption** (`assert "cmd" in
     block` also matches `cmd --self-test` — compare whole stripped lines),
     **comment subsumption** (the words you assert on also appear in the
     comment explaining them — strip comments first), and **a vacuous scan**
     (zero files found passes; assert the scan was non-empty).
   - **Verify the probe, not just the result.** A mutation that silently edited
     the wrong text makes a working gate look broken; an unchanged file makes a
     dead gate look alive. Confirm the subject actually changed.
   - **Four ways a command lies green** (`R2`): a pipeline reports its *last*
     stage's status, so `pytest … | tail` says 0 for a red run; `git add a b c`
     with one bad pathspec stages **nothing** and the next commit takes the old
     index looking entirely normal — read `git status --porcelain` back;
     `grep -c` exits 1 on a count of zero; a backgrounded command's result
     lives in its output artifact, not in the launcher's echo.
3. **Commit** the phase by explicit path (`feat(...)` / `fix(...)` /
   `refactor(...)`), one commit per phase. Never `git add -A`; never
   `git stash` (repo-global, and it has clobbered a sibling's work).
4. **Update the docs the phase falsified, in the same commit** (`R17`). A
   number in `README.md`, `docs/model.md`, `docs/usecases-and-pitfalls.md` or
   `mcp/` that this phase moved is now a false claim — and in `mcp/` it is a
   *failing test*, so this is not optional. Re-measure; never loosen the claim
   gate to make a sentence pass.
5. **Retire any `todos.md` action this phase completed**, applying
   `dev-docs-cleanup` §3b at phase-commit time rather than as a later pass.
6. Continue into the next phase.

Stop mid-plan only for a genuine blocker: an unfixable failure, an
architectural surprise invalidating a later phase, or an engine limitation
needing a kglite change. Surface it; don't push through.

**Bugs that surface mid-plan — fix them, don't step over them.**

- **In scope** (the source or subsystem you are touching): reproduce, confirm
  the root cause, then fix it as its **own bisectable phase** — `Phase Nb`,
  with its own red-first test.
- **Out of scope** (a different source, or a kglite bug): reproduce, confirm,
  then either file it via `add-todo` or `notify` kglite. Add a cheap fixture
  regression if one fits.

Either way, record it in the report-out.

## Phase 4 — Cost gate (only if the plan touched build, load or query cost)

A change to a prep, the composition step, the index set or a hot query path
gets a `bench/bench.py` capture before the plan is declared done; a plan that
touched none of those skips this. The protocol is `bench/README.md` and
AGENTS.md — release-mode wheel, the statistic the harness records per cell,
**unchanged-path control cells** as the drift meter, two agreeing runs, and one
retake for a verdict near its threshold. A *control* that regresses means the
instrument moved, not the code (`R11`).

**A capture must not write `data/csv/` or `graph/`.** The harness points its
build at a scratch dir outside the repo; a capture that rewrites the shipped
graph invalidates the goldens the truth gates assert. Check `git status` after
one: a capture taken while a fragment is being edited materialises that
in-flight edit into `blueprint.json`.

Record the numbers in `bench/results/` (tracked, durable — never deleted) and
note the machine state the capture was taken under (`R11`: a longitudinal
number carries its conditions).

## Report out (when the plan completes)

Under 400 tokens; link the plan doc for detail.

- **Phases** done, one line each, with commit shas.
- **The full-suite result** at completion — the number, and which graph it ran
  against.
- **Bugs surfaced** and each one's disposition: fixed in Phase Nb / filed to
  backlog / routed to kglite. Mandatory even if empty.
- **New or changed gates**, and the red you saw for each (`R1`).
- **Cost gate** result, or "not applicable — the plan touched no cost path".
- **`todos.md` changes**: retired, and carried-over items added.
- **Plan deviations** and why.

## Phase 5 — Ship

There is nothing to ship. This repo publishes no package and has no remote; the
`release` skill is a stub that says so and points at
`docs/design/release-readiness.md`, the seven ordered prerequisites. If the
user asks to publish, that is a new plan — and every outward-facing step in it,
creating the remote included, needs its own in-the-moment approval (`R6`).

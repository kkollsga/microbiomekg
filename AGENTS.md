# MicrobiomeKG — Codex Conventions

**Authority:** `CLAUDE.md` + `.claude/skills/` are the authority this repo's
agent instructions are regenerated from; `AGENTS.md` and `.agents/skills/` are
generated adapters (identical modulo the `CLAUDE.md` → `AGENTS.md`
substitution, which the Authority block itself is exempt from). Edit the
authority and regenerate in the same action — never edit an adapter.
`make check-adapters` proves the pair equivalent, and `make sync-adapters`
regenerates them.

An eleven-source microbiome knowledge graph on [kglite](../../Rust/KGLite),
**100% Python** — no Rust crate, no compiled extension of our own. kglite does
the graph work; this repo orchestrates prep, composition, load, audit and
report. Everything that ships lives under `microbiomekg/` — the preps, the
blueprint fragments, the MCP surface, the build — and `scripts/*.py` are thin
callers kept so the documented commands work from a checkout. `README.md` is the layout; `docs/model.md` is the graph model;
`docs/usecases-and-pitfalls.md` is the user contract.

The estate's numbered invariants live in `../../Rust/doctrine/rules/RULES.md`
and are cited here by ID (`R4`, `R15`, …) rather than paraphrased. The version
of that layer this repo last synced against is `dev-docs/.doctrine-synced`.

> The standing process rules are here; the working system lives in `dev-docs/`
> and `inbox/` (both gitignored) and is operated by the skills — see **The
> dev-docs / inbox / skills system** at the bottom.

## Build & test

```bash
make venv                 # provision .venv (pytest, pytest-timeout, ruff, build, kglite) + the package, editable
make check-install        # wheel + sdist → clean venv outside the repo → the three verbs run
make docs                 # sphinx -W: the guides + the generated reference (tens of seconds)
make gate                 # the fast gate — adapters, bounds, ruff, blueprint, claim gate (~30 s)
make test                 # the full suite: .venv/bin/python -m pytest -q
make build                # .venv/bin/python scripts/build.py  (ARGS='--with-kegg' to add flags)
make prune-dev            # bounded caches and scratch tiers, per R4
```

Targets resolve `.venv/bin/…` themselves — no activation. `make venv` installs
the package editable, so `.venv/bin/microbiomekg` (`fetch` / `status` /
`build` / `serve`, each over `--data`) and `import microbiomekg` work from the
checkout; `microbiomekg/api.py` is the Python form of the same three verbs.
There is **no build step for the code**: `make build` builds the *graph*, takes minutes and 7.5 GB
of operator-owned raw input, and is never part of a gate.

`make gate` is the pre-commit ceiling: it runs the adapter mirror, the
accumulation bounds, ruff (check + format), `scripts/build_blueprint.py
--check`, and the two truth gates (`tests/test_skill_claims.py`,
`tests/test_documented_queries.py`). It compiles nothing and rebuilds no graph.
It reads `graph/microbiomekg.kgl`, so on a tree with no built graph it **fails
with the build command printed** — it never skips (`R10`: green and
not-attempted must not render identically).

In flight, gate on what the change could break — the touched surface plus its
direct consumers (a prep edit → that source's `tests/test_<src>.py` *and*
`tests/test_acceptance.py`; a skill or manifest edit → `test_skill_claims` +
`test_mcp_skills` + `test_mcp_manifest`). The **full suite runs once** at a
program's completion over the union of its phases, not after each one.

**A gate may never silently no-op.** If a tool is missing the target fails with
the fix printed, and the tool is in `DEV_DEPS` so it is actually there. A gate
that can skip is a gate that has never run.

**There is no CI.** This repo has no remote and no GitHub project yet.
`.github/workflows/ci.yml` is written and correct but **inert — a file on disk,
not a live gate**; nothing runs it until a remote exists
(`docs/design/library-pipeline.md` item 5). Until then the local gate is the
*only* gate, which is why it must be able to fail and must never be skipped.
Do not report a CI result; there is none.

## Pure Python — and what that excludes

**This repo is 100% Python and stays so.** No Rust crate, no compiled
extension, no `maturin`, no workspace. That is a decision, not a stage:
`docs/design/library-pipeline.md` opens with it. kglite does the graph work and
arrives as a wheel; if something here needs to be fast, the answer is a better
query or an engine ask (`docs/model.md` §8), never a native module of our own.
This is where the repo differs from its nearest sibling, kglite-datasets, which
is Python + Rust.

So the gates are **Python gates** and nothing else: `ruff check` + `ruff format
--check`, `pytest`, the claim gate, the blueprint-composition check, and
`sphinx-build -W` over `docs/` (`make docs`, at a program's completion rather
than in `make gate`). There is
no type checker today — `mypy` is not installed, not configured and not run,
and "the gate runs mypy" would be a false claim. Adopting it is a deliberate
change that adds it to `DEV_DEPS`, to `make lint`, and to this paragraph in the
same commit.

**Estate rules that are Rust-shaped do not apply here, and saying so is
cheaper than re-deriving it every time:** the five-place workspace version
lockstep (there is one version, in `pyproject.toml`, and it is a placeholder);
`cargo` target-dir pruning and free-space gates (nothing here compiles);
cbindgen header drift and the C-ABI additive-only rule (there is no C ABI);
debug-vs-release extension profiles (there is no extension — the kglite wheel
is always a release build, which `bench/bench.py` asserts); `cargo
semver-checks`. When the release regime from the estate playbook is adapted
here it is the **Python-package** version — wheel + sdist, trusted publishing
on a tag, artifact-set verification, and a clean-venv `pip`/`uv` install of the
*published* artifact — not the multi-crate lockstep. The seven pre-release
items are enumerated in `docs/design/release-readiness.md`; none is done.

## The fragment framework — a source is four files, discovered not listed

**Adding a source is adding files, never editing shared ones.** A source is:

| file | what it carries |
|---|---|
| `microbiomekg/preps/prep_<src>.py` | raw → flat CSV in `data/csv/`, plus `DEPENDS_ON` and `RAW_INPUTS` |
| `microbiomekg/blueprints/<src>.json` | the node types and junction edges it writes rows into |
| `microbiomekg/ontology/<src>.py` | its audit rules and evidence mapping |
| `tests/test_<src>.py` | its fixture-backed tests |

Nothing lists them. Preps are globbed, ontology modules are walked with
`pkgutil`, fragments are globbed — so a source that forgets one of the four is
half-loaded rather than rejected, and its test file is the thing that notices.

- **`RAW_INPUTS` is what `status` reports on** — the raw files the prep reads,
  relative to `--raw`, in the layout `fetch` writes. `tests/test_sources.py`
  withholds each declared file and expects the prep to refuse by name, so the
  declaration cannot drift from the check.
- **`DEPENDS_ON` places a prep in the build**, not alphabetical order.
  `microbiomekg/pipeline.py` topologically sorts with cycle detection. Name order once
  loaded `IS_DRUG` with zero edges (`docs/model.md` §8).
- **Exit code 3 (`MISSING_INPUT`) means "my raw input is absent"** — a skip
  with a reason, never an error and never a half-load. A dependent of a skipped
  source is itself a skip with a reason. A skipped source is dropped from the
  *load* blueprint and the ontology, because a node type loaded empty gives its
  audit rules a 0/0 denominator — a gate that cannot fail (`R1`).
- **Fragments merge, they never override.** Declaring the same thing twice is
  how a source says "I write rows into this table too"; declaring more is
  additive; declaring the same key with a **different** value raises
  `FragmentConflict` naming both fragments. A last-writer-wins merger would
  turn a real disagreement about which CSV backs `Disease` into a silently
  different graph.
- **The checked-in `blueprint.json` is always composed from the whole fragment
  set**, never from the sources one machine happens to have. It is a tracked
  artifact with a drift gate (`tests/test_fragments.py`, and
  `scripts/build_blueprint.py --check` in `make gate`). A partial build writes
  its own `blueprint.load.json` beside the CSVs instead.

## The contract, and the gate that keeps the prose true

`docs/usecases-and-pitfalls.md` is **the user contract**, not a design note.
Part C's pitfalls each have a guard test; **Part D's twenty acceptance queries
and their goldens are asserted by `tests/test_documented_queries.py` and
`tests/test_acceptance.py`** — a documented query that stops returning its
golden is a failing test, not a stale doc.

**`tests/test_skill_claims.py` makes a false sentence in `microbiomekg/mcp/` a failing
test.** Every number and every existential phrase in a skill body, in a skill's
routing `description`, and in the manifest's two prose keys must be covered by
a claim in `tests/claims/`, and every graph claim is executed against the built
graph. The same gate covers the tracked pages `DOC_UNITS` in
`tests/skill_claims.py` names — `docs/benchmarks.md` today, sidecar under
`docs/claims/` — and it is extended one small measured page at a time, never to
`docs/model.md` wholesale, where narrative numbers would make it tiresome. It exists because on 2026-09-03 all 810 tests passed while the shipped
`metabolites_pathways` skill told agents there was no `CONSUMES` edge in a
graph holding 4,784 of them: the skill tests checked that the *Cypher* ran,
never that the *prose* was true.

**Never loosen this gate to make a sentence pass — re-measure the sentence.**
The four failures it can raise are all wanted: a claim disagreeing with the
data, a number covered by no claim, a claim filed under a section that no
longer exists, a malformed annotation. `test_the_gate_can_fail` keeps it
non-vacuous by running the scanner over hand-written defective text; if you
extend the scanner, extend that test in the same change (`R1`).

## The evidence model — the reason this graph exists

1. **Every association edge carries the provenance set** — `primary_source`,
   `source_record_id`, `source_licence`, plus the study design, assay, both
   group sizes and the citing paper. An edge that cannot say where it came from
   does not get written.
2. **`not_provided` and `unknown` are real, countable values — never nulls and
   never plausible defaults.** A source whose evidence model nobody has read
   gets `not_provided`. `unknown` is never silently promoted to
   `observational`. The point is that the gap stays *countable*.
3. **Nothing is stored as a score.** A confidence may be computed in a query
   from the components; it is never persisted as the evidence field.
   `evidence_level` describes **one observation, never a body of evidence** —
   replication is `count(DISTINCT r.study_id)` at query time.
4. **Direction is per study, never aggregated.** `direction` is our two-valued
   normalisation and `source_relation` keeps the source's own wording of the
   same fact, absent in exactly the same rows, so the normalisation is
   reversible. Forty reports on one pair stay forty reports, dissent included.
5. **Nothing is dropped silently.** A name that will not resolve, a row that
   will not map, a record that fails a check — each goes to a ledger CSV
   (`data/csv/unresolved_taxa.csv` and its siblings) with the reason. "Dropped"
   is a number this graph can report.
6. **Measured negatives are first-class.** The 61,127 "tested and nothing
   happened" edges are the population no comparable resource ships; a change
   that folds them into their positive relationship destroys the thing worth
   having here.

## Reconciliation doctrine

- **NCBI `tax_id` is the canonical key** (`Taxon.id`, integer).
  `microbiomekg/reconcile.py` is the single place a name or id becomes one, and
  it records *how*.
- **Ambiguity is never resolved first-wins.** An ambiguous name returns
  `status="ambiguous"`, `tax_id=None` and the full candidate tuple — the dump
  has 1,992 ambiguous name keys, and picking one would be a wrong answer
  wearing a confident face. The caller disambiguates with context this module
  does not have, or writes it to the ledger.
- **The verbatim source string is always kept** beside the resolved id
  (`source_condition`, `reported_compound`, `ReportedTaxon`, …). A rename must
  survive the reconciliation, and a query for what a source actually *said*
  must be answerable.
- `resolve()` never raises. `tax_id is None` with a status is the failure
  channel, and the ledger is where those land.

## The two flags, and why each exists

- **`--with-kegg` is a licence gate.** KEGG's licence forbids redistributing a
  graph carrying it, so the source has a loader and is off by default. A future
  restricted source takes the same shape.
- **`--with-vectors` is a cost gate.** The character-n-gram vector index buys
  query-time tolerance for a *misspelt* organism name and nothing else —
  load-time reconciliation matches exactly, through synonyms and authority
  stripping, and never touches it — while costing +82.6 s of build, `.kgl`
  46.7 MB → 212.7 MB, load 1.03 s → 2.41 s, serving RSS 1.2 GB → 3.7 GB.

**A default build says in its report that the lane was skipped and which flag
turns it on.** That is the rule for both flags and for any flag added later:
the report prices what was skipped, so a build with fewer sources than the
operator expected is never silent.

## `data/raw/` is operator-owned

7.5 GB of third-party raw input, gitignored, **never pruned automatically and
never rebuilt by a gate**. Re-fetching it costs hours and, for three origins,
cannot be automated at all: **HMDB and MiMeDB are behind Cloudflare and MASI
behind an expired certificate — those three are browser-only downloads.**
`microbiomekg/download.py` reports them as `manual-present` / absent and prints the
precise steps; it never pretends to fetch them.

So: no tool in this repo deletes anything under `data/raw/`. `make
check-data-bounds` *reports* its size and never touches it. If it needs
reclaiming, the operator does it knowing what a re-fetch costs
(`data/raw/<src>/PROVENANCE.md` records where each came from).

## Testing discipline

- **Red first.** A fix lands with the test that fails without it, in the same
  commit. A gate is not trusted until it has been **seen red** — break the
  thing it guards, watch it fail, restore (`R1`). Three ways a gate is born
  dead: substring subsumption (`assert "cmd" in block` also matches `cmd
  --self-test`), comment subsumption (the words asserted on also appear in the
  comment explaining them), and a scan that finds zero files and passes
  vacuously. Say in the commit message how you saw it red.
- **A reported status is not the result (`R2`).** A pipeline reports its last
  stage's status, so `pytest … | tail` says 0 for a red run. `grep -c` exits 1
  on a count of zero. `git add a b c` with one bad pathspec stages **nothing**
  and the next commit looks normal — read `git status --porcelain` back.
- **Fixtures carry real NCBI ids, never invented ones.** Every fixture under
  `tests/fixtures/` is a cut of the real source (`make_*_mini.py` scripts
  record the cut). A fabricated tax_id makes the reconciler's own contract
  untestable and will resolve to something real and wrong the day the dump
  moves.
- **Every test carries a 120 s hang ceiling** (`pytest-timeout`, in
  `pyproject.toml`). A test that hits it is a FAILED test — fix the hang, never
  raise the ceiling. The slowest test in the suite is ~2 s.
- **Tests are offline.** A test builds from a checked-in fixture, never a live
  fetch. The full-graph suites read the built `graph/microbiomekg.kgl`.
- A skipped test is not a pass. The vector-lane skips are the only governed
  ones, and each prints the flag that turns it on.

## Every file accumulation has a bound and an owner (`R4`)

Any path the tooling writes outside git carries a documented lifetime and
something that reports or enforces it. Adding a file-writing step without
pointing it at a bounded tier — **in the same change** — is not allowed.

| path | size | bound | owner |
|---|---|---|---|
| `data/raw/` | 7.5 GB | **none — never pruned automatically** | the operator; `make check-data-bounds` reports only |
| `data/csv/` | ~264 MB | regenerated per build; `microbiomekg/pipeline.py` empties it first | the build |
| `graph/*.kgl` | 47 MB (213 MB with `--with-vectors`) | one file, overwritten per build | the build |
| `bench/results/` | small, **tracked** | the longitudinal record — never deleted; heavy capture output goes to the scratch dir `bench/README.md` names | `make check-data-bounds` warns past 5 MB |
| `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `__pycache__/` | 112 MB + caches | regenerable | `make prune-dev` |
| `docs/_build/` | ~16 MB | regenerated by every `make docs` | `make prune-dev` |
| `dev-docs/temp/` | scratch | **purged > 1 day** | `dev-docs-cleanup`, `make prune-dev` |
| `dev-docs/bin/` | soft-deletes | **purged > 7 days** | `dev-docs-cleanup`, `make prune-dev` |
| `dev-docs/` (total) | — | `make check-dev-docs` **fails** past 256 MB | you; it never deletes |
| `inbox/read/` | archive | **purged > 7 days**, and only entries carrying the Status footer | `read-inbox` |

`make check-dev-docs` and `make check-data-bounds` are prerequisites of `make
gate`, so the bound runs at working cadence rather than at a milestone — a
bound checked only at milestones is not a bound (`R4` corollary).

## Working style

- **Understand before changing.** Reproduce with evidence before fixing; probe
  real behaviour with a scratch script rather than trusting your mental model.
  For a loader that means prepping one source against its fixture and reading
  the CSV, not reasoning about the CSV.
- **Is it ours or the engine's?** A wrong graph can come from our mapping *or*
  from a kglite bug. Isolate which before fixing — an engine bug is a `notify`
  to kglite (`../../Rust/KGLite/inbox/`), not a workaround this repo pretends
  is a design. `docs/model.md` §8 is the running list; kglite 0.16.22 was cut
  for it and closed eight of twelve items.
- **Offload, don't print.** Long output (dumps, graph inspections, triage
  write-ups) goes to `dev-docs/temp/` and you report the path.
- **Keep responses tight** (~400 tokens); link a file for detail.

## Code health

- **No bugs left behind.** A pre-existing bug found while working is fixed in
  the same change, or surfaced explicitly (a todo, a `notify`) — never stepped
  over. Before "fixing", confirm it is a defect and not deliberate: read the
  surrounding code and tests. Several things here that look wrong are load-
  bearing (the `not_provided` values, the parallel `taxon_condition` rows, the
  ambiguity ledger).
- **Fixing a bug — scan for the class.** Eleven preps share a shape; the
  reported symptom is rarely the only instance.
- Factor a function past ~80 lines or 3+ unrelated concerns. Prefer small named
  strategy functions over long if/else chains.
- **A comment is a claim, and a false claim is a defect (`R17`).** A change
  that falsifies a nearby comment corrects it in the **same** change; a change
  through commented code deletes what carries zero information and compresses
  what carries little. Deletion has a floor: why-not-what, invariants, the
  data-shape traps (`"NA"` is a string, not a NaN), regression rationale in
  tests, and anything under `R18`.
- **A comment the tooling parses is load-bearing (`R18`).** In this repo:
  `microbiomekg/mcp/microbiomekg.skills/*` bodies and frontmatter `description`s are
  injected verbatim into the tool descriptions an agent reads and are checked
  by `tests/test_skill_claims.py`; `tests/claims/*.md` and `docs/claims/*.md`
  annotations are parsed by `tests/skill_claims.py`; `_`-prefixed keys in `microbiomekg/blueprints/*.json` are
  comments the composer strips; a module docstring passed to argparse
  (`description=__doc__`, e.g. `scripts/build_blueprint.py`) is rendered
  verbatim as `--help`. The `clean-comments` skill carries the maintained
  enumeration — extend it there when a new reader appears.

## Code review — report what is broken, not what you would have written

**A finding names a concrete failure** (`R15`): the input or state, and the
wrong outcome it produces — a wrong graph, a wrong count, a dropped row, a
claim the code or the data contradicts, a broken contract with a caller or with
`docs/usecases-and-pitfalls.md`, a gate that cannot fail. **"No findings" is a
valid review**, and a good one.

**Design, structure, naming, "consider using X", "this won't scale" are not
findings at review — they are mis-staged.** Their venue is planning: the
`phased-plan` investigation and plan approval is where "I would have designed
this differently" is invited, argued and settled, before the code exists. After
approval, review measures the implementation against *that plan* and against
correctness, never against the reviewer's alternative design.

**A finding that cannot state its failure case is removed, not downgraded.**
"Minor: consider extracting this" is a preference wearing a label.

**One narrow exception:** citing a rule this project declared *before* the diff
existed — the four-file source shape, the claim gate, the evidence-model rules,
the offline-tests rule, the ~80-line ceiling — naming both the rule and the
violating line. That is enforcement, not taste.

## Commits & releases

Commit format: `type: short description` (`feat`, `fix`, `docs`, `refactor`,
`test`, `chore`). Stage **by explicit path** — never `git add -A`, and never
`git stash` (it is repo-global and has clobbered a sibling's work). Read
`git status --porcelain` back after staging.

- **Never work a large project directly on `main`** — branch (`feat/…`,
  `refactor/…`, `fix/…`), one commit per bisectable phase. There is no remote,
  so there is no PR and no CI to track: the branch is local, and the
  `phased-plan` skill says what replaces the PR checklist.
- **Nothing here is published.** No PyPI package, no remote, no tag, no
  licence chosen yet. `pyproject.toml`'s `version = "0.1.0"` is a placeholder
  and stays one until the library release happens. The seven things that have
  to land first are `docs/design/release-readiness.md`; the `release` skill is
  a **stub** pointing there.
- **One version bump per push** (`R5`) and **patch by default** — a minor or
  major only when the release invocation names one — apply from the day a
  remote exists, not before.
- **Publishing is irreversible and needs in-the-moment authorization**
  (`R6`) — and that includes creating a remote, pushing to one, filing an
  issue, or uploading to PyPI. None of those happen without the user asking for
  that act, in the turn it happens. Plan approval and skill invocation are not
  approval.
- **Commit messages are public.** Describe the mechanical change; keep
  positioning and internal motivation out of them.
- **An agent worktree lives in `../MicrobiomeKG-worktrees/<name>`** — a sibling
  directory holding all of them, never loose beside the real projects under
  `Python/`. That directory exists only while worktrees are in progress and is
  deleted when the last one is removed. A worktree with uncommitted work is
  never removed without its `git diff` saved and a `todos.md` entry pointing at
  it. Note that a worktree does **not** get `data/raw/` or `graph/` — both are
  gitignored — so anything graph-backed must run in the main checkout or point
  `--raw` at the real directory.
- Co-author trailer per the harness convention.

## The dev-docs / inbox / skills system

A gitignored **working folder + cross-project inbox + seven skills** that
operate them. Two canonical layout maps are the source of truth; the skills
point at them instead of re-describing the folders, so nothing drifts:

- **`dev-docs/README.md`** — the working-folder map: every dir, its lifecycle
  (durable vs time-boxed), and "where does X go". **Read it first.**
- **`inbox/README.md`** — the cross-project channel map: the `unread/`→`read/`
  lifecycle, the filename schema, the routing rule.

The skills (`.agents/skills/`):

- **`add-todo`** — capture work into `dev-docs/todos.md` + a `plans/` detail
  doc. The single authority on todo-entry shape.
- **`phased-plan`** — run a large change as gated phases: doctrine sync →
  investigate → plan → local branch → autonomous test/commit loop. No PR or CI
  ceremony, because there is no remote.
- **`dev-docs-cleanup`** — purge the time-boxed tiers, tidy `todos.md`,
  soft-delete stale docs to `bin/`, resync the adapters.
- **`read-inbox`** — triage `inbox/unread/` into durable detail + lean
  backlinks; route items to the party who can act.
- **`notify`** — send a note to another project's inbox. Workspace root is
  `/Volumes/EksternalHome/Koding`; the usual target is **kglite**
  (`../../Rust/KGLite/inbox/`).
- **`clean-comments`** — coordinator-run comment cleanup over a measured scope
  (`R17`/`R18`), with the reader enumeration this repo's tooling needs.
- **`release`** — a **stub**. This repo publishes nothing; the skill says so
  and points at `docs/design/library-pipeline.md`'s prerequisites.

**Skill mandates:** demand `phased-plan` for any large feature or refactor (not
plain plan mode); file backlog via `add-todo`; process the inbox via
`read-inbox` / `notify`. Durable detail lives in the linked `plans/` /
`designs/` doc, never inline in `todos.md`.

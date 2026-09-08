# Release readiness — what stands between this tree and a published package

Status: **0.1.0 published and verified 2026-09-09.** The
[GitHub release](https://github.com/kkollsga/microbiomekg/releases/tag/v0.1.0)
points at the release commit, and all three jobs in the
[publish workflow](https://github.com/kkollsga/microbiomekg/actions/runs/34287869780)
succeeded. PyPI serves the expected wheel and sdist with verified hashes; an
independent clean install reported version 0.1.0 and passed the CLI status
table, `prepare`, and empty-build checks. Read the Docs `stable` and `latest`
builds 34460335 and 34460318 succeeded at
`05e4a055ffe4d8eab17da1b459d603ddbbb3207e`, and the stable guide serves HTTP
200. Companion to
[library-pipeline.md](library-pipeline.md), which is the *design* — this is the
*checklist*. Tracked here rather than in `dev-docs/` because `dev-docs/` is
gitignored and unbacked, and `dev-docs/todos.md` carries one lean backlink per
item into this file.

Nothing here is authorization to do what is left. Tagging and publishing are
irreversible outward-facing acts that need the user's approval in the turn they
happen (`R6`); pushing a branch and opening a PR against the repo's own remote
became routine flow when §1 landed.

The order matters: each item's "done" depends on the one above it.

---

## 1. GitHub repository

**Scope.** A remote for a history that has never left this machine. **The user
creates it** — an agent does not create a repository, and does not push to one
it did not see the user ask for.

**Done 2026-09-08.** `github.com/kkollsga/microbiomekg` exists, the local
default branch was renamed `master` → `main` before the first push (CI triggers
on `main` only, so pushing `master` would have run nothing and looked quiet
rather than red), and the full history is pushed. `phased-plan` has its PR half
back: branch → `gh pr create --draft` → phases as commits → batched pushes with
`make gate` before each → required checks green → merge and delete the branch.

**Still the owner's, not an agent's:** branch protection on `main` — require a
PR and require the seven check names CI reports (`gate (ruff, adapters, bounds,
blueprint)`, `pytest (py3.11–3.14, graph-backed suites skipped)` ×4, `sphinx -W
(the guides and the generated reference)`, `build against an empty data
directory`) — plus the repository description and topics.

## 2. CI

**Scope.** GitHub Actions running `make gate` and the **full** pytest suite on
a Python matrix — **3.11 to 3.14** (`requires-python = ">=3.11"`, and the local
venv is 3.14, so the top of the range is the one actually in use and the bottom
is the one nothing has ever run). Plus the smoke build the design doc's rule 2
demands: `scripts/build.py` against an **empty** data directory, which must
**succeed** and report **every** source as absent. That is the test that proves
"absent means skipped, loudly" rather than "absent means a half-built graph".

Two things the workflow must not paper over:

- **The graph-backed suites self-skip in CI.** Measured on the first run
  (`a53ac8e`, py3.12): with no `graph/microbiomekg.kgl`, the suite is *1,013
  passed, 409 skipped* against *1,407 passed, 15 skipped* locally. Those 409
  are the acceptance goldens, the documented queries and the claim gate — the
  repo's most valuable tests. **A skip is not a pass** (`R10`), so CI prints
  the skip count and the job says in its name what it does not cover, until
  item 3's `status`-driven smoke build gives CI a graph to assert against.
- **The 120 s per-test ceiling** (`pytest-timeout`, `pyproject.toml`) is the
  hang detector, not a budget. A test that hits it in CI is a FAILED test; the
  ceiling is never raised to make a job green.

`.github/workflows/ci.yml` carries four jobs — `gate`, `tests`, `docs` and
`smoke` — and runs on every push to `main` and every PR against it.

**The empty-directory smoke build is in it** (the `smoke` job), and the
build it asserts on behaves as rule 2 wants since 2026-09-03: an empty
directory is the fresh-clone state, so `build.py` exits 0, names every source
as skipped with the file it wanted, and writes no graph — "nothing loaded" is
printed rather than an empty `.kgl` that reads as built. A directory holding
only the taxdump builds the Taxon spine and says "taxonomy-only". The defect
that blocked this — every prep routed a missing taxdump through argparse, exit
2, which the build reads as fatal — is closed: `microbiomekg.rawdata.missing_input`
is the one door, and `tests/test_build_pipeline.py` holds all eleven preps and
both build shapes to it, offline.

**Done 2026-09-08.** The first push to `main` (`a53ac8e`) ran all seven jobs
green in 51 s: the gate's data-free steps, the four-version matrix, `make docs`
under `-W`, and the smoke build. The skip accounting is in the summary and the
measurement moved with the suite — py3.12 reported **1,013 passed, 409 skipped**
of 1,422 collected, against **1,407 passed, 15 skipped** locally. Those 409 are
the acceptance goldens, the documented queries and the claim gate; they run
only where a graph exists, which is why `make gate` stays the whole net for
them.

## 3. Package surface

**Scope.** What `library-pipeline.md` specifies, in its order:

- `microbiomekg/api.py` exposing `fetch` / `status` / `build`, with
  `scripts/*.py` becoming thin callers of the API rather than the reverse.
- `status` as a real object — `SourceStatus(state ∈ {absent, present, stale,
  manual}, path, how_to_get, licence)` — moving `fetch.py`'s manual-source
  instructions out of print statements and into data.
- A console entry point (`microbiomekg = microbiomekg.cli:main`) so the three
  verbs work from a shell.
- `pyproject.toml` metadata: description, readme, keywords, classifiers,
  project URLs — and a **licence**. The siblings (kglite, kglite-datasets) are
  `license = "MIT"` with `license-files = ["LICENSE"]`; match them unless there
  is a reason not to. The licence covers **the code only** — no data and no
  built graph ships, because 26% of evidence-bearing edges have no
  redistribution permission (`docs/evaluation.md` §4).
- ~~The PyPI name `microbiomekg` is unverified.~~ Checked 2026-09-03:
  `https://pypi.org/pypi/microbiomekg/json` → 404. Unclaimed; re-check on the
  day of item 4, since nothing here reserves it.

**Done 2026-09-03**, except the push: `microbiomekg/api.py` (`status` /
`fetch` / `build` over one data directory, `build` returning a `BuildResult`
with the kglite graph and a `BuildReport`), `microbiomekg/sources.py`
(`SourceStatus`), `microbiomekg/cli.py` behind the `microbiomekg` console
script with `fetch` / `status` / `build` / `serve`, hatchling metadata, MIT
`LICENSE`, and `make check-install` — the wheel + sdist built, installed into a
clean venv outside the repo root, and the three verbs run there against an
empty directory. The PyPI name `microbiomekg` answered 404 on 2026-09-03:
unclaimed, not reserved. Project URLs are deliberately absent until §1 gives
them something to point at.

## 4. PyPI publishing

**Scope.** A trusted-publishing workflow gated on a `v*` **tag** push (never on
a branch push), building both a **wheel and an sdist**. After publish,
**verify the artifact set, not the version** (`R9`): a version query answers
"did something publish", never "did everything publish", and an upload step
with no fail-on-empty setting can upload nothing from a green build. Verify the
tag exists on both sides at the same commit, and install the published artifact
into a clean venv (`uv pip install microbiomekg==<v>`) outside the repo root,
so the local package cannot shadow it.

The **`release` skill became the active procedure after 0.1.0 was verified**,
using the siblings' preconditions, artifact-set verification and
one-bump-per-push rule (`R5`).

**The workflow is written** — `.github/workflows/publish.yml`, gated on
`push: tags: ['v*']` and nothing else, three jobs: `build` (wheel + sdist, with
both asserted present and the tag asserted to match the built version),
`publish` (the only `id-token: write` in the file, doing nothing but the
upload), and `verify` (no checkout, a clean venv, `pip install
microbiomekg==<tag>` from the index, the import and `microbiomekg status` run
there, then both `bdist_wheel` and `sdist` asserted present on the release).
It declares **no** `environment:`. `tests/test_packaging.py` holds it to that
shape, because otherwise its first execution would be the release itself.

**Configured 2026-09-09:** the repository owner created the pending publisher
for project `microbiomekg`, owner `kkollsga`, repository `microbiomekg`,
workflow filename `publish.yml`, with the environment name empty to match the
workflow. The project still answered 404 before the first publication.

**Done when:** a tag publishes a wheel + sdist, the artifact set is verified,
and a clean-venv install of the published package runs `microbiomekg status`.

## 5. ReadTheDocs

**Scope.** A `.readthedocs.yaml` plus a Sphinx build, matching KGLite's stack so
the estate has one: `sphinx`, `furo`, `myst-parser` (the docs are Markdown),
`sphinx-autoapi` for the generated API reference, `sphinx-copybutton`.

The four existing docs become the guides —
`docs/usecases-and-pitfalls.md` (the user contract),
`docs/model.md` (the graph model),
`docs/sources.md` (per-source licence and provenance),
`docs/evaluation.md` (the honest verdict) — and the API reference is generated
from the `microbiomekg/` docstrings, so `api.py` from item 3 is a prerequisite
for the reference being worth anything.

**The docs build is a CI gate, with `-W`** (`sphinx-build -W --keep-going`),
like KGLite's: a warning is a broken cross-reference or a docstring that no
longer parses, and a docs job that tolerates warnings tolerates rot.

**Done 2026-09-09:** `docs/conf.py` (furo, myst-parser,
sphinx-autoapi over `microbiomekg/`, copybutton), `docs/index.md` with the
five guides, the design notes and the research pages, `docs/requirements.txt`,
`.readthedocs.yaml`, and `make docs` = `sphinx-build -W --keep-going`, green.
CI runs the `docs` job on every push and PR. The repository owner connected
the project at
`https://microbiomekg.readthedocs.io`; the confirmed slug is `microbiomekg`.

**Done when:** the build is green under `-W` in CI and the site serves the
guides plus a generated reference.

## 6. README, human-first

**Scope.** Rewrite in the order a person reads: **Python API → Cypher → MCP**.
The evaluation's verdict was "a dataset worth having, packaged as an agent
product", and the second half is the criticism this repo set out to answer.
Today the README opens with the layout and reaches the human entry point never
— there is no browser, no CLI query tool, no export, and the only way to ask
the graph a question is to write Python or to be an LLM holding an MCP
connection.

The evidence model and the 61,127 measured negatives are the lede, not a
footnote: they are the thing no comparable resource ships.

**Done 2026-09-03.** The README opens with the evidence model and the 61,127
measured negatives, then Install → Python → Cypher → MCP → adding a source →
layout → building. Every number in it is executed by the claim gate
(`docs/claims/README.md`, via `DOC_UNITS` in `tests/skill_claims.py`), so the
README cannot drift from the graph. The one sentence that stays untrue until
the first release is `pip install microbiomekg`; the release preparation
changes that sentence to the published install path.

**Done when:** a reader who is not an agent can install it, build it, and ask
it a question from the README alone.

## 7. CHANGELOG and the versioning rule

**Scope.** A `CHANGELOG.md` in Keep-a-Changelog form with an `[Unreleased]`
section at the top; user-visible changes land in it as they happen, and a
release promotes the section into a version block. Internal refactors, test-only
changes and formatting do not get entries.

The versioning rule matches the siblings: **patch by default**. A minor or
major happens only when the release invocation names one. This project will
ship documented breaking changes in patch bumps like the rest of the estate, so
a breaking change is not a reason to stop and ask (`R6`, last paragraph) — it
is a reason to write the break into the entry.

**Done 2026-09-03:** `CHANGELOG.md` with `[Unreleased]` carrying the release
train's user-visible changes, and the rule in `CLAUDE.md` *Commits & releases*.

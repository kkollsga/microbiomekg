---
name: release
description: STUB — this repo has published nothing yet. The remote and CI exist and the publish workflow is written, but no tag has been pushed, no wheel is on PyPI and the ReadTheDocs project does not exist. Invoking this skill reports exactly what is missing and who can do it; it must not bump a version, tag, push a tag, or upload anything.
---

# release — not yet, and here is precisely what is left

**This repo has released nothing, and this skill ships no procedure.** Say what
is missing, name who can do it, and stop. Do not bump `pyproject.toml`'s
version, do not tag, do not push a tag, do not upload to PyPI. Each is an
irreversible outward-facing act needing the user's in-the-moment approval for
*that* act (`R6`), and none of them is authorized by invoking this skill.

## What is done

- **The remote** — `github.com/kkollsga/microbiomekg`, `main` pushed
  (release-readiness §1).
- **CI** — `.github/workflows/ci.yml` runs on every push to `main` and every
  PR: the gate's data-free steps, the full suite on Python 3.11–3.14, `make
  docs` under `-W`, and the empty-directory smoke build. First green run
  2026-09-08. The graph-backed suites self-skip there and a skip is not a pass
  (§2).
- **The package surface** — `microbiomekg/api.py`, `SourceStatus`, the console
  script, hatchling metadata with project URLs, MIT `LICENSE`, and `make
  check-install`: wheel + sdist built, installed into a clean venv outside the
  repo root, the three verbs run there (§3).
- **The publish workflow** — `.github/workflows/publish.yml`: trusted
  publishing on a `v*` tag, wheel **and** sdist, a fail-on-empty artifact
  assertion, and a verification job that installs the *published* wheel in a
  clean venv outside the checkout (§4's mechanism).
- **README, CHANGELOG and the versioning rule** (§6, §7), and the Sphinx build
  under `-W` locally and in CI (§5's local half).

## What is missing — two items, both the user's

1. **The PyPI pending publisher** (§4). Nothing an agent can do: at
   <https://pypi.org/manage/account/publishing/>, project `microbiomekg`,
   owner `kkollsga`, repository `microbiomekg`, workflow filename
   `publish.yml`, environment name **empty** — the workflow declares none, and
   the two must agree or the upload is rejected. The name answered 404 on
   2026-09-03; re-check on the day, since nothing reserves it.
2. **The ReadTheDocs project** (§5's hosting half). The user connects the repo
   on readthedocs.org and reports the real slug: `.readthedocs.yaml` and
   `pyproject.toml` both assume `microbiomekg`, and RTD suffixes a slug that is
   already taken.

Everything else — the tag, the first `[0.1.0]` block, the release commit — is
work this repo can do the day item 1 lands, and needs its own approval.

## What to do when someone invokes this

Report the two items above, name which of them blocks a first publish (item 1),
and offer to run **`phased-plan`** if the request is really "prepare the
release" rather than "publish now". `dev-docs/todos.md` carries the same two as
lean backlinks into `docs/design/release-readiness.md`.

**Rewrite this skill only once the repo has actually published something** —
after a `v*` tag has produced a wheel *and* an sdist on PyPI and the
verification job has installed it. Write it then from the sibling flows
(`../../Rust/KGLite/.claude/skills/release`,
`../../Rust/kglite-datasets/.claude/skills/release`) rather than from memory:
their preconditions, artifact-set-not-version verification (`R9`) and
one-bump-per-push rule (`R5`) were paid for.

Three questions in `docs/design/library-pipeline.md` stay planning-time
decisions rather than release steps: whether `build` on an empty directory
produces the NCBI-only taxonomy graph or refuses (decided — it refuses to write
one), whether the MCP manifest and skills ship in the package (they do), and
whether the `.kgl` build stamp belongs upstream in kglite.

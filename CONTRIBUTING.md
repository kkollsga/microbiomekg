# Contributing

Thanks for looking. This is a research pipeline with an unusually strict rule
about prose, so the short version is worth reading before you open a PR.

## The loop

1. **Branch** — `feat/…`, `fix/…`, `refactor/…`. Never work on `main`.
2. **Commit per phase.** A change that has steps gets one commit per step, each
   independently runnable and testable, so a bisect lands on something small.
   Format: `type: short description` (`feat`, `fix`, `docs`, `refactor`,
   `test`, `chore`).
3. **Open a draft PR** and let CI run: the gate, the full suite on Python
   3.11–3.14, `sphinx -W`, and a build against an empty data directory.
4. **Mark it ready** when every required check is green.

## The gate

```bash
make venv    # provision .venv and install the package editable
make gate    # ruff, adapter mirror, accumulation bounds, blueprint composition,
             # and the two truth gates (~30 s)
make test    # the full suite
make docs    # sphinx -W
```

Run `make gate` before every push. It is fast, and it catches the things CI
cannot: **CI has no built graph**, so the acceptance goldens, the documented
queries and the claim gate self-skip there. A green PR does not mean those
passed — only a local run against a built graph does. A skipped test is not a
pass.

Building the graph needs raw input the repository does not ship
(`docs/sources.md` says where each source comes from, and three of them are
browser-only downloads). `microbiomekg status --data ./data` prints the
to-do list. Without it you can still change and test everything that is
fixture-backed, which is most of the suite.

## Two rules that are not style preferences

**A claim in prose is executed.** Every number and every existential phrase in
`microbiomekg/mcp/` — the skills an LLM agent reads — and in the pages listed
in `tests/skill_claims.py` (`README.md`, `docs/benchmarks.md`,
`docs/queries-by-task.md`) is covered by a claim in `tests/claims/` or
`docs/claims/`, and every graph claim is run against the built graph. If your
change moves a number, re-measure it and update the claim. **Never loosen the
gate to make a sentence pass.** The gate exists because a shipped skill once
told agents there was no `CONSUMES` edge in a graph holding 4,784 of them,
while every test passed.

**A fix lands with the test that fails without it**, in the same commit, and a
new gate is not trusted until it has been seen red — break the thing it guards,
watch it fail, restore, and say so in the commit message.

## Adding a source

A source is four files and edits no shared file:

| file | what it carries |
|---|---|
| `microbiomekg/preps/prep_<src>.py` | `run(raw, store, …)`: raw files → tables, plus `DEPENDS_ON` and `RAW_INPUTS` |
| `microbiomekg/blueprints/<src>.json` | the node types and junction edges it writes rows into |
| `microbiomekg/ontology/<src>.py` | its audit rules, evidence mapping and licence |
| `tests/test_<src>.py` | its fixture-backed tests, against a real cut of the source |

Preps are discovered, not listed, so nothing central needs editing — and the
test file is what notices a source that forgot one of the four. Fixtures carry
real NCBI ids, cut from the real source; an invented id resolves to something
real and wrong the day the dump moves.

A source's edges must be able to say where they came from: `primary_source`,
`source_record_id`, `source_licence`, the study design, both group sizes and
the citing paper. An edge that cannot does not get written, and a value nobody
has read is `not_provided` rather than a plausible default — the point is that
the gap stays countable.

`docs/model.md` is the graph model, `docs/usecases-and-pitfalls.md` is the user
contract, and `CLAUDE.md` is the full set of conventions this repository works
under.

## Licence

Contributions are accepted under the MIT licence in `LICENSE`, which covers the
code only. No data is redistributed here (see the README's Licence section).

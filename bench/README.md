# `bench/` — the performance harness

What it costs to build this graph, load it, index it, query it, and reach it
through an agent's MCP surface. One command produces a capture; the capture is
a markdown table set beside the JSON it was rendered from.

```bash
.venv/bin/python bench/bench.py --label ten-sources         # the whole capture
.venv/bin/python bench/bench.py --sections query,control    # queries only
.venv/bin/python bench/bench.py --quick --sections query    # smoke it, ~40 s
```

It writes `bench/results/<date>-<label>.json` (every sample of every cell) and
`bench/results/<date>-<label>.md` (the tables). Re-rendering a capture without
re-measuring is `bench/render.py`'s `render_markdown()` over the JSON.

## What it will and will not touch

The build section runs `scripts/build.py` with `--out` pointed at a
`bench/results/` also holds the external-coverage captures `docs/benchmarks.md`
G6 points at (`<date>-external-coverage.json`, written by
`python -m microbiomekg.coverage --out`) — not a timing, but a longitudinal
number with the same never-deleted lifetime.

**scratch directory outside the repo** —
`/Volumes/EksternalHome/coding-cache/microbiomekg-bench`, `--scratch` to move
it. It never writes `graph/microbiomekg.kgl`: the shipped graph
is what `scripts/serve.py` serves and what `tests/test_acceptance.py` asserts
its goldens against, and a benchmark that could invalidate either is a
liability. The scratch holds ~1.7 GB (a 240 MB CSV set, and one `.kgl` per
index stage — eleven of them, the last three at 212 MB); nothing prunes it, so
`rm -rf` it when you are done.

A capture rewrites nothing in the repo. It used to rewrite `blueprint.json`
— the build composed it on every run, and a capture taken while someone was
editing a fragment materialised their in-flight edit into it (that happened
during the 2026-09-03 capture) — but since the package relocation the build
composes only the load copy beside the CSVs, and `make gate` is what checks
the tracked file. Still read `git status` back after a capture: the habit is
cheaper than the one time it is not clean.

**Do not run a capture while another build is running.** Two builds on one
machine measure the contention, not the build. The harness cannot detect this
and will not warn you.

`--note "…"` records a paragraph in the capture's metadata, and a capture that
will be read months later needs one: the load average says *how busy*, never
*what else was running*. The controls are what keep a busy capture usable — see
below.

## Sections

| section | what it measures |
|---|---|
| `build` | `scripts/build.py` end to end: wall time, per-prep time, CSV rows, peak RSS |
| `load` | `from_blueprint` alone, in a fresh process, with its own peak RSS |
| `saveload` | `save()` and `kglite.load()` for the BM25-only and the BM25+vector graph |
| `index` | each of the five BM25 and two vector indexes: build time and the bytes it adds |
| `query` | every `answerable-now` / `partial` Part D acceptance query |
| `control` | the machine-drift meter |
| `mcp` | Part D's D2 and D15 over stdio JSON-RPC vs in-process |

`--sections` takes any comma-separated subset. `load`, `saveload` and `index`
share one child process and one `from_blueprint`, so asking for any of them
runs all three; the child runs the preps itself, untimed, and times the load
from the tables they leave in memory — nothing on disk stands between them.

**The `build` section no longer includes the vector lane by default** (changed
after the 2026-09-03 capture): `scripts/build.py` builds it only under
`--with-vectors`, so a fresh `build` row is now the BM25-only build — about
82.6 s shorter, writing a 46.7 MB `.kgl` rather than 212.7 MB. Reproduce the
2026-09-03 capture's build section with `--build-args --with-vectors`. The
`index` and `saveload` sections are unaffected: they stage every index
themselves, both lanes, from `pipeline.TEXT_INDEXES` and `pipeline.VECTOR_INDEXES`,
and are what §3 and §4's default-vs-flagged numbers come from.

## Where the query cells come from

**The query benchmark is Part D itself, extracted at run time.**
`docs/usecases-and-pitfalls.md` Part D is the user contract — twenty acceptance
queries with a status each — and `part_d_queries()` reads every fenced `cypher`
block in every `answerable-now` or `partial` section and runs it as authored.
Nothing here is a synthetic query written to look fast.

Consequences worth knowing:

- **A section with several statements contributes several cells**, numbered in
  document order: `D15.1` is the audit call, `D15.2` the per-field census it
  rolls up. A section with one statement keeps the bare number (`D2`).
- **A new source that edits Part D moves the benchmark with it.** That is the
  point: the cells track the contract, not a snapshot of it.
- **A query that stops running is reported, not dropped.** Every cell is probed
  once before it is timed; a failure becomes a named row under "Did not run"
  with the engine's message. A silently missing cell would be the one thing
  worse than a slow one.
- **Three reconciliation cells come from
  `microbiomekg/mcp/microbiomekg.skills/reconciliation.md`**, not from Part D. D12's own
  fenced block is the *lexical* half of the lookup; the misspelling case —
  BM25 fused with the two vector lanes — is authored in the skill, which
  `docs/model.md` §6b names as its authority. **Those three need a graph built
  with `--with-vectors`**; against a default graph `text_score()` raises and
  they land under "Did not run", correctly, with the engine's message.
- **Two cells are the harness's own** (`point_taxon_by_id`, `lineage_walk`):
  shapes the evaluation asks for by name that Part D has no block for.
- **A query cell within 3× the noise floor is called out under the table.** The
  2× rule that keeps a control honest applies to a query too: a point lookup at
  1.8 µs against a 1.0 µs floor is reporting the cost of *asking*, and quoting
  it as the lookup's cost would claim more than the instrument can support.
- **The graph gets an embedder before any query runs.** `microbiomekg/mcp/microbiomekg_mcp.yaml`
  registers `microbiomekg.embedder:build` under `extensions.embedder`, so the
  served graph has one; without it every `text_score()` cell raises instead of
  being measured.

## How a number is chosen — the statistic rule

This harness obeys **KGLite's performance protocol** (`../../Rust/KGLite/CLAUDE.md`,
"Performance protocol"), because what it measures is kglite serving this graph.
Six of the nine items are mechanised rather than left to whoever runs it.

- **Release mode only.** `check_release()` reads the installed wheel's `WHEEL`
  metadata and refuses to run unless it is an `abi3` wheel. A debug-built
  extension has different assertions compiled in and its timings are not
  comparable to anything; the protocol says such numbers "must be discarded",
  so the harness declines to produce them.
- **`min` by default**, because for a repeatable sub-millisecond cell the
  median drifts upward with machine load while the min reports the best-case
  rate. Two exceptions, both from the protocol, both applied automatically and
  both named in the row's `statistic` column:
  - **`median` for a heavy-tailed cell** — one whose own `min` sits 30% or more
    below its own median. That min is a lucky round, not a rate.
  - **`mean` for a once-per-event cost** — a build, a save, a load. The
    expensive part happens on the first call; a min would report only the cheap
    repeats and be structurally blind to the thing being measured.
- **Rounds and warmup are set from a pilot**: 200 rounds for a sub-10-µs cell,
  100 up to 10 ms, 20 up to 100 ms, 5 beyond, each behind 20 warmup iterations
  (5 for the slow ones), with a per-cell time budget. `--scale` multiplies the
  round counts and the budget; `--quick` divides them by ten for a smoke run.
- **The distribution is printed, not just the headline.** Every row carries
  min / median / mean / p95 / max and `n`. A cell whose max sits at **30× its
  median or more** is flagged `rare branch`: the protocol reads that shape as an
  expensive branch taken occasionally, to be chased rather than averaged away.
- **The load average at the start and end of the capture is in the metadata.**
  The protocol stopped requiring an idle machine in 2026-08 — waiting for quiet
  cost more than it bought — so a capture runs under whatever load there is and
  *records* it. A longitudinal comparison reads that field first.

## The control cells

Controls are the instrument check: if a control moves between two captures, the
machine moved, and a difference in any other row means nothing until that is
explained.

| control | what it is |
|---|---|
| `ctrl_unwind_200k` | `UNWIND range(1, 200000)` — pure executor, ~10 ms |
| `ctrl_unwind_20k` | the same at a tenth the size, ~0.9 ms |
| `ctrl_unwind_case_20k` | 20k rows through a `CASE` and a `sum()`, ~1.5 ms |
| `ctrl_sha256_16mib` | 16 MiB of SHA-256 — **not kglite at all**, ~5 ms |

The first three touch no node, no edge and no index, so no source landing can
move them. The fourth does not enter kglite: it is the cross-check that says
whether a drift is the engine's or the machine's, which is the protocol's
"measure a claim two independent ways" applied to the instrument.

**Every control's median must sit at 2× the measured noise floor or more**, and
the capture prints the ratio and a pass/fail per control. The floor is the
median of `RETURN 1` — dispatch and result materialisation with no graph work
behind it — and on this machine it is about **1 µs**.

Two graph-shaped controls were tried and rejected, and the reasons are worth
keeping:

- `MATCH (t:Taxon) RETURN count(t)` and every other label count answer from a
  metadata fast path in ~0.9 µs. That is *at* the floor: a control there
  measures dispatch, not the graph, and the protocol's 2× rule exists exactly to
  catch it.
- A lineage walk and a 1-hop expansion do real work and are stable — but they
  move when the NCBI dump or a source's cited-taxa set moves, which is the
  failure the protocol names: a control chosen because "our source can't touch
  it" expires silently when the thing that moves is a dependency.
  `lineage_walk` is therefore kept as a **reported query cell**, never as a
  control.

## Reading the MCP section

Three rows, and the first one is the answer:

- **`mcp_floor`** is `RETURN 1` over the protocol and in-process. Its overhead
  column is the agent surface's fixed cost with no graph work behind it: JSON-RPC
  encode, a pipe round trip, the server rendering a result as text.
- **`D2`** and **`D15.1`** are Part D's own queries, by id, so the MCP row and
  the section-5 row are the same query text rather than a paraphrase.
- **Boot is separate.** Server start plus the `initialize` handshake includes
  loading the `.kgl`; an agent pays it once a session, and the per-call rows
  every question.

Where the overhead is smaller than the MCP cell's own run-to-run spread, the
table says so instead of printing a difference. A 24 µs surface cost inside a
370 ms query is not a measurement, and rounding noise there occasionally comes
out negative.

## What this harness deliberately does not measure

- **A cold-cache load.** Dropping the macOS unified buffer cache needs
  `sudo purge`. The harness has no sudo and does not ask for it, so the two load
  columns are *first touch after the save that wrote the file* and *warm
  repeats* — both warm, differently. A genuine cold load is not measured and is
  not estimated.
- **Anything in the default/debug profile.** See `check_release()`.
- **`save()` inside the build's segment table.** `scripts/build.py` prints its
  `saved …` marker *after* the save returns, so the save's time lands in the
  preceding `report` segment and the `save` row is only the tail before process
  exit. Section 3 measures `save()` directly; quote that one.
- **Per-index size in isolation.** The `.kgl` deltas in section 4 are cumulative
  and order-dependent, because `save()` consolidates the whole graph on the way
  out: each row is what the file grew by when that index joined the ones before
  it, in `scripts/build.py`'s order.

## Dependencies

None beyond what the repo already has. `pytest-benchmark` was considered and
not adopted: the statistic rule above is per cell rather than per suite, several
cells are whole subprocesses rather than callables, and the capture needs every
sample kept for a later re-read — so the timing loop is 40 lines here instead of
a dependency and an adapter. The MCP section reuses `tests/mcp_support.MCPClient`,
the same stdio client the MCP tests drive the server with.

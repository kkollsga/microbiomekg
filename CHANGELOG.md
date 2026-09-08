# Changelog

All notable changes to MicrobiomeKG will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
User-visible changes land under `[Unreleased]` as they happen; a release
promotes that section into a version block. Internal refactors, test-only
changes and formatting do not get entries. Nothing has been released yet:
`0.1.0` in `pyproject.toml` is a placeholder until the first tag.

## [Unreleased]

### Added
- **Guidance in the data-loading path.** `prepare(data_dir)` creates the input
  layout and prints a dataset table with availability, total size and oldest
  local file age. Missing files and files above `max_age_days` (30 by default;
  CLI `--max-age-days`) get download URLs and expected filenames. `status` and the CLI fetch report share the same guidance;
  `status --create` creates the layout from the shell. Python `status` remains
  a silent evaluator with per-file metadata on `SourceStatus.files`.
- **Fetch missing inputs.** `fetch(data_dir, missing=True)` and `fetch --missing`
  select fetchers for missing required inputs, deduplicating shared sources
  and excluding optional KEGG unless explicitly selected with `only` / `--only`.
  Selected fetchers retain their existing cache and update behavior.
- **PyPI publishing, prepared.** `[project.urls]` (homepage, repository, docs,
  changelog, issues) so the PyPI page links somewhere, and
  `.github/workflows/publish.yml`: trusted publishing on a `v*` tag, a wheel
  **and** an sdist with the artifact set asserted before and after the upload,
  and a verification job that installs the *published* wheel into a clean venv
  outside any checkout and runs the CLI there. Nothing is published yet — the
  pending publisher on pypi.org is the repository owner's step.
- **`CITATION.cff` and `CONTRIBUTING.md`**, and a **Licence** section in the
  README: the code is MIT and covers only this repository; no data and no built
  graph is distributed; every edge carries the `source_licence` it came with,
  and 80,118 of them carry an `-unstated` token against 68,752 that are CC0.
  Per-source terms stay in `docs/sources.md`.
- **The sdist carries `blueprint.json` and `CHANGELOG.md`.** The composed
  blueprint is what the fragment-drift gate reads at the repo root, so it was
  missing from the one distribution that ships the tests; the gate now runs
  from an unpacked sdist.
- **G6, coverage of two external curations.** `microbiomekg.coverage` reads
  HMDAD and Peryton, reconciles them the way the preps do, and reports how
  many of their (taxon, disease) pairs the graph asserts, with the evidence
  histogram and direction agreement; neither set is loaded. Both are fetched
  by `microbiomekg fetch --only hmdad` / `--only peryton`, and the numbers
  ride into `docs/benchmarks.md` from a tracked capture.
- **G7, the breadth proxy against a published meta-analysis.** D14's
  signature-breadth ranking scored against Duvallet et al. 2017's non-specific
  genus set: nine of the top ten at genus rank, claim-gated in
  `docs/benchmarks.md`. The reference set is fetched by
  `microbiomekg fetch --only duvallet2017` and cut to a checked-in table.
- **Source to graph, with nothing on disk in between.** Every prep is a
  function, `run(raw, store, ...)`, that puts its tables into one in-memory
  store; the build composes a blueprint whose `files:` section declares each
  table as a frame and loads it with kglite 0.16.23's `frames=`. The
  `BuildResult` carries the store, ledgers included.
- **The package surface.** `import microbiomekg` gives `status(data_dir)`,
  `fetch(data_dir)` and `build(data_dir)` over one data directory; `build`
  returns a `BuildResult` holding the kglite graph and a `BuildReport`. The
  `microbiomekg` console script runs the same three verbs over `--data`, plus
  `serve` over `--graph`. The package is a wheel: `make check-install` builds it and proves
  it in a clean venv.
- **`SourceStatus`.** Every prep declares `RAW_INPUTS`, and `status` reports
  each source as `absent`, `present`, `stale` or `manual`, with the missing
  files and a `how_to_get` line as data — the three browser-only origins'
  instructions included.
- **A build with nothing in it succeeds.** An empty data directory exits 0,
  names every source as skipped, and writes no graph; a directory holding only
  the NCBI taxdump builds the Taxon spine and says "taxonomy-only".
- `docs/benchmarks.md`: the association-layer shape, reconciliation confidence,
  the two drug-screen headline reproductions, BugSigDB loader fidelity and
  cross-source direction agreement, every number executed by the claim gate.
- The Sphinx docs (`make docs`, built under `-W`) and the human-first README,
  also claim-gated.

### Changed
- **The benchmark harness's scratch directory defaults to a sibling of the
  checkout** (`../MicrobiomeKG-bench`) instead of one machine's absolute path.
  `MICROBIOMEKG_BENCH_SCRATCH` moves it per machine, `--scratch` per run.
- **`docs/sources.md` reads in numeric order** — the MONDO section (11) sat
  after 17.
- **The kglite floor is `>=0.17.1`.** The graph rebuilds table-for-table
  identical on it (56 tables, 864,132 taxa, 112,966 `taxon_condition` rows),
  and the full suite — the acceptance goldens, the documented queries and the
  claim gate against a 0.17.1-built graph — is unchanged. 0.17.0 also closes
  two more `docs/model.md` §8 engine asks: a Cypher query can force the exact
  vector scan with `{exact: true}` and read which lane served it from the
  result's retrieval diagnostics, and the ontology audits *node* properties
  as well as edge ones.
- **A blueprint fragment names its input with `file` only.** The pre-0.16.23
  `csv` spelling, which the build and `declared_types` still accepted and
  rewrote, is no longer read; no fragment used it.
- **`mondo.obo` is a declared input.** The three preps that key conditions on
  MONDO list `mondo/mondo.obo` in `RAW_INPUTS`, `status` reports it, `fetch`
  pulls it (`--only mondo`, and with BugSigDB and gutMDisorder), and an absent
  file skips the source with the reason instead of silently writing every
  disease under its source's own id. Withholding any declared input — not only
  the first — now makes its prep refuse by name; that also caught MiMeDB's
  microbes dump and four of the five taxonomy dumps.
- `--csv` and `--skip-prep` are gone from the build: there is no CSV
  directory to point at or reuse, and `microbiomekg build --data D` reads
  `D/raw/` only. A prep's absent input is a `MissingInput` exception the
  build reports as the skip, not an exit code.
- kglite ≥ 0.16.23 is required.
- The preps, blueprint fragments, MCP manifest and skills, and the build,
  fetch and serve modules moved into the package (`microbiomekg/preps/`,
  `microbiomekg/blueprints/`, `microbiomekg/mcp/`, `pipeline.py`,
  `download.py`, `serve.py`); `scripts/*.py` are thin callers. The build runs
  preps as `python -m microbiomekg.preps.<name>`.
- The build no longer rewrites the tracked `blueprint.json`; `make gate`
  composes it in `--check` mode.
- The claim gate covers tracked markdown pages (`DOC_UNITS`), not only the
  MCP prose.

### Fixed
- Data guidance uses the chosen data directory, quotes shell paths, and
  distinguishes missing automatic inputs within a partly manual source.
  Malformed manifest shapes no longer prevent status inspection. The fetch
  CLI now exits unsuccessfully when a fetcher raises, while still displaying
  the remaining input status.
- **A malformed raw file skips its source instead of ending the build.** The
  workbook preps (Maier 2018, Zimmermann 2019, NJC19) raised `SystemExit`
  when a sheet or header row was not where the paper put it, or when a rule
  derived from the file stopped reproducing the paper's own numbers; the
  build caught none of it, so one renamed header ended a multi-minute build
  with no report and no census. They raise `MalformedInput` now, the build
  reports the source as present-but-malformed beside the absent ones, and
  `<graph>.build.json` carries every skip's reason under `skip_reasons`.
- Ten preps reported a missing NCBI taxdump through argparse (exit 2), which
  the build reads as fatal; every prep now exits 3, the skip code.
- A relative `--csv` loaded the ontology from a doubled path; the build
  resolves its paths first.
- `docs/evaluation.md` §5 compared the comparator's disease *nodes* to ours
  and quoted a stale metabolite count; `docs/usecases-and-pitfalls.md` D17
  quoted pre-MASI goldens.

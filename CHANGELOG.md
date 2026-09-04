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
- **Source to graph, with nothing on disk in between.** Every prep is a
  function, `run(raw, store, ...)`, that puts its tables into one in-memory
  store; the build composes a blueprint whose `files:` section declares each
  table as a frame and loads it with kglite 0.16.23's `frames=`. The
  `BuildResult` carries the store, ledgers included.
- **The package surface.** `import microbiomekg` gives `status(data_dir)`,
  `fetch(data_dir)` and `build(data_dir)` over one data directory; `build`
  returns a `BuildResult` holding the kglite graph and a `BuildReport`. The
  `microbiomekg` console script runs the same verbs plus `serve`, each taking
  `--data`. The package is a wheel: `make check-install` builds it and proves
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
- Ten preps reported a missing NCBI taxdump through argparse (exit 2), which
  the build reads as fatal; every prep now exits 3, the skip code.
- A relative `--csv` loaded the ontology from a doubled path; the build
  resolves its paths first.
- `docs/evaluation.md` §5 compared the comparator's disease *nodes* to ours
  and quoted a stale metabolite count; `docs/usecases-and-pitfalls.md` D17
  quoted pre-MASI goldens.

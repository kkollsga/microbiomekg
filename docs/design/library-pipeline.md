# MicrobiomeKG as a library: the data-directory contract

Status: the packaging half shipped 2026-09-03 (items 1–3 below); the remote,
CI and PyPI halves wait on `release-readiness.md` §1.

## The decision already made

- **100% Python.** No Rust crate. kglite does the heavy lifting; this package
  only orchestrates prep, composition, load and report.
- **No data and no finished graph ships.** 26% of evidence-bearing edges have no
  redistribution permission (docs/evaluation.md §4), and the clean CC0 cut drops
  the drug and resistance layers. What ships is the pipeline.
- **What separates this from Sodir** (kglite-datasets): Sodir's fetch is fully
  automatic against a REST API, so its pipeline has no manual step. Three of our
  origins are browser-only (HMDB and MiMeDB behind Cloudflare, MASI behind an
  expired certificate). "Remove all friction" therefore has a floor: the manual
  steps cannot be eliminated, so they must be *precise* — which file, from which
  page, into which directory — and the pipeline must say exactly what it did
  without them.

## The contract

One directory is the entire input. The library scales the build to what is in it.

```
microbiomekg status --data ./data --create  # create directories; show availability, size and age
microbiomekg fetch  --data ./data --missing # run fetchers needed by missing default inputs; report again
microbiomekg build  --data ./data            # build from whatever is present; report what was skipped
```

and the Python convenience path:

```python
import microbiomekg as mkg
mkg.prepare("./data")                  # create directories, print report, return {source: SourceStatus}
mkg.fetch("./data", missing=True)      # fetch missing automatic inputs, then print and return status
result = mkg.build("./data", with_kegg=False, with_vectors=False)
```

`status` is the silent, read-only evaluator behind both reports. Each
`SourceStatus.files` entry is an `InputFile` carrying the local state, size,
modification time and age together with its URL and fetcher. `prepare` adds
directory creation and presentation; it never downloads. Age is time since the
local modification time, and `stale` means that a local size differs from the
fetch manifest. Neither is an upstream release or digest check. `present`
means only that a path exists; the build validates its contents.

Missing-only fetch selects fetchers, not individual network operations. A
selected source's existing fetcher may check or update its other files, and
fetchers shared by several sources run once. It excludes the licence-gated
KEGG input unless the caller explicitly selects `only=["kegg"]` (or uses
`--only kegg`). Bare `fetch` keeps its existing full-fetch behaviour, including
references and KEGG. When every default input is complete, missing-only fetch
runs no fetcher and simply reports the current state.

Rules that make it a contract rather than a convention:

1. **A source is discovered, never listed.** Adding a source is adding
   `prep_<src>.py` + `microbiomekg/blueprints/<src>.json` + `ontology/<src>.py`; the
   directory layout `data/raw/<src>/` is derived from the module name. Already
   true today (pkgutil / glob); the contract makes it the documented rule.
2. **Absent means skipped, loudly.** A source with no raw input is dropped from
   the composed blueprint and the ontology (no empty node type, no 0/0 audit
   rule — the existing `test_audit_denominators_are_not_zero` is the gate).
   The build report lists every skipped source with its `how_to_get` line. A
   build that silently has fewer sources than the operator expected is the
   failure this rule prevents.
3. **Dependency order is declared, not alphabetical.** `DEPENDS_ON` per prep
   (already shipped); a dependency on a *skipped* source is itself a skip with a
   reason, never an error and never a half-load.
4. **Licence gates are flags, off by default.** `--with-kegg` today; any future
   restricted source follows the same shape. The report names what the flag
   added so a distributable graph can be built without it.
5. **Cost gates are flags, off by default.** `--with-vectors` today (quadruples
   the file, +2.5 GB RSS, +83 s). Same rule: the report prices what was skipped.
6. **Status is a first-class output**, not a side effect of a failed build. An
   operator on a fresh clone runs `status` and gets a to-do list: which
   automatic fetches to run, which files to download by hand and where to put
   them, which sources are optional and why.
   The report is a dataset table (availability, total size, oldest local file
   age). Missing inputs and inputs older than `max_age_days` (30 by default;
   CLI `--max-age-days`) get a URL and expected filename beneath the table.
   This threshold changes presentation only, not automatic fetch selection.
   `prepare` is the guided Python presentation of that same status, while CLI
   `status --create` provides the normal shell path.
7. **The graph's provenance is in the graph.** Every association edge already
   carries `primary_source`, `source_record_id`, `source_licence`. `build`
   additionally stamps the graph with the source set and raw-file digests it
   was built from, so two graphs can be compared by what went in.

## What already exists (do not rebuild)

| Contract piece | Where it lives today |
|---|---|
| Source discovery | `microbiomekg/pipeline.py` (glob over `microbiomekg/preps/`, pkgutil over `microbiomekg.ontology`, glob over `microbiomekg/blueprints/`) |
| Absent → skipped, no 0/0 rules | `compose(sources)`, `ontology_for(sources)`, a prep's `MissingInput` |
| Dependency order | `DEPENDS_ON` in each prep, topologically sorted with cycle detection |
| Licence / cost flags | `--with-kegg`, `--with-vectors` |
| Manual-source detection | `fetch.py`'s `manual-present` status (HMDB, MiMeDB v2, MASI) |
| Guided status as data | `microbiomekg.sources.status(data_dir)` → `{source: SourceStatus(..., files: tuple[InputFile, ...])}` is silent and read-only; `prepare(create=True)` and CLI `status --create` create directories and render it; each prep declares `RAW_INPUTS`, and fetch metadata says how to get them |
| Per-source provenance | `data/raw/<src>/PROVENANCE.md` (gitignored) + `docs/sources.md` (tracked) |
| Truth gates | `tests/test_skill_claims.py`, `tests/test_documented_queries.py`, the junction rows-to-edges pin |
| Source to graph | every prep returns frames into `microbiomekg.tables.Frames`; the load is `from_blueprint(frames=)` (kglite 0.16.23); no intermediate on disk |

## What the library release needs (in order, when there is time)

1. ~~A `microbiomekg/api.py` exposing `fetch` / `status` / `build`~~ **Done
   2026-09-03.** `scripts/*.py` are thin callers; the code is
   `microbiomekg/pipeline.py` (build), `download.py` (fetch), `sources.py`
   (status), `api.py` (the three verbs over one data directory).
2. ~~`status` as a real object~~ **Done 2026-09-03**: `microbiomekg/sources.py`,
   `SourceStatus(state ∈ {absent, present, stale, manual}, path, inputs,
   missing, how_to_get, licence, gated_by)`; the manual-source text lives in
   `fetch.MANUAL` and the fetchers print the same strings.
3. ~~A console entry point~~ **Done 2026-09-03**: `microbiomekg fetch | status |
   build`, each taking `--data`, and `microbiomekg serve` over `--graph`.
4. The README rewritten for a **human reader first** (Python API, then Cypher,
   then MCP) — the evaluation's own verdict was "a dataset worth having,
   packaged as an agent product", which is the critique the project set out to
   answer.
5. ~~A GitHub repository and CI~~ **Done 2026-09-08**:
   `github.com/kkollsga/microbiomekg`, with `.github/workflows/ci.yml` running
   the gate's data-free steps, the full suite on Python 3.11–3.14, `make docs`
   under `-W`, and the `status`-driven smoke build against an empty data
   directory. CI has no graph, so the graph-backed suites self-skip there and
   the local gate keeps them.
6. ~~Name check on PyPI (`microbiomekg`)~~ — 404 on 2026-09-03, unclaimed.
   `.github/workflows/publish.yml` is written; the pending publisher on
   pypi.org is the repository owner's step, and the first tag is a separate
   release request.

## Open questions (decide at planning time, not now)

- ~~Whether `build` on an empty directory should produce the NCBI-only taxonomy
  graph or refuse.~~ **Decided 2026-09-03.** `build` does not fetch, so an
  *empty* directory builds nothing: exit 0, every source named as skipped, no
  graph written. A directory holding only the taxdump builds the Taxon spine
  and the report says "taxonomy-only". Both are tests in
  `tests/test_build_pipeline.py`.
- Whether the MCP manifest and skills ship in the package or stay a
  documented add-on. They are the agent surface the critique was about;
  shipping them makes the package's default framing agent-first again.
- Whether the `.kgl` build stamp (rule 7) belongs in kglite itself as a
  general "built-from" provenance block. Probably yes; file upstream when the
  time comes.

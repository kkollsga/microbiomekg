# MicrobiomeKG as a library: the data-directory contract

Status: design note, no rush (user direction 2026-09-03). Not scheduled.

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
microbiomekg fetch  --data ./data      # fills what it can; prints the manual steps for the rest
microbiomekg status --data ./data      # per source: absent / present / stale, with the fix for each
microbiomekg build  --data ./data      # builds from whatever is present; reports what was skipped
```

and the same three as Python:

```python
import microbiomekg as mkg
mkg.fetch("./data")                    # returns a status; never raises on a manual source
mkg.status("./data")                   # -> {source: SourceStatus(state, path, how_to_get)}
g = mkg.build("./data", with_kegg=False, with_vectors=False)   # -> kglite.KnowledgeGraph
```

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
7. **The graph's provenance is in the graph.** Every association edge already
   carries `primary_source`, `source_record_id`, `source_licence`. `build`
   additionally stamps the graph with the source set and raw-file digests it
   was built from, so two graphs can be compared by what went in.

## What already exists (do not rebuild)

| Contract piece | Where it lives today |
|---|---|
| Source discovery | `scripts/build.py` (pkgutil over `microbiomekg.ontology`, glob over `microbiomekg/blueprints/`) |
| Absent → skipped, no 0/0 rules | `build_blueprint --sources`, `ontology_for(sources)`, prep exit code 3 |
| Dependency order | `DEPENDS_ON` in each prep, topologically sorted with cycle detection |
| Licence / cost flags | `--with-kegg`, `--with-vectors` |
| Manual-source detection | `fetch.py`'s `manual-present` status (HMDB, MiMeDB v2, MASI) |
| `status` as data | `microbiomekg.sources.status(data_dir)` → `{source: SourceStatus(state, path, inputs, missing, how_to_get, licence, gated_by)}`; each prep declares `RAW_INPUTS`, `fetch.FETCHES`/`fetch.MANUAL` say how to get them |
| Per-source provenance | `data/raw/<src>/PROVENANCE.md` (gitignored) + `docs/sources.md` (tracked) |
| Truth gates | `tests/test_skill_claims.py`, `tests/test_documented_queries.py`, the junction rows-to-edges pin |

## What the library release needs (in order, when there is time)

1. A `microbiomekg/api.py` exposing `fetch` / `status` / `build` as the three
   functions above, wrapping what `scripts/*.py` already do. The scripts become
   thin callers of the API, not the other way round.
2. ~~`status` as a real object~~ **Done 2026-09-03**: `microbiomekg/sources.py`,
   `SourceStatus(state ∈ {absent, present, stale, manual}, path, inputs,
   missing, how_to_get, licence, gated_by)`; the manual-source text lives in
   `fetch.MANUAL` and the fetchers print the same strings.
3. A console entry point (`microbiomekg = microbiomekg.cli:main`) so the three
   verbs work from a shell without `python scripts/...`.
4. The README rewritten for a **human reader first** (Python API, then Cypher,
   then MCP) — the evaluation's own verdict was "a dataset worth having,
   packaged as an agent product", which is the critique the project set out to
   answer.
5. A GitHub repository and CI. The tree has never been verified off this
   machine; the 1,216-test suite plus a `status`-driven smoke build against an
   empty data directory (which must succeed and report every source as absent)
   is the CI shape.
6. Name check on PyPI (`microbiomekg`), then release through the same flow as
   the other siblings.

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

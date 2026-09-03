# MicrobiomeKG

A test build of a microbiome knowledge graph on kglite, modelled on the
MicroMap post (taxa, diseases, metabolites, pathways, drugs, resistance,
papers) but with the *evidence model* as the point: every association edge
carries study design, direction, sample size and the citing paper, and the
ontology audit reports what fraction of edges lack evidence.

Eleven sources are loaded: BugSigDB, gutMDisorder, CARD, HMDB, Reactome,
ChEMBL, MiMeDB, NJC19, the two landmark drug screens — Maier 2018 and
Zimmermann 2019 — and MASI, over NCBI taxonomy. KEGG has a loader and is **off
by default** — `--with-kegg` — because its licence forbids redistributing a
graph carrying it.

The drug↔taxon layer is the part worth knowing about. Maier's 1,197 drugs × 40
gut isolates say which drugs inhibit a bacterium; Zimmermann's 271 drugs × 76
strains say which bacteria metabolise a drug; **each keeps its measured non-hits
— 42,233 and 17,479 — as their own relationship** (`docs/sources.md` §15, §16).
**MASI is the aggregator that curates the same literature, and it is loaded as
one**: 66.4% of its 12,512 interaction records cite one of those two papers, and
62.5% of the edges it produces restate a (taxon, compound) pair one of those
screens already *measures*. So its substances are their own `Substance` node
type, its four interaction relationships are its own, and the identity between a
MASI substance and a `Drug` is a declared `SAME_COMPOUND_AS` edge — never a
merge. A query for what was measured never sees a re-curation of it; a query for
MASI's curated literature asks for it in one hop, and
`WHERE r.duplicates_primary_source IS NULL` is the 4,295 edges nothing else here
carries (§14).

Layout:

- `scripts/fetch.py`  — manifest-driven downloads into `data/raw/` (skip if present, resume).
- `scripts/prep_*.py` — per-source preprocessing into flat CSVs in `data/csv/`.
  Each declares `DEPENDS_ON`: the preps whose tables it reads.
- `scripts/build.py`  — the whole build: prep in dependency order, compose,
  load, index, audit, save.
- `blueprints/*.json` — one blueprint fragment per source, composed into
  `blueprint.json` by `scripts/build_blueprint.py`.
- `microbiomekg/ontology/` — one module per source, composed into `ONTOLOGY`.
- `microbiomekg/tables.py` — the shared flat-CSV writer, and how two sources
  merge rows into one table without either knowing the other's columns.
- `microbiomekg/embedder.py` — the deterministic character-n-gram embedder the
  semantic name lookup uses. No model download, and **off by default** —
  `--with-vectors`; see `docs/model.md` §6b.
- `mcp/microbiomekg_mcp.yaml` — the MCP manifest: read-only, skills on, the
  evidence rules in `instructions:` and the sticky field reminder in
  `overview_prefix:`.
- `mcp/microbiomekg.skills/` — one skill per Part D use-case family. These are
  injected into the tool descriptions the agent reads, so the methodology
  travels with the tool.
- `scripts/serve.py`  — launches that server (`--selftest` for a green/red
  configuration check). The manifest has no `graph:` key, so this pairing is
  the only supported way to start it.
- `docs/model.md`     — the graph model and the evidence-field contract.
- `docs/sources.md`   — each source: URL, licence, format, fetch status.
- `docs/usecases-and-pitfalls.md` — the user contract: workflows, the evidence
  vocabulary, the ten guards, and the twenty acceptance queries.

**Adding a source** means adding files, not editing shared ones:
`scripts/prep_<source>.py`, `blueprints/<source>.json`,
`microbiomekg/ontology/<source>.py`, `tests/test_<source>.py`. The prep
scripts, the blueprint fragments and the ontology modules are each discovered
by glob rather than listed anywhere, the prep's `DEPENDS_ON` is what places it
in the build, and a fragment that contradicts another is a build error rather
than a silent override.

Build it:

```bash
.venv/bin/python scripts/build.py          # --scope microbial is the default
.venv/bin/python scripts/build.py --with-kegg      # + the licence-gated source
.venv/bin/python scripts/build.py --with-vectors   # + the semantic name lane
.venv/bin/python -m pytest -q
```

Two things are **off by default and opt in by a flag**, for different reasons.
`--with-kegg` is a licence gate (above). `--with-vectors` is a cost gate: the
character-n-gram vector index buys query-time tolerance for a *misspelt*
organism name and nothing else — load-time reconciliation matches exactly,
through synonyms and through authority stripping, and never touches it — while
costing +82.6 s of build, `.kgl` 46.7 MB → 212.7 MB, load 1.03 s → 2.41 s and
serving RSS 1.2 GB → 3.7 GB (measured, `docs/model.md` §6b). The five BM25
indexes are unconditional at 276 ms and 14.3 MB. A default build says in its
report that the lane was skipped and which flag turns it on.

The build prints node and edge counts, the ontology audit, and G10's expansion
factor — edges per source record — for every relationship the fragments
declare. It writes the graph to `graph/microbiomekg.kgl` and, beside the CSVs
it loaded, the `blueprint.load.json` and ontology document that describe *that*
build. `--csv <dir>` moves all of it somewhere else.

Serve it to an agent:

```bash
.venv/bin/python scripts/serve.py --selftest   # green/red configuration check
.venv/bin/python scripts/serve.py              # MCP over stdio, read-only
```

Engine: kglite (`../../Rust/KGLite`, source of API truth `kglite/__init__.pyi`).

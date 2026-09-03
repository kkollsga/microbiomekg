# MicrobiomeKG

A test build of a microbiome knowledge graph on kglite, modelled on the
MicroMap post (taxa, diseases, metabolites, pathways, drugs, resistance,
papers) but with the *evidence model* as the point: every association edge
carries study design, direction, sample size and the citing paper, and the
ontology audit reports what fraction of edges lack evidence.

Nine sources are loaded: BugSigDB, gutMDisorder, CARD, HMDB, Reactome, ChEMBL,
MiMeDB, NJC19 and the Maier 2018 drug screen, over NCBI taxonomy. KEGG has a
loader and is **off by default** — `--with-kegg` — because its licence forbids
redistributing a graph carrying it. MASI was fetched and is **not** loaded: its
download is the substance dictionary and names no organism, so nothing in it can
become an edge (`docs/sources.md` §14) — the drug↔taxon layer it was fetched for
comes from Maier's published screen instead, 1,197 drugs × 40 gut isolates,
**with its 42,233 measured non-hits kept as their own relationship** (§15).

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
  semantic name lookup uses. No model download; see `docs/model.md` §6b.
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
.venv/bin/python -m pytest -q
```

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

# MicrobiomeKG

A test build of a microbiome knowledge graph on kglite, modelled on the
MicroMap post (taxa, diseases, metabolites, pathways, drugs, resistance,
papers) but with the *evidence model* as the point: every association edge
carries study design, direction, sample size and the citing paper, and the
ontology audit reports what fraction of edges lack evidence.

Layout:

- `scripts/fetch.py`  — manifest-driven downloads into `data/raw/` (skip if present, resume).
- `scripts/prep_*.py` — per-source preprocessing into flat CSVs in `data/csv/`.
- `scripts/build.py`  — the whole build: prep, compose, load, index, audit, save.
- `blueprints/*.json` — one blueprint fragment per source, composed into
  `blueprint.json` by `scripts/build_blueprint.py`.
- `microbiomekg/ontology/` — one module per source, composed into `ONTOLOGY`.
- `docs/model.md`     — the graph model and the evidence-field contract.
- `docs/sources.md`   — each source: URL, licence, format, fetch status.
- `docs/usecases-and-pitfalls.md` — the user contract: workflows, the evidence
  vocabulary, the ten guards, and the twenty acceptance queries.

**Adding a source** means adding files, not editing shared ones:
`scripts/prep_<source>.py`, `blueprints/<source>.json`,
`microbiomekg/ontology/<source>.py`, `tests/test_<source>.py`. All three are
discovered rather than listed, and a fragment that contradicts another is a
build error rather than a silent override.

Build it:

```bash
.venv/bin/python scripts/build.py --scope microbial
.venv/bin/python -m pytest -q
```

Engine: kglite (`../../Rust/KGLite`, source of API truth `kglite/__init__.pyi`).

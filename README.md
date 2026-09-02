# MicrobiomeKG

A test build of a microbiome knowledge graph on kglite, modelled on the
MicroMap post (taxa, diseases, metabolites, pathways, drugs, resistance,
papers) but with the *evidence model* as the point: every association edge
carries study design, direction, sample size and the citing paper, and the
ontology audit reports what fraction of edges lack evidence.

Layout:

- `scripts/fetch.py`  — manifest-driven downloads into `data/raw/` (skip if present, resume).
- `scripts/prep_*.py` — per-source preprocessing into flat CSVs in `data/csv/`.
- `blueprint.json`    — kglite blueprint over `data/csv/`.
- `docs/model.md`     — the graph model and the evidence-field contract.
- `docs/sources.md`   — each source: URL, licence, format, fetch status.

Engine: kglite (`../../Rust/KGLite`, source of API truth `kglite/__init__.pyi`).

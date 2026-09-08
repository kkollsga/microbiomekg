# MicrobiomeKG

A microbiome knowledge graph on [kglite](https://github.com/kkollsga/kglite),
**with the evidence model as the point**. Every association edge carries the
study design, the direction, both group sizes and the citing paper; nothing is
stored as a score; direction is per study and never aggregated, so forty
reports on one pair stay forty reports, dissent included. And the **measured
negatives are first-class**: 61,127 edges record that somebody looked and found
nothing — 42,233 drugs that did not inhibit a gut isolate, 17,479 that no
strain metabolised, 894 metabolites with no exchange, and 521 curated
non-effects — each as its own relationship, so no query mistakes "never
tested" for "tested and clean".

Eleven curated sources over NCBI taxonomy: BugSigDB, gutMDisorder, CARD, HMDB,
Reactome, ChEMBL, MiMeDB, NJC19, the Maier 2018 and Zimmermann 2019 drug
screens, and MASI. 934,206 nodes and 1,324,684 edges; 105,880
microbe–disease reports over 56,306 distinct pairs. KEGG has a loader and is
off by default, because its licence forbids redistributing a graph carrying it.

No data and no built graph ships. What ships is the pipeline: one directory
is the entire input, a source is discovered rather than listed, and a source
whose raw files are absent is skipped loudly, never silently.

## Install, get the data and build

Install MicrobiomeKG from PyPI, then use one data directory throughout:

```bash
python -m pip install microbiomekg
microbiomekg status --data ./my-data --create
microbiomekg fetch  --data ./my-data --missing
microbiomekg build  --data ./my-data
```

`status --create` creates the required raw-input directories and shows a table
of dataset availability, size and age. Missing files and files older than the
configurable age threshold get a download URL and expected filename below the
table. It does not download anything. `fetch --missing` selects the automatic fetchers needed
for missing default inputs, then prints the same report so remaining manual
work stays visible. A build can use a partial data directory and names every
source it skipped. See the [getting-started guide](docs/getting-started.md) for
the browser-only inputs and Python equivalent.

## Python

```python
import microbiomekg as mkg

data = "./my-data"
mkg.prepare(data)                         # create directories and print the input report
mkg.fetch(data, missing=True)             # fetch missing automatic inputs; report again
result = mkg.build(data)                  # build from what is present; does not save by default
g = result.graph

g.cypher("""
MATCH (t:Taxon {id: 851})-[r:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0005575'})
RETURN r.direction, r.evidence_level, r.study_design, r.group_1_size, r.pmid
ORDER BY r.evidence_level
""")
```

That query — *Fusobacterium nucleatum* in colorectal cancer — returns 40 rows
from 21 studies, one of them `decreased`. It is never one aggregated row, and
the dissent is never removed. The twenty documented queries in
[`docs/usecases-and-pitfalls.md`](docs/usecases-and-pitfalls.md) are the user
contract; each has a golden the test suite asserts.

## Cypher

The graph is a kglite `.kgl` file: open it in Python, or over Bolt for driver
tooling. Three of the documented queries, as the shape of what it answers:

```cypher
// D17 — where do studies disagree, and which pairs rest on a single cohort?
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
WITH t, d, collect(DISTINCT r.direction) AS directions,
     count(DISTINCT r.study_id) AS n_studies, count(r) AS n_edges
RETURN t.title, d.title, directions, n_studies,
       size(directions) > 1 AS direction_conflict, n_studies = 1 AS single_cohort
ORDER BY n_edges DESC LIMIT 50
```

```cypher
// D8 — does a drug inhibit gut bacteria, and is it metabolised by them?
MATCH (d:Drug {pref_name: 'METFORMIN'})-[r]->(t:Taxon)
RETURN type(r) AS relationship, count(*) AS strains
```

```cypher
// D6 — which taxa consume a metabolite, and which produce it? (cross-feeding)
MATCH (m:Metabolite {title: 'Butyric acid'})
OPTIONAL MATCH (p:Taxon)-[:PRODUCES]->(m)
OPTIONAL MATCH (c:Taxon)-[:CONSUMES]->(m)
RETURN count(DISTINCT p) AS producers, count(DISTINCT c) AS consumers
```

The model — node types, the evidence-field contract, the reconciliation ledger
— is [`docs/model.md`](docs/model.md); the per-source licences and provenance
are [`docs/sources.md`](docs/sources.md); what the graph reproduces and
against what is [`docs/benchmarks.md`](docs/benchmarks.md).

## MCP

```bash
microbiomekg serve --selftest    # green/red configuration check
microbiomekg serve               # kglite's MCP server on stdio, read-only
```

The manifest and the skills ship inside the package. One skill per use-case
family, injected into the tool descriptions an agent reads, so the evidence
rules travel with the tool; the prose in them is held to the graph by the
same claim gate that holds this README.

## Adding a source

A source is four files, discovered rather than listed, and adding one never
edits a shared file:

| file | what it carries |
|---|---|
| `microbiomekg/preps/prep_<src>.py` | `run(raw, store, …)`: raw files → tables in the build's store, plus `DEPENDS_ON` and `RAW_INPUTS` |
| `microbiomekg/blueprints/<src>.json` | the node types and junction edges it writes rows into |
| `microbiomekg/ontology/<src>.py` | its audit rules, evidence mapping and licence |
| `tests/test_<src>.py` | its fixture-backed tests, against a real cut of the source |

Fragments merge and never override: declaring the same key with a different
value is a build error naming both fragments.

## Layout

- `microbiomekg/` — the package: `api.py` (the three verbs), `cli.py`, the
  preps, the blueprint fragments, the ontology modules, `pipeline.py` (the
  build), `download.py` (fetch), `sources.py` (status), `serve.py`, and `mcp/`.
- `scripts/` — thin callers into the package, so `scripts/build.py` and
  friends work from a checkout; `scripts/check_install.py` is the wheel proof.
- `docs/` — the guides, the design notes, and the Sphinx build (`make docs`).
- `tests/` — offline, fixture-backed; the graph-backed suites read the built
  `graph/microbiomekg.kgl`. `tests/claims/` and `docs/claims/` hold the claims
  the truth gate executes.
- `bench/` — the longitudinal cost record.
- `data/` and `graph/` are not in the tree: a checkout symlinks them to the
  sibling `../MicrobiomeKG-Data/` (`raw/`, `graph/`), and
  `--data ../MicrobiomeKG-Data` names the same directory without the links.

## Building and testing

```bash
make venv          # provision .venv and install the package editable
make build         # the graph (minutes; needs data/raw — see docs/sources.md)
make gate          # the pre-commit gate: ruff, bounds, blueprint composition, the truth gates
make test          # the full suite
make docs          # sphinx -W
```

Two flags are off by default. `--with-kegg` is a licence gate. `--with-vectors`
is a cost gate: the character-n-gram vector index buys query-time tolerance for
a *misspelt* organism name and nothing else, while costing +82.6 s of build,
`.kgl` 46.7 MB → 212.7 MB, load 1.03 s → 2.41 s and serving RSS 1.2 GB → 3.7 GB
(the `2026-09-03` capture, `bench/results/`). A default build says in its report
that the lane was skipped and which flag turns it on.

The conventions an agent works under are `CLAUDE.md`, and `CONTRIBUTING.md` is
the short version for a contributor.

## Licence

**The code is MIT** (`LICENSE`). That covers this repository — the preps, the
blueprint fragments, the ontology modules, the build and the MCP surface — and
nothing else.

**The data is not ours to relicense, and none of it ships here.** No raw input
and no built graph is distributed: a build reads sources the operator fetched
under each source's own terms, and every edge carries the `source_licence` it
came with. In a default build that is `CC-BY-4.0`, `CC0-1.0`,
`CC-BY-SA-3.0`, `CARD-noncommercial`, `HMDB-noncommercial`, `unknown`, and an
`-unstated` token on the sources whose papers state no redistribution terms —
so a query can select exactly the cut it is allowed to pass on. It is a real
constraint: 80,118 edges carry an `-unstated` token, against 68,752 that are
CC0.

Per-source terms are in `docs/sources.md` ("Redistribution: what blocks
shipping a built graph"); what that leaves a redistributable cut looking like
is measured in `docs/evaluation.md`. KEGG is behind `--with-kegg` for exactly
this reason.

If you use this pipeline in published work, `CITATION.cff` has the citation —
and cite the sources you actually loaded, which `docs/sources.md` lists with
their papers.

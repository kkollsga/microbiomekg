# The graph model

MicroMap's shape (taxa, diseases, metabolites, pathways, drugs, resistance,
papers) with one thing added that it does not have: **an association edge
cannot exist without saying how it was demonstrated**, and the ontology
reports what fraction of them fail that.

Everything below marked *(increment 1)* is built and measured. Increment 1 is
NCBI taxonomy + BugSigDB; the rest of the sources extend the same shapes.

---

## 1. Node types

| Type | pk | title | Source of the key | Increment |
|---|---|---|---|---|
| `Taxon` | `tax_id` (int) | `scientific_name` | NCBI `nodes.dmp` | 1 |
| `UnresolvedTaxon` | `unresolved:<source>:<raw>` | `raw_name` | our own | 1 |
| `Disease` | source CURIE (`MONDO:0005265`) else `cond:<slug>` | `label` | BugSigDB "EFO ID" | 1 |
| `BodySite` | `UBERON:0001155` else `site:<slug>` | `label` | BugSigDB "UBERON ID" | 1 |
| `Study` | `bsdb:<n>` | `title` | BugSigDB BSDB ID prefix | 1 |
| `Signature` | `bsdb:<study>/<exp>/<sig>` | `description` | BugSigDB BSDB ID | 1 |
| `Paper` | `pmid` (int) | `title` | PubMed | 1 |
| `Metabolite` | HMDB id | `name` | HMDB; ChEBI/KEGG/PubChem as properties | 2 |
| `Pathway` | `R-HSA-…` / `mapNNNNN` | `name` | Reactome / KEGG, `source` property | 2 |
| `Drug` | ChEMBL id | `pref_name` | ChEMBL `max_phase = 4` | 3 |
| `ProteinTarget` | ChEMBL target id | `pref_name` | ChEMBL; `uniprot` property | 3 |
| `AROTerm` | `ARO:3000015` | `name` | CARD `aro.obo` | 3 |

Decisions worth the ink:

**`Disease` is not EFO-keyed, despite the column name.** BugSigDB's "EFO ID"
column carries twelve vocabularies: MONDO 48%, EFO 36%, then HP, OBA, CHEBI,
GO, NCBITAXON, CL, OBI, PATO, XCO, ENVO, and more. The pk is therefore the raw
CURIE and the prefix is kept as an `ontology` property, so
`WHERE d.ontology = 'MONDO'` is expressible instead of silently pretending the
column is homogeneous. The 1.3% of signatures with a condition label but no
CURIE get a `cond:<slug>` key, never a drop.

**`Paper` is separate from `Study`.** Every later source (CARD, ChEMBL,
Disbiome) cites PMIDs too, so `Paper` is the join point that makes "what else
does this paper support?" a one-hop query. `Study` is BugSigDB's curation unit;
`Paper` is the literature. Verified: the study-level fields (PMID, title,
journal, year, DOI) are perfectly constant within all 2,126 BugSigDB studies,
so hoisting them to a node loses nothing.

**A few PMIDs are not PMIDs.** A handful of rows put a DOI or a PMC id in the
PMID column. Those get no `Paper` node and no `pmid` on the edge, and the raw
string is kept as `Study.pmid_raw` so the loss is visible.

### `Signature` is a node — recommended, and why

The choice was between a flattened `(Taxon)-[:ASSOCIATED_WITH {…20 fields}]->(Disease)`
edge and a `Signature` node with one edge per taxon. **The model uses both, with
a rule that stops it being duplication:**

> Anything the ontology must *audit* lives on the edge. Everything else lives on
> the `Signature` node.

- `Signature` (14,846 nodes) carries the full 30-field curation record: group
  names and definitions, variable region, sequencing platform, data
  transformation, MHT correction, LDA cutoff, matched-on, confounders, alpha
  diversity, curator, curation date, figure of origin, state.
- `ASSOCIATED_WITH` (117,160 edges) carries the **ten-field evidence
  contract** and nothing else, because `required_properties` is the only
  completeness check kglite can enforce, and it works on **edge** properties
  only. Putting the evidence on the `Signature` node would make the whole
  premise of this project unauditable.

What the `Signature` node buys, concretely:

- "How many independent studies support this taxon in this disease?" is
  `count(DISTINCT r.study_id)` either way, but "which experimental arms, at what
  group sizes, from which figure?" needs the node.
- The evidence for 115k taxon mentions is written **once per signature** rather
  than being a per-mention string blob.
- The 1.3% of signatures with no condition still exist as nodes with their taxa
  attached; a purely flattened model would have nothing to hang them on.

What the flattened edge buys: `shortestPath` and evidence filtering are one hop,
not three, and the ontology can audit them.

`sub_nodes` were considered for `Signature` under `Study` and rejected:
`Signature` is referenced by `Taxon` and `Disease` from outside its parent, so
it is a first-class node, not owned detail. `sub_nodes` fits the
`Signature`→per-taxon-statistic table if a later source provides effect sizes
per taxon (BugSigDB does not).

---

## 2. Edge types and the evidence contract

| Edge | Domain → Range | Carries |
|---|---|---|
| `HAS_PARENT` | `Taxon` → `Taxon` | — (parent pointer, `ancestry`) |
| `ASSOCIATED_WITH` | `Taxon` → `Disease` | **the evidence contract** |
| `REPORTED_BY` | `ReportedTaxon` → `Signature` | reconciliation provenance |
| `PART_OF_STUDY` | `Signature` → `Study` | — |
| `IN_CONDITION` | `Signature` → `Disease` | — |
| `AT_BODY_SITE` | `Signature` → `BodySite` | — |
| `PUBLISHED_AS` | `Study` → `Paper` | — |

### The evidence contract on `ASSOCIATED_WITH`

Ten properties, declared `required_properties` in the ontology. One edge per
`(signature, taxon, condition)` — parallel edges are the point, not an error:
they *are* the independent observations.

| Property | Type | From | Missing (measured) |
|---|---|---|---|
| `direction` | string `increased`/`decreased` | Abundance in Group 1 | 0.8% |
| `study_design` | string | Study design | 0.02% |
| `evidence_level` | string, **derived** (below) | design + sequencing + host | 0% |
| `sequencing_type` | string `16S`/`WMS`/`ITS / ITS2`/`18S`/`PCR` | Sequencing type | 1.0% |
| `statistical_test` | string | Statistical test | 1.3% |
| `group_0_size` | int | Group 0 sample size | 11.7% |
| `group_1_size` | int | Group 1 sample size | 11.6% |
| `pmid` | int | PMID | 0.9% |
| `source` | string `bugsigdb` | ours | 0% |
| `signature_id` | string, the BSDB ID | BSDB ID | 0% |

Also carried, deliberately outside the audited contract because they are
context rather than evidence: `study_id`, `host_species`,
`body_site`, `significance_threshold`, `mht_correction`.

**Measured headline: 14.00% of association edges (16,455 of 117,160) are
missing at least one contract field.** That number is what
`ontology_audit()` returns and what the build prints, and it is the number the
project exists to make visible.

`required_properties` reports one row per *edge*, not per field, so the audit
gives one honest completeness fraction and the per-field breakdown is a Cypher
query (§7, Q5). That is a deliberate reading of the tool, not a workaround.

### `evidence_level`

Derived in `microbiomekg.ontology.evidence_level(study_design, sequencing_type,
host_species)`; the design→level table is `EVIDENCE_LEVELS`. First match wins:

1. `laboratory experiment` → `in-vitro` when no live host is named, else
   `in-vivo-model`;
2. any non-human host → `in-vivo-model`, whatever the design — *a mouse RCT is
   not human interventional evidence*;
3. `randomized controlled trial` → `interventional-rct`; `meta-analysis` →
   `meta-analysis`;
4. an observational design refined by what it sequenced →
   `observational-shotgun` / `observational-16S` / `observational-amplicon` /
   `observational-targeted` / `observational-unspecified`;
5. otherwise `unknown` — never silently "observational".

Measured over all 14,846 signatures: `observational-16S` 55.6%,
`in-vivo-model` 20.2%, `observational-shotgun` 12.2%, `interventional-rct`
5.1%, `meta-analysis` 2.3%, `observational-unspecified` 1.9%, `in-vitro` 1.2%,
`observational-amplicon` 0.7%, `observational-targeted` 0.7%, `unknown` 0.1%.

> **Gotcha, load-bearing.** BugSigDB joins multiple designs with commas, and one
> of its designs — `cross-sectional observational, not case-control` — *contains
> a comma*. A naive `split(",")` shreds 4,170 of 14,846 rows into two bogus
> atoms. `split_study_designs()` does longest-key-first substring matching
> instead; verified to reconstruct all 14,846 cells exactly.

### `REPORTED_BY` — the provenance edge

`(Taxon | UnresolvedTaxon) -[:REPORTED_BY]-> (Signature)`, 114,742 edges,
carrying `reported_name`, `reported_rank`, `reported_tax_id`,
`resolution_status`, `resolution_note`, `direction`, `source`. Its
`required_properties` are declared at `enforcement: error` because *we* write
them unconditionally — a violation there is a bug in this repo, not upstream
data, so it should fail the build.

Its domain is the abstract class `ReportedTaxon`, which is the one place an
abstract class earns its keep here: one declaration covers edges from two
concrete types, and `ontology_audit({by: 'domain_class'})` then splits the
result by resolved-vs-unresolved for free.

---

## 3. Taxon reconciliation

Implemented in `microbiomekg/reconcile.py` (`TaxonomyIndex`, `Resolution`), not
in the prep scripts, so every source routes through one policy.

**NCBI `tax_id` is the canonical key.** Nothing else. Names are lookup keys.

1. **An explicit id beats a name.** BugSigDB *does* carry NCBI ids (column
   `NCBI Taxonomy IDs`), so it resolves by id and the name is only a label.
   Disbiome and CARD will resolve by name.
2. **`merged.dmp` remap**, chased transitively. Measured: **413 of 115,634
   BugSigDB taxon mentions point at an id NCBI has since merged.** Without the
   remap those become 413 dangling or duplicate taxa.
3. **Rank promotion.** `rank_ceiling` defaults to `species`: anything more
   specific (strain, subspecies, varietas, isolate, serotype…) is promoted to
   its nearest ancestor at or above the ceiling, status `promoted`, with the
   original id kept in `reported_tax_id` and the walk recorded in
   `resolution_note`. Measured: 152 promotions.
   The rule for **unplaced** ranks (`no rank`, `clade`) matters and is easy to
   get wrong: such a node is treated as below the ceiling only if its *nearest
   placed ancestor* is also below it. Otherwise `Enterobacteriaceae incertae
   sedis` (rank `no rank`, parent = a family) would be "promoted" to its family
   and a real intermediate node would vanish.
4. **Name lookup** is case-insensitive over the name classes
   `scientific name`, `synonym`, `equivalent name`, `genbank synonym`,
   `includes`. `authority` and `in-part` are excluded — the first is a citation
   string, the second is explicitly *not* a name for the taxon it is filed
   under. `common name` is excluded by the same rule, which is why `E. coli`
   does not resolve.
4b. **Authority stripping, as a fallback only.** NCBI keeps some legacy
   binomials *only* in decorated form, and one of them is the most-cited
   renamed organism in the field:

   ```
   1496 | Clostridioides difficile                                        | scientific name
   1496 | Clostridium difficile (Hall and O'Toole 1935) Prevot 1938 …     | synonym
   ```

   There is no bare `Clostridium difficile` row anywhere in `names.dmp`, so a
   literal lookup of the name every paper prints returns nothing. Same for
   *Lactobacillus plantarum*, *Lactobacillus reuteri* and *Eubacterium rectale*.
   `strip_authority()` builds a second index keyed on the bare name, consulted
   **only after the exact index misses**, so `Escherichia coli K-12` still
   resolves to its own taxon rather than collapsing onto *E. coli*. The rule
   cuts at the first `(` or four-digit year and leaves a string with neither
   untouched — which is what keeps it from manufacturing hits for
   `Clostridium symbiosum` (bracket marker) or `Cibiobacter qucibialis`
   (`Candidatus` marker). A normalised match records the decorated spelling it
   matched in `note`.
5. **Ambiguity is never guessed.** A name matching more than one taxon returns
   `status="ambiguous"`, `tax_id=None`, and the full candidate tuple. The dump
   has 1,992 ambiguous name keys (`bacteria`, `paracoccus`,
   `bacteroides corrodens`, …). Picking the first would be a silent wrong
   answer; returning candidates lets the caller disambiguate with context this
   module does not have.
6. **Nothing is dropped.** Anything with `tax_id is None` — `ambiguous`,
   `deleted`, `unresolved` — becomes an `UnresolvedTaxon` node with the raw
   string, the status, the candidates and the note, wired to its signatures by
   the same `REPORTED_BY` edge a resolved taxon uses, and written to
   `data/csv/unresolved_taxa.csv`. Measured: 1 such node — NCBI **deleted**
   `3120442` (*Staphylococcales*), still cited by 16 BugSigDB signatures. That
   one node is the whole argument for the policy: a silent drop would have
   removed 16 real observations and left no trace.

`Resolution.status` ∈ `exact` | `synonym` | `merged` | `promoted` |
`ambiguous` | `deleted` | `unresolved`. `resolve()` never raises, and never
returns a `tax_id` for the last three.

Measured over BugSigDB: `exact` 115,042, `merged` 413, `promoted` 163,
`deleted` 16 (of 115,634 mentions), collapsing to 8,078 distinct taxa.

---

## 4. The ontology declaration

`microbiomekg/ontology.py::ONTOLOGY`, written to `ontology.json`, referenced by
`blueprint.json`'s top-level `"ontology"` key so the declarations become a
build-time gate.

```python
"ASSOCIATED_WITH": {
    "domain": "Taxon", "range": "Disease",
    "required_properties": EVIDENCE_CONTRACT,          # the ten fields
    "property_types": {"pmid": "integer", "group_0_size": "integer", ...},
    "enforcement": {"required_properties": "warn", "property_types": "error"},
},
```

**Severity is split on who owns the gap**, which is the lifecycle the kglite
ontology guide prescribes:

- `warn`, permanently: `ASSOCIATED_WITH.required_properties` (14.0%),
  `IN_CONDITION.required` (1.3%), `AT_BODY_SITE.required` (0.5%). These are
  upstream curation reality. Failing the build on BugSigDB's missing group
  sizes would only mean never building; the number belongs in the build log,
  not the exit code.
- `error`: `REPORTED_BY.required_properties`, both `property_types` checks,
  `PART_OF_STUDY.required`/`cardinality`, `PUBLISHED_AS.cardinality`. These are
  things *our* prep guarantees, so a violation is a regression here and should
  stop the build. All measure 0.

**`ancestry: True` on `HAS_PARENT`, never `transitive: True`.** They are
mutually exclusive and mean different things: `transitive` is a promise that the
closure is *stored*, and it enrolls `transitivity_violation`, which flags every
`a→b→c` with no stored `a→c`. We store parent pointers only, so `transitive`
would report ~100% violations on a perfectly correct taxonomy. `ancestry`
records that the chain is meaningful and is walked with `*1..`, and enrolls no
check — exactly the parent-pointer shape. (The 512-class cap says the same thing
from the other side: a 3M-node taxonomy is *data*, not classes.)

Classes are kept minimal and only `ReportedTaxon` is abstract, because it is the
only place an abstract class buys a union endpoint (§2). `Metabolite`, `Drug`
and the rest are **not** declared yet: a concrete class naming no live node type
is a returned warning, so classes land with their data.

Materialization (`materialize_ontology()`) is **not** used. It would stamp
`:ReportedTaxon` on 863k `Taxon` nodes to make one query shape shorter, and
`MATCH (t:Taxon|UnresolvedTaxon)` already expresses the union without a managed
label to maintain.

---

## 5. Storage: microbial scope, default (in-memory)

**Recommendation: `--scope microbial` (Bacteria + Archaea + Fungi + everything
cited), `storage="default"`.** Measured on this machine, with the full BugSigDB
layer attached:

| Scope | Taxa | Nodes | Edges | Build | Peak RSS | `.kgl` |
|---|---|---|---|---|---|---|
| `cited` | 10,515 | 30,827 | 289,735 | 0.6 s | — | 4 MB |
| `microbial` | 863,879 | 884,191 | 1,143,099 | **2.4 s** | **1.23 GB** | 25 MB |
| `all` | 2,993,226 | ~3.0 M | ~3.3 M | (not built) | ~4 GB est. | — |

An evidence-filtered `ASSOCIATED_WITH` scan runs in **7 ms** at microbial
scope, and a BM25 index over all 863,879 scientific names builds in **0.2 s**
(442,903 terms). There is no memory or latency argument for `mapped` or `disk`
here, and `disk` would additionally **refuse `build_text_index()`** — the BM25
index is heap-resident by design, and text search over taxon names and
synonyms is a core feature of this graph, not a nicety. Revisit only if a later
source pushes the graph past ~10M nodes.

Loading the *whole* 3.0M-node dump buys nothing: 2.0M of the 2.9M taxa are
under Eukaryota and will never be cited by a microbiome source.

**But the clade filter must never lose a fact.** 192 of the taxa BugSigDB cites
live outside Bacteria/Archaea/Fungi (viruses, protists, host plants). Without
special handling the loader vivifies them as untitled stub nodes and says so in
a single warning nobody reads. `prep_taxonomy.py --scope microbial` therefore
unions the clade walk with `cited_taxa.csv`; verified afterwards by
`build_text_index('Taxon','scientific_name')` reporting `skipped: 0` where it
previously reported `skipped: 192`.

Every scope also includes the **full ancestor chain** of everything it selects,
so `parent_tax_id` never dangles and `-[:HAS_PARENT*1..]->` always terminates at
a domain. `root`'s self-parent is blanked; a self-loop there would make the walk
non-terminating.

---

## 6. Text search (BM25, `build_text_index`)

| Node type | Property | What it is for |
|---|---|---|
| `Taxon` | `scientific_name` | the everyday lookup |
| `Taxon` | `synonyms` | reconciliation by an old name — "Bacillus coli" → *Escherichia coli* |
| `Disease` | `label` | condition free text, since 48% of ids are MONDO and few users know MONDO ids |
| `Signature` | `description` | the curator's sentence: "genus-level microbes correlating with odor intensity" |
| `Paper` | `title` | literature entry point |

Not indexed: `Study.title` (identical to `Paper.title`), `BodySite.label` (237
values, an exact match is better), any numeric or CURIE field.

`Taxon.synonyms` is a `" | "`-joined **string**, capped at 20 names per taxon
(68 taxa hit the cap at microbial scope). It is not a list property — see §8.

Index sizes at microbial scope: `Taxon.scientific_name` 863,879 documents /
442,903 terms; `Taxon.synonyms` 103,111 / 98,543 (760,768 taxa have no synonym
at all, so BM25 skips them — an absent property is not an empty document);
`Signature.description` 14,425 / 6,383; `Disease.label` 992; `Paper.title`
2,110. All five build in well under a second.

---

## 7. Demo queries

All eight run against the built graph.

**Q1 — taxon → disease with an evidence filter.** The query the whole model
exists for: only shotgun or RCT evidence, both arms ≥ 30 subjects, a citation
present.

```cypher
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
WHERE r.evidence_level IN ['observational-shotgun', 'interventional-rct']
  AND r.group_0_size >= 30 AND r.group_1_size >= 30
  AND r.direction = 'increased' AND r.pmid IS NOT NULL
RETURN d.title AS disease, t.title AS taxon,
       count(r) AS n_signatures, count(DISTINCT r.study_id) AS n_studies
ORDER BY n_studies DESC, n_signatures DESC LIMIT 10
```

Top row: *Peptostreptococcus stomatis* ↑ in colorectal cancer, 17 signatures
across 8 studies — followed by *Parvimonas micra* and *Fusobacterium
nucleatum*, which is the textbook CRC result and a good sanity check that the
pipeline is not scrambling anything.

**Q2 — biomarker signature for one condition.**

```cypher
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0005265'})
RETURN t.title AS taxon, t.rank AS rank, r.direction AS direction,
       count(DISTINCT r.study_id) AS studies,
       collect(DISTINCT r.evidence_level) AS levels
ORDER BY studies DESC LIMIT 20
```

**Q3 — the ancestry walk: everything under a genus, with its evidence.** This is
what `ancestry: True` documents.

```cypher
MATCH (g:Taxon {title: 'Bacteroides'})<-[:HAS_PARENT*1..]-(t:Taxon)
MATCH (t)-[r:ASSOCIATED_WITH]->(d:Disease)
WHERE r.evidence_level STARTS WITH 'observational'
RETURN t.title AS taxon, d.title AS disease, r.direction, r.pmid
ORDER BY taxon
```

**Q4 — shortestPath between a taxon and a disease.**

```cypher
MATCH p = shortestPath((t:Taxon {id: 853})-[*..4]-(d:Disease {id: 'MONDO:0005011'}))
RETURN length(p) AS hops, [n IN nodes(p) | labels(n)[0]] AS types
```

Returns 1 hop when a direct association exists — the flattened edge is doing its
job. For the *evidence* path rather than the shortcut, ask for it explicitly:

```cypher
MATCH p = (t:Taxon {id: 853})-[:REPORTED_BY]->(s:Signature)-[:IN_CONDITION]->(d:Disease)
RETURN s.title, s.evidence_level, s.group_0_size, s.group_1_size LIMIT 5
```

**Q5 — per-field evidence completeness**, the breakdown the audit's single
percentage rolls up:

```cypher
MATCH (:Taxon)-[r:ASSOCIATED_WITH]->(:Disease)
RETURN count(r) AS edges,
       sum(CASE WHEN r.direction       IS NULL THEN 1 ELSE 0 END) AS no_direction,
       sum(CASE WHEN r.pmid            IS NULL THEN 1 ELSE 0 END) AS no_pmid,
       sum(CASE WHEN r.group_0_size    IS NULL THEN 1 ELSE 0 END) AS no_group0,
       sum(CASE WHEN r.statistical_test IS NULL THEN 1 ELSE 0 END) AS no_stat
```

→ `117160, 894, 1074, 13666, 1515`.

**Q6 — resolve an obsolete name through the synonym index.**

```cypher
MATCH (t:Taxon) WHERE text_bm25(t, 'synonyms', 'Bacillus coli') > 0
RETURN t.title, t.rank, text_bm25(t, 'synonyms', 'Bacillus coli') AS score
ORDER BY score DESC LIMIT 3
```

→ *Escherichia coli* (10.16), well clear of the next hit.

**Q7 — what failed to reconcile, and what it cost.**

```cypher
MATCH (u:UnresolvedTaxon)-[:REPORTED_BY]->(s:Signature)
RETURN u.title AS raw_name, u.status, u.note, count(s) AS signatures
```

→ `Staphylococcales | deleted | 3120442 listed in delnodes.dmp | 16`

**Q8 — the ontology audit.** The project's headline metric.

```cypher
CALL ontology_audit() YIELD rule, severity, violations, exempted, total, pct
RETURN rule, severity, violations, total, pct ORDER BY pct DESC
```

```
ASSOCIATED_WITH.required_properties   warn      16455 / 117160   14.00%
IN_CONDITION.required                 warn        200 / 14846     1.30%
AT_BODY_SITE.required                 warn         78 / 14846     0.50%
ASSOCIATED_WITH.property_types        error         0 / 117160     0.00%
REPORTED_BY.required_properties       error         0 / 114742     0.00%
PART_OF_STUDY.cardinality             error         0 / 14846      0.00%
… 24 rules total, all others 0
```

Drill down to individual edges with
`CALL edge_property_violation() YIELD relationship, check, source, target, property`,
and split by source type with `CALL ontology_audit({by: 'domain_class'})`.

---

## 8. Building it, and what the blueprint could not express

```bash
uv venv .venv && uv pip install --python .venv/bin/python pandas kglite

.venv/bin/python scripts/prep_bugsigdb.py     # writes cited_taxa.csv — run first
.venv/bin/python scripts/prep_taxonomy.py --scope microbial

KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE=1000000 \
  .venv/bin/python -c "import kglite; kglite.from_blueprint('blueprint.json', verbose=True)"
```

**That environment variable is not optional, and this is a kglite defect.** The
blueprint junction-edge loader streams each junction CSV in 100,000-row chunks
and calls the connect path once per chunk; parallel edges are written on the
*first* call for a relationship type and **deduplicated on every call after it**.
`taxon_disease.csv` is ~117k rows of deliberately parallel edges, so a default
build silently produced 109,065 of them instead of 117,160 — **7.7% of the
evidence lost, with no warning and no error**. Setting the chunk size above the
row count restores the exact count (verified both ways). Worth reporting
upstream: the chunk boundary changes the *result*, not just the memory profile.

Four other things the blueprint format could not express:

1. **No list property from CSV.** `map_blueprint_type` accepts only
   `string`/`int`/`float`/`bool`/`date`-family plus the spatial and temporal
   virtual types. `add_nodes` turns a DataFrame column of Python lists into a
   native list property and `from_records` does the same for a JSON array, but a
   CSV column cannot. `Taxon.synonyms` is therefore a `" | "`-joined string —
   fine for BM25 and `contains()`, but `'Bacillus coli' IN t.synonyms` is not
   available. The alternative (a `TaxonName` sub-node per name) would add ~3.5M
   nodes to serve a lookup that already happens in Python at prep time.
2. **FK edges cannot carry properties** — only junction edges can. Any
   evidence-bearing edge therefore needs its own CSV even when the data is 1:1
   with a node row. That is why `taxon_disease.csv` exists as a separate file
   rather than being columns on `signature.csv`.
3. **No secondary labels.** `NodeSpec` has no `labels` field, so the ontology
   guide's advice to model multi-role nodes with secondary labels is not
   reachable from a blueprint build; the escape hatches are a post-build
   `SET n:X` or `materialize_ontology()`. This bites because `is_a` is a
   **forest** — `Taxon` can have exactly one parent class, so it cannot be both
   `ReportedTaxon` (union of things a signature names) and a future
   `Associatable` (union of things that associate with a disease). When
   `Metabolite` and `Drug` arrive with their own association edges, either the
   forest is re-rooted or the relationships get distinct names.
4. **The ontology audits edge properties only.** There is no
   `required_properties` for *node* properties, which is the single fact that
   decided §1's edge-vs-node split. And `required_properties` reports per edge,
   not per property, so a ten-field contract yields one percentage and the
   per-field breakdown has to be a Cypher query (Q5).

Two upstream data traps, both silent, recorded so the next source does not
re-learn them:

- BugSigDB's two taxon columns use **different delimiters**: `MetaPhlAn taxon
  names` separates taxa with `,`, `NCBI Taxonomy IDs` separates them with `;`,
  and both use `|` between lineage ranks. Pairing them that way aligns on all
  14,225 rows that carry taxa; using the same delimiter for both misaligns
  11,273 of them — and the misalignment is *plausible*, so it would have
  attached wrong names to right ids for most of the graph.
- 4.2% of BugSigDB rows carry taxon *names* with no id column. Pairing the two
  columns positionally makes those rows produce zero taxa — the whole row
  vanishes without a warning. The name-only path resolves them by name instead,
  which is precisely what §3 exists for.
- The DOI column mixes bare DOIs, `https://doi.org/…` and DataCite URLs, and
  DOIs are case-insensitive by spec, so the same paper appears three times
  unless the value is normalised (`normalise_doi()`).
- BugSigDB writes missing values as the literal string `"NA"`. Passing that
  through would fill every evidence gap with a non-null value and drive the
  audit to 0.00% — a green gate that means nothing. `na()` in
  `prep_bugsigdb.py` maps it to an empty cell, which kglite reads as an absent
  property.

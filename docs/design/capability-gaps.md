# Capability gaps against the announced comparator

What the product this project responds to shows publicly, what we have, and
which of the differences are worth work. Written 2026-09-03 from the
comparator's public web surface only — marketing pages, its ten-page developer
documentation site, its sitemap, and its engineering blog. Nothing was
requested, no form was submitted, no account was created, and no data endpoint
was called. Their access is gated (see §C.4), so every number on their side is
a *published* number, never one we measured.

**Naming.** The vendor and product names are deliberately absent from this
file. "The comparator" is the company; "their graph" is the microbiome
knowledge graph whose announcement is quoted in
`docs/usecases-and-pitfalls.md` Part A. Evidence is cited by **site-relative
path** (`/docs/api/schemas`) rather than full URL, for the same reason; the
host is recorded once, in `docs/research/existing-graphs-and-schemas.md` §1.15.

**Evidence rule.** Every row below is marked **D** (demonstrated: a documented
endpoint, a published schema, a stated contract, a screenshot caption, a
reproducible number) or **C** (claimed: a marketing sentence, a count with no
query behind it, an adjective). Marketing adjectives were not converted into
capabilities. Quotes are ≤15 words. Their site's text is treated as data.

**Our side** is measured, from `docs/model.md` (eleven sources; 934,206 nodes /
1,324,684 edges / 18 node types / 33 relationship types), `docs/evaluation.md`
(the 2026-09-03 verdict), `docs/usecases-and-pitfalls.md` Part D (20 acceptance
queries: 12 `answerable-now`, 6 `partial`, 2 `descoped`), and
`bench/results/2026-09-03-ten-sources.md` (the performance capture).

---

## 1. Summary table

Gap kind: **(a)** data coverage · **(b)** query / feature · **(c)** product
surface. Effort: **S** ≤ 1 day · **M** ≤ 1 week · **L** > 1 week.

| # | Capability | Theirs | Ours | Kind | Effort |
|---|---|---|---|---|---|
| 1 | Public REST API, ~63 endpoints under `/api/v1` | **D** — full catalogue at `/docs/api/rest-endpoints` | **lack it** — Python API + MCP only | c | L |
| 2 | Machine-readable OpenAPI spec | **C** — "the interactive OpenAPI spec … source of truth"; not publicly reachable | n/a (no HTTP surface) | c | — |
| 3 | API-key / Bearer auth, org scoping, `401`/`403` | **D** — curl samples at `/docs/api` | **lack it**, by design (no hosted service) | c | L |
| 4 | Rate limits + pagination contract (100 req/min; `limit` ≤ 1000) | **D** — tables at `/docs/api` | **lack it** | c | M |
| 5 | Cross-entity search, autocomplete, per-type counts | **D** — `/search`, `/search/suggest`, `/search/counts` | **partial** — BM25 + optional vector lanes exist; no autocomplete/count surface | b + c | M |
| 6 | Shortest path / connections / neighborhood endpoints | **D** — `/graph/path`, `/graph/connections`, `/graph/neighborhood` | **have it** as Cypher (D16); no endpoint | b (surface only) | S |
| 7 | Cross-feeding endpoints and a consumption-shaped relation | **D** — `/networks/cross-feeding`; `UTILIZES`, `PROCESSES` in the published schema | **have it**, and measured: 4,784 `CONSUMES`, 387 `DEGRADES`, 894 `NO_EXCHANGE_WITH` | b (parity; see §D.1.3) | — |
| 8 | Probiotic-candidate and SCFA-producer discovery endpoints | **D** — `/discovery/probiotics/{disease_id}`, `/discovery/scfa-producers` | **have it** as Cypher (D10; butyrate 109 producers) | b (surface only) | S |
| 9 | Biomarker / signature endpoints keyed by `signature_id` | **D** — `/biomarkers/{signature_id}` | **have it, better** — `Signature` is a node, 14,846 of them, 114,742 membership edges | — | — |
| 10 | Published node/relationship schema (15 labels, 21 relations) | **D** — `/docs/api/schemas` | **have it, better** — 18 node types, 33 relations, plus per-property types and required-property rules | — | — |
| 11 | Property-level schema, field types, evidence model in the docs | **absent** — no property list on any docs page | **have it** — 14-field evidence contract, `docs/model.md` §2 | — | — |
| 12 | A per-connection confidence score | **D** — and it is *entity-mapping* confidence: "Exact NCBI ID match = 1.0. Fuzzy name match = 0.7" | **deliberately declined** — components stored, never a score (`docs/model.md` §2, guard F10) | — | — |
| 13 | Evidence *type* per association (experimental vs observational) | **absent** — no docs page or post defines one | **have it** — 12-value `evidence_level`, 0% missing, plus Biolink `knowledge_level` × `agent_type` | — | — |
| 14 | Per-edge provenance: source DB, DOI, confidence, extraction method | **C** — stated in a blog post, absent from the schema page | **have it** — `primary_source`, `source_record_id`, `pmid`, `source_licence`, `source_relation` on every association edge | — | — |
| 15 | Direction normalised, source wording preserved | **C** — "increased, decreased, and associated"; original description kept | **have it** — `direction` + `source_relation`, 0.8% missing | — | — |
| 16 | Provenance write-back: Experiment → Analysis → Assertion ledger | **D** — contract, fields, JSON shapes at `/docs/provenance` | **lack it**, and it is out of scope for a pipeline library | b | L |
| 17 | Temporal assertions (`valid_from`/`valid_to`, `as_of`, `supersedes`) | **D** — documented request/response | **lack it** | b | L |
| 18 | Decision ledger (`DecisionEvent` ingest + query) | **D** — field contract at `/docs/api/schemas` | **lack it** | b | L |
| 19 | MCP server with a read-only graph-query tool | **D** — `query_graph`, `get_schema`, `list_databases` at `/docs/api/mcp-tools` | **have it** — 7 tools, 8 skills injected, read-only enforced with a typed refusal | — | — |
| 20 | ~40 MCP tools spanning ingest, execution, files | **D** — full tool catalogue published | **lack it** (we expose query + schema only) | c | L |
| 21 | Generic ingest engine: 9 stages, human approval gate, 5 discipline templates, 15 input formats | **D** — stage list, template table, format list at the ingest-engine docs page | **partial** — blueprint + prep + ontology per source, discovered not listed (`docs/design/library-pipeline.md`); no approval gate, one discipline | b | L |
| 22 | 55 validated pipeline nodes + custom node publishing | **C** — count stated, catalogue not published | **deliberately declined** — D19/D20 descoped; matrices and FBA belong to SIAMCAT/MICOM | — | — |
| 23 | Proprietary interpretable rule-mining model | **C** — one illustrative rule, no evaluation | **deliberately declined** — D19 descoped (no sample-level matrices) | — | — |
| 24 | Hosted natural-language agent returning cited answers | **D as a screenshot** — hero alt text describes "a real … session"; not reproducible | **partial** — MCP surface exists, no hosted app, no human front door | c | L |
| 25 | Managed / self-hosted / licensed deployment | **C** | **deliberately declined** — we ship a pipeline, not a service | — | — |
| 26 | Versioned ingestion with staging diff and review | **C** — blog post only; "still our biggest operational headache" | **partial** — `fetch.py` manifest with sha256 per file; no staging diff | b | M |
| 27 | Named source list (11 databases) | **C** — no versions, no per-source counts, no licences | **have it, better** — `docs/sources.md`: 16 sources, per-file URL/sha256/date, licence and redistribution analysis | — | — |
| 28 | Association layer 63,316 assoc. / **2,981 microbes** / **243 diseases** | **C** — homepage headline | **ahead** — 112,966 association edges, 56,124 distinct pairs, 808 `Disease` nodes (§D.1.1) | — | — |
| 29 | 1.7M+ entities, 1.1M+ taxa, 6,500+ metabolites, 6,200+ drugs, 2,028 proteins | **C** | comparable-to-larger except taxa (§D.1.2) | a (partly) | — |
| 30 | `Gene` and `Protein` as first-class nodes with their own endpoints | **D** — labels published, `/genes/{id}/taxa`, `/proteins/{id}/drugs` | **partial** — `ProteinTarget` (ChEMBL) exists; **no `Gene` node** (Part D D8) | a + b | M |
| 31 | Federation across discipline graphs | **C** — "one query can span multiple constituent graphs" | **lack it**; not wanted | b | — |
| 32 | Documentation site: 10 pages, search, catalogues | **D** | **partial** — tracked Markdown, no published site yet | c | M |
| 33 | Measured performance numbers | **absent** — only a rate-limit policy and one agent latency range | **have it** — `bench/results/`, 38 query cells, controls, MCP overhead | — | — |
| 34 | Measured negative results (tested-and-found-nothing edges) | **absent** — no relation in the published schema is a refutation | **have it, uniquely** — 61,127 measured/curated negatives | — | — |
| 35 | Per-field completeness audit of its own data | **absent** | **have it** — `ontology_audit()`, 15.5% of association edges incomplete, published | — | — |

---

## 2. Section A — data-coverage gaps

Sources or entity types they have and we do not. Each names the public source
that would fill it, and its licence.

### A.1 Disbiome — the one association source they have and we cannot fetch

Their blog names Disbiome among the eleven integrated databases
("NCBI Taxonomy, Disbiome, BugSigDB, gutMDisorder, HMDB, KEGG, ChEMBL,
Reactome, PubMed, PubChem, and CARD", 2026-04-11). `docs/sources.md` §3
records ours as **unreachable**: the origin does not complete a TCP connection
and Wayback has never captured its JSON API (confirmed by a domain-wide CDX
query). Licence: Disbiome's terms are unstated by the site.

Consequence: one fewer independent curation to cross-check BugSigDB against —
which is exactly what §D.2.5's cross-source agreement benchmark needs a third
arm for. **Status: blocked, not declined.** Two partial routes exist and both
are benchmark inputs rather than loaders: **Peryton** (7,977 experimentally
supported microbe–disease associations, 43 diseases; DIANA-lab, freely
downloadable) and **HMDAD** (483 curated associations, 39 diseases, 292
microbes) redistribute much of the same literature. See §D.2.3–4.

### A.2 KEGG — they ship it, we gate it off

KEGG is in their eleven. Ours has a working loader behind `--with-kegg` and
contributes **zero edges to a default build**, verified. This is
**deliberately declined**, not a gap: `docs/sources.md` §7 records that KEGG is
"not a public database", that a service on top of it needs a licence, and that
a graph containing KEGG content cannot be published freely. Their public pages
do not mention any KEGG licence.

### A.3 PubChem — a compound-identity source we do not load

Named in their eleven; ours carries PubChem ids only as *properties* on HMDB
records, never as a source. Public, PubChem data are in the public domain.
Filling it would add compound synonymy and cross-references, not associations.
Low value: our `Metabolite` key is already ChEBI-where-available, and MiMeDB
already contributes the 1,237 compounds HMDB lacks. **Not recommended.**

### A.4 A `Gene` node type

Their published schema has `Gene`, `ENCODED_BY`, `PARTICIPATES_IN`, and the
endpoints `/genes/{gene_id}/taxa` and `/genes/{gene_id}/pathways`. We have
`ProteinTarget` (ChEMBL) and `ResistanceGene` (CARD ARO), but Part D records
"the gene layer W7 asks for rides on the edge, and there is still no `Gene`
node" — Zimmermann 2019's locus tags are edge properties on 32 `METABOLISES`
edges. Public sources that would fill it: **UniProt** (CC BY 4.0) for
protein↔gene identity, and **gutSMASH** (already named in `docs/evaluation.md`
§4.1 for D13's gene leg; MIT-licensed tool, its output is derived data).
Effort **M**; it changes D13 from `partial` and gives W4 the enzyme leg it
lacks.

### A.5 Where the coverage difference is a *shape* difference, not a gap

Three of their headline counts look like coverage we lack and are not:

- **1.1M+ taxa.** Ours is 864,110 `Taxon` nodes, of which **8,717 carry any
  claim**. Their 1.1M is approximately NCBI Taxonomy itself, so both numbers
  count lineage scaffolding. The comparable number is claims-bearing taxa, and
  their homepage now publishes it: **2,981 microbes** in the association layer,
  against our 7,753 in the same query (§D.1.1).
- **231,556 production links** (Part A). Their current site does not repeat
  this figure and their docs publish no per-relation count. Ours is **3,418**.
  This remains the largest genuine coverage difference in the comparison, and
  `docs/evaluation.md` §4.2 already prices it at 68×. No downloadable source
  carries per-taxon production at that scale — MiMeDB was fetched twice to test
  exactly that and publishes a *count* of 830,984 pairs while naming none of
  them (`docs/sources.md` §12). A 231,556-edge production layer is almost
  certainly propagated or inferred; nothing public lets us check.
- **276,169 AMR links** (Part A). Ours is 26,619. `docs/evaluation.md` §5
  identifies theirs as CARD *Prevalence*, which CARD's own documentation calls
  in-silico and outside its primary curation. **Deliberately declined**: we
  load the curated half, and our own predicted layer is 104 of 13,691 edges,
  removable with one `WHERE`.

---

## 3. Section B — query / feature gaps

Things a user can do there and not here, with the shape we would need.

### B.1 Entity comparison (`/taxa/compare`, `/diseases/compare`)

Two documented endpoints with no equivalent here. The shape is a set
intersection over two entities' association neighbourhoods:

```cypher
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
WHERE d.id IN [$a, $b]
WITH t, collect(DISTINCT d.id) AS in_both, count(DISTINCT r.study_id) AS studies
WHERE size(in_both) = 2
RETURN t.title, studies ORDER BY studies DESC
```

Effort **S**. Worth adding to the demo-query set in `docs/model.md` §7 rather
than as an API.

### B.2 Autocomplete and typed result counts

`/search/suggest` and `/search/counts` are documented; we have BM25 indexes on
`Taxon.scientific_name`, `Taxon.synonyms`, `Disease.label`,
`Signature.description` and `Paper.title`, plus an opt-in vector lane. What is
missing is the *count-by-type* rollup a search UI needs:

```cypher
CALL text_search('Taxon', 'scientific_name', $q, 50) YIELD node, score
RETURN 'Taxon' AS type, count(*) AS n
```
one call per indexed field, unioned. Effort **S** as a helper; **M** if it
becomes a surface.

### B.3 The provenance write-back loop

Their `Experiment → Analysis → Assertion → Decision` ledger, with deterministic
assertion ids (`sha256(analysis_id | subject | predicate | object)`), validity
windows, `supersedes`, and point-in-time `as_of` queries, is the most
substantial *feature* on their side that we have no counterpart to. It is a
different product though: it exists so a customer's own analyses can be written
back into a tenant-scoped graph. Our design (`docs/design/library-pipeline.md`)
ships a pipeline and no service, so there is no tenant to scope to.

**Assessment: deliberately declined for the library; noted as the strongest
candidate if the project ever grows a hosted surface.** One piece of it is
cheap and worth stealing regardless: `library-pipeline.md` rule 7 already wants
`build` to stamp the graph with its source set and raw-file digests, which is
the same idea one level up — provenance of the *graph*, not of an assertion.

### B.4 Federated multi-domain query

Claimed, not demonstrated (`/docs/concepts`: routes across "microbiome,
genomics, transcriptomics, metabolomics, proteomics" constituents). No public
example, no schema for a second constituent. Not a gap worth acting on.

### B.5 Pipeline execution and model training

Their 55 pipeline nodes, custom-node publishing, and rule-mining model are
capabilities we have explicitly descoped: D19 ("train a cross-cohort
classifier") and D20 ("compute per-sample cross-feeding fluxes") are marked
`descoped` in Part D with reasons — no sample-level abundance matrices, and
genome-scale simulation is computation over an input community rather than a
database to load. Part D also fixes the terms on which a computed layer could
ever be ingested: `knowledge_level = 'prediction'`,
`agent_type = 'computational_model'`, `evidence_level = 'computational-predicted'`,
**in its own relationship type**. That constraint is worth restating whenever
this gap is raised.

---

## 4. Section C — product-surface gaps

This is where the difference is largest and least about data.

### C.1 An HTTP read surface

They publish ~63 endpoints in 13 groups. We have none. `docs/evaluation.md` §6
already names this as the live objection — *"There is no human entry point: no
browser, no CLI query tool, no export"* — and §7 item 2 already proposes the
fix. The comparator's catalogue is a usable **specification** for the shape:
per-entity get/list/search, two-hop relations (`/taxa/{id}/diseases`,
`/metabolites/{id}/producers`), traversal, and per-entity provenance. Effort
**L** for a service; **M** for a documented CLI + CSV export, which is what
evaluation §7 actually asks for.

### C.2 Access model

`/docs/quickstart`: "There is no self-serve signup — access is granted and
scoped to your organization." Their rate policy is 100 requests per minute per
key, `limit` default 100 / max 1000, offset pagination, `429` on overage.

Ours is the mirror image: no access control at all, because the artefact is a
build script and a `.kgl` file. This is not a gap to close; it is the same
choice `library-pipeline.md` makes ("No data and no finished graph ships"). It
*is* the reason no head-to-head measurement is possible (§C.4).

### C.3 Documentation surface

Their docs are ten pages: introduction, quickstart, core concepts, two
component pages, provenance, and a four-page reference (API, REST endpoints,
MCP tools, schemas), with sidebar navigation and a search box. What they do
well, and what a published site of ours should match or beat:

| They publish | Quality | Ours today | What ours needs |
|---|---|---|---|
| Endpoint catalogue, 13 groups, every path listed | strong | n/a | the CLI/Python verb catalogue in the same shape |
| Auth + errors + status codes + pagination + rate limits, as tables | strong | n/a | licence gates and cost gates as the equivalent contract tables |
| Copy-pasteable `curl` and MCP JSON config | strong | scattered in `docs/model.md` §7 | one quickstart with runnable Python + Cypher |
| Node labels and relationship types | present, list only | `docs/model.md` §1–2 with types and required properties | publish it as a reference page, not prose |
| Assertion field contract with types | strong | our 14-field evidence contract is stronger | publish it as the headline page |
| MCP tool catalogue with one-line purposes | strong | `microbiomekg/mcp/microbiomekg_mcp.yaml` is not documented for a reader | a tool + skill reference page |
| **Data sources with versions and licences** | **absent** | `docs/sources.md`, 16 sources, per-file sha256 | publish it — this is the page they cannot write |
| **Evidence / confidence definition** | **absent from the docs**; only in an April blog post | `docs/model.md` §2 `evidence_level`, 12 values | publish it — the second page they cannot write |
| **Completeness audit of their own data** | **absent** | `ontology_audit()`, D15 | publish the numbers, including the bad ones |
| Changelog / versioning page | **absent** | `CHANGELOG`-shaped history not yet published | a dated source-set + graph-shape changelog |
| Any benchmark or validation page | **absent** | `bench/results/` | publish the capture, controls and all |

The honest summary: **their documentation is excellent about the surface and
silent about the data.** Not one page defines what a confidence score means —
that definition exists only in a blog post (§D.1.5) — and no page lists a
source, a version, a licence, or a per-relation count. `docs/design/release-readiness.md`
should treat the four bolded rows as the differentiator and the six above them
as table stakes.

### C.4 What a head-to-head would need that we cannot obtain

Their API is provisioned per organisation; `/docs/api` states plainly that
"there is no shared public endpoint", and the one public host their April blog
post cited for API docs now returns `404`. Therefore:

- **Per-relation counts on their side are unobtainable.** `/api/v1/stats` would
  give them; it requires a key.
- **Latency is unobtainable.** Every timing comparison in §D.3 is a policy on
  their side against a measurement on ours, and is labelled as such.
- **Their answer to any specific query is unobtainable.** Every kind-1
  benchmark below is therefore *"our number against their published number"*,
  never *"our answer against their answer"*.

**Obtaining a key would require asking them for access, which this analysis was
instructed not to do and did not do.** If the user ever wants a true
head-to-head, that request is the prerequisite, and it is theirs to make.

---

## 5. Section D — benchmarks we can run

The most useful output here. Three kinds, cheapest and most decisive first.
"Runnable today" means: no new download, against the current build.

### D.1 Kind 1 — reproducible from what they publish

#### D.1.1 The association-layer shape — the single most decisive number

Their homepage publishes the whole shape of the layer, not just its size:

> "63,316 microbe–disease associations, spanning 2,981 microbes and 243 diseases"
> — homepage, *Proof* section (**C**: a headline, no query behind it)

Ours, same shape, three ways — because our edges are one-per-report and theirs
are of unstated granularity, the fair comparison is **distinct pairs**:

```cypher
// edge count, and the pair/microbe/disease shape behind it
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
WITH t, d, count(r) AS reports
RETURN count(*)            AS distinct_pairs,
       sum(reports)        AS association_edges,
       count(DISTINCT t)   AS microbes,
       count(DISTINCT d)   AS diseases
```

Known from `docs/evaluation.md` and Part D without re-running: **105,880**
disease edges (112,966 over all three condition types), **56,124** distinct
pairs (D17), **7,753** taxa in the cross-disease query (D3), **808**
`Disease` nodes. So on the layer that actually carries claims we are
**~2.6× their microbes and ~3.3× their diseases**, at a comparable pair count.

**Runnable today. Highest value of anything in this file**, because it inverts
the reading in `docs/evaluation.md` §5, which compared our 808 diseases against
their *node* count of 1,464 and concluded ours was "smaller". Against the layer
they now publish, ours is larger. §F.1 records the correction.

#### D.1.2 The six headline entity counts

| They publish (**C**) | Ours (measured) | Runnable today |
|---|---|---|
| 1.7M+ entities | 934,206 nodes | yes |
| 1.1M+ taxa | 864,110 `Taxon`; **8,717 with any claim** | yes |
| 1,400+ diseases | 808 `Disease` (931 `Condition`); **243 vs 808 is the live comparison** | yes |
| 6,500+ metabolites | 9,056 `Metabolite` (see §G.3) | yes |
| 6,200+ drugs | 6,408 `Drug` | yes |
| 2,028 proteins | `ProteinTarget` count not stated in `docs/model.md`; `drug_target.csv` is 7,018 rows | yes — **and it fills a hole in our own docs** |

```cypher
MATCH (n) RETURN labels(n)[0] AS type, count(*) AS n ORDER BY n DESC
```

#### D.1.3 Cross-feeding — the claim in our evaluation that needs re-testing

`docs/evaluation.md` §5 argues that our cross-feeding query is a structural win
because "a production-only graph … returns 0.0 on every row". **Their public
schema does not support the premise.** `/docs/api/schemas` lists `UTILIZES` and
`PROCESSES` among the 21 relationship types, and
`/docs/api/rest-endpoints` documents `/networks/cross-feeding` and
`/networks/cross-feeding/{taxon_id}` (**D**: documented endpoints). So they
demonstrate a cross-feeding *surface*; what they publish no number for is its
*size*.

The benchmark to run is our own MES table, published with its inputs so the
comparison is on volume and provenance rather than on existence:

```cypher
MATCH (m:Metabolite)
OPTIONAL MATCH (p:Taxon)-[:PRODUCES]->(m) WHERE p.placeholder = false
OPTIONAL MATCH (c:Taxon)-[:CONSUMES]->(m) WHERE c.placeholder = false
WITH m, count(DISTINCT p) AS P, count(DISTINCT c) AS C
WHERE P > 0 AND C > 0
RETURN m.title, P, C, 2.0*P*C/(P+C) AS mes ORDER BY mes DESC LIMIT 20
```

Runnable today; known: 96 metabolites carry both halves; acetate 441/72,
butyrate 109/26. **A head-to-head needs their `/networks/cross-feeding`
response, which needs a key (§C.4).**

#### D.1.4 The four other announced query types (Part A A5)

Each of theirs is now a documented endpoint, so the comparison is
query-shape-to-endpoint and is runnable today on our side alone:

| Theirs (**D**, documented endpoint) | Ours | Status |
|---|---|---|
| `/taxa/{id}/diseases`, `/diseases/{id}/taxa` | D2 — 40 reports across 21 studies for one pair | runs, 89.6 µs |
| `/metabolites/{id}/producers`, `/taxa/{id}/metabolites` | D5 — 4 products for *A. muciniphila*, 109 producers for butyrate | runs |
| `/graph/path` | D16 — 1 hop direct, 3-hop evidence walk | runs, 14.2 µs |
| `/biomarkers/disease/{id}`, `/discovery/probiotics/{id}` | D1 + D10 — 26→32 IBD candidates at `n_studies ≥ 2` | runs |
| `/discovery/scfa-producers` | see below | runs |

The SCFA one is worth publishing on its own because it is a named, closed
question and their endpoint implies a specific answer set:

```cypher
MATCH (t:Taxon)-[:PRODUCES]->(m:Metabolite)
WHERE m.title IN ['Butyric acid','Acetic acid','Propionic acid']
RETURN m.title, count(DISTINCT t) AS producers ORDER BY producers DESC
```

#### D.1.5 Their confidence scale, reproduced as our decomposition

Their engineering blog defines the score their marketing sells:

> "Exact NCBI ID match = 1.0. Fuzzy name match = 0.7. Genus-level-only match = 0.5."
> — engineering blog, *What We Learned Integrating 12 Biological Databases…*, 2026-04-11 (**D**: a stated definition)

and

> "We estimate that ~95% of our associations have high-confidence entity mappings."
> (**C**: "we estimate", no query)

This is **entity-mapping confidence, not evidence strength** — which settles
Part A's A1 objection against them in their own words, and confirms
`docs/research/existing-graphs-and-schemas.md` guard F10. Our directly
comparable, *decomposed* quantity is the reconciliation ledger:

```cypher
MATCH (:ReportedTaxon)-[r:REPORTED_BY]->(:Signature)
RETURN r.resolution_status, r.resolution_normalized, count(*) AS n
ORDER BY n DESC
```

Runnable today over 114,742 edges; known: `resolution_normalized` is `false` on
all 114,742 BugSigDB edges because BugSigDB resolves by id. The publishable
number is our exact-id share against their estimated 95%, plus the count of
`UnresolvedTaxon` tombstones — the population they describe as "flagged but
included" and we keep as nodes.

#### D.1.6 Their build claim

> "… built [their graph] — a microbiome knowledge graph — from raw sources in days"
> — homepage (**C**; the two product names are elided per the naming rule)

Ours is measured: **5.4 min** end-to-end for a full rebuild over 7.5 GB of raw
input, 1,379,915 CSV rows, 54 tables, peak RSS 5,197 MB
(`bench/results/2026-09-03-ten-sources.md` §1). These measure different things —
theirs includes first-time source integration, ours is a reproducible rebuild —
so publish both with that caveat rather than as a ratio. Note their own blog
contradicts the homepage on the manual half: "Budget 3x the time you think you
need" and "queued for human review before it enters the graph" (their
ingest-engine page)
against "no manual curation pipeline" (homepage). See §F.4.

---

### D.2 Kind 2 — vendor-independent benchmarks in the field

These score the graph against the literature, not against a competitor, so they
survive the comparator disappearing.

#### D.2.1 Maier 2018's headline — **runnable today, already passing**

Published: 24% of human-targeted drugs inhibited at least one gut strain.
Ours from the loaded edges: **24.3%** (203 of 835), reproduced in Part D D8 and
asserted by `tests/test_acceptance.py`.

```cypher
MATCH (d:Drug)-[r:INHIBITS_GROWTH_OF]->(:Taxon) WHERE r.drug_class = 'human-targeted drugs'
WITH count(DISTINCT d) AS hit
MATCH (d2:Drug)-[r2]->(:Taxon)
WHERE type(r2) IN ['INHIBITS_GROWTH_OF','DOES_NOT_INHIBIT_GROWTH_OF']
  AND r2.drug_class = 'human-targeted drugs'
RETURN hit, count(DISTINCT d2) AS screened, 100.0*hit/count(DISTINCT d2) AS pct
```

**What it demonstrates:** that the loader is faithful enough to a published
screen to reproduce its abstract. Promote it from a test assertion to a
published benchmark row. Effort **S**.

#### D.2.2 Zimmermann 2019's headline — **runnable today, already passing with a priced gap**

Published: 176 of 271 drugs metabolised by at least one strain. Ours:
**172 of 271**, with the four-drug gap named and priced (two unresolved strain
names left unresolved rather than guessed). Publishing the *gap* is the point:
a benchmark that reports 172/176 with the reason is worth more than one that
reports 176/176 by rounding.

#### D.2.3 HMDAD coverage/recall — **one download**

HMDAD (Ma et al. 2017) is the standard held-out set the microbe–disease
association-prediction literature scores against (LRLSHMDA, KATZHMDA, NTSHMDA
and successors, typically 5-fold CV / LOOCV AUC in the 0.85–0.91 range).
**We should not chase those AUCs** — D19 is descoped, we hold no matrices, and
training a link predictor is a different product. What we *can* score is
**coverage**, which is the question a curated graph should be judged on:

- **Dataset:** HMDAD, 483 curated microbe–disease associations, 39 diseases,
  292 microbes. Distributed from its lab page and redistributed in the public
  repos of most of the prediction papers; **licence unstated upstream — record
  it as unstated, the same way we handle MASI.**
- **Split:** none. All 483 pairs, as a recall target.
- **Metric:** (i) fraction of HMDAD pairs our graph independently asserts, after
  taxon reconciliation to `tax_id` and disease reconciliation to MONDO;
  (ii) the `evidence_level` histogram of the ones we cover; (iii) the pairs we
  cover *and contradict on direction*.
- **The join:** reconcile HMDAD's microbe strings through the same BM25 +
  authority-stripping path `REPORTED_BY` uses, then
  `MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)` on the reconciled pairs.
- **Expected range:** unknown, and it should stay unknown until run. HMDAD is
  2016-era and genus-heavy; our BugSigDB spine is far larger, so recall should
  be high — but the *reconciliation* half is exactly the thing this project
  claims to do well, so a low number would be a real finding, not a data gap.
- **What it demonstrates:** the first number in this project that is scored
  against an external, vendor-neutral, widely-cited reference set.

#### D.2.4 Peryton coverage — **one download**

Peryton (Skoufos et al., NAR 2021) publishes 7,977 *experimentally supported*
microbe–disease associations over 43 diseases, freely downloadable from the
DIANA-lab site (licence: check and record at fetch time). Same join and same
three metrics as D.2.3, with one addition that HMDAD cannot support: Peryton
tags its associations as experimentally supported, so the overlap can be split
by **our** `evidence_level` and the two evidence models compared directly. That
is the closest thing to an external validation of the twelve-value ladder that
exists.

#### D.2.5 Cross-source direction agreement — **runnable today**

The Duvallet-2017 shape of question ("do independent studies agree?") applied
to the sources already in the graph. Two arms exist today (BugSigDB,
gutMDisorder) and MASI adds a curated third:

```cypher
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
WITH t, d, collect(DISTINCT r.primary_source) AS srcs,
        collect(DISTINCT r.direction) AS dirs
WHERE size(srcs) > 1
RETURN size(dirs) = 1 AS agree, count(*) AS pairs
```

Known baselines to state alongside it, both already measured: **8,238
conflicts** and **47,232 of 56,124 pairs single-cohort (84.2%)** (D17).
**What it demonstrates:** the honest replication picture, which is this
project's strongest and least flattering claim — and which no comparator
publishes at all.

#### D.2.6 Duvallet et al. 2017 non-specificity — **one download**

Duvallet et al., *Nat Commun* 8:1784 (2017), CC BY 4.0, meta-analyses 28
case-control studies across 10 diseases and separates a broadly-shifted
"non-specific" genus set from disease-specific ones. Our D14 answers the same
question by signature *breadth* and its top six are Bacteroides, Streptococcus,
Prevotella, Lachnospiraceae, Lactobacillus, Oscillospiraceae. **Metric:**
overlap@10 and rank correlation between our breadth ranking and their
non-specific set. **What it demonstrates:** that a breadth proxy computed from
one curation reproduces a published cross-study meta-analysis — which is
exactly the claim `docs/evaluation.md` §4.1 says is currently a *proxy* for the
missing GMrepo prevalence data. If it reproduces, the proxy is validated; if it
does not, GMrepo moves up the backlog with evidence.

*(The brief also names Tierney et al. 2022 for cross-study consistency. The web
search budget was exhausted before that citation could be verified in this
session — treat it as a lead, not a source, until checked. See §H.)*

#### D.2.7 BugSigDB loader fidelity — **runnable today, no download**

BugSigDB's own paper (Geistlinger et al., *Nat Biotechnol* 42:790, 2024;
PMC11098749) states counts for studies, experiments and signatures in the
release. Our build reports 2,126 studies and 14,846 signatures from the
2026-09-02 `full_dump`. **Metric:** exact agreement between our loaded counts
and the source's own published/exported counts for the same dump.
**What it demonstrates:** that 110,547 of our 112,966 association edges — the
single-source risk `docs/evaluation.md` §6 names as the case against the
project — are a faithful transcription and not a distortion. Cheapest decisive
benchmark on this list.

---

### D.3 Kind 3 — performance

Their public performance surface is two numbers, and neither is a measurement.

| They publish | Kind | Our measured cell | Comparable? |
|---|---|---|---|
| "100 requests per minute per API key" (`/docs/api`) | **D**, a *policy* | median Part D cell ≈ 1.5 ms in-process → ~660 q/s single process | **No** — a quota against a latency. State both; do not divide. |
| `limit` default 100, max 1000 (`/docs/api`) | **D**, a policy | our queries return whole result sets (D8.5 → 2,575 rows in 4.79 ms) | **No** — but worth stating: their cap forces 3 round trips for a 2,575-row answer |
| "30-60 seconds vs. 5 seconds for a simple query" (blog, agent modes) | **C** | our MCP round trip: `mcp_floor` 20.8 µs, D2 97.7 µs, heaviest audit 439 ms | **No** — theirs is an LLM turn, ours is transport + engine. The LLM dominates both. |
| — | — | MCP server boot + handshake **4.10 s**, once per session | a real disadvantage against an always-on hosted service; measured, ours |
| — | — | full rebuild **5.4 min**; `from_blueprint` **2.74 s**; save 653 ms (BM25) / 2.73 s (+vectors) | nothing on their side to compare to |

**The one honest performance statement available today:** every one of the 38
measured Part D cells answers inside the 600 ms per-request budget their own
published rate limit implies, and 33 of them fit more than 100× inside it —
but that compares our engine latency to their throughput policy, and the
comparison is illustrative, not a benchmark. Any real timing comparison needs a
key (§C.4).

Re-running `bench/bench.py` is not required for any of the above; the
2026-09-03 capture already carries every cell, with its control contract
holding and its machine-load caveat recorded.

---

## 6. Section E — where we are demonstrably ahead

Briefly, each with the query that proves it.

1. **Evidence type per edge, at 0% missing.** Twelve `evidence_level` values
   derived from source fields, never defaulted, plus Biolink `knowledge_level`
   × `agent_type`. Their entire public surface defines no evidence type; their
   only quality field is a name-matching score (§D.1.5). Proof: D4 — in-vivo
   17,858 · meta-analysis 4,297 · RCT 4,247 · in-vitro 1,613.

2. **61,127 measured negatives.** 42,233 "this drug did not inhibit this
   bacterium" + 17,479 "this bacterium did not touch this drug" + 894 curated
   refutations of exchange + 521 curated non-effects, as *their own relationship
   types* so no query counts a refutation as an observation. Nothing in the
   comparator's 21 published relationship types is a refutation. Proof: D8's
   metformin three-outcome — 0 inhibited, 38 tested-no-effect.

3. **A per-field completeness audit of our own data.** `ontology_audit()`
   reports 17,546 of 112,966 association edges (15.5%) missing at least one of
   fourteen contract fields, with a per-field and per-source breakdown (D15).
   Their docs publish no completeness figure of any kind.

4. **Provenance to study level, not paper level.** `Study` and `Paper` are
   separate nodes; an association resolves to design, cohort, body site,
   sequencing method and both arm sizes. Proof: D2 — 40 separate reports across
   21 studies for one pair, with the one dissenting study still present.

5. **A reconciliation ledger where nothing is dropped.** Every unresolved name
   is an `UnresolvedTaxon` node or a ledger row (`unresolved_conditions.csv`,
   `unresolved_production.csv`, `unresolved_maier2018.csv`,
   `unresolved_zimmermann2019.csv`), and input-row accounting is a test (C18).
   Their equivalent is "the remaining 5% are flagged but included" (**C**, no
   mechanism published).

6. **`Signature` as a first-class node.** 14,846 signatures, 114,742 membership
   edges, so the taxon *set* survives and enrichment (W1) is possible. Their
   published label list has no signature type, though `/biomarkers/{signature_id}`
   implies something equivalent exists — undecidable from public evidence.
   Proof: D1, `overlap ≤ signature_size` on every returned row.

7. **Per-edge licence, so a redistributable cut is one `WHERE`.**
   `source_licence` on 272,897 edges; the CC0 cut is 68,752 edges. Their public
   surface states no licence for any source, and their homepage's largest
   claimed layer (§A.5) has unknown provenance.

8. **An open, measurable pipeline.** `docs/sources.md` records every raw file's
   URL, byte count and sha256; two independent full builds produced identical
   graphs (932,372 nodes / 1,311,540 edges). Their build is a product.

9. **We publish what did not work.** MiMeDB contributing zero production edges,
   MASI restating 62.5% of what two primary screens already measured, HMDB's
   disease layer refused because 72% of it carries one name, the "unrecoverable"
   retraction in `docs/sources.md` §14. No vendor page can carry that, and it is
   the most credible thing in either surface.

---

## 7. Section F — what their surface contradicts in our own documents

Four corrections, all ours to make. **Do not fix them in this file** — each
belongs in the document that carries the claim.

1. **`docs/evaluation.md` §5 compares the wrong disease number.** It puts their
   1,464 diseases against our 808 and reads ours as "smaller". Their homepage
   now publishes the *association layer's* shape — 2,981 microbes and 243
   diseases — against which our 7,753 claim-bearing taxa and 808 diseases are
   larger. The row should compare layer to layer, with both numbers.

2. **`docs/evaluation.md` §5's cross-feeding "structural win" overstates.** It
   asserts a production-only comparator returns 0.0 on the MES query. Their
   published schema has `UTILIZES` and `PROCESSES` and their API documents
   `/networks/cross-feeding` (**D**). The win that survives is on *measured
   volume and provenance*, not on existence — and it is unverifiable either way
   without a key.

3. **`docs/research/existing-graphs-and-schemas.md` §1.15 says the schema is
   "Not published."** It now is: `/docs/api/schemas` publishes 15 node labels
   and 21 relationship types, and `/docs/api/rest-endpoints` publishes ~63
   endpoints. What remains unpublished is the *property-level* schema, the
   identifier convention, and any evidence model — which is the sharper and
   still-correct version of the same finding. The same §1.15 row "Provenance
   claim … not public" also needs updating: `/docs/provenance` publishes a full
   assertion contract.

4. **Their own two claims disagree, and our notes should say which we quote.**
   Homepage: "from raw sources in days, no manual curation pipeline" (**C**).
   Their ingest-engine page: "Every entity link … queued for human review before it enters
   the graph" (**D**, a documented stage). Blog: "Budget 3x the time you think
   you need." The documented pipeline has an explicit `approve` stage with a
   reviewer and timestamp, so "no manual curation pipeline" is the outlier.
   Quote the documented version.

---

## 8. Section G — proposed backlog items

> **Direction (user, 2026-09-03).** Focus on what the comparator does better, and
> improve there — but kglite is the superpower, and it lets the API surface stay
> *small*. Their endpoint catalogue is what one builds when the graph sits behind a
> database the user cannot be handed; each endpoint is a frozen query. Here the
> query language is the API: shortest path, neighbourhood, cross-feeding and
> probiotic discovery are each one Cypher statement (D16, D6, D10). So G8 is a
> **Cypher-first read surface** over what kglite already ships (Bolt, MCP, Python),
> documented as "one statement per endpoint group", plus only what Cypher cannot
> do (a typed-count / autocomplete recipe). What they genuinely do better after
> that reframe: always-on access (our 4.1 s MCP boot vs a service), documentation
> as a product surface, search with typed counts, and Gene/Protein as first-class
> entities — the last is the one real data gap.


At most eight, benchmarks first because they are cheap and decisive. Each is
one line of scope plus what it depends on. **Not filed here** — the coordinator
owns `dev-docs/todos.md`.

| # | Item | Scope | Depends on | Effort |
|---|---|---|---|---|
| G1 | **Association-layer shape benchmark** | Run §D.1.1 + §D.1.2, publish the table, and correct `docs/evaluation.md` §5 per §F.1 | nothing — current build | S |
| G2 | **Reconciliation-confidence benchmark** | Run §D.1.5; publish our `resolution_status` histogram and unresolved-tombstone count against their published 1.0/0.7/0.5 scale and 95% estimate | nothing — current build | S |
| G3 | **Drug-screen headline reproductions, promoted to published benchmarks** | Lift §D.2.1 and §D.2.2 out of `tests/test_acceptance.py` into a `bench/`-published table showing published-vs-measured and the priced 4-drug gap | nothing | S |
| G4 | **BugSigDB loader-fidelity benchmark** | Run §D.2.7 against the source paper's own stated counts for the loaded dump; red if they disagree | nothing | S |
| G5 | **Cross-source direction-agreement benchmark** | Run §D.2.5; publish agreement rate beside the 8,238 conflicts and 84.2% single-cohort figures | nothing | S |
| G6 | **External coverage benchmark: HMDAD + Peryton** | Fetch both, record licences (HMDAD unstated → use the `*-unstated` token convention), score coverage / evidence histogram / direction contradictions per §D.2.3–4. **Score against them; do not load them** | `scripts/fetch.py`; the reconciliation path used by `REPORTED_BY` | M |
| G7 | **Duvallet 2017 validation of the dysbiosis-breadth proxy** | Fetch the CC BY 4.0 supplementary, score D14's ranking by overlap@10 per §D.2.6; the result decides whether GMrepo (evaluation §7 item 3) moves up | one download | M |
| G8 | **A documented human read surface, shaped by their endpoint catalogue** | `docs/evaluation.md` §7 item 2 already scopes it (CLI + licence-tagged CSV export); use `/docs/api/rest-endpoints`' 13 groups as the verb list, and §C.3's four bolded rows as the documentation differentiator | `docs/design/library-pipeline.md`, `docs/design/release-readiness.md` | M |

**Runners-up, deliberately not filed** — each is already covered elsewhere or
too speculative to schedule: a `Gene` node type via UniProt/gutSMASH (§A.4;
overlaps evaluation §7's D13 note), GMrepo for healthy baselines (already
evaluation §7 item 3 — G7 decides its priority), an HTTP service and a
write-back ledger (§B.3, §C.1 — both are hosted-product features this project
has decided not to be), and PubChem (§A.3, low value).

---

## 9. Section H — what could not be verified

- **Any number on their side.** All of §D.1 compares our measurement to their
  published claim. Their API is provisioned per organisation, and the analysis
  was instructed not to request access.
- **Their OpenAPI spec.** `/docs/api/rest-endpoints` calls `/openapi.json` the
  "always-current source of truth"; it is not reachable without a provisioned
  base URL. The one public host their April blog post named for API docs
  returns `404` today.
- **Per-relation counts, source versions, source licences, and any
  evidence-model definition on their side.** Not published on any page.
- **Their video walkthroughs.** Two pages link "the full session on YouTube";
  the channel redirects to a consent interstitial, which would require
  accepting terms — out of bounds, so the videos are unread. They are the only
  place a worked example with real output values might exist.
- **Their code.** The obvious GitHub organisation exists with **zero public
  repositories**. There is no public package, no preprint, and no job ad found
  on the surfaces read.
- **A same-named ReadTheDocs project is a different thing.** A
  `readthedocs.io` site under the same word documents an unrelated 2023
  academic Python package for graph feature extraction from medical imaging —
  name collision, not their documentation. The "Read the Docs" link on their
  site is a button label pointing at `/docs` on their own domain.
- **Tierney et al. 2022** as a cross-study-consistency source (§D.2.6) — the
  session's web-search budget was exhausted before it could be checked.
- **One inconsistency on *our* side, found while writing this.**
  `docs/model.md` §1 says 9,056 `Metabolite` nodes (HMDB 7,773 · MiMeDB 1,237 ·
  NJC19 46); `docs/evaluation.md` §5 says 8,754 (MiMeDB 935). The bench
  capture's `metabolite.csv` is 8,754 rows for the ten-source build.
  **Resolved 2026-09-03:** the built graph holds 9,056 (`MATCH (m:Metabolite)
  RETURN count(*)`, by source 7,773 / 1,237 / 46), `tests/claims/` already
  asserts it, and `docs/evaluation.md` §5 was the stale row — corrected. The
  bench capture's 8,754 is a dated record of that build and stays.

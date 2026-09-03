---
name: metabolites_pathways
description: "TRIGGER for metabolite questions — 'which metabolites does taxon X
  produce', 'who makes butyrate / SCFAs / bile acids / TMAO', 'which taxa consume
  M', 'who could cross-feed whom', 'which pathway carries this production claim',
  'is that measured or predicted'. Read the coverage section BEFORE answering:
  production and consumption arrive from different sources at different sizes,
  the exchange layer is not gut-scoped, and the obvious ChEBI key for a
  short-chain fatty acid matches nothing at all. SKIP for drug metabolism (that
  is `drugs`) and for taxon-disease association (taxon_disease_evidence)."
references_tools: [cypher_query]
applies_when:
  graph_has_node_type: [Metabolite]
---

# Metabolite exchange and pathways: two curated layers, honestly sized

## Coverage first, because it changes the answer

**3,418 `PRODUCES` edges over 830 organisms and 226 metabolites** — `in-vitro`
3,383, `computational-predicted` 35 — from two sources that must be told apart
by `primary_source`:

- **NJC19** — 2,840 edges, 638 organisms, 99 metabolites. One 2020 curation of
  microbial physiology, CC0, species-level, every edge an experimentally
  observed export event.
- **HMDB** — 578 edges, 272 organisms, 154 metabolites, from free-text organism
  strings with no taxid.

Replication is thin and real: 43 (taxon, metabolite) pairs carry more than one
source record and the most any pair carries is 3 — HMDB and NJC19 independently
curating the same production, or several NJC19 species strings promoting onto
one NCBI node. It is not double-counting, and it is not corroboration at scale.

Two consequences to state in any answer:

- **The layer is not gut-scoped.** NJC19 curates microbial physiology, not a gut
  community, so a producer/consumer join will happily pair a swine pathogen with
  a deep-sea thermophile. Nothing on the edge restricts a pair to organisms that
  could ever meet; say "potential exchange" and name the organisms.
- **Neither source carries the enzyme or the reaction.** There is no enzyme
  property to return and no pathway of the production's own — the pathway layer
  below is about the *metabolite*, not about the taxon. MiMeDB is loaded and
  contributes 0 `PRODUCES` edges, because its published bulk downloads carry no
  microbe-metabolite association; when a caller needs per-taxon production with
  the enzyme, say the graph cannot supply it.

## Consumption, degradation and refutation — the cross-feeding half

**4,784 `CONSUMES` edges over 714 taxa and 205 metabolites**, all NJC19, all
`in-vitro`, plus **387 `DEGRADES`** over 212 taxa and 17 macromolecules
(cellulose, mucin, xylan, chitin …) and **894 `NO_EXCHANGE_WITH`** — the
curated refutations, `import-negative` 720, `degrade-negative` 87,
`export-negative` 87. A refutation is its own relationship so no query counts
it as an observation by omission.

Degradation is a separate relationship on purpose: extracellular breakdown of a
polymer is a different claim about a community from uptake of a small molecule.
Do not merge it into `CONSUMES`.

```cypher
// The Metabolite Exchange Score: MES = 2*P*C/(P+C), the harmonic mean of
// producer and consumer counts, which is identically 0 when either side is 0.
MATCH (m:Metabolite)
OPTIONAL MATCH (p:Taxon)-[:PRODUCES]->(m) WHERE p.placeholder = false
OPTIONAL MATCH (c:Taxon)-[:CONSUMES]->(m) WHERE c.placeholder = false
WITH m, count(DISTINCT p) AS producers, count(DISTINCT c) AS consumers
RETURN m.title AS metabolite, m.id AS id, producers, consumers,
       CASE WHEN producers + consumers = 0 THEN 0.0
            ELSE 2.0 * producers * consumers / (producers + consumers)
       END AS mes
ORDER BY mes DESC LIMIT 20
```

**96 metabolites carry both a producer and a consumer**, so 96 rows have a
non-zero MES and every other metabolite in the graph scores 0 — including every
metabolite whose only source is HMDB, which curates no consumption at all. The
top of the ranking is CO2, acetate, hydrogen, lactate and formate: what a
cross-feeding network is supposed to look like, and a reminder that these are
the promiscuous currency metabolites. *Acetic acid* is 441 producers against 72
consumers.

## The forward query (D5)

```cypher
MATCH (t:Taxon {id: $taxon_id})-[p:PRODUCES]->(m:Metabolite)
RETURN m.title AS metabolite, m.chebi_id AS chebi, m.status AS hmdb_status,
       p.evidence_level AS level, p.knowledge_level AS knowledge_level,
       p.reported_name AS organism_as_named, p.genus_level_evidence AS genus_only,
       p.publications AS refs, p.primary_source AS source
ORDER BY level, metabolite
```

`p.reported_name` is the organism string the source actually printed, and it is
worth returning: HMDB's is free text, misspelt and mixed-rank
(`Citrobacter frundii`, `Akkermansia muciniphilia`, phyla filed as "genus", a
ligature typo), and names that resolved to no tax_id are `UnresolvedTaxon` nodes
rather than dropped rows. `p.genus_level_evidence` is NJC19's own admission that
a species-filed row was read at genus level — 2,432 of its edges carry it as
true, 1,456 of them productions, and a species-level answer must not rest on
one.

*Akkermansia muciniphila* (239935) is the worked example: **4 products** —
acetic acid, ethanol, propionic acid, sulfate — and **3 consumptions** —
N-acetylgalactosamine, N-acetyl-D-glucosamine, D-glucose, which is the
mucin-degradation story at species level. All seven edges are NJC19's; HMDB
attributes no metabolite to it at all, so the source that was supposed to answer
this half of the question answers none of it.

## The reverse query, and the acid/base trap that makes it return nothing

```cypher
MATCH (t:Taxon)-[p:PRODUCES]->(m:Metabolite {id: $metabolite_id})
WHERE t.placeholder = false
RETURN t.title AS producer, t.rank AS rank, p.evidence_level AS level,
       p.primary_source AS source,
       count(DISTINCT p.source_record_id) AS n_records
ORDER BY level, n_records DESC
```

**Butyrate is `CHEBI:30772`, not `CHEBI:17968`.** The first is butyric *acid*,
which is what HMDB's record carries; the second is the conjugate base, and ChEBI
holds them as two terms. `Metabolite` is keyed on HMDB's `chebi_id`, so the distinction
survives as two identities and the "obvious" key returns **nothing at all** —
which looks exactly like "no source has this". Whenever a metabolite lookup
returns zero rows, resolve the name first rather than reporting absence:

```cypher
// CONTAINS, not text_bm25(): only five columns carry a BM25 index in this
// graph (Taxon.scientific_name, Taxon.synonyms_text, Disease.label,
// Signature.description, Paper.title) and Metabolite.name is not one.
MATCH (m:Metabolite)
WHERE toLower(m.name) CONTAINS toLower($name)
RETURN m.id AS id, m.title AS name, m.chebi_id AS chebi, m.status AS hmdb_status,
       m.selection_rule AS why_loaded
ORDER BY name LIMIT 10
```

With the right key, butyrate returns **109 producers, all `in-vitro`**: HMDB's 6
(*Roseburia*, *Eubacterium*, *Anaerostipes*, *Coprococcus eutactus*,
*Allocoprococcus comes*, *Faecalibacterium prausnitzii*) and 106 from NJC19, 3
of them shared. It also has 26 consumers, which is what makes butyrate a
cross-feeding question rather than a production one.

The join that makes those two sets meet is on the edge: NJC19 writes `Butyrate`
and HMDB writes `Butyric acid`, and `metabolite_join = 'conjugate'` records
every pair the `-ate` / `-ic acid` step matched. Where the graph holds a
conjugate pair as two nodes it still does — `formate` is `CHEBI:15740` while
HMDB's 10 formate producers sit on `Formic acid`, `CHEBI:30751` — so a caller
computing MES over a conjugate pair has to say which term they mean.

`m.selection_rule` says why the metabolite is in the graph at all —
`microbial-origin` (a microbial-origin claim), `feces` (a gut biospecimen),
`reactome-chebi` (reachable from a pathway), `njc19-exchange` (an exchange
partner) — a list, so filter it with `WHERE 'feces' IN m.selection_rule`. It is
a filter, not decoration.

## Pathways: capability, not production (D13)

```cypher
MATCH (t:Taxon {id: $taxon_id})-[p:PRODUCES]->(m:Metabolite)-[i:IN_PATHWAY]->(pw:Pathway)
RETURN m.title AS metabolite, pw.id AS pathway, pw.title AS pathway_name,
       pw.pathway_source AS pathway_source, pw.species AS pathway_species,
       i.evidence_code AS pathway_evidence, i.knowledge_level AS pathway_knowledge,
       p.evidence_level AS production_level,
       p.knowledge_level AS production_knowledge,
       'capability, not production' AS reading
ORDER BY pathway_source, pathway
```

The literal string in that `RETURN` is the point. **Reactome's 23,604 pathways
span 16 organisms, of which only 3 are organisms this graph also credits with
producing something** — *Mycobacterium tuberculosis*, *Plasmodium falciparum*
and *Saccharomyces cerevisiae*, a pathogen, a parasite and a yeast, and not one
gut commensal. So a pathway hit says the *metabolite* participates in a human
(or bovine, or zebrafish) pathway; it never says the taxon runs it. The
three-hop walk resolves 130,214 rows over 628 taxa and 1,125 pathways; *E. coli*
alone reaches 1,028, and every one of them is a statement about the metabolite.

**Read the evidence code.** `IN_PATHWAY` splits `IEA` 31,773 / `TAS` 4,357 —
87.9% is an orthology projection from human, not a read paper, carried as
`knowledge_level = 'logical_entailment'` against `'knowledge_assertion'`.
Without that on the answer, a Reactome hit reads as curated throughout.

The pathway DAG is a **DAG, not a tree**: 388 of the children in the
23,717-edge `PART_OF_PATHWAY` hierarchy have more than one parent. A walk that
assumes one parent loses them silently.

```cypher
MATCH (:Metabolite)-[i:IN_PATHWAY]->(pw:Pathway)
RETURN i.evidence_code AS evidence_code, i.knowledge_level AS knowledge_level,
       count(i) AS edges, count(DISTINCT pw) AS pathways
ORDER BY edges DESC
```

## What this layer cannot do

- **No gene-level production claim.** No source here carries the enzyme or the
  reaction behind a production edge, so the taxon-to-pathway assignment is
  genome-inferred in every case available, and measured gene abundance is
  "almost completely uncorrelated" with metabolite level across 1,135
  individuals.
- **No absence claim from `PRODUCES` alone.** A taxon with no production edge
  was not measured by either source; only `NO_EXCHANGE_WITH` records a curated
  "looked and found nothing", and it holds 894 edges against 9,056 metabolites.

---
name: metabolites_pathways
description: "TRIGGER for metabolite questions — 'which metabolites does taxon X
  produce', 'who makes butyrate / SCFAs / bile acids / TMAO', 'which pathway
  carries this production claim', 'is that measured or predicted'. Read the
  coverage section BEFORE answering: this layer is 578 production edges, and the
  honest answer to most 'who produces M' questions is that the source that would
  answer it is not loaded. SKIP for cross-feeding / consumption (there is no
  CONSUMES edge in this graph at all) and for drug metabolism (drugs)."
references_tools: [cypher_query]
applies_when:
  graph_has_node_type: [Metabolite]
---

# Metabolite production and pathways: a thin layer, honestly labelled

## Coverage first, because it changes the answer

**578 `PRODUCES` edges over 272 organisms and 154 metabolites** — `in-vitro`
543, `computational-predicted` 35 — and the replication count is **1** for
every (taxon, metabolite) pair. That is the whole production layer.

It is thin because of where it comes from: HMDB has 217,920 records, 88.8% of
them `predicted` or `expected`, and only **224 carry the ontology path that
makes a microbial-origin claim at all**. 67 of those name no organism. So a
"which taxa produce M" question usually has a small answer or none, and *none*
does not mean "no organism produces it".

Two consequences to state in any answer:

- ***Akkermansia muciniphila* (239935) has zero metabolites here.** A
  headline gut commensal, on the source that is supposed to answer this half of
  the question. That is coverage, not biology.
- **MiMeDB is the source that closes this** (29,295 metabolites, 3,725
  microbes, 25,276 curated reactions) and it is **not loaded**. When a caller
  needs per-taxon production with the enzyme, say that.

## The forward query (D5)

```cypher
MATCH (t:Taxon {id: $taxon_id})-[p:PRODUCES]->(m:Metabolite)
RETURN m.title AS metabolite, m.chebi_id AS chebi, m.hmdb_status AS hmdb_status,
       p.evidence_level AS level, p.knowledge_level AS knowledge_level,
       p.reported_name AS organism_as_named, p.enzyme AS enzyme,
       p.publications AS refs, p.primary_source AS source
ORDER BY level, metabolite
```

`p.reported_name` is the organism string HMDB actually printed. It is worth
returning: the source is free text, misspelt and mixed-rank
(`Citrobacter frundii`, `Akkermansia muciniphilia`, phyla filed as "genus", a
ligature typo), and names that resolved to no tax_id are `UnresolvedTaxon`
nodes rather than dropped rows.

## The reverse query, and the acid/base trap that makes it return nothing

```cypher
MATCH (t:Taxon)-[p:PRODUCES]->(m:Metabolite {id: $metabolite_id})
WHERE t.placeholder = false
RETURN t.title AS producer, t.rank AS rank, p.evidence_level AS level,
       count(DISTINCT p.source_record_id) AS n_records
ORDER BY level, n_records DESC
```

**Butyrate is `CHEBI:30772`, not `CHEBI:17968`.** 30772 is butyric *acid*, which
is what HMDB's record carries; 17968 is the conjugate base, and ChEBI holds
them as two terms. `Metabolite` is keyed on HMDB's `chebi_id`, so the
distinction survives as two identities and the "obvious" key returns **nothing
at all** — which looks exactly like "no source has this". Whenever a metabolite
lookup returns zero rows, resolve the name first rather than reporting absence:

```cypher
// CONTAINS, not text_bm25(): only five columns carry a BM25 index in this
// graph (Taxon.scientific_name, Taxon.synonyms, Disease.label,
// Signature.description, Paper.title) and Metabolite.name is not one.
MATCH (m:Metabolite)
WHERE toLower(m.name) CONTAINS toLower($name)
RETURN m.id AS id, m.title AS name, m.chebi_id AS chebi, m.status AS hmdb_status,
       m.selection_rule AS why_loaded
ORDER BY name LIMIT 10
```

With the right key, butyrate returns **six producers, all `in-vitro`**:
*Roseburia*, *Eubacterium*, *Anaerostipes*, *Coprococcus eutactus*,
*Allocoprococcus comes*, *Faecalibacterium prausnitzii*.

`m.selection_rule` says why the metabolite is in the graph at all —
`microbe` (a microbial-origin claim), `feces` (a gut biospecimen), `reactome`
(reachable from a pathway), joined with `|` when several applied. It is a
filter, not decoration: `WHERE m.selection_rule = 'feces'` counts the rule
instead of trusting a paragraph.

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
span 16 model organisms and not one gut commensal** — the only overlap with the
272 organisms HMDB attributes a metabolite to is *Mycobacterium tuberculosis*, a
pathogen. So a pathway hit says the *metabolite* participates in a human (or
bovine, or zebrafish) pathway; it never says the taxon runs it. The three-hop
walk resolves for 4,806 rows over 95 organisms and 635 pathways; *E. coli*
alone reaches 387.

**Read the evidence code.** `IN_PATHWAY` splits `IEA` 31,773 / `TAS` 4,357 —
87.7% is an orthology projection from human, not a read paper, carried as
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

- **No `CONSUMES` edge exists.** Cross-feeding needs one on both sides — the
  Metabolite Exchange Score is the harmonic mean of producer and consumer
  counts, and it is identically 0 when either is 0. Do not simulate consumption
  by inverting `PRODUCES`.
- **No gene-level production claim.** The taxon-to-pathway assignment is
  genome-inferred in every case available here, and measured gene abundance is
  "almost completely uncorrelated" with metabolite level across 1,135
  individuals.

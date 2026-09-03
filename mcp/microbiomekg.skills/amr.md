---
name: amr
description: "TRIGGER for antimicrobial resistance questions — 'which resistance
  genes does X carry', 'what confers resistance to <drug class>', 'by which
  mechanism', 'which taxa carry beta-lactamases', AMR surveillance over a
  metagenome's taxon list. SKIP for a drug's effect on bacteria or bacterial
  metabolism of a drug (that is `drugs`), and for resistance as a *disease*
  association (taxon_disease_evidence)."
references_tools: [cypher_query]
applies_when:
  graph_has_node_type: [ResistanceGene]
---

# AMR carriage: what the edge claims, and what it does not

The layer is CARD 4.0.2: **6,451 `ResistanceGene`s** (one node per CARD
*model*, not per ARO term), 50 `DrugClass`es, 8 `ResistanceMechanism`s, joined
by 6,415 `CARRIES_RESISTANCE_GENE`, 13,691 `CONFERS_RESISTANCE_TO` and 6,513
`VIA_MECHANISM` edges over **539 taxa**.

```cypher
MATCH (t:Taxon {id: $taxon_id})-[c:CARRIES_RESISTANCE_GENE]->(g:ResistanceGene)
OPTIONAL MATCH (g)-[:CONFERS_RESISTANCE_TO]->(dc:DrugClass)
OPTIONAL MATCH (g)-[:VIA_MECHANISM]->(m:ResistanceMechanism)
RETURN g.title AS determinant, g.id AS aro, m.title AS mechanism,
       dc.title AS drug_class, c.model_type AS model_type,
       c.sequence_derived AS from_reference_sequence,
       c.taxon_specificity AS taxon_specificity,
       c.evidence_level AS level, c.knowledge_level AS knowledge,
       c.primary_source AS source, c.source_licence AS licence
ORDER BY drug_class, determinant
```

For *E. coli* (562) that is 1,535 rows: 646 determinants, 31 drug classes,
7 mechanisms.

## The claim, stated plainly

**`sequence_derived = true` means the tax_id is the reference *sequence's*
organism** — "this sequence was cloned from this organism" — **not "this
organism is resistant".** That is the single most important sentence in this
skill. Report it with the answer; do not phrase a carriage edge as a resistance
phenotype.

Three consequences, each a countable filter rather than a caveat you have to
remember:

- **`taxon_specificity`** carries the call confidence CARD actually has. 132
  carriage edges are keyed on taxid 2 (*Bacteria*) alone, 264 are above species
  rank in total, and 18 point at something that is not an organism at all
  (plasmids, a transposon, a synthetic construct). All are kept and flagged;
  one `WHERE` excludes them.
- **Gene presence is not phenotype.** Even a perfect sequence hit "does not
  indicate if the AMR gene is expressed or if it results in elevated MIC".
  Measured against real resistance, tools of this class score 54-58% balanced
  accuracy.
- **The predicted layer is small and separable.** 104 of the 13,691
  `CONFERS_RESISTANCE_TO` edges — the 36 meta-models with no reference sequence
  — carry `evidence_level = 'computational-predicted'`. Excluding them is one
  clause; a headline "276k AMR links" from a prevalence file is a different
  population than this one.

**RGI hit category (Perfect / Strict / Loose) is not here and cannot be.** It
is produced by *running* RGI against a sample, so it is a per-sample output; no
CARD download carries it. Say it is unavailable rather than substituting
`taxon_specificity` for it silently.

## Mechanism is a node because a model can have two

`MexR` is `antibiotic efflux` **and** `antibiotic target alteration`. A string
property could hold only one, so ask through `VIA_MECHANISM` and expect
multiple rows per determinant.

```cypher
MATCH (g:ResistanceGene)-[:CONFERS_RESISTANCE_TO]->(dc:DrugClass)
MATCH (g)-[:VIA_MECHANISM]->(m:ResistanceMechanism)
MATCH (t:Taxon)-[c:CARRIES_RESISTANCE_GENE]->(g)
WHERE dc.title = $drug_class AND t.placeholder = false
RETURN m.title AS mechanism, count(DISTINCT g) AS determinants,
       count(DISTINCT t) AS taxa, collect(DISTINCT t.title)[0..8] AS example_taxa
ORDER BY determinants DESC
```

## Licence rides the edge, not the graph

`aro.obo` is `CC-BY-4.0`; `card-data/` is CARD's non-commercial licence. Only
**42 of 13,691** drug-class edges are `CC-BY-4.0` — the AMR answer lives almost
entirely in the non-redistributable half. `c.source_licence` is on every edge
so a redistributable subset can be selected; report the licence when the answer
will be republished.

```cypher
MATCH (:ResistanceGene)-[r:CONFERS_RESISTANCE_TO]->(:DrugClass)
RETURN r.source_licence AS licence, r.evidence_level AS level, count(r) AS edges
ORDER BY edges DESC
```

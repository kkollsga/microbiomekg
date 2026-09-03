---
name: signature_enrichment
description: "TRIGGER when the user arrives with a *list* of taxa — a
  differential-abundance result, a hit list, 'my 30 significant genera', 'which
  published studies match these' — and wants to know which curated signatures it
  overlaps, for which condition, at which body site, in which direction. Also
  for 'is this taxon just a generic dysbiosis marker'. SKIP for a single
  taxon-disease question (taxon_disease_evidence) and for anything asking the
  graph to compute an enrichment p-value: the graph serves the sets, the
  statistic runs outside it."
references_tools: [cypher_query]
applies_when:
  graph_has_node_type: [Signature]
---

# Signature overlap: the query the model was shaped for

A `Signature` is a **node**, not a flattened edge — 14,846 of them, each one
curator's published differential-abundance result, with its members hanging off
it as `(:Taxon)-[:REPORTED_BY]->(:Signature)`. That is what makes a hit list
comparable to published work: the taxon *set* survives. A model that flattened
this into `(Taxon)-[:ASSOCIATED_WITH]->(Disease)` destroys the set and makes
enrichment impossible.

The signature carries the whole curation record — group names and definitions,
`variable_region`, `sequencing_platform`, `data_transformation`,
`mht_correction`, `lda_cutoff`, `matched_on`, `confounders`,
`antibiotics_exclusion`, `alpha_diversity`, curator and curation date. The
*evidence contract* lives on the association edges instead, because
`required_properties` — the only completeness check the ontology can enforce —
works on edge properties only.

## The overlap query (D1)

```cypher
UNWIND $taxon_ids AS tid
MATCH (t:Taxon {id: tid})-[:REPORTED_BY]->(s:Signature)
WHERE s.direction = 'increased'
MATCH (s)-[:IN_CONDITION]->(d:Disease)
OPTIONAL MATCH (s)-[:AT_BODY_SITE]->(b:BodySite)
WITH s, d, b, count(DISTINCT t) AS overlap
WHERE overlap >= 2
RETURN d.title AS condition, b.title AS body_site, s.id AS signature,
       overlap, s.n_taxa AS signature_size,
       s.sequencing_type AS assay, s.variable_region AS region,
       s.host_species AS host, s.group_0_size AS n0, s.group_1_size AS n1,
       s.pmid AS pmid, s.evidence_level AS level
ORDER BY overlap DESC, signature_size ASC LIMIT 25
```

Four things this shape gets right, each worth keeping when you adapt it:

1. **`s.direction` is filtered before the overlap is counted.** A signature is
   wholly `increased` or wholly `decreased`; matching a depleted hit list
   against an enriched signature and calling it overlap is the commonest error
   here. Compare like with like, or return both and label them.
2. **`s.n_taxa` is the enrichment denominator.** An overlap of 4 against a
   1,200-member signature is noise; against a 12-member one it is a result.
   Sorting by raw overlap alone ranks the biggest signatures first, always.
   `ORDER BY overlap DESC, signature_size ASC` is the minimum correction; a
   real ORA/PADOG/CBEA statistic runs **outside** the graph on these sets.
3. **`overlap <= signature_size` always.** A larger overlap means a missing
   `DISTINCT` counted a taxon twice.
4. **`AT_BODY_SITE` is `OPTIONAL`** — 78 signatures have none, and an inner
   match silently drops them.

## Body site and host are part of the identity

An association's identity includes direction, body site and host. A gut
signature and an oral signature for the same taxon-condition pair are two
findings, not one replicated finding — never collapse them to raise a
replication count. `s.host_species` is the same rule: a mouse signature is
`in-vivo-model` evidence whatever its design.

## Is my hit just a generic dysbiosis marker? (D14)

```cypher
MATCH (t:Taxon)-[:REPORTED_BY]->(s:Signature)
WHERE t.placeholder = false
WITH t, count(s) AS n_signatures,
     sum(CASE WHEN s.direction = 'increased' THEN 1 ELSE 0 END) AS n_increased
MATCH (t)-[r:ASSOCIATED_WITH]->(d:Disease)
WITH t, n_signatures, n_increased, count(DISTINCT d.id) AS n_conditions
RETURN t.title AS taxon, t.rank AS rank, n_signatures, n_conditions,
       1.0 * n_increased / n_signatures AS frac_increased,
       n_signatures > 100 AS non_specific
ORDER BY n_signatures DESC LIMIT 20
```

The top of that list is *Bacteroides* (1,150), *Streptococcus* (1,123),
*Prevotella* (1,063), *Lachnospiraceae* (1,024), *Lactobacillus* (938),
*Oscillospiraceae* (875) — the genera reported in more than 100 signatures
each. A hit list whose "strongest" members are these has found dysbiosis, not a
disease.

**Half of this query is missing and the answer must say so.** True
disease-specificity needs healthy-cohort prevalence (a genus's healthy
prevalence correlates at r = -0.84 with how often it is reported increased in
disease), and no source here carries it. What the graph gives is
signature *breadth*, which is a proxy.

**A standing negative:** the Firmicutes:Bacteroidetes ratio must never be
returned as an obesity signal. Ten studies found no significant phylum-level
association. A pipeline that surfaces it has a bug.

## Which studies controlled for confounders? (D11)

```cypher
MATCH (s:Signature)-[:IN_CONDITION]->(d:Disease {id: $disease_id})
RETURN s.id AS signature, s.pmid AS pmid, s.study_design AS design,
       s.matched_on AS matched_on,
       s.confounders AS confounders_controlled,
       s.antibiotics_exclusion AS antibiotics_exclusion,
       s.group_0_size AS n0, s.group_1_size AS n1
ORDER BY pmid
```

This is the strongest single argument for these signatures as the spine: **no
other source in the field records confounder control at all.** Coverage is
2,304 signatures with `matched_on`, 1,958 with `confounders`, 6,485 with
`antibiotics_exclusion`, out of 14,846. For type 2 diabetes (`MONDO:0005148`)
that is 180 signatures, 58 with confounders, 42 matched.

Why it outranks its position in any list: 26 differentially abundant ASVs in
T2D became **zero** after matching on host variables, and significance vanished
entirely for depression, autism, lung disease, thyroid disease, migraine and
SIBO. An unfiltered graph serves every one of those edges.

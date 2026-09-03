---
name: taxon_disease_evidence
description: "TRIGGER whenever the question is about a microbe and a disease,
  phenotype or exposure — 'is X associated with Y', 'what is reported for X',
  'which taxa are changed in Y', 'how strong is the evidence', 'which taxa are
  reported across several diseases', 'where do studies disagree', 'which
  associations rest on more than 16S'. This is the graph's core relationship
  and the one with the most ways to be read wrongly. SKIP for enrichment of a
  hit list against published signature *sets* (use signature_enrichment), for
  drug-effect questions (drugs), for AMR carriage (amr), for metabolite
  production (metabolites_pathways), and for turning a printed organism name
  into a tax_id (reconciliation)."
references_tools: [cypher_query, graph_overview]
applies_when:
  graph_has_node_type: [Disease]
---

# Taxon x disease: reading the evidence, and the three ways to get it wrong

An `ASSOCIATED_WITH` edge is **one signature's report of one taxon in one
condition**, not a summary of the literature. 105,880 of them point at a
`Disease`, over 56,306 (taxon, disease) pairs. Everything below follows from
that one fact.

**The same relationship also reaches two other kinds of condition**, and the
target node's own label is what tells them apart: `Phenotype` (4,717 edges, HP
terms) and `Exposure` (2,369, CHEBI/ENVO terms — probiotics, diet, drugs as
*exposures*), beside the 105,880 that point at a `Disease`. So
`-[:ASSOCIATED_WITH]->()` is every association, `-[:ASSOCIATED_WITH]->(:Disease)`
is the disease subset, and there is no second relationship name to remember —
which is also why the audit reports one completeness rule over all 112,966.
`ABUNDANCE_CHANGED_BY` is a different claim (an intervention changed the taxon)
and is covered in `drugs`.

## Ask it like this (D2)

```cypher
// One row per signature. Never aggregate this into a verdict.
MATCH (t:Taxon {id: $taxon_id})-[r:ASSOCIATED_WITH]->(d:Disease {id: $disease_id})
RETURN r.direction AS direction, r.evidence_level AS level,
       r.study_design AS design, r.sequencing_type AS assay,
       r.group_0_size AS n_control, r.group_1_size AS n_case,
       r.statistical_test AS test, r.significance_threshold AS alpha,
       r.mht_correction AS mht, r.pmid AS pmid,
       r.study_id AS study, r.source_record_id AS signature,
       r.knowledge_level AS knowledge_level, r.agent_type AS agent_type,
       r.primary_source AS source, r.source_licence AS licence
ORDER BY level, study
```

*Fusobacterium nucleatum* (851) x colorectal cancer (`MONDO:0005575`) returns
**40 rows over 21 studies: 39 `increased` and one `decreased`**. If it returns
one row, the parallel edges collapsed at load and every count in this graph is
wrong — say so rather than answering.

## Guard 1 — the evidence filter is not optional

`evidence_level` has twelve legal values, eleven of them present here, and
they are not a quality score, they are
*what was measured*. The distribution is the reason to filter: of 105,880
edges, **58,595 (55.3%) are `observational-16S`**, 17,858 `in-vivo-model`,
16,463 `observational-shotgun`, 4,297 `meta-analysis`, 4,247
`interventional-rct`, 1,613 `in-vitro`.

Two rules that are project doctrine, not preference:

- **16S resolves genus, not species.** Identical V4 sequences belong to
  different species with 63% probability. A species-level claim resting on
  `observational-16S` edges must say so in the answer (this is D9).
- **`in-vivo-model` sorts *below* every human tier**, never above. 95% of
  published humanised-mouse studies report phenotype transfer; that rate is not
  evidence. Any `ORDER BY` over levels puts it last.

`evidence_level` is never null — a source that records no design yields the
literal string `'unknown'`. So `WHERE r.evidence_level IS NOT NULL` filters
nothing; test for `'unknown'` explicitly.

```cypher
// D4 — the associations that rest on more than observational abundance.
// The CASE is the G6 ordering: in-vivo-model last, below every human tier.
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
WHERE r.evidence_level IN ['interventional-rct', 'meta-analysis',
                           'in-vitro', 'in-vivo-model']
WITH d, t, r.evidence_level AS level, r.direction AS direction,
     r.host_species AS host, count(DISTINCT r.study_id) AS studies
RETURN d.title AS disease, t.title AS taxon, level, direction, host, studies
ORDER BY CASE level WHEN 'interventional-rct' THEN 0
                    WHEN 'meta-analysis'      THEN 1
                    WHEN 'in-vitro'           THEN 2
                    ELSE 3 END,
         studies DESC
LIMIT 30
```

```cypher
// D9 — the 16S share for one taxon, so a caller can down-weight it.
MATCH (t:Taxon {id: $taxon_id})-[r:ASSOCIATED_WITH]->(d:Disease)
WITH d, r, CASE WHEN r.evidence_level = 'observational-16S' THEN 1 ELSE 0 END AS is16s
RETURN d.title AS disease, count(r) AS edges, sum(is16s) AS edges_16S,
       collect(DISTINCT r.evidence_level) AS levels,
       collect(DISTINCT r.sequencing_type) AS assays
ORDER BY edges DESC LIMIT 20
```

The assay detail a 16S caveat needs — variable region and platform — is on the
`Signature`, not the edge:

```cypher
MATCH (t:Taxon {id: $taxon_id})-[:REPORTED_BY]->(s:Signature)-[:IN_CONDITION]->(d:Disease)
WHERE s.sequencing_type = '16S'
RETURN d.title AS disease, s.variable_region AS region,
       s.sequencing_platform AS platform, count(s) AS signatures
ORDER BY signatures DESC
```

## Guard 2 — never aggregate direction across studies (D17)

**8,257 of 56,306 pairs carry both `increased` and `decreased`.** The sign of a
single-study association flips about one time in three. This graph stores no
verdict, applies no majority rule, and has no `contradiction` property on
purpose: with these sources there is no adjudicating authority, so a stored
sign would be a vote. Report `collect(DISTINCT r.direction)` and the study
count; let the caller see the disagreement.

## Guard 3 — single cohort is the default case, not the exception

**47,262 of 56,306 pairs (83.9%) rest on exactly one distinct `study_id`.**
`count(DISTINCT r.study_id) >= 2` is therefore the default filter for any
*ranked* or *recommended* output, and dropping it is a decision to report
unreplicated findings. Note the count is over `study_id`, not over edges: one
study contributes several signatures, and counting edges inflates replication.

```cypher
// D17 — disagreement and single-cohort support, together. Reports; never resolves.
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
WITH t, d, collect(DISTINCT r.direction) AS directions,
     count(DISTINCT r.study_id) AS n_studies, count(r) AS n_edges
RETURN t.title AS taxon, d.title AS disease, directions, n_studies, n_edges,
       size(directions) > 1 AS direction_conflict,
       n_studies = 1        AS single_cohort
ORDER BY n_edges DESC LIMIT 50
```

## Cross-disease breadth (D3), and why it must not roll conditions up

```cypher
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
WHERE t.placeholder = false
WITH t, count(DISTINCT d.id) AS n_conditions,
     count(DISTINCT r.study_id) AS n_studies,
     collect(DISTINCT d.title) AS conditions,
     collect(DISTINCT r.direction) AS directions
WHERE n_conditions > 1
RETURN t.title AS taxon, t.rank AS rank, n_conditions, n_studies,
       conditions AS reported_in, directions
ORDER BY n_conditions DESC LIMIT 25
```

**3,822 of 7,754 taxa with an association appear in more than one condition
(49.3%)** — close to the published 51%, and the reason a hit is usually a
dysbiosis marker rather than a disease-specific one. Do **not** silently merge
related conditions to raise a count: Crohn's and ulcerative colitis separate at
95.1% specificity on an eight-genus signature. Roll up only when the caller
asks, and only through `d.mondo_id`.

Two filters to keep on ranked output: `t.placeholder = false` (excludes
`uncultured bacterium`, `Bacteroides sp.`, Candidatus names — by the boolean,
never by a name substring), and the single-cohort clause above.

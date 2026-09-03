# Claims checked in `mcp/microbiomekg.skills/amr.md`

Every heading below names a section of that skill; the claims under it
are executed against the built graph by `tests/test_skill_claims.py`,
and every number in that section must appear among their expected
values. See `tests/skill_claims.py` for the syntax and the escape
hatches.

## AMR carriage: what the edge claims, and what it does not

<!-- claim: MATCH (g:ResistanceGene) WITH count(g) AS genes
     MATCH (d:DrugClass) WITH genes, count(d) AS classes
     MATCH (m:ResistanceMechanism) WITH genes, classes, count(m) AS mechs
     MATCH (t:Taxon)-[c:CARRIES_RESISTANCE_GENE]->()
     WITH genes, classes, mechs, count(c) AS carries, count(DISTINCT t) AS taxa
     MATCH ()-[x:CONFERS_RESISTANCE_TO]->()
     WITH genes, classes, mechs, carries, taxa, count(x) AS confers
     MATCH ()-[v:VIA_MECHANISM]->()
     RETURN genes, classes, mechs, carries, confers, count(v) AS via, taxa
     == 6451, 50, 8, 6415, 13691, 6513, 539 -->

<!-- claim: MATCH (t:Taxon {id: 562})-[c:CARRIES_RESISTANCE_GENE]->(g:ResistanceGene)
     OPTIONAL MATCH (g)-[:CONFERS_RESISTANCE_TO]->(dc:DrugClass)
     OPTIONAL MATCH (g)-[:VIA_MECHANISM]->(m:ResistanceMechanism)
     RETURN 562 AS taxon, count(*) AS rows, count(DISTINCT g) AS determinants,
            count(DISTINCT dc) AS classes, count(DISTINCT m) AS mechanisms
     == 562, 1535, 646, 31, 7 -->

## The claim, stated plainly

<!-- claim: MATCH (t:Taxon)-[r:CARRIES_RESISTANCE_GENE]->()
     WITH sum(CASE WHEN t.id = 2 THEN 1 ELSE 0 END) AS bacteria_only,
          sum(CASE WHEN r.taxon_specificity = 'above-species' THEN 1 ELSE 0 END) AS above,
          sum(CASE WHEN r.taxon_specificity = 'not-an-organism' THEN 1 ELSE 0 END) AS nonorganism
     MATCH (g:ResistanceGene)-[c:CONFERS_RESISTANCE_TO]->()
     WITH bacteria_only, above, nonorganism, count(c) AS confers,
          sum(CASE WHEN c.evidence_level = 'computational-predicted' THEN 1 ELSE 0 END) AS predicted,
          count(DISTINCT CASE WHEN c.evidence_level = 'computational-predicted' THEN g END) AS meta_models
     RETURN bacteria_only, 2 AS bacteria_taxid, above, nonorganism,
            predicted, confers, meta_models
     == 132, 2, 264, 18, 104, 13691, 36 -->

<!-- claim external: 54, 58 — the balanced accuracy of genotype-to-phenotype AMR
     prediction in the literature (docs/research), measured against real MICs
     rather than against this graph. -->

<!-- claim external: 276 — CARD Prevalence's announced "276k AMR links", quoted
     to contrast a population this graph deliberately does not load. -->

## Licence rides the edge, not the graph

<!-- claim: MATCH ()-[r:CONFERS_RESISTANCE_TO]->()
     RETURN sum(CASE WHEN r.source_licence = 'CC-BY-4.0' THEN 1 ELSE 0 END) AS open,
            count(r) AS total == 42, 13691 -->

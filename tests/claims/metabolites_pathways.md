# Claims checked in `microbiomekg/mcp/microbiomekg.skills/metabolites_pathways.md`

Every heading below names a section of that skill; the claims under it are
executed against the built graph by `tests/test_skill_claims.py`, and every
number in that section must appear among their expected values. See
`tests/skill_claims.py` for the syntax and the escape hatches.

## description

<!-- claim: MATCH (m:Metabolite {id: 'CHEBI:17968'}) RETURN count(m) AS conjugate_base == 0 -->

## Coverage first, because it changes the answer

<!-- claim: MATCH (t:Taxon)-[r:PRODUCES]->(m:Metabolite)
     RETURN count(r) AS edges, count(DISTINCT t) AS organisms,
            count(DISTINCT m) AS metabolites,
            sum(CASE WHEN r.evidence_level = 'in-vitro' THEN 1 ELSE 0 END) AS in_vitro,
            sum(CASE WHEN r.evidence_level = 'computational-predicted' THEN 1 ELSE 0 END) AS predicted,
            count(DISTINCT r.primary_source) AS sources
     == 3418, 830, 226, 3383, 35, 2 -->

<!-- claim: MATCH (t:Taxon)-[r:PRODUCES]->(m:Metabolite) WHERE r.primary_source = 'njc19'
     WITH count(r) AS edges, count(DISTINCT t) AS organisms, count(DISTINCT m) AS metabolites
     MATCH (t2:Taxon)-[h:PRODUCES]->(m2:Metabolite) WHERE h.primary_source = 'hmdb'
     RETURN edges, organisms, metabolites, count(h) AS hmdb_edges,
            count(DISTINCT t2) AS hmdb_organisms, count(DISTINCT m2) AS hmdb_metabolites
     == 2840, 638, 99, 578, 272, 154 -->

<!-- claim: MATCH (t:Taxon)-[r:PRODUCES]->(m:Metabolite)
     WITH t, m, count(DISTINCT r.source_record_id) AS records
     RETURN sum(CASE WHEN records > 1 THEN 1 ELSE 0 END) AS replicated,
            max(records) AS most == 43, 3 -->

<!-- claim: MATCH ()-[r]->() WHERE r.primary_source = 'mimedb'
     RETURN count(r) AS mimedb_edges == 0 -->

## Consumption, degradation and refutation — the cross-feeding half

<!-- claim: MATCH (t:Taxon)-[r:CONSUMES]->(m:Metabolite)
     WITH count(r) AS consumes, count(DISTINCT t) AS taxa, count(DISTINCT m) AS metabolites
     MATCH (t2:Taxon)-[d:DEGRADES]->(m2:Metabolite)
     WITH consumes, taxa, metabolites, count(d) AS degrades,
          count(DISTINCT t2) AS degraders, count(DISTINCT m2) AS macromolecules
     MATCH ()-[n:NO_EXCHANGE_WITH]->()
     RETURN consumes, taxa, metabolites, degrades, degraders, macromolecules,
            count(n) AS refutations,
            sum(CASE WHEN n.source_relation = 'import-negative' THEN 1 ELSE 0 END) AS import_neg,
            sum(CASE WHEN n.source_relation = 'degrade-negative' THEN 1 ELSE 0 END) AS degrade_neg
     == 4784, 714, 205, 387, 212, 17, 894, 720, 87 -->

<!-- claim: MATCH (m:Metabolite)
     WHERE EXISTS { MATCH (p:Taxon)-[:PRODUCES]->(m) WHERE p.placeholder = false }
       AND EXISTS { MATCH (c:Taxon)-[:CONSUMES]->(m) WHERE c.placeholder = false }
     WITH count(m) AS both
     MATCH (a:Metabolite {title: 'Acetic acid'})
     OPTIONAL MATCH (p2:Taxon)-[:PRODUCES]->(a) WHERE p2.placeholder = false
     OPTIONAL MATCH (c2:Taxon)-[:CONSUMES]->(a) WHERE c2.placeholder = false
     RETURN both, count(DISTINCT p2) AS acetate_producers,
            count(DISTINCT c2) AS acetate_consumers, 0 AS floor == 96, 441, 72, 0 -->

## The forward query (D5)

<!-- claim: MATCH ()-[r]->() WHERE r.genus_level_evidence = true
     RETURN count(r) AS genus_level,
            sum(CASE WHEN type(r) = 'PRODUCES' THEN 1 ELSE 0 END) AS productions
     == 2432, 1456 -->

<!-- claim: MATCH (t:Taxon {id: 239935})
     OPTIONAL MATCH (t)-[p:PRODUCES]->(m:Metabolite)
     OPTIONAL MATCH (t)-[c:CONSUMES]->(m2:Metabolite)
     RETURN 239935 AS taxon, count(DISTINCT m) AS products,
            count(DISTINCT c) AS consumptions,
            count(DISTINCT p) + count(DISTINCT c) AS exchange_edges == 239935, 4, 3, 7 -->

<!-- claim: MATCH (t:Taxon {id: 239935})-[p:PRODUCES]->()
     WHERE p.primary_source = 'hmdb' RETURN count(p) AS hmdb_products == 0 -->

## The reverse query, and the acid/base trap that makes it return nothing

<!-- claim: MATCH (m:Metabolite {id: 'CHEBI:30772'}) WITH m
     OPTIONAL MATCH (t:Taxon)-[p:PRODUCES]->(m) WHERE t.placeholder = false
     OPTIONAL MATCH (c:Taxon)-[:CONSUMES]->(m) WHERE c.placeholder = false
     RETURN count(DISTINCT t) AS producers,
            count(DISTINCT CASE WHEN p.primary_source = 'hmdb' THEN t END) AS from_hmdb,
            count(DISTINCT CASE WHEN p.primary_source = 'njc19' THEN t END) AS from_njc19,
            count(DISTINCT c) AS consumers == 109, 6, 106, 26 -->

<!-- claim: MATCH (t:Taxon)-[p:PRODUCES]->(m:Metabolite {id: 'CHEBI:30772'})
     WHERE t.placeholder = false AND p.primary_source = 'hmdb'
     WITH collect(DISTINCT t) AS hmdb_producers
     MATCH (t2:Taxon)-[p2:PRODUCES]->(m2:Metabolite {id: 'CHEBI:30772'})
     WHERE t2.placeholder = false AND p2.primary_source = 'njc19' AND t2 IN hmdb_producers
     RETURN count(DISTINCT t2) AS shared == 3 -->

<!-- claim: MATCH (t:Taxon)-[p:PRODUCES]->(m:Metabolite {title: 'Formic acid'})
     WITH count(DISTINCT t) AS formic_producers
     MATCH (f:Metabolite) WHERE f.id IN ['CHEBI:15740', 'CHEBI:30751']
     RETURN formic_producers, count(f) AS conjugate_pair_nodes == 10, 2 -->

## Pathways: capability, not production (D13)

<!-- claim: MATCH (pw:Pathway)
     RETURN count(pw) AS pathways, count(DISTINCT pw.species) AS species == 23604, 16 -->

<!-- claim: MATCH (t:Taxon)-[:PRODUCES]->() WITH collect(DISTINCT t.title) AS producers
     MATCH (pw:Pathway) WHERE pw.species IN producers
     RETURN count(DISTINCT pw.species) AS overlap == 3 -->

<!-- claim: MATCH (t:Taxon)-[p:PRODUCES]->(m:Metabolite)-[i:IN_PATHWAY]->(pw:Pathway)
     RETURN count(*) AS rows, count(DISTINCT t) AS taxa, count(DISTINCT pw) AS pathways,
            sum(CASE WHEN t.id = 562 THEN 1 ELSE 0 END) AS ecoli == 130214, 628, 1125, 1028 -->

<!-- claim: MATCH ()-[i:IN_PATHWAY]->()
     RETURN sum(CASE WHEN i.evidence_code = 'IEA' THEN 1 ELSE 0 END) AS iea,
            sum(CASE WHEN i.evidence_code = 'TAS' THEN 1 ELSE 0 END) AS tas,
            round(1000.0 * sum(CASE WHEN i.evidence_code = 'IEA' THEN 1 ELSE 0 END)
                  / count(i)) / 10.0 AS pct == 31773, 4357, 87.9 -->

<!-- claim: MATCH ()-[r:PART_OF_PATHWAY]->() WITH count(r) AS edges
     MATCH (c:Pathway)-[p:PART_OF_PATHWAY]->(:Pathway)
     WITH edges, c, count(p) AS parents
     RETURN edges, sum(CASE WHEN parents > 1 THEN 1 ELSE 0 END) AS multi_parent
     == 23717, 388 -->

## What this layer cannot do

<!-- claim: MATCH ()-[n:NO_EXCHANGE_WITH]->() WITH count(n) AS refutations
     MATCH (m:Metabolite) RETURN refutations, count(m) AS metabolites == 894, 9056 -->

<!-- claim external: 1135 — the cohort size behind the published finding that
     gene abundance and metabolite level are almost uncorrelated. A paper's
     number, quoted as the reason for the caveat. -->

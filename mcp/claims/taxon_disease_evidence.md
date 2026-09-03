# Claims checked in `mcp/microbiomekg.skills/taxon_disease_evidence.md`

Every heading below names a section of that skill; the claims under it
are executed against the built graph by `tests/test_skill_claims.py`,
and every number in that section must appear among their expected
values. See `tests/skill_claims.py` for the syntax and the escape
hatches.

## Taxon x disease: reading the evidence, and the three ways to get it wrong

<!-- claim: MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
     WITH t, d, count(r) AS n RETURN sum(n) AS edges, count(*) AS pairs
     == 105880, 56306 -->

<!-- claim: MATCH ()-[p:ASSOCIATED_WITH_PHENOTYPE]->() WITH count(p) AS phenotype
     MATCH ()-[e:ASSOCIATED_WITH_EXPOSURE]->()
     RETURN phenotype, count(e) AS exposure == 4717, 2369 -->

## Ask it like this (D2)

<!-- claim: MATCH (t:Taxon {id: 851})-[r:ASSOCIATED_WITH]->(:Disease {id: 'MONDO:0005575'})
     RETURN 851 AS taxon, count(r) AS rows, count(DISTINCT r.study_id) AS studies,
            sum(CASE WHEN r.direction = 'increased' THEN 1 ELSE 0 END) AS increased
     == 851, 40, 21, 39 -->

## Guard 1 — the evidence filter is not optional

<!-- claim: MATCH (:Taxon)-[r:ASSOCIATED_WITH]->(:Disease)
     RETURN count(r) AS edges,
            sum(CASE WHEN r.evidence_level = 'observational-16S' THEN 1 ELSE 0 END) AS amplicon_16s,
            round(1000.0 * sum(CASE WHEN r.evidence_level = 'observational-16S' THEN 1 ELSE 0 END)
                  / count(r)) / 10.0 AS pct,
            sum(CASE WHEN r.evidence_level = 'in-vivo-model' THEN 1 ELSE 0 END) AS mouse,
            sum(CASE WHEN r.evidence_level = 'observational-shotgun' THEN 1 ELSE 0 END) AS shotgun,
            sum(CASE WHEN r.evidence_level = 'meta-analysis' THEN 1 ELSE 0 END) AS meta,
            sum(CASE WHEN r.evidence_level = 'interventional-rct' THEN 1 ELSE 0 END) AS rct,
            sum(CASE WHEN r.evidence_level = 'in-vitro' THEN 1 ELSE 0 END) AS in_vitro
     == 105880, 58595, 55.3, 17858, 16463, 4297, 4247, 1613 -->

<!-- claim: MATCH ()-[r]->() WHERE r.evidence_level IS NOT NULL
     RETURN count(DISTINCT r.evidence_level) AS in_use == 11 -->

<!-- claim external: 12 — the declared `evidence_level` vocabulary in
     microbiomekg/ontology/vocabulary.py; `text-mined` is reserved and unused. -->

<!-- claim external: 63, 95 — two published rates quoted as reasons for the
     guards: identical V4 sequences belonging to different species, and
     phenotype transfer reported in humanised-mouse studies. Neither is
     measurable in this graph. -->

## Guard 2 — never aggregate direction across studies (D17)

<!-- claim: MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
     WITH t, d, collect(DISTINCT r.direction) AS dirs
     RETURN sum(CASE WHEN size(dirs) > 1 THEN 1 ELSE 0 END) AS conflicting,
            count(*) AS pairs == 8257, 56306 -->

## Guard 3 — single cohort is the default case, not the exception

<!-- claim: MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
     WITH t, d, count(DISTINCT r.study_id) AS studies
     WITH count(*) AS pairs, sum(CASE WHEN studies = 1 THEN 1 ELSE 0 END) AS single
     RETURN single, pairs, round(1000.0 * single / pairs) / 10.0 AS pct
     == 47232, 56306, 83.9 -->

## Cross-disease breadth (D3), and why it must not roll conditions up

<!-- claim: MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
     WITH t, count(DISTINCT d.id) AS conditions
     WITH count(*) AS taxa, sum(CASE WHEN conditions > 1 THEN 1 ELSE 0 END) AS multi
     RETURN multi, taxa, round(1000.0 * multi / taxa) / 10.0 AS pct
     == 3822, 7754, 49.3 -->

<!-- claim external: 51, 95.1, 8 — the published multi-condition share this
     graph's 49.3% is compared against, and the specificity an eight-genus
     signature reaches separating Crohn's from ulcerative colitis. -->

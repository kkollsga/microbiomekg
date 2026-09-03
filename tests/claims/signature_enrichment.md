# Claims checked in `microbiomekg/mcp/microbiomekg.skills/signature_enrichment.md`

Every heading below names a section of that skill; the claims under it
are executed against the built graph by `tests/test_skill_claims.py`,
and every number in that section must appear among their expected
values. See `tests/skill_claims.py` for the syntax and the escape
hatches.

## Signature overlap: the query the model was shaped for

<!-- claim: MATCH (s:Signature) WITH count(s) AS signatures
     MATCH ()-[r:REPORTED_BY]->() RETURN signatures, count(r) AS memberships
     == 14846, 114742 -->

## The overlap query (D1)

<!-- claim: MATCH (s:Signature) WHERE NOT EXISTS { MATCH (s)-[:AT_BODY_SITE]->() }
     RETURN count(s) AS no_body_site == 78 -->

<!-- claim external: 4, 12, 1200 — an illustration of the ratio the denominator
     controls (an overlap of 4 against a 1,200-member signature versus a
     12-member one), not a row this graph returns. -->

## Is my hit just a generic dysbiosis marker? (D14)

<!-- claim: MATCH (t:Taxon)-[:REPORTED_BY]->(s:Signature) WHERE t.placeholder = false
     WITH t.title AS taxon, count(s) AS n ORDER BY n DESC LIMIT 6
     RETURN collect(n)[0] AS bacteroides, collect(n)[1] AS streptococcus,
            collect(n)[2] AS prevotella, collect(n)[3] AS lachnospiraceae,
            collect(n)[4] AS lactobacillus, collect(n)[5] AS oscillospiraceae,
            100 AS threshold == 1150, 1123, 1063, 1024, 938, 875, 100 -->

<!-- claim external: 0.84 — the published correlation between a genus's healthy
     prevalence and how often it is reported increased in disease. The healthy
     half is the source this graph does not have. -->

<!-- claim external: 10 — the count of published studies finding no
     phylum-level obesity association (docs/research). A statement about the
     literature, not about a loaded edge. -->

## Which studies controlled for confounders? (D11)

<!-- claim: MATCH (s:Signature)
     WITH count(s) AS signatures,
          sum(CASE WHEN s.matched_on <> '' THEN 1 ELSE 0 END) AS matched,
          sum(CASE WHEN s.confounders <> '' THEN 1 ELSE 0 END) AS confounders,
          sum(CASE WHEN s.antibiotics_exclusion <> '' THEN 1 ELSE 0 END) AS abx
     MATCH (t:Signature)-[:IN_CONDITION]->(:Disease {id: 'MONDO:0005148'})
     RETURN matched, confounders, abx, signatures, count(t) AS t2d,
            sum(CASE WHEN t.confounders <> '' THEN 1 ELSE 0 END) AS t2d_confounders,
            sum(CASE WHEN t.matched_on <> '' THEN 1 ELSE 0 END) AS t2d_matched
     == 2304, 1958, 6485, 14846, 180, 58, 42 -->

<!-- claim external: 26 — the published count of T2D ASVs that lost
     significance after matching on host variables. A re-analysis of cohorts,
     not a count of anything in this graph. -->

# Claims checked in `microbiomekg/mcp/microbiomekg.skills/evidence_audit.md`

Every heading below names a section of that skill; the claims under it
are executed against the built graph by `tests/test_skill_claims.py`,
and every number in that section must appear among their expected
values. See `tests/skill_claims.py` for the syntax and the escape
hatches.

## The audit: what fraction of each relationship fails its own contract

<!-- claim: CALL ontology_audit() YIELD rule, violations, total, pct
     WITH count(*) AS rules,
          sum(CASE WHEN rule ENDS WITH '.required_properties' THEN 1 ELSE 0 END) AS completeness,
          sum(CASE WHEN rule = 'ASSOCIATED_WITH.required_properties' THEN violations ELSE 0 END) AS bad,
          sum(CASE WHEN rule = 'ASSOCIATED_WITH.required_properties' THEN total ELSE 0 END) AS edges,
          sum(CASE WHEN rule = 'ASSOCIATED_WITH.required_properties' THEN pct ELSE 0.0 END) AS pct
     RETURN rules, completeness, bad, edges, pct == 111, 22, 17546, 112966, 15.5 -->

## How to read a row — three failure modes it can hide

<!-- claim: MATCH (:Taxon)-[r:ASSOCIATED_WITH]->(:Disease)
     WHERE r.evidence_level = 'unknown' RETURN count(r) AS meaningless == 800 -->

<!-- claim: CALL ontology_audit() YIELD rule, total
     RETURN sum(CASE WHEN total = 0 THEN 1 ELSE 0 END) AS zero_denominator == 0 -->

<!-- claim external: 0.00 — the illustration's own percentage, a shape a rule
     can take rather than a row this build produces. -->

## The fraction is not comparable across sources — this is the important part

<!-- claim: CALL ontology_audit() YIELD rule, violations, total
     WHERE rule = 'ABUNDANCE_CHANGED_BY.required_properties'
     WITH violations, total
     MATCH ()-[r:ASSOCIATED_WITH]->() WHERE r.primary_source = 'gutmdisorder'
     RETURN violations, total, round(1000.0 * violations / total) / 10.0 AS pct,
            count(r) AS second_source == 1380, 1380, 100, 1636 -->

<!-- claim external: 13.87, 15.20 — the same rule before and after gutMDisorder
     landed. The earlier build is history, not a query this graph can answer. -->

<!-- claim external: 14 — the length of `ASSOCIATED_WITH.required_properties`
     in ontology.json, which the audit reports against but does not return. -->

## Which fields are the gap — ask the audit, do not derive it

<!-- claim: CALL ontology_audit({by: 'property'})
     YIELD rule, property, violations, total, pct
     WHERE rule = 'ASSOCIATED_WITH.required_properties' AND property IS NOT NULL
     RETURN sum(CASE WHEN property = 'group_0_size' THEN violations ELSE 0 END) AS g0,
            sum(CASE WHEN property = 'group_0_size' THEN pct ELSE 0.0 END) AS g0_pct,
            sum(CASE WHEN property = 'group_1_size' THEN violations ELSE 0 END) AS g1,
            sum(CASE WHEN property = 'group_1_size' THEN pct ELSE 0.0 END) AS g1_pct,
            sum(CASE WHEN property = 'study_design' THEN violations ELSE 0 END) AS design,
            sum(CASE WHEN property = 'statistical_test' THEN violations ELSE 0 END) AS test,
            sum(CASE WHEN property = 'sequencing_type' THEN violations ELSE 0 END) AS assay,
            sum(CASE WHEN property = 'pmid' THEN violations ELSE 0 END) AS pmid,
            sum(CASE WHEN property = 'direction' THEN violations ELSE 0 END) AS direction,
            max(total) AS edges
     == 14837, 13.1, 14732, 13.0, 2436, 2305, 1910, 1061, 894, 112966 -->

<!-- claim: CALL ontology_audit({by: 'property'})
     YIELD rule, property, violations
     WHERE rule = 'ASSOCIATED_WITH.required_properties' AND property IS NOT NULL
     RETURN sum(CASE WHEN violations = 0 THEN 1 ELSE 0 END) AS complete == 6 -->

<!-- claim: CALL ontology_audit() YIELD rule, violations
     RETURN sum(CASE WHEN rule = 'ASSOCIATED_WITH.required_properties'
                     THEN violations ELSE 0 END) AS aggregate == 17546 -->

<!-- claim: CALL ontology_audit({by: 'property'})
     YIELD rule, property, violations, total
     WHERE rule = 'CONFERS_RESISTANCE_TO.required_properties' AND property IS NOT NULL
     RETURN sum(CASE WHEN property = 'pmid' THEN violations ELSE 0 END) AS no_pmid,
            max(total) AS edges,
            round(1000.0 * sum(CASE WHEN property = 'pmid' THEN violations ELSE 0 END)
                  / max(total)) / 10.0 AS pct
     == 8052, 13691, 58.8 -->

<!-- claim: MATCH (g:ResistanceGene)
     RETURN count(g) AS models,
            sum(CASE WHEN g.publications IS NULL THEN 0 ELSE 1 END) AS cited
     == 6451, 2734 -->

## Distinct values, because a near-miss spelling is a silent filter miss

<!-- claim: MATCH ()-[r]->() WHERE r.evidence_level IS NOT NULL
     RETURN count(DISTINCT r.evidence_level) AS in_use == 11 -->

<!-- claim external: 12 — the declared vocabulary in
     microbiomekg/ontology/vocabulary.py, of which `text-mined` is reserved for
     a source class this graph does not yet load. -->

## Nothing was dropped silently, so "absent" is a question with an answer

<!-- claim: MATCH (u:UnresolvedTaxon) RETURN count(u) AS tombstones == 224 -->

# Claims checked in `mcp/microbiomekg.skills/evidence_audit.md`

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

## Distinct values, because a near-miss spelling is a silent filter miss

<!-- claim: MATCH ()-[r]->() WHERE r.evidence_level IS NOT NULL
     RETURN count(DISTINCT r.evidence_level) AS in_use == 11 -->

<!-- claim external: 12 — the declared vocabulary in
     microbiomekg/ontology/vocabulary.py, of which `text-mined` is reserved for
     a source class this graph does not yet load. -->

## Nothing was dropped silently, so "absent" is a question with an answer

<!-- claim: MATCH (u:UnresolvedTaxon) RETURN count(u) AS tombstones == 224 -->

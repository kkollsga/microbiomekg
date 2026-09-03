---
name: evidence_audit
description: "TRIGGER before trusting or reporting any relationship in bulk, and
  whenever the user asks how complete / trustworthy / well-evidenced the graph
  is, how many edges lack evidence, which sources are weakest, or wants a
  coverage statement to put in a methods section. Run `ontology_audit()` FIRST
  when a question spans a whole relationship rather than one entity. SKIP for
  a single lookup, where the per-edge provenance fields already answer it."
references_tools: [cypher_query, graph_overview]
applies_when:
  graph_has_node_type: [Disease]
---

# The audit: what fraction of each relationship fails its own contract

This graph's premise is that an association edge cannot exist without saying
how it was demonstrated. `ontology_audit()` is how that premise is checked
rather than claimed, and it is the query that keeps every other answer honest.

```cypher
CALL ontology_audit() YIELD rule, severity, violations, exempted, total, pct
RETURN rule, severity, violations, total, pct ORDER BY pct DESC
```

111 rules, 22 of them the `required_properties` completeness check. The
headline row is
**`ASSOCIATED_WITH.required_properties` at 17,546 of 112,966 edges = 15.5%,
`severity = warn`** — one rule over every association, whatever kind of
condition it points at. Narrow it by the target's own label
(`-[r:ASSOCIATED_WITH]->(:Disease)`) when a question is about diseases only;
there is no separate relationship name to remember.

## How to read a row — three failure modes it can hide

- **A zero denominator means the rule is auditing property names nothing
  writes.** 0 of 0 is not a clean bill of health; it is a rule pointed at the
  wrong spelling. Check `total` before quoting `pct`.
- **A 0.00% fraction on a source known to have gaps means a literal `"NA"`
  string reached the graph as a value.** The property is present, so the check
  passes, and it means nothing.
- **`evidence_level` can never violate a required-property rule**, because a
  source with no derivable level yields the string `'unknown'` rather than
  null. 800 edges carry a level that means nothing and no completeness check
  can see them. The audit percentage is a **floor** on the gap, not the gap.

## The fraction is not comparable across sources — this is the important part

A single percentage over sources with different column sets is not a quality
ranking. Two rows make it concrete:

- **`ABUNDANCE_CHANGED_BY.required_properties` reads 1,380 of 1,380 = 100%.**
  Its whole population is one source that records no `study_design` and whose
  association rows carry no link to a sample arm, so no per-association group
  sizes exist either. Three columns the source never had, not 1,380 defects.
- **`ASSOCIATED_WITH` rose from 13.87% to 15.20% when a second source landed**,
  because all 1,636 of that source's edges are violations for the same reason.
  **The rise is the audit working**, not a regression.

So a "shared-14 fraction" — the share of edges carrying the full fourteen-field
evidence contract — compares a source that *has* those columns against one that
never did.

Comparing sources needs the per-field census, per source, and that
census cannot be built from the audit: the `edge_property_violation` procedure
names only the **first** missing property, so a breakdown built from it
under-counts every field but one. Ask for the fields directly:

```cypher
MATCH (:Taxon)-[r:ASSOCIATED_WITH]->(:Disease)
RETURN r.primary_source AS source, count(r) AS edges,
       sum(CASE WHEN r.direction        IS NULL THEN 1 ELSE 0 END) AS no_direction,
       sum(CASE WHEN r.pmid             IS NULL THEN 1 ELSE 0 END) AS no_pmid,
       sum(CASE WHEN r.group_0_size     IS NULL THEN 1 ELSE 0 END) AS no_group0,
       sum(CASE WHEN r.group_1_size     IS NULL THEN 1 ELSE 0 END) AS no_group1,
       sum(CASE WHEN r.statistical_test IS NULL THEN 1 ELSE 0 END) AS no_test,
       sum(CASE WHEN r.evidence_level  = 'unknown'      THEN 1 ELSE 0 END) AS level_unknown,
       sum(CASE WHEN r.knowledge_level = 'not_provided' THEN 1 ELSE 0 END) AS kl_not_provided
ORDER BY edges DESC
```

Each association relationship declares its own required set, and they are not
the same set. Read the declaration before reading the percentage:

```cypher
CALL ontology_audit() YIELD rule, severity, violations, total, pct
WHERE rule ENDS WITH '.required_properties'
RETURN rule, severity, violations, total, pct
ORDER BY total DESC
```

## Distinct values, because a near-miss spelling is a silent filter miss

`evidence_level` has twelve legal values and this build carries eleven of
them, hyphenated with `16S` capitalised. A
row spelled `observational_16s` would be filtered out by every query in every
other skill and reported by none of them. Count the values, do not assume them:

```cypher
MATCH ()-[r:ASSOCIATED_WITH]->()
RETURN r.evidence_level AS level, r.knowledge_level AS knowledge_level,
       r.agent_type AS agent_type, count(r) AS edges
ORDER BY edges DESC
```

## Nothing was dropped silently, so "absent" is a question with an answer

Every input row that reached no edge is a ledger row with its raw string and
the reason — unresolved taxa, unresolved conditions, unresolved associations,
unresolved production. `UnresolvedTaxon` nodes are the in-graph half of that:
tombstones for names no tax_id resolved and for deleted ids, still wired to the
signatures that cited them.

```cypher
MATCH (u:UnresolvedTaxon)
RETURN u.status AS status, u.source AS source, count(u) AS names
ORDER BY names DESC
```

Before reporting that the graph has no data for an organism, check there — an
absent `Taxon` and an `UnresolvedTaxon` tombstone are very different answers.

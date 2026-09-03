# Claims checked in `mcp/microbiomekg_mcp.yaml`

The two headings below name the manifest's prose keys — the handshake
`instructions` and the `overview_prefix` that rides every bare
`graph_overview()`. Both reach an agent verbatim, so both are gated by
`tests/test_skill_claims.py`; everything else in the manifest is configuration.

## instructions

<!-- claim: MATCH (n) WITH count(n) AS nodes
     MATCH ()-[r]->() RETURN nodes, count(r) AS edges == 934206, 1324684 -->

<!-- claim: MATCH ()-[r]->() WITH collect(DISTINCT r.primary_source) AS edge_sources
     MATCH (n) WHERE n.source IS NOT NULL
     WITH edge_sources + collect(DISTINCT n.source) AS every UNWIND every AS source
     RETURN count(DISTINCT source) AS sources == 11 -->

<!-- claim: MATCH (:Taxon)-[r:ASSOCIATED_WITH]->(:Disease)
     RETURN round(1000.0 * sum(CASE WHEN r.evidence_level = 'observational-16S'
                                    THEN 1 ELSE 0 END) / count(r)) / 10.0 AS pct_16s == 55.3 -->

<!-- claim: MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
     WITH t, d, collect(DISTINCT r.direction) AS dirs,
          count(DISTINCT r.study_id) AS studies
     WITH count(*) AS pairs,
          sum(CASE WHEN size(dirs) > 1 THEN 1 ELSE 0 END) AS conflicting,
          sum(CASE WHEN studies = 1 THEN 1 ELSE 0 END) AS single
     RETURN conflicting, round(1000.0 * single / pairs) / 10.0 AS single_pct
     == 8257, 83.9 -->

<!-- claim: CALL ontology_audit() YIELD rule, pct
     RETURN sum(CASE WHEN rule = 'ASSOCIATED_WITH.required_properties' THEN pct ELSE 0.0 END) AS assoc,
            sum(CASE WHEN rule = 'ABUNDANCE_CHANGED_BY.required_properties' THEN pct ELSE 0.0 END) AS abundance
     == 15.5, 100 -->

<!-- claim: MATCH ()-[r]->() WHERE r.primary_source = 'mimedb'
     RETURN count(r) AS mimedb_edges == 0 -->

## overview_prefix

<!-- claim: MATCH ()-[r]->() WHERE r.primary_source IS NOT NULL
     RETURN count(DISTINCT r.primary_source) AS edge_writing_sources == 10 -->

<!-- claim: MATCH ()-[r]->() WITH collect(DISTINCT r.primary_source) AS edge_sources
     MATCH (n) WHERE n.source IS NOT NULL
     WITH edge_sources + collect(DISTINCT n.source) AS every UNWIND every AS source
     RETURN count(DISTINCT source) AS sources == 11 -->

<!-- claim: MATCH ()-[r]->() WHERE r.evidence_level IS NOT NULL
     RETURN count(DISTINCT r.evidence_level) AS in_use == 11 -->

<!-- claim external: 12 — the declared `evidence_level` vocabulary in
     microbiomekg/ontology/vocabulary.py; `text-mined` is reserved for a source
     class this graph does not load, so eleven of the twelve are in use. -->

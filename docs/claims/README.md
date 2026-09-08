# Claims checked in `README.md`

The README is human-first and every number in it is a measurement, so it is
gated the way the agent-facing prose is: one heading per section, every
number covered, the bench figures marked `external` with the capture they
come from.

## MicrobiomeKG

<!-- claim: MATCH ()-[r]->()
     WHERE type(r) IN ['DOES_NOT_INHIBIT_GROWTH_OF', 'DOES_NOT_METABOLISE', 'NO_EXCHANGE_WITH',
                       'DOES_NOT_METABOLISE_SUBSTANCE', 'ABUNDANCE_UNCHANGED_BY_SUBSTANCE']
     RETURN count(r) AS negatives,
            sum(CASE WHEN type(r) = 'DOES_NOT_INHIBIT_GROWTH_OF' THEN 1 ELSE 0 END) AS a,
            sum(CASE WHEN type(r) = 'DOES_NOT_METABOLISE' THEN 1 ELSE 0 END) AS b,
            sum(CASE WHEN type(r) = 'NO_EXCHANGE_WITH' THEN 1 ELSE 0 END) AS c,
            sum(CASE WHEN type(r) IN ['DOES_NOT_METABOLISE_SUBSTANCE', 'ABUNDANCE_UNCHANGED_BY_SUBSTANCE'] THEN 1 ELSE 0 END) AS d
     == 61127, 42233, 17479, 894, 521 -->

<!-- claim: MATCH ()-[r]->() WITH collect(DISTINCT r.primary_source) AS edge_sources
     MATCH (n) WHERE n.source IS NOT NULL
     WITH edge_sources + collect(DISTINCT n.source) AS every UNWIND every AS source
     RETURN count(DISTINCT source) AS sources == 11 -->

<!-- claim: MATCH (n) WITH count(n) AS nodes
     MATCH ()-[r]->() RETURN nodes, count(r) AS edges == 934206, 1324684 -->

<!-- claim: MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
     WITH t, d, count(r) AS reports
     RETURN sum(reports) AS edges, count(*) AS pairs == 105880, 56306 -->

<!-- claim: MATCH ()-[r]->() WHERE r.primary_source = 'kegg' RETURN count(r) AS kegg_edges == 0 -->

<!-- claim external: 40 — "forty reports on one pair" is the D2 fixture, claimed under Python below -->

## Python

<!-- claim: MATCH (t:Taxon {id: 851})-[r:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0005575'})
     RETURN count(r) AS rows, count(DISTINCT r.study_id) AS studies,
            sum(CASE WHEN r.direction = 'decreased' THEN 1 ELSE 0 END) AS decreased
     == 40, 21, 1 -->

<!-- claim external: 851, 20 — the NCBI tax id in the query, and "twenty documented queries" is Part D's count (docs/usecases-and-pitfalls.md), not a graph quantity -->

## Cypher

<!-- claim external: 17, 8, 6, 50 — D-numbers and a LIMIT in the query text, not quantities the graph carries -->

## Adding a source

<!-- claim external: 4 — the four-file source shape is a repo convention (CLAUDE.md), not a graph quantity -->

## Building and testing

<!-- claim external: 82.6, 46.7, 212.7, 1.03, 2.41, 1.2, 3.7, 2 — the 2026-09-03 bench capture (bench/results/2026-09-03-ten-sources.md §1, §3, §4); a cost measured by the harness, not a graph quantity; "two flags" is a count of CLI flags -->

## Licence

<!-- claim: MATCH ()-[r]->() WHERE r.source_licence ENDS WITH '-unstated'
     WITH count(r) AS unstated
     MATCH ()-[s]->() WHERE s.source_licence = 'CC0-1.0'
     RETURN unstated, count(s) AS cc0 == 80118, 68752 -->

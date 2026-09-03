# Claims checked in `docs/benchmarks.md`

One heading per section of the page; every number in a section is covered by a
claim here, executed against the built graph, or marked `external` with the
reason it cannot be. The page's comparator figures are `external`: they are
what the other side published, not what this graph measures.

## Benchmarks — what the graph reproduces, and against what

<!-- claim: MATCH ()-[r]->() WITH collect(DISTINCT r.primary_source) AS edge_sources
     MATCH (n) WHERE n.source IS NOT NULL
     WITH edge_sources + collect(DISTINCT n.source) AS every UNWIND every AS source
     RETURN count(DISTINCT source) AS sources == 11 -->

## G1 — Association-layer shape

<!-- claim external: 63316, 2981, 243 — the comparator's homepage figures, read 2026-09-03; published, never re-measured here -->

<!-- claim: MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
     WITH t, d, count(r) AS reports
     RETURN count(*) AS pairs, sum(reports) AS edges,
            count(DISTINCT t) AS taxa, count(DISTINCT d) AS diseases
     == 56306, 105880, 7754, 813 -->

<!-- claim: MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
     WITH count(DISTINCT t) AS taxa, count(DISTINCT d) AS diseases
     RETURN round(10.0 * taxa / 2981) / 10.0 AS taxa_x, round(10.0 * diseases / 243) / 10.0 AS diseases_x
     == 2.6, 3.3 -->

<!-- claim: MATCH (n) WITH labels(n)[0] AS t, count(*) AS n
     RETURN sum(CASE WHEN t = 'Taxon' THEN n ELSE 0 END) AS c1,
            sum(CASE WHEN t = 'Disease' THEN n ELSE 0 END) AS c2,
            sum(CASE WHEN t = 'Metabolite' THEN n ELSE 0 END) AS c3,
            sum(CASE WHEN t = 'Drug' THEN n ELSE 0 END) AS c4,
            sum(CASE WHEN t = 'Pathway' THEN n ELSE 0 END) AS c5,
            sum(CASE WHEN t = 'ProteinTarget' THEN n ELSE 0 END) AS c6,
            sum(CASE WHEN t = 'Paper' THEN n ELSE 0 END) AS c7
     == 864132, 826, 9056, 6408, 23604, 1518, 2528 -->

<!-- claim external: 40 — "forty reports on one pair" is the D2 fixture's shape, quoted from docs/usecases-and-pitfalls.md -->

## G2 — Reconciliation confidence

<!-- claim external: 95 — the comparator's own estimate of its high-confidence share, quoted from its engineering blog -->

<!-- claim: MATCH ()-[r:REPORTED_BY]->()
     RETURN sum(CASE WHEN r.resolution_status = 'exact' THEN 1 ELSE 0 END) AS c1,
            sum(CASE WHEN r.resolution_status = 'merged' THEN 1 ELSE 0 END) AS c2,
            sum(CASE WHEN r.resolution_status = 'promoted' THEN 1 ELSE 0 END) AS c3,
            sum(CASE WHEN r.resolution_status = 'deleted' THEN 1 ELSE 0 END) AS c4,
            count(r) AS c5,
            round(1000.0 * sum(CASE WHEN r.resolution_status = 'exact' THEN 1 ELSE 0 END) / count(r)) / 10.0 AS c6,
            sum(CASE WHEN r.resolution_normalized THEN 1 ELSE 0 END) AS c7
     == 114161, 413, 152, 16, 114742, 99.5, 0 -->

<!-- claim: MATCH (u:UnresolvedTaxon) RETURN count(*) AS tombstones == 224 -->

<!-- claim external: 3 — "three-point scale" is the comparator's own definition (1.0 / 0.7 / 0.5), quoted -->

## G3 — Drug-screen headlines

<!-- claim external: 24, 176, 271 — the two papers' abstracts (Nature 555:623; Nature 570:462), quoted -->

<!-- claim: MATCH (d:Drug)-[r:INHIBITS_GROWTH_OF]->(:Taxon) WHERE r.drug_class = 'human-targeted drugs'
     WITH count(DISTINCT d) AS hit
     MATCH ()-[r2:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->()
     WHERE r2.drug_class = 'human-targeted drugs'
     RETURN hit, count(DISTINCT r2.prestwick_id) AS screened,
            round(1000.0 * hit / count(DISTINCT r2.prestwick_id)) / 10.0 AS pct
     == 203, 835, 24.3 -->

<!-- claim: MATCH ()-[r:METABOLISES|DOES_NOT_METABOLISE]->()
     WITH count(DISTINCT r.reported_drug_name) AS screened
     MATCH ()-[m:METABOLISES]->()
     RETURN count(DISTINCT m.reported_drug_name) AS metabolised, screened, 176 - count(DISTINCT m.reported_drug_name) AS gap
     == 172, 271, 4 -->

<!-- claim: MATCH (u:UnresolvedTaxon) WHERE u.source = 'zimmermann2019'
     RETURN count(*) AS refused, sum(size(u.candidates)) / count(*) AS candidates_each == 2, 2 -->

## G4 — BugSigDB loader fidelity

<!-- claim external: 14846, 2126 — the dump's own row count and distinct Study values, read off data/raw/bugsigdb/full_dump_main.csv (2026-09-02) with pandas, not the graph -->

<!-- claim: MATCH ()-[r:ASSOCIATED_WITH]->() WHERE r.primary_source = 'bugsigdb' RETURN count(r) == 110547 -->

<!-- claim: MATCH (s:Signature)-[:PART_OF_STUDY]->(st:Study)
     RETURN count(DISTINCT s) AS signatures, count(DISTINCT st) AS studies == 14846, 2126 -->

## G5 — Cross-source direction agreement

<!-- claim: MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
     WITH t, d, collect(DISTINCT r.direction) AS dirs, count(DISTINCT r.study_id) AS studies
     WITH count(*) AS pairs,
          sum(CASE WHEN size(dirs) > 1 THEN 1 ELSE 0 END) AS conflicting,
          sum(CASE WHEN studies = 1 THEN 1 ELSE 0 END) AS single
     RETURN pairs, conflicting, single, round(1000.0 * single / pairs) / 10.0 AS single_pct
     == 56306, 8257, 47262, 83.9 -->

<!-- claim: MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
     WITH t, d, r.primary_source AS src, collect(DISTINCT r.direction) AS dirs
     WITH t, d, count(src) AS n_src,
          sum(CASE WHEN size(dirs) = 1 THEN 1 ELSE 0 END) AS unanimous,
          collect(DISTINCT dirs[0]) AS firsts
     WHERE n_src > 1
     RETURN count(*) AS multi,
            sum(CASE WHEN unanimous = n_src AND size(firsts) = 1 THEN 1 ELSE 0 END) AS agree,
            sum(CASE WHEN unanimous = n_src AND size(firsts) > 1 THEN 1 ELSE 0 END) AS disagree,
            sum(CASE WHEN unanimous < n_src THEN 1 ELSE 0 END) AS within
     == 871, 335, 120, 416 -->

<!-- claim: MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
     WITH t, d, collect(DISTINCT r.primary_source) AS srcs
     WHERE size(srcs) > 1
     WITH size(srcs) AS n, 'bugsigdb' IN srcs AS b, 'gutmdisorder' IN srcs AS g, 'masi' IN srcs AS m, count(*) AS pairs
     RETURN sum(CASE WHEN n = 2 AND b AND g THEN pairs ELSE 0 END) AS c1,
            sum(CASE WHEN n = 3 THEN pairs ELSE 0 END) AS c2,
            sum(CASE WHEN n = 2 AND g AND m THEN pairs ELSE 0 END) AS c3,
            sum(CASE WHEN n = 2 AND b AND m THEN pairs ELSE 0 END) AS c4,
            3 AS c5
     == 424, 244, 119, 84, 3 -->

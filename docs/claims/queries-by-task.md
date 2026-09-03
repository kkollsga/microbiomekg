# Claims checked in `docs/queries-by-task.md`

## Queries by task — one statement per endpoint group

## Lookup and autocomplete

<!-- claim: MATCH (n:Taxon) WHERE text_bm25(n, 'scientific_name', 'Bacteroides') > 0
     WITH count(*) AS taxa
     MATCH (s:Signature) WHERE text_bm25(s, 'description', 'Bacteroides') > 0
     WITH taxa, count(*) AS signatures
     MATCH (p:Paper) WHERE text_bm25(p, 'title', 'Bacteroides') > 0
     WITH taxa, signatures, count(*) AS papers
     OPTIONAL MATCH (d:Disease) WHERE text_bm25(d, 'label', 'Bacteroides') > 0
     RETURN taxa, signatures, papers, count(d) AS diseases == 1036, 32, 7, 0 -->

<!-- claim: MATCH (t:Taxon) WHERE t.scientific_name STARTS WITH 'Bacteroides fr'
     RETURN count(*) AS taxa, sum(CASE WHEN t.rank = 'species' THEN 1 ELSE 0 END) AS species == 99, 1 -->

<!-- claim: MATCH (t:Taxon) WHERE text_bm25(t, 'scientific_name', 'Bacteroid') > 0 RETURN count(*) AS n == 0 -->

<!-- claim external: 8, 10, 5, 12 — a wall-clock cost measured once by hand (about 8 ms), two LIMITs in the query text, and D12's number -->

<!-- claim external: 5, 2 — five is the count of BM25 indexes the build declares (TEXT_INDEXES in microbiomekg/pipeline.py), two is prose; neither is a graph quantity -->

## An entity's neighbourhood

<!-- claim: MATCH (t:Taxon {id: 817})-[r]-(x)
     WITH type(r) AS rel, labels(x)[0] AS neighbour, count(*) AS n
     RETURN count(*) AS rows, max(n) AS largest == 16, 2117 -->

<!-- claim external: 817 — the NCBI tax id in the query text -->

## Comparing two entities

<!-- claim: MATCH (a:Taxon {id: 817})-[]->(x)<-[]-(b:Taxon {id: 853})
     WITH labels(x)[0] AS shared, count(DISTINCT x) AS n
     RETURN sum(CASE WHEN shared = 'Disease' THEN n ELSE 0 END) AS diseases,
            sum(CASE WHEN shared = 'Signature' THEN n ELSE 0 END) AS signatures,
            sum(CASE WHEN shared = 'Metabolite' THEN n ELSE 0 END) AS metabolites == 47, 37, 11 -->

<!-- claim: MATCH (t:Taxon)-[:ASSOCIATED_WITH]->(:Disease {id: 'MONDO:0005011'})
     MATCH (t)-[:ASSOCIATED_WITH]->(:Disease {id: 'MONDO:0005101'})
     RETURN count(DISTINCT t) AS shared_taxa == 195 -->

<!-- claim external: 817, 853, 17, 2 — the two NCBI tax ids in the query text, D17's number, and "two taxa" / "two diseases" as prose -->

## A path between two entities

<!-- claim: MATCH p = shortestPath((a:Taxon {id: 817})-[*..4]-(m:Metabolite {title: 'Butyric acid'}))
     RETURN length(p) AS hops LIMIT 1 == 3 -->

<!-- claim external: 817, 4, 16 — the tax id and the hop bound in the query text, and D16's number -->

## Producers of a named metabolite class

<!-- claim: MATCH (t:Taxon)-[:PRODUCES]->(m:Metabolite)
     WHERE m.title IN ['Butyric acid', 'Acetic acid', 'Propionic acid'] AND t.placeholder = false
     WITH m.title AS scfa, count(DISTINCT t) AS producers
     RETURN sum(CASE WHEN scfa = 'Acetic acid' THEN producers ELSE 0 END) AS acetate,
            sum(CASE WHEN scfa = 'Butyric acid' THEN producers ELSE 0 END) AS butyrate,
            sum(CASE WHEN scfa = 'Propionic acid' THEN producers ELSE 0 END) AS propionate == 441, 109, 102 -->

<!-- claim external: 6, 5 — the D6 and D5 query numbers in docs/usecases-and-pitfalls.md, labels rather than quantities -->

## Candidates: biomarkers and probiotics

<!-- claim external: 1, 10 — the D1 and D10 query numbers in docs/usecases-and-pitfalls.md, labels rather than quantities -->

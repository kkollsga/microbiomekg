# Claims checked in `microbiomekg/mcp/microbiomekg.skills/reconciliation.md`

Every heading below names a section of that skill; the claims under it are
executed against the built graph by `tests/test_skill_claims.py`, and every
number in that section must appear among their expected values. Claims marked
`claim vectors:` need a `--with-vectors` build and are skipped, with a reason,
on a default one.

## description

<!-- claim: MATCH (t:Taxon) WHERE t.scientific_name = 'Clostridium difficile'
     RETURN count(t) AS exact_hits_for_the_most_cited_renamed_organism == 0 -->

## Resolving a printed organism name to a tax_id

<!-- claim: MATCH (t:Taxon)
     WHERE t.id IN [1496, 1598, 33038, 1747, 1590, 39491, 1386, 583, 210425,
                    539, 827, 77133, 29523]
     RETURN count(t) AS ids_that_resolve,
            count(DISTINCT CASE WHEN t.title = 'Clostridioides difficile' THEN t END) * 1496 AS cdiff,
            count(DISTINCT CASE WHEN t.title = 'Limosilactobacillus reuteri' THEN t END) * 1598 AS reuteri,
            count(DISTINCT CASE WHEN t.title = 'Mediterraneibacter gnavus' THEN t END) * 33038 AS gnavus,
            count(DISTINCT CASE WHEN t.title = 'Cutibacterium acnes' THEN t END) * 1747 AS acnes,
            count(DISTINCT CASE WHEN t.title = 'Lactiplantibacillus plantarum' THEN t END) * 1590 AS plantarum,
            count(DISTINCT CASE WHEN t.title = 'Agathobacter rectalis' THEN t END) * 39491 AS rectalis
     == 13, 1496, 1598, 33038, 1747, 1590, 39491 -->

<!-- claim: MATCH (t:Taxon) WHERE t.title = 'Bacillus'
     RETURN count(t) AS kingdoms, min(t.id) AS bacterium, max(t.id) AS stick_insect
     == 2, 1386, 55087 -->

<!-- claim: MATCH (t:Taxon) WHERE t.title = 'Proteus'
     RETURN min(t.id) AS bacterium, max(t.id) AS salamander == 583, 210425 -->

<!-- claim: MATCH (t:Taxon) WHERE t.id IN [539, 827]
     RETURN min(t.id) AS eikenella, max(t.id) AS campylobacter == 539, 827 -->

<!-- claim: MATCH (t:Taxon) WHERE t.id IN [77133, 29523] AND t.placeholder = true
     RETURN min(t.id) AS uncultured, max(t.id) AS bacteroides_sp == 29523, 77133 -->

## Stage 1 — lexical first. This is a contract, not a preference

<!-- claim: MATCH (t:Taxon) WHERE t.id IN [562, 83333]
     RETURN min(t.id) AS species, max(t.id) AS strain == 562, 83333 -->

<!-- claim: MATCH (t:Taxon) WHERE t.id IN [33038, 1747, 47715]
     RETURN count(t) AS resolved, min(t.id) AS gnavus, max(t.id) AS rhamnosus
     == 3, 1747, 47715 -->

<!-- claim: MATCH (t:Taxon) WHERE t.id = 33038 RETURN t.id AS gnavus == 33038 -->

## Stage 2 — the vector lane, for a name stage 1 could not match

<!-- claim vectors: MATCH (t:Taxon) WHERE t.rank = 'species' AND t.placeholder = false
     WITH t, score_fuse(text_score(t, 'scientific_name', 'Clostridium dificile'),
                        text_score(t, 'scientific_name', 'dificile')) AS score
     RETURN t.id AS resolved ORDER BY score DESC LIMIT 1 == 1496 -->

<!-- claim vectors: MATCH (t:Taxon) WHERE t.rank = 'species' AND t.placeholder = false
     WITH t, score_fuse(text_score(t, 'scientific_name', 'Akkermansia muciniphilia'),
                        text_score(t, 'scientific_name', 'muciniphilia')) AS score
     RETURN t.id AS resolved ORDER BY score DESC LIMIT 1 == 239935 -->

<!-- claim vectors: MATCH (t:Taxon) WHERE t.rank = 'species' AND t.placeholder = false
     WITH t, score_fuse(text_score(t, 'scientific_name', 'Citrobacter frundii'),
                        text_score(t, 'scientific_name', 'frundii')) AS score
     RETURN t.id AS resolved ORDER BY score DESC LIMIT 1 == 546 -->

<!-- claim vectors: MATCH (t:Taxon) WHERE t.rank = 'species' AND t.placeholder = false
     WITH t, score_fuse(text_score(t, 'scientific_name', 'Lactobacillus plantari'),
                        text_score(t, 'scientific_name', 'plantari')) AS score
     RETURN t.id AS resolved ORDER BY score DESC LIMIT 1 == 1590 -->

<!-- claim vectors: MATCH (t:Taxon) WHERE t.rank = 'genus' AND t.placeholder = false
     WITH t, score_fuse(text_score(t, 'scientific_name', 'Fecalibacterium'),
                        text_score(t, 'scientific_name', 'Fecalibacterium')) AS score
     RETURN t.id AS resolved ORDER BY score DESC LIMIT 1 == 216851 -->

## Both lanes in one score, and the trap in doing it

<!-- claim: MATCH (t:Taxon) RETURN count(t) AS taxa == 864132 -->

<!-- claim external: 1 — the upper bound of cosine similarity, which is why an
     unbounded BM25 lane decides a naively weighted blend. Arithmetic, not a
     measurement. -->

<!-- claim external: 4, 8, 7 — the fixture sweep behind the weights: equal
     weights resolve 4 of 8 test names wrongly and the tuned blend 7 of 8. A
     measurement of eight probe queries, not a count of anything stored. -->

## Read the audit trail before trusting the resolution

<!-- claim: MATCH ()-[r:REPORTED_BY]->()
     RETURN sum(CASE WHEN r.resolution_status = 'exact' THEN 1 ELSE 0 END) AS exact,
            sum(CASE WHEN r.resolution_status = 'merged' THEN 1 ELSE 0 END) AS merged,
            sum(CASE WHEN r.resolution_status = 'promoted' THEN 1 ELSE 0 END) AS promoted,
            sum(CASE WHEN r.resolution_status = 'deleted' THEN 1 ELSE 0 END) AS deleted,
            sum(CASE WHEN r.resolution_normalized = true THEN 1 ELSE 0 END) AS normalized
     == 114161, 413, 152, 16, 0 -->

## When a name resolves to nothing, it is a tombstone, not a gap

<!-- claim: MATCH (u:UnresolvedTaxon)-[r]-(s:Signature) WHERE u.status = 'deleted'
     RETURN count(DISTINCT s) AS signatures_kept == 16 -->

## The limit this graph cannot fix

<!-- claim: MATCH (t:Taxon {id: 47715}) RETURN t.id AS lgg == 47715 -->

# Queries by task — one statement per endpoint group

The read surface is Cypher, over what kglite already ships: the Python API,
Bolt for driver tooling, and the MCP server for agents. An endpoint catalogue
is what one builds when the graph sits behind a service the user cannot be
handed; each endpoint is a frozen query. Here the query language is the API,
so this page documents **one statement per task** a catalogue would freeze —
and, for the two things Cypher does not do by itself, a recipe. Every block
runs against the built graph in the test suite, and every number is executed
by the claim gate (`docs/claims/queries-by-task.md`). Tax ids are NCBI's;
disease ids are MONDO CURIEs.

The evidence questions — what is reported for a pair, replication, dissent,
the measured negatives — are Part D of
[`docs/usecases-and-pitfalls.md`](usecases-and-pitfalls.md), the user
contract, and are not restated here.

## Lookup and autocomplete

BM25 indexes cover `Taxon.scientific_name`, `Taxon.synonyms_text`,
`Disease.label`, `Signature.description` and `Paper.title`. A search box needs
two things Cypher does not hand it: a count per type, and prefix completion.

**Typed counts for a term** — one `UNION ALL` arm per indexed field. A type
with no hit returns no row, which reads as zero:

```cypher
MATCH (n:Taxon) WHERE text_bm25(n, 'scientific_name', 'Bacteroides') > 0
RETURN 'Taxon' AS type, count(*) AS n
UNION ALL
MATCH (n:Disease) WHERE text_bm25(n, 'label', 'Bacteroides') > 0
RETURN 'Disease' AS type, count(*) AS n
UNION ALL
MATCH (n:Signature) WHERE text_bm25(n, 'description', 'Bacteroides') > 0
RETURN 'Signature' AS type, count(*) AS n
UNION ALL
MATCH (n:Paper) WHERE text_bm25(n, 'title', 'Bacteroides') > 0
RETURN 'Paper' AS type, count(*) AS n
```

For `Bacteroides` that is 1,036 taxa, 32 signatures and 7 papers, and no
disease.

**Prefix completion** — BM25 is token-based and `Bacteroid` matches nothing,
so completion is a `STARTS WITH` scan. Over the taxonomy it costs about 8 ms,
and the rank filter is what makes it useful: 99 taxa begin with
`Bacteroides fr`, and exactly one of them is a species.

```cypher
MATCH (t:Taxon)
WHERE t.scientific_name STARTS WITH 'Bacteroides fr' AND t.rank = 'species'
RETURN t.id AS tax_id, t.title AS name ORDER BY name LIMIT 10
```

**Free text to a disease id** — the everyday case, since the key is a MONDO
CURIE few users know. `crohn` returns Crohn disease, Crohn ileitis and Crohn's
colitis, scored:

```cypher
MATCH (d:Disease) WHERE text_bm25(d, 'label', 'crohn') > 0
RETURN d.id AS id, d.title AS label, text_bm25(d, 'label', 'crohn') AS score
ORDER BY score DESC LIMIT 5
```

An old name resolves through the synonym index — D12 — and it should say
which rank it wants, for the reason D12 gives.

## An entity's neighbourhood

What a node is connected to, by relationship and by the type on the other
end. *Bacteroides fragilis* (817) has 16 such rows; the largest is the
measured non-effect of 2,117 drugs that did not inhibit it, which is the
layer this graph keeps and a catalogue's neighbourhood endpoint would not.

```cypher
MATCH (t:Taxon {id: 817})-[r]-(x)
RETURN type(r) AS relationship, labels(x)[0] AS neighbour, count(*) AS n
ORDER BY n DESC
```

## Comparing two entities

Two taxa, by what they share on the other side of any edge — 47 diseases, 37
signatures and 11 metabolites for *B. fragilis* against *F. nucleatum* (853):

```cypher
MATCH (a:Taxon {id: 817})-[]->(x)<-[]-(b:Taxon {id: 853})
RETURN labels(x)[0] AS shared, count(DISTINCT x) AS n ORDER BY n DESC
```

Two diseases, by the taxa reported in both — 195 for Crohn disease against
ulcerative colitis. Direction is per report and is not collapsed here; D17 is
where agreement is asked.

```cypher
MATCH (t:Taxon)-[:ASSOCIATED_WITH]->(:Disease {id: 'MONDO:0005011'})
MATCH (t)-[:ASSOCIATED_WITH]->(:Disease {id: 'MONDO:0005101'})
RETURN count(DISTINCT t) AS shared_taxa
```

## A path between two entities

`shortestPath` with a hop bound. *B. fragilis* to butyrate is 3 hops, through
another taxon and another metabolite — and that is the caveat D16 makes part
of the answer: over a graph this size a shortest path routes through hubs and
is a navigation aid, never evidence.

```cypher
MATCH p = shortestPath((a:Taxon {id: 817})-[*..4]-(m:Metabolite {title: 'Butyric acid'}))
RETURN length(p) AS hops, [n IN nodes(p) | labels(n)[0]] AS types
```

## Producers of a named metabolite class

The short-chain fatty acids are a closed, named question, so the answer set is
worth stating: 441 producers of acetate, 109 of butyrate and 102 of propionate,
among taxa the taxonomy names (placeholders excluded, as in D6).

```cypher
MATCH (t:Taxon)-[:PRODUCES]->(m:Metabolite)
WHERE m.title IN ['Butyric acid', 'Acetic acid', 'Propionic acid']
  AND t.placeholder = false
RETURN m.title AS scfa, count(DISTINCT t) AS producers ORDER BY producers DESC
```

Cross-feeding around one metabolite — producers beside consumers — is D6;
what a taxon produces and the reverse is D5.

## Candidates: biomarkers and probiotics

Both are D-queries already, because both are evidence questions: D1 scores a
signature overlap for a hit list, and D10 ranks depleted taxa as probiotic
candidates with replication as the filter. Neither is a lookup, and neither is
restated here.

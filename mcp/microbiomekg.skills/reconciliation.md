---
name: reconciliation
description: "TRIGGER before any other query whenever the user gives an organism
  as a *name* rather than a tax_id — a name from a paper, a spreadsheet, a
  BLAST hit, an old binomial, a possible misspelling — and whenever a lookup
  returns zero rows for an organism the user is sure exists. A name is not a
  key: resolve it here first, then hand the tax_id to the query skills. SKIP
  once you already hold a tax_id, and for disease/metabolite naming (those
  resolve through their own CURIEs)."
references_tools: [cypher_query]
applies_when:
  graph_has_node_type: [Taxon]
---

# Resolving a printed organism name to a tax_id

**`Taxon` is keyed on the integer NCBI tax_id.** `{id: 851}`, never
`{scientific_name: 'Fusobacterium nucleatum'}`. Everything here exists to get
from the second to the first without inventing a fact.

Four ways a name lookup goes wrong, all of them silent:

- **Renames.** *Clostridium difficile* is now *Clostridioides difficile*
  (1496); *Lactobacillus reuteri* is *Limosilactobacillus reuteri* (1598);
  *Ruminococcus gnavus* is *Mediterraneibacter gnavus* (33038). NCBI is
  **inconsistent** about keeping the old form: for 1747 and 33038 the bare old
  binomial is a synonym, but for 1496, 1598, 1590 and 39491 it exists **only**
  in authority-decorated form (`Clostridium difficile (Hall and O'Toole 1935)
  Lawson et al. 2016`). So an exact name search returns nothing for the single
  most-cited renamed organism in the clinical literature, and the failure looks
  exactly like a data gap.
- **Homonyms.** `Bacillus` is 1386 (bacteria) **and** 55087 (stick insects),
  and both are nodes here — a name match returns two organisms from different
  kingdoms.
  `Proteus` is 583 and 210425 (a salamander). `Morganella` is a three-way
  collision. Even "prefer the bacterial one" fails: `Bacteroides corrodens` is a
  synonym of both 539 and 827, and both are oral/gut bacteria.
- **Strains outrank species in a text search.** A strain's name repeats the
  binomial in a shorter document, so BM25 and n-gram similarity both score it
  higher. **A name lookup must say which rank it wants.**
- **Placeholders are real nodes.** `uncultured bacterium` (77133),
  `Bacteroides sp.` (29523) and Candidatus names resolve and carry
  `placeholder = true`. Exclude them by that boolean, never by a name
  substring.

## Stage 1 — lexical first. This is a contract, not a preference

Consult the exact/lexical index first and take its answer when it has one. A
normalised or fuzzy match consulted *first* is measurably wrong: a greedy
authority-stripper maps `Escherichia coli K-12` to `escherichia coli`, and a
fuzzy-first resolver then reports plain *Escherichia coli* as ambiguous between
562 and 83333.

```cypher
// The old binomial through the synonym index (D12). The rank filter is the
// load-bearing clause: unfiltered, the top three hits for
// 'Lactobacillus reuteri' are strains 491077, 299033 and 1273150, and species
// 1598 is below them.
MATCH (t:Taxon)
WHERE text_bm25(t, 'synonyms', $name) > 0
  AND t.rank = $rank
RETURN t.id AS tax_id, t.title AS current_name, t.rank AS rank,
       t.synonyms AS synonyms,
       text_bm25(t, 'synonyms', $name) AS score
ORDER BY score DESC LIMIT 5
```

This resolves the bare old binomials: *Ruminococcus gnavus* -> 33038,
*Propionibacterium acnes* -> 1747, *Lactobacillus rhamnosus* -> 47715. It
returns nothing useful for a name NCBI keeps only in authority-decorated form,
and nothing at all for a misspelling — both go to stage 2.

## Stage 2 — the vector lane, for a name stage 1 could not match

**Check that this lane exists before you use it.** The embedding store is built
only when the graph was built with `--with-vectors`, and on a graph without one
`text_score()` **raises** — it does not score zero — so the query below fails
outright rather than ranking badly. The probe is one call:

```cypher
CALL db.indexes()
```

A default build returns `FULLTEXT` rows only; a `--with-vectors` build also
returns `Taxon.scientific_name | VECTOR | ONLINE`. `graph_overview()` says
nothing about embedding stores, so this is the only way to know.

**When the `VECTOR` row is absent, do not run this query or the blended one
below.** Resolve what Stage 1 can, then run the `UnresolvedTaxon` tombstone
query, and **say in the answer that the misspelling lane is unavailable on this
graph** — "no such organism" and "this graph cannot resolve a misspelling" are
different answers and collapsing them invents a fact.

The vector store is **not a semantic model**. It is deterministic character
n-gram hashing (`microbiomekg/embedder.py`), so `text_score()` here means
*spelled like*, never *means the same as*: it will resolve
`Akkermansia muciniphilia`, and it will not connect "bowel" to "intestinal".
Say which of those you did.

```cypher
// Two vector lanes fused: the WHOLE name, and the EPITHET alone.
// $epithet is the last whitespace-separated word of the printed name
// ('Clostridium dificile' -> 'dificile'); for a genus-only query pass the same
// string in both.
MATCH (t:Taxon)
WHERE t.rank = $rank AND t.placeholder = false
WITH t, score_fuse(text_score(t, 'scientific_name', $name),
                   text_score(t, 'scientific_name', $epithet)) AS score
RETURN t.id AS tax_id, t.title AS current_name, t.rank AS rank,
       t.synonyms AS synonyms, score
ORDER BY score DESC LIMIT 5
```

**Why two lanes and not one.** A genus rename destroys the first word and
leaves the second: `Clostridium dificile` shares almost nothing with
*Clostridioides difficile* as a whole string — the whole-name lane alone ranks
*Clostridium diolis* first — while the epithet lane alone matches `dificile`
against every *difficile*-like epithet in the tree, including
*Flavobacterium difficile*. Fused, each cancels the other's failure mode.
Measured on a `--with-vectors` graph, the fused query returns the right taxon
at rank 1 for all of: `Clostridium dificile` -> 1496, `Fecalibacterium` -> 216851,
`Akkermansia muciniphilia` -> 239935, `Citrobacter frundii` -> 546,
`Lactobacillus plantari` -> 1590.

## Both lanes in one score, and the trap in doing it

`score_fuse()` takes lanes of any kind, so BM25 and vector can ride one score —
on a graph that has the vector lane. Re-weighting cannot rescue it on a graph
that does not: `text_score()` raises before any fusing happens, whatever weight
it carries, so a zero weight is not a fallback and the whole query fails.

```cypher
MATCH (t:Taxon)
WHERE t.rank = $rank AND t.placeholder = false
WITH t, score_fuse(text_bm25(t, 'synonyms', $name),
                   text_score(t, 'scientific_name', $name),
                   text_score(t, 'scientific_name', $epithet),
                   [0.05, 0.475, 0.475]) AS score
RETURN t.id AS tax_id, t.title AS current_name, t.rank AS rank, score
ORDER BY score DESC LIMIT 5
```

**The weights are the whole query.** BM25 is unbounded and cosine is capped at
1, so at equal weights the lexical lane simply decides the ranking: measured on
the eight fixtures above, equal weights get **4 of 8 wrong**, including three
the vector lanes alone get right. At `[0.05, 0.475, 0.475]` the blend adds the
bare-old-binomial cases to the vector lane's misspelling cases and gets 7 of 8
— losing only `Clostridium dificile`, which is both renamed *and* misspelt and
which the pure vector fusion above resolves.

So the routing rule is **two stages, not one blended score**: lexical first,
vector on a miss. Reach for the blended form when you want one ranked list to
show a user, not when you want the answer.

An absent lane leaves the average rather than scoring zero — a taxon with no
synonyms is not punished for it — which is what makes the blend safe to run
over all 864,132 taxa at once.

## Read the audit trail before trusting the resolution

Every `REPORTED_BY` edge records how *that* spelling resolved, so the graph can
say what it did rather than being taken on trust:

```cypher
MATCH (t:Taxon {id: $taxon_id})-[r:REPORTED_BY]->(s:Signature)
RETURN r.reported_name AS as_printed, r.reported_tax_id AS as_given,
       r.resolution_status AS status,
       r.resolution_normalized AS needed_authority_stripping,
       r.resolution_note AS note, count(s) AS signatures
ORDER BY as_printed
```

Across the graph the statuses are `exact` 114,161 / `merged` 413 / `promoted`
152 / `deleted` 16, and `resolution_normalized` is **true on no edge at all** —
the curators printed current names, so authority stripping is a resolver path
this corpus never exercises. Report that as "nothing needed rescuing", not as
"the resolver works".

## When a name resolves to nothing, it is a tombstone, not a gap

```cypher
// `UnresolvedTaxon.raw_name` has no BM25 index (docs/model.md §6 indexes five
// columns and this is not one), so match it with CONTAINS. text_bm25() over an
// unindexed property does not rank badly — it returns nothing.
MATCH (u:UnresolvedTaxon)
WHERE toLower(u.raw_name) CONTAINS toLower($epithet)
RETURN u.id AS key, u.title AS raw_name, u.status AS status,
       u.source AS source, u.reported_rank AS reported_rank,
       u.n_signatures AS signatures, u.note AS note
ORDER BY raw_name LIMIT 10
```

`UnresolvedTaxon` holds the names no tax_id resolved and the ids NCBI deleted,
still wired to the signatures that cited them — a deleted id keeps its
tombstone and its 16 signatures rather than vanishing. An organism absent from
`Taxon` and present here is a **recorded** failure with a reason, which is a
different answer from "this graph has no data".

## The limit this graph cannot fix

NCBI is the only nomenclatural authority here, and it is not the only one that
exists. LPSN records *Lacticaseibacillus rhamnosus* — taxid 47715, the LGG
probiotic — as **taxonomically suspended** in favour of *Lactobacillus
rhamnosus*, and the same disagreement recurs for *Prevotella* /
*Segatella copri*. One `current name` field cannot express two authorities
disagreeing about one taxid, and this graph has one field. It reports NCBI's
name; the disagreement is invisible. Do not paper over it with an un-renaming
normaliser — that is the string-matching this whole skill exists to prevent.

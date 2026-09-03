"""The semantic name lane: five misspellings must reach the right tax_id.

This is the half of reconciliation the lexical index cannot do. NCBI keeps the
old binomial for *Clostridium difficile*, *Limosilactobacillus reuteri*,
*Lactiplantibacillus plantarum* and *Agathobacter rectalis* **only** in
authority-decorated form (Part C, C4), so an exact or BM25 lookup of the bare
name returns nothing and the failure looks like a data gap. Add a typo on top
and no token-level index can help at all.

The embedder is deterministic character-n-gram hashing, not a downloaded model
— ``microbiomekg/embedder.py`` says why, and the honest consequence is stated
here too: this lane means *spelled like*, never *means the same as*. Every
assertion below is about spelling.

Two stages are tested separately, because each covers exactly what the other
misses and a single blended score does neither job as well (see
``mcp/microbiomekg.skills/reconciliation.md``).
"""

from __future__ import annotations

import pytest

from tests.mcp_support import GRAPH

kglite = pytest.importorskip("kglite")

#: The fused vector query the reconciliation skill teaches for a misspelling.
#: Two lanes over the same store: the whole printed name, and the epithet alone.
#: A genus rename destroys the first word and leaves the second, so neither lane
#: alone resolves both classes — measured below.
FUSED_VECTOR = """
MATCH (t:Taxon)
WHERE t.rank = $rank AND t.placeholder = false
WITH t, score_fuse(text_score(t, 'scientific_name', $name),
                   text_score(t, 'scientific_name', $epithet)) AS score
RETURN t.id AS tax_id, t.title AS current_name, score
ORDER BY score DESC LIMIT 5
"""

SINGLE_VECTOR = """
MATCH (t:Taxon)
WHERE t.rank = $rank AND t.placeholder = false
RETURN t.id AS tax_id, t.title AS current_name,
       text_score(t, 'scientific_name', $name) AS score
ORDER BY score DESC LIMIT 5
"""

#: The lexical stage: an exactly-spelled old binomial through the synonym index.
BM25_SYNONYMS = """
MATCH (t:Taxon)
WHERE text_bm25(t, 'synonyms', $name) > 0 AND t.rank = $rank
RETURN t.id AS tax_id, t.title AS current_name,
       text_bm25(t, 'synonyms', $name) AS score
ORDER BY score DESC LIMIT 5
"""

#: The blended single score the skill shows and warns about.
BLENDED = """
MATCH (t:Taxon)
WHERE t.rank = $rank AND t.placeholder = false
WITH t, score_fuse(text_bm25(t, 'synonyms', $name),
                   text_score(t, 'scientific_name', $name),
                   text_score(t, 'scientific_name', $epithet),
                   $weights) AS score
RETURN t.id AS tax_id, t.title AS current_name, score
ORDER BY score DESC LIMIT 5
"""

#: (printed name, epithet, expected tax_id, rank wanted, what makes it hard).
#: Every one is a name class Part C catalogues: C1's `(sic)` misspelling class,
#: C4's renamed genera, and the free-text organism strings HMDB ships (Part D,
#: D5: `Citrobacter frundii`, `Akkermansia muciniphilia` verbatim).
MISSPELLINGS = [
    ("Clostridium dificile", "dificile", 1496, "species", "renamed genus AND misspelt epithet"),
    ("Fecalibacterium", "Fecalibacterium", 216851, "genus", "dropped vowel, genus rank"),
    ("Akkermansia muciniphilia", "muciniphilia", 239935, "species", "HMDB's spelling of the epithet"),
    ("Citrobacter frundii", "frundii", 546, "species", "HMDB's spelling, dropped 'e'"),
    ("Lactobacillus plantari", "plantari", 1590, "species", "renamed genus AND truncated epithet"),
]

#: Correctly-spelled old binomials NCBI keeps as bare synonyms (C4). The vector
#: lane cannot know these are the same organism; the synonym index can.
OLD_BINOMIALS = [
    ("Ruminococcus gnavus", 33038, "species"),
    ("Propionibacterium acnes", 1747, "species"),
    ("Lactobacillus rhamnosus", 47715, "species"),
]


@pytest.fixture(scope="session")
def graph():
    if not GRAPH.exists():
        pytest.skip(
            f"no graph at {GRAPH} — build it with "
            f"`.venv/bin/python scripts/build.py --scope microbial`"
        )
    loaded = kglite.load(str(GRAPH))
    if loaded.embedding_dim("Taxon", "scientific_name") is None:
        pytest.skip(
            "this graph carries no Taxon.scientific_name vectors — rebuild without "
            "`--no-vectors`"
        )
    from microbiomekg.embedder import CharGramEmbedder

    loaded.set_embedder(CharGramEmbedder())
    return loaded


def top(graph, query: str, **params) -> list[dict]:
    return list(graph.cypher(query, params=params))


def test_the_stores_are_the_two_the_build_declares(graph):
    stores = {
        (store["node_type"], store["text_column"]): store for store in graph.list_embeddings()
    }
    assert set(stores) == {("Taxon", "scientific_name"), ("Disease", "label")}
    assert stores[("Taxon", "scientific_name")]["count"] == 864110
    assert stores[("Disease", "label")]["count"] == 808
    for store in stores.values():
        assert store["dimension"] == 256
        assert store["metric"] == "cosine"


@pytest.mark.parametrize(
    "name,epithet,tax_id,rank,why", MISSPELLINGS, ids=[case[0] for case in MISSPELLINGS]
)
def test_a_misspelling_resolves_to_the_right_taxon(graph, name, epithet, tax_id, rank, why):
    rows = top(graph, FUSED_VECTOR, name=name, epithet=epithet, rank=rank)
    assert rows, f"{name!r} returned nothing at rank {rank!r}"
    assert rows[0]["tax_id"] == tax_id, (
        f"{name!r} ({why}) resolved to {rows[0]['tax_id']} "
        f"({rows[0]['current_name']!r}), expected {tax_id}"
    )


def test_both_lanes_are_needed_and_neither_alone_suffices(graph):
    """The reason the skill routes in two stages instead of blending one score.

    Asserting the *complementarity*, not just the successes: a single-lane
    result that happened to pass would make the second lane look like
    decoration, and the next person would delete it.
    """
    single_lane_misses = [
        name
        for name, epithet, tax_id, rank, _ in MISSPELLINGS
        if top(graph, SINGLE_VECTOR, name=name, rank=rank)[0]["tax_id"] != tax_id
    ]
    assert single_lane_misses, (
        "the whole-name vector lane alone now resolves every misspelling — if that "
        "is real, the epithet lane is no longer earning its place"
    )

    vector_misses_an_old_binomial = False
    for name, tax_id, rank in OLD_BINOMIALS:
        epithet = name.split()[-1]
        if top(graph, FUSED_VECTOR, name=name, epithet=epithet, rank=rank)[0]["tax_id"] != tax_id:
            vector_misses_an_old_binomial = True
        # …and the lexical lane gets every one of them.
        lexical = top(graph, BM25_SYNONYMS, name=name, rank=rank)
        assert lexical and lexical[0]["tax_id"] == tax_id, (
            f"the synonym index failed on {name!r}, which NCBI keeps as a bare synonym"
        )
    assert vector_misses_an_old_binomial, (
        "the vector lane now resolves every renamed binomial too — if that is real, "
        "the lexical-first stage can be reconsidered"
    )


def test_equal_weights_let_bm25_decide_the_blend(graph):
    """Why the blended query in the skill carries a 0.05 weight on the BM25 lane.

    BM25 is unbounded, cosine is capped at 1. Fused at equal weights the lexical
    lane simply *is* the ranking — this asserts that failure so the weights are
    not tidied away as arbitrary.
    """
    cases = [(n, e, t, r) for n, e, t, r, _ in MISSPELLINGS] + [
        (n, n.split()[-1], t, r) for n, t, r in OLD_BINOMIALS
    ]
    equal = sum(
        top(graph, BLENDED, name=n, epithet=e, rank=r, weights=[1.0, 1.0, 1.0])[0]["tax_id"] == t
        for n, e, t, r in cases
    )
    tuned = sum(
        top(graph, BLENDED, name=n, epithet=e, rank=r, weights=[0.05, 0.475, 0.475])[0]["tax_id"] == t
        for n, e, t, r in cases
    )
    assert equal < tuned, (
        f"equal weights resolved {equal}/{len(cases)} and the tuned weights "
        f"{tuned}/{len(cases)} — the skill's warning about scale mismatch no longer holds"
    )


def test_the_disease_store_answers_a_free_text_condition(graph):
    """`Disease` is keyed on a MONDO/EFO CURIE almost nobody knows by heart, so
    the vector lane over `label` is the entry point to every disease query."""
    rows = top(
        graph,
        """
        MATCH (d:Disease)
        RETURN d.id AS id, d.title AS label, text_score(d, 'label', $q) AS score
        ORDER BY score DESC LIMIT 5
        """,
        q="colorectal cancer",
    )
    assert rows[0]["id"] == "MONDO:0005575", rows


def test_the_index_agrees_with_an_exact_scan(graph):
    """The HNSW index is a cache and must not change the answer.

    It did: at kglite's default `ef_search=64` this corpus — hashed n-grams,
    the "unclustered high-dimensional" case its docs warn about — returned
    *Enterobacteriaceae bacterium HGPR34* at 0.428 for `Citrobacter frundii`
    while *Citrobacter freundii* sat unfound at 0.808. Cypher pushes
    `ORDER BY text_score(...) DESC LIMIT n` into the index, so the wrong answer
    arrives as an ordinary result set. The build pins `ef_search=512`; this is
    the check that the pin is still in the saved graph.
    """
    for name, _epithet, tax_id, _rank, _why in MISSPELLINGS:
        approx = graph.select("Taxon").search_text("scientific_name", name, top_k=1)
        exact = graph.select("Taxon").search_text("scientific_name", name, top_k=1, exact=True)
        assert approx[0]["id"] == exact[0]["id"], (
            f"HNSW disagrees with the exact scan on {name!r}: "
            f"{approx[0]['id']} ({approx[0]['score']:.3f}) vs "
            f"{exact[0]['id']} ({exact[0]['score']:.3f}) — raise ef_search in "
            f"scripts/build.py VECTOR_INDEXES and rebuild"
        )

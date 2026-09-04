"""Build the graph from the fixture and assert GOLDEN values.

`count > 0` passes on a graph that lost 90% of its rows, so every number below
is exact. Each was derived **twice, independently**: once by re-deriving it
from `tests/fixtures/bugsigdb_mini.csv` + `taxdump_mini/` here in the test
module's own terms, and once by reading it off the pipeline's output. Where
the two disagree the golden is the *first* derivation, and the test is meant
to stay red until the pipeline agrees. Part C19 records the table.

The module skips — with a reason naming the missing piece — if the
implementation, the prep scripts or the blueprint are not there.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import BUGSIGDB_MINI, MONDO_MINI, TAXDUMP_MINI, read_bugsigdb

kglite = pytest.importorskip("kglite")
pytest.importorskip(
    "microbiomekg.reconcile",
    reason="microbiomekg.reconcile is not implemented — the build cannot resolve taxa",
)
pytest.importorskip(
    "microbiomekg.ontology",
    reason="microbiomekg.ontology is not implemented — the build has no ontology to gate on",
)

from microbiomekg.ontology import (  # noqa: E402
    ASSOCIATION_RELATIONSHIPS,
    EVIDENCE_CONTRACT,
)

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "blueprint.json"
PREP_BUGSIGDB = ROOT / "microbiomekg" / "preps" / "prep_bugsigdb.py"
PREP_TAXONOMY = ROOT / "microbiomekg" / "preps" / "prep_taxonomy.py"

for _needed in (BLUEPRINT, PREP_BUGSIGDB, PREP_TAXONOMY):
    if not _needed.is_file():
        pytest.skip(
            f"{_needed.relative_to(ROOT)} does not exist yet", allow_module_level=True
        )


# --------------------------------------------------------------------------
# Golden values. See the module docstring for how they were derived.
# --------------------------------------------------------------------------

INPUT_ROWS = 43  # 34 real BugSigDB rows + 9 adversarial

NODE_COUNTS = {
    "Signature": 43,  # one per input row; BSDB IDs are unique
    "Study": 39,  # distinct BugSigDB Study ids
    "Paper": 33,  # distinct PMIDs; 5 rows have none
    # The 20 distinct terms of the `EFO ID` column, routed by vocabulary:
    # 6 MONDO + 9 EFO are diseases, HP:0002745 is a phenotype, 2 CHEBI + EXO +
    # GSSO are exposures, and NCBITAXON:568703 is an organism and gets no node
    # at all — it is in `unresolved_conditions` instead (C14).
    "Disease": 15,
    "Phenotype": 1,
    "Exposure": 4,
    "BodySite": 9,  # distinct UBERON ids
    "Taxon": 143,  # 53 cited + their lineage closure to root
    "UnresolvedTaxon": 3,  # 1009 deleted, 999999999 unknown, an ambiguous name
}

EDGE_COUNTS = {
    "HAS_PARENT": 142,  # every Taxon but root, which is its own parent
    "REPORTED_BY": 74,  # every taxon mention, resolved or not
    # (resolved taxon x condition term) per signature, over the union of the
    # three condition types. 72, not 73: the one association to
    # NCBITAXON:568703 has no condition node to point at and is in the ledger.
    "ASSOCIATED_WITH": 72,
    "IN_CONDITION": 43,
    "AT_BODY_SITE": 45,
    "PART_OF_STUDY": 43,
    "PUBLISHED_AS": 34,
}

#: Every association edge, whatever its condition type — one relationship name
#: over a union range since kglite 0.16.22 (docs/model.md §8).
ANY_ASSOCIATION = "ASSOCIATED_WITH"
ASSOCIATION_EDGES = 72

CITED_TAXA = 53  # taxa some signature actually named
TAXON_MENTIONS = 74  # 71 resolvable + 3 not
UNRESOLVED_RECORDS = 3

#: Condition terms with no node type of their own — NCBITAXON:568703.
UNRESOLVED_CONDITIONS = 1
#: Disease-hub misses: 14 of the 20 typed terms have no MONDO equivalence in
#: the 2026-09-01 release (all 9 EFO ids, the 4 exposures, the phenotype), so
#: they keep their own CURIE as key. The 6 MONDO ids are their own hub key.
CONDITIONS_WITHOUT_MONDO = 14

# ASSOCIATED_WITH edges missing at least one evidence property. `ontology_audit`
# counts edges, not property-instances, so this is the union.
EDGES_MISSING_EVIDENCE = 16

UNRESOLVED_REPORT = "unresolved_taxa"
CONDITION_LEDGER = "unresolved_conditions"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Run the real preps over the fixture, in process, then the real blueprint."""
    from microbiomekg import pipeline
    from microbiomekg.preps import prep_bugsigdb, prep_taxonomy
    from microbiomekg.tables import Frames

    store = Frames()
    prep_bugsigdb.run(BUGSIGDB_MINI, store, taxdump=TAXDUMP_MINI, mondo=MONDO_MINI)
    prep_taxonomy.run(BUGSIGDB_MINI.parent, store, taxdump=TAXDUMP_MINI, scope="cited")
    # The BugSigDB slice of the blueprint, not the shipped whole: this fixture
    # preps one source, and a blueprint declaring another source's node types
    # would load them as empty — which makes every ontology rule over them a
    # gate that cannot fail (`test_audit_denominators_are_not_zero`).
    graph, _ = pipeline.load_graph(store, ["bugsigdb"], verbose=False)
    return graph, store


@pytest.fixture(scope="module")
def graph(built):
    return built[0]


@pytest.fixture(scope="module")
def store(built):
    return built[1]


@pytest.fixture(scope="module")
def condition_ledger(store):
    assert CONDITION_LEDGER in store, f"the build wrote no {CONDITION_LEDGER}"
    return store.rows(CONDITION_LEDGER)


@pytest.fixture(scope="module")
def unresolved_report(store):
    assert UNRESOLVED_REPORT in store, f"the build wrote no {UNRESOLVED_REPORT}"
    return store.rows(UNRESOLVED_REPORT)


def rows(graph, query):
    return list(graph.cypher(query))


def count(graph, query):
    return rows(graph, query)[0]["n"]


# --------------------------------------------------------------------------
# C19 — golden counts
# --------------------------------------------------------------------------


def test_golden_node_counts(graph):
    got = {
        r["t"]: r["n"]
        for r in rows(graph, "MATCH (n) RETURN labels(n)[0] AS t, count(n) AS n")
    }
    assert got == NODE_COUNTS


def test_golden_edge_counts(graph):
    got = {
        r["t"]: r["n"]
        for r in rows(graph, "MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS n")
    }
    assert got == EDGE_COUNTS


def test_every_input_row_became_a_signature(graph):
    assert count(graph, "MATCH (s:Signature) RETURN count(s) AS n") == INPUT_ROWS
    assert len(read_bugsigdb()) == INPUT_ROWS


# --------------------------------------------------------------------------
# C10 — the taxon column is a lineage path
# --------------------------------------------------------------------------


def test_only_leaf_taxa_are_cited(graph):
    """C10: the last element of a `|` path is the taxon; the rest are ancestors.

    Ancestors are legitimately *present* — HAS_PARENT has to be walkable — but
    they must carry no REPORTED_BY edge, because no study named them.
    """
    assert (
        count(
            graph,
            "MATCH (t:Taxon) WHERE EXISTS { (t)-[:REPORTED_BY]->() } RETURN count(t) AS n",
        )
        == CITED_TAXA
    )


@pytest.mark.parametrize(
    "ancestor",
    [
        2,  # Bacteria
        131567,  # cellular organisms
        1783272,  # Bacillati
        1224,  # Pseudomonadota
        91347,  # Enterobacterales
    ],
)
def test_ancestors_acquire_no_association_edges(graph, ancestor):
    """C10: splitting on `|` too would give 1,306 phantom taxa edges in the full dump."""
    assert (
        count(
            graph,
            f"MATCH (t:Taxon)-[r:REPORTED_BY|ASSOCIATED_WITH]->() "
            f"WHERE t.tax_id = {ancestor} RETURN count(r) AS n",
        )
        == 0
    ), f"{ancestor} is a lineage ancestor, not a reported taxon"


# --------------------------------------------------------------------------
# C6 / C7 — merged ids and promotion, in the built graph
# --------------------------------------------------------------------------


@pytest.mark.parametrize("old, new", [(1440055, 1496), (105824, 853)])
def test_merged_old_id_absent_new_id_present(graph, old, new):
    assert (
        count(graph, f"MATCH (t:Taxon) WHERE t.tax_id = {old} RETURN count(t) AS n")
        == 0
    ), f"the retired id {old} became a node"
    assert (
        count(graph, f"MATCH (t:Taxon) WHERE t.tax_id = {new} RETURN count(t) AS n")
        == 1
    ), f"the survivor {new} is missing"


def test_merged_row_lands_on_the_survivor(graph):
    """`bsdb:adv-merged/1/1` cites 1440055; the edge must reach 1496."""
    hit = rows(
        graph,
        "MATCH (t:Taxon)-[r:REPORTED_BY]->(s:Signature) "
        "WHERE s.signature_id = 'bsdb:adv-merged/1/1' "
        "RETURN t.tax_id AS tax_id, r.resolution_status AS status, "
        "r.reported_tax_id AS reported",
    )
    assert [h["tax_id"] for h in hit] == [1496]
    assert hit[0]["status"] == "merged"
    assert hit[0]["reported"] == 1440055, "the original id was not kept on the edge"


@pytest.mark.parametrize(
    "signature_id, cited, landed, rank",
    [
        ("bsdb:adv-strain/1/1", 83333, 562, "strain"),
        ("bsdb:adv-subsp/1/1", 1682, 216816, "subspecies"),
    ],
)
def test_below_species_rows_land_on_the_species_node(
    graph, signature_id, cited, landed, rank
):
    """C7: promoted, with the original id and rank kept on the edge."""
    assert (
        count(graph, f"MATCH (t:Taxon) WHERE t.tax_id = {cited} RETURN count(t) AS n")
        == 0
    ), f"{cited} is below species and must not be a node of its own"
    hit = rows(
        graph,
        f"MATCH (t:Taxon)-[r:REPORTED_BY]->(s:Signature) "
        f"WHERE s.signature_id = '{signature_id}' "
        f"RETURN t.tax_id AS tax_id, r.resolution_status AS status, "
        f"r.reported_tax_id AS reported, r.reported_rank AS reported_rank, "
        f"r.original_rank AS original_rank",
    )
    assert [h["tax_id"] for h in hit] == [landed]
    assert hit[0]["status"] == "promoted"
    assert hit[0]["reported"] == cited
    # C21.4: two ranks, two meanings. `reported_rank` is what the *source*
    # claimed — MetaPhlAn's `t__` prefix, which has no `subspecies` and calls
    # both of these a strain. `original_rank` is NCBI's rank for the same id.
    assert hit[0]["reported_rank"] == "strain"
    assert hit[0]["original_rank"] == rank


# --------------------------------------------------------------------------
# C12 / C13 — direction and dedupe
# --------------------------------------------------------------------------


def test_direction_is_stored_per_association(graph):
    """C12: `increased` means "in Group 1", so it belongs on the edge."""
    hit = rows(
        graph,
        "MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease) "
        "WHERE t.tax_id = 853 AND d.condition_id = 'MONDO:0011122' "
        "RETURN r.direction AS direction, r.signature_id AS sig",
    )
    got = {h["sig"]: h["direction"] for h in hit}
    assert got == {
        "bsdb:19849869/1/1": "increased",
        "bsdb:23032991/1/1": "increased",
        "bsdb:adv-noevidence/1/1": "increased",
    }


def test_same_pair_from_three_signatures_is_three_edges(graph):
    """C13: three experiments of PMID 23459324 — same taxon, same condition."""
    sigs = sorted(
        h["sig"]
        for h in rows(
            graph,
            "MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease) "
            "WHERE t.tax_id = 1598 AND d.condition_id = 'MONDO:0011122' "
            "RETURN r.signature_id AS sig",
        )
    )
    assert sigs == [
        "bsdb:23459324/3/2",
        "bsdb:23459324/4/1",
        "bsdb:23459324/6/1",
    ], "the three signatures were collapsed into one edge"


def test_the_condition_union_is_matchable_as_one_label(graph):
    """`Condition` is abstract in the ontology and a real label on the nodes.

    The blueprint stamps it (`labels: ["Condition"]`), so the union the range
    check reasons about is also a thing a query can name — without
    `materialize_ontology()`, which changes query semantics graph-wide, and
    without re-rooting the `is_a` forest, which has one parent per class.

    The primary label stays first in `labels(n)`, which the build report and
    every `labels(n)[0]` query depend on.
    """
    total = count(graph, "MATCH (c:Condition) RETURN count(c) AS n")
    parts = sum(
        count(graph, f"MATCH (c:{kind}) RETURN count(c) AS n")
        for kind in ("Disease", "Phenotype", "Exposure")
    )
    assert (
        total
        == parts
        == (NODE_COUNTS["Disease"] + NODE_COUNTS["Phenotype"] + NODE_COUNTS["Exposure"])
    )
    primaries = {
        r["t"]
        for r in rows(
            graph,
            "MATCH (c:Condition) RETURN DISTINCT labels(c)[0] AS t",
        )
    }
    assert primaries == {"Disease", "Phenotype", "Exposure"}, (
        f"`Condition` displaced the primary label: {primaries}"
    )
    # And it reaches a node no CSV supplied — the blueprint owns every node of
    # the types it declares, including a stub some edge vivified.
    assert (
        count(
            graph,
            "MATCH (:Taxon)-[:ASSOCIATED_WITH]->(c:Condition) RETURN count(c) AS n",
        )
        == ASSOCIATION_EDGES
    )


def test_conflicting_directions_survive_as_separate_edges(graph):
    """C12: 1386 is increased on `bsdb:27026576/1/1`, decreased on `/3/2`."""
    got = {
        h["sig"]: h["direction"]
        for h in rows(
            graph,
            "MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Phenotype) "
            "WHERE t.tax_id = 1386 AND d.condition_id = 'HP:0002745' "
            "RETURN r.signature_id AS sig, r.direction AS direction",
        )
    }
    assert got == {
        "bsdb:27026576/1/1": "increased",
        "bsdb:27026576/3/2": "decreased",
    }


# --------------------------------------------------------------------------
# C14 — condition identity
# --------------------------------------------------------------------------


def test_condition_terms_keep_their_source_vocabulary(graph):
    """C14: the `EFO ID` column carries EFO, MONDO, CHEBI, EXO, GSSO, HP, NCBITAXON.

    Keying on MONDO does not throw the source id away — `source_vocabulary` is
    what makes `WHERE d.source_vocabulary = 'EFO'` expressible after the hub
    has renamed the key.
    """
    got = {}
    for label in ("Disease", "Phenotype", "Exposure"):
        for r in rows(
            graph,
            f"MATCH (d:{label}) RETURN d.source_vocabulary AS v, count(d) AS n",
        ):
            got[(label, r["v"])] = r["n"]
    assert got == {
        ("Disease", "EFO"): 9,
        ("Disease", "MONDO"): 6,
        ("Phenotype", "HP"): 1,
        ("Exposure", "CHEBI"): 2,
        ("Exposure", "EXO"): 1,
        ("Exposure", "GSSO"): 1,
    }


def test_non_disease_terms_are_not_disease_nodes(graph, condition_ledger):
    """C14: `NCBITAXON:568703` is *Lacticaseibacillus rhamnosus* GG — an organism
    used as the exposure, not a disease and not a term this model types at all.

    It is not dropped: it is in `unresolved_conditions` with its raw
    strings and the reason.
    """
    for label in ("Disease", "Phenotype", "Exposure"):
        assert (
            count(
                graph,
                f"MATCH (d:{label}) WHERE d.condition_id = 'NCBITAXON:568703' "
                f"RETURN count(d) AS n",
            )
            == 0
        ), f"an NCBI organism became a :{label}"
    ledgered = [r for r in condition_ledger if r["source_id"] == "NCBITAXON:568703"]
    assert ledgered, "the NCBITAXON condition vanished instead of reaching the ledger"
    assert ledgered[0]["source_vocabulary"] == "NCBITAXON"
    assert ledgered[0]["reason"]
    assert len(condition_ledger) == UNRESOLVED_CONDITIONS


def test_the_phenotype_and_exposure_terms_are_their_own_types(graph):
    """C14: `HP:0002745` (Oral leukoplakia) is a phenotype and `CHEBI:33281`
    (Antimicrobial agent) is a chemical exposure. Neither is a disease."""
    assert (
        count(
            graph,
            "MATCH (d:Phenotype) WHERE d.condition_id = 'HP:0002745' "
            "RETURN count(d) AS n",
        )
        == 1
    )
    assert (
        count(
            graph,
            "MATCH (d:Exposure) WHERE d.condition_id = 'CHEBI:33281' "
            "RETURN count(d) AS n",
        )
        == 1
    )
    assert (
        count(
            graph,
            "MATCH (d:Disease) WHERE d.condition_id IN "
            "['HP:0002745','CHEBI:33281'] RETURN count(d) AS n",
        )
        == 0
    )


def test_two_colorectal_terms_stay_distinct(graph):
    """C14: MONDO:0005575 (cancer) and MONDO:0024331 (carcinoma) are not one term."""
    got = {
        r["d"]
        for r in rows(
            graph,
            "MATCH (d:Disease) WHERE d.condition_id IN "
            "['MONDO:0005575','MONDO:0024331'] RETURN d.condition_id AS d",
        )
    }
    assert got == {"MONDO:0005575", "MONDO:0024331"}


def test_multi_condition_row_links_to_both_terms(graph):
    """C14: `bsdb:23349750/1/2` is `EFO:0001799,EXO:0000114` — a set, not a zip.

    Equal comma counts, so the pairing is positional: `Ethnic group` to the EFO
    id and `Socioeconomic status` to the EXO one. The two terms land in
    different node types, and both links survive.
    """
    got = {
        (r["t"], r["d"], r["c"])
        for r in rows(
            graph,
            "MATCH (s:Signature)-[:IN_CONDITION]->(d) "
            "WHERE s.signature_id = 'bsdb:23349750/1/2' "
            "RETURN labels(d)[0] AS t, d.condition_id AS d, d.source_condition AS c",
        )
    }
    assert got == {
        ("Disease", "EFO:0001799", "Ethnic group"),
        ("Exposure", "EXO:0000114", "Socioeconomic status"),
    }


# --------------------------------------------------------------------------
# C15 — paper identity
# --------------------------------------------------------------------------


def test_papers_without_pmid_do_not_collapse(graph):
    """C15: five fixture rows have PMID `NA`, from five distinct studies.

    Keying `:Paper` on PMID would map all five to a node called `NA`. The
    model instead gives every row a `:Study` and hangs `PUBLISHED_AS` off it
    only when there is a PMID — so the five stay five studies with no paper.
    """
    sigs = (
        "'bsdb:11/1/1','bsdb:39/1/1','bsdb:513/1/1','bsdb:562/1/1',"
        "'bsdb:adv-noevidence/1/1'"
    )
    studies = {
        r["sid"]
        for r in rows(
            graph,
            f"MATCH (s:Signature)-[:PART_OF_STUDY]->(st:Study) "
            f"WHERE s.signature_id IN [{sigs}] RETURN st.study_id AS sid",
        )
    }
    assert len(studies) == 5, f"five PMID-less papers collapsed into {len(studies)}"
    assert (
        count(
            graph,
            f"MATCH (s:Signature)-[:PART_OF_STUDY]->(st:Study)-[:PUBLISHED_AS]->(:Paper) "
            f"WHERE s.signature_id IN [{sigs}] RETURN count(*) AS n",
        )
        == 0
    ), "a paper was invented for a study that has no PMID"
    assert count(graph, "MATCH (p:Paper) RETURN count(p) AS n") == NODE_COUNTS["Paper"]


def test_doi_forms_are_normalised(graph):
    """C15: bare, `https://doi.org/...` and DataCite forms all appear upstream."""
    dois = [
        r["doi"]
        for r in rows(graph, "MATCH (st:Study) RETURN st.doi AS doi")
        if r["doi"]
    ]
    assert dois, "no study carries a DOI at all"
    bad = [d for d in dois if d.startswith("http") or d != d.lower()]
    assert not bad, f"un-normalised DOIs survived into the graph: {sorted(bad)}"


# --------------------------------------------------------------------------
# C16 — integer id pitfalls
# --------------------------------------------------------------------------


def test_tax_ids_are_integers_not_strings(graph):
    """C16: a string key silently matches nothing on an integer comparison."""
    assert (
        count(graph, "MATCH (t:Taxon) WHERE t.tax_id = 562 RETURN count(t) AS n") == 1
    ), "`WHERE t.tax_id = 562` found nothing — the ids landed as strings"
    value = rows(graph, "MATCH (t:Taxon) WHERE t.tax_id = 562 RETURN t.tax_id AS v")[0][
        "v"
    ]
    assert isinstance(value, int) and not isinstance(value, bool)


def test_sample_sizes_are_integers_not_floats(graph):
    """C16: one `NA` makes the pandas column float64 and pins the schema to Float64."""
    hit = rows(
        graph,
        "MATCH (s:Signature) WHERE s.signature_id = 'bsdb:19849869/1/1' "
        "RETURN s.group_0_size AS g0, s.group_1_size AS g1",
    )[0]
    assert hit["g0"] == 13 and hit["g1"] == 15
    for key, value in hit.items():
        assert not isinstance(value, float), (
            f"{key} is {value!r}, a float — a pandas NaN widened the column"
        )


def test_missing_sample_size_is_absent_not_the_string_NA(graph):
    """C16/C17: `NA` written through as text makes every evidence gap look filled."""
    hit = rows(
        graph,
        "MATCH (s:Signature) WHERE s.signature_id = 'bsdb:23032991/1/1' "
        "RETURN s.group_1_size AS g1",
    )[0]
    assert hit["g1"] is None, f"missing sample size came through as {hit['g1']!r}"


# --------------------------------------------------------------------------
# C17 — evidence completeness is countable
# --------------------------------------------------------------------------


def test_ontology_audit_counts_the_missing_evidence_edges(graph):
    """C17: 16 of the 73 association edges are missing at least one evidence field."""
    audit = {
        r["rule"]: r
        for r in rows(
            graph,
            "CALL ontology_audit() YIELD rule, severity, violations, exempted, total, pct",
        )
    }
    assert audit, "ontology_audit() returned nothing — no ontology was declared"
    violations = total = 0
    for rel in ASSOCIATION_RELATIONSHIPS:
        rule = audit.get(f"{rel}.required_properties")
        assert rule is not None, (
            f"{rel} declares no required_properties — the evidence contract is "
            f"then unmeasurable"
        )
        assert rule["severity"] == "warn", (
            "an upstream-data-reality rule at `error` refuses to build the real export"
        )
        violations += rule["violations"]
        total += rule["total"]
    assert total == ASSOCIATION_EDGES
    assert violations == EDGES_MISSING_EVIDENCE


def test_edge_property_violation_names_the_evidence_free_row(graph):
    """C17: the row-level drill-down behind the audit count.

    `edge_property_violation()` emits **one row per violating edge**, naming
    only the *first* missing property in declaration order — not one row per
    missing field. So it identifies *which* edges are incomplete, and a
    per-field census needs the Cypher query in the next test.
    """
    flagged = [
        (r["source"], r["property"])
        for r in rows(
            graph,
            "CALL edge_property_violation() YIELD check, source, property "
            "RETURN source.tax_id AS source, property AS property",
        )
    ]
    assert len(flagged) == EDGES_MISSING_EVIDENCE, (
        "one row per violating edge is the documented shape; the audit counted "
        f"{EDGES_MISSING_EVIDENCE} violating edges but the drill-down listed "
        f"{len(flagged)}"
    )
    props = {p for s, p in flagged if s == 853}
    assert "study_design" in props, (
        f"the evidence-free row `bsdb:adv-noevidence/1/1` (taxon 853) was not "
        f"flagged for its missing study design: {sorted(props)}"
    )
    contract = set(EVIDENCE_CONTRACT)
    assert {p for _, p in flagged} <= contract, (
        "a property outside the declared evidence contract was flagged"
    )


@pytest.mark.parametrize(
    "prop, missing",
    [
        ("pmid", 6),
        ("direction", 1),
        ("statistical_test", 6),
        ("group_0_size", 2),
        ("study_design", 3),
        ("group_1_size", 5),
        ("sequencing_type", 5),
        ("evidence_level", 0),  # always derived, never absent
        # The source's own wording of the relation, kept beside the normalised
        # `direction`. Absent exactly where the direction is, so the gap stays
        # countable instead of being papered over with a "not reported" string.
        ("source_relation", 1),
        ("knowledge_level", 0),
        ("agent_type", 0),
        ("primary_source", 0),
        ("source_record_id", 0),
        ("source_licence", 0),
    ],
)
def test_per_field_evidence_gap_census(graph, prop, missing):
    """C17/A1: "what fraction of edges lack each evidence field" is the ask.

    `ontology_audit()` gives the edge count; only this query gives the
    per-field breakdown, and A1 asks for the per-field number. It runs over
    *every* association relationship: asking only the disease one would report
    a confidently low number that happens to be right.
    """
    got = count(
        graph,
        f"MATCH ()-[r:{ANY_ASSOCIATION}]->() WHERE r.{prop} IS NULL "
        f"RETURN count(r) AS n",
    )
    assert got == missing, f"{prop}: {got} edges lack it, expected {missing}"


def test_every_association_carries_the_biolink_evidence_pair(graph):
    """Schema survey §5(b): the pair replaces a confidence score, so it has to
    be on every edge, verbatim, and derived from the source — not defaulted."""
    got = {
        (r["k"], r["a"], r["s"], r["lic"]): r["n"]
        for r in rows(
            graph,
            f"MATCH ()-[r:{ANY_ASSOCIATION}]->() "
            f"RETURN r.knowledge_level AS k, r.agent_type AS a, "
            f"r.primary_source AS s, r.source_licence AS lic, count(r) AS n",
        )
    }
    assert got == {
        (
            "statistical_association",
            "manual_agent",
            "bugsigdb",
            "CC-BY-4.0",
        ): ASSOCIATION_EDGES
    }


def test_the_source_record_id_is_the_sources_own_key(graph):
    """It is what makes an edge re-verifiable against the source and diffable
    across a refresh, so it must be BugSigDB's BSDB ID, not a mint of ours."""
    hit = rows(
        graph,
        f"MATCH ()-[r:{ANY_ASSOCIATION}]->() "
        f"WHERE r.source_record_id = 'bsdb:adv-noevidence/1/1' "
        f"RETURN r.source_relation AS rel, r.signature_id AS sig",
    )
    assert hit, "no edge carries the source's own record id"
    assert hit[0]["sig"] == "bsdb:adv-noevidence/1/1"
    assert hit[0]["rel"] == "abundance in group 1 increased"


def test_audit_denominators_are_not_zero(graph):
    """A rule with total 0 is a gate that cannot fail."""
    for r in rows(
        graph, "CALL ontology_audit() YIELD rule, total, violations RETURN rule, total"
    ):
        assert r["total"] > 0, f"{r['rule']} audits nothing"


# --------------------------------------------------------------------------
# C18 — silent drops
# --------------------------------------------------------------------------


def test_every_taxon_mention_is_accounted_for(graph, unresolved_report):
    """C18: REPORTED_BY edges + unresolved records == mentions in."""
    reported = count(graph, "MATCH ()-[r:REPORTED_BY]->() RETURN count(r) AS n")
    assert reported == TAXON_MENTIONS, (
        f"{TAXON_MENTIONS} taxa were mentioned by the 42 rows but only {reported} "
        f"REPORTED_BY edges exist — mentions vanished between the CSV and the graph"
    )
    assert len(unresolved_report) == UNRESOLVED_RECORDS


@pytest.mark.parametrize(
    "cited, status",
    [
        ("1009", "deleted"),
        ("999999999", "unresolved"),
        ("Bacteroides corrodens", "ambiguous"),
    ],
)
def test_adversarial_rows_are_in_the_unresolved_report(
    unresolved_report, cited, status
):
    """C18: never dropped, never guessed — recorded with the reason."""
    hits = [r for r in unresolved_report if cited in r.values()]
    assert hits, (
        f"{cited!r} is missing from {UNRESOLVED_REPORT} — it was dropped silently"
    )
    assert any(r.get("status") == status for r in hits), (
        f"{cited!r} is reported without status {status!r}: {hits}"
    )


def test_ambiguous_record_lists_its_candidates(unresolved_report):
    """C18/C3: `Bacteroides corrodens` is 539 and 827 — both must be recorded."""
    hits = [r for r in unresolved_report if "Bacteroides corrodens" in r.values()]
    assert hits, "the ambiguous name never reached the unresolved report"
    blob = " ".join(v for r in hits for v in r.values() if v)
    assert "539" in blob and "827" in blob, (
        f"the ambiguous record does not name its candidates: {hits}"
    )


def test_unresolved_taxa_are_still_joined_to_their_signature(graph):
    """C18: an unresolved taxon that loses its signature link is a drop with extra steps."""
    assert (
        count(
            graph,
            "MATCH (u:UnresolvedTaxon)-[:REPORTED_BY]->(:Signature) RETURN count(*) AS n",
        )
        == UNRESOLVED_RECORDS
    )


def test_empty_signature_row_exists_but_reports_nothing(graph):
    """C18: `bsdb:19533811/2/NA` names no taxa. It is a filter, not a hole.

    621 rows of the real dump are like it.
    """
    assert (
        count(
            graph,
            "MATCH (s:Signature) WHERE s.signature_id = 'bsdb:19533811/2/NA' "
            "RETURN count(s) AS n",
        )
        == 1
    ), "the empty signature was dropped instead of recorded"
    assert (
        count(
            graph,
            "MATCH (:Taxon)-[r:REPORTED_BY]->(s:Signature) "
            "WHERE s.signature_id = 'bsdb:19533811/2/NA' RETURN count(r) AS n",
        )
        == 0
    )


def test_name_only_rows_are_resolved_not_ignored(graph):
    """C18/C4: the `name` half of the resolver must actually be used.

    `bsdb:adv-legacyname/1/1` gives `Clostridium difficile` and no NCBI id;
    `bsdb:adv-ambig/1/1` gives `Bacteroides corrodens`. A loader that reads
    only `NCBI Taxonomy IDs` drops both without a counter — and with them the
    entire C4 rename problem, which is the one the user named.
    """
    for signature_id in ("bsdb:adv-legacyname/1/1", "bsdb:adv-ambig/1/1"):
        assert (
            count(
                graph,
                f"MATCH (r)-[e:REPORTED_BY]->(s:Signature) "
                f"WHERE s.signature_id = '{signature_id}' RETURN count(e) AS n",
            )
            == 1
        ), f"{signature_id} names a taxon by name only and it was ignored"
    assert (
        count(
            graph,
            "MATCH (t:Taxon)-[:REPORTED_BY]->(s:Signature) "
            "WHERE s.signature_id = 'bsdb:adv-legacyname/1/1' "
            "AND t.tax_id = 1496 RETURN count(t) AS n",
        )
        == 1
    ), "`Clostridium difficile` did not reach Clostridioides difficile (1496)"


# --------------------------------------------------------------------------
# A5.3 — shortest path
# --------------------------------------------------------------------------


def test_shortest_path_taxon_to_disease(graph):
    """A5.3: 853 associates with Obesity directly — one hop."""
    hit = rows(
        graph,
        "MATCH p = shortestPath((t:Taxon)-[*..6]-(d:Disease)) "
        "WHERE t.tax_id = 853 AND d.condition_id = 'MONDO:0011122' "
        "RETURN length(p) AS len",
    )
    assert hit, "no path between Faecalibacterium prausnitzii and Obesity"
    assert hit[0]["len"] == 1


def test_shortest_path_between_two_co_reported_taxa(graph):
    """A5.3: 239935 and 562 are both named by `bsdb:26919743/3/2` — two hops."""
    hit = rows(
        graph,
        "MATCH p = shortestPath((a:Taxon)-[*..6]-(b:Taxon)) "
        "WHERE a.tax_id = 239935 AND b.tax_id = 562 RETURN length(p) AS len",
    )
    assert hit, "no path between Akkermansia muciniphila and Escherichia coli"
    assert hit[0]["len"] == 2


def test_taxon_lineage_is_walkable_to_root(graph):
    """C8: HAS_PARENT is `ancestry`, walked with `*1..`, not a stored closure."""
    hit = rows(
        graph,
        "MATCH p = (t:Taxon)-[:HAS_PARENT*1..]->(r:Taxon) "
        "WHERE t.tax_id = 562 AND r.tax_id = 1 RETURN length(p) AS len",
    )
    assert hit, "Escherichia coli does not reach root through HAS_PARENT"
    # 562 -> 561 -> 543 -> 91347 -> 1236 -> 1224 -> 3379134 -> 2 -> 131567 -> 1
    assert hit[0]["len"] == 9


# --------------------------------------------------------------------------
# C21.1 / C21.2 — the reconciliation flags reach the graph
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tax_id, placeholder",
    [
        (77133, True),  # uncultured bacterium
        (29523, True),  # Bacteroides sp.
        (1512, True),  # [Clostridium] symbiosum
        (2500537, True),  # Candidatus Cibiobacter qucibialis
        (48479, True),  # environmental samples (a lineage ancestor)
        (562, False),
        (1496, False),
        (853, False),
    ],
)
def test_placeholder_taxa_are_excludable_with_one_clause(graph, tax_id, placeholder):
    """C9/C21.1: `WHERE NOT t.placeholder`, not a LIKE over the name."""
    hit = rows(
        graph, f"MATCH (t:Taxon) WHERE t.tax_id = {tax_id} RETURN t.placeholder AS p"
    )
    assert hit, f"{tax_id} is not in the graph at all"
    assert hit[0]["p"] is placeholder


def test_placeholder_is_a_boolean_not_a_string(graph):
    """A string `"true"` makes `WHERE NOT t.placeholder` silently wrong."""
    value = rows(
        graph, "MATCH (t:Taxon) WHERE t.tax_id = 77133 RETURN t.placeholder AS p"
    )[0]["p"]
    assert isinstance(value, bool)


def test_authority_stripped_matches_are_countable_on_the_edge(graph):
    """C21.2: `bsdb:adv-legacyname/1/1` names `Clostridium difficile`, which
    exists in names.dmp only in authority-decorated form."""
    hit = rows(
        graph,
        "MATCH ()-[r:REPORTED_BY]->(s:Signature) "
        "WHERE s.signature_id = 'bsdb:adv-legacyname/1/1' "
        "RETURN r.resolution_normalized AS n, r.resolution_status AS status",
    )
    assert hit and hit[0]["n"] is True
    assert hit[0]["status"] == "synonym"
    assert (
        count(
            graph,
            "MATCH ()-[r:REPORTED_BY]->() WHERE r.resolution_normalized "
            "RETURN count(r) AS n",
        )
        == 1
    ), "exactly one fixture mention needed authority stripping"


# --------------------------------------------------------------------------
# C14 / schema survey §5(a) — the MONDO disease hub and the condition ledger
# --------------------------------------------------------------------------


def test_a_live_mondo_id_keys_its_own_disease_node(graph):
    hit = rows(
        graph,
        "MATCH (d:Disease) WHERE d.condition_id = 'MONDO:0011122' "
        "RETURN d.mondo_id AS mondo, d.mondo_label AS mondo_label, "
        "d.source_id AS source, d.source_vocabulary AS vocab, "
        "d.source_condition AS verbatim, d.label AS label",
    )
    assert hit, "MONDO:0011122 is not in the graph"
    assert hit[0]["mondo"] == "MONDO:0011122"
    # MONDO's own name, not BugSigDB's spelling — the source string is kept
    # beside it rather than overwriting it.
    assert hit[0]["mondo_label"] == "obesity disorder"
    assert hit[0]["label"] == "obesity disorder"
    assert hit[0]["verbatim"] == "Obesity"
    assert hit[0]["source"] == "MONDO:0011122"
    assert hit[0]["vocab"] == "MONDO"


def test_terms_with_no_mondo_equivalence_keep_their_own_curie(graph):
    """None of BugSigDB's 394 EFO ids appears as a `MONDO:equivalentTo` xref in
    the 2026-09-01 release — measured, not assumed. They keep their own key and
    say so with a null `mondo_id`, rather than being merged by label."""
    hit = rows(
        graph,
        "MATCH (d:Disease) WHERE d.condition_id = 'EFO:0000246' "
        "RETURN d.mondo_id AS mondo, d.source_vocabulary AS vocab, "
        "d.source_condition AS verbatim",
    )
    assert hit and hit[0]["mondo"] is None
    assert hit[0]["vocab"] == "EFO"
    assert hit[0]["verbatim"] == "Age"
    without = 0
    for label in ("Disease", "Phenotype", "Exposure"):
        without += count(
            graph,
            f"MATCH (d:{label}) WHERE d.mondo_id IS NULL RETURN count(d) AS n",
        )
    assert without == CONDITIONS_WITHOUT_MONDO


def test_a_comma_inside_a_condition_label_does_not_mispair(graph):
    """C14: `bsdb:adv-condcomma/1/1` is `MONDO:0025082` with condition
    `Helminthiasis, animal` — one id, two comma-separated fragments.

    A positional zip pairs the id with `Helminthiasis` and drops `animal`. All
    42 mismatched-count rows of the real dump are this shape.
    """
    hit = rows(
        graph,
        "MATCH (s:Signature)-[:IN_CONDITION]->(d:Disease) "
        "WHERE s.signature_id = 'bsdb:adv-condcomma/1/1' "
        "RETURN d.condition_id AS id, d.source_condition AS verbatim, "
        "d.mondo_label AS mondo_label",
    )
    assert len(hit) == 1, f"the comma-in-label row produced {len(hit)} conditions"
    assert hit[0]["id"] == "MONDO:0025082"
    assert hit[0]["verbatim"] == "Helminthiasis, animal"
    assert hit[0]["mondo_label"] == "helminthiasis, animal"


def test_every_condition_mention_is_accounted_for(graph, condition_ledger):
    """C18, for the condition column: typed node links + ledger rows == the
    condition mentions the 43 rows carry."""
    linked = count(
        graph,
        "MATCH (:Signature)-[r:IN_CONDITION]->() RETURN count(r) AS n",
    )
    mentions = 0
    for row in read_bugsigdb():
        cell = row["EFO ID"]
        if cell and cell != "NA":
            mentions += len([c for c in cell.replace(";", ",").split(",") if c.strip()])
    assert linked + len(condition_ledger) == mentions


def test_association_edges_never_point_at_an_untyped_condition(graph):
    """Every association edge's target is one of the three condition types."""
    got = {
        r["t"]: r["n"]
        for r in rows(
            graph,
            f"MATCH (:Taxon)-[r:{ANY_ASSOCIATION}]->(c) "
            f"RETURN labels(c)[0] AS t, count(r) AS n",
        )
    }
    assert got == {"Disease": 55, "Phenotype": 3, "Exposure": 14}
    assert sum(got.values()) == ASSOCIATION_EDGES

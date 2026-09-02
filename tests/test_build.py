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

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import BUGSIGDB_MINI, TAXDUMP_MINI, read_bugsigdb

kglite = pytest.importorskip("kglite")
pytest.importorskip(
    "microbiomekg.reconcile",
    reason="microbiomekg.reconcile is not implemented — the build cannot resolve taxa",
)
pytest.importorskip(
    "microbiomekg.ontology",
    reason="microbiomekg.ontology is not implemented — the build has no ontology to gate on",
)

from microbiomekg.ontology import EVIDENCE_CONTRACT  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "blueprint.json"
PREP_BUGSIGDB = ROOT / "scripts" / "prep_bugsigdb.py"
PREP_TAXONOMY = ROOT / "scripts" / "prep_taxonomy.py"

for _needed in (BLUEPRINT, PREP_BUGSIGDB, PREP_TAXONOMY):
    if not _needed.is_file():
        pytest.skip(f"{_needed.relative_to(ROOT)} does not exist yet", allow_module_level=True)


# --------------------------------------------------------------------------
# Golden values. See the module docstring for how they were derived.
# --------------------------------------------------------------------------

INPUT_ROWS = 42                 # 34 real BugSigDB rows + 8 adversarial

NODE_COUNTS = {
    "Signature": 42,            # one per input row; BSDB IDs are unique
    "Study": 38,                # distinct BugSigDB Study ids
    "Paper": 33,                # distinct PMIDs; 5 rows have none
    "Disease": 20,              # distinct ontology terms in the `EFO ID` column
    "BodySite": 9,              # distinct UBERON ids
    "Taxon": 143,               # 53 cited + their lineage closure to root
    "UnresolvedTaxon": 3,       # 1009 deleted, 999999999 unknown, an ambiguous name
}

EDGE_COUNTS = {
    "HAS_PARENT": 142,          # every Taxon but root, which is its own parent
    "REPORTED_BY": 74,          # every taxon mention, resolved or not
    "ASSOCIATED_WITH": 73,      # (resolved taxon x condition term) per signature
    "IN_CONDITION": 43,
    "AT_BODY_SITE": 44,
    "PART_OF_STUDY": 42,
    "PUBLISHED_AS": 33,
}

CITED_TAXA = 53                 # taxa some signature actually named
TAXON_MENTIONS = 74             # 71 resolvable + 3 not
UNRESOLVED_RECORDS = 3

# ASSOCIATED_WITH edges missing at least one evidence property. `ontology_audit`
# counts edges, not property-instances, so this is the union.
EDGES_MISSING_EVIDENCE = 16

UNRESOLVED_REPORT = "unresolved_taxa.csv"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Run the real prep scripts over the fixture, then the real blueprint."""
    work = tmp_path_factory.mktemp("build")
    csv_dir = work / "csv"
    csv_dir.mkdir()

    def run(script, *args):
        proc = subprocess.run(
            [sys.executable, str(script), *args],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert proc.returncode == 0, f"{script.name} failed:\n{proc.stdout}\n{proc.stderr}"
        return proc

    run(
        PREP_BUGSIGDB,
        "--raw", str(BUGSIGDB_MINI),
        "--taxdump", str(TAXDUMP_MINI),
        "--out", str(csv_dir),
    )
    run(
        PREP_TAXONOMY,
        "--taxdump", str(TAXDUMP_MINI),
        "--out", str(csv_dir),
        "--scope", "cited",
        "--cited-from", str(csv_dir / "cited_taxa.csv"),
    )

    blueprint = json.loads(BLUEPRINT.read_text())
    settings = blueprint.setdefault("settings", {})
    settings["root"] = str(csv_dir)
    for key in ("output", "output_path", "output_file"):
        settings.pop(key, None)
    # Materialise the ontology from the module, not from the repo-root
    # artifact: a stale ontology.json gates the build on property names that
    # do not exist, which is a silent no-op audit (test_ontology.py has the
    # drift guard).
    ontology_ref = blueprint.get("ontology")
    if isinstance(ontology_ref, str):
        from microbiomekg.ontology import write_json

        write_json(csv_dir / Path(ontology_ref).name)
    local = csv_dir / "blueprint.test.json"
    local.write_text(json.dumps(blueprint))

    return kglite.from_blueprint(local, verbose=False, save=False), csv_dir


@pytest.fixture(scope="module")
def graph(built):
    return built[0]


@pytest.fixture(scope="module")
def csv_dir(built):
    return built[1]


@pytest.fixture(scope="module")
def unresolved_report(csv_dir):
    path = csv_dir / UNRESOLVED_REPORT
    assert path.is_file(), f"the build wrote no {UNRESOLVED_REPORT}"
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


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
        2,        # Bacteria
        131567,   # cellular organisms
        1783272,  # Bacillati
        1224,     # Pseudomonadota
        91347,    # Enterobacterales
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
        count(graph, f"MATCH (t:Taxon) WHERE t.tax_id = {old} RETURN count(t) AS n") == 0
    ), f"the retired id {old} became a node"
    assert (
        count(graph, f"MATCH (t:Taxon) WHERE t.tax_id = {new} RETURN count(t) AS n") == 1
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
        count(graph, f"MATCH (t:Taxon) WHERE t.tax_id = {cited} RETURN count(t) AS n") == 0
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
        "WHERE t.tax_id = 853 AND d.disease_id = 'MONDO:0011122' "
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
            "WHERE t.tax_id = 1598 AND d.disease_id = 'MONDO:0011122' "
            "RETURN r.signature_id AS sig",
        )
    )
    assert sigs == [
        "bsdb:23459324/3/2",
        "bsdb:23459324/4/1",
        "bsdb:23459324/6/1",
    ], "the three signatures were collapsed into one edge"


def test_conflicting_directions_survive_as_separate_edges(graph):
    """C12: 1386 is increased on `bsdb:27026576/1/1`, decreased on `/3/2`."""
    got = {
        h["sig"]: h["direction"]
        for h in rows(
            graph,
            "MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease) "
            "WHERE t.tax_id = 1386 AND d.disease_id = 'HP:0002745' "
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


def test_condition_terms_keep_their_source_ontology(graph):
    """C14: the `EFO ID` column carries EFO, MONDO, CHEBI, EXO, GSSO, HP, NCBITAXON."""
    got = {
        r["p"]: r["n"]
        for r in rows(
            graph,
            "MATCH (d:Disease) RETURN split(d.disease_id, ':')[0] AS p, count(d) AS n",
        )
    }
    assert got == {
        "EFO": 9,
        "MONDO": 5,
        "CHEBI": 2,
        "EXO": 1,
        "GSSO": 1,
        "HP": 1,
        "NCBITAXON": 1,
    }


def test_non_disease_terms_are_distinguishable(graph):
    """C14: `NCBITAXON:568703` is *Lacticaseibacillus rhamnosus* GG, an exposure.

    A query for "diseases" must be able to exclude it without string-matching
    the label, so the term's source ontology has to be a property.
    """
    hit = rows(
        graph,
        "MATCH (d:Disease) WHERE d.disease_id = 'NCBITAXON:568703' "
        "RETURN d.ontology AS ontology, d.label AS label",
    )
    assert hit, "the NCBITAXON condition is missing entirely"
    assert hit[0]["ontology"] == "NCBITAXON"
    assert (
        count(
            graph,
            "MATCH (d:Disease) WHERE d.ontology IN ['MONDO','EFO'] RETURN count(d) AS n",
        )
        == 14
    ), "the disease-ish terms are 9 EFO + 5 MONDO"


def test_two_colorectal_terms_stay_distinct(graph):
    """C14: MONDO:0005575 (cancer) and MONDO:0024331 (carcinoma) are not one term."""
    got = {
        r["d"]
        for r in rows(
            graph,
            "MATCH (d:Disease) WHERE d.disease_id IN "
            "['MONDO:0005575','MONDO:0024331'] RETURN d.disease_id AS d",
        )
    }
    assert got == {"MONDO:0005575", "MONDO:0024331"}


def test_multi_condition_row_links_to_both_terms(graph):
    """C14: `bsdb:23349750/1/2` is `EFO:0001799,EXO:0000114` — a set, not a zip."""
    got = {
        r["d"]
        for r in rows(
            graph,
            "MATCH (s:Signature)-[:IN_CONDITION]->(d:Disease) "
            "WHERE s.signature_id = 'bsdb:23349750/1/2' RETURN d.disease_id AS d",
        )
    }
    assert got == {"EFO:0001799", "EXO:0000114"}


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
    value = rows(graph, "MATCH (t:Taxon) WHERE t.tax_id = 562 RETURN t.tax_id AS v")[0]["v"]
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
    rule = audit.get("ASSOCIATED_WITH.required_properties")
    assert rule is not None, (
        "the association relationship declares no required_properties — "
        "the evidence contract is then unmeasurable"
    )
    assert rule["total"] == EDGE_COUNTS["ASSOCIATED_WITH"]
    assert rule["violations"] == EDGES_MISSING_EVIDENCE
    assert rule["severity"] == "warn", (
        "an upstream-data-reality rule at `error` refuses to build the real export"
    )


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
        ("evidence_level", 0),   # always derived, never absent
        ("source", 0),
        ("signature_id", 0),
    ],
)
def test_per_field_evidence_gap_census(graph, prop, missing):
    """C17/A1: "what fraction of edges lack each evidence field" is the ask.

    `ontology_audit()` gives the edge count; only this query gives the
    per-field breakdown, and A1 asks for the per-field number.
    """
    got = count(
        graph,
        f"MATCH ()-[r:ASSOCIATED_WITH]->() WHERE r.{prop} IS NULL RETURN count(r) AS n",
    )
    assert got == missing, f"{prop}: {got} edges lack it, expected {missing}"


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
def test_adversarial_rows_are_in_the_unresolved_report(unresolved_report, cited, status):
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
        "WHERE t.tax_id = 853 AND d.disease_id = 'MONDO:0011122' "
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
        (77133, True),    # uncultured bacterium
        (29523, True),    # Bacteroides sp.
        (1512, True),     # [Clostridium] symbiosum
        (2500537, True),  # Candidatus Cibiobacter qucibialis
        (48479, True),    # environmental samples (a lineage ancestor)
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

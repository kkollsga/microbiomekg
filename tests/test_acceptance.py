"""Every ``answerable-now`` D-query, run against the real built graph.

``docs/usecases-and-pitfalls.md`` Part D is the user contract: twenty queries,
each with a status and, for the ones the graph claims to answer, a *golden
check* — a measured number the build must reproduce. This module runs those
queries verbatim and asserts those numbers. A query that returns rows is not
evidence: D2 returned one row instead of forty when the junction loader
deduplicated parallel edges, and every number below exists because a plausible
non-empty answer was wrong.

Unlike ``tests/test_build.py``, which builds a 43-row fixture, this module
needs the **real** ``data/csv/`` — the goldens are measurements of the full
BugSigDB dump. It skips, naming the command that produces them, when those
CSVs are not on this machine.

The goldens are re-measured whenever a source lands: they are properties of the
loaded data, not of the code, and a new source moving them is the expected
outcome, not a regression. Each block says which build it was measured on.
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path

import pytest

kglite = pytest.importorskip("kglite")

ROOT = Path(__file__).resolve().parents[1]
CSV_DIR = ROOT / "data" / "csv"
BLUEPRINT = ROOT / "blueprint.json"

#: Files without which there is nothing to assert against.
REQUIRED_CSVS = ("signature.csv", "taxon.csv", "taxon_disease.csv", "disease.csv")

#: The sources these goldens were measured over. A build missing one of them is
#: not a failure of this module — it is a different build — so the fixture
#: skips rather than reporting a wrong number as a regression.
REQUIRED_SOURCES = frozenset({"bugsigdb", "gutmdisorder"})

#: Measured 2026-09-03 on the full build: NCBI ``new_taxdump`` 2026-09-02 +
#: BugSigDB ``full_dump`` 2026-09-02 + gutMDisorder v1 (2020, Wayback),
#: ``--scope microbial``. Each is quoted in Part D as that query's golden check.
#: The numbers that moved when gutMDisorder landed are marked; the ones that did
#: not are marked too, because "unchanged" is also a measurement.
GOLDEN = {
    # D2 — Fusobacterium nucleatum (851) x colorectal cancer (MONDO:0005575).
    # Unchanged by the second source: gutMDisorder curates no F. nucleatum
    # result for colorectal cancer at all.
    "d2_edges": 40,
    "d2_studies": 21,
    "d2_increased": 39,
    "d2_dissenting_record": "bsdb:41270896/1/2",
    # D3 — taxa reported in more than one condition (was 3,799 of 7,718)
    "d3_multi_condition_taxa": 3821,
    "d3_taxa_with_associations": 7753,
    # D9 — the 16S share of the evidence (was 57,391 of 103,461)
    "d9_association_edges": 105097,
    "d9_observational_16S": 58595,
    # D15 — the headline audit number (was 14,349 of 103,461 = 13.87%). It rose
    # because every gutMDisorder edge is missing three contract fields: the
    # source records no study design, and its association rows have no link to
    # a sample arm, so there are no per-association group sizes either.
    "d15_rule": "ASSOCIATED_WITH.required_properties",
    "d15_violations": 15985,
    "d15_total": 105097,
    # D17 — disagreement and single-cohort support (was 8,114 and 46,809 of
    # 55,445)
    "d17_pairs": 56124,
    "d17_direction_conflict": 8238,
    "d17_single_cohort": 47232,
    # D4 — the intervention leg, which needed gutMDisorder and now exists
    "d4_intervention_edges": 1380,
    "d4_interventions": 220,
    # D11 — the confounder columns, and G7
    "d11_signatures": 14846,
    "d11_matched_on": 2304,
    "d11_confounders": 1958,
    "d11_antibiotics_exclusion": 6485,
    "d11_t2d_signatures": 180,
    "d11_t2d_confounders": 58,
    "d11_t2d_matched_on": 42,
}

#: D14's standing fixture: the four genera BugSigDB itself names as reported in
#: more than 100 signatures, with the two families that interleave with them.
D14_TOP_TAXA = {
    "Bacteroides": 1150,
    "Streptococcus": 1123,
    "Prevotella": 1063,
    "Lachnospiraceae": 1024,
    "Lactobacillus": 938,
    "Oscillospiraceae": 875,
}


@pytest.fixture(scope="session")
def graph():
    """The real graph, built once from ``data/csv/``.

    ``KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE`` is not optional: the junction
    loader deduplicates parallel edges from the second 100,000-row chunk
    onwards, and this graph's parallel edges *are* its independent
    observations. Without it D2 returns 1 row instead of 40 and D17's whole
    premise disappears — silently, with no warning and no error.
    """
    missing = [name for name in REQUIRED_CSVS if not (CSV_DIR / name).is_file()]
    if missing:
        pytest.skip(
            f"no built CSVs at {CSV_DIR} (missing {', '.join(missing)}) — "
            f"run `.venv/bin/python scripts/build.py --scope microbial` first"
        )
    if not BLUEPRINT.is_file():
        pytest.skip("blueprint.json does not exist yet")
    with (CSV_DIR / "taxon_disease.csv").open(encoding="utf-8", newline="") as fh:
        loaded = {row["primary_source"] for row in csv.DictReader(fh)}
    if not REQUIRED_SOURCES <= loaded:
        pytest.skip(
            f"the built CSVs carry {sorted(loaded)}; these goldens were measured "
            f"over {sorted(REQUIRED_SOURCES)} — a build that skipped a source "
            f"whose raw files are absent is a different build, not a regression"
        )

    from microbiomekg.ontology import write_json

    work = Path(tempfile.mkdtemp(prefix="acceptance-"))
    blueprint = json.loads(BLUEPRINT.read_text())
    settings = blueprint.setdefault("settings", {})
    settings["root"] = str(CSV_DIR)
    for key in ("output", "output_path", "output_file"):
        settings.pop(key, None)
    write_json(work / "ontology.json")
    blueprint["ontology"] = str(work / "ontology.json")
    (work / "blueprint.json").write_text(json.dumps(blueprint))

    os.environ["KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE"] = "1000000"
    return kglite.from_blueprint(work / "blueprint.json", verbose=False, save=False)


def rows(graph, query: str) -> list[dict]:
    return list(graph.cypher(query))


def one(graph, query: str) -> dict:
    result = rows(graph, query)
    assert result, f"query returned no rows:\n{query}"
    return result[0]


# --------------------------------------------------------------------------
# D1 — "Which published signatures does my hit list overlap?"
# --------------------------------------------------------------------------


def test_d1_hit_list_overlaps_signatures_with_their_metadata(graph):
    """The query the model was reshaped for: `Signature` is a node, so the
    taxon *set* survives and an overlap is countable. A flattened
    (Taxon)-[:ASSOCIATED_WITH]->(Disease) model destroys the set."""
    result = rows(
        graph,
        """
        UNWIND [821, 851, 1263, 40520, 239935, 33038] AS tid
        MATCH (t:Taxon {id: tid})-[:REPORTED_BY]->(s:Signature)
        WHERE s.direction = 'increased'
        MATCH (s)-[:IN_CONDITION]->(d:Disease)
        OPTIONAL MATCH (s)-[:AT_BODY_SITE]->(b:BodySite)
        WITH s, d, b, count(DISTINCT t) AS overlap
        WHERE overlap >= 2
        RETURN d.title AS condition, b.title AS body_site, s.id AS signature,
               overlap, s.n_taxa AS signature_size,
               s.sequencing_type AS assay, s.variable_region AS region,
               s.host_species AS host, s.group_0_size AS n0, s.group_1_size AS n1,
               s.pmid AS pmid, s.evidence_level AS level
        ORDER BY overlap DESC, signature_size ASC LIMIT 25
        """,
    )
    assert result, "no signature overlaps the hit list at all"
    for row in result:
        # The golden check Part D states: an overlap can never exceed the set
        # it is an overlap *with*. A larger one means the query counted the
        # same taxon twice, which is what a missing DISTINCT looks like.
        assert row["overlap"] <= row["signature_size"], row
        assert row["condition"], "a signature reached IN_CONDITION with no title"


def test_d1_signature_size_is_the_membership_the_query_reports(graph):
    """`n_taxa` is the row's taxon-mention count, and REPORTED_BY is its
    membership. They differ only where a signature named a strain *and* its
    species and both resolved to the same tax_id — a duplicate fact, not a
    second member — so the degree is never larger than the mention count."""
    result = one(
        graph,
        """
        MATCH (x)-[:REPORTED_BY]->(s:Signature)
        WITH s, count(x) AS degree
        RETURN count(*) AS signatures,
               sum(CASE WHEN degree > s.n_taxa THEN 1 ELSE 0 END) AS degree_exceeds
        """,
    )
    assert result["degree_exceeds"] == 0, result


# --------------------------------------------------------------------------
# D2 — "What is reported for taxon X in disease Y, and how strong is each?"
# --------------------------------------------------------------------------


def test_d2_one_row_per_signature_never_one_aggregated_row(graph):
    result = rows(
        graph,
        """
        MATCH (t:Taxon {id: 851})-[r:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0005575'})
        RETURN r.direction AS direction, r.evidence_level AS level,
               r.study_design AS design, r.sequencing_type AS assay,
               r.group_0_size AS n_control, r.group_1_size AS n_case,
               r.statistical_test AS test, r.significance_threshold AS alpha,
               r.mht_correction AS mht, r.pmid AS pmid,
               r.study_id AS study, r.source_record_id AS signature,
               r.knowledge_level AS knowledge_level, r.agent_type AS agent_type,
               r.primary_source AS source, r.source_licence AS licence
        ORDER BY level, study
        """,
    )
    assert len(result) == GOLDEN["d2_edges"], (
        f"expected {GOLDEN['d2_edges']} parallel edges, got {len(result)}. One row "
        f"means C13's parallel-edge collapse recurred and "
        f"KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE was not set above the row count."
    )
    assert len({r["study"] for r in result}) == GOLDEN["d2_studies"]
    increased = [r for r in result if r["direction"] == "increased"]
    decreased = [r for r in result if r["direction"] == "decreased"]
    assert len(increased) == GOLDEN["d2_increased"]
    # G4: the dissenting edge is reported, never removed and never out-voted.
    assert [r["signature"] for r in decreased] == [GOLDEN["d2_dissenting_record"]]


def test_d2_every_returned_row_carries_its_provenance(graph):
    for row in rows(
        graph,
        """
        MATCH (t:Taxon {id: 851})-[r:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0005575'})
        RETURN r.primary_source AS source, r.source_licence AS licence,
               r.knowledge_level AS knowledge_level, r.agent_type AS agent_type,
               r.source_record_id AS record
        """,
    ):
        assert row["source"], row
        # G3: the licence rides on the edge, not on the graph, which is what
        # lets a mixed-licence graph be redistributed in parts.
        assert row["licence"], row
        assert row["knowledge_level"] and row["agent_type"], row
        assert row["record"], row


# --------------------------------------------------------------------------
# D3 — "Which taxa are reported in more than one disease?"
# --------------------------------------------------------------------------


def test_d3_half_of_all_reported_taxa_are_reported_in_several_conditions(graph):
    """Duvallet et al. put 51% of genus-level associations in more than one
    disease. A build that returns a materially lower fraction is under-loaded."""
    result = one(
        graph,
        """
        MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
        WITH t, count(DISTINCT d.id) AS n_conditions
        RETURN count(t) AS taxa,
               sum(CASE WHEN n_conditions > 1 THEN 1 ELSE 0 END) AS multi
        """,
    )
    assert result["taxa"] == GOLDEN["d3_taxa_with_associations"]
    assert result["multi"] == GOLDEN["d3_multi_condition_taxa"]
    # Duvallet et al. put 51% of genus-level associations in more than one
    # disease; two sources give 49.3%, within two points, as one source did.
    assert 0.45 < result["multi"] / result["taxa"] < 0.55


def test_d3_the_ranked_form_excludes_placeholders_by_the_flag(graph):
    """G9: `uncultured bacterium` is excluded by a boolean, never by matching
    its name — the string-matching this project argues against everywhere."""
    result = rows(
        graph,
        """
        MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
        WHERE t.placeholder = false
        WITH t, count(DISTINCT d.id) AS n_conditions,
             count(DISTINCT r.study_id) AS n_studies,
             collect(DISTINCT d.title) AS conditions,
             collect(DISTINCT r.direction) AS directions
        WHERE n_conditions > 1
        RETURN t.title AS taxon, t.rank AS rank, n_conditions, n_studies,
               conditions AS reported_in, directions
        ORDER BY n_conditions DESC LIMIT 25
        """,
    )
    assert len(result) == 25
    for row in result:
        assert "uncultured" not in (row["taxon"] or "").lower()
        assert row["n_conditions"] > 1


# --------------------------------------------------------------------------
# D9 — "Show me every association where the evidence is 16S-only"
# --------------------------------------------------------------------------


def test_d9_the_16S_share_is_the_measured_majority(graph):
    """G5 depends on this query: identical V4 sequences belong to different
    species with 63% probability, so a species-level claim resting only on
    `observational-16S` edges has to say so."""
    result = one(
        graph,
        """
        MATCH (:Taxon)-[r:ASSOCIATED_WITH]->(:Disease)
        RETURN count(r) AS edges,
               sum(CASE WHEN r.evidence_level = 'observational-16S' THEN 1 ELSE 0 END)
                 AS edges_16S
        """,
    )
    assert result["edges"] == GOLDEN["d9_association_edges"]
    assert result["edges_16S"] == GOLDEN["d9_observational_16S"]


def test_d9_the_variable_region_lives_on_the_signature_not_the_edge(graph):
    result = rows(
        graph,
        """
        MATCH (t:Taxon {id: 851})-[:REPORTED_BY]->(s:Signature)-[:IN_CONDITION]->(d:Disease)
        WHERE s.sequencing_type = '16S'
        RETURN d.title AS disease, s.variable_region AS region,
               s.sequencing_platform AS platform, count(s) AS signatures
        ORDER BY signatures DESC
        """,
    )
    assert result, "no 16S signature names taxon 851"
    assert any(row["region"] for row in result), (
        "not one 16S signature carries a variable region: the column did not "
        "reach the Signature node"
    )


# --------------------------------------------------------------------------
# D14 — "Which of my taxa are just generic dysbiosis markers?"
# --------------------------------------------------------------------------


def test_d14_the_named_non_specific_genera_are_reproduced(graph):
    """BugSigDB itself names four genera as reported in more than 100
    signatures. A build that does not reproduce them is under-loaded."""
    got = {
        row["taxon"]: row["n_signatures"]
        for row in rows(
            graph,
            """
            MATCH (t:Taxon)-[:REPORTED_BY]->(s:Signature)
            WHERE t.placeholder = false
            WITH t, count(s) AS n_signatures
            RETURN t.title AS taxon, n_signatures
            ORDER BY n_signatures DESC LIMIT 6
            """,
        )
    }
    assert got == D14_TOP_TAXA


# --------------------------------------------------------------------------
# D15 — "How many association edges have no evidence level?"
# --------------------------------------------------------------------------


def test_d15_the_audit_reports_the_headline_completeness_number(graph):
    audit = {
        row["rule"]: row
        for row in rows(
            graph,
            "CALL ontology_audit() YIELD rule, severity, violations, exempted, "
            "total, pct RETURN rule, severity, violations, exempted, total, pct",
        )
    }
    rule = audit.get(GOLDEN["d15_rule"])
    assert rule is not None, f"the audit has no {GOLDEN['d15_rule']} rule"
    assert rule["severity"] == "warn"
    # A zero denominator means the rule is auditing property names nothing
    # writes (C20); a 0.00% fraction means BugSigDB's literal "NA" reached the
    # graph as a value (C17) and the gate is vacuous.
    assert rule["total"] == GOLDEN["d15_total"]
    assert rule["violations"] == GOLDEN["d15_violations"]
    assert 0 < rule["pct"] < 100


def test_d15_the_per_field_census_the_audit_rolls_up(graph):
    """C17: `edge_property_violation` names only the FIRST missing property,
    so a breakdown built from it under-counts every field but one."""
    result = rows(
        graph,
        """
        MATCH (:Taxon)-[r:ASSOCIATED_WITH]->(:Disease)
        RETURN r.primary_source AS source, count(r) AS edges,
               sum(CASE WHEN r.direction        IS NULL THEN 1 ELSE 0 END) AS no_direction,
               sum(CASE WHEN r.pmid             IS NULL THEN 1 ELSE 0 END) AS no_pmid,
               sum(CASE WHEN r.group_0_size     IS NULL THEN 1 ELSE 0 END) AS no_group0,
               sum(CASE WHEN r.group_1_size     IS NULL THEN 1 ELSE 0 END) AS no_group1,
               sum(CASE WHEN r.statistical_test IS NULL THEN 1 ELSE 0 END) AS no_test,
               sum(CASE WHEN r.evidence_level  = 'unknown'      THEN 1 ELSE 0 END)
                 AS level_unknown,
               sum(CASE WHEN r.knowledge_level = 'not_provided' THEN 1 ELSE 0 END)
                 AS kl_not_provided
        ORDER BY edges DESC
        """,
    )
    assert result, "no association edge carries a primary_source"
    assert sum(row["edges"] for row in result) == GOLDEN["d9_association_edges"]
    for row in result:
        assert row["source"], "an edge reached the graph with no primary_source (G3)"
        # G8: knowledge_level is written from a per-source table, never
        # defaulted. `not_provided` is legal but must be a deliberate reading
        # of a source, so it may not be the whole of any source's edges.
        assert row["kl_not_provided"] < row["edges"], row
        # `evidence_level` is never absent — the derivation returns the string
        # "unknown" — so these edges carry a level that means nothing and no
        # required-property check can see them. That is deliberate.
        assert row["level_unknown"] < row["edges"], row


# --------------------------------------------------------------------------
# D16 — shortest path (A5.3)
# --------------------------------------------------------------------------


def test_d16_shortest_path_is_one_hop_where_a_direct_edge_exists(graph):
    result = one(
        graph,
        """
        MATCH p = shortestPath((t:Taxon {id: 853})-[*..4]-(d:Disease {id: 'MONDO:0005011'}))
        RETURN length(p) AS hops,
               [n IN nodes(p) | labels(n)[0]] AS types,
               [n IN nodes(p) | n.title] AS names
        """,
    )
    assert result["hops"] == 1, "the flattened edge is not doing its job"
    assert result["types"] == ["Taxon", "Disease"]


def test_d16_the_evidence_path_is_asked_for_explicitly(graph):
    """A shortest path is a navigation aid, never evidence (G10). The walk
    that *is* evidence is three hops and has to be asked for."""
    result = rows(
        graph,
        """
        MATCH p = (t:Taxon {id: 853})-[:REPORTED_BY]->(s:Signature)
                  -[:IN_CONDITION]->(d:Disease {id: 'MONDO:0005011'})
        RETURN s.id AS signature, s.evidence_level AS level,
               s.study_design AS design, s.group_0_size AS n0,
               s.group_1_size AS n1, s.pmid AS pmid LIMIT 5
        """,
    )
    assert result, "the shortcut exists but the evidence it stands for does not"
    for row in result:
        assert row["level"], row


# --------------------------------------------------------------------------
# D17 — "Where do studies disagree, and which pairs rest on one cohort?"
# --------------------------------------------------------------------------


def test_d17_disagreement_is_reported_never_resolved(graph):
    """G4, and the query the Tierney result makes mandatory: 1 in 3 taxa show
    substantial inconsistency in association sign."""
    result = one(
        graph,
        """
        MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
        WITH t, d, collect(DISTINCT r.direction) AS directions,
             count(DISTINCT r.study_id) AS n_studies, count(r) AS n_edges
        RETURN count(*) AS pairs,
               sum(CASE WHEN size(directions) > 1 THEN 1 ELSE 0 END) AS direction_conflict,
               sum(CASE WHEN n_studies = 1 THEN 1 ELSE 0 END) AS single_cohort
        """,
    )
    assert result["pairs"] == GOLDEN["d17_pairs"]
    assert result["direction_conflict"] == GOLDEN["d17_direction_conflict"]
    assert result["single_cohort"] == GOLDEN["d17_single_cohort"]


def test_d17_the_named_fixture_returns_both_directions(graph):
    """D2's pair is D17's standing fixture: 40 edges, 21 studies, both signs,
    and no majority rule applied anywhere."""
    result = one(
        graph,
        """
        MATCH (t:Taxon {id: 851})-[r:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0005575'})
        WITH collect(DISTINCT r.direction) AS directions,
             count(DISTINCT r.study_id) AS n_studies, count(r) AS n_edges
        RETURN directions, n_studies, n_edges
        """,
    )
    assert sorted(result["directions"]) == ["decreased", "increased"]
    assert result["n_edges"] == GOLDEN["d2_edges"]
    assert result["n_studies"] == GOLDEN["d2_studies"]


# --------------------------------------------------------------------------
# D11 — "Which studies for disease Y controlled for medication or antibiotics?"
# --------------------------------------------------------------------------
#
# Part D calls this "the one place the graph fails a guard it declared": G7
# says confounder control is schema, not metadata, and the three columns that
# make it so are `Matched on`, `Confounders controlled for` and `Antibiotics
# exclusion`. The research calls them the strongest argument for BugSigDB as
# the spine — no other surveyed source records confounder control at all — and
# the number behind that: 26 differentially abundant ASVs in T2D became **0**
# after matching on host variables.


def test_d11_the_confounder_columns_are_declared_by_the_blueprint(graph):
    """Declared, not merely present. The loader carries an undeclared CSV
    column into the graph anyway, so `s.confounders` answering is not evidence
    that anything guarantees it: an undeclared column has no type, is invisible
    to the ontology's `property_types` check, and disappears the day the
    loader stops being generous. G7 needs a declaration."""
    declared = json.loads(BLUEPRINT.read_text())["nodes"]["Signature"]["properties"]
    for column in ("matched_on", "confounders", "antibiotics_exclusion"):
        assert declared.get(column) == "string", (
            f"Signature.{column} is not declared in blueprint.json — "
            f"G7 is unenforceable and D11 rests on loader generosity"
        )


def test_d11_every_confounder_column_reaches_the_signature(graph):
    """All three, with their measured non-null counts. `Antibiotics exclusion`
    is the one that was never extracted at all, and it is the widest of the
    three: 6,485 of 14,846 signatures carry it."""
    result = one(
        graph,
        """
        MATCH (s:Signature)
        RETURN count(s) AS signatures,
               sum(CASE WHEN s.matched_on IS NULL THEN 0 ELSE 1 END) AS matched_on,
               sum(CASE WHEN s.confounders IS NULL THEN 0 ELSE 1 END) AS confounders,
               sum(CASE WHEN s.antibiotics_exclusion IS NULL THEN 0 ELSE 1 END)
                 AS antibiotics_exclusion
        """,
    )
    assert result["signatures"] == GOLDEN["d11_signatures"]
    assert result["matched_on"] == GOLDEN["d11_matched_on"]
    assert result["confounders"] == GOLDEN["d11_confounders"]
    assert result["antibiotics_exclusion"] == GOLDEN["d11_antibiotics_exclusion"]


def test_d11_the_breakdown_for_one_disease_is_one_query(graph):
    """G7's testable form: "which studies for disease Y controlled for
    medication" returns a non-empty breakdown, for type 2 diabetes — the
    disease the Vujkovic-Cvijin result is about."""
    result = rows(
        graph,
        """
        MATCH (s:Signature)-[:IN_CONDITION]->(d:Disease {id: 'MONDO:0005148'})
        RETURN s.id AS signature, s.pmid AS pmid, s.study_design AS design,
               s.matched_on AS matched_on,
               s.confounders AS confounders_controlled,
               s.antibiotics_exclusion AS antibiotics_exclusion,
               s.group_0_size AS n0, s.group_1_size AS n1
        ORDER BY pmid
        """,
    )
    assert len(result) == GOLDEN["d11_t2d_signatures"]
    assert sum(1 for r in result if r["confounders_controlled"]) == GOLDEN["d11_t2d_confounders"]
    assert sum(1 for r in result if r["matched_on"]) == GOLDEN["d11_t2d_matched_on"]
    assert sum(1 for r in result if r["antibiotics_exclusion"]) > 0, (
        "not one type 2 diabetes signature records an antibiotics exclusion "
        "window — the column was not extracted"
    )


# --------------------------------------------------------------------------
# D4 — "Which associations are supported by more than observational abundance?"
# --------------------------------------------------------------------------
#
# Part D filed this `partial`: the tiers were derivable from BugSigDB, but
# *interventions as a relation type* needed gutMDisorder, "the only surveyed
# source that curates them". That leg exists now.


def test_d4_the_four_stronger_tiers_are_all_populated(graph):
    result = {
        r["level"]: r["edges"]
        for r in rows(
            graph,
            """
            MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
            WHERE r.evidence_level IN ['interventional-rct', 'meta-analysis',
                                       'in-vitro', 'in-vivo-model']
            RETURN r.evidence_level AS level, count(r) AS edges
            """,
        )
    }
    assert set(result) == {"interventional-rct", "meta-analysis", "in-vitro",
                           "in-vivo-model"}
    assert all(n > 0 for n in result.values())


def test_d4_g6_sorts_animal_evidence_below_every_human_tier(graph):
    """95% of published HMA-rodent studies report phenotype transfer, and that
    rate is not evidence. The ordering is the guard."""
    result = rows(
        graph,
        """
        MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
        WHERE r.evidence_level IN ['interventional-rct', 'meta-analysis',
                                   'in-vitro', 'in-vivo-model']
        WITH d, t, r.evidence_level AS level, r.direction AS direction,
             r.host_species AS host, count(DISTINCT r.study_id) AS studies
        RETURN d.title AS disease, t.title AS taxon, level, direction, host, studies
        ORDER BY CASE level WHEN 'interventional-rct' THEN 0
                            WHEN 'meta-analysis'      THEN 1
                            WHEN 'in-vitro'           THEN 2
                            ELSE 3 END,
                 studies DESC
        LIMIT 30
        """,
    )
    assert len(result) == 30
    assert result[0]["level"] == "interventional-rct"
    assert all(row["level"] != "in-vivo-model" for row in result[:5])


def test_d4_the_intervention_leg_exists_and_is_its_own_relation(graph):
    """`(Taxon)-[:ABUNDANCE_CHANGED_BY]->(Intervention)` — what Part D named as
    D4's missing piece. It is deliberately not an ASSOCIATED_WITH: "this drug
    changed this taxon" and "this taxon is associated with this disease" are
    different claims, and collapsing them is MDAD's documented weakness."""
    result = one(
        graph,
        """
        MATCH (t:Taxon)-[r:ABUNDANCE_CHANGED_BY]->(i:Intervention)
        RETURN count(r) AS edges, count(DISTINCT i.id) AS interventions,
               collect(DISTINCT r.primary_source) AS sources
        """,
    )
    assert result["edges"] == GOLDEN["d4_intervention_edges"]
    assert result["interventions"] == GOLDEN["d4_interventions"]
    assert result["sources"] == ["gutmdisorder"]


def test_d4_a_mouse_intervention_is_still_animal_evidence(graph):
    """G6 again, at the source level: gutMDisorder's whole mouse workbook is
    `in-vivo-model` whatever its design, so the intervention edges split into
    an animal tier and a human one rather than all counting as interventional."""
    result = {
        r["level"]: r["edges"]
        for r in rows(
            graph,
            "MATCH ()-[r:ABUNDANCE_CHANGED_BY]->() "
            "RETURN r.evidence_level AS level, count(r) AS edges",
        )
    }
    assert set(result) == {"in-vivo-model", "interventional-rct"}
    assert result["in-vivo-model"] > result["interventional-rct"]


def test_d15_a_second_source_moved_the_headline_number_and_says_why(graph):
    """The audit rose from 13.87% to 15.20% when gutMDisorder landed, and the
    census says exactly which fields did it: every one of its edges is missing
    `study_design` (the source records none) and both group sizes (its
    association rows have no link to a sample arm). That is the audit working
    — a source whose gaps did not show would mean the gate had stopped
    measuring."""
    census = {
        r["source"]: r
        for r in rows(
            graph,
            """
            MATCH (:Taxon)-[r:ASSOCIATED_WITH]->(:Disease)
            RETURN r.primary_source AS source, count(r) AS edges,
                   sum(CASE WHEN r.study_design IS NULL THEN 1 ELSE 0 END) AS no_design,
                   sum(CASE WHEN r.group_0_size IS NULL THEN 1 ELSE 0 END) AS no_group0,
                   sum(CASE WHEN r.pmid IS NULL THEN 1 ELSE 0 END) AS no_pmid
            """,
        )
    }
    assert set(census) == {"bugsigdb", "gutmdisorder"}
    gut = census["gutmdisorder"]
    assert gut["no_design"] == gut["edges"]
    assert gut["no_group0"] == gut["edges"]
    # And what it *does* carry: every gutMDisorder edge has its citation.
    assert gut["no_pmid"] == 0
    assert census["bugsigdb"]["no_design"] < census["bugsigdb"]["edges"]

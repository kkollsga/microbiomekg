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


# --------------------------------------------------------------------------
# D7 — "Which AMR genes does taxon X carry, to which drug class, by which
#       mechanism, and at what call confidence?"
# --------------------------------------------------------------------------
#
# Part D filed this `pending-source: CARD`, and wrote its Cypher against the
# names `docs/research/source-formats.md`'s extraction table proposed. The
# loader that landed uses three of them differently, and each difference is a
# fact about the data rather than a preference:
#
# * `AROTerm` is `ResistanceGene`, because the node is one CARD *model* and
#   `model_type` is the thing W6 asks for; `CARRIES_DETERMINANT` is
#   `CARRIES_RESISTANCE_GENE` for the same reason.
# * `a.resistance_mechanism` is a `ResistanceMechanism` node behind
#   `VIA_MECHANISM` rather than a string property. The extraction table filed
#   the eight mechanisms as a property and the 50 drug classes as nodes;
#   they are the same shape of fact — an ARO category on a model — and a model
#   may carry two of them (`MexR` carries `antibiotic efflux` *and*
#   `antibiotic target alteration`), which a single property cannot hold.
# * **`c.hit_category` does not exist and cannot.** RGI's Perfect / Strict /
#   Loose is produced by *running* RGI against a sample; it is in no CARD
#   download. The column is not written as an empty placeholder, and
#   `taxon_specificity` carries the call-confidence information CARD does have.
#
# Measured 2026-09-03 over CARD 4.0.2 (`_timestamp` 2026-08-11) and NCBI
# `new_taxdump` 2026-09-02.

D7 = {
    "resistance_genes": 6451,
    "drug_classes": 50,
    "mechanisms": 8,
    "carriage_edges": 6415,
    "confers_edges": 13691,
    "taxa_carrying": 539,
    # E. coli, the taxon D7's own Cypher names.
    "ecoli_rows": 1535,
    "ecoli_determinants": 646,
    "ecoli_drug_classes": 31,
    "ecoli_mechanisms": 7,
    # The caveats, as counts.
    "bacteria_only": 132,        # models whose whole taxon claim is "a bacterium"
    "not_an_organism": 18,       # plasmids, a transposon, a synthetic construct
    "predicted_confers": 104,    # the 36 meta-models' drug-class edges
    "ccby_confers": 42,          # the slice `aro.obo` also states
}


def card_loaded(graph) -> bool:
    return bool(rows(graph, "MATCH (g:ResistanceGene) RETURN g LIMIT 1"))


def test_d7_the_resistance_layer_is_the_size_card_ships(graph):
    if not card_loaded(graph):
        pytest.skip("this build did not load CARD")
    result = one(
        graph,
        """
        MATCH (g:ResistanceGene) WITH count(g) AS genes
        MATCH (d:DrugClass) WITH genes, count(d) AS drug_classes
        MATCH (m:ResistanceMechanism) RETURN genes, drug_classes, count(m) AS mechanisms
        """,
    )
    assert result["genes"] == D7["resistance_genes"]
    assert result["drug_classes"] == D7["drug_classes"]
    assert result["mechanisms"] == D7["mechanisms"]
    edges = {
        r["rel"]: r["n"]
        for r in rows(
            graph,
            "MATCH ()-[r:CARRIES_RESISTANCE_GENE|CONFERS_RESISTANCE_TO]->() "
            "RETURN type(r) AS rel, count(r) AS n",
        )
    }
    assert edges["CARRIES_RESISTANCE_GENE"] == D7["carriage_edges"]
    assert edges["CONFERS_RESISTANCE_TO"] == D7["confers_edges"]


def test_d7_the_query_answers_for_a_named_taxon(graph):
    """D7's query, against the names the loader shipped (see the note above).
    Every row says which drug class, by which mechanism, from which model type
    — and what the taxon edge actually claims."""
    if not card_loaded(graph):
        pytest.skip("this build did not load CARD")
    result = rows(
        graph,
        """
        MATCH (t:Taxon {id: 562})-[c:CARRIES_RESISTANCE_GENE]->(g:ResistanceGene)
        OPTIONAL MATCH (g)-[:CONFERS_RESISTANCE_TO]->(dc:DrugClass)
        OPTIONAL MATCH (g)-[:VIA_MECHANISM]->(m:ResistanceMechanism)
        RETURN g.title AS determinant, g.id AS aro, m.title AS mechanism,
               dc.title AS drug_class, c.model_type AS model_type,
               c.sequence_derived AS from_reference_sequence,
               c.taxon_specificity AS taxon_specificity,
               c.evidence_level AS level, c.knowledge_level AS knowledge,
               c.primary_source AS source, c.source_licence AS licence
        ORDER BY drug_class, determinant
        """,
    )
    assert len(result) == D7["ecoli_rows"]
    assert len({r["aro"] for r in result}) == D7["ecoli_determinants"]
    assert len({r["drug_class"] for r in result}) == D7["ecoli_drug_classes"]
    assert len({r["mechanism"] for r in result}) == D7["ecoli_mechanisms"]
    # Every row carries its provenance and its caveat; none is null.
    assert all(r["from_reference_sequence"] is True for r in result)
    assert all(r["source"] == "card" for r in result)
    assert all(r["level"] and r["licence"] and r["model_type"] for r in result)
    # A variant model means the *mutation* confers resistance, not the gene's
    # presence — W6's "detection model type" requirement, and it is populated.
    assert "protein variant model" in {r["model_type"] for r in result}


def test_d7_the_taxon_edge_does_not_claim_the_organism_is_resistant(graph):
    """The condition D7 states in prose, asserted as counts. 132 models are
    keyed on taxid 2 (Bacteria) alone and 18 on something that is not an
    organism at all; both are kept, flagged, and excludable."""
    if not card_loaded(graph):
        pytest.skip("this build did not load CARD")
    by_scope = {
        r["scope"]: r["n"]
        for r in rows(
            graph,
            "MATCH ()-[r:CARRIES_RESISTANCE_GENE]->() "
            "RETURN r.taxon_specificity AS scope, count(r) AS n",
        )
    }
    assert by_scope["above-species"] >= D7["bacteria_only"]
    assert by_scope["not-an-organism"] == D7["not_an_organism"]
    assert sum(by_scope.values()) == D7["carriage_edges"]
    bacteria = one(
        graph,
        "MATCH (t:Taxon {id: 2})-[r:CARRIES_RESISTANCE_GENE]->() "
        "RETURN count(r) AS n, t.title AS name",
    )
    assert bacteria["n"] == D7["bacteria_only"]
    # Never CARD's editorial label for taxid 2.
    assert bacteria["name"] == "Bacteria"
    carriers = one(
        graph,
        "MATCH (t:Taxon)-[:CARRIES_RESISTANCE_GENE]->() "
        "RETURN count(DISTINCT t.id) AS taxa",
    )
    assert carriers["taxa"] == D7["taxa_carrying"]


def test_d7_the_predicted_layer_and_the_licence_are_each_one_where_clause(graph):
    """Two of D7's stated conditions. A "276k AMR links" figure sourced from
    CARD Prevalence would be `computational-predicted`; here the predicted
    layer is the 36 meta-models with no reference sequence, and dropping it is
    one clause. The licence is per edge because the download carries two, and
    the CC BY 4.0 slice is *small* — 42 of 13,691 — which is the finding, not
    a rounding error: `aro.obo` names every term but states only 37 models'
    drug classes, so D7's answer lives in the non-redistributable half."""
    if not card_loaded(graph):
        pytest.skip("this build did not load CARD")
    levels = {
        r["level"]: r["n"]
        for r in rows(
            graph,
            "MATCH ()-[r:CONFERS_RESISTANCE_TO]->() "
            "RETURN r.evidence_level AS level, count(r) AS n",
        )
    }
    assert levels["computational-predicted"] == D7["predicted_confers"]
    assert set(levels) == {"in-vitro", "computational-predicted"}
    licences = {
        r["licence"]: r["n"]
        for r in rows(
            graph,
            "MATCH ()-[r:CONFERS_RESISTANCE_TO]->() "
            "RETURN r.source_licence AS licence, count(r) AS n",
        )
    }
    assert licences == {
        "CARD-noncommercial": D7["confers_edges"] - D7["ccby_confers"],
        "CC-BY-4.0": D7["ccby_confers"],
    }


def test_d7_and_d2_meet_on_one_taxon(graph):
    """The reason CARD is in this graph rather than beside it: *E. coli* is one
    node that carries resistance determinants and is reported in diseases, so
    "what does this taxon carry, and what is it associated with?" is one query
    rather than two databases and a join by name."""
    if not card_loaded(graph):
        pytest.skip("this build did not load CARD")
    result = one(
        graph,
        """
        MATCH (t:Taxon {id: 562})
        OPTIONAL MATCH (t)-[a:ASSOCIATED_WITH]->(d:Disease)
        OPTIONAL MATCH (t)-[c:CARRIES_RESISTANCE_GENE]->(:ResistanceGene)
        RETURN t.title AS name, count(DISTINCT a) AS associations,
               count(DISTINCT d.id) AS diseases, count(DISTINCT c) AS determinants
        """,
    )
    assert result["name"] == "Escherichia coli"
    assert result["determinants"] == D7["ecoli_determinants"]
    assert result["associations"] > 0 and result["diseases"] > 0


# --------------------------------------------------------------------------
# ChEMBL — "drugs and their targets are reachable from the graph"
#
# D8 and D18 stay `pending-source: MASI`: ChEMBL carries no drug↔taxon edge at
# all, and no query below invents one. What lands here is the half of those two
# queries that ChEMBL can supply — the `Drug` and `ProteinTarget` nodes, the
# mechanism between them, and the target organisms, which is what makes "which
# approved drugs act on a bacterial protein?" answerable one join short of
# "which gut bacteria does this drug inhibit?".
# --------------------------------------------------------------------------

#: Measured 2026-09-03 on the full build: ChEMBL 37 REST subset (7,561
#: mechanism rows, 4,225 max_phase-4 molecules, 1,518 targets) against NCBI
#: `new_taxdump` 2026-09-02, `--scope microbial`.
CHEMBL_GOLDEN = {
    # 4,225 molecule rows collapse to 3,120 nodes (1,105 are a salt of another
    # approved molecule), plus 2,910 molecules a mechanism names and the
    # max_phase-4 file does not carry.
    "drugs": 6030,
    "approved": 3120,
    "withdrawn": 297,
    "targets": 1518,
    "mechanisms": 6984,          # 7,561 rows − 577 with no target
    "of_organism": 1493,         # 98.4% of targets carry a tax_id
    "target_taxa": 94,           # 125 source taxids, promoted to the species ceiling
    "non_human_mechanisms": 865,
    # The D8 slice that exists today: approved drugs acting on a protein of a
    # bacterium.
    "bacterial_drugs": 95,
    "bacterial_drugs_approved": 65,
    "bacterial_taxa": 28,
    "evidence_levels": {"in-vitro": 3153, "interventional-rct": 2059, "unknown": 1772},
    # 15 of gutMDisorder's 222 interventions carry a name ChEMBL knows.
    "is_drug": 15,
    "interventions": 222,
    "metformin": "CHEMBL:CHEMBL1431",
}


@pytest.fixture(scope="session")
def chembl_graph(graph):
    """The same graph, skipped when the build did not include ChEMBL."""
    if not (CSV_DIR / "drug.csv").is_file():
        pytest.skip(
            "no drug.csv in the built CSVs — this build did not load ChEMBL, "
            "which is a different build rather than a regression"
        )
    return graph


def test_chembl_drugs_and_their_targets_are_reachable(chembl_graph):
    """The acceptance sentence, as one query: from a drug, to the protein it
    acts on, to the organism that protein belongs to — with the evidence and
    the licence on the edge."""
    result = one(
        chembl_graph,
        """
        MATCH (d:Drug)-[r:HAS_MECHANISM]->(p:ProteinTarget)
        RETURN count(r) AS mechanisms, count(DISTINCT d) AS drugs,
               count(DISTINCT p) AS targets
        """,
    )
    assert result["mechanisms"] == CHEMBL_GOLDEN["mechanisms"]
    assert result["targets"] == CHEMBL_GOLDEN["targets"]
    nodes = one(
        chembl_graph,
        "MATCH (d:Drug) RETURN count(d) AS drugs, "
        "sum(CASE WHEN d.approved THEN 1 ELSE 0 END) AS approved, "
        "sum(CASE WHEN d.withdrawn THEN 1 ELSE 0 END) AS withdrawn",
    )
    assert nodes["drugs"] == CHEMBL_GOLDEN["drugs"]
    assert nodes["approved"] == CHEMBL_GOLDEN["approved"]
    assert nodes["withdrawn"] == CHEMBL_GOLDEN["withdrawn"]
    # A worked example, so "reachable" is not a count nobody read: vancomycin,
    # its target and that target's organism.
    walk = rows(
        chembl_graph,
        """
        MATCH (d:Drug {pref_name: 'VANCOMYCIN'})-[r:HAS_MECHANISM]->
              (p:ProteinTarget)-[:OF_ORGANISM]->(t:Taxon)
        RETURN p.title AS target, p.uniprot AS uniprot, t.title AS organism,
               r.action_type AS action, r.evidence_level AS level,
               r.source_licence AS licence
        """,
    )
    assert walk, "vancomycin reaches no target organism"
    assert all(row["licence"] == "CC-BY-SA-3.0" for row in walk)


def test_chembl_a_bacterial_target_is_the_half_of_d8_that_exists(chembl_graph):
    """865 mechanism rows point at a non-human target, and those are the only
    part of ChEMBL that touches a microbe. This is D8's "which drugs hit
    bacterial targets" — the *protein* half, which needs no MASI.

    Approved and unapproved are counted separately because they answer
    different questions: 65 of the 95 are marketed drugs, and the other 30 are
    molecules the max_phase-4 file does not carry, which a clinical reading
    must exclude and a mechanism reading must not."""
    result = one(
        chembl_graph,
        """
        MATCH (d:Drug)-[:HAS_MECHANISM]->(p:ProteinTarget)-[:OF_ORGANISM]->(t:Taxon)
        WHERE t.lineage_domain = 'Bacteria'
        RETURN count(DISTINCT d) AS drugs, count(DISTINCT t) AS taxa,
               count(DISTINCT CASE WHEN d.approved THEN d.id END) AS approved
        """,
    )
    assert result["drugs"] == CHEMBL_GOLDEN["bacterial_drugs"]
    assert result["approved"] == CHEMBL_GOLDEN["bacterial_drugs_approved"]
    assert result["taxa"] == CHEMBL_GOLDEN["bacterial_taxa"]
    organisms = one(
        chembl_graph,
        "MATCH (p:ProteinTarget)-[:OF_ORGANISM]->(t:Taxon) "
        "RETURN count(*) AS edges, count(DISTINCT t) AS taxa",
    )
    assert organisms["edges"] == CHEMBL_GOLDEN["of_organism"]
    assert organisms["taxa"] == CHEMBL_GOLDEN["target_taxa"]


def test_chembl_has_no_drug_taxon_edge_which_is_what_keeps_d8_partial(
    chembl_graph,
):
    """The gap is load-bearing and must stay visible: ChEMBL has **no**
    drug↔taxon edge, and a graph that quietly grew a `Drug`–`Taxon` shortcut
    through a shared organism would answer D8 and D18 wrongly. Within ChEMBL
    the only path from a drug to a taxon runs through the protein it acts on,
    which is a different claim. The drug→taxon leg those two queries do have
    comes from *gutMDisorder* — `ABUNDANCE_CHANGED_BY` joined through
    `IS_DRUG` — and is 15 interventions wide, which is why both are `partial`
    rather than `answerable-now`."""
    direct = one(
        chembl_graph,
        "MATCH (d:Drug)-[r]-(t:Taxon) RETURN count(r) AS edges",
    )
    assert direct["edges"] == 0
    # And metformin — D18's drug — is present and reachable, so the query is one
    # source away rather than one model change away.
    metformin = one(
        chembl_graph,
        f"MATCH (d:Drug {{id: '{CHEMBL_GOLDEN['metformin']}'}}) "
        "RETURN d.title AS name, d.atc_codes AS atc, d.first_approval AS approved",
    )
    assert metformin["name"] == "METFORMIN"
    assert metformin["atc"] == "A10BA02"


def test_chembl_an_intervention_that_names_a_drug_reaches_it(chembl_graph):
    """gutMDisorder mints `Intervention` nodes with DrugBank ids; ChEMBL's
    molecule subset carries none, so the join is an exact name match and it is
    thin on purpose — 15 of 222. The rest are ledgered rather than fuzzy
    matched, and the low rate is the measurement, not a failure."""
    result = one(
        chembl_graph,
        "MATCH (i:Intervention)-[r:IS_DRUG]->(d:Drug) "
        "RETURN count(r) AS links, count(DISTINCT d) AS drugs, "
        "collect(DISTINCT r.match_method) AS methods",
    )
    assert result["links"] == CHEMBL_GOLDEN["is_drug"]
    assert result["methods"] == ["pref_name"]
    total = one(chembl_graph, "MATCH (i:Intervention) RETURN count(i) AS n")["n"]
    assert total == CHEMBL_GOLDEN["interventions"]


def test_chembl_every_mechanism_edge_says_how_it_was_demonstrated(chembl_graph):
    """The project's thesis applied to a source with no study design at all:
    an approved label and a paper are different claims, and both are
    countable. `unknown` is 25% of the edges and is a value, not a null."""
    levels = {
        r["level"]: r["edges"]
        for r in rows(
            chembl_graph,
            "MATCH ()-[r:HAS_MECHANISM]->() "
            "RETURN r.evidence_level AS level, count(r) AS edges",
        )
    }
    assert levels == CHEMBL_GOLDEN["evidence_levels"]
    audit = {
        r["rule"]: r
        for r in rows(
            chembl_graph,
            "CALL ontology_audit() YIELD rule, severity, violations, total "
            "RETURN rule, severity, violations, total",
        )
    }
    for rule in ("HAS_MECHANISM.required_properties", "OF_ORGANISM.required_properties",
                 "IS_DRUG.required_properties"):
        assert audit[rule]["severity"] == "error"
        assert audit[rule]["violations"] == 0
        assert audit[rule]["total"] > 0, f"{rule} audits nothing"


# --------------------------------------------------------------------------
# D5 — "Which metabolites does taxon X produce, and is that measured or
#       predicted?" (and the reverse: which taxa produce metabolite M?)
# --------------------------------------------------------------------------

#: Measured 2026-09-03 over HMDB 5.0 (`hmdb_metabolites.xml`, 2021-11-17) +
#: Reactome (2026-09-02 fetch), `--scope microbial`. KEGG is **not** in these
#: numbers: it is licence-gated and off unless `scripts/build.py --with-kegg`
#: is passed, so a default build's pathway layer is Reactome alone.
METABOLITE_GOLDEN = {
    # D5 — the whole relationship. 224 microbial-origin metabolites, of which
    # 67 name no organism at all, over 957 organism terms.
    "d5_produces_edges": 578,
    "d5_producing_taxa": 272,
    "d5_metabolites_produced": 154,
    "d5_in_vitro": 543,
    "d5_computational_predicted": 35,
    # D5's stated required qualifier: the replication count, whose expected
    # value is 1. It is 1 for every pair, which is the answer, not a shortfall.
    "d5_max_records_per_pair": 1,
    # Butyric acid — the canonical "who makes butyrate" question.
    "d5_butyrate_id": "CHEBI:30772",
    "d5_butyrate_producers": 6,
    # The taxon Part D's own D5 query names. HMDB attributes nothing to it.
    "d5_akkermansia": 239935,
    # The metabolite slice and its microbial-origin subset.
    "metabolites": 7773,
    "microbial_origin": 224,
    # D13 — the pathway layer, Reactome only in a default build.
    "d13_pathways": 23604,
    "d13_hierarchy_edges": 23717,
    "d13_multi_parent_children": 388,
    "d13_in_pathway_tas": 4357,
    "d13_in_pathway_iea": 31773,
    "d13_reactome_species": 16,
}


@pytest.fixture(scope="session")
def metabolite_graph(graph):
    """The real graph, skipped unless the HMDB slice is in it.

    HMDB is fetched by hand — `hmdb.ca` answers every non-browser client with a
    Cloudflare 403 — so a machine can legitimately have the rest of the build
    and none of this. A skip that names the command is the honest outcome; a
    test that quietly passed on an empty `Metabolite` set would be the one to
    worry about.
    """
    if not rows(graph, "MATCH (m:Metabolite) RETURN m LIMIT 1"):
        pytest.skip(
            "no Metabolite nodes in data/csv — run "
            "`.venv/bin/python scripts/build.py --scope microbial` with "
            "data/raw/hmdb/hmdb_metabolites.xml present"
        )
    return graph


def test_d5_the_production_relationship_is_224_records_wide_not_thousands(
    metabolite_graph,
):
    """*Status:* still `pending-source: MiMeDB`, and this is what the HMDB half
    alone delivers. The 224 microbial-origin records are HMDB's entire yield —
    0.10% of the file — and **67 of them name no organism at all**, so the
    edge count comes from 157 records over 957 organism terms. Anyone sizing
    D5 on "HMDB has microbial metabolites" needs these numbers before the
    query, not after it."""
    result = one(
        metabolite_graph,
        """
        MATCH (t:Taxon)-[p:PRODUCES]->(m:Metabolite)
        RETURN count(p) AS edges, count(DISTINCT t.id) AS taxa,
               count(DISTINCT m.id) AS metabolites
        """,
    )
    assert result["edges"] == METABOLITE_GOLDEN["d5_produces_edges"]
    assert result["taxa"] == METABOLITE_GOLDEN["d5_producing_taxa"]
    assert result["metabolites"] == METABOLITE_GOLDEN["d5_metabolites_produced"]
    slice_ = one(
        metabolite_graph,
        "MATCH (m:Metabolite) WHERE m.source = 'hmdb' RETURN count(m) AS n, "
        "sum(CASE WHEN m.microbial_origin THEN 1 ELSE 0 END) AS microbial",
    )
    assert slice_["n"] == METABOLITE_GOLDEN["metabolites"]
    assert slice_["microbial"] == METABOLITE_GOLDEN["microbial_origin"]


def test_d5_measured_or_predicted_is_the_answers_first_column(metabolite_graph):
    """A1's whole point, on this relationship: the tier is not a footnote. It
    comes from the metabolite's `status`, which is 100% filled — `in-vitro`
    where the compound was detected or quantified, `computational-predicted`
    where it is only expected."""
    levels = {
        r["level"]: r["n"]
        for r in rows(
            metabolite_graph,
            "MATCH ()-[p:PRODUCES]->() RETURN p.evidence_level AS level, count(p) AS n",
        )
    }
    assert levels == {
        "in-vitro": METABOLITE_GOLDEN["d5_in_vitro"],
        "computational-predicted": METABOLITE_GOLDEN["d5_computational_predicted"],
    }
    # And the companion columns, which are *not* the same question: the
    # microbial-origin annotation is a curator's on all 224 whatever the
    # compound's detection status.
    assert rows(
        metabolite_graph,
        "MATCH ()-[p:PRODUCES]->() RETURN DISTINCT p.knowledge_level AS kl, "
        "p.agent_type AS agent, p.source_licence AS licence",
    ) == [{"kl": "knowledge_assertion", "agent": "manual_agent",
           "licence": "HMDB-noncommercial"}]


def test_d5_reverse_who_makes_butyrate_and_the_key_part_d_names_is_wrong(
    metabolite_graph,
):
    """**A contract statement the data made untenable.** Part D's D5 reverse
    query addresses butyrate as `CHEBI:17968`, the conjugate base. HMDB's
    butyric acid record carries `chebi_id` **30772**, the acid, and ChEBI holds
    those as two terms — so the query as written returns nothing at all, which
    looks exactly like "no source has this". Keying `Metabolite` on HMDB's own
    `chebi_id` preserves the acid/base distinction as two identities, and a
    consumer has to ask for the one HMDB curated.

    Asked with the right key it answers, and the answer is a real one: six
    named butyrate producers, every one `in-vitro`."""
    assert not rows(
        metabolite_graph, "MATCH (m:Metabolite {id: 'CHEBI:17968'}) RETURN m"
    ), "CHEBI:17968 now exists — Part D's D5 key can be un-caveated"
    producers = rows(
        metabolite_graph,
        f"""
        MATCH (t:Taxon)-[p:PRODUCES]->(m:Metabolite {{id: '{METABOLITE_GOLDEN["d5_butyrate_id"]}'}})
        WHERE t.placeholder = false
        RETURN t.title AS producer, t.rank AS rank, p.evidence_level AS level,
               count(DISTINCT p.source_record_id) AS n_records
        ORDER BY level, n_records DESC
        """,
    )
    assert len(producers) == METABOLITE_GOLDEN["d5_butyrate_producers"]
    assert {r["level"] for r in producers} == {"in-vitro"}
    assert "Faecalibacterium prausnitzii" in {r["producer"] for r in producers}


def test_d5_the_taxon_part_d_names_has_no_hmdb_production_at_all(metabolite_graph):
    """Part D's D5 example is `Taxon {id: 239935}` — *Akkermansia
    muciniphila*. HMDB attributes **no** metabolite to it, so the query returns
    zero rows on the source that is supposed to answer half of D5. That is the
    `pending-source: MiMeDB` status stated as a number rather than a label: the
    HMDB half is 578 edges over 272 organisms and this is not one of them."""
    assert not rows(
        metabolite_graph,
        f"MATCH (t:Taxon {{id: {METABOLITE_GOLDEN['d5_akkermansia']}}})"
        "-[p:PRODUCES]->(m:Metabolite) RETURN m",
    )
    # The taxon is in the graph — the gap is the source's, not the loader's.
    assert rows(
        metabolite_graph,
        f"MATCH (t:Taxon {{id: {METABOLITE_GOLDEN['d5_akkermansia']}}}) RETURN t",
    )


def test_d5_the_replication_count_is_one_and_that_is_the_answer(metabolite_graph):
    """D5's *required qualifier*: the answer carries a replication count and
    the expected value is **1**. HMDB curates one microbial-origin annotation
    per (organism, metabolite), so every pair has exactly one source record.
    A pair showing 2 would mean the loader double-counted a term — the ligature
    typo beside its correctly spelled sibling is the shape that does it."""
    result = one(
        metabolite_graph,
        """
        MATCH (t:Taxon)-[p:PRODUCES]->(m:Metabolite)
        WITH t, m, count(DISTINCT p.source_record_id) AS n
        RETURN max(n) AS max_records, count(*) AS pairs
        """,
    )
    assert result["max_records"] == METABOLITE_GOLDEN["d5_max_records_per_pair"]
    assert result["pairs"] == METABOLITE_GOLDEN["d5_produces_edges"]


# --------------------------------------------------------------------------
# D13 — "Which pathway or gene carries the production claim for taxon X →
#        metabolite M?"
# --------------------------------------------------------------------------


def test_d13_the_path_resolves_and_every_pathway_is_a_model_organisms(
    metabolite_graph,
):
    """*Status:* `pending-source: KEGG / Reactome — and misleading if
    unqualified`, and the qualifier survives the load intact. The three-hop
    path resolves, and **every pathway it reaches belongs to one of Reactome's
    16 model organisms** — there is not a gut commensal among them, so the row
    says the *metabolite* takes part in a human (or mouse, or zebrafish)
    pathway and never that the taxon runs it. `capability, not production` is
    part of the answer, not a caveat attached to it."""
    result = rows(
        metabolite_graph,
        """
        MATCH (t:Taxon)-[p:PRODUCES]->(m:Metabolite)-[i:IN_PATHWAY]->(pw:Pathway)
        WHERE pw.pathway_source = 'reactome'
        RETURN pw.species AS species, count(*) AS rows
        ORDER BY rows DESC
        """,
    )
    assert result, "no taxon reaches a pathway at all"
    assert len(result) == METABOLITE_GOLDEN["d13_reactome_species"]
    assert result[0]["species"] == "Homo sapiens"
    # The claim in one query, and it has **one exception the plan did not
    # name**: of the 272 organisms HMDB attributes a metabolite to, exactly one
    # is also a species Reactome models — *Mycobacterium tuberculosis*, which
    # Reactome carries for its infection pathways. So for that single organism
    # the row is not "capability, not production"; for every other one it is,
    # and Part D's "not a single gut commensal" survives intact, because a
    # tuberculosis bacillus is a pathogen and not a gut commensal.
    overlap = rows(
        metabolite_graph,
        """
        MATCH (t:Taxon)-[:PRODUCES]->()-[:IN_PATHWAY]->(pw:Pathway)
        WHERE pw.species = t.title
        RETURN DISTINCT t.id AS tax_id, t.title AS taxon
        """,
    )
    assert overlap == [{"tax_id": 1773, "taxon": "Mycobacterium tuberculosis"}]


def test_d13_the_evidence_code_separates_curated_from_projected(metabolite_graph):
    """87.7% of `ChEBI2Reactome.txt` is `IEA` — an orthology projection from
    human, not a read paper — and it is the cleanest `knowledge_level` signal
    in the whole increment. Without it on the edge nothing distinguishes a
    curated membership from a propagated one, and D13's answer would read as
    curated throughout."""
    counts = {
        (r["code"], r["kl"], r["level"]): r["n"]
        for r in rows(
            metabolite_graph,
            "MATCH ()-[i:IN_PATHWAY]->() WHERE i.primary_source = 'reactome' "
            "RETURN i.evidence_code AS code, i.knowledge_level AS kl, "
            "i.evidence_level AS level, count(i) AS n",
        )
    }
    assert counts == {
        ("TAS", "knowledge_assertion", "unknown"):
            METABOLITE_GOLDEN["d13_in_pathway_tas"],
        ("IEA", "logical_entailment", "computational-predicted"):
            METABOLITE_GOLDEN["d13_in_pathway_iea"],
    }


def test_d13_the_pathway_hierarchy_is_a_dag_not_a_tree(metabolite_graph):
    """388 children have more than one parent. A loader modelling this as a
    tree loses those edges silently, and D13's "which pathway carries the
    claim" then walks a subtree rather than the hierarchy it was asked for."""
    result = one(
        metabolite_graph,
        """
        MATCH (c:Pathway)-[:PART_OF_PATHWAY]->(p:Pathway)
        WITH c, count(p) AS parents
        RETURN sum(parents) AS edges,
               sum(CASE WHEN parents > 1 THEN 1 ELSE 0 END) AS multi_parent
        """,
    )
    assert result["edges"] == METABOLITE_GOLDEN["d13_hierarchy_edges"]
    assert result["multi_parent"] == METABOLITE_GOLDEN["d13_multi_parent_children"]


def test_d13_a_default_build_carries_no_kegg_pathway(metabolite_graph):
    """The licence gate, asserted where it matters rather than only in
    `tests/test_kegg.py`: KEGG is not a public database, so the graph
    `scripts/build.py` produces without `--with-kegg` must contain none of it.
    D13's KEGG half is therefore absent by default and that is the design —
    `--with-kegg` adds 587 `KEGG:map…` pathways and their edges, and changes
    nothing else."""
    assert one(
        metabolite_graph, "MATCH (p:Pathway) RETURN count(p) AS n"
    )["n"] == METABOLITE_GOLDEN["d13_pathways"]
    assert not rows(
        metabolite_graph,
        "MATCH ()-[r]->() WHERE r.source_licence = 'KEGG-restricted' RETURN r LIMIT 1",
    )


# --------------------------------------------------------------------------
# The three `partial` queries whose legs the later sources moved
#
# D10, D12 and D18 are `partial` in Part D, and Part D requires every
# `answerable-now` **and** `partial` query to have a matching test — a status
# nothing runs is a claim, not a contract. Each of these was measured on the
# same 2026-09-03 six-source build as the goldens above, and each says which
# leg works and which is still waiting on a source.
# --------------------------------------------------------------------------

PARTIAL_GOLDEN = {
    # D10 — inflammatory bowel disease (MONDO:0005265), replicated depletions.
    # The AMR and metabolite columns read 0 and [] for every row before CARD
    # and HMDB landed; they are the two numbers that say the legs exist.
    "d10_candidates": 26,
    "d10_with_amr": 4,
    "d10_with_metabolites": 7,
    "d10_candidates_any_support": 118,
    # D12 — the synonym lookup, and the rank filter that makes it an answer.
    "d12_reuteri": 1598,
    "d12_rhamnosus": 47715,
    "d12_scoring_taxa": 726,
    "d12_authority_synonym": "Lactobacillus reuteri Kandler et al. 1982",
    "d12_reuteri_signatures": 69,
    "d12_resolution_statuses": {
        "exact": 114161, "merged": 413, "promoted": 152, "deleted": 16,
    },
    # D18 — metformin as a competing explanation, through gutMDisorder's
    # intervention edge joined to ChEMBL's drug identity by IS_DRUG.
    "d18_metformin_edges": 24,
    "d18_metformin_taxa": 21,
    "d18_t2d_rows": 19,
    "d18_t2d_taxa": 17,
    # Forslund et al.'s named fixtures. gutMDisorder curates a metformin edge
    # for none of the first three, which is why D18 is not `answerable-now`.
    "d18_absent_fixtures": ("Escherichia", "Intestinibacter", "Lactobacillus"),
    "d18_present_fixture": "Bifidobacterium",
}


@pytest.fixture(scope="session")
def synonym_index(graph):
    """`text_bm25` is opt-in, so D12's query needs the index built first —
    which `scripts/build.py` does and the acceptance fixture does not."""
    graph.build_text_index("Taxon", "synonyms")
    return graph


# --------------------------------------------------------------------------
# D10 — "For disease Y, which depleted taxa are plausible probiotic candidates?"
# --------------------------------------------------------------------------


def test_d10_the_amr_and_metabolite_legs_are_populated_not_zero(graph):
    """Part D filed D10 `partial` with the AMR and metabolite columns
    returning `0` and `[]` for every row — "the honest answer, not a bug".
    CARD and HMDB changed that, and the two counts are what the status now
    rests on: the gap is coverage, not a missing relationship."""
    result = one(
        graph,
        """
        MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0005265'})
        WHERE r.direction = 'decreased' AND t.placeholder = false
        WITH t, count(DISTINCT r.study_id) AS n_studies
        WHERE n_studies >= 2
        OPTIONAL MATCH (t)-[:CARRIES_RESISTANCE_GENE]->(a:ResistanceGene)
        OPTIONAL MATCH (t)-[:PRODUCES]->(m:Metabolite)
        WITH t, count(DISTINCT a) AS amr, count(DISTINCT m) AS metabolites
        RETURN count(*) AS candidates,
               sum(CASE WHEN amr > 0 THEN 1 ELSE 0 END) AS with_amr,
               sum(CASE WHEN metabolites > 0 THEN 1 ELSE 0 END) AS with_metabolites
        """,
    )
    assert result["candidates"] == PARTIAL_GOLDEN["d10_candidates"]
    assert result["with_amr"] == PARTIAL_GOLDEN["d10_with_amr"]
    assert result["with_metabolites"] == PARTIAL_GOLDEN["d10_with_metabolites"]


def test_d10_g4_is_the_two_study_clause_not_a_nicety(graph):
    """84.2% of (taxon, condition) pairs rest on a single study and the sign of
    a single-study association flips about one time in three, so a candidate
    list without `n_studies >= 2` is a list of coin flips. The clause drops
    **92 of 118** candidates here — measured, so a build where it stopped
    filtering could not pass by returning the same list twice."""
    def candidates(minimum: int) -> int:
        return one(
            graph,
            f"""
            MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease {{id: 'MONDO:0005265'}})
            WHERE r.direction = 'decreased' AND t.placeholder = false
            WITH t, count(DISTINCT r.study_id) AS n_studies
            WHERE n_studies >= {minimum}
            RETURN count(*) AS n
            """,
        )["n"]
    assert candidates(2) == PARTIAL_GOLDEN["d10_candidates"]
    assert candidates(1) == PARTIAL_GOLDEN["d10_candidates_any_support"]


# --------------------------------------------------------------------------
# D12 — "This paper says Lactobacillus reuteri. What is the current name?"
# --------------------------------------------------------------------------


def test_d12_the_synonym_lookup_needs_the_rank_filter_to_be_an_answer(
    synonym_index,
):
    """**Part D's golden was wrong until this was run.** Unfiltered, the top
    BM25 hits for an obsolete binomial are *strains*: a strain's synonym string
    repeats the binomial in a shorter document, which is exactly what BM25
    scores higher. The species the question is about is only the top hit once
    the query says it wants a species."""
    unfiltered = rows(
        synonym_index,
        """
        MATCH (t:Taxon)
        WHERE text_bm25(t, 'synonyms', 'Lactobacillus reuteri') > 0
        RETURN t.id AS tax_id, t.rank AS rank,
               text_bm25(t, 'synonyms', 'Lactobacillus reuteri') AS score
        ORDER BY score DESC LIMIT 3
        """,
    )
    assert [r["rank"] for r in unfiltered] == ["strain"] * 3
    assert PARTIAL_GOLDEN["d12_reuteri"] not in {r["tax_id"] for r in unfiltered}

    filtered = rows(
        synonym_index,
        """
        MATCH (t:Taxon)
        WHERE text_bm25(t, 'synonyms', 'Lactobacillus reuteri') > 0
          AND t.rank = 'species'
        RETURN t.id AS tax_id, t.title AS current_name, t.rank AS rank,
               t.synonyms AS synonyms,
               text_bm25(t, 'synonyms', 'Lactobacillus reuteri') AS score
        ORDER BY score DESC LIMIT 3
        """,
    )
    assert filtered[0]["tax_id"] == PARTIAL_GOLDEN["d12_reuteri"]
    assert filtered[0]["current_name"] == "Limosilactobacillus reuteri"
    # C4, in the built graph: NCBI keeps the old binomial **only** in
    # authority-decorated form, so a resolver indexing name classes literally
    # returns `unresolved` for it and the failure looks like a data gap.
    synonyms = filtered[0]["synonyms"].split(" | ")
    assert PARTIAL_GOLDEN["d12_authority_synonym"] in synonyms
    assert "Lactobacillus reuteri" not in synonyms
    # And the rank filter is load-bearing rather than tidy: 726 taxa score
    # above zero on that query.
    assert one(
        synonym_index,
        "MATCH (t:Taxon) WHERE text_bm25(t, 'synonyms', 'Lactobacillus reuteri') > 0 "
        "RETURN count(t) AS n",
    )["n"] == PARTIAL_GOLDEN["d12_scoring_taxa"]


def test_d12_the_rhamnosus_case_answers_cleanly_and_is_still_partial(
    synonym_index,
):
    """The note Part D attaches to this query: `Lactobacillus rhamnosus`
    resolves to 47715 as a bare synonym, so the *lookup* is clean — and LPSN
    records the current name as taxonomically suspended, which a graph with one
    name field cannot express. The test asserts the half that is answerable."""
    result = rows(
        synonym_index,
        """
        MATCH (t:Taxon)
        WHERE text_bm25(t, 'synonyms', 'Lactobacillus rhamnosus') > 0
          AND t.rank = 'species'
        RETURN t.id AS tax_id, t.title AS name,
               text_bm25(t, 'synonyms', 'Lactobacillus rhamnosus') AS score
        ORDER BY score DESC LIMIT 3
        """,
    )
    assert result[0]["tax_id"] == PARTIAL_GOLDEN["d12_rhamnosus"]
    assert result[0]["name"] == "Lacticaseibacillus rhamnosus"


def test_d12_the_audit_trail_records_a_resolution_that_needed_no_rescue(graph):
    """The second half of D12's golden, and it also came out other than Part D
    claimed. BugSigDB prints the **current** name, so every one of taxon 1598's
    report edges resolved `exact` with no authority stripping — and
    `resolution_normalized` is true on **no edge in the graph**. Authority
    stripping is a resolver path this corpus never exercises; asserting it here
    would be asserting a fact about `tests/test_reconcile.py`."""
    trail = rows(
        graph,
        """
        MATCH (t:Taxon {id: 1598})-[r:REPORTED_BY]->(s:Signature)
        RETURN r.reported_name AS as_printed, r.reported_tax_id AS as_given,
               r.resolution_status AS status,
               r.resolution_normalized AS needed_authority_stripping,
               r.resolution_note AS note, count(s) AS signatures
        ORDER BY as_printed
        """,
    )
    assert len(trail) == 1
    assert trail[0]["as_printed"] == "Limosilactobacillus reuteri"
    assert trail[0]["status"] == "exact"
    assert trail[0]["needed_authority_stripping"] is False
    assert trail[0]["signatures"] == PARTIAL_GOLDEN["d12_reuteri_signatures"]
    statuses = {
        r["status"]: r["n"]
        for r in rows(
            graph,
            "MATCH ()-[r:REPORTED_BY]->() "
            "RETURN r.resolution_status AS status, count(r) AS n",
        )
    }
    assert statuses == PARTIAL_GOLDEN["d12_resolution_statuses"]
    assert not rows(
        graph,
        "MATCH ()-[r:REPORTED_BY]->() WHERE r.resolution_normalized = true "
        "RETURN r LIMIT 1",
    ), "an edge now needed authority stripping — D12's golden can be restated"


# --------------------------------------------------------------------------
# D18 — the metformin confounding check
# --------------------------------------------------------------------------


def test_d18_metformin_is_offered_as_a_competing_explanation(graph):
    """What moved D18 off `pending-source`: gutMDisorder curates metformin as
    an `Intervention` and ChEMBL knows METFORMIN, so `IS_DRUG` joins them and
    the drug→taxon leg exists — for the 15 interventions that join, at least.
    17 T2D taxa can be handed their competing explanation, which is 17 more
    than a graph with no drug→taxon layer at all."""
    reach = one(
        graph,
        f"""
        MATCH (t:Taxon)-[r:ABUNDANCE_CHANGED_BY]->(i:Intervention)
              -[:IS_DRUG]->(d:Drug {{id: '{CHEMBL_GOLDEN["metformin"]}'}})
        RETURN count(r) AS edges, count(DISTINCT t.id) AS taxa,
               collect(DISTINCT r.direction) AS directions
        """,
    )
    assert reach["edges"] == PARTIAL_GOLDEN["d18_metformin_edges"]
    assert reach["taxa"] == PARTIAL_GOLDEN["d18_metformin_taxa"]
    # G4 again: the drug's effect is reported in both directions and neither
    # is resolved away.
    assert sorted(reach["directions"]) == ["decreased", "increased"]

    joined = rows(
        graph,
        f"""
        MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease {{id: 'MONDO:0005148'}})
        MATCH (t)-[a:ABUNDANCE_CHANGED_BY]->(i:Intervention)
              -[:IS_DRUG]->(drug:Drug {{id: '{CHEMBL_GOLDEN["metformin"]}'}})
        WITH t, collect(DISTINCT r.direction) AS direction_in_t2d,
             collect(DISTINCT a.direction) AS metformin_effect,
             a.evidence_level AS metformin_level, a.pmid AS metformin_pmid,
             count(DISTINCT r.study_id) AS t2d_studies
        RETURN t.title AS taxon, direction_in_t2d, t2d_studies,
               metformin_effect, metformin_level, metformin_pmid,
               'competing explanation' AS reading
        ORDER BY t2d_studies DESC
        """,
    )
    assert len(joined) == PARTIAL_GOLDEN["d18_t2d_rows"]
    assert len({r["taxon"] for r in joined}) == PARTIAL_GOLDEN["d18_t2d_taxa"]
    for row in joined:
        assert row["metformin_pmid"], row
        assert row["metformin_effect"], row


def test_d18_is_partial_because_the_named_fixtures_are_the_missing_ones(graph):
    """Forslund et al. name an *Escherichia* increase, an *Intestinibacter*
    decrease and a *Lactobacillus* increase as metformin effects rather than
    T2D signals. gutMDisorder curates a metformin edge for **none** of them —
    only *Bifidobacterium* of the named set is reachable — so the query answers
    with the taxa this corpus happens to have, and MASI's 4,001 + 7,770 typed
    pairs are still what closes it."""
    reachable = {
        r["taxon"]
        for r in rows(
            graph,
            f"""
            MATCH (t:Taxon)-[a:ABUNDANCE_CHANGED_BY]->(i:Intervention)
                  -[:IS_DRUG]->(d:Drug {{id: '{CHEMBL_GOLDEN["metformin"]}'}})
            RETURN DISTINCT t.title AS taxon
            """,
        )
    }
    assert PARTIAL_GOLDEN["d18_present_fixture"] in reachable
    assert not (set(PARTIAL_GOLDEN["d18_absent_fixtures"]) & reachable)

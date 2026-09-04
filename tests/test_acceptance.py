"""Every ``answerable-now`` D-query, run against the real built graph.

``docs/usecases-and-pitfalls.md`` Part D is the user contract: twenty queries,
each with a status and, for the ones the graph claims to answer, a *golden
check* — a measured number the build must reproduce. This module runs those
queries verbatim and asserts those numbers. A query that returns rows is not
evidence: D2 returned one row instead of forty when the junction loader
deduplicated parallel edges, and every number below exists because a plausible
non-empty answer was wrong.

Unlike ``tests/test_build.py``, which builds a 43-row fixture, this module
needs the **real** shipped graph and its build census — the goldens are
measurements of the full BugSigDB dump. It skips, naming the command that
produces them, when they are not on this machine.

The goldens are re-measured whenever a source lands: they are properties of the
loaded data, not of the code, and a new source moving them is the expected
outcome, not a regression. Each block says which build it was measured on.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

kglite = pytest.importorskip("kglite")

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "graph" / "microbiomekg.kgl"
#: What the build put in: written beside the graph by the build itself.
CENSUS = GRAPH.with_suffix(".build.json")
BLUEPRINT = ROOT / "blueprint.json"

#: Files without which there is nothing to assert against.
REQUIRED_TABLES = ("signature", "taxon", "taxon_condition", "disease")

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
    # D3 — taxa reported in more than one condition (was 3,799 of 7,718, then
    # 3,821 of 7,753; MASI's 783 associations added one taxon and one pairing)
    "d3_multi_condition_taxa": 3822,
    "d3_taxa_with_associations": 7754,
    # D9 — the 16S share of the evidence (was 57,391 of 103,461). The
    # denominator moved with MASI and the numerator did not: MASI's disease
    # export records no sequencing type, so all 783 are `unknown`.
    "d9_association_edges": 105880,
    "d9_observational_16S": 58595,
    # D15 — the headline audit number (was 14,349 of 103,461 = 13.87%). It rose
    # because every gutMDisorder edge is missing three contract fields: the
    # source records no study design, and its association rows have no link to
    # a sample arm, so there are no per-association group sizes either.
    # It rose again — 15.20% to 15.80% — when MASI landed, for the third
    # variant of the same reason: its disease export names no design, host,
    # sequencing type, statistical test or arm sizes, so all 783 are
    # violations. 15,985 + 783 = 16,768.
    #
    # And the **denominator** then grew, because the union target made
    # `ASSOCIATED_WITH` one relationship over all three condition types: the
    # rule now covers the 4,717 phenotype and 2,369 exposure edges that used to
    # be two separate rules nobody quoted. 16,768 + 293 + 485 = 17,546 of
    # 112,966 = 15.53%. The headline fell because the two absorbed rules were
    # *cleaner* than the disease one, which is the audit describing the data.
    "d15_rule": "ASSOCIATED_WITH.required_properties",
    "d15_violations": 17546,
    "d15_total": 112966,
    # The disease-only slice the earlier goldens measured, still asked of the
    # same relationship — narrowed by the target's label rather than by a
    # relationship name.
    "d15_disease_violations": 16768,
    "d15_disease_total": 105880,
    # D17 — disagreement and single-cohort support (was 8,114 and 46,809 of
    # 55,445, then 8,238 and 47,232 of 56,124)
    "d17_pairs": 56306,
    "d17_direction_conflict": 8257,
    "d17_single_cohort": 47262,
    # D4 — the four tiers Part D quotes, and the intervention leg that needed
    # gutMDisorder. The tier counts are the golden: "all four are non-empty"
    # passes on a build that lost 90% of one of them.
    "d4_tiers": {
        "in-vivo-model": 17858,
        "meta-analysis": 4297,
        "interventional-rct": 4247,
        "in-vitro": 1613,
    },
    "d4_intervention_edges": 1380,
    "d4_interventions": 220,
    "d4_intervention_taxa": 395,
    "d4_intervention_levels": {"in-vivo-model": 822, "interventional-rct": 558},
    # D15 — the rule whose whole population is one source with three missing
    # columns, quoted in Part D as 1,380 of 1,380.
    "d15_intervention_rule": "ABUNDANCE_CHANGED_BY.required_properties",
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
    """The real graph the build saved — loaded at the default chunk size.

    Deliberately not raising ``KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE``. Until
    kglite 0.16.22 the junction loader deduplicated parallel edges from the
    second 100,000-row chunk onwards, and this graph's parallel edges *are* its
    independent observations: D2 returned 1 row instead of 40 and D17's whole
    premise disappeared, silently. The override that hid it is gone, so a
    return of that defect now shows up here — and in
    ``test_every_association_row_became_an_edge`` — rather than being masked.
    """
    if not CENSUS.is_file():
        pytest.skip(
            f"no build census at {CENSUS} — "
            f"run `.venv/bin/python scripts/build.py --scope microbial` first"
        )
    census = json.loads(CENSUS.read_text(encoding="utf-8"))
    missing = [name for name in REQUIRED_TABLES if name not in census["tables"]]
    if missing:
        pytest.skip(f"the build census lacks {', '.join(missing)} — a partial build")
    if not BLUEPRINT.is_file():
        pytest.skip("blueprint.json does not exist yet")
    loaded = set(census["sources"])
    if not REQUIRED_SOURCES <= loaded:
        pytest.skip(
            f"the build loaded {sorted(loaded)}; these goldens were measured "
            f"over {sorted(REQUIRED_SOURCES)} — a build that skipped a source "
            f"whose raw files are absent is a different build, not a regression"
        )

    # The shipped graph itself, which is what the goldens describe and what
    # the MCP server serves. The build loaded it at the default chunk size
    # from the same tables the rows-to-edges family reads back below.
    if not GRAPH.is_file():
        pytest.skip(f"no graph at {GRAPH} — build it first")
    return kglite.load(str(GRAPH))


def rows(graph, query: str) -> list[dict]:
    return list(graph.cypher(query))


def one(graph, query: str) -> dict:
    result = rows(graph, query)
    assert result, f"query returned no rows:\n{query}"
    return result[0]


# --------------------------------------------------------------------------
# C13 at scale — every junction row is an edge, at the default chunk size
# --------------------------------------------------------------------------


def junction_edges() -> dict[str, list[str]]:
    """``relationship -> the junction table(s) blueprint.json loads it from``."""
    blueprint = json.loads(BLUEPRINT.read_text())
    tables: dict[str, list[str]] = {}
    for spec in blueprint.get("nodes", {}).values():
        for rel, edge in spec.get("connections", {}).get("junction_edges", {}).items():
            tables.setdefault(rel, []).append(edge["file"])
    return tables


@pytest.mark.parametrize("relationship", sorted(junction_edges()))
def test_every_junction_row_became_an_edge(graph, relationship):
    """The regression detector for C13, and the reason the override is gone.

    A junction row is an evidence record: `taxon_condition.csv` is 112,966 rows
    of deliberately parallel edges, and kglite < 0.16.22 kept only the first
    100,000-row chunk's — 7.7% of the associations gone with no warning, no
    error and a plausible-looking graph. Equality with the CSV is the check
    that cannot be satisfied by a build that quietly dropped rows, and it needs
    no re-measuring when a source lands: the goldens elsewhere pin *this*
    build's numbers, this pins the loader's contract with any build's.

    Every junction table in this graph loads 1:1 — a missing endpoint vivifies
    a stub rather than dropping the row — so the equality holds for all of
    them, not only the association tables.
    """
    census = json.loads(CENSUS.read_text(encoding="utf-8"))["tables"]
    tables = junction_edges()[relationship]
    missing = [name for name in tables if name not in census]
    if missing:
        pytest.skip(f"{relationship} is loaded from {missing}, not in this build")
    rows_in = sum(census[name] for name in tables)
    edges = one(graph, f"MATCH ()-[r:{relationship}]->() RETURN count(r) AS n")["n"]
    assert edges == rows_in, (
        f"{relationship}: {rows_in:,} rows in "
        f"{', '.join(p.name for p in tables)} became {edges:,} edges. Rows are "
        f"evidence records here; a shortfall is the kglite<0.16.22 "
        f"chunk-boundary dedupe or something like it, and this build sets no "
        f"KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE override to hide it."
    )


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
        f"means C13's parallel-edge collapse recurred — the chunk-boundary "
        f"dedupe kglite 0.16.22 fixed, which this build no longer overrides."
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
    # The companion Part D quotes beside it: a rule whose whole population is
    # one source with three missing columns reads 100%, and that is the audit
    # describing the data rather than failing.
    intervention = audit[GOLDEN["d15_intervention_rule"]]
    assert intervention["violations"] == GOLDEN["d4_intervention_edges"]
    assert intervention["total"] == GOLDEN["d4_intervention_edges"]
    # One rule, not three: the union range is what makes the headline cover
    # every association rather than the disease subset of them.
    assert [r for r in audit if r.startswith("ASSOCIATED_WITH_")] == []
    # And the disease slice is still exactly askable, by the target's label.
    disease = one(
        graph,
        "MATCH (:Taxon)-[r:ASSOCIATED_WITH]->(:Disease) RETURN count(r) AS n",
    )
    assert disease["n"] == GOLDEN["d15_disease_total"]


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
        #
        # **MASI is the exception, and it is a whole-source one.** Its disease
        # export has eleven columns and none of them is a design, a host or an
        # assay, so Part B's own definition of `unknown` covers all 783: "the
        # source records no design, host or assay from which a level can be
        # derived. Never defaulted to observational." Naming it here rather
        # than relaxing the rule is the point — a second source landing at 100%
        # `unknown` should turn this red until somebody writes down why.
        if row["source"] == "masi":
            assert row["level_unknown"] == row["edges"] == 783, row
            continue
        assert row["level_unknown"] < row["edges"], row


# --------------------------------------------------------------------------
# D16 — shortest path (A5.3)
# --------------------------------------------------------------------------


def test_d15_the_per_field_census_names_the_gap(graph):
    """The query the project's premise rests on, per field rather than per edge.

    `required_properties` reports one percentage over a fourteen-field
    contract, and a reader who takes it for "15.5% of the fields are missing"
    is wrong in both directions: an edge missing two fields is one violation,
    and a field nothing fails is invisible. `{by: 'property'}` answers both —
    it is a **census**, so its rows sum to *at least* the aggregate and never
    back to it, and it emits a zero row for a complete field.
    """
    census = {
        r["property"]: r
        for r in rows(
            graph,
            "CALL ontology_audit({by: 'property'}) "
            "YIELD rule, property, violations, total, pct "
            "WHERE rule = 'ASSOCIATED_WITH.required_properties' "
            "AND property IS NOT NULL "
            "RETURN property, violations, total, pct",
        )
    }
    from microbiomekg.ontology import EVIDENCE_CONTRACT

    assert set(census) == set(EVIDENCE_CONTRACT), (
        "the census must name every declared property, including the complete "
        f"ones: missing {sorted(set(EVIDENCE_CONTRACT) - set(census))}"
    )
    assert all(r["total"] == GOLDEN["d15_total"] for r in census.values())
    assert census["group_0_size"]["violations"] == 14837
    assert census["group_1_size"]["violations"] == 14732
    complete = {p for p, r in census.items() if r["violations"] == 0}
    assert complete == {
        "evidence_level",
        "knowledge_level",
        "agent_type",
        "primary_source",
        "source_record_id",
        "source_licence",
    }, complete

    # A census, not a partition — and the difference is not academic here:
    # the group sizes are absent together on most of the edges that lack them.
    summed = sum(r["violations"] for r in census.values())
    assert summed > GOLDEN["d15_violations"], (
        f"the per-property rows sum to {summed:,}, which is not more than the "
        f"rule's {GOLDEN['d15_violations']:,} — either nothing overlaps or this "
        f"breakdown has become a partition, and the skill says otherwise"
    )

    # And the row-level procedure carries the whole failing set, not its first
    # member, so an UNWIND over it reproduces the census exactly.
    unwound = {
        r["field"]: r["edges"]
        for r in rows(
            graph,
            "CALL edge_property_violation() YIELD relationship, properties, exempt "
            "WHERE relationship = 'ASSOCIATED_WITH' AND NOT exempt "
            "UNWIND properties AS field "
            "RETURN field, count(*) AS edges",
        )
    }
    assert unwound == {p: r["violations"] for p, r in census.items() if r["violations"]}


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
    assert (
        sum(1 for r in result if r["confounders_controlled"])
        == GOLDEN["d11_t2d_confounders"]
    )
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
    assert result == GOLDEN["d4_tiers"], (
        "Part D quotes these four counts; `all four are non-empty` would pass "
        "on a build that lost 90% of one of them"
    )


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
               count(DISTINCT t.id) AS taxa,
               collect(DISTINCT r.primary_source) AS sources
        """,
    )
    assert result["edges"] == GOLDEN["d4_intervention_edges"]
    assert result["interventions"] == GOLDEN["d4_interventions"]
    assert result["taxa"] == GOLDEN["d4_intervention_taxa"]
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
    assert result == GOLDEN["d4_intervention_levels"]
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
    assert set(census) == {"bugsigdb", "gutmdisorder", "masi"}
    gut = census["gutmdisorder"]
    assert gut["no_design"] == gut["edges"]
    assert gut["no_group0"] == gut["edges"]
    # And what it *does* carry: every gutMDisorder edge has its citation.
    assert gut["no_pmid"] == 0
    assert census["bugsigdb"]["no_design"] < census["bugsigdb"]["edges"]
    # MASI is the third source and the same shape again — 15.20% to 15.80% —
    # for a reason the census names rather than a regression: its disease
    # export is eleven columns and not one of them is a design, a host, a
    # sequencing type, a statistical test or an arm size. What it does carry is
    # the citation, on every row.
    masi = census["masi"]
    assert masi["no_design"] == masi["edges"] == 783
    assert masi["no_group0"] == masi["edges"]
    assert masi["no_pmid"] == 0


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
    "above_species": 264,  # carriage edges whose taxon is above species rank
    "bacteria_only": 132,  # models whose whole taxon claim is "a bacterium"
    "not_an_organism": 18,  # plasmids, a transposon, a synthetic construct
    "predicted_confers": 104,  # the 36 meta-models' drug-class edges
    "ccby_confers": 42,  # the slice `aro.obo` also states
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
    assert by_scope["above-species"] == D7["above_species"]
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
# ChEMBL carries no drug↔taxon edge at all, and no query below invents one —
# the direct layer came from the two published screens and, as a curated third
# opinion, from MASI. What lands here is the half of D8 and D18 that ChEMBL can
# supply — the `Drug` and `ProteinTarget` nodes, the
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
    # 6,030 ChEMBL nodes plus the 355 Prestwick library entries Maier 2018
    # mints and the 23 screened compounds Zimmermann 2019 does, which is why
    # this number keeps moving: `drug.csv` is a shared table and a further
    # source's rows are rows, not a second node type.
    "drugs": 6408,
    "chembl_drugs": 6030,
    "approved": 3120,
    "withdrawn": 297,
    "targets": 1518,
    "mechanisms": 6984,  # 7,561 rows − 577 with no target
    "of_organism": 1493,  # 98.4% of targets carry a tax_id
    "target_taxa": 94,  # 125 source taxids, promoted to the species ceiling
    "non_human_mechanisms": 865,
    # The D8 slice that exists today: approved drugs acting on a protein of a
    # bacterium.
    "bacterial_drugs": 95,
    "bacterial_drugs_approved": 65,
    "bacterial_taxa": 28,
    "evidence_levels": {"in-vitro": 3153, "interventional-rct": 2059, "unknown": 1772},
    # 15 of gutMDisorder's 222 interventions carry a name ChEMBL knows, and
    # that join is D8's second leg: a drug that changed a taxon's abundance.
    "is_drug": 15,
    "interventions": 222,
    "d8_leg2_edges": 85,
    "d8_leg2_taxa": 57,
    "metformin": "CHEMBL:CHEMBL1431",
}


@pytest.fixture(scope="session")
def chembl_graph(graph):
    """The same graph, skipped when the build did not include ChEMBL."""
    if "chembl" not in json.loads(CENSUS.read_text(encoding="utf-8"))["sources"]:
        pytest.skip(
            "this build did not load ChEMBL, which is a different build rather "
            "than a regression"
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
    # `approved` is ChEMBL's max_phase-4 claim and stays ChEMBL's: the 355
    # nodes Maier mints are all `approved = false`, because inheriting the
    # Prestwick catalogue's "approved drugs" marketing would put an unverified
    # regulatory status on them.
    by_source = {
        r["source"]: r["n"]
        for r in rows(
            chembl_graph,
            "MATCH (d:Drug) RETURN d.source AS source, count(d) AS n",
        )
    }
    assert by_source["chembl"] == CHEMBL_GOLDEN["chembl_drugs"]
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


def test_chembl_still_has_no_drug_taxon_edge_of_its_own(chembl_graph):
    """The guard, restated rather than deleted. It used to assert that
    `MATCH (d:Drug)-[r]-(t:Taxon)` returns **0**, so D8's gap could not close by
    accident. The two published screens closed it deliberately, so the zero is
    gone — but the thing the zero was protecting is not: **ChEMBL still has no
    drug↔taxon edge of its own**, and a graph that quietly grew a `Drug`–`Taxon`
    shortcut through a shared organism would answer D8 and D18 wrongly.

    So the assertion moves from "there are none" to "every one of them is a
    measurement somebody published", which is a rule that can still fail: an
    edge of any other type, or of these four from any other source, means either
    a new source landed without restating these goldens or something collapsed
    ChEMBL's two-hop `HAS_MECHANISM` path into a claim it does not make. The
    pattern is deliberately **undirected** — the two screens point opposite ways
    and both are in scope here; that they point opposite ways is asserted in
    D8's own block."""
    kinds = {
        (r["rel"], r["source"]): r["n"]
        for r in rows(
            chembl_graph,
            "MATCH (d:Drug)-[r]-(t:Taxon) "
            "RETURN type(r) AS rel, r.primary_source AS source, count(r) AS n",
        )
    }
    assert set(kinds) == {
        ("INHIBITS_GROWTH_OF", "maier2018"),
        ("DOES_NOT_INHIBIT_GROWTH_OF", "maier2018"),
        ("METABOLISES", "zimmermann2019"),
        ("DOES_NOT_METABOLISE", "zimmermann2019"),
    }, "a Drug-Taxon edge appeared that is neither published screen"
    # And metformin — D18's drug — is present and reachable, so the query is one
    # source away rather than one model change away.
    metformin = one(
        chembl_graph,
        f"MATCH (d:Drug {{id: '{CHEMBL_GOLDEN['metformin']}'}}) "
        "RETURN d.title AS name, d.atc_codes AS atc, d.first_approval AS approved",
    )
    assert metformin["name"] == "METFORMIN"
    assert metformin["atc"] == ["A10BA02"]


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
    # D8's second leg, which is what those 15 links are for: the drug that
    # changed a taxon's abundance, reachable from the drug rather than only
    # from gutMDisorder's own label.
    leg2 = one(
        chembl_graph,
        "MATCH (t:Taxon)-[r:ABUNDANCE_CHANGED_BY]->(i:Intervention)-[:IS_DRUG]->(d:Drug) "
        "RETURN count(r) AS edges, count(DISTINCT d.id) AS drugs, "
        "count(DISTINCT t.id) AS taxa",
    )
    assert leg2["edges"] == CHEMBL_GOLDEN["d8_leg2_edges"]
    assert leg2["drugs"] == CHEMBL_GOLDEN["is_drug"]
    assert leg2["taxa"] == CHEMBL_GOLDEN["d8_leg2_taxa"]


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
    for rule in (
        "HAS_MECHANISM.required_properties",
        "OF_ORGANISM.required_properties",
        "IS_DRUG.required_properties",
    ):
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
    # D5 — the whole relationship, now two sources in one table. HMDB's half is
    # unchanged (224 microbial-origin records, 67 of which name no organism at
    # all, over 957 organism terms); NJC19's export events are the rest.
    "d5_produces_edges": 3418,
    "d5_producing_taxa": 830,
    "d5_metabolites_produced": 226,
    "d5_hmdb_edges": 578,
    "d5_hmdb_taxa": 272,
    "d5_hmdb_metabolites": 154,
    "d5_njc19_edges": 2840,
    "d5_njc19_taxa": 638,
    "d5_njc19_metabolites": 99,
    "d5_in_vitro": 3383,
    "d5_computational_predicted": 35,
    # D5's stated required qualifier: the replication count. Part D says the
    # expected value is 1 and that is no longer true — see
    # test_d5_the_replication_count_is_no_longer_one_and_the_reasons_are_two.
    "d5_max_records_per_pair": 3,
    "d5_replicated_pairs": 43,
    # Butyric acid — the canonical "who makes butyrate" question.
    "d5_butyrate_id": "CHEBI:30772",
    "d5_butyrate_producers": 109,
    "d5_butyrate_producers_hmdb": 6,
    # The taxon Part D's own D5 query names. HMDB attributes nothing to it and
    # NJC19 attributes four things to it.
    "d5_akkermansia": 239935,
    "d5_akkermansia_products": 4,
    # The metabolite slice, its microbial-origin subset, and who wrote which
    # node. `microbial_origin` stays HMDB's claim and only HMDB's.
    "metabolites": 7773,
    # 8,754 while MiMeDB v1.0 was the loaded release; v2.0 (2026-09-03) adds 302
    # nodes and, as v1.0 did, no edges at all.
    "metabolites_total": 9056,
    "metabolites_by_source": {"hmdb": 7773, "mimedb": 1237, "njc19": 46},
    "microbial_origin": 224,
    # D6 — the cross-feeding query, answerable since NJC19 landed.
    "d6_consumes_edges": 4784,
    "d6_consuming_taxa": 714,
    "d6_consumed_metabolites": 205,
    "d6_degrades_edges": 387,
    "d6_degrading_taxa": 212,
    "d6_degraded_macromolecules": 17,
    "d6_negatives": 894,
    "d6_negatives_by_relation": {
        "import-negative": 720,
        "degrade-negative": 87,
        "export-negative": 87,
    },
    "d6_non_zero_mes": 96,
    "d6_acetate_id": "CHEBI:15366",
    "d6_acetate_producers": 441,
    "d6_acetate_consumers": 72,
    "d6_genus_level_edges": 2432,
    "d6_species_level_edges": 6473,
    "d6_unresolved_taxa": 15,
    # D13 — the pathway layer, Reactome only in a default build.
    "d13_pathways": 23604,
    "d13_hierarchy_edges": 23717,
    "d13_multi_parent_children": 388,
    "d13_in_pathway_tas": 4357,
    "d13_in_pathway_iea": 31773,
    "d13_reactome_species": 16,
    # The three-hop walk itself, which Part D quotes as its golden. It grew
    # 27x when NJC19's export half landed in the PRODUCES table — the walk is
    # taxon -> metabolite -> pathway and NJC19 attributes 2,840 productions to
    # 638 taxa, most of them compounds Reactome has a pathway for. The HMDB-only
    # figures are kept beside it because they are what Part D quotes and because
    # the pair is what says by how much a source moved the number.
    "d13_walk_rows": 130214,
    "d13_walk_taxa": 628,
    "d13_walk_pathways": 1125,
    "d13_walk_rows_hmdb": 4806,
    "d13_walk_taxa_hmdb": 95,
    "d13_walk_pathways_hmdb": 635,
    "d13_ecoli_rows": 1028,
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
            "no Metabolite nodes in this build — run "
            "`.venv/bin/python scripts/build.py --scope microbial` with "
            "data/raw/hmdb/hmdb_metabolites.xml present"
        )
    return graph


def test_d5_is_two_sources_in_one_table_and_the_split_is_the_answer(
    metabolite_graph,
):
    """*Status:* **`partial`**, not `pending-source` — and **not because MiMeDB
    landed.** The MiMeDB downloads carry no microbe–metabolite association at
    all (`microbiomekg/ontology/mimedb.py`), so the source that was supposed to
    answer D5 contributes zero edges to it. What moved the query is NJC19's
    export half, which was fetched for D6: 2,840 edges over 638 taxa, nearly
    five times HMDB's whole yield.

    HMDB's half is unchanged and still small for the reason it always was: 224
    microbial-origin records, 0.10% of the file, **67 of which name no organism
    at all**, so its 578 edges come from 157 records over 957 organism terms.
    Anyone sizing D5 needs the split, not the total."""
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

    per_source = {
        r["source"]: r
        for r in rows(
            metabolite_graph,
            """
            MATCH (t:Taxon)-[p:PRODUCES]->(m:Metabolite)
            RETURN p.primary_source AS source, count(p) AS edges,
                   count(DISTINCT t.id) AS taxa, count(DISTINCT m.id) AS metabolites
            """,
        )
    }
    assert set(per_source) == {"hmdb", "njc19"}, "MiMeDB must contribute no PRODUCES"
    assert per_source["hmdb"]["edges"] == METABOLITE_GOLDEN["d5_hmdb_edges"]
    assert per_source["hmdb"]["taxa"] == METABOLITE_GOLDEN["d5_hmdb_taxa"]
    assert per_source["hmdb"]["metabolites"] == METABOLITE_GOLDEN["d5_hmdb_metabolites"]
    assert per_source["njc19"]["edges"] == METABOLITE_GOLDEN["d5_njc19_edges"]
    assert per_source["njc19"]["taxa"] == METABOLITE_GOLDEN["d5_njc19_taxa"]
    assert (
        per_source["njc19"]["metabolites"] == METABOLITE_GOLDEN["d5_njc19_metabolites"]
    )

    slice_ = one(
        metabolite_graph,
        "MATCH (m:Metabolite) WHERE m.source = 'hmdb' RETURN count(m) AS n, "
        "sum(CASE WHEN m.microbial_origin THEN 1 ELSE 0 END) AS microbial",
    )
    assert slice_["n"] == METABOLITE_GOLDEN["metabolites"]
    assert slice_["microbial"] == METABOLITE_GOLDEN["microbial_origin"]


def test_d5_mimedb_contributes_metabolite_identity_and_no_production_claim(
    metabolite_graph,
):
    """**The finding that keeps D5 short of `answerable-now`.** MiMeDB was
    fetched to close D5 and its bulk downloads cannot: they are one MySQL table
    each, the metabolites dump contains zero `MMDBm` ids and the microbes dump
    zero `MMDBc` ids, and the only column in either that looks like a relation
    is a `microbes.activity` that names no compound.

    What it does contribute is compound identity for a source that has none —
    NJC19 carries no ChEBI, HMDB, KEGG or PubChem id for any of its 283
    compounds — and that is countable: 1,237 `Metabolite` nodes, none of them
    claiming microbial origin, none of them an endpoint of anything MiMeDB
    wrote.

    **v2.0 was fetched on 2026-09-03 and does not change the finding.** It adds
    1,654 records, 302 of which become nodes, three cross-reference columns and
    a `microbe_relations` integer that *counts* related microbes without naming
    one — 830,984 pairs tallied over the file, zero enumerated. The zero below
    is the same zero it was under v1.0, which is why this test asserts it
    against the release the node property names rather than against a
    filename."""
    by_source = {
        r["source"]: r["n"]
        for r in rows(
            metabolite_graph,
            "MATCH (m:Metabolite) RETURN m.source AS source, count(m) AS n",
        )
    }
    assert by_source == METABOLITE_GOLDEN["metabolites_by_source"]
    assert sum(by_source.values()) == METABOLITE_GOLDEN["metabolites_total"]
    assert not rows(
        metabolite_graph,
        "MATCH ()-[r]->() WHERE r.primary_source = 'mimedb' RETURN r LIMIT 1",
    ), "MiMeDB wrote an edge — its downloads carry no association to write one from"
    # `microbial_origin` stays HMDB's claim and only HMDB's: "an organism
    # exchanges this" and "this compound is of microbial origin" are different
    # claims, and pectin is a plant polymer.
    assert not rows(
        metabolite_graph,
        "MATCH (m:Metabolite) WHERE m.source <> 'hmdb' AND m.microbial_origin = true "
        "RETURN m LIMIT 1",
    )


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
    # `computational-predicted` is HMDB's and only HMDB's: NJC19's inclusion
    # criterion is an experimentally verified event, so a predicted NJC19 edge
    # would be a value nothing in that source could justify.
    assert {
        r["source"]
        for r in rows(
            metabolite_graph,
            "MATCH ()-[p:PRODUCES]->() WHERE p.evidence_level = 'computational-predicted' "
            "RETURN DISTINCT p.primary_source AS source",
        )
    } == {"hmdb"}
    # And the companion columns, which are *not* the same question. Both
    # sources are a curator's assertion — the microbial-origin annotation is
    # one whatever the compound's detection status — and the licences differ,
    # which is what makes a CC0-only subgraph cuttable (G3).
    assert sorted(
        rows(
            metabolite_graph,
            "MATCH ()-[p:PRODUCES]->() RETURN DISTINCT p.knowledge_level AS kl, "
            "p.agent_type AS agent, p.source_licence AS licence",
        ),
        key=lambda r: r["licence"],
    ) == [
        {"kl": "knowledge_assertion", "agent": "manual_agent", "licence": "CC0-1.0"},
        {
            "kl": "knowledge_assertion",
            "agent": "manual_agent",
            "licence": "HMDB-noncommercial",
        },
    ]


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
    # The count moved from 6 to 109 when NJC19 landed, and it moved **onto the
    # same node** only because the conjugate route reaches it: NJC19 says
    # `Butyrate`, HMDB records `Butyric acid`, and a loader that matched names
    # literally would have minted `NJC19:Butyrate` and left this query at 6
    # while 103 producers sat on a node nobody queried.
    by_source = {
        r["source"]: r["taxa"]
        for r in rows(
            metabolite_graph,
            f"""
            MATCH (t:Taxon)-[p:PRODUCES]->(m:Metabolite {{id: '{METABOLITE_GOLDEN["d5_butyrate_id"]}'}})
            WHERE t.placeholder = false
            RETURN p.primary_source AS source, count(DISTINCT t.id) AS taxa
            """,
        )
    }
    assert by_source["hmdb"] == METABOLITE_GOLDEN["d5_butyrate_producers_hmdb"]
    assert by_source["njc19"] > by_source["hmdb"]
    assert {
        r["route"]
        for r in rows(
            metabolite_graph,
            f"MATCH ()-[p:PRODUCES]->(m:Metabolite {{id: '{METABOLITE_GOLDEN['d5_butyrate_id']}'}}) "
            "WHERE p.primary_source = 'njc19' RETURN DISTINCT p.metabolite_join AS route",
        )
    } == {"conjugate"}


def test_d5_the_taxon_part_d_names_now_has_an_answer_and_it_is_not_hmdbs(
    metabolite_graph,
):
    """**A Part D statement the data overturned.** D5 recorded that
    *Akkermansia muciniphila* (239935) — the taxon its own forward query names
    — had **zero** rows, "this query's `pending-source` status as a number
    rather than a label". It has four now, and every one is NJC19's: HMDB still
    attributes nothing to it. The label was right about the gap and wrong about
    which source would close it."""
    products = rows(
        metabolite_graph,
        f"MATCH (t:Taxon {{id: {METABOLITE_GOLDEN['d5_akkermansia']}}})"
        "-[p:PRODUCES]->(m:Metabolite) "
        "RETURN m.title AS metabolite, p.primary_source AS source ORDER BY metabolite",
    )
    assert len(products) == METABOLITE_GOLDEN["d5_akkermansia_products"]
    assert {r["source"] for r in products} == {"njc19"}


def test_d5_the_replication_count_is_no_longer_one_and_the_reasons_are_two(
    metabolite_graph,
):
    """**A second Part D statement the data overturned.** D5's *required
    qualifier* said the replication count is **1** for every (taxon,
    metabolite) pair and that this was "the required qualifier answered, not a
    shortfall". With a second source in the table it reaches **3**, for two
    reasons that are both correct behaviour rather than double-counting:

    1. **HMDB and NJC19 curate the same production independently.** 29 pairs
       carry one record from each — *Faecalibacterium prausnitzii* → butyric
       acid is one — and that is exactly the cross-source replication D3 and
       D17 treat as evidence. Collapsing it would destroy the only genuine
       corroboration this relationship has ever had.
    2. **Several NJC19 species strings resolve to one taxon.**
       *Thermoanaerobacter thermohydrosulfuricus*, *T. indiensis* and *T.
       ethanolicus* are three curated rows that NCBI files under one species,
       so the promotion (G5) turns three source records into three parallel
       edges on one pair. `reported_name` keeps all three strings, which is
       what makes the collapse inspectable rather than invisible. Two taxa in
       the whole build are shaped this way.

    A pair showing more records than its distinct source strings *would* be
    double-counting; that is what this test still guards."""
    result = one(
        metabolite_graph,
        """
        MATCH (t:Taxon)-[p:PRODUCES]->(m:Metabolite)
        WITH t, m, count(DISTINCT p.source_record_id) AS n
        RETURN max(n) AS max_records, count(*) AS pairs,
               sum(CASE WHEN n > 1 THEN 1 ELSE 0 END) AS replicated
        """,
    )
    assert result["max_records"] == METABOLITE_GOLDEN["d5_max_records_per_pair"]
    assert result["replicated"] == METABOLITE_GOLDEN["d5_replicated_pairs"]
    # No pair carries more records than it carries distinct (source, organism
    # string, compound string) triples — which is what double-counting one
    # annotation spelled two ways would look like.
    assert not rows(
        metabolite_graph,
        """
        MATCH (t:Taxon)-[p:PRODUCES]->(m:Metabolite)
        WITH t, m, count(DISTINCT p.source_record_id) AS records,
             count(DISTINCT p.primary_source + '|' + p.reported_name + '|'
                   + coalesce(p.reported_compound, '')) AS claims
        WHERE records > claims
        RETURN t.title AS taxon, m.title AS metabolite LIMIT 5
        """,
    )


# --------------------------------------------------------------------------
# D6 — "Which taxa consume metabolite M?" — the cross-feeding query
# --------------------------------------------------------------------------


def test_d6_the_metabolite_exchange_score_is_no_longer_identically_zero(
    metabolite_graph,
):
    """**The query this whole increment exists for.** Marcelino et al.'s
    Metabolite Exchange Score is **MES = 2·P·C / (P + C)** — the harmonic mean
    of the number of potential producers and consumers — and it is **0 whenever
    a metabolite is only produced or only consumed**. Before NJC19 landed, C
    was zero for every metabolite in the graph, so every row of D6 returned 0.0
    and the use case was, in Part B's word, dead.

    96 metabolites now carry both. The top of the ranking is what a gut
    cross-feeding network is supposed to look like: CO2, acetate, hydrogen and
    lactate, which is the exchange currency the literature describes."""
    ranked = rows(
        metabolite_graph,
        """
        MATCH (m:Metabolite)
        OPTIONAL MATCH (p:Taxon)-[:PRODUCES]->(m) WHERE p.placeholder = false
        OPTIONAL MATCH (c:Taxon)-[:CONSUMES]->(m) WHERE c.placeholder = false
        WITH m, count(DISTINCT p) AS producers, count(DISTINCT c) AS consumers
        WHERE producers > 0 AND consumers > 0
        RETURN m.title AS metabolite, producers, consumers,
               2.0 * producers * consumers / (producers + consumers) AS mes
        ORDER BY mes DESC
        """,
    )
    assert len(ranked) == METABOLITE_GOLDEN["d6_non_zero_mes"]
    assert all(r["mes"] > 0.0 for r in ranked)
    assert {"Acetic acid", "L-Lactic acid", "Hydrogen"} <= {
        r["metabolite"] for r in ranked[:10]
    }


def test_d6_acetate_has_both_halves_which_was_the_stated_golden(metabolite_graph):
    """Part D's D6 golden check, written before the source landed: "acetate,
    the most frequently exported product (44.3% of NJC19's species), must have
    both a non-zero producer and a non-zero consumer count". It does — and it
    does so on **one** node, which is the part that was not guaranteed. HMDB
    records `Acetic acid`; NJC19 says `Acetate`; without the conjugate route
    the producers and the consumers would be on two nodes and this golden would
    read 0."""
    counts = one(
        metabolite_graph,
        f"""
        MATCH (m:Metabolite {{id: '{METABOLITE_GOLDEN["d6_acetate_id"]}'}})
        OPTIONAL MATCH (p:Taxon)-[:PRODUCES]->(m) WHERE p.placeholder = false
        OPTIONAL MATCH (c:Taxon)-[:CONSUMES]->(m) WHERE c.placeholder = false
        RETURN count(DISTINCT p) AS producers, count(DISTINCT c) AS consumers
        """,
    )
    assert counts["producers"] == METABOLITE_GOLDEN["d6_acetate_producers"]
    assert counts["consumers"] == METABOLITE_GOLDEN["d6_acetate_consumers"]
    assert {
        r["source"]
        for r in rows(
            metabolite_graph,
            f"MATCH ()-[p:PRODUCES]->(m:Metabolite {{id: '{METABOLITE_GOLDEN['d6_acetate_id']}'}}) "
            "RETURN DISTINCT p.primary_source AS source",
        )
    } == {"hmdb", "njc19"}


def test_d6_import_export_and_degrade_are_three_relationships(metabolite_graph):
    """Part D's proposed loader contract asked for
    `(Taxon)-[:PRODUCES|CONSUMES]->(Metabolite)` with `source_relation ∈
    {export, import, degrade}`. It landed as three relationship *types* rather
    than one with a discriminating property, because the blueprint's junction
    rule is one relationship per CSV per target type (docs/model.md §8) — and
    because extracellular breakdown of a polymer is a different claim about a
    community from uptake of a small molecule. `source_relation` carries the
    source's own word on every edge regardless, so the contract's filter still
    works."""
    consumes = one(
        metabolite_graph,
        "MATCH (t:Taxon)-[r:CONSUMES]->(m:Metabolite) RETURN count(r) AS edges, "
        "count(DISTINCT t.id) AS taxa, count(DISTINCT m.id) AS metabolites",
    )
    assert consumes["edges"] == METABOLITE_GOLDEN["d6_consumes_edges"]
    assert consumes["taxa"] == METABOLITE_GOLDEN["d6_consuming_taxa"]
    assert consumes["metabolites"] == METABOLITE_GOLDEN["d6_consumed_metabolites"]

    degrades = one(
        metabolite_graph,
        "MATCH (t:Taxon)-[r:DEGRADES]->(m:Metabolite) RETURN count(r) AS edges, "
        "count(DISTINCT t.id) AS taxa, count(DISTINCT m.id) AS metabolites",
    )
    assert degrades["edges"] == METABOLITE_GOLDEN["d6_degrades_edges"]
    assert degrades["taxa"] == METABOLITE_GOLDEN["d6_degrading_taxa"]
    assert degrades["metabolites"] == METABOLITE_GOLDEN["d6_degraded_macromolecules"]

    relations = {
        r["rel"]: r["n"]
        for r in rows(
            metabolite_graph,
            "MATCH ()-[r]->(:Metabolite) WHERE r.primary_source = 'njc19' "
            "RETURN r.source_relation AS rel, count(r) AS n",
        )
    }
    assert set(relations) == {
        "import",
        "export",
        "degrade",
        "import-negative",
        "export-negative",
        "degrade-negative",
    }


def test_d6_the_negatives_are_countable_and_not_reachable_as_observations(
    metabolite_graph,
):
    """Part D's D6 contract: "the **912 negative associations as their own edge
    type** — explicit negatives are rare enough in this field to be worth their
    own shape". 894 of the 912 survive; the other 18 sit on rows whose organism
    is one of NJC19's six host cell types or a taxon NCBI has renamed, and they
    are ledger rows in `unresolved_exchange.csv` rather than losses.

    The shape is the point. A refutation stored as a property of a `CONSUMES`
    edge would be counted as an observation by every query that did not know to
    exclude it — and nothing in the query text would say so."""
    total = one(
        metabolite_graph,
        "MATCH (t:Taxon)-[r:NO_EXCHANGE_WITH]->(m:Metabolite) RETURN count(r) AS n",
    )["n"]
    assert total == METABOLITE_GOLDEN["d6_negatives"]
    by_relation = {
        r["rel"]: r["n"]
        for r in rows(
            metabolite_graph,
            "MATCH ()-[r:NO_EXCHANGE_WITH]->() "
            "RETURN r.source_relation AS rel, count(r) AS n",
        )
    }
    assert by_relation == METABOLITE_GOLDEN["d6_negatives_by_relation"]
    # And no positive relationship carries a negated source_relation.
    for rel in ("PRODUCES", "CONSUMES", "DEGRADES"):
        assert not rows(
            metabolite_graph,
            f"MATCH ()-[r:{rel}]->() WHERE r.source_relation ENDS WITH '-negative' "
            "RETURN r LIMIT 1",
        )


def test_d6_a_species_claim_on_genus_level_literature_is_marked(metabolite_graph):
    """Guard G5 on this relationship. NJC19 files every row against a species,
    and **26.6% of them stand on nothing but `(G)`-marked references** — a
    genus-level reading presented at species level. The flag is on every edge,
    so the two populations are one `WHERE` clause apart rather than
    indistinguishable."""
    split = {
        r["g"]: r["n"]
        for r in rows(
            metabolite_graph,
            "MATCH ()-[r]->(:Metabolite) WHERE r.primary_source = 'njc19' "
            "RETURN r.genus_level_evidence AS g, count(r) AS n",
        )
    }
    assert split[True] == METABOLITE_GOLDEN["d6_genus_level_edges"]
    assert split[False] == METABOLITE_GOLDEN["d6_species_level_edges"]
    assert not rows(
        metabolite_graph,
        "MATCH ()-[r]->(:Metabolite) WHERE r.primary_source = 'njc19' "
        "AND r.genus_level_evidence IS NULL RETURN r LIMIT 1",
    ), "an unmarked edge is one a G5-aware query cannot see"


def test_d6_the_organisms_it_could_not_resolve_are_tombstones_not_drops(
    metabolite_graph,
):
    """G2, on the source whose organism column is the cleanest in the project:
    823 of 838 species names resolve, every one of them at rank `species`, and
    the 15 that do not are nomenclatural churn — eight *Mycoplasma* species
    split into *Mycoplasmoides*/*Mycoplasmopsis* in 2018, three *Lactobacillus*
    species from the 2020 25-genus split, and two names two taxa share, which
    are refused rather than guessed."""
    tombstones = rows(
        metabolite_graph,
        "MATCH (u:UnresolvedTaxon) WHERE u.source = 'njc19' "
        "RETURN u.raw_name AS name, u.status AS status ORDER BY name",
    )
    assert len(tombstones) == METABOLITE_GOLDEN["d6_unresolved_taxa"]
    assert {r["status"] for r in tombstones} == {"unresolved", "ambiguous"}
    names = {r["name"] for r in tombstones}
    assert "Mycoplasma pneumoniae" in names
    assert "Lactobacillus plantarum" in names
    # And none of the six host cell types is in here: they are not taxa NCBI
    # lost, they are not taxa.
    assert not any("colonocyte" in n or "hepatocyte" in n for n in names)


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
    walk = one(
        metabolite_graph,
        """
        MATCH (t:Taxon)-[:PRODUCES]->(m:Metabolite)-[:IN_PATHWAY]->(pw:Pathway)
        RETURN count(*) AS rows, count(DISTINCT t.id) AS taxa,
               count(DISTINCT pw.id) AS pathways
        """,
    )
    assert walk["rows"] == METABOLITE_GOLDEN["d13_walk_rows"]
    assert walk["taxa"] == METABOLITE_GOLDEN["d13_walk_taxa"]
    assert walk["pathways"] == METABOLITE_GOLDEN["d13_walk_pathways"]
    # The HMDB half unchanged beside it: this walk grew 27x when NJC19 landed,
    # and a golden that only carried the total could not say whether the growth
    # was a new source or a loader bug duplicating rows.
    hmdb_walk = one(
        metabolite_graph,
        """
        MATCH (t:Taxon)-[p:PRODUCES]->(m:Metabolite)-[:IN_PATHWAY]->(pw:Pathway)
        WHERE p.primary_source = 'hmdb'
        RETURN count(*) AS rows, count(DISTINCT t.id) AS taxa,
               count(DISTINCT pw.id) AS pathways
        """,
    )
    assert hmdb_walk["rows"] == METABOLITE_GOLDEN["d13_walk_rows_hmdb"]
    assert hmdb_walk["taxa"] == METABOLITE_GOLDEN["d13_walk_taxa_hmdb"]
    assert hmdb_walk["pathways"] == METABOLITE_GOLDEN["d13_walk_pathways_hmdb"]
    # Part D's own D13 query names E. coli, which is the taxon it resolves for.
    assert (
        one(
            metabolite_graph,
            "MATCH (t:Taxon {id: 562})-[:PRODUCES]->(m:Metabolite)-[:IN_PATHWAY]->(pw:Pathway) "
            "RETURN count(*) AS rows",
        )["rows"]
        == METABOLITE_GOLDEN["d13_ecoli_rows"]
    )
    # The claim in one query, and it has **two exceptions, one of which NJC19
    # added**: of the 830 organisms the graph attributes a production to, two
    # are also species Reactome models — *Mycobacterium tuberculosis*, which
    # Reactome carries for its infection pathways and HMDB names as a producer,
    # and *Saccharomyces cerevisiae*, which NJC19 curates exchanges for and
    # Reactome models as a reference organism. For those two the row is not
    # "capability, not production"; for the other 828 it is, and Part D's "not
    # a single gut commensal" survives both — a tuberculosis bacillus is a
    # pathogen and brewer's yeast is not a gut commensal either.
    overlap = rows(
        metabolite_graph,
        """
        MATCH (t:Taxon)-[:PRODUCES]->()-[:IN_PATHWAY]->(pw:Pathway)
        WHERE pw.species = t.title
        RETURN DISTINCT t.id AS tax_id, t.title AS taxon
        ORDER BY tax_id
        """,
    )
    assert overlap == [
        {"tax_id": 1773, "taxon": "Mycobacterium tuberculosis"},
        {"tax_id": 4932, "taxon": "Saccharomyces cerevisiae"},
    ]


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
        ("TAS", "knowledge_assertion", "unknown"): METABOLITE_GOLDEN[
            "d13_in_pathway_tas"
        ],
        ("IEA", "logical_entailment", "computational-predicted"): METABOLITE_GOLDEN[
            "d13_in_pathway_iea"
        ],
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
    assert (
        one(metabolite_graph, "MATCH (p:Pathway) RETURN count(p) AS n")["n"]
        == METABOLITE_GOLDEN["d13_pathways"]
    )
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
    # Was 26 before MASI: its 46 IBD associations over 32 taxa added six
    # candidates that now clear the two-study clause.
    "d10_candidates": 32,
    "d10_with_amr": 5,
    # Was 7 with HMDB alone; NJC19's export half more than doubled it, which is
    # W3's metabolite leg going from a sample to something a candidate list can
    # be filtered on, and MASI's taxa added two more.
    "d10_with_metabolites": 20,
    "d10_candidates_any_support": 119,
    # **The column D10 is named for, and it did not exist until MASI.** Seven of
    # the 32 depleted-in-IBD candidates are organisms MASI records as being used
    # as probiotics, with the stage that use has reached — including
    # *Akkermansia muciniphila*, the case D10's own narrative walks through, and
    # *Faecalibacterium prausnitzii*.
    "d10_probiotic_candidates": 7,
    "d10_probiotic_named": "Akkermansia muciniphila",
    # D12 — the synonym lookup, and the rank filter that makes it an answer.
    "d12_reuteri": 1598,
    "d12_rhamnosus": 47715,
    "d12_scoring_taxa": 726,
    "d12_authority_synonym": "Lactobacillus reuteri Kandler et al. 1982",
    "d12_reuteri_signatures": 69,
    "d12_resolution_statuses": {
        "exact": 114161,
        "merged": 413,
        "promoted": 152,
        "deleted": 16,
    },
    # D18 — metformin as a competing explanation, through gutMDisorder's
    # intervention edge joined to ChEMBL's drug identity by IS_DRUG.
    #
    # MASI added a third route and it is the largest: 365 edges over 185 taxa
    # onto the `Substance` node metformin also has, one `SAME_COMPOUND_AS` hop
    # from `CHEMBL:CHEMBL1431`. 347 of those 365 are pairs no screen measured.
    "d18_masi_metformin_edges": 365,
    "d18_masi_metformin_taxa": 185,
    "d18_masi_metformin_novel": 347,
    "d18_masi_t2d_taxa": 48,
    "d18_metformin_edges": 24,
    "d18_metformin_taxa": 21,
    "d18_t2d_rows": 19,
    "d18_t2d_taxa": 17,
    # Forslund et al.'s named fixtures. gutMDisorder curates a metformin edge
    # for none of the first three, which is why D18 is not `answerable-now`.
    "d18_absent_fixtures": ("Escherichia", "Intestinibacter", "Lactobacillus"),
    "d18_present_fixture": "Bifidobacterium",
    # --- Maier 2018, measured 2026-09-03 on the nine-source build -----------
    # D8 leg 3: the growth screen. `no_effect` is the number that did not exist
    # before this source — a drug the screen *tested* against a taxon and found
    # nothing at 20 uM, which is a measurement rather than an absence of
    # curation and which no other source here supports for drugs.
    "d8_inhibits": 5592,
    "d8_no_effect": 42233,
    "d8_screen_taxa": 38,
    "d8_screen_drugs": 1197,
    "d8_drugs_with_a_hit": 399,
    "d8_approved_with_a_hit": 287,
    # The paper's own headline, reproduced from the loaded edges: "24% of the
    # drugs with human targets ... inhibited the growth of at least one strain".
    "d8_human_targeted_hitting": 203,
    "d8_human_targeted_edges": 1120,
    # The dose-response follow-up, split by which relationship it landed on.
    "d8_validation": {
        "INHIBITS_GROWTH_OF": {"TP": 158, "FP": 12},
        "DOES_NOT_INHIBIT_GROWTH_OF": {"TN": 182, "FN": 27},
    },
    # The three join routes and the minted remainder, over 1,197 library
    # entries reaching 1,197 distinct Drug nodes.
    "d8_drug_join": {"name": 455, "atc": 361, "salt-name": 26, "minted": 355},
    # --- Zimmermann 2019, measured 2026-09-03 on the ten-source build --------
    # D8 leg 4: the metabolism screen, the direction Maier cannot answer. The
    # negatives are again the larger half, and they are again a measurement.
    "d8_metabolises": 2575,
    "d8_no_metabolism": 17479,
    "d8_metabolism_taxa": 66,
    "d8_metabolism_drugs": 271,
    "d8_drugs_metabolised": 172,
    "d8_approved_metabolised": 147,
    # The published headline is 176 of 271. The four the graph does not carry
    # are metabolised **only** by `Bifidobacterium ruminatum`, one of the two
    # strain names the loader refuses to guess at — the priced cost of that
    # refusal, named rather than rounded away.
    "d8_published_metabolised": 176,
    "d8_metabolised_only_by_a_refused_strain": (
        "ALPRENOLOL",
        "DIPHENYLPYRALINE",
        "IRSOGLADINE MALEATE",
        "MEMANTINE",
    ),
    "d8_metabolism_drug_join": {
        "molename": 195,
        "parent-name": 43,
        "salt-name": 10,
        "minted": 23,
    },
    # Supplementary table 13's gain-of-function genes, split by the relationship
    # they landed on: 5 of the 37 pairs are the two experiments disagreeing.
    "d8_gene_edges": {"METABOLISES": 32, "DOES_NOT_METABOLISE": 5},
    # The overlap between the two screens, which is what makes "does the gut
    # destroy this drug, and does this drug destroy the gut" one question.
    "d8_drugs_in_both_screens": 195,
    "d8_taxa_in_both_screens": 26,
    "d8_sulfasalazine": (52, 14),
    # Digoxin: 15 taxa over 21 screened isolates metabolise it — and
    # *Eggerthella lenta*, the textbook one, is a measured non-hit here.
    "d8_digoxin": (15, 21),
    # D18 leg 3: metformin against the 40 isolates. **Forty measurements, zero
    # hits** — the competing explanation is now a negative, and a negative is
    # what the confounding argument actually needed.
    "d18_metformin_measurements": 40,
    "d18_metformin_screen_taxa": 38,
    "d18_metformin_hits": 0,
    "d18_screen_t2d_taxa": 32,
    "d18_t2d_taxa_inhibited_by_something": 32,
    "d18_t2d_inhibiting_drugs": 380,
    "d18_t2d_human_targeted_inhibitors": 186,
    # Forslund's named genera, at the species the screen actually ran. Three of
    # the four are now measured; gutMDisorder curated only the fourth.
    "d18_screened_fixtures": (
        "Escherichia coli",
        "Lacticaseibacillus paracasei",
        "Bifidobacterium longum",
        "Bifidobacterium adolescentis",
    ),
    "d18_unscreened_fixture_genus": "Intestinibacter",
}


@pytest.fixture(scope="session")
def synonym_index(graph):
    """`text_bm25` is opt-in, so D12's query needs the index built first —
    which `scripts/build.py` does and the acceptance fixture does not."""
    graph.build_text_index("Taxon", "synonyms_text")
    return graph


# --------------------------------------------------------------------------
# D10 — "For disease Y, which depleted taxa are plausible probiotic candidates?"
# --------------------------------------------------------------------------


def test_d10_the_amr_and_metabolite_legs_are_populated_not_zero(graph):
    """Part D filed D10 `partial` with the AMR and metabolite columns
    returning `0` and `[]` for every row — "the honest answer, not a bug".
    CARD and HMDB changed that, and the two counts are what the status now
    rests on: the gap is coverage, not a missing relationship. MASI moved the
    candidate list itself, 26 -> 32."""
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


def test_d10_now_has_the_column_it_is_named_for(graph):
    """**D10 asks for "plausible probiotic candidates" and until MASI landed
    the graph had no column that said which taxa anybody uses as one.** It has
    one now, on the node: `Taxon.probiotic` with the population it was used in
    and the stage that use has reached, from MASI's microbe dictionary.

    Seven of the 32 depleted-in-IBD candidates carry it, and the list is not a
    curiosity — it contains *Akkermansia muciniphila*, whose randomised
    double-blind pilot D10's own text walks through as the chain the query is a
    proxy for, and *Faecalibacterium prausnitzii*. The flag is **three-state**:
    a candidate MASI does not cover is null, never false, so this query never
    reads "MASI has no row for this organism" as "this organism is not a
    probiotic"."""
    named = rows(
        graph,
        """
        MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0005265'})
        WHERE r.direction = 'decreased' AND t.placeholder = false
          AND t.probiotic = true
        WITH t, count(DISTINCT r.study_id) AS n_studies
        WHERE n_studies >= 2
        RETURN t.title AS candidate, t.probiotic_use_species AS used_in,
               t.probiotic_research_stage AS stage
        ORDER BY candidate
        """,
    )
    assert len(named) == PARTIAL_GOLDEN["d10_probiotic_candidates"]
    assert PARTIAL_GOLDEN["d10_probiotic_named"] in {r["candidate"] for r in named}
    assert all(r["used_in"] and r["stage"] for r in named), (
        "a probiotic flag with no use population and no research stage is a "
        "boolean, not an answer"
    )
    # Three-state, and the third state is what stops the flag being read as a
    # verdict on the organisms MASI never mentions.
    assert (
        one(graph, "MATCH (t:Taxon) WHERE t.probiotic IS NULL RETURN count(*) AS n")[
            "n"
        ]
        > 0
    )


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
        WHERE text_bm25(t, 'synonyms_text', 'Lactobacillus reuteri') > 0
        RETURN t.id AS tax_id, t.rank AS rank,
               text_bm25(t, 'synonyms_text', 'Lactobacillus reuteri') AS score
        ORDER BY score DESC LIMIT 3
        """,
    )
    assert [r["rank"] for r in unfiltered] == ["strain"] * 3
    assert PARTIAL_GOLDEN["d12_reuteri"] not in {r["tax_id"] for r in unfiltered}

    filtered = rows(
        synonym_index,
        """
        MATCH (t:Taxon)
        WHERE text_bm25(t, 'synonyms_text', 'Lactobacillus reuteri') > 0
          AND t.rank = 'species'
        RETURN t.id AS tax_id, t.title AS current_name, t.rank AS rank,
               t.synonyms AS synonyms,
               text_bm25(t, 'synonyms_text', 'Lactobacillus reuteri') AS score
        ORDER BY score DESC LIMIT 3
        """,
    )
    assert filtered[0]["tax_id"] == PARTIAL_GOLDEN["d12_reuteri"]
    assert filtered[0]["current_name"] == "Limosilactobacillus reuteri"
    # C4, in the built graph: NCBI keeps the old binomial **only** in
    # authority-decorated form, so a resolver indexing name classes literally
    # returns `unresolved` for it and the failure looks like a data gap.
    # `synonyms` is a native list, so this reads it rather than re-splitting a
    # joined string — and the same check is a Cypher predicate below.
    synonyms = filtered[0]["synonyms"]
    assert isinstance(synonyms, list), f"synonyms is not a list property: {synonyms!r}"
    assert PARTIAL_GOLDEN["d12_authority_synonym"] in synonyms
    assert "Lactobacillus reuteri" not in synonyms
    membership = PARTIAL_GOLDEN["d12_authority_synonym"].replace("'", "\\'")
    assert (
        one(
            synonym_index,
            f"MATCH (t:Taxon) WHERE '{membership}' IN t.synonyms RETURN count(t) AS n",
        )["n"]
        >= 1
    ), (
        "membership on the list property found nothing — the whole point of "
        "declaring `synonyms` a list is that this is a query, not a re-parse"
    )
    # And the rank filter is load-bearing rather than tidy: 726 taxa score
    # above zero on that query.
    assert (
        one(
            synonym_index,
            "MATCH (t:Taxon) WHERE text_bm25(t, 'synonyms_text', 'Lactobacillus reuteri') > 0 "
            "RETURN count(t) AS n",
        )["n"]
        == PARTIAL_GOLDEN["d12_scoring_taxa"]
    )


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
        WHERE text_bm25(t, 'synonyms_text', 'Lactobacillus rhamnosus') > 0
          AND t.rank = 'species'
        RETURN t.id AS tax_id, t.title AS name,
               text_bm25(t, 'synonyms_text', 'Lactobacillus rhamnosus') AS score
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
    only *Bifidobacterium* of the named set is reachable on this route, which
    is why the intervention leg alone answers with the taxa this corpus happens
    to have. MASI's route reaches the other three
    (`test_d18_masi_reaches_the_three_confounders_gutmdisorder_misses`), on
    curated literature rather than on a measurement."""
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


def test_d18_masi_reaches_the_three_confounders_gutmdisorder_misses(graph):
    """**The leg D18 was filed `partial` for, and what it turns out to be.**
    Part D's caveat was that *Intestinibacter* — "the decrease Forslund calls
    the most consistent of the four" — was not one of Maier's 40 isolates and
    could get no measurement from that source. MASI reaches it: a curated
    abundance **decrease** under metformin, in vivo in humans.

    And the citation on that edge is `PMID:26633628`, which is **Forslund et
    al. itself**. That is worth stating plainly rather than counting as a win:
    the graph now contains the finding the query is checking a T2D association
    against, curated by a third party, and a curated restatement of the paper
    is not independent evidence for or against it. D18 therefore stays
    `partial`. What did change is the reach — 32 T2D taxa to 48 — and the
    shape of the gap: it is no longer "no edge exists" but "the edge that
    exists is the claim, not a test of it", which `primary_source = 'masi'`,
    `evidence_level` and `publications` all say on the edge itself."""
    metformin = one(
        graph,
        f"MATCH (s:Substance)-[:{'SAME_COMPOUND_AS'}]->"
        f"(:Drug {{id: '{CHEMBL_GOLDEN['metformin']}'}}) RETURN s.id AS id",
    )["id"]
    reach = one(
        graph,
        f"MATCH (t:Taxon)-[r]->(:Substance {{id: '{metformin}'}}) "
        f"RETURN count(r) AS edges, count(DISTINCT t) AS taxa, "
        f"sum(CASE WHEN r.duplicates_primary_source IS NULL THEN 1 ELSE 0 END) "
        f"AS novel",
    )
    assert reach["edges"] == PARTIAL_GOLDEN["d18_masi_metformin_edges"]
    assert reach["taxa"] == PARTIAL_GOLDEN["d18_masi_metformin_taxa"]
    assert reach["novel"] == PARTIAL_GOLDEN["d18_masi_metformin_novel"]
    assert (
        one(
            graph,
            f"""
        MATCH (t:Taxon)-[:ASSOCIATED_WITH]->(:Disease {{id: 'MONDO:0005148'}})
        MATCH (t)-[:ABUNDANCE_CHANGED_BY_SUBSTANCE|ABUNDANCE_UNCHANGED_BY_SUBSTANCE
                  |METABOLISES_SUBSTANCE|DOES_NOT_METABOLISE_SUBSTANCE]->
              (:Substance {{id: '{metformin}'}})
        RETURN count(DISTINCT t) AS taxa
        """,
        )["taxa"]
        == PARTIAL_GOLDEN["d18_masi_t2d_taxa"]
    )

    named = {
        (r["taxon"], r["direction"]): r
        for r in rows(
            graph,
            f"MATCH (t:Taxon)-[r]->(:Substance {{id: '{metformin}'}}) "
            f"WHERE t.title IN "
            f"{list(PARTIAL_GOLDEN['d18_absent_fixtures'])} "
            f"RETURN t.title AS taxon, r.direction AS direction, "
            f"r.publications AS publications, r.evidence_level AS level",
        )
    }
    assert {t for t, _d in named} == set(PARTIAL_GOLDEN["d18_absent_fixtures"])
    # The one the caveat is named for, and the paper it comes from.
    intestinibacter = named[("Intestinibacter", "decreased")]
    assert intestinibacter["publications"] == ["PMID:26633628"]
    assert intestinibacter["level"] == "unknown"
    assert ("Escherichia", "increased") in named


def test_d8_leg3_is_the_growth_screen_and_its_negatives(graph):
    """**What closed D8's inhibition leg, after MASI could not.** MASI's
    interaction tables are unrecoverable — its origin no longer completes a TLS
    connection and the Wayback Machine never captured them — so the aggregator
    was replaced by the landmark screen it aggregates: Maier et al. measured
    1,197 marketed drugs against 40 human gut isolates, every cell of the
    matrix, and published the p-values.

    The number that matters is the second one. **42,233 measured non-hits** is
    a population no other source in this graph has for drugs: MASI would have
    curated positives, and gutMDisorder curates what somebody chose to publish.
    They are their own relationship rather than a flag, so no
    `MATCH (d)-[:INHIBITS_GROWTH_OF]->(t)` can count a refutation as an
    observation by omission — Part D's own rule for this layer, stated before
    the source arrived."""
    counts = {
        r["rel"]: r
        for r in rows(
            graph,
            "MATCH (d:Drug)-[r:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->(t:Taxon) "
            "RETURN type(r) AS rel, count(r) AS edges, count(DISTINCT t) AS taxa",
        )
    }
    assert counts["INHIBITS_GROWTH_OF"]["edges"] == PARTIAL_GOLDEN["d8_inhibits"]
    assert (
        counts["DOES_NOT_INHIBIT_GROWTH_OF"]["edges"] == PARTIAL_GOLDEN["d8_no_effect"]
    )
    assert all(c["taxa"] == PARTIAL_GOLDEN["d8_screen_taxa"] for c in counts.values())
    reach = one(
        graph,
        "MATCH (d:Drug)-[:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->() "
        "RETURN count(DISTINCT d) AS drugs",
    )
    assert reach["drugs"] == PARTIAL_GOLDEN["d8_screen_drugs"], (
        "1,197 library entries must reach 1,197 distinct Drug nodes: an ATC "
        "code two entries claim identifies neither, and joining both to the one "
        "node it names attributes one enantiomer's measurement to the other"
    )
    hits = one(
        graph,
        "MATCH (d:Drug)-[:INHIBITS_GROWTH_OF]->() "
        "RETURN count(DISTINCT d) AS drugs, "
        "count(DISTINCT CASE WHEN d.approved THEN d.id END) AS approved",
    )
    assert hits["drugs"] == PARTIAL_GOLDEN["d8_drugs_with_a_hit"]
    assert hits["approved"] == PARTIAL_GOLDEN["d8_approved_with_a_hit"]


def test_d8_reproduces_the_papers_own_headline_from_the_loaded_edges(graph):
    """ "24% of the drugs with human targets ... inhibited the growth of at
    least one strain in vitro" (Nature 555:623, abstract). The graph says
    **203 of 835 = 24.3%** — computed from the edges, not quoted.

    This is not decoration: the hit threshold is *derived* (the sheet publishes
    p-values and an `n_hit` count and never states the cutoff), it decides the
    **type** of every edge in the source, and reproducing the abstract is one
    of the four independent checks that it is right."""
    result = one(
        graph,
        "MATCH (d:Drug)-[r:INHIBITS_GROWTH_OF]->(t:Taxon) "
        "WHERE r.drug_class = 'human-targeted drugs' "
        "RETURN count(r) AS edges, count(DISTINCT d) AS drugs, "
        "count(DISTINCT t) AS taxa",
    )
    assert result["drugs"] == PARTIAL_GOLDEN["d8_human_targeted_hitting"]
    assert result["edges"] == PARTIAL_GOLDEN["d8_human_targeted_edges"]
    assert result["taxa"] == PARTIAL_GOLDEN["d8_screen_taxa"]
    screened = one(
        graph,
        "MATCH ()-[r:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->() "
        "WHERE r.drug_class = 'human-targeted drugs' "
        "RETURN count(DISTINCT r.prestwick_id) AS drugs",
    )
    assert screened["drugs"] == 835
    assert 0.24 <= result["drugs"] / screened["drugs"] < 0.245


def test_d8_the_authors_own_validation_lands_on_the_right_relationship(graph):
    """Supplementary table 4 re-measured 379 pairs in a dilution series and
    scored each against the screen's call. Every `TP`/`FP` sits on a hit edge
    and every `TN`/`FN` on a non-hit edge — a check on the derived threshold
    from a column that had no part in deriving it. It is also where the
    negatives get *bounded*: `> 160 µM` is a far stronger statement than "not
    at 20 µM", and `ic25_qualifier` keeps the source's own operator."""
    got: dict[str, dict[str, int]] = {}
    for row in rows(
        graph,
        "MATCH ()-[r:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->() "
        "WHERE r.validation_outcome <> '' "
        "RETURN type(r) AS rel, r.validation_outcome AS outcome, count(r) AS n",
    ):
        got.setdefault(row["rel"], {})[row["outcome"]] = row["n"]
    assert got == PARTIAL_GOLDEN["d8_validation"]
    qualifiers = {
        r["q"]
        for r in rows(
            graph,
            "MATCH ()-[r:DOES_NOT_INHIBIT_GROWTH_OF]->() "
            "WHERE r.ic25_qualifier <> '' RETURN DISTINCT r.ic25_qualifier AS q",
        )
    }
    assert ">" in qualifiers, "a bounded negative must keep the source's operator"


def test_d8_every_edge_says_which_identifier_space_reached_the_drug(graph):
    """The Prestwick library names salts and catalogue forms and ChEMBL keys on
    the parent molecule, so the join is three routes tried verbatim-first. The
    rate is **842 of 1,197 = 70.3%** and the other 355 are minted on their
    catalogue number — reported rather than hidden, and `drug_join` is what
    makes the weakest route countable instead of assumed."""
    got = {
        r["route"]: r["drugs"]
        for r in rows(
            graph,
            "MATCH ()-[r:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->() "
            "RETURN r.drug_join AS route, count(DISTINCT r.prestwick_id) AS drugs",
        )
    }
    assert got == PARTIAL_GOLDEN["d8_drug_join"]
    assert sum(got.values()) == PARTIAL_GOLDEN["d8_screen_drugs"]


def test_d8_the_metabolism_leg_is_the_other_direction_and_it_is_closed(graph):
    """D8 asks two things — "does drug D inhibit gut bacteria, **or get
    metabolised by them**" — and Maier only answers the first. Zimmermann et al.
    2019 measured 271 oral drugs against 76 gut strains, every cell, and it
    lands as its **own pair of edge types running the other way**: Part D
    required that before either source was fetched, because collapsing
    inhibition into metabolism conflates antimicrobial killing with chemical
    modification, which is MDAD's documented weakness.

    This test replaces the one that asserted no such relationship existed. The
    guard it protected has not been dropped, it has been restated: the direction
    is what keeps `MATCH (d:Drug)-[]->(t:Taxon)` meaning the growth screen and
    nothing else, and the next test asserts exactly that."""
    counts = {
        r["rel"]: r
        for r in rows(
            graph,
            "MATCH (t:Taxon)-[r:METABOLISES|DOES_NOT_METABOLISE]->(d:Drug) "
            "RETURN type(r) AS rel, count(r) AS edges, count(DISTINCT t) AS taxa",
        )
    }
    assert counts["METABOLISES"]["edges"] == PARTIAL_GOLDEN["d8_metabolises"]
    assert counts["DOES_NOT_METABOLISE"]["edges"] == PARTIAL_GOLDEN["d8_no_metabolism"]
    assert all(
        c["taxa"] == PARTIAL_GOLDEN["d8_metabolism_taxa"] for c in counts.values()
    )
    reach = one(
        graph,
        "MATCH ()-[:METABOLISES|DOES_NOT_METABOLISE]->(d:Drug) "
        "RETURN count(DISTINCT d) AS drugs",
    )
    assert reach["drugs"] == PARTIAL_GOLDEN["d8_metabolism_drugs"], (
        "all 271 screened compounds must reach a Drug node: 248 join one that "
        "already existed and 23 are minted, and a drug that reached none would "
        "look like a compound the screen never tested"
    )
    hits = one(
        graph,
        "MATCH ()-[:METABOLISES]->(d:Drug) "
        "RETURN count(DISTINCT d) AS drugs, "
        "count(DISTINCT CASE WHEN d.approved THEN d.id END) AS approved",
    )
    assert hits["drugs"] == PARTIAL_GOLDEN["d8_drugs_metabolised"]
    assert hits["approved"] == PARTIAL_GOLDEN["d8_approved_metabolised"]


def test_d8_the_two_screens_point_opposite_ways_and_that_is_the_model(graph):
    """The agent is on the tail of every edge in this layer: the drug acts in
    one screen, the bacterium acts in the other. That is what makes
    `(d:Drug)-[]->(t:Taxon)` the growth screen alone — the assertion that used
    to say "there are no such edges" and now says "there are only these" — and
    the `effect` vocabularies are disjoint for the same reason a shared
    `no-effect` token would be wrong: "did not stop it growing" and "did not
    touch the drug" are different findings about different things."""
    forward = {
        r["rel"]
        for r in rows(
            graph, "MATCH (d:Drug)-[r]->(t:Taxon) RETURN DISTINCT type(r) AS rel"
        )
    }
    assert forward == {"INHIBITS_GROWTH_OF", "DOES_NOT_INHIBIT_GROWTH_OF"}
    backward = {
        r["rel"]
        for r in rows(
            graph, "MATCH (t:Taxon)-[r]->(d:Drug) RETURN DISTINCT type(r) AS rel"
        )
    }
    assert backward == {"METABOLISES", "DOES_NOT_METABOLISE"}
    effects = {
        (r["rel"], r["effect"])
        for r in rows(
            graph,
            "MATCH ()-[r:METABOLISES|DOES_NOT_METABOLISE|INHIBITS_GROWTH_OF"
            "|DOES_NOT_INHIBIT_GROWTH_OF]->() "
            "RETURN DISTINCT type(r) AS rel, r.effect AS effect",
        )
    }
    assert effects == {
        ("INHIBITS_GROWTH_OF", "inhibited"),
        ("DOES_NOT_INHIBIT_GROWTH_OF", "no-effect"),
        ("METABOLISES", "metabolised"),
        ("DOES_NOT_METABOLISE", "not-metabolised"),
    }


def test_d8_reproduces_the_metabolism_headline_and_prices_what_it_does_not(graph):
    """ "176 of 271 drugs (65%) were metabolised by at least one strain." The
    graph says **172**, and the gap is not a loss — it is four drugs metabolised
    *only* by `Bifidobacterium ruminatum`, one of the two strain names NCBI
    holds two candidates for and whose row offers nothing to choose with. The
    loader refuses to guess; this is what the refusal costs, named.

    The call rule behind the 176 is derived — the sheet publishes each drug's
    depletion threshold and no significance cutoff — so reproducing the headline
    is the check that it is right, and `microbiomekg/preps/prep_zimmermann2019.py` refuses
    to write when it stops holding."""
    # Keyed on what the *screen* called the compound, not on the node's
    # `pref_name`: 248 of the 271 joined a node ChEMBL or the growth screen had
    # already named, so `IRSOGLADINE MALEATE` is `IRSOGLADINE` on its node.
    metabolised = {
        r["drug"]
        for r in rows(
            graph,
            "MATCH ()-[r:METABOLISES]->() RETURN DISTINCT r.reported_drug_name AS drug",
        )
    }
    assert len(metabolised) == PARTIAL_GOLDEN["d8_drugs_metabolised"]
    missing = set(PARTIAL_GOLDEN["d8_metabolised_only_by_a_refused_strain"])
    assert not (metabolised & missing)
    assert len(metabolised) + len(missing) == PARTIAL_GOLDEN["d8_published_metabolised"]
    # And each of the four is in the graph as a screened drug with edges — it is
    # the *hit* that the refusal cost, not the compound.
    for drug in missing:
        assert rows(
            graph,
            "MATCH ()-[r:DOES_NOT_METABOLISE]->() "
            f"WHERE r.reported_drug_name = '{drug}' RETURN r LIMIT 1",
        ), f"{drug} lost its measured non-hits too"
    tombstones = {
        r["name"]: r["candidates"]
        for r in rows(
            graph,
            "MATCH (u:UnresolvedTaxon) WHERE u.source = 'zimmermann2019' "
            "RETURN u.raw_name AS name, u.candidates AS candidates",
        )
    }
    assert set(tombstones) == {"Bacteroides WH2", "Bifidobacterium ruminatum"}
    assert all(len(c) == 2 for c in tombstones.values()), (
        "a refusal has to name what it rejected, or the next reader has a dead end"
    )


def test_d8_every_metabolism_edge_says_which_identifier_space_reached_the_drug(graph):
    """Three routes, tried verbatim-first, and no ATC route because the sheet
    has no ATC column. **248 of 271 = 91.5%**, and the route is on the edge so
    the weakest is countable rather than assumed."""
    got = {
        r["route"]: r["drugs"]
        for r in rows(
            graph,
            "MATCH ()-[r:METABOLISES|DOES_NOT_METABOLISE]->() "
            "RETURN r.drug_join AS route, "
            "count(DISTINCT r.reported_drug_name) AS drugs",
        )
    }
    assert got == PARTIAL_GOLDEN["d8_metabolism_drug_join"]
    assert sum(got.values()) == PARTIAL_GOLDEN["d8_metabolism_drugs"]


def test_d8_the_gene_layer_rides_on_the_edge_and_keeps_its_disagreement(graph):
    """Part B's W7 asks for "the gene where identified" and the graph answers it
    in one hop, with no `Gene` node — the recommendation `docs/model.md`
    records. The genes came from a gain-of-function library expressed in
    *E. coli*, not from the 76 screened strains, so **5 of the 37 pairs sit on
    `DOES_NOT_METABOLISE` edges**: the two experiments disagree there, and
    dropping those or moving them onto the hit edge would be inventing
    agreement."""
    got = {
        r["rel"]: r["n"]
        for r in rows(
            graph,
            "MATCH ()-[r:METABOLISES|DOES_NOT_METABOLISE]->() "
            "WHERE r.gene_locus_tags <> '' "
            "RETURN type(r) AS rel, count(r) AS n",
        )
    }
    assert got == PARTIAL_GOLDEN["d8_gene_edges"]
    labels = {
        label
        for row in rows(graph, "MATCH (n) RETURN DISTINCT labels(n) AS label")
        for label in row["label"]
    }
    assert "Gene" not in labels, (
        "a Gene node type appeared — docs/model.md's recommendation against one "
        "has to be restated rather than left as it is"
    )


def test_d8_the_two_screens_overlap_and_the_overlap_is_the_point(graph):
    """195 drugs and 26 taxa are in both screens, so for those pairs the graph
    answers "does the gut destroy this drug **and** does this drug damage the
    gut" as one question with four measured outcomes, two of them negative.
    Before the second screen the first two of those four were empty for every
    drug, and empty was indistinguishable from "tested, nothing happened"."""
    drugs = one(
        graph,
        "MATCH ()-[:METABOLISES|DOES_NOT_METABOLISE]->(d:Drug) "
        "WITH collect(DISTINCT d.id) AS metabolism "
        "MATCH (e:Drug)-[:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->() "
        "WHERE e.id IN metabolism RETURN count(DISTINCT e) AS both",
    )
    assert drugs["both"] == PARTIAL_GOLDEN["d8_drugs_in_both_screens"]
    taxa = one(
        graph,
        "MATCH (t:Taxon)-[:METABOLISES|DOES_NOT_METABOLISE]->() "
        "WITH collect(DISTINCT t.id) AS metabolism "
        "MATCH (d:Drug)-[:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->(u:Taxon) "
        "WHERE u.id IN metabolism RETURN count(DISTINCT u) AS both",
    )
    assert taxa["both"] == PARTIAL_GOLDEN["d8_taxa_in_both_screens"]
    outcome = one(
        graph,
        "MATCH (d:Drug {pref_name: 'SULFASALAZINE'}) "
        "OPTIONAL MATCH (t:Taxon)-[:METABOLISES]->(d) "
        "OPTIONAL MATCH (u:Taxon)-[:DOES_NOT_METABOLISE]->(d) "
        "RETURN count(DISTINCT t) AS metabolised, "
        "count(DISTINCT u) AS tested_untouched",
    )
    assert (outcome["metabolised"], outcome["tested_untouched"]) == (
        PARTIAL_GOLDEN["d8_sulfasalazine"]
    )


def test_d8_a_measured_negative_is_bounded_by_its_assay_and_digoxin_proves_it(graph):
    """*Eggerthella lenta* reducing digoxin is the textbook drug-metabolism
    result, and **this screen measured that pair and scored it a non-hit** —
    4.0% consumed against the drug's own 20% threshold, FDR p = 0.55. That is
    not a refutation: digoxin reduction needs the *cgr* operon expressed under
    arginine-poor conditions and this screen ran one medium for 12 h.

    The edge is kept, with `incubation_hours` and `replicates` on it, precisely
    so the bound is readable — a `DOES_NOT_METABOLISE` edge means "not in this
    assay", never "not at all". Fifteen other taxa, across 21 screened isolates,
    do metabolise digoxin here — which is the finding the single-organism story
    does not carry."""
    lenta = one(
        graph,
        "MATCH (t:Taxon)-[r:DOES_NOT_METABOLISE]->(d:Drug {pref_name: 'DIGOXIN'}) "
        "WHERE t.title CONTAINS 'Eggerthella' "
        "RETURN r.percent_consumed AS consumed, "
        "r.drug_threshold_percent AS threshold, r.fdr_p_value AS p, "
        "r.incubation_hours AS hours, r.replicates AS n",
    )
    assert lenta["consumed"] < lenta["threshold"]
    assert lenta["p"] > 0.05
    assert lenta["hours"] == 12.0 and lenta["n"] == 4
    assert not rows(
        graph,
        "MATCH (t:Taxon)-[r:METABOLISES]->(d:Drug {pref_name: 'DIGOXIN'}) "
        "WHERE t.title CONTAINS 'Eggerthella' RETURN r",
    )
    others = one(
        graph,
        "MATCH (t:Taxon)-[r:METABOLISES]->(d:Drug {pref_name: 'DIGOXIN'}) "
        "RETURN count(DISTINCT t) AS taxa, "
        "count(DISTINCT r.screen_column) AS isolates",
    )
    assert (others["taxa"], others["isolates"]) == PARTIAL_GOLDEN["d8_digoxin"], (
        "the whole point of a screen over the single-organism result"
    )


def test_masi_is_loaded_and_never_onto_a_relationship_a_screen_owns(graph):
    """**What the MASI download turned out to be, once all of it arrived.** The
    2026-09-02 record called the interaction tables *unrecoverable*, and that
    was wrong: `www.aiddlab.com` has an expired TLS certificate rather than
    being gone, so every programmatic fetch failed at the handshake and the
    Wayback Machine — which will not archive a host it cannot handshake with —
    had never captured them either. Two failures with one cause corroborated
    each other into a false negative. A browser asks and proceeds; all eight
    files answered on 2026-09-03.

    MASI is the eleventh source, and it is an **aggregator**: 5,419 of its
    12,512 interaction records cite Maier 2018 and 2,884 cite Zimmermann 2019,
    both already loaded from the papers themselves, and **7,161 of the 11,456
    edges it produces restate a (taxon, compound) pair one of those screens
    already measures**. So it gets its own node type and its own four
    relationships, and the identity between a MASI substance and a graph `Drug`
    is a declared `SAME_COMPOUND_AS` edge rather than a merge.

    This test is the guard that used to assert MASI loaded nothing, restated
    for what it actually protects: **no measured relationship may carry a MASI
    edge**. If one did, `MATCH (t:Taxon)-[:METABOLISES]->(d:Drug)` — the query
    D8 is written as — would count a curated restatement and a measured screen
    cell as two observations, with nothing in the query text to say so."""
    for relationship in (
        "INHIBITS_GROWTH_OF",
        "DOES_NOT_INHIBIT_GROWTH_OF",
        "METABOLISES",
        "DOES_NOT_METABOLISE",
    ):
        assert not rows(
            graph,
            f"MATCH ()-[r:{relationship}]->() WHERE r.primary_source = 'masi' "
            f"RETURN r LIMIT 1",
        ), (
            f"{relationship} carries a MASI edge. That relationship is a "
            f"published screen's measured population; an aggregator's curation "
            f"of the same literature belongs on its own."
        )
    assert (ROOT / "microbiomekg" / "preps" / "prep_masi.py").is_file()
    assert (ROOT / "microbiomekg" / "blueprints" / "masi.json").is_file()
    assert (ROOT / "data" / "raw" / "masi" / "PROVENANCE.md").is_file()
    counts = {
        r["t"]: r["n"]
        for r in rows(
            graph,
            "MATCH ()-[r]->(:Substance) RETURN type(r) AS t, count(*) AS n",
        )
    }
    assert counts == {
        "METABOLISES_SUBSTANCE": 3356,
        "DOES_NOT_METABOLISE_SUBSTANCE": 16,
        "ABUNDANCE_CHANGED_BY_SUBSTANCE": 7579,
        "ABUNDANCE_UNCHANGED_BY_SUBSTANCE": 505,
    }
    overlap = one(
        graph,
        "MATCH ()-[r]->(:Substance) RETURN count(*) AS edges, "
        "sum(CASE WHEN r.duplicates_primary_source IS NULL THEN 0 ELSE 1 END) "
        "AS restated",
    )
    assert (overlap["edges"], overlap["restated"]) == (11456, 7161)


def test_masi_mints_no_drug_node_and_the_identity_is_an_edge(graph):
    """MASI never writes a `Drug`. Both screens do — they mint one for each
    screened compound no ChEMBL route reaches — so this is a real difference and
    not an accident of what happened to join: 278 of MASI's 1,350 substances
    have no therapeutic category at all (*Cadmium*, *Black tea extract*), and
    typing those `Drug` is the C14 error in a different column.

    883 of the 1,350 reach an existing `Drug` by an exact or salt-stripped name
    match, and that identity is an edge a query traverses deliberately."""
    assert one(graph, "MATCH (s:Substance) RETURN count(*) AS n")["n"] == 1350
    assert not rows(graph, "MATCH (d:Drug) WHERE d.source = 'masi' RETURN d LIMIT 1")
    assert (
        one(graph, "MATCH ()-[r:SAME_COMPOUND_AS]->() RETURN count(*) AS n")["n"] == 883
    )
    # And the hop works in the direction D8 and D18 need it.
    assert (
        one(
            graph,
            f"MATCH (t:Taxon)-[m]->(s:Substance)-[:SAME_COMPOUND_AS]->"
            f"(d:Drug {{id: '{CHEMBL_GOLDEN['metformin']}'}}) "
            f"RETURN count(m) AS edges",
        )["edges"]
        == PARTIAL_GOLDEN["d18_masi_metformin_edges"]
    )


def test_masi_is_the_fourth_association_source_and_all_of_it_is_a_violation(graph):
    """Its 784 disease records land as rows in the shared `taxon_condition.csv`,
    not as a fourth relationship, so D2/D3/D17 span them without knowing MASI
    arrived. All 783 edges violate the fourteen-property contract, and that is
    the audit working for the third time: the export has eleven columns and not
    one of them is a design, a host, a sequencing type, a statistical test or an
    arm size.

    The disease keys come through MONDO **by name**, because MASI ships no
    condition identifier at all — 684 of the 783 edges reach a live MONDO term
    by a label or an exact synonym, and the other 99 keep `MASI:DIS<n>` with
    `mondo_id` null, the shape BugSigDB's 503 own-CURIE terms already have."""
    assert (
        one(
            graph,
            "MATCH ()-[r:ASSOCIATED_WITH]->() WHERE r.primary_source = 'masi' "
            "RETURN count(*) AS n",
        )["n"]
        == 783
    )
    routes = {
        r["route"]: r["n"]
        for r in rows(
            graph,
            "MATCH ()-[r:ASSOCIATED_WITH]->(:Disease) "
            "WHERE r.primary_source = 'masi' "
            "RETURN r.condition_join AS route, count(*) AS n",
        )
    }
    assert routes == {"mondo-name": 358, "mondo-exact-synonym": 326, "unmatched": 99}
    # **`condition_join` is on the edge and not on the node**, because
    # `disease.csv` is shared and key-deduped: 631 of the MONDO ids MASI reaches
    # were written by BugSigDB or gutMDisorder first, so a node column would be
    # null for exactly the edges it describes. Same constraint as a screen's
    # `drug_class`, same answer.
    assert not rows(
        graph, "MATCH (d:Disease) WHERE d.condition_join IS NOT NULL RETURN d LIMIT 1"
    )
    # A name-keyed disease is still a disease with its source string on it, so
    # the join stays reversible.
    unmatched = one(
        graph,
        "MATCH ()-[r:ASSOCIATED_WITH]->(d:Disease) "
        "WHERE r.condition_join = 'unmatched' "
        "AND d.source_condition = 'Rheumatoid arthrits' "
        "RETURN d.id AS id, d.mondo_id AS mondo",
    )
    assert unmatched["id"].startswith("MASI:") and unmatched["mondo"] is None


def test_d18_metformin_inhibits_none_of_the_screened_taxa(graph):
    """**D18's leg 3, and it is a negative — which is what the confounding
    argument actually needed.** Forslund et al. showed that metformin, not type
    2 diabetes, explains an *Escherichia* increase and an *Intestinibacter*
    decrease. The competing explanation the graph could offer was
    gutMDisorder's abundance shifts for 17 taxa; what it could never say was
    *how* — and "metformin does not inhibit the growth of any of these 38
    isolates at 20 µM" is a measured constraint on the mechanism rather than a
    second correlation.

    40 measurements, 38 taxa, **zero hits**, and every one of them is a
    `DOES_NOT_INHIBIT_GROWTH_OF` edge that a query can count."""
    growth = rows(
        graph,
        f"MATCH (:Drug {{id: '{CHEMBL_GOLDEN['metformin']}'}})"
        "-[g:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->(t:Taxon) "
        "RETURN type(g) AS rel, count(g) AS edges, count(DISTINCT t) AS taxa",
    )
    assert len(growth) == 1, "metformin must reach exactly one of the two relationships"
    assert growth[0]["rel"] == "DOES_NOT_INHIBIT_GROWTH_OF"
    assert growth[0]["edges"] == PARTIAL_GOLDEN["d18_metformin_measurements"]
    assert growth[0]["taxa"] == PARTIAL_GOLDEN["d18_metformin_screen_taxa"]
    hits = one(
        graph,
        f"MATCH (:Drug {{id: '{CHEMBL_GOLDEN['metformin']}'}})"
        "-[g:INHIBITS_GROWTH_OF]->() RETURN count(g) AS n",
    )
    assert hits["n"] == PARTIAL_GOLDEN["d18_metformin_hits"]


def test_d18_the_competing_explanation_is_now_offered_for_32_t2d_taxa(graph):
    """The same query D18 always asked, through the growth screen instead of
    through 15 name-matched interventions: **32** T2D taxa carry a metformin
    measurement, against gutMDisorder's 17, and all 32 read `no-effect`.

    Both legs stay — they answer different questions. gutMDisorder says
    metformin *changed this taxon's abundance in a patient*; Maier says it
    *does not kill this taxon in a tube*. Neither refutes the other, and the
    pair is more informative than either: an abundance shift with no growth
    inhibition is an argument for an indirect mechanism."""
    joined = rows(
        graph,
        f"""
        MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease {{id: 'MONDO:0005148'}})
        MATCH (drug:Drug {{id: '{CHEMBL_GOLDEN["metformin"]}'}})
              -[g:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->(t)
        WITH t, collect(DISTINCT r.direction) AS direction_in_t2d,
             count(DISTINCT r.study_id) AS t2d_studies,
             collect(DISTINCT g.effect) AS metformin_growth_effect,
             collect(DISTINCT g.nt_code) AS isolates,
             collect(DISTINCT g.source_relation) AS wording
        RETURN t.title AS taxon, direction_in_t2d, t2d_studies,
               metformin_growth_effect, isolates, wording,
               'competing explanation' AS reading
        ORDER BY t2d_studies DESC
        """,
    )
    assert len(joined) == PARTIAL_GOLDEN["d18_screen_t2d_taxa"]
    for row in joined:
        assert row["metformin_growth_effect"] == ["no-effect"], row
        assert row["isolates"], row
        # G3: the source's own wording survives the normalisation, so a reader
        # can see the threshold the call rests on rather than trusting `effect`.
        assert all("adjusted p" in w for w in row["wording"]), row
    # The old leg is untouched and still 17 — two legs, two questions.
    assert (
        len(
            rows(
                graph,
                f"""
        MATCH (t:Taxon)-[:ASSOCIATED_WITH]->(:Disease {{id: 'MONDO:0005148'}})
        MATCH (t)-[:ABUNDANCE_CHANGED_BY]->(:Intervention)
              -[:IS_DRUG]->(:Drug {{id: '{CHEMBL_GOLDEN["metformin"]}'}})
        RETURN DISTINCT t.id AS taxon
        """,
            )
        )
        == PARTIAL_GOLDEN["d18_t2d_taxa"]
    )


def test_d18_the_screen_widens_the_question_past_metformin(graph):
    """D18 is a template, not one drug. Every T2D taxon can now be handed the
    full list of drugs measured against it — **380** that inhibit at least one
    of the 32, of which **186** are human-targeted rather than antibacterial.
    That is the shape of the confounding question Forslund generalised to: of
    41 drug categories, 19 associated singly with the microbiome and only 6
    survived multi-drug correction."""
    result = one(
        graph,
        """
        MATCH (t:Taxon)-[:ASSOCIATED_WITH]->(:Disease {id: 'MONDO:0005148'})
        MATCH (d:Drug)-[g:INHIBITS_GROWTH_OF]->(t)
        RETURN count(DISTINCT t) AS taxa, count(DISTINCT d) AS drugs,
               count(DISTINCT CASE WHEN g.drug_class = 'human-targeted drugs'
                                   THEN d.id END) AS human_targeted
        """,
    )
    assert result["taxa"] == PARTIAL_GOLDEN["d18_t2d_taxa_inhibited_by_something"]
    assert result["drugs"] == PARTIAL_GOLDEN["d18_t2d_inhibiting_drugs"]
    assert (
        result["human_targeted"] == PARTIAL_GOLDEN["d18_t2d_human_targeted_inhibitors"]
    )


def test_d18_three_of_forslunds_four_named_taxa_are_now_screened(graph):
    """The reason D18 was `partial` was that gutMDisorder curated a metformin
    edge for none of *Escherichia*, *Intestinibacter* or *Lactobacillus* — only
    *Bifidobacterium* of the named set. The screen ran three of the four at
    species level, so the query answers with the taxa the confounding
    literature names rather than with the taxa this corpus happens to have.

    **The fourth is why the status does not become `answerable-now`:**
    *Intestinibacter* is in the taxonomy and was not one of the 40 isolates, so
    the decrease Forslund calls the most consistent metformin effect of the
    four has no growth measurement here and cannot get one from this source."""
    screened = {
        r["taxon"]
        for r in rows(
            graph,
            "MATCH (d:Drug)-[:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->(t:Taxon) "
            "RETURN DISTINCT t.title AS taxon",
        )
    }
    assert set(PARTIAL_GOLDEN["d18_screened_fixtures"]) <= screened
    genus = PARTIAL_GOLDEN["d18_unscreened_fixture_genus"]
    assert (
        one(
            graph,
            f"MATCH (t:Taxon) WHERE t.lineage_genus = '{genus}' RETURN count(t) AS n",
        )["n"]
        > 0
    ), f"{genus} is not even in the taxonomy — a different gap"
    assert not rows(
        graph,
        "MATCH (d:Drug)-[:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->(t:Taxon) "
        f"WHERE t.lineage_genus = '{genus}' RETURN t LIMIT 1",
    ), f"{genus} was screened after all — D18's status can be restated"

"""The ontology document is a contract, not documentation.

Guards C11 (the study-design vocabulary) and C17 (evidence completeness must
be countable), and checks that ``define_ontology(ONTOLOGY)`` is accepted by a
real kglite graph rather than merely being a well-formed dict.
"""

from __future__ import annotations

import re

import pandas as pd
import pytest

from microbiomekg.ontology import EVIDENCE_LEVELS, ONTOLOGY

from conftest import read_bugsigdb

kglite = pytest.importorskip("kglite")


# The seven atomic values of BugSigDB's `Study design`, read off the real
# 2026-09-02 export. Note the comma *inside* the second one: the column is
# comma-joined, so it cannot be split on its own delimiter (C11).
BUGSIGDB_DESIGNS = (
    "cross-sectional observational, not case-control",  # longest first
    "time series / longitudinal observational",
    "randomized controlled trial",
    "laboratory experiment",
    "prospective cohort",
    "case-control",
    "meta-analysis",
)

# Artefacts a naive `value.split(",")` produces. None is a study design.
NAIVE_SPLIT_ARTEFACTS = ("cross-sectional observational", "not case-control")

# The evidence contract from Part A1/A2, as concept -> accepted property
# spellings. The test asserts one spelling of each concept is required; it
# does not dictate which, because the field names are docs/model.md's call.
EVIDENCE_CONCEPTS = {
    "evidence level": ("evidence_level", "evidenceLevel", "evidence"),
    "study design": ("study_design", "studyDesign", "design"),
    "direction": ("direction", "abundance_direction", "effect_direction"),
    "sample size (group 0)": ("group_0_size", "group0_sample_size", "n_group0"),
    "sample size (group 1)": ("group_1_size", "group1_sample_size", "n_group1"),
    "source": ("source", "source_db", "source_database", "source_id"),
    "paper": ("pmid", "doi", "paper_id"),
}

# A relationship is an *association* — the thing A1 is about — when it carries
# both a direction and a study design. That is what separates the taxon-disease
# edge from provenance edges such as REPORTED_BY, which also carry a `source`
# but are written by this repo and may legitimately be enforced at `error`.
ASSOCIATION_MARKERS = (
    EVIDENCE_CONCEPTS["direction"],
    EVIDENCE_CONCEPTS["study design"],
)


def split_designs(value: str) -> list[str]:
    """Split against the known vocabulary, longest match first (C11)."""
    if value == "NA":
        return []
    rest, out = value, []
    while rest:
        for design in BUGSIGDB_DESIGNS:
            if rest.startswith(design):
                out.append(design)
                rest = rest[len(design):].lstrip(",")
                break
        else:
            raise AssertionError(f"unknown study design token in {value!r}: {rest!r}")
    return out


def association_relationships() -> dict[str, dict]:
    """Relationships that declare any evidence property as required.

    ONTOLOGY does not name its association edges explicitly (see the interface
    gap noted in Part C20), so they are identified by the property set they
    carry. That is enough to catch the real defect class — one evidence field
    declared, another forgotten.
    """
    out = {}
    for rel, decl in ONTOLOGY.get("relationships", {}).items():
        required = set(decl.get("required_properties", ()))
        if all(required & set(marker) for marker in ASSOCIATION_MARKERS):
            out[rel] = decl
    return out


# --------------------------------------------------------------------------
# C11 — the study-design vocabulary
# --------------------------------------------------------------------------


def test_evidence_levels_cover_every_fixture_design():
    """C11: every atomic design in the fixture maps to an evidence level."""
    seen = set()
    for row in read_bugsigdb():
        seen.update(split_designs(row["Study design"]))
    assert seen, "fixture has no study designs at all"
    missing = seen - set(EVIDENCE_LEVELS)
    assert not missing, f"EVIDENCE_LEVELS has no entry for {sorted(missing)}"


def test_evidence_levels_cover_the_whole_bugsigdb_vocabulary():
    """C11: not just what the fixture happens to contain."""
    missing = set(BUGSIGDB_DESIGNS) - set(EVIDENCE_LEVELS)
    assert not missing, f"EVIDENCE_LEVELS has no entry for {sorted(missing)}"


def test_naive_comma_split_is_not_the_design_vocabulary():
    """C11: `cross-sectional observational` and `not case-control` are artefacts.

    Their presence as keys is the fingerprint of a `value.split(",")` loader.
    """
    for artefact in NAIVE_SPLIT_ARTEFACTS:
        assert artefact not in EVIDENCE_LEVELS, (
            f"{artefact!r} is half of `cross-sectional observational, not "
            f"case-control` — the design column was split on its delimiter"
        )


def test_the_multi_design_fixture_row_splits_into_two_known_designs():
    """C11: `bsdb:27171425/1/1` is `case-control,meta-analysis`."""
    rows = {r["BSDB ID"]: r for r in read_bugsigdb()}
    assert split_designs(rows["bsdb:27171425/1/1"]["Study design"]) == [
        "case-control",
        "meta-analysis",
    ]
    assert split_designs(rows["bsdb:22949626/2/2"]["Study design"]) == [
        "cross-sectional observational, not case-control"
    ]


def test_evidence_levels_values_are_the_declared_levels():
    """A1: the level distinguishes interventional from observational."""
    assert EVIDENCE_LEVELS["randomized controlled trial"] != EVIDENCE_LEVELS[
        "case-control"
    ], "an RCT and a case-control study are not the same evidence level"
    assert EVIDENCE_LEVELS["laboratory experiment"] != EVIDENCE_LEVELS[
        "case-control"
    ], "an in-vitro experiment and an observational study are not the same level"
    assert all(isinstance(v, str) and v for v in EVIDENCE_LEVELS.values())


# --------------------------------------------------------------------------
# C17 — evidence completeness must be countable
# --------------------------------------------------------------------------


def test_ontology_declares_association_relationships():
    assert association_relationships(), (
        "no relationship in ONTOLOGY requires any evidence property — "
        "ontology_audit() can then never report missing evidence (C17)"
    )


def test_every_evidence_property_is_required_on_associations():
    """C17: one field forgotten is one field ontology_audit() cannot count."""
    for rel, decl in association_relationships().items():
        required = set(decl.get("required_properties", ()))
        for concept, spellings in EVIDENCE_CONCEPTS.items():
            assert required & set(spellings), (
                f"{rel} does not require any property for {concept!r}; "
                f"tried {spellings}"
            )


def test_evidence_rules_are_not_enforcement_error():
    """C17: these describe upstream data reality — `warn`, never `error`.

    `error` fails the build and writes no output file; 621 rows of the real
    dump have no taxa and 58 have no PMID. Per KGLite's ontology guide, rules
    about upstream reality belong in the build log, not the exit code.
    """
    for rel, decl in association_relationships().items():
        enforcement = decl.get("enforcement", "advisory")
        if isinstance(enforcement, dict):
            enforcement = enforcement.get("required_properties", "advisory")
        assert enforcement != "error", (
            f"{rel}.required_properties is `error`: the build will refuse the "
            f"real BugSigDB export"
        )
        assert enforcement == "warn", (
            f"{rel}.required_properties is {enforcement!r}; `advisory` keeps it "
            f"out of the build report, which is where A1 says it belongs"
        )


# --------------------------------------------------------------------------
# The document must be accepted by a real kglite graph
# --------------------------------------------------------------------------


def concrete_classes() -> list[str]:
    return [
        name
        for name, decl in ONTOLOGY.get("classes", {}).items()
        if not decl.get("abstract", False)
    ]


@pytest.fixture
def declared_graph():
    """A graph holding one node per concrete class and one edge per relationship.

    define_ontology() warns about a concrete class naming no live node type,
    so the ontology can only be validated against a graph that actually has
    those types.
    """
    g = kglite.KnowledgeGraph()
    for i, cls in enumerate(concrete_classes(), start=1):
        g.add_nodes(
            pd.DataFrame({"id": [f"{cls}-{i}a", f"{cls}-{i}b"], "title": [cls, cls]}),
            cls,
            "id",
            "title",
        )
    for rel, decl in ONTOLOGY.get("relationships", {}).items():
        src, dst = decl.get("domain"), decl.get("range")
        if src not in concrete_classes() or dst not in concrete_classes():
            continue  # abstract endpoint: materialisation is the build's job
        g.add_connections(
            pd.DataFrame({"s": [f"{src}-{concrete_classes().index(src) + 1}a"],
                          "t": [f"{dst}-{concrete_classes().index(dst) + 1}b"]}),
            rel,
            src,
            "s",
            dst,
            "t",
        )
    return g


def test_define_ontology_is_accepted_by_kglite(declared_graph):
    """A malformed document raises ValueError; a stale one returns warnings."""
    warnings = declared_graph.define_ontology(ONTOLOGY)
    assert warnings == [], f"define_ontology returned warnings: {warnings}"


def test_ontology_audit_runs_and_reports_every_declared_rule(declared_graph):
    """C17: the audit is the deliverable, so it must actually produce rows."""
    declared_graph.define_ontology(ONTOLOGY)
    rows = list(
        declared_graph.cypher(
            "CALL ontology_audit() YIELD rule, severity, violations, exempted, total, pct"
        )
    )
    assert rows, "ontology_audit() returned nothing for a declared ontology"
    rules = {r["rule"] for r in rows}
    for rel in association_relationships():
        assert f"{rel}.required_properties" in rules, (
            f"ontology_audit() has no {rel}.required_properties rule"
        )


def test_class_names_do_not_shadow_each_other():
    """kglite refuses an abstract class that shadows a live node type."""
    names = list(ONTOLOGY.get("classes", {}))
    assert len(names) == len(set(names))
    for name in names:
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name), name


def test_the_checked_in_ontology_json_matches_the_module():
    """The blueprint gates on `ontology.json`; the module is where it is edited.

    A drifted artifact is worse than none: the build then audits property
    names nothing writes, so every edge is flagged for a field that does not
    exist while the real gaps go uncounted. Regenerate with
    `python -m microbiomekg.ontology`.
    """
    import json as _json
    from pathlib import Path as _Path

    artifact = _Path(__file__).resolve().parents[1] / "ontology.json"
    if not artifact.is_file():
        pytest.skip("no checked-in ontology.json to compare against")
    assert _json.loads(artifact.read_text()) == ONTOLOGY, (
        "ontology.json has drifted from microbiomekg/ontology.py — "
        "run `python -m microbiomekg.ontology` to regenerate it"
    )


def test_is_a_forest_has_no_dangling_parents():
    classes = ONTOLOGY.get("classes", {})
    for name, decl in classes.items():
        parent = decl.get("is_a")
        if parent is not None:
            assert parent in classes, f"{name} is_a {parent!r}, which is not declared"


def test_relationship_endpoints_are_declared_classes():
    classes = set(ONTOLOGY.get("classes", {}))
    for rel, decl in ONTOLOGY.get("relationships", {}).items():
        for side in ("domain", "range"):
            if side in decl:
                assert decl[side] in classes, f"{rel}.{side} = {decl[side]!r} undeclared"

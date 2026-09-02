"""The declared semantic layer and the evidence-level vocabulary.

:data:`ONTOLOGY` is the document handed to ``KnowledgeGraph.define_ontology``
and written to ``ontology.json`` for the blueprint's build-time gate. Its point
is the ``required_properties`` declaration on ``ASSOCIATED_WITH``: that is what
turns "does this taxon–disease edge say how it was demonstrated?" from an
opinion into a number ``ontology_audit()`` reports on every rebuild.

:data:`EVIDENCE_LEVELS` maps a single BugSigDB study-design string to a coarse
evidence level; :func:`evidence_level` refines an observational one using the
sequencing type and host species.
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = [
    "ONTOLOGY",
    "EVIDENCE_LEVELS",
    "OBSERVATIONAL_BY_SEQUENCING",
    "NON_HOST_SPECIES",
    "evidence_level",
    "split_study_designs",
    "write_json",
]

# ---------------------------------------------------------------- evidence

#: BugSigDB "Study design" atom → coarse evidence level. The keys are the seven
#: atomic strings BugSigDB uses; a cell may carry several of them joined by
#: commas, which is why :func:`split_study_designs` exists — one of the keys
#: *contains a comma itself*, so a naive ``str.split(",")`` shreds it.
EVIDENCE_LEVELS: dict[str, str] = {
    "randomized controlled trial": "interventional-rct",
    "laboratory experiment": "in-vitro",
    "meta-analysis": "meta-analysis",
    "case-control": "observational",
    "cross-sectional observational, not case-control": "observational",
    "prospective cohort": "observational",
    "time series / longitudinal observational": "observational",
}

#: An observational design is only as strong as what it measured with.
OBSERVATIONAL_BY_SEQUENCING: dict[str, str] = {
    "WMS": "observational-shotgun",
    "16S": "observational-16S",
    "ITS / ITS2": "observational-amplicon",
    "18S": "observational-amplicon",
    "PCR": "observational-targeted",
}

#: Host species that make a result animal-model evidence rather than human.
NON_HOST_SPECIES: frozenset[str] = frozenset({"", "NA", "Not specified", "Homo sapiens"})

#: Precedence when a study declares several designs at once. First match wins.
_DESIGN_PRECEDENCE: tuple[str, ...] = (
    "laboratory experiment",
    "randomized controlled trial",
    "meta-analysis",
    "case-control",
    "prospective cohort",
    "time series / longitudinal observational",
    "cross-sectional observational, not case-control",
)


def split_study_designs(cell: str | None) -> list[str]:
    """Split a BugSigDB "Study design" cell into its atomic designs.

    ``"cross-sectional observational, not case-control"`` is itself one design
    containing a comma, and BugSigDB joins multiple designs with commas and no
    space. Splitting on ``","`` therefore produces two bogus atoms out of one
    real design (~4,200 of 14,846 rows). Longest-key-first substring matching
    is used instead, which is unambiguous because no key is a substring of
    another.
    """
    if not cell:
        return []
    text = cell.strip()
    if text in ("", "NA"):
        return []
    found: list[tuple[int, str]] = []
    for key in sorted(EVIDENCE_LEVELS, key=len, reverse=True):
        start = 0
        while (pos := text.find(key, start)) != -1:
            if not any(a <= pos < a + len(k) for a, k in found):
                found.append((pos, key))
            start = pos + 1
    return [k for _, k in sorted(found)]


def evidence_level(
    study_design: str | None,
    sequencing_type: str | None = None,
    host_species: str | None = None,
) -> str:
    """Derive the ``evidence_level`` an association edge carries.

    Precedence, first match wins:

    1. a laboratory experiment is ``in-vitro`` when no live host is named,
       ``in-vivo-model`` when one is;
    2. any non-human host makes the result ``in-vivo-model``, whatever the
       design — a mouse RCT is not human interventional evidence;
    3. ``interventional-rct`` / ``meta-analysis`` by design;
    4. an observational design is refined by what it sequenced;
    5. anything left is ``unknown`` — never silently "observational".
    """
    designs = split_study_designs(study_design)
    seq = (sequencing_type or "").strip()
    host = (host_species or "").strip()
    non_human = host not in NON_HOST_SPECIES

    if "laboratory experiment" in designs:
        return "in-vivo-model" if non_human else "in-vitro"
    if non_human and designs:
        return "in-vivo-model"

    for design in _DESIGN_PRECEDENCE:
        if design not in designs:
            continue
        level = EVIDENCE_LEVELS[design]
        if level != "observational":
            return level
        if seq in OBSERVATIONAL_BY_SEQUENCING:
            return OBSERVATIONAL_BY_SEQUENCING[seq]
        return "observational-unspecified"
    return "unknown"


# ---------------------------------------------------------------- ontology

#: The nine properties every taxon–disease association edge must carry. This
#: list *is* the project's thesis: the audit's ``ASSOCIATED_WITH
#: .required_properties`` row is the fraction of associations that do not say
#: how they were demonstrated.
EVIDENCE_CONTRACT: list[str] = [
    "direction",
    "study_design",
    "evidence_level",
    "sequencing_type",
    "statistical_test",
    "group_0_size",
    "group_1_size",
    "pmid",
    "source",
    "signature_id",
]

ONTOLOGY: dict = {
    "classes": {
        # Abstract only where it buys a union endpoint a flat schema cannot
        # declare: REPORTED_BY runs from *either* a resolved Taxon or the
        # UnresolvedTaxon placeholder, and `by: 'domain_class'` then splits the
        # audit by which of the two it came from.
        "ReportedTaxon": {
            "abstract": True,
            "description": "An organism as some source named it — resolved to NCBI or not.",
        },
        "Taxon": {
            "is_a": "ReportedTaxon",
            "description": "An NCBI Taxonomy node, keyed by tax_id.",
        },
        "UnresolvedTaxon": {
            "is_a": "ReportedTaxon",
            "description": "A source's organism string that no NCBI id could be resolved for.",
        },
        "Disease": {"description": "A condition, keyed by EFO id where the source gives one."},
        "BodySite": {"description": "An anatomical site, keyed by UBERON id."},
        "Study": {"description": "One curated study — the unit that carries a citation."},
        "Signature": {
            "description": "One curated differential-abundance result: a taxon set with "
            "a direction, measured in one experiment."
        },
        "Paper": {"description": "A publication, keyed by PMID."},
    },
    "relationships": {
        # Parent pointers only. `ancestry`, never `transitive`: the closure is
        # not stored, so `transitive` would enroll transitivity_violation and
        # report ~100% violations on a correct graph.
        "HAS_PARENT": {
            "domain": "Taxon",
            "range": "Taxon",
            "ancestry": True,
            "cardinality": {"max": 1},
            "description": "NCBI parent pointer; walk it with -[:HAS_PARENT*1..]->.",
        },
        # The headline contract.
        "ASSOCIATED_WITH": {
            "domain": "Taxon",
            "range": "Disease",
            "required_properties": EVIDENCE_CONTRACT,
            "property_types": {
                "direction": "string",
                "study_design": "string",
                "evidence_level": "string",
                "sequencing_type": "string",
                "statistical_test": "string",
                "group_0_size": "integer",
                "group_1_size": "integer",
                "pmid": "integer",
                "source": "string",
                "signature_id": "string",
            },
            # warn, not error, and permanently: the gaps are upstream curation
            # reality (BugSigDB is missing group sizes on ~17% of signatures).
            # Failing the build on someone else's missing data would only mean
            # never building. `property_types` is ours — our prep writes the
            # column types — so that one is an error.
            "enforcement": {"required_properties": "warn", "property_types": "error"},
            "description": "Differential abundance of a taxon in a condition, with the "
            "evidence that established it. One edge per (signature, taxon).",
        },
        "REPORTED_BY": {
            "domain": "ReportedTaxon",
            "range": "Signature",
            # No `required`: most Taxon nodes are ancestors pulled in to keep
            # HAS_PARENT walkable, and an ancestor no signature named is
            # correct, not a gap.
            # `source` is on the edge but deliberately not *declared* here:
            # this edge asserts "the name as reported, and how it reconciled",
            # not an evidence claim. Declaring it would file REPORTED_BY as an
            # association edge for anything reading the ontology by shape.
            "required_properties": ["reported_name", "resolution_status"],
            "property_types": {
                "reported_name": "string",
                "resolution_status": "string",
                # The source's rank claim and NCBI's own rank for the same id
                # are different facts and are stored as different properties
                # (C21.4): MetaPhlAn's prefix vocabulary has no `subspecies`.
                "reported_rank": "string",
                "original_rank": "string",
                "resolution_normalized": "boolean",
            },
            # Ours, unconditionally written by prep_bugsigdb.py: a violation is
            # a bug in this repo, so it fails the build.
            "enforcement": {"required_properties": "error", "property_types": "error"},
            "description": "The taxon as a signature named it, with how it reconciled.",
        },
        "PART_OF_STUDY": {
            "domain": "Signature",
            "range": "Study",
            "required": True,
            "cardinality": {"min": 1, "max": 1},
            "inverse_name": "HAS_SIGNATURE",
            "enforcement": {"cardinality": "error", "required": "error"},
            "description": "Every signature belongs to exactly one study.",
        },
        # No `cardinality: {max: 1}` on either of these, and that is a data
        # fact, not an oversight: 329 BugSigDB signatures name two conditions
        # and 462 name two body sites (comma-joined in one cell), so both are
        # genuinely one-to-many and are loaded from junction CSVs.
        "IN_CONDITION": {
            "domain": "Signature",
            "range": "Disease",
            "required": True,
            "inverse_name": "HAS_SIGNATURE",
            "enforcement": {"required": "warn"},
            "description": "A condition the signature contrasts. Multi-valued upstream.",
        },
        "AT_BODY_SITE": {
            "domain": "Signature",
            "range": "BodySite",
            "required": True,
            "enforcement": {"required": "warn"},
            "description": "Where the sample was taken. Multi-valued upstream.",
        },
        "PUBLISHED_AS": {
            "domain": "Study",
            "range": "Paper",
            "cardinality": {"max": 1},
            "enforcement": {"cardinality": "error"},
            "description": "The citation for a study. Absent when BugSigDB has no PMID.",
        },
    },
}


def write_json(path: str | Path = "ontology.json") -> Path:
    """Write :data:`ONTOLOGY` where the blueprint's ``ontology`` key points."""
    p = Path(path)
    p.write_text(json.dumps(ONTOLOGY, indent=2) + "\n", encoding="utf-8")
    return p


if __name__ == "__main__":  # python -m microbiomekg.ontology [path]
    import sys

    print(write_json(sys.argv[1] if len(sys.argv) > 1 else "ontology.json"))

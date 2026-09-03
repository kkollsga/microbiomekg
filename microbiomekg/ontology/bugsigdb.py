"""BugSigDB's half of the ontology: the signature, and what a signature says.

Everything here exists because BugSigDB curates *sets* — a signature is a taxon
set that moved in one direction in one experiment — and the set has to survive
into the graph or the enrichment use case (W1/D1) is impossible. The
association edges themselves are declared in :mod:`.core`; this source writes
rows into them and adds the nodes and provenance edges only it has.
"""

from __future__ import annotations

from .vocabulary import register_source

__all__ = ["ASSOCIATION_RELATIONSHIPS", "CLASSES", "RELATIONSHIPS", "SOURCE"]

SOURCE = "bugsigdb"

#: **BugSigDB is `statistical_association` + `manual_agent`.** The assertion an
#: edge carries is "this taxon's abundance differed significantly between these
#: two groups" — a statistical association, not a knowledge assertion about
#: causation and not a prediction. The *agent* is a person: a named curator read
#: a published figure or table and transcribed it, with a curation date and a
#: review state on the row. It is deliberately not `data_analysis_pipeline`,
#: which would be right for a resource that re-ran the statistics itself.
#: The licence is the one the export declares on its own first line.
register_source(
    SOURCE,
    knowledge_level="statistical_association",
    agent_type="manual_agent",
    licence="CC-BY-4.0",
)

#: BugSigDB declares no association relationship of its own — it writes rows
#: into the three :mod:`.core` declares.
ASSOCIATION_RELATIONSHIPS: tuple[str, ...] = ()

CLASSES: dict[str, dict] = {
    "BodySite": {"description": "An anatomical site, keyed by UBERON id."},
    "Signature": {
        "description": "One curated differential-abundance result: a taxon set with "
        "a direction, measured in one experiment."
    },
}

RELATIONSHIPS: dict[str, dict] = {
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
    # No `cardinality: {max: 1}`, and that is a data fact, not an oversight:
    # 329 BugSigDB signatures name two conditions and 462 name two body sites
    # (comma-joined in one cell), so both are genuinely one-to-many and are
    # loaded from junction CSVs.
    #
    # `required` here now counts what §4 always wanted it to: signatures with
    # **no condition of any kind**. It used to count signatures with no
    # *disease*-coded one, because the relation was split across
    # IN_CONDITION / IN_PHENOTYPE / IN_EXPOSURE and the ontology cannot say
    # "at least one of these three" — so `required` on all three reported ~99%
    # violations on the two narrow ones and `required` on one over-counted.
    # The union target made the question askable of a single rule.
    "IN_CONDITION": {
        "domain": "Signature",
        "range": "Condition",
        "required": True,
        "inverse_name": "HAS_SIGNATURE",
        "enforcement": {"required": "warn"},
        "description": "A condition the signature contrasts — a disease, an "
        "HP-coded phenotype or a chemical, environmental or social exposure, and "
        "the node's own type says which. Multi-valued upstream. Its `required` "
        "violations are signatures naming no condition at all.",
    },
    "AT_BODY_SITE": {
        "domain": "Signature",
        "range": "BodySite",
        "required": True,
        "enforcement": {"required": "warn"},
        "description": "Where the sample was taken. Multi-valued upstream.",
    },
}

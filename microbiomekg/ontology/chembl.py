"""ChEMBL 37: approved drugs, the proteins they act on, and one microbial hook.

This source adds two node types and three relationships, and no association
edge at all — which is the point worth stating first. **ChEMBL carries no
drug↔taxon edge**, and it still does not: that layer came from the two
published screens (Maier 2018, Zimmermann 2019) and, as a curated third
opinion, from MASI. What it does
carry is `target.tax_id` on 98.4% of targets, 124 of them non-human, and 865
mechanism rows pointing at those: enough to make "which approved drugs act on a
bacterial protein?" answerable now, one join short of "which gut bacteria does
this drug inhibit?".

Three derivations are this source's own, and none of them can use the shared
``evidence_level``: ChEMBL records no study design, no host and no assay, so
the shared derivation would return ``unknown`` for every row and lose the one
distinction the data does support — an approved label is a different claim from
a paper.

**The licence is load-bearing.** ChEMBL is CC BY-SA 3.0, i.e. copyleft: a
derived work incorporating this slice must itself be shared under CC BY-SA, and
this is the only source in the graph that imposes that. Carrying it per edge and
per node (G3) is what lets the rest of the graph be redistributed on its own
terms. The FTP ``REQUIRED.ATTRIBUTION`` also asks that ChEMBL IDs be preserved
and the release number displayed, so :data:`RELEASE` rides on every node and
edge rather than living only in ``docs/sources.md``.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .vocabulary import DRUG_DESCRIPTION, register_source

__all__ = [
    "APPROVED_PHASE",
    "ASSOCIATION_RELATIONSHIPS",
    "ATTRIBUTION",
    "CLASSES",
    "LICENCE",
    "LITERATURE_REF_TYPES",
    "MECHANISM_CONTRACT",
    "MECHANISM_PROPERTY_TYPES",
    "PUBLICATION_PREFIXES",
    "REGULATORY_REF_TYPES",
    "RELATIONSHIPS",
    "RELEASE",
    "SOURCE",
    "evidence_level",
    "max_phase",
    "publication_curie",
]

SOURCE = "chembl"

#: Displayed on every node and edge, because the attribution terms ask for it
#: and a release number in a prose file is not attached to the data it
#: describes. ChEMBL 37 is what ``scripts/fetch.py`` pulled on 2026-09-02.
RELEASE = "ChEMBL 37"
ATTRIBUTION = "ChEMBL 37 — Mendez et al. 2019, Nucleic Acids Res 47(D1):D930–D940"
LICENCE = "CC-BY-SA-3.0"

#: Every mechanism row is a curator's assertion backed by a typed reference —
#: not a statistical association the way a differential-abundance result is.
#: "Drug X inhibits protein Y" is a knowledge assertion; that is what
#: distinguishes this source's edges from BugSigDB's in one WHERE clause.
register_source(
    SOURCE,
    knowledge_level="knowledge_assertion",
    agent_type="manual_agent",
    licence=LICENCE,
)

#: ChEMBL declares no association relationship: it has no taxon endpoint.
ASSOCIATION_RELATIONSHIPS: tuple[str, ...] = ()

#: ``max_phase`` value that means "approved for clinical use".
APPROVED_PHASE = 4

#: ``ref_type`` values that are a drug regulator's own label or formulary — a
#: different evidence class from a paper, and the thing that turns
#: ``max_phase = 4`` into an *approved clinical use*. Part B names DailyMed,
#: FDA and EMA; PMDA (Japan), HMA (EU heads of agencies) and BNF (the British
#: formulary) are the same artefact from other jurisdictions and are read the
#: same way rather than being silently demoted to ``unknown``.
REGULATORY_REF_TYPES: frozenset[str] = frozenset(
    {"DailyMed", "FDA", "EMA", "PMDA", "HMA", "BNF"}
)

#: ``ref_type`` values that are a published paper. Wikipedia, ISBN, Expert,
#: Patent and ``Other`` are deliberately **not** here: a mechanism carried only
#: by a textbook or an encyclopedia entry is not a measured in-vitro result, and
#: calling it one would be the F10 failure the schema survey warns about.
LITERATURE_REF_TYPES: frozenset[str] = frozenset({"PubMed", "PMC", "DOI"})

#: ``ref_type`` → the CURIE prefix a publication reference is written under.
#: ``PMC`` is literature for the level rule but has no entry here: a PMC id is
#: not a PMID, and writing one as the other is the same class of error as the
#: URL trap below.
PUBLICATION_PREFIXES: Mapping[str, str] = {"PubMed": "PMID", "DOI": "DOI"}


def max_phase(value: Any) -> int | None:
    """``max_phase`` as an int, whichever of its two spellings arrived.

    The field is the **integer** ``4`` on a mechanism row and the **string**
    ``"4.0"`` on a molecule row — the same fact in two types in two files, so
    ``mechanism["max_phase"] == molecule["max_phase"]`` is false for every pair
    and a build that compares them raw finds no approved molecule at all.
    Returns ``None`` for absent or unparseable values rather than a plausible
    ``0``: ``-1`` is a real ChEMBL phase and a default would collide with it.
    """
    if value is None or value == "":
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def publication_curie(ref: Mapping[str, Any]) -> str | None:
    """A ``mechanism_refs`` entry as a publication CURIE, or ``None``.

    Two real rows put a PMC **URL** in a ``PubMed`` ``ref_id``, so the id is
    validated as digits before it is written as ``PMID:<id>``. Writing it
    through would mint ``PMID:https://www.ncbi.nlm.nih.gov/...``, which no
    lookup resolves and which reads as a citation everywhere downstream.
    """
    prefix = PUBLICATION_PREFIXES.get(str(ref.get("ref_type") or ""))
    ref_id = str(ref.get("ref_id") or "").strip()
    if not prefix or not ref_id:
        return None
    if prefix == "PMID" and not ref_id.isdigit():
        return None
    return f"{prefix}:{ref_id}"


def evidence_level(phase: Any, ref_types: Iterable[str]) -> str:
    """Derive ``evidence_level`` for one ChEMBL mechanism.

    Precedence, first match wins:

    1. ``max_phase = 4`` **and** a regulatory reference → ``interventional-rct``.
       Part B admits an approved clinical use to that rung: the label is a
       regulator's finding that the mechanism supports an approved indication.
       Both halves are required — a phase-2 molecule with a DailyMed reference
       is a label for something else, and phase 4 with only a paper is not an
       approved *mechanism* claim.
    2. references that are **all** literature → ``in-vitro``. Part B's reading:
       a mechanism whose only support is published papers is a measured
       molecular result, not a clinical one. "All", not "any" — one Wikipedia
       entry in the set means the mechanism is not carried by papers alone.
    3. otherwise ``unknown``, including the 0.6% of rows with no references at
       all. Never ``computational-predicted``: nothing in this subset is
       predicted, and never a defaulted ``in-vitro``.
    """
    types = {str(t) for t in ref_types}
    if max_phase(phase) == APPROVED_PHASE and types & REGULATORY_REF_TYPES:
        return "interventional-rct"
    if types and types <= LITERATURE_REF_TYPES:
        return "in-vitro"
    return "unknown"


#: What every ``HAS_MECHANISM`` edge must carry. Deliberately **not** the
#: fourteen-field :data:`~.vocabulary.EVIDENCE_CONTRACT`: eight of those fields
#: describe a differential-abundance observation (direction, group sizes,
#: sequencing type, statistical test) and a drug–protein mechanism has none of
#: them. Requiring them would report ~100% violations that mean "this is not an
#: abundance study" rather than "this evidence is missing", and an audit row
#: that always reads 100% is one nobody looks at again.
#:
#: These seven are the §5(b) provenance set plus the derived level — all of them
#: written by our prep unconditionally, which is why the rule is declared at
#: ``error``: a violation is a regression here, not a gap in ChEMBL. The gaps
#: that *are* upstream (42 ref-less rows, 577 targetless mechanisms) are
#: countable as ``evidence_level = 'unknown'`` and as ledger rows.
MECHANISM_CONTRACT: list[str] = [
    "evidence_level",
    "knowledge_level",
    "agent_type",
    "primary_source",
    "source_record_id",
    "source_licence",
    "source_relation",
]

MECHANISM_PROPERTY_TYPES: dict[str, str] = {
    "evidence_level": "string",
    "knowledge_level": "string",
    "agent_type": "string",
    "primary_source": "string",
    "source_record_id": "string",
    "source_licence": "string",
    "source_relation": "string",
    "action_type": "string",
    "mechanism_of_action": "string",
    "publications": "any",
    "regulatory_refs": "any",
    "clinical_phase": "integer",
    "direct_interaction": "boolean",
    "disease_efficacy": "boolean",
    "reported_molecule_chembl_id": "string",
    "chembl_release": "string",
}

CLASSES: dict[str, dict] = {
    "Drug": {"description": DRUG_DESCRIPTION},
    "ProteinTarget": {
        "description": "A ChEMBL target — a single protein, a complex, a family or "
        "a whole organism — with its UniProt accessions and the organism it belongs "
        "to. Only 71% are a single protein."
    },
}

RELATIONSHIPS: dict[str, dict] = {
    "HAS_MECHANISM": {
        "domain": "Drug",
        "range": "ProteinTarget",
        "required_properties": MECHANISM_CONTRACT,
        "property_types": MECHANISM_PROPERTY_TYPES,
        "enforcement": {"required_properties": "error", "property_types": "error"},
        "description": "A curated mechanism of action: one edge per ChEMBL mec_id, so "
        "two curated assertions about one drug–target pair stay two edges.",
    },
    # The join that makes ChEMBL a microbiome source rather than a pharmacology
    # one. `required` is not declared: 1.6% of targets carry no tax_id, and
    # they are real targets with real mechanisms.
    "OF_ORGANISM": {
        "domain": "ProteinTarget",
        "range": "Taxon",
        "cardinality": {"max": 1},
        "required_properties": [
            "reported_tax_id",
            "resolution_status",
            "primary_source",
        ],
        "property_types": {
            "reported_tax_id": "integer",
            "resolution_status": "string",
            "primary_source": "string",
            "organism": "string",
            "source_licence": "string",
        },
        "enforcement": {
            "cardinality": "error",
            "required_properties": "error",
            "property_types": "error",
        },
        "description": "The organism a target belongs to, resolved through the same "
        "NCBI policy every other source uses. One organism per target.",
    },
    # Declared here rather than in the gutMDisorder module because it is this
    # source that can make the claim: gutMDisorder knows nothing about ChEMBL.
    # The domain type is gutMDisorder's, which is exactly the shared-declaration
    # case microbiomekg.fragments exists for.
    "IS_DRUG": {
        "domain": "Intervention",
        "range": "Drug",
        "cardinality": {"max": 1},
        "required_properties": ["match_method", "primary_source", "source_licence"],
        "property_types": {
            "match_method": "string",
            "matched_name": "string",
            "primary_source": "string",
            "source_licence": "string",
        },
        "enforcement": {
            "cardinality": "error",
            "required_properties": "error",
            "property_types": "error",
        },
        "description": "The ChEMBL molecule an intervention names. Exact name match "
        "only, so one intervention reaches at most one drug; every near miss is a "
        "row in unresolved_chembl.csv rather than a guess.",
    },
}

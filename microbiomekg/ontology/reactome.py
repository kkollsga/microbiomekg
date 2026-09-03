"""Reactome: the pathway vocabulary, and the one clean evidence code in the set.

This source adds the ``Pathway`` node type, the ``IN_PATHWAY`` edge from a
metabolite to a pathway, and ``PART_OF_PATHWAY`` for the hierarchy. It is CC0,
which makes it the only pathway source that can ship.

**`evidence_code` is the cleanest `knowledge_level` signal in the increment and
it is 100% filled.** Every mapping row is ``TAS`` (traceable author statement —
a curator read a paper) or ``IEA`` (inferred from electronic annotation — an
orthology projection from human), and the split is 14,011 / 99,768 in
``ChEBI2Reactome.txt``. So 87.7% of what Reactome asserts about a compound is a
projection, and :data:`EVIDENCE_CODES` is what makes that one ``WHERE`` clause
away instead of invisible.

**What a Reactome hit does not say.** Its 23,603 pathways span 16 species and
every one of them is a model organism — the bacterial content is *Mycobacterium
tuberculosis* and *Plasmodium falciparum*, pathogens Reactome models for
infection pathways, and there is not a single gut commensal. A
``(Taxon)-[:PRODUCES]->(Metabolite)-[:IN_PATHWAY]->(Pathway)`` path therefore
says the *metabolite* takes part in a human (or mouse, or zebrafish) pathway.
It never says the taxon runs it. D13 labels its rows ``capability, not
production`` for exactly this reason, and that label is part of the answer
rather than a caveat attached to it.

**The hierarchy is a DAG.** 388 of 23,188 children have more than one parent, so
a loader modelling it as a tree — one parent per pathway, `cardinality: max 1` —
silently loses edges. ``PART_OF_PATHWAY`` declares no cardinality cap for that
reason, and is ``ancestry`` rather than ``transitive``: the closure is not
stored, and declaring a stored closure that does not exist reports ~100%
violations on a correct graph.

``NCBI2Reactome.txt`` is **NCBI Gene**, not NCBI Taxonomy — 73,767 numeric ids
over 16 species' pathways, with 22 of them not gene ids at all but nucleotide
accessions (`MN908947.3`, the SARS-CoV-2 reference genome). It is not loaded:
this graph has no host-gene layer to attach it to, and reading those ids as
taxids would wire 73,767 imaginary organisms into the pathway set.
"""

from __future__ import annotations

from .vocabulary import register_source

__all__ = [
    "ASSOCIATION_RELATIONSHIPS",
    "CLASSES",
    "EVIDENCE_CODES",
    "PATHWAY_CONTRACT",
    "PATHWAY_PROPERTY_TYPES",
    "RELATIONSHIPS",
    "SOURCE",
    "evidence_for",
]

SOURCE = "reactome"

#: The source-level default, used where a row carries no code of its own (the
#: hierarchy edges). Per-row values come from :func:`evidence_for`, which is
#: what the mapping files' ``evidence_code`` column deserves.
register_source(
    SOURCE,
    knowledge_level="knowledge_assertion",
    agent_type="manual_agent",
    licence="CC0-1.0",
)

#: Reactome declares no taxon–condition association.
ASSOCIATION_RELATIONSHIPS: tuple[str, ...] = ()

#: ``evidence_code`` → ``(evidence_level, knowledge_level, agent_type, eco)``.
#:
#: ``TAS`` takes ``unknown`` rather than a plausible-looking observational
#: value: Part B is explicit that the ladder describes an abundance
#: observation, a pathway membership is not one, and ``unknown`` is a real
#: countable value where a fabricated level is the F10 failure the schema
#: survey warns about. ``IEA`` is ``logical_entailment`` because an orthology
#: projection is exactly that — a conclusion drawn from a rule, not a
#: measurement and not a statistical model.
EVIDENCE_CODES: dict[str, tuple[str, str, str, str]] = {
    "TAS": ("unknown", "knowledge_assertion", "manual_agent", "ECO:0000304"),
    "IEA": (
        "computational-predicted",
        "logical_entailment",
        "automated_agent",
        "ECO:0000501",
    ),
}


def evidence_for(code: str | None) -> tuple[str, str, str, str]:
    """``(evidence_level, knowledge_level, agent_type, eco)`` for one code.

    An unrecognised code answers ``unknown`` / ``not_provided`` /
    ``not_provided`` with an empty ECO term rather than inheriting ``TAS``'s.
    The column has held exactly two values in every row of both mapping files,
    so a third would be new data and must not silently pick up a curator's
    authority.
    """
    return EVIDENCE_CODES.get(
        (code or "").strip().upper(), ("unknown", "not_provided", "not_provided", "")
    )


#: What an ``IN_PATHWAY`` edge must carry. Like ``PRODUCES``, a deliberately
#: smaller set than the association contract: a pathway membership has no
#: direction, no assay and no cohort. Every field is written by the prep, so
#: the rule can fail.
PATHWAY_CONTRACT: list[str] = [
    "evidence_level",
    "knowledge_level",
    "agent_type",
    "primary_source",
    "source_record_id",
    "source_licence",
    "source_relation",
]

PATHWAY_PROPERTY_TYPES: dict[str, str] = {
    "evidence_level": "string",
    "knowledge_level": "string",
    "agent_type": "string",
    "primary_source": "string",
    "source_record_id": "string",
    "source_licence": "string",
    "source_relation": "string",
    "evidence_code": "string",
    "eco_id": "string",
    "species": "string",
}

CLASSES: dict[str, dict] = {
    "Pathway": {
        "description": "A curated pathway, keyed `REACT:<id>` or `KEGG:<map>`. "
        "`species` is a plain-English string — neither source ships a taxid — "
        "and Reactome's 16 species are model organisms, so a pathway is never "
        "evidence that a gut taxon runs it.",
    },
}

RELATIONSHIPS: dict[str, dict] = {
    "IN_PATHWAY": {
        "domain": "Metabolite",
        "range": "Pathway",
        "required_properties": PATHWAY_CONTRACT,
        "property_types": PATHWAY_PROPERTY_TYPES,
        "enforcement": {"required_properties": "warn", "property_types": "error"},
        "description": "A metabolite that takes part in a pathway. One edge per "
        "source mapping row; `evidence_code` says whether a curator read a paper "
        "(TAS) or an orthology projection produced it (IEA).",
    },
    # No `cardinality`, on purpose: 388 children have more than one parent, and
    # a `max: 1` cap would describe a tree this data is not. `ancestry`, not
    # `transitive`: nothing stores the closure, so the transitivity check would
    # report ~100% violations on a correct load.
    "PART_OF_PATHWAY": {
        "domain": "Pathway",
        "range": "Pathway",
        "ancestry": True,
        "description": "Sub-pathway to parent pathway. A DAG, not a tree — walk "
        "it with -[:PART_OF_PATHWAY*1..]->.",
    },
}

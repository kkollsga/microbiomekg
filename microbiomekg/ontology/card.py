"""CARD: resistance determinants, and an edge whose claim is weaker than it looks.

This source adds three node types — ``ResistanceGene``, ``DrugClass`` and
``ResistanceMechanism`` — and the three relationships between them and
``Taxon``. It writes **no** rows into the ``taxon_condition`` table: CARD curates
no taxon–disease association, so nothing here lands in the shared
``ASSOCIATED_WITH`` tables and :data:`ASSOCIATION_RELATIONSHIPS` is empty.

Three things about this source are unusual enough to be declared here rather
than discovered in the prep.

**The licence is per edge, and the two halves disagree about what they cover.**
``card-data/`` is © McMaster and non-commercial; ``card-ontology/aro.obo`` is
CC BY 4.0. Part D's W6 says to "prefer the CC BY 4.0 half" — and for *names* and
the term hierarchy that works, because ``aro.obo`` names every one of the 6,451
model terms and all 587 categories. It does **not** work for the resistance
assignments themselves: 6,414 of 6,451 models get their drug class only from
``card.json``'s ``ARO_category``, and ``aro.obo``'s
``confers_resistance_to_drug_class`` covers 37. So D7's answer is in the
non-redistributable half whatever we prefer, and the honest response is to say
so per edge: :func:`licence_for` returns ``CC-BY-4.0`` for a fact ``aro.obo``
also states and ``CARD-noncommercial`` otherwise, which is exactly the case
Hetionet's per-edge licence field exists for.

**The taxon on a model is the reference sequence's organism.** Not the
resistant isolate: model 2 (``CblA-1``) is described as "found in *Bacteroides
uniformis*" and carries taxid 663108, ``mixed culture bacterium
AX_gF3SD01_15``. 132 models carry taxid 2 (Bacteria) and nothing else, and 18
carry one of 17 taxids that are a plasmid, a transposon, ``synthetic
construct`` or a metagenome — not an organism at all (``sediment metagenome``
backs two models). The edge says so in three properties rather than in prose:
``sequence_derived``, ``taxon_scope`` and :func:`taxon_specificity`.

**Only two of the twelve evidence levels can be reached from this source**, and
which one an edge gets is decided by whether CARD curated a reference sequence
for it — see :func:`evidence_level`.
"""

from __future__ import annotations

from .vocabulary import register_source

__all__ = [
    "ASSOCIATION_RELATIONSHIPS",
    "CARD_EVIDENCE_CONTRACT",
    "CARD_PROPERTY_TYPES",
    "CLASSES",
    "DATA_LICENCE",
    "META_MODEL_TYPES",
    "NOT_AN_ORGANISM_ROOTS",
    "ONTOLOGY_LICENCE",
    "RELATIONSHIPS",
    "SOURCE",
    "SPECIFICITY_VALUES",
    "evidence_level",
    "knowledge_level",
    "licence_for",
    "taxon_specificity",
]

SOURCE = "card"

#: ``card-data/`` — © McMaster University, reproducible by academic, government
#: and non-profit users, commercial use prohibited without a written licence.
#: Not an SPDX id because there is no SPDX id for it; the token is what a
#: ``WHERE r.source_licence = …`` clause filters a redistributable subgraph on.
DATA_LICENCE = "CARD-noncommercial"

#: ``card-ontology/aro.obo`` — the explicit CC BY 4.0 exception in the same
#: download. Every ARO name and every ``is_a`` parent in the graph comes from
#: here, which is why the node tables are redistributable even where the edges
#: built from ``card.json`` are not.
ONTOLOGY_LICENCE = "CC-BY-4.0"

#: CARD is expert-curated against a published inclusion bar (an MIC measured
#: over controls — quoted in full in :func:`evidence_level`), so the agent is a
#: person and the default claim is a knowledge assertion.
#: :func:`knowledge_level` downgrades the individual edges
#: that carry no citation; the registration is the source's default, and the
#: licence recorded is the one the *records* ship under.
register_source(
    SOURCE,
    knowledge_level="knowledge_assertion",
    agent_type="manual_agent",
    licence=DATA_LICENCE,
)

#: CARD curates no taxon–disease association, so it declares none of the shared
#: three. Its own relationships carry :data:`CARD_EVIDENCE_CONTRACT` instead.
ASSOCIATION_RELATIONSHIPS: tuple[str, ...] = ()

#: The two model types with no ``model_sequences`` at all — 36 models, all of
#: them a *system* rather than a gene (an efflux pump, a van gene cluster).
#: They are the source's only ``computational-predicted`` rows and its only
#: models with no taxon.
META_MODEL_TYPES: frozenset[str] = frozenset(
    {"efflux pump system meta-model", "gene cluster meta-model"}
)

#: NCBI's two non-organism subtrees, by tax_id. ``other sequences`` (28384)
#: holds plasmids, transposons and ``synthetic construct``; ``unclassified
#: sequences`` (12908) holds metagenome and ``uncultured organism`` entries.
#: 17 of CARD's 743 taxids sit under one of them, and an edge from one of those
#: is not a claim about an organism at all.
NOT_AN_ORGANISM_ROOTS: frozenset[int] = frozenset({28384, 12908})

#: What ``taxon_specificity`` may hold. Three values, because "the reference
#: sequence came from *Escherichia coli*", "…from Bacteria" and "…from plasmid
#: RP4" are three different amounts of information and a query that ranks
#: carriage claims has to be able to tell them apart with one ``WHERE``.
SPECIFICITY_VALUES: tuple[str, ...] = (
    "species-or-below",
    "above-species",
    "not-an-organism",
)


def evidence_level(has_reference_sequence: bool) -> str:
    """``in-vitro`` for a curated model, ``computational-predicted`` for a
    meta-model.

    CARD's own inclusion bar is what makes the first value right: an AMR
    determinant is admitted only when it is "described in a peer-reviewed
    scientific publication, with its DNA sequence available in GenBank,
    including clear experimental evidence of elevated minimum inhibitory
    concentration (MIC) over controls". That is an MIC measured in culture,
    which is the definition of ``in-vitro`` in Part B's table.

    The 36 meta-models have no reference sequence and no MIC of their own: they
    assert that a *set* of genes together confers resistance, which is a
    curator's model rather than a measurement of this edge. Part B files that
    as ``computational-predicted``, and D7 requires it to be excludable with one
    ``WHERE`` — which is the whole point of not defaulting both to ``in-vitro``.

    Note what neither value is: **gene presence is not phenotype.** Even a
    Perfect RGI hit "does not indicate if the AMR gene is expressed or if it
    results in elevated MIC". ``in-vitro`` here means CARD measured an MIC for
    the *reference* determinant, not that any particular organism is resistant.
    """
    return "in-vitro" if has_reference_sequence else "computational-predicted"


def knowledge_level(n_publications: int) -> str:
    """``knowledge_assertion`` with a citation, ``not_provided`` without one.

    ``PMID.tsv`` covers 2,742 of the 6,451 model ARO terms. The rest are
    curated the same way and by the same people, but this project does not
    promote "we believe a curator read something" to a knowledge assertion: the
    gap is a real, countable value, and D15 counts it.
    """
    return "knowledge_assertion" if n_publications else "not_provided"


def licence_for(also_in_ontology: bool) -> str:
    """The licence for one edge, by which half of the download states it.

    ``aro.obo`` is CC BY 4.0 and ``card-data/`` is not, so a fact both halves
    state may be redistributed and a fact only ``card.json`` states may not.
    Recording that per edge is what lets the graph ship in parts; recording one
    licence for the source would either over-claim on 13,691 drug-class edges
    or under-claim on every ARO name.
    """
    return ONTOLOGY_LICENCE if also_in_ontology else DATA_LICENCE


#: NCBI rank strings at or above genus that CARD's resolved taxids actually
#: carry. Enumerated rather than compared on a ladder, for the reason
#: ``reconcile.BELOW_SPECIES_RANKS`` gives: "above species" is not a total
#: order over NCBI's rank vocabulary. ``no rank`` is here because the one CARD
#: taxid that keeps it after promotion is a rankless group, not a strain.
_ABOVE_SPECIES: frozenset[str] = frozenset(
    {
        "genus",
        "family",
        "order",
        "class",
        "phylum",
        "kingdom",
        "domain",
        "superkingdom",
        "species group",
        "no rank",
        "clade",
    }
)


def taxon_specificity(rank: str | None, lineage: list[int] | tuple[int, ...]) -> str:
    """How much of an organism the reference sequence's taxid names.

    ``not-an-organism`` wins over everything: a plasmid node *has* rank
    ``species`` in ``nodes.dmp``, so the rank alone says the opposite of the
    truth and only the lineage can correct it. Otherwise ``above-species`` for
    anything NCBI ranks at genus or broader — 25 of CARD's 743 taxids, but 132
    models, because taxid 2 alone carries 132 of them.
    """
    if any(root in lineage for root in NOT_AN_ORGANISM_ROOTS):
        return "not-an-organism"
    if (rank or "").strip().lower() in _ABOVE_SPECIES:
        return "above-species"
    return "species-or-below"


#: What every CARD edge must carry. **Eight properties, not the shared
#: fourteen**, and the difference is deliberate. ``direction``,
#: ``sequencing_type``, ``statistical_test`` and the two group sizes describe a
#: differential-abundance observation; a resistance model is not one, and no
#: CARD release will ever fill them. Declaring them would report a permanent
#: 100% violation — a gate that cannot go green tells a reader as little as one
#: that cannot go red, and after the first build it stops being information.
#:
#: ``pmid`` is the one field here that is genuinely sometimes missing (3,717 of
#: 6,451 model terms have no ``PMID.tsv`` row), so the rule stays at ``warn``
#: and its violation fraction *means* something: it is the share of CARD edges
#: with no citation behind them.
CARD_EVIDENCE_CONTRACT: list[str] = [
    "evidence_level",
    "pmid",
    "knowledge_level",
    "agent_type",
    "primary_source",
    "source_record_id",
    "source_licence",
    "source_relation",
]

CARD_PROPERTY_TYPES: dict[str, str] = {
    "evidence_level": "string",
    "pmid": "integer",
    "knowledge_level": "string",
    "agent_type": "string",
    "primary_source": "string",
    "source_record_id": "string",
    "source_licence": "string",
    "source_relation": "string",
}


def _card_declaration(domain: str, range_class: str, description: str) -> dict:
    return {
        "domain": domain,
        "range": range_class,
        "required_properties": CARD_EVIDENCE_CONTRACT,
        "property_types": CARD_PROPERTY_TYPES,
        # `pmid` is upstream's gap, so warn; the types are ours to write, so
        # error — the same split the shared association edges use.
        "enforcement": {"required_properties": "warn", "property_types": "error"},
        "description": description,
    }


CLASSES: dict[str, dict] = {
    "ResistanceGene": {
        "description": "An antibiotic-resistance determinant, keyed on its ARO "
        "accession and backed by one CARD detection model. `model_type` says "
        "what kind of evidence detects it: a variant model means the *mutation* "
        "confers resistance, not the gene's presence."
    },
    "DrugClass": {
        "description": "A class of antibiotics a determinant confers resistance "
        "to — an ARO term of category class 'Drug Class', keyed on its ARO "
        "accession."
    },
    "ResistanceMechanism": {
        "description": "How a determinant confers resistance: inactivation, "
        "efflux, target alteration, target protection, target replacement, "
        "reduced permeability, absence, or host-dependent nutrient acquisition."
    },
}

RELATIONSHIPS: dict[str, dict] = {
    "CONFERS_RESISTANCE_TO": _card_declaration(
        "ResistanceGene",
        "DrugClass",
        "A determinant confers resistance to a class of antibiotics. One edge "
        "per (model, drug class) pair; a model naming several classes is "
        "several edges, never a joined string.",
    ),
    "VIA_MECHANISM": _card_declaration(
        "ResistanceGene",
        "ResistanceMechanism",
        "The mechanism by which a determinant confers resistance.",
    ),
    "CARRIES_RESISTANCE_GENE": _card_declaration(
        "Taxon",
        "ResistanceGene",
        "The organism CARD's reference sequence for this determinant was "
        "obtained from — NOT a claim that this organism is resistant. "
        "`sequence_derived` is true on every edge and `taxon_specificity` says "
        "how much of an organism the taxid names: 132 models carry taxid 2 "
        "(Bacteria) and 17 taxids are plasmids or synthetic constructs.",
    ),
}

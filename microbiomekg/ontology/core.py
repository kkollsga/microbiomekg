"""The shared spine: the classes and relationships more than one source writes.

A source module declares what *it* adds. This module declares what every source
lands in — the taxon side of the graph, the three condition types, the paper
and study nodes, and the association relationship itself. It is the only file
here that two source-loading agents both depend on, and a source only has to
touch it when it needs a genuinely new *shared* field.

``Taxon`` lives here rather than in an ``ncbi`` module because the NCBI dump is
not a source of associations: it is the coordinate system every source resolves
into, and the store's ``cited_taxa`` table — the list of taxa the taxonomy build
keeps — is written by all of them.
"""

from __future__ import annotations

from .vocabulary import (
    ASSOCIATION_RANGES,
    ASSOCIATION_RELATIONSHIPS as _ASSOCIATIONS,
    association_declaration,
)

__all__ = ["ASSOCIATION_RELATIONSHIPS", "CLASSES", "RELATIONSHIPS"]

#: The association relationships this module declares — the shared three.
ASSOCIATION_RELATIONSHIPS: tuple[str, ...] = _ASSOCIATIONS

CLASSES: dict[str, dict] = {
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
    # Three condition types, chosen by the CURIE's vocabulary, never by the
    # column name (C14). They are separate types rather than one with a
    # `kind` property because the schema survey's §5(a) counter-example is
    # exactly that merge: PrimeKG folded HPO phenotypes and drug side
    # effects into one type and cannot undo it.
    #
    # `Condition` is the abstract union over them, and it is what makes
    # ASSOCIATED_WITH and IN_CONDITION one relationship each: a junction edge's
    # `target` is a list plus a per-row type column (kglite 0.16.22), and the
    # ontology `range` is then the class the three are `is_a`. It is a *union*,
    # not a merge — the concrete type stays the node's own, so
    # `-[:ASSOCIATED_WITH]->(:Disease)` is still exactly the disease subset.
    "Condition": {
        "abstract": True,
        "description": "What a signature contrasts: a disease, a phenotype or an "
        "exposure. Abstract — every node is one of the three.",
    },
    "Disease": {
        "is_a": "Condition",
        "description": "A disease, keyed on its MONDO CURIE where MONDO declares "
        "an equivalence and on the source CURIE otherwise.",
    },
    "Phenotype": {
        "is_a": "Condition",
        "description": "An observable trait coded in HP — kept apart from Disease, "
        "which it is not.",
    },
    "Exposure": {
        "is_a": "Condition",
        "description": "What the subjects were exposed to or characterised by: a "
        "chemical, an environment, a social or an exposure-ontology term.",
    },
    "Study": {"description": "One curated study — the unit that carries a citation."},
    "Paper": {"description": "A publication, keyed by PMID."},
}

RELATIONSHIPS: dict[str, dict] = {
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
    # The headline contract, once. It used to be three relationship names for
    # one relation, because a blueprint junction edge named exactly one target
    # node type; kglite 0.16.22's union target retired that, so the rule the
    # audit reports covers every association rather than the disease third of
    # them (docs/model.md section 8).
    **{
        rel: association_declaration(rng)
        for rel, rng in zip(ASSOCIATION_RELATIONSHIPS, ASSOCIATION_RANGES)
    },
    "PUBLISHED_AS": {
        "domain": "Study",
        "range": "Paper",
        "cardinality": {"max": 1},
        "enforcement": {"cardinality": "error"},
        "description": "The citation for a study. Absent when the source has no PMID.",
    },
}

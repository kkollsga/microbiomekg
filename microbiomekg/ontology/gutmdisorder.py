"""gutMDisorder: interventions, and a mouse corpus that is not human evidence.

This source adds one node type and one relationship. Its taxon–disease
associations are rows in the shared ``ASSOCIATED_WITH`` tables :mod:`.core`
declares, because a junction entry names one relationship, one CSV and one
target type — so a second source's association is a row, not a second
relationship, and that is what makes D2, D3 and D17 span both sources.

What is genuinely new is the other half of the corpus: 168 of 190 mouse studies
and 86 of 325 human ones are *interventions* — "interventions change the
composition of gut microbiota" — which is a taxon changed **by** something, not
a taxon associated **with** a disease. gutMDisorder is the only surveyed source
that curates that relation, and D4's missing leg is exactly it.

Two derivations are this source's own and neither can use the shared
``evidence_level``: gutMDisorder records no study design at all, and its whole
mouse workbook is animal evidence whatever the design.
"""

from __future__ import annotations

from .vocabulary import EVIDENCE_CONTRACT, EVIDENCE_PROPERTY_TYPES, register_source

__all__ = [
    "ASSOCIATION_RELATIONSHIPS",
    "CLASSES",
    "INTERVENTION_RESEARCH_TYPES",
    "RELATIONSHIPS",
    "SOURCE",
    "evidence_level",
    "sequencing_type",
]

SOURCE = "gutmdisorder"

#: Every row is a differential-abundance result with a p-value and a named
#: test, transcribed from a paper by a human curator — the same claim shape and
#: the same agent as BugSigDB, written from this table rather than inherited
#: from it.
#:
#: **The licence is `unknown`, and that is a value, not a gap.** The site
#: states no licence and the workbooks carry none; recording `unknown` keeps
#: the fact countable (`WHERE r.source_licence = 'unknown'` is the
#: redistribution question) instead of implying a permission nobody granted.
register_source(
    SOURCE,
    knowledge_level="statistical_association",
    agent_type="manual_agent",
    licence="unknown",
)

#: gutMDisorder declares no association relationship of its own.
ASSOCIATION_RELATIONSHIPS: tuple[str, ...] = ()

#: `Research Type` values that make a human study interventional. The column has
#: exactly three values and is 100% filled, which is what makes it usable as the
#: observational-vs-interventional discriminator this source has no study-design
#: column for.
INTERVENTION_RESEARCH_TYPES: frozenset[str] = frozenset(
    {
        "Interventions change the composition of gut microbiota",
        "Gut microbiota for adjuvant therapy",
    }
)

#: `Sequencing Technology` substring → this project's assay vocabulary, most
#: specific first. The column is comma-multivalued (`16S rRNA sequences,qPCR`)
#: and free-text, so it is matched by substring and the strongest assay wins:
#: a study that ran both shotgun and 16S supports the shotgun claim.
_SEQUENCING: tuple[tuple[str, str], ...] = (
    ("shotgun", "WMS"),
    ("16s", "16S"),
    ("qpcr", "PCR"),
    ("pcr", "PCR"),
    ("denaturing gradient gel electrophoresis", "PCR"),
)


def sequencing_type(technology: str | None) -> str:
    """gutMDisorder's free-text assay → ``WMS`` / ``16S`` / ``PCR`` / ``""``.

    Mapped onto the vocabulary the graph already carries rather than kept
    verbatim, because ``r.sequencing_type = '16S'`` has to mean the same thing
    on every edge for D9 to be a single query. The source's own string is kept
    on the ``Study`` node, so the normalisation stays reversible.
    """
    text = (technology or "").strip().casefold()
    if not text:
        return ""
    for needle, value in _SEQUENCING:
        if needle in text:
            return value
    return ""


def evidence_level(
    workbook: str, research_type: str | None, technology: str | None
) -> str:
    """Derive ``evidence_level`` for one gutMDisorder association.

    1. **The whole mouse workbook is ``in-vivo-model``, whatever the design.**
       Not a simplification: 95% of published HMA-rodent studies (36/38)
       reported phenotype transfer, a rate Walter et al. call implausible, and
       G6 makes animal evidence a discounted tier rather than a weaker version
       of the human one. A mouse RCT is not human interventional evidence.
    2. A human study whose ``Research Type`` names an intervention is
       ``interventional-rct``. This is the vocabulary's own reading (Part B:
       "gutMDisorder human rows whose Research Type names an intervention"),
       and it is the loosest assignment this loader makes — the column says the
       study intervened, not that it randomised, and gutMDisorder records no
       design column to check it against.
    3. Otherwise observational, refined by what it sequenced.
    """
    if workbook == "mouse":
        return "in-vivo-model"
    if (research_type or "").strip() in INTERVENTION_RESEARCH_TYPES:
        return "interventional-rct"
    return {
        "WMS": "observational-shotgun",
        "16S": "observational-16S",
        "PCR": "observational-targeted",
    }.get(sequencing_type(technology), "observational-unspecified")


CLASSES: dict[str, dict] = {
    "Intervention": {
        "description": "Something done to the subjects that changed the microbiota: "
        "a drug, a food or another treatment, with its DrugBank id where the "
        "source gives one."
    },
}

RELATIONSHIPS: dict[str, dict] = {
    # Deliberately *not* an ASSOCIATED_WITH: "this drug changed this taxon" and
    # "this taxon is associated with this disease" are different claims with
    # different directions, and MDAD's documented weakness is collapsing the
    # two. It carries the same evidence contract, so ontology_audit() holds it
    # to the same completeness standard.
    "ABUNDANCE_CHANGED_BY": {
        "domain": "Taxon",
        "range": "Intervention",
        "required_properties": EVIDENCE_CONTRACT,
        "property_types": EVIDENCE_PROPERTY_TYPES,
        "enforcement": {"required_properties": "warn", "property_types": "error"},
        "description": "A taxon whose abundance changed under an intervention, with "
        "the evidence that established it. One edge per curated association row.",
    },
}

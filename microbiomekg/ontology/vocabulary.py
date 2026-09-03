"""The evidence vocabulary every source writes against.

This module is source-neutral on purpose. It holds the three vocabularies a
source has to speak — :data:`EVIDENCE_LEVELS` (project-controlled),
:data:`KNOWLEDGE_LEVELS` and :data:`AGENT_TYPES` (Biolink, verbatim) — the
fourteen-property :data:`EVIDENCE_CONTRACT` those values ride on, and the
per-source registries that say which values a given source is entitled to.

A source module (``microbiomekg/ontology/<source>.py``) adds its row to the
registries and, where its own columns need a different derivation, its own
``evidence_level``-shaped function. It never invents a value: a near-miss
spelling exports silently and nothing downstream recognises it, which is why
the enums are pinned here and tested.
"""

from __future__ import annotations

__all__ = [
    "AGENT_TYPES",
    "ASSOCIATION_RANGES",
    "ASSOCIATION_RELATIONSHIPS",
    "EVIDENCE_CONTRACT",
    "EVIDENCE_LEVELS",
    "EVIDENCE_LEVEL_VALUES",
    "EVIDENCE_PROPERTY_TYPES",
    "EXCHANGE_CONTRACT",
    "EXCHANGE_PROPERTY_TYPES",
    "DRUG_DESCRIPTION",
    "PRODUCTION_DESCRIPTION",
    "KNOWLEDGE_LEVELS",
    "NON_HOST_SPECIES",
    "OBSERVATIONAL_BY_SEQUENCING",
    "SOURCE_EVIDENCE",
    "SOURCE_LICENCE",
    "agent_type",
    "association_declaration",
    "evidence_level",
    "exchange_declaration",
    "knowledge_level",
    "split_study_designs",
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

#: The twelve values an ``evidence_level`` may hold, and the only twelve
#: (docs/usecases-and-pitfalls.md Part B, "The final `evidence_level`
#: vocabulary"). Eleven are emitted today; only ``text-mined`` is reserved, so
#: that a SemMedDB-class source can never land as anything else. Spelling is
#: hyphenated with ``16S`` capitalised because that is what the built edges
#: carry — a near-miss spelling is a silent filter miss, so a source that
#: writes ``observational_16s`` maps to the hyphenated form on write.
EVIDENCE_LEVEL_VALUES: tuple[str, ...] = (
    "computational-predicted",
    "text-mined",
    "unknown",
    "observational-unspecified",
    "observational-targeted",
    "observational-amplicon",
    "observational-16S",
    "observational-shotgun",
    "meta-analysis",
    "in-vitro",
    "in-vivo-model",
    "interventional-rct",
)

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


# ------------------------------------------------- Biolink evidence vocabulary

#: Biolink's ``knowledge_level`` enum, **verbatim**. This is the interoperable
#: half of A1: ``evidence_level`` above is project-controlled because ECO has no
#: term that separates 16S from shotgun differential abundance, but *how much of
#: a claim* an edge is has a portable vocabulary and this is it. A near-miss
#: spelling exports silently and nothing downstream recognises it, so the tuple
#: is pinned and tested rather than written out at each use.
KNOWLEDGE_LEVELS: tuple[str, ...] = (
    "knowledge_assertion",
    "logical_entailment",
    "prediction",
    "statistical_association",
    "text_co_occurrence",
    "observation",
    "not_provided",
)

#: Biolink's ``agent_type`` enum, verbatim. Together with
#: :data:`KNOWLEDGE_LEVELS` it replaces the single-confidence-score pattern the
#: schema survey's §5(d) argues against: "a curator asserted this" and "a
#: pipeline emitted this" are different facts and neither is a number.
AGENT_TYPES: tuple[str, ...] = (
    "manual_agent",
    "automated_agent",
    "data_analysis_pipeline",
    "computational_model",
    "text_mining_agent",
    "image_processing_agent",
    "manual_validation_of_automated_agent",
    "not_provided",
)

#: source token → its ``(knowledge_level, agent_type)``, filled in by the
#: source modules through :func:`register_source`. Empty here on purpose: a
#: source whose evidence model nobody has read must reach ``not_provided``
#: rather than inheriting a neighbour's answer.
SOURCE_EVIDENCE: dict[str, tuple[str, str]] = {}

#: source token → the licence its records ship under, as an SPDX-ish token. A
#: per-edge licence is what lets a mixed-licence graph be redistributed in parts
#: instead of not at all, and with KEGG in the source list that is not optional.
SOURCE_LICENCE: dict[str, str] = {}


def register_source(
    source: str, *, knowledge_level: str, agent_type: str, licence: str
) -> None:
    """Record what kind of claim a source's edges are, and under what licence.

    Called once per source module at import. The values are checked against the
    pinned Biolink enums here rather than at use, so a typo fails the import of
    the module that made it instead of silently exporting.
    """
    if knowledge_level not in KNOWLEDGE_LEVELS:
        raise ValueError(f"{source}: {knowledge_level!r} is not a Biolink knowledge_level")
    if agent_type not in AGENT_TYPES:
        raise ValueError(f"{source}: {agent_type!r} is not a Biolink agent_type")
    SOURCE_EVIDENCE[source] = (knowledge_level, agent_type)
    SOURCE_LICENCE[source] = licence


def knowledge_level(source: str | None) -> str:
    """Biolink ``knowledge_level`` for a source, or a countable ``not_provided``.

    Never a guess: a source nobody has read the evidence model of gets
    ``not_provided``, which is a real value one ``WHERE`` clause counts — not a
    null, and not a plausible-looking default.
    """
    return SOURCE_EVIDENCE.get(source or "", ("not_provided", "not_provided"))[0]


def agent_type(source: str | None) -> str:
    """Biolink ``agent_type`` for a source, or a countable ``not_provided``."""
    return SOURCE_EVIDENCE.get(source or "", ("not_provided", "not_provided"))[1]


# ---------------------------------------------------------------- contract

#: Every property an association edge must carry. This list *is* the project's
#: thesis: the audit's ``ASSOCIATED_WITH.required_properties`` row is the
#: fraction of associations that do not say how they were demonstrated.
#:
#: The first block is *how it was demonstrated*; the second is *who says so and
#: under what terms*, from the schema survey's §5(b) minimal provenance set.
#: ``primary_source`` and ``source_record_id`` carry what ``source`` and
#: ``signature_id`` used to, under the names a Biolink/KGX export uses — they
#: are renames, not additions, because two byte-identical strings on 110,547
#: edges is duplication, not provenance.
EVIDENCE_CONTRACT: list[str] = [
    "direction",
    "study_design",
    "evidence_level",
    "sequencing_type",
    "statistical_test",
    "group_0_size",
    "group_1_size",
    "pmid",
    "knowledge_level",
    "agent_type",
    "primary_source",
    "source_record_id",
    "source_licence",
    "source_relation",
]

#: Declared types for the contract's properties. `property_types` is enforced
#: at `error` because *we* write these columns: a type violation is a bug here,
#: not a gap upstream.
EVIDENCE_PROPERTY_TYPES: dict[str, str] = {
    "direction": "string",
    "study_design": "string",
    "evidence_level": "string",
    "sequencing_type": "string",
    "statistical_test": "string",
    "group_0_size": "integer",
    "group_1_size": "integer",
    "pmid": "integer",
    "knowledge_level": "string",
    "agent_type": "string",
    "primary_source": "string",
    "source_record_id": "string",
    "source_licence": "string",
    "source_relation": "string",
}

#: What a `Taxon` -> `Metabolite` **exchange** edge must carry, whichever source
#: wrote it. `PRODUCES` is the shared table two sources now write rows into —
#: HMDB's ontology annotation and NJC19's curated export events — so the
#: required set has to be the set *both* can fill. It is the schema survey's
#: §5(b) provenance block plus `evidence_level` and the organism string the
#: source actually said, and every one of the eight is written by a prep rather
#: than read from upstream, so the rule sits at zero and a violation is a bug
#: here (which is what makes it able to fail).
#:
#: **`hmdb_status` used to be the ninth and is not any more.** It is HMDB's
#: detection status and NJC19 has no column that could fill it; leaving it
#: required would have made every NJC19 `PRODUCES` edge a violation of a rule
#: that was meant to read zero, i.e. an audit number that means "a second
#: source landed" rather than "evidence is missing". It stays a declared,
#: type-checked property, and `tests/test_hmdb.py` asserts HMDB still writes it
#: on every edge of its own.
EXCHANGE_CONTRACT: list[str] = [
    "evidence_level",
    "knowledge_level",
    "agent_type",
    "primary_source",
    "source_record_id",
    "source_licence",
    "source_relation",
    "reported_name",
]

#: Declared types for :data:`EXCHANGE_CONTRACT`. All strings: the eight are
#: identifiers and vocabulary values, never counts.
EXCHANGE_PROPERTY_TYPES: dict[str, str] = {field: "string" for field in EXCHANGE_CONTRACT}


def exchange_declaration(description: str, extra_property_types: dict | None = None) -> dict:
    """One ``Taxon`` -> ``Metabolite`` exchange relationship declaration.

    Here rather than in a source module because ``PRODUCES`` has two authors:
    HMDB's ontology annotation and NJC19's curated export events land in one
    table, so both fragments have to declare the *same* relationship. Fragment
    merging unions a property-type dict and raises on a contradicting scalar
    (``description`` is the scalar that would contradict), so the shape both
    sources agree on is built once here and each passes only what it adds.
    """
    return {
        "domain": "Taxon",
        "range": "Metabolite",
        "required_properties": list(EXCHANGE_CONTRACT),
        "property_types": {**EXCHANGE_PROPERTY_TYPES, **(extra_property_types or {})},
        # The same split the association contract uses and for the same reason:
        # a completeness number belongs in the build report, so
        # `required_properties` warns; `property_types` is ours to write, so a
        # violation there is a bug here and errors. Unlike the association rule
        # this one *should* read zero — every field is written by a prep — and
        # each source's test asserts that it does.
        "enforcement": {"required_properties": "warn", "property_types": "error"},
        "description": description,
    }


#: The description ``PRODUCES`` carries, written for both its authors. HMDB's
#: half is an organism named in a hand-built origin ontology; NJC19's is an
#: export event read out of a paper. `primary_source` is what separates them,
#: and it is on every edge.
#: The description ``Drug`` carries, written for both its authors. `Drug` is a
#: shared node table the way `PRODUCES` is a shared edge table: ChEMBL keys it
#: on the parent molecule, and Maier 2018 mints one for each screened compound
#: no ChEMBL join route reaches. Fragment merging raises on a contradicting
#: scalar, and a class `description` is exactly that — so the sentence both
#: sources agree on is written once, here, rather than duplicated into two
#: modules that would then drift.
DRUG_DESCRIPTION: str = (
    "A drug keyed on the ChEMBL id of its parent molecule, so a salt form is "
    "the same drug rather than a second one, and on its Prestwick catalogue "
    "number for a screened compound no ChEMBL join route reaches. `approved` "
    "is false both for a molecule a mechanism names that the max_phase-4 file "
    "does not carry, and for every minted screen compound."
)


PRODUCTION_DESCRIPTION: str = (
    "An organism a source names as making this metabolite: HMDB's "
    "microbial-origin annotation, or NJC19's curated export event. One edge per "
    "(metabolite, organism, source record); the organism is free text in both "
    "sources and carries no taxid, so `reported_name` is what was said and the "
    "edge's endpoint is what it resolved to."
)


#: The relationships that carry the evidence contract, **named** rather than
#: inferred. `tests/test_ontology.py` used to work out which relationships were
#: associations by looking for a direction plus a study design, which is a
#: heuristic standing in for a declaration (C21.5).
#:
#: There is **one**, and that is the point. Until kglite 0.16.22 a blueprint
#: junction edge named exactly one target node type, so one relation over
#: `Disease` ∪ `Phenotype` ∪ `Exposure` needed three relationship names — and
#: the headline audit number then covered only the disease third of it. The
#: union target collapsed them; a query that wants only diseases says
#: `-[:ASSOCIATED_WITH]->(:Disease)`, which the three-name shape could not
#: improve on.
ASSOCIATION_RELATIONSHIPS: tuple[str, ...] = ("ASSOCIATED_WITH",)

#: The class each association relationship points at, positionally. `Condition`
#: is abstract and `Disease`/`Phenotype`/`Exposure` are `is_a` it, so the range
#: check reads the union and `ontology_audit()` reports one rule.
ASSOCIATION_RANGES: tuple[str, ...] = ("Condition",)


def association_declaration(range_class: str) -> dict:
    """One association relationship declaration."""
    return {
        "domain": "Taxon",
        "range": range_class,
        "required_properties": EVIDENCE_CONTRACT,
        "property_types": EVIDENCE_PROPERTY_TYPES,
        # warn, not error, and permanently: the gaps are upstream curation
        # reality (BugSigDB is missing group sizes on ~17% of signatures).
        # Failing the build on someone else's missing data would only mean
        # never building. `property_types` is ours — our prep writes the
        # column types — so that one is an error.
        "enforcement": {"required_properties": "warn", "property_types": "error"},
        "description": f"Differential abundance of a taxon in a "
        f"{range_class.lower()} — a disease, a phenotype or an exposure, and "
        f"the node's own type says which. Carries the evidence that established "
        f"it; one edge per (signature, taxon).",
    }

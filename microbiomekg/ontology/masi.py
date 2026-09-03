"""MASI: the aggregator, loaded as an aggregator — and the 85% of it two
primary sources in this graph already measured.

MASI (Zeng et al., *Nucleic Acids Research* 49:D776, 2021, PMC7779062) curates
microbiota–active-substance interactions **out of the primary literature**. It
is not a screen and it did not measure anything; it is a curator's index of what
other people measured. That single fact decides everything below, because two of
the papers it indexes are already in this graph as sources of their own: **5,419
of its 12,512 interaction rows cite Maier 2018 (PMID 29555994) and 2,884 cite
Zimmermann 2019 (PMID 31158845)** — 66.4% of the file — and **85.1% of the
(taxon, drug) pairs it resolves to are pairs one of those two screens already
carries an edge for**.

Six decisions this module records.

**MASI's substances are ``Substance`` nodes, never ``Drug`` nodes, and its
interaction edges never land on a relationship a primary source owns.** The
alternative — pointing a MASI metabolism edge at the ``Drug`` node its compound
joins to, and calling it ``METABOLISES`` — was rejected on a measured number
rather than on taste: it would put ~1,815 re-curations of Zimmermann's own cells
into the same relationship as those cells, so ``MATCH (t:Taxon)-[:METABOLISES]->
(d:Drug)`` — the query D8 is written as — would double-count without saying so.
An aggregated claim is a separate edge with its own provenance (schema survey
§5(b)); here it is a separate edge on a separate relationship pointing at a
separate node type, and the identity between the two is a **declared edge**,
:data:`RELATION_SAME_COMPOUND` — not a merge and not a silent one. So the
duplication is opt-in in one hop rather than opt-out in a ``WHERE`` clause
nobody writes.

**And where a duplicate exists it is named on the edge.**
``duplicates_primary_source`` carries the source token of every loaded primary
source that already measures this exact (taxon, compound) pair — ``maier2018``,
``zimmermann2019``, or both, pipe-joined — and is empty when MASI is the only
source in the graph making the claim. That is the *countable* half of the
aggregator contract: "what does MASI add that we did not already have" is one
``WHERE r.duplicates_primary_source = ''``.

**Two interaction categories, two relationship families, and the second one is
deliberately not** ``INHIBITS_GROWTH_OF``. ``Interaction_Category`` has exactly
two values over all 12,512 rows: ``Microbes metabolize substances`` (4,295) and
``Substances alter microbe abundance`` (8,217). The first is the claim
``METABOLISES`` makes, one node type over. The second is **not** growth
inhibition: its own column is ``Microbe_Change`` with values
``Increase``/``Decrease``/``No significant change``, and 995 of its rows are
``In vivo`` — an abundance shift in a host, which is what gutMDisorder's
``ABUNDANCE_CHANGED_BY`` already models. Routing it to ``INHIBITS_GROWTH_OF``
would have been doubly wrong: 4,778 of its 5,467 resolvable pairs are pairs
Maier's screen already measured, so the graph would have gained a second,
weaker copy of the one relationship D8 and D18 both read.

**A measured "no change" is its own relationship.** 507 abundance rows say
``No significant change`` and 404 metabolism rows say ``Microbe does not
metabolize drug``. Those are curated *refutations* from the primary literature,
and a refutation stored as a property is counted as an observation by every
query that does not know to exclude it — the rule ``NO_EXCHANGE_WITH``,
``DOES_NOT_INHIBIT_GROWTH_OF`` and ``DOES_NOT_METABOLISE`` already follow.
``effect`` rides on all four so the whole measured population is one property.

**``evidence_level`` is derived per row and is not ``in-vitro`` everywhere.**
:func:`evidence_level_for` reads ``Experiment_System`` and
``Experiment_Model_Species``: an in-vivo row in a non-human host is
``in-vivo-model``, an in-vitro row is ``in-vitro``, and a row whose system column
is ``n.a.`` — 2,396 of them — is ``unknown`` rather than a plausible default.
The **disease** table has no design, host or assay column at all, so every one
of its 784 rows is ``unknown``; Part B's own definition of that value is this
table.

**The taxon id comes from three places in a fixed order, and the microbe
dictionary is what saves 3,007 rows.** ``Microbe-Tax-ID`` is ``n.a.`` on 4,965
interaction rows, but ``microbesInfo`` carries an id for most of those microbes,
and a genus id for 92 more that have no id of their own. The order is the row's
own id, then the dictionary's, then the dictionary's genus — and where the first
two disagree (three microbes, 69 rows, every one a phylum id against a class id
for a name that is spelled the same at both ranks) the row's own id wins and the
disagreement is a ledger row.
"""

from __future__ import annotations

import re

from ..drugs import strip_salt
from .vocabulary import DRUG_DESCRIPTION, register_source

__all__ = [
    "ABUNDANCE_RELATIONSHIPS",
    "DECREASE",
    "INCREASE",
    "NOT_AVAILABLE",
    "REPORTED_RANK_COLUMN",
    "ASSOCIATION_RELATIONSHIPS",
    "CATEGORIES",
    "CATEGORY_ABUNDANCE",
    "CATEGORY_METABOLISM",
    "CLASSES",
    "CLASS_SUBCATEGORIES",
    "CONTRACT",
    "DISEASE_EVIDENCE_LEVEL",
    "INTERACTION_PROPERTY_TYPES",
    "METABOLISM_RELATIONSHIPS",
    "NOT_METABOLISED_MARKER",
    "NO_CHANGE",
    "PUBMED_ID",
    "BROADEST_ACCEPTED_RANK",
    "RELATIONSHIPS",
    "RELATION_ABUNDANCE_CHANGED",
    "RELATION_ABUNDANCE_UNCHANGED",
    "RELATION_METABOLISES",
    "RELATION_NO_METABOLISM",
    "RELATION_SAME_COMPOUND",
    "SOURCE",
    "SOURCE_RELATIONS",
    "SUBSTANCE_PROPERTY_TYPES",
    "TAXON_PROBIOTIC_PROPERTIES",
    "direction_of",
    "disease_key",
    "evidence_level_for",
    "is_class_substance",
    "missing",
    "normalise_disease_name",
    "publications_of",
    "relation_for_abundance",
    "relation_for_metabolism",
    "substance_key",
    "substance_variants",
]

SOURCE = "masi"

#: **Every MASI record is a curator's transcription of a published result.** The
#: database's stated inclusion criterion is an experimentally determined
#: interaction reported in the literature, and every row carries the reference it
#: was read out of — which is Biolink's ``knowledge_assertion`` by a
#: ``manual_agent``, the same pair the two screens and NJC19 carry.
#:
#: The licence token is ``MASI-unstated`` and it says what it means. Neither the
#: four downloads nor the download page states a licence, and
#: ``docs/research/researcher-workflows.md`` §1.11 records the same finding at
#: the source ("No separate database license"). Inventing ``CC-BY-4.0`` on
#: 12,000-odd edges would put a redistribution claim in the graph nobody made;
#: because G3 puts the licence on the edge, ``WHERE r.source_licence <>
#: 'MASI-unstated'`` is the cut and this token contaminates nothing else.
register_source(
    SOURCE,
    knowledge_level="knowledge_assertion",
    agent_type="manual_agent",
    licence="MASI-unstated",
)

#: MASI writes rows into the shared taxon–disease table, so it declares the
#: association relationship it lands in. Its 784 disease records fill 8 of the
#: contract's 14 properties; the other six describe a differential-abundance
#: *study* — a design, two arm sizes, a sequencing type and a statistical test —
#: and this source's disease export has no column for any of them. All 784 are
#: therefore audit violations, which is the same shape gutMDisorder's 1,636 are
#: and is the audit working rather than a rule to weaken.
ASSOCIATION_RELATIONSHIPS: tuple[str, ...] = ("ASSOCIATED_WITH",)

#: The literal string MASI writes for a missing value, in every column of every
#: one of the four tables. It is **not** an empty cell: a reader that only
#: checked for blanks would carry the three characters ``n.a.`` into
#: ``reported_name``, ``pmid`` and ``substance_category`` alike.
NOT_AVAILABLE: str = "n.a."

#: The two values ``Interaction_Category`` takes, over all 12,512 rows. They are
#: an enum in practice and are treated as one: a third value is a ledger row and
#: no edge, because a category this module has not read is a claim of unknown
#: shape and guessing its direction is how an aggregator's error becomes ours.
CATEGORY_METABOLISM: str = "Microbes metabolize substances"
CATEGORY_ABUNDANCE: str = "Substances alter microbe abundance"
CATEGORIES: tuple[str, ...] = (CATEGORY_METABOLISM, CATEGORY_ABUNDANCE)

#: ``Metabolism_Effect_on_Drug`` verbatim, for the 404 rows that record a
#: *measured non-metabolism*. Every other value of that column — ``Increase
#: Toxicity``, ``Activation of prodrug``, ``n.a.`` — describes what the
#: metabolism did, so the marker is one exact string and not a rule.
NOT_METABOLISED_MARKER: str = "Microbe does not metabolize drug"

#: ``Microbe_Change`` verbatim for a curated *no-effect*. 507 rows.
NO_CHANGE: str = "No significant change"

#: ``Microbe_Change`` verbatim for the two directions this model has.
INCREASE: str = "Increase"
DECREASE: str = "Decrease"

RELATION_METABOLISES: str = "METABOLISES_SUBSTANCE"
RELATION_NO_METABOLISM: str = "DOES_NOT_METABOLISE_SUBSTANCE"
RELATION_ABUNDANCE_CHANGED: str = "ABUNDANCE_CHANGED_BY_SUBSTANCE"
RELATION_ABUNDANCE_UNCHANGED: str = "ABUNDANCE_UNCHANGED_BY_SUBSTANCE"
RELATION_SAME_COMPOUND: str = "SAME_COMPOUND_AS"

#: The two metabolism relationships, in the order the build report prints them.
METABOLISM_RELATIONSHIPS: tuple[str, ...] = (
    RELATION_METABOLISES,
    RELATION_NO_METABOLISM,
)
#: The two abundance relationships, likewise.
ABUNDANCE_RELATIONSHIPS: tuple[str, ...] = (
    RELATION_ABUNDANCE_CHANGED,
    RELATION_ABUNDANCE_UNCHANGED,
)

#: relationship -> ``(effect, source_relation)``. ``effect`` is what a query
#: groups on when it wants the whole measured population of one family;
#: ``source_relation`` is MASI's own wording, so the normalisation stays
#: reversible (G3).
#:
#: The abundance pair's ``effect`` is filled per row rather than per
#: relationship — ``increased`` and ``decreased`` are both
#: :data:`RELATION_ABUNDANCE_CHANGED` — so its entry here carries the
#: relationship-level wording only and :func:`direction_of` supplies the rest.
SOURCE_RELATIONS: dict[str, tuple[str, str]] = {
    RELATION_METABOLISES: (
        "metabolised",
        "curated from the literature: this microbe metabolises this substance",
    ),
    RELATION_NO_METABOLISM: (
        "not-metabolised",
        f"curated from the literature: {NOT_METABOLISED_MARKER.lower()}",
    ),
    RELATION_ABUNDANCE_CHANGED: (
        "",
        "curated from the literature: this substance altered this microbe's abundance",
    ),
    RELATION_ABUNDANCE_UNCHANGED: (
        "unchanged",
        f"curated from the literature: {NO_CHANGE.lower()} in this microbe's "
        f"abundance under this substance",
    ),
}

#: What MASI says it curated, kept on every edge as ``reported_rank``.
#: ``microbe_tax_level`` in ``microbesInfo`` ranges from ``Strain`` through
#: ``Species``, ``genus``, ``family``, ``class`` and ``Order`` to ``n.a.``, and
#: its case is inconsistent (``genus`` 61 against ``Genus`` 58), so it is
#: lower-cased on write and NCBI's own rank is kept beside it in
#: ``original_rank`` — G5's two-rank split.
REPORTED_RANK_COLUMN: str = "microbe_tax_level"

#: Broadest NCBI rank a MASI claim may be made at — i.e. **none**, and this is
#: the one place MASI departs from the two screens.
#:
#: Maier and Zimmermann both refuse a resolution broader than ``genus``, because
#: every organism they screened is one cultured isolate and a genus-level answer
#: there is a promotion surprise. MASI genuinely curates above genus: 45 of its
#: resolved taxa are families, 21 classes, 14 orders and 11 phyla, and the two
#: organisms its disease table cites most are *Firmicutes* and *Bacteroidetes*.
#: A guard here would drop real curation, so there is none, and ``reported_rank``
#: (MASI's own ``microbe_tax_level``) beside ``original_rank`` (NCBI's) is what a
#: query filters on — G5's two-rank split, doing the work a ceiling would do
#: badly.
#:
#: Promotion is unaffected and unchanged: strains and subspecies still promote to
#: the species ceiling every other source uses (C7), which is why
#: ``probiotic_reported_name`` exists.
BROADEST_ACCEPTED_RANK: str | None = None

#: The paper describing the database, carried as ``aggregator_publication`` on
#: every edge. It is deliberately **not** ``publications``: what a MASI edge
#: cites is the primary study the curator read, and the database's own paper is
#: a different claim about a different thing.
PUBMED_ID: int = 33313900

#: The ``evidence_level`` every disease-association row carries.
#:
#: ``microbeDiseaseAssociationRecords`` has eleven columns and not one of them
#: names a study design, a host, a sequencing type or an assay. Part B's
#: definition of ``unknown`` is written for exactly this case — "the source
#: records no design, host or assay from which a level can be derived. Never
#: defaulted to observational" — and the temptation here is real, because these
#: *are* differential-abundance reports and ``observational-unspecified`` would
#: look right. It would be a guess about 784 edges that no column supports.
DISEASE_EVIDENCE_LEVEL: str = "unknown"

#: ``Substance_subcategory`` values that name a **class of compounds** rather
#: than a compound. MASI says so itself, which is why this is a two-entry set of
#: its own vocabulary and not a rule over names: joining ``Fluoroquinolones`` or
#: ``NSAIDs`` onto whichever molecule happens to share the spelling is the
#: level-4-ATC error :mod:`microbiomekg.drugs` already refuses ("level 4 names a
#: *class*, and joining ``L01BB`` would put every nitrogen-mustard analogue on
#: one node"). 41 of the 1,350 substances are one of these; they become
#: ``Substance`` nodes with their edges intact and are never offered to the drug
#: join.
CLASS_SUBCATEGORIES: frozenset[str] = frozenset({"drug class", "drug category"})

#: The four columns MASI's microbe dictionary contributes to a ``Taxon`` node,
#: and the reason ``prep_taxonomy.py`` names this source in its ``DEPENDS_ON``.
#:
#: ``probiotic`` is a **three-state** boolean and the third state is the point:
#: ``true`` for the 46 organisms MASI marks ``if_probiotic = Yes``, ``false`` for
#: the other organisms MASI curates, and **null for every taxon MASI says
#: nothing about** — which is 862,000-odd of them. Collapsing null into ``false``
#: would turn "this database does not cover the organism" into "this organism is
#: not a probiotic", a claim MASI never made about anything.
#:
#: ``probiotic_reported_name`` is here because two of the 46 are subspecies that
#: promote to their species, and *Bifidobacterium longum* carrying
#: ``probiotic = true`` with no record that the claim was made about
#: *B. longum* subsp. *infantis* would be a wider claim than the source's.
TAXON_PROBIOTIC_PROPERTIES: tuple[str, ...] = (
    "probiotic",
    "probiotic_use_species",
    "probiotic_research_stage",
    "probiotic_reported_name",
)

_NOT_ALNUM = re.compile(r"[^a-z0-9]+")
_PMID = re.compile(r"PMID:?\s*(\d+)", re.IGNORECASE)
_BARE_ID = re.compile(r"^\s*(\d+)\s*$")
_DOI = re.compile(r"DOI:?\s*(\S+)", re.IGNORECASE)
#: A trailing parenthesised abbreviation on a disease label:
#: ``Crohn's disease(CD)``, ``Parkinson's disease (PD)``. Stripped **only** for
#: the MONDO lookup; the verbatim string survives as ``source_condition``.
_ABBREVIATION = re.compile(r"\s*\([^)]*\)\s*$")


def missing(cell: str | None) -> bool:
    """Whether a MASI cell holds no value.

    ``n.a.`` is the source's own spelling of absent and appears in every column
    of every table — 12,463 times in ``Metabolism_Enzymes`` alone. A reader that
    only tested for the empty string would write the literal three characters
    into a node title.
    """
    text = (cell or "").strip()
    return text == "" or text.casefold() == NOT_AVAILABLE


def substance_key(substance_id: str) -> str:
    """``PMDBD530`` -> ``MASI:PMDBD530``, the ``Substance`` node key.

    MASI's own accession, prefixed. It carries the database's earlier
    "PharmacoMicrobiomics DB" name in the ``PMDBD`` stem, which is a fact about
    the source rather than a reason to renumber it.
    """
    return f"MASI:{substance_id.strip()}"


def disease_key(disease_id: str) -> str:
    """``DIS29`` -> ``MASI:DIS29``, the key a disease keeps when MONDO has no
    name for it."""
    return f"MASI:{disease_id.strip()}"


def is_class_substance(subcategory: str | None) -> bool:
    """Whether MASI's own subcategory says this row names a class, not a compound.

    ``Drug Class`` and ``Drug category``. The cell is ``;``-joined, so a
    substance filed under both a class and a compound subcategory counts as a
    class: the safe direction is the one that declines a join.
    """
    parts = {p.strip().casefold() for p in (subcategory or "").split(";")}
    return bool(parts & CLASS_SUBCATEGORIES)


def substance_variants(name: str) -> list[tuple[str, str, str]]:
    """``(kind, key, join route)`` attempts for one substance, in order.

    Two routes, both over ``pref_name``, verbatim first — the same policy the two
    screens declare over their own columns:

    ``substance-name``
        ``Substance_name`` exactly as MASI writes it.
    ``salt-name``
        the same with a salt or hydrate suffix removed. Derived, so it is tried
        last and can never displace a match on what the source wrote.

    **There is no identifier route, and that is a finding rather than an
    omission.** MASI carries a DrugBank id on 709 substances, a PubChem CID on
    1,067, a KEGG id on 561 and an InChIKey on 1,067 — a richer cross-reference
    block than any other source here — and *none of them reaches anything*,
    because the fetched ChEMBL molecule JSONL carries no cross-references at all
    (the REST pull's ``only=`` kept 13 of 34 fields). That is the same wall
    ``IS_DRUG`` already documents, hit from the other side.
    """
    written = (name or "").strip()
    out: list[tuple[str, str, str]] = [("name", written, "substance-name")]
    bare = strip_salt(written)
    if bare and bare.casefold() != written.casefold():
        out.append(("name", bare, "salt-name"))
    return out


def relation_for_metabolism(effect_on_drug: str | None) -> str:
    """The relationship one ``Microbes metabolize substances`` row becomes.

    :data:`RELATION_NO_METABOLISM` for the 404 rows whose
    ``Metabolism_Effect_on_Drug`` is exactly :data:`NOT_METABOLISED_MARKER`, and
    :data:`RELATION_METABOLISES` for every other row of the category — including
    the 3,431 whose effect column is ``n.a.``, because the *category* is the
    claim and the effect column only qualifies it. Reading a blank effect as a
    non-hit would invert 3,431 edges.
    """
    if (effect_on_drug or "").strip() == NOT_METABOLISED_MARKER:
        return RELATION_NO_METABOLISM
    return RELATION_METABOLISES


def relation_for_abundance(microbe_change: str | None) -> str | None:
    """The relationship one ``Substances alter microbe abundance`` row becomes.

    ``Increase``/``Decrease`` -> :data:`RELATION_ABUNDANCE_CHANGED`,
    :data:`NO_CHANGE` -> :data:`RELATION_ABUNDANCE_UNCHANGED`, and **``None`` for
    anything else** — which on the real file is six ``n.a.`` rows and two that
    say ``delay microbiota maturation``. That last one is a real curated finding
    with no direction this model can write: filing it as a decrease would invent
    a sign, and filing it as "no change" would invert one. It is a ledger row.
    """
    change = (microbe_change or "").strip()
    if change in (INCREASE, DECREASE):
        return RELATION_ABUNDANCE_CHANGED
    if change == NO_CHANGE:
        return RELATION_ABUNDANCE_UNCHANGED
    return None


def direction_of(microbe_change: str | None) -> str:
    """``Increase`` -> ``increased``, ``Decrease`` -> ``decreased``, else ``""``.

    The same two-valued normalisation BugSigDB and gutMDisorder write, so a
    cross-source query on ``direction`` means one thing.
    """
    change = (microbe_change or "").strip()
    if change == INCREASE:
        return "increased"
    if change == DECREASE:
        return "decreased"
    return ""


def _hosts(model_species: str | None) -> list[str]:
    return [
        p.strip()
        for p in re.split(r"[;/]", (model_species or ""))
        if p.strip() and p.strip().casefold() != NOT_AVAILABLE
    ]


def evidence_level_for(experiment_system: str | None, model_species: str | None) -> str:
    """Derive an interaction row's ``evidence_level`` from its own two columns.

    Precedence, first match wins, and it is Part B's ladder read against what
    this source actually carries:

    1. the system names **in vivo** and any named model species is not human ->
       ``in-vivo-model``. 1,157 rows, mostly mouse and rat. A mixed cell
       (``In vivo (Rat); In vitro (Human)``) counts as in vivo: the stronger
       claim in the row is the one the level has to bound.
    2. the system names in vivo with no non-human host -> ``unknown``. 41 rows.
       An in-vivo human observation with no design column is not
       ``observational-unspecified``, because nothing here says it was
       observational — it could be a trial.
    3. the system names **in vitro** -> ``in-vitro``. 8,913 rows, including the
       472 whose model species is a human faecal culture: an ex-vivo mixed
       culture is still culture.
    4. anything else — ``n.a.``, 2,396 rows — -> ``unknown``.

    The 8,303 rows whose model species reads ``High-throughput incubation
    assays`` are the two screens' own cells, and they land at ``in-vitro`` by
    this rule, which is what the primary sources give them.
    """
    system = (experiment_system or "").strip().casefold()
    if "in vivo" in system:
        return (
            "in-vivo-model"
            if any(not h.casefold().startswith("human") for h in _hosts(model_species))
            else "unknown"
        )
    if "in vitro" in system:
        return "in-vitro"
    return "unknown"


def publications_of(
    reference_type: str | None, reference_id: str | None
) -> tuple[list[str], int | None]:
    """``([CURIEs], the first PMID as an int or None)`` for one reference cell.

    The cell is multi-valued on 2,058 interaction rows
    (``PMID: 26569070; PMID: 22516259; ...``), sometimes opens with a stray
    separator (``; DOI: 10.1016/...``), and its ``Reference_ID_Type`` column is
    only two-valued (``PMID`` 12,461, ``DOI`` 51) where a single cell may carry
    both.

    **So the text is parsed and the type column is not trusted, and the file
    settles the argument: 25 rows typed** ``PMID`` **carry a DOI and no PMID at
    all**, and one row typed ``DOI`` carries a PMID after the DOI. A reader that
    branched on the type column would file 25 DOIs as accessions. Parsing the
    text reaches a publication on **all 12,512 rows**.

    The bare-number fallback is for a shape this release does not contain: it
    fires only when the type column says ``PMID`` *and* the whole cell is
    digits, because a looser rule would turn a DOI's year into an accession.
    """
    text = (reference_id or "").strip()
    out: list[str] = []
    pmids: list[int] = []
    for match in _PMID.finditer(text):
        value = int(match.group(1))
        if value not in pmids:
            pmids.append(value)
            out.append(f"PMID:{value}")
    for match in _DOI.finditer(text):
        curie = f"doi:{match.group(1).strip().rstrip(';,')}"
        if curie not in out:
            out.append(curie)
    if not out and (reference_type or "").strip().upper() == "PMID":
        bare = _BARE_ID.match(text)
        if bare:
            pmids.append(int(bare.group(1)))
            out.append(f"PMID:{pmids[0]}")
    return out, (pmids[0] if pmids else None)


def normalise_disease_name(name: str | None) -> str:
    """The form a MASI disease label is looked up in MONDO under.

    Casefolded, with a trailing parenthesised abbreviation removed:
    ``Crohn's disease(CD)`` -> ``crohn's disease``,
    ``Inflammatory bowel disease (IBD)`` -> ``inflammatory bowel disease``. The
    verbatim label survives on the node as ``source_condition``, so the
    normalisation is only ever a lookup key.

    **Nothing else is normalised.** ``Rheumatoid arthrits`` keeps its typo and
    reaches no MONDO term, and ``coeliac disease`` — which MASI files under a
    *second* disease id beside ``Celiac disease`` — is not an exact synonym of
    any MONDO term in the loaded release, so the two spellings stay two
    ``Disease`` nodes. Correcting either by hand would be a spelling rule
    standing in for a curated equivalence, and the ledger says so instead.
    """
    return _ABBREVIATION.sub("", (name or "").strip()).strip().casefold()


#: What every MASI interaction edge must carry: the schema survey's §5(b)
#: provenance block, ``evidence_level``, and ``effect``.
#:
#: The same nine as the two screens, and the same six of the association
#: contract's fourteen are left out for the same reason — ``direction`` (on the
#: metabolism pair), the two group sizes, ``sequencing_type``,
#: ``statistical_test`` and ``study_design`` describe a differential-abundance
#: *study*, and a curated interaction record is not one. ``effect`` is required
#: because it is the one field that says which of the two measurements an edge
#: is; ``publications`` is required because an aggregator's edge whose primary
#: reference is missing is an edge with no evidence at all.
CONTRACT: list[str] = [
    "effect",
    "evidence_level",
    "knowledge_level",
    "agent_type",
    "primary_source",
    "source_record_id",
    "source_licence",
    "source_relation",
    "publications",
]

#: Declared types for every property a MASI interaction edge carries.
INTERACTION_PROPERTY_TYPES: dict[str, str] = {
    **{field: "string" for field in CONTRACT},
    # `any`, not a list type: kglite 0.16.22 gave the *blueprint* a "list"
    # column type but the ontology's `property_types` grammar still accepts
    # only string/integer/float/boolean/date/datetime/timestamp/point/any, so
    # "string" here reads every list cell as a violation and there is nothing
    # narrower to say. Presence is still checked — these fields are in the
    # relationship's `required_properties` — only the shape is not.
    "publications": "any",
    "pmid": "integer",
    "aggregator_publication": "string",
    # The aggregator contract, made countable. Absent when no loaded primary
    # source measures this (taxon, compound) pair; otherwise a list of the
    # source tokens of the ones that do.
    "duplicates_primary_source": "any",
    "direction": "string",
    "interaction_category": "string",
    # MASI's own record id, which is **not** unique: 2,891 of the 12,512 rows
    # share an id with exactly one other row, always a second microbe under one
    # curated statement. `source_record_id` therefore keys on the triple.
    "masi_record_id": "string",
    # The substance end: what MASI said, and how (or whether) it reached a Drug.
    # `masi_substance_id` and not `substance_id`, which is the junction's target
    # foreign key: a property sharing the FK's name would be written twice with
    # two meanings, the CURIE and the bare accession.
    "masi_substance_id": "string",
    "substance_name": "string",
    "substance_category": "string",
    "substance_subcategory": "string",
    "drug_join": "string",
    "substance_exposure_details": "string",
    # The taxon end: the same two questions.
    "masi_microbe_id": "string",
    "reported_name": "string",
    "reported_tax_id": "integer",
    "reported_rank": "string",
    "original_rank": "string",
    "resolution_status": "string",
    "taxon_id_route": "string",
    # What the record says about the experiment.
    "microbiota_site": "string",
    "experiment_system": "string",
    "experiment_model_species": "string",
    "model_condition": "string",
    "outcome": "string",
    # The metabolism block, empty on an abundance edge.
    "metabolites": "string",
    "metabolism_type": "string",
    "metabolism_enzymes": "string",
    "metabolism_effect_on_drug": "string",
    "metabolism_mechanism": "string",
    # The abundance block, empty on a metabolism edge.
    "microbe_change": "string",
    "microbe_change_statistics": "string",
}

#: Declared types for the ``Substance`` node's properties.
SUBSTANCE_PROPERTY_TYPES: dict[str, str] = {
    "name": "string",
    "substance_category": "string",
    "substance_subcategory": "string",
    "therapeutic_class": "string",
    "product_company": "string",
    "molecular_formula": "string",
    "iupac_name": "string",
    "inchikey": "string",
    "cas": "string",
    "drugbank_id": "string",
    "pharmgkb_id": "string",
    "kegg_id": "string",
    "ttd_id": "string",
    "pubchem_cid": "string",
    "chemspider_id": "string",
    "npass_id": "string",
    "synonyms": "string",
    "drug_id": "string",
    "drug_join": "string",
    "source": "string",
    "source_licence": "string",
}


def _interaction(description: str) -> dict:
    return {
        "domain": "Taxon",
        "range": "Substance",
        "required_properties": list(CONTRACT),
        "property_types": INTERACTION_PROPERTY_TYPES,
        # Both at `error`: every one of the nine is written by this prep
        # unconditionally rather than read from upstream, so a violation is a bug
        # here and not a gap in someone's curation.
        "enforcement": {"required_properties": "error", "property_types": "error"},
        "description": description,
    }


CLASSES: dict[str, dict] = {
    "Substance": {
        "description": (
            "A microbiota-active substance as MASI curates it: a drug, a "
            "medicinal herb or its compound, a dietary compound or an "
            "environmental chemical, keyed on MASI's own `PMDBD` accession. It "
            "is a separate type from `Drug` because most of what MASI indexes "
            "is not a drug — 278 of its 1,350 substances are herbal, dietary "
            "or environmental with no therapeutic category at all — and "
            "because MASI is an aggregator: keeping its claims on its own "
            "nodes is what stops a curated re-statement of a published screen "
            "being counted as a second measurement. Where the substance is a "
            "compound this graph already has a `Drug` node for, "
            "`SAME_COMPOUND_AS` says so and `drug_id` carries the key."
        ),
    },
    # Declared here because SAME_COMPOUND_AS points at it. The shared sentence
    # lives in vocabulary.DRUG_DESCRIPTION: fragment merging raises on a
    # contradicting scalar, which is what a second author of a description is.
    "Drug": {"description": DRUG_DESCRIPTION},
}

RELATIONSHIPS: dict[str, dict] = {
    RELATION_METABOLISES: _interaction(
        "A microbe MASI curates as metabolising this substance, read out of the "
        "primary literature rather than measured. The same claim "
        "`METABOLISES` makes about a `Drug`, kept on its own relationship "
        "because 2,884 of MASI's 4,295 metabolism rows are its curation of "
        "Zimmermann 2019 — which this graph already loads from the screen "
        "itself — so merging the two would double-count the very query D8 "
        "asks. `duplicates_primary_source` names the overlap per edge."
    ),
    RELATION_NO_METABOLISM: _interaction(
        "A substance MASI curates as **not** metabolised by this microbe: 404 "
        "records whose `Metabolism_Effect_on_Drug` says so outright. Its own "
        "relationship rather than a flag, so no query counts a curated "
        "refutation as metabolism by omission."
    ),
    RELATION_ABUNDANCE_CHANGED: _interaction(
        "A substance MASI curates as changing this microbe's abundance, with "
        "`direction` carrying which way. Deliberately **not** "
        "`INHIBITS_GROWTH_OF`: the claim is an abundance shift — 995 of these "
        "records are in-vivo observations in a host — and 4,778 of the pairs "
        "it resolves to are pairs Maier 2018's growth screen already measured "
        "in monoculture, so routing them onto that relationship would put a "
        "weaker restatement into the population D8 and D18 both read."
    ),
    RELATION_ABUNDANCE_UNCHANGED: _interaction(
        "A substance MASI curates as leaving this microbe's abundance "
        "unchanged: 507 records that say `No significant change`. The same "
        "measured-negative rule `NO_EXCHANGE_WITH` and "
        "`DOES_NOT_INHIBIT_GROWTH_OF` follow, applied to a curated source."
    ),
    RELATION_SAME_COMPOUND: {
        "domain": "Substance",
        "range": "Drug",
        "cardinality": {"max": 1},
        "enforcement": {"cardinality": "error"},
        "description": (
            "The `Drug` node this MASI substance is the same compound as, "
            "reached by an exact or salt-stripped match on ChEMBL's "
            "`pref_name`. Absent for a substance no route reaches and for "
            "every substance MASI's own subcategory files as a *class* of "
            "compounds rather than a compound. It is a declared edge rather "
            "than a merge because MASI is an aggregator: a query that wants "
            "its claims about a drug asks for them in one hop, and a query "
            "that wants what was measured never sees them at all."
        ),
    },
}

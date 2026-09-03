"""Zimmermann 2019: the bug changes the drug — D8's other direction, and the
17,000-odd measured pairs where it does not.

Maier 2018 gave this graph ``INHIBITS_GROWTH_OF``: *the drug stops the bacterium
growing*. This source gives it :data:`RELATION_METABOLISES`: *the bacterium
depletes the drug*. They are opposite claims about the same two entities and
Part D's D8 required in advance that they land as different edge types, because
collapsing them conflates antimicrobial killing with drug metabolism — MDAD's
documented weakness. Zimmermann et al., *Nature* 570:462-467 (2019), PMID
31158845: 271 orally administered drugs against 76 human gut bacterial strains,
every cell measured by LC-MS at 12 h against t=0 over four independent cultures.

Six decisions this module records.

**The direction is ``Taxon -> Drug``, not ``Drug -> Taxon``.** Maier's edges run
drug-to-taxon because the drug is the agent; here the bacterium is. Reversing
one of them to make the pair symmetric would put the agent on the wrong end of
half the edges and make ``MATCH (d:Drug)-[]->(t:Taxon)`` — which
``tests/test_acceptance.py`` asserts is *only ever* the growth screen — quietly
untrue.

**The negatives are the larger half again, and they get their own
relationship.** The screen measured 271 x 76 = 20,596 pairs and left none of
them blank, so "this strain was given this drug and did not touch it" is a
*measurement*. It lands as :data:`RELATION_NO_METABOLISM` rather than as a flag
on the positive edge, for the reason ``NO_EXCHANGE_WITH`` and
``DOES_NOT_INHIBIT_GROWTH_OF`` already do: a refutation stored as a property is
counted as an observation by every query that does not know to exclude it.
``effect`` rides on both, so a query that wants the whole measured population
groups on one property instead of unioning two labels.

**Four of the eighty columns in the screen are not organisms.** ``Control pH
4/5/6/7`` sit among the strain columns, carry the same five sub-columns, and
produce 38 apparent hits between them under the very rule that calls a real hit —
they are the abiotic-degradation controls, and a loader that read the column
block structurally would have written 1,084 cells of *chemistry* as microbial
metabolism. Excluding them is also what makes the paper's own "76 human gut
bacteria" reproduce from the sheet instead of reading 80.
:func:`is_control_column` is the guard, and each excluded column is a ledger row.

**The call rule is derived, and the file only publishes half of it.** Column B
of the screen gives each drug its own ``Drug adaptive FC threshold %`` — 20% for
124 of the 271 drugs and higher for the rest — so the depletion cutoff *is*
published. What is not published is the comparison and the significance cutoff,
and both matter: ``% consumed >= threshold`` with ``p(FDR) <= 0.05`` reproduces
the paper's **176 of 271 metabolised by at least one strain** exactly, while
``p(FDR) < 0.05`` gives 175, ``p(FDR) <= 0.01`` gives 133, and ignoring the
per-drug threshold in favour of its 20% floor gives 190.
:data:`METABOLISED_DRUGS` is that headline and
``scripts/prep_zimmermann2019.py`` re-derives it on every run, refusing to write
when it stops holding — the rule decides the *type* of every edge here.

**Two of the 76 strain names stay unresolved on purpose, and five are
corrected.** :data:`SPECIES_OVERRIDES` carries the five strings the paper
misspells or writes with a strain designation inside the species name, and every
one of them is confirmed by something in its own row rather than by the
spelling: three by the culture-collection number, one because it is the only
name in the whole of ``names.dmp`` at edit distance 1, one because the binomial
is a verbatim prefix of the string. ``Bacteroides WH2`` and ``Bifidobacterium
ruminatum`` meet neither test — NCBI holds two candidates for each and nothing
in the row chooses — so they stay ``UnresolvedTaxon`` tombstones with both
candidates named in the ledger. Guessing would attribute 271 measurements each
to an organism nobody screened.

**There is no ``Gene`` node, and supplementary table 13 is the reason to say so
rather than the reason to add one.** The paper's second half identifies 30
bacterial gene products that metabolise 20 of the drugs — but it identifies them
in a **gain-of-function library expressed in *E. coli***, which is a different
experiment from the 76-strain screen these edges come from. The evidence rides
on the edge as :data:`GENE_PROPERTIES` instead: the locus tags, the product
descriptions and the RefSeq protein ids of the donor organism's gene products
that metabolised that drug. That answers Part B's W7 field list ("and the gene
where identified") in one hop, without a node type no Part D query reads, and it
keeps the 5 pairs where the two experiments *disagree* visible — a gene that
worked in *E. coli* while its donor strain did not deplete the drug in culture
sits on a ``DOES_NOT_METABOLISE`` edge, and hiding that would be inventing
agreement. docs/model.md records the recommendation and what would change it.
"""

from __future__ import annotations

import re

from ..drugs import strip_salt
from .vocabulary import DRUG_DESCRIPTION, register_source

__all__ = [
    "AMBIGUOUS_STRAINS",
    "ASSOCIATION_RELATIONSHIPS",
    "CLASSES",
    "COLUMN_OVERRIDES",
    "CONTROL_PREFIX",
    "DRUG_PROPERTY_TYPES",
    "EVIDENCE_LEVEL",
    "FDR_THRESHOLD",
    "GENE_PROPERTIES",
    "INCUBATION_HOURS",
    "METABOLISED_DRUGS",
    "METABOLISM_CONTRACT",
    "METABOLISM_PROPERTY_TYPES",
    "METABOLISM_RELATIONSHIPS",
    "PUBLICATION",
    "PUBMED_ID",
    "RANK_CEILING",
    "RELATION_METABOLISES",
    "RELATION_NO_METABOLISM",
    "REPLICATES",
    "REPORTED_RANK",
    "REPORTED_STRAINS",
    "SCREENED_DRUGS",
    "SOURCE",
    "SOURCE_RELATIONS",
    "SPECIES_OVERRIDES",
    "drug_variants",
    "effect_of",
    "is_control_column",
    "join_key",
    "patric_tax_id",
    "relation_for",
]

SOURCE = "zimmermann2019"

#: **Every edge is a curator transcribing a published mass-spectrometry
#: measurement.** The screen is a laboratory assay; what this loader reads is the
#: authors' own published depletion call in a supplementary table — a person
#: asserting "this strain metabolised this drug", which is Biolink's
#: ``knowledge_assertion`` by a ``manual_agent``, the pair Maier, NJC19 and HMDB
#: all carry.
#:
#: The licence is the same shape as Maier's and the token says so rather than
#: guessing. Journal supplementary material of a subscription article, no licence
#: line, no terms URL and no document property in the workbook; inventing
#: ``CC-BY-4.0`` on 20,054 edges would put a redistribution claim in the graph
#: that nobody made. G3's per-edge licence keeps that token from contaminating
#: anything else: ``WHERE r.source_licence <> 'Zimmermann2019-unstated'`` is the
#: shippable cut, and it is a *different* token from Maier's so the two screens
#: can be excluded independently.
register_source(
    SOURCE,
    knowledge_level="knowledge_assertion",
    agent_type="manual_agent",
    licence="Zimmermann2019-unstated",
)

#: This source declares no taxon–condition association: it is an in-vitro
#: metabolism screen, not a differential-abundance corpus.
ASSOCIATION_RELATIONSHIPS: tuple[str, ...] = ()

#: The one ``evidence_level`` this source emits. Part B's ``in-vitro`` row names
#: exactly this shape — "measured in culture: growth, a metabolite assay, an MIC
#: over controls" — and the workbook carries no per-row design, host or assay
#: column that could move it.
EVIDENCE_LEVEL: str = "in-vitro"

#: The paper, as Part D's D8 cites it. Carried as ``publications`` on every edge
#: and as an integer ``pmid``. No ``Paper`` node is minted, for the reason Maier's
#: is not: one node with 20,054 edges would dominate every path query in the
#: graph for no gain over the property.
PUBMED_ID: int = 31158845
PUBLICATION: str = f"PMID:{PUBMED_ID}"

#: FDR-corrected p at or below which the authors called a depletion real.
#:
#: **Derived.** The sheet publishes a per-drug depletion threshold and an FDR
#: p-value per cell, and states no significance cutoff. This value, with
#: ``% consumed >= the drug's own threshold``, reproduces
#: :data:`METABOLISED_DRUGS` exactly; ``<`` rather than ``<=`` gives 175, 0.01
#: gives 133, and 0.001 gives 53. The boundary is not academic — fourteen cells
#: sit at exactly ``0.05``.
FDR_THRESHOLD: float = 0.05

#: The paper's own headline, and what the prep re-derives on every run:
#: **176 of 271 drugs were metabolised by at least one of the 76 strains** (65%).
#: Quoted in Part B's W7 and ``docs/research/researcher-workflows.md`` from the
#: abstract, so it is a number this repo committed to before reading the file.
METABOLISED_DRUGS: int = 176

#: The screen's own dimensions, asserted rather than trusted: a re-extraction
#: that dropped a column would otherwise change every count in silence.
SCREENED_DRUGS: int = 271
REPORTED_STRAINS: int = 76

#: What the sheet's own header rows state about the assay. Both are on every
#: edge, because "measured at 12 h over four independent cultures" is what bounds
#: the negative — the screen carries no concentration anywhere, so unlike Maier's
#: ``screen_concentration_um`` there is nothing here to write and none is
#: invented.
INCUBATION_HOURS: float = 12.0
REPLICATES: int = 4

#: The hit relationship, and the measured non-hit. Two types, never one.
RELATION_METABOLISES: str = "METABOLISES"
RELATION_NO_METABOLISM: str = "DOES_NOT_METABOLISE"

#: The two relationships in the order the build report prints them.
METABOLISM_RELATIONSHIPS: tuple[str, ...] = (
    RELATION_METABOLISES, RELATION_NO_METABOLISM,
)

#: relationship -> ``(effect, source_relation)``. ``effect`` is what a query
#: groups on when it wants the whole measured population; ``source_relation`` is
#: the screen's own wording of the call, thresholds and all, so the
#: normalisation stays reversible (G3).
#:
#: The values are ``metabolised`` / ``not-metabolised`` rather than reusing
#: Maier's ``inhibited`` / ``no-effect``: sharing ``no-effect`` across the two
#: screens would make ``WHERE r.effect = 'no-effect'`` mix "did not stop it
#: growing" with "did not touch the drug", which are different findings about
#: different things.
SOURCE_RELATIONS: dict[str, tuple[str, str]] = {
    RELATION_METABOLISES: (
        "metabolised",
        f"screen hit (drug depleted to or past its own adaptive threshold, "
        f"FDR p <= {FDR_THRESHOLD})",
    ),
    RELATION_NO_METABOLISM: (
        "not-metabolised",
        f"screened, not a hit (depletion below the drug's own adaptive threshold "
        f"or FDR p > {FDR_THRESHOLD})",
    ),
}

#: What the source says it screened. Supplementary table 1 files each row under a
#: ``Name`` *and* a culture-collection number or ``fecal isolate``, so the unit of
#: measurement is an isolate; ``original_rank`` carries NCBI's rank for whatever
#: the name first resolved to, which is how G5's two-rank split works everywhere
#: else in this graph.
REPORTED_RANK: str = "strain-level isolate"

#: Broadest NCBI rank a metabolism claim may be made at. Every organism here is a
#: single cultured isolate, so — as in Maier and NJC19 — this is a guard against
#: a promotion surprise rather than a working filter.
RANK_CEILING: str = "genus"

#: What the screen's four non-organism columns are called. They are
#: ``Control pH 4``…``Control pH 7`` and they sit *between* two strain columns in
#: the sheet, so nothing structural separates them: the prefix is the only
#: marker, and :func:`is_control_column` is the only place that knows it.
CONTROL_PREFIX: str = "Control"

#: Supplementary table 3's column header -> the ``Name`` and ``Reference`` of the
#: supplementary table 1 row it means, where the two sheets spell the strain
#: differently.
#:
#: Every other column joins on its normalised ``Name`` + ``Reference`` (or on the
#: ``Name`` alone for the four isolates whose reference is ``fecal isolate``), and
#: 74 of the 76 do so exactly. These two do not: table 3 writes the *E. coli*
#: strain by its lineage (``K-12``) where table 1 writes the Keio designation
#: (``BW25113``), and it spells ``formatexigens`` where table 1 spells
#: ``formataxigens``. A prefix-matching rule would catch the first and would also
#: match ``Bacteroides fragilis NCTC9343`` against any of the seven
#: *B. fragilis* rows, silently attaching one isolate's measurements to another's
#: strain designation — which is why this is a closed two-entry map of verbatim
#: strings and not a rule.
COLUMN_OVERRIDES: dict[str, str] = {
    "Escherichia coli  K-12": "Escherichia coli BW25113",
    "Bryantia formatexigens DSM14469": "Bryantia formataxigens DSM14469",
}

#: The casefolded supplementary-table-1 ``Name`` strings that are not names NCBI
#: spells, mapped to the ones it does.
#:
#: **Each entry is confirmed by something other than the spelling, and the two
#: strings that are not are deliberately absent.** Reading left to right:
#:
#: ``pretovella copri``
#:     a transposition. The row's own ``DSM18205`` is the type strain, and
#:     ``names.dmp`` carries ``Prevotella copri DSM 18205`` (537011) under
#:     *Segatella copri* 165179.
#: ``bryantia formataxigens``
#:     genus and epithet both misspelt. ``DSM14469`` again decides it:
#:     ``names.dmp`` carries ``Bryantella formatexigens DSM 14469`` under
#:     *Marvinbryantia formatexigens* 168384.
#: ``eubacterium biforme``
#:     a renamed organism NCBI no longer spells this way at species level, but
#:     *does* still spell at strain level: ``Eubacterium biforme DSM 3989`` is a
#:     synonym of ``Holdemanella biformis DSM 3989`` (518637), and the row's
#:     reference is ``DSM3989``.
#: ``odoribacter splanchnius``
#:     one letter. The row is a fecal isolate with no collection number, so the
#:     confirmation is exhaustive instead: *Odoribacter splanchnicus* is the
#:     **only** name in the whole of ``names.dmp`` at edit distance 1 from it.
#: ``lactobacillus  reuteri cf48-3a``
#:     a strain designation written inside the species column, the same shape as
#:     Maier's *B. fragilis* toxigenicity qualifiers — the binomial is a verbatim
#:     prefix of the string, and ``BEI HM-102`` is that strain.
#:
#: **``Bacteroides WH2`` and ``Bifidobacterium ruminatum`` are not here.** NCBI
#: holds *two* candidates for each — ``Bacteroides sp. WH2`` (311784) and
#: ``Bacteroides cellulosilyticus WH2`` (1268240); *B. ruminantium* (78346) and
#: *B. ruminale*, which is a synonym of *B. thermophilum* (33905) — and neither
#: row carries a collection number to choose with. They become tombstones with
#: both candidates in the ledger, costing 271 measurements each. That is the
#: honest outcome: picking one would attribute a strain's whole row to an
#: organism nobody screened, and it would not be visible in any count.
SPECIES_OVERRIDES: dict[str, str] = {
    "pretovella copri": "Prevotella copri",
    "bryantia formataxigens": "Bryantella formatexigens",
    "eubacterium biforme": "Holdemanella biformis",
    "odoribacter splanchnius": "Odoribacter splanchnicus",
    "lactobacillus  reuteri cf48-3a": "Lactobacillus reuteri",
}

#: The two strain names :data:`SPECIES_OVERRIDES` deliberately does **not**
#: correct, and the NCBI taxa each of them could have meant.
#:
#: An override is written only when something other than the spelling confirms
#: it — the row's own culture-collection number, or an exhaustive near-miss
#: search. These two have neither: the reference column says ``WH2`` and ``fecal
#: isolate``, and NCBI holds two live candidates for each name. Picking one would
#: attribute a strain's whole 271-cell row to an organism nobody screened, and
#: nothing in any count would show it.
#:
#: They are here rather than nowhere because a tombstone that says only "no name
#: match in names.dmp" is a dead end, while one that names what was rejected is a
#: decision the next reader can reverse: if a future release merges
#: ``Bacteroides sp. WH2`` into *B. cellulosilyticus*, or the authors state which
#: strain they screened, the answer is one line of this map away.
AMBIGUOUS_STRAINS: dict[str, tuple[tuple[int, str], ...]] = {
    "bacteroides wh2": (
        (311784, "Bacteroides sp. WH2"),
        (1268240, "Bacteroides cellulosilyticus WH2"),
    ),
    "bifidobacterium ruminatum": (
        (78346, "Bifidobacterium ruminantium"),
        (33905, "Bifidobacterium ruminale, a synonym of B. thermophilum"),
    ),
}

#: ``fig|226186.12.peg.149`` — supplementary table 13's PATRIC identifier. The
#: first component of a PATRIC genome id **is the NCBI taxid**, which is what
#: makes the gene table joinable to the screen without a hand-written map of
#: locus-tag prefixes: 226186 is *B. thetaiotaomicron* VPI-5482, 411903 is
#: *C. aerofaciens* ATCC 25986 and 483217 is *B. dorei* DSM 17855, and each one's
#: scientific name normalises onto exactly one screened column.
_PATRIC = re.compile(r"^fig\|(?P<tax_id>\d+)\.\d+\.peg\.\d+$", re.IGNORECASE)

#: Everything that is not a letter or a digit. The sheets punctuate a strain
#: designation differently in almost every row — ``ATCC 15703`` against
#: ``ATCC15703``, ``3397 (T10)`` against ``3397 T10`` — so the join key is the
#: casefolded alphanumerics and nothing else.
_NOT_ALNUM = re.compile(r"[^a-z0-9]+")


def join_key(label: str | None) -> str:
    """The key two spellings of one label agree on.

    ``'Alistipes indistinctus DSM 22520'`` and ``'Alistipes indistinctus
    DSM22520'`` both become ``'alistipesindistinctusdsm22520'``; so do
    supplementary table 13's ``'Norethindrone acetate'`` and the screen's
    ``'NORETHINDRONEACETATE'``. Deliberately lossy and only ever used to *look a
    row up*: the verbatim strings survive on the edge as ``reported_name``,
    ``strain`` and ``reported_drug_name``.
    """
    return _NOT_ALNUM.sub("", (label or "").casefold())


def is_control_column(label: str | None) -> bool:
    """Whether a screen column is an abiotic control rather than an organism.

    ``Control pH 4`` through ``Control pH 7``. They carry the same five
    sub-columns as a strain and sit between two of them, so a reader that walked
    the block structure would load 1,084 cells of chemistry as microbial
    metabolism — and would report 80 screened "strains" against the paper's 76.
    """
    return (label or "").strip().startswith(CONTROL_PREFIX)


def patric_tax_id(patric_id: str | None) -> int | None:
    """The NCBI taxid inside a PATRIC feature id, or ``None``.

    ``fig|226186.12.peg.149`` -> ``226186``. ``None`` for anything that is not a
    PATRIC id, so a release that changes the spelling ledgers the gene rather
    than attaching it to whichever organism a looser parse reached.
    """
    match = _PATRIC.match(str(patric_id or "").strip())
    return int(match.group("tax_id")) if match else None


def drug_variants(molename: str, parent_name: str | None) -> list[tuple[str, str, str]]:
    """``(kind, key, join route)`` attempts for one screened compound, in order.

    The order *is* the policy, and it is Maier's policy over this file's columns:
    what the source wrote before anything derived from it. There is no ATC route
    — supplementary table 2 carries no ATC column — and there is a route Maier
    has no column for.

    ``molename``
        the screened compound's name verbatim (``MOLENAME``), against
        ``pref_name``. This names the *salt* that went into the well.
    ``parent-name``
        supplementary table 2's own ``name`` column, which is the parent drug —
        ``ABACAVIR SULFATE`` has ``Abacavir`` here. Still verbatim: the file
        supplies it, this loader does not derive it. It is tried second because
        ``MOLENAME`` is what was actually measured, and where the two disagree
        the ledger says so.
    ``salt-name``
        ``MOLENAME`` with a salt or hydrate suffix removed. The one derived
        route, tried last, for the compounds whose parent column is empty or
        spelled differently again.

    ``kind`` is always ``"name"`` here; it is kept because
    :meth:`microbiomekg.drugs.DrugIndex.lookup` takes the same pair from both
    screens.
    """
    written = (molename or "").strip()
    out: list[tuple[str, str, str]] = [("name", written, "molename")]
    parent = (parent_name or "").strip()
    if parent and parent.casefold() != written.casefold():
        out.append(("name", parent, "parent-name"))
    bare = strip_salt(written)
    if bare and bare.casefold() not in {written.casefold(), parent.casefold()}:
        out.append(("name", bare, "salt-name"))
    return out


def relation_for(
    percent_consumed: float | None,
    drug_threshold: float | None,
    fdr_p: float | None,
) -> str | None:
    """The relationship one screen cell becomes, or ``None`` when unmeasured.

    A cell is :data:`RELATION_METABOLISES` when the drug was depleted **to or
    past** its own published adaptive threshold *and* the FDR-corrected p is at
    or below :data:`FDR_THRESHOLD`; anything else the screen measured is
    :data:`RELATION_NO_METABOLISM`.

    ``None`` is the answer when any of the three numbers is missing. The real
    workbook has no such cell — all 20,596 are numeric, which is itself worth
    knowing — but a pair with no measurement is neither a hit nor a non-hit, and
    the direction that would look harmless is filing it as a non-hit.
    """
    if percent_consumed is None or drug_threshold is None or fdr_p is None:
        return None
    hit = percent_consumed >= drug_threshold and fdr_p <= FDR_THRESHOLD
    return RELATION_METABOLISES if hit else RELATION_NO_METABOLISM


def effect_of(relationship: str) -> str:
    """``metabolised`` / ``not-metabolised`` for a relationship name."""
    return SOURCE_RELATIONS[relationship][0]


#: What a metabolism edge must carry, and the applicable subset it is.
#:
#: The same nine as Maier's growth screen, for the same reason: six of the
#: association contract's fourteen — ``direction``, the two group sizes,
#: ``sequencing_type``, ``statistical_test``, ``study_design`` — describe a
#: differential-abundance observation, and a monoculture metabolism assay has
#: none of them. Declaring them would report a permanent ~100% violation meaning
#: "this is not an abundance study" rather than "this evidence is missing".
#:
#: ``effect`` is required alongside the provenance block because it is the one
#: field that says which of the two measurements an edge *is*.
METABOLISM_CONTRACT: list[str] = [
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

#: The four columns supplementary table 13's gain-of-function screen contributes
#: to an edge, where it covers that (organism, drug) pair at all.
#:
#: They are **not** a claim that this strain uses this gene: the genes were
#: identified by expressing a library of them in *E. coli*, which is a different
#: experiment from the one every edge here comes from. What they say is "a gene
#: product of this organism metabolised this drug when expressed heterologously",
#: which is exactly Part B's W7 field "and the gene where identified" — and
#: putting it here rather than on a ``Gene`` node is what keeps it answerable in
#: one hop without a node type no Part D query reads.
GENE_PROPERTIES: tuple[str, ...] = (
    "gene_locus_tags", "gene_products", "gene_protein_ids", "n_gene_products",
)

#: Declared types for every property a metabolism edge carries: the contract's
#: nine, plus the numbers the call was made from, plus what the sheet said about
#: each end and how each end reached a node, plus the gene block.
METABOLISM_PROPERTY_TYPES: dict[str, str] = {
    **{field: "string" for field in METABOLISM_CONTRACT},
    "pmid": "integer",
    # The measurement itself. `drug_threshold_percent` is on the edge and not
    # only in `source_relation` because it is per *drug*: a query comparing two
    # drugs' depletion cannot use `percent_consumed` without it.
    "percent_consumed": "float",
    "percent_consumed_std": "float",
    "fold_change": "float",
    "fold_change_std": "float",
    "fdr_p_value": "float",
    "drug_threshold_percent": "float",
    "incubation_hours": "float",
    "replicates": "integer",
    # The drug end: what the sheet said, and how it reached a node.
    "reported_drug_name": "string",
    "parent_drug_name": "string",
    "therapeutic_indication": "string",
    "drug_join": "string",
    # The taxon end: the same two questions, one per sheet.
    "screen_column": "string",
    "reported_name": "string",
    "strain": "string",
    "phylum": "string",
    "reported_rank": "string",
    "original_rank": "string",
    "resolution_status": "string",
    "strain_join": "string",
    "taxon_join": "string",
    # Supplementary table 13's gain-of-function screen, on the 37 pairs it
    # covers and empty on the other 20,017.
    "gene_locus_tags": "string",
    "gene_products": "string",
    "gene_protein_ids": "string",
    "n_gene_products": "integer",
}

#: What this source adds to the ``Drug`` node ChEMBL owns. Three columns, empty
#: on every row the other sources wrote and filled on the ones minted here.
#:
#: They are on the *node* only for minted drugs, and that asymmetry is the
#: model's: ``drug.csv`` is keyed on ``drug_id`` and the first row per key wins,
#: so a screen fact about a drug ChEMBL or Maier already holds cannot be written
#: onto its node at all. Anything a query needs for *every* screened drug —
#: ``therapeutic_indication`` — therefore rides on the edge as well.
DRUG_PROPERTY_TYPES: dict[str, str] = {
    "cas": "string",
    "trade_name": "string",
    "therapeutic_indication": "string",
}


def _declaration(description: str) -> dict:
    return {
        "domain": "Taxon",
        "range": "Drug",
        "required_properties": list(METABOLISM_CONTRACT),
        "property_types": METABOLISM_PROPERTY_TYPES,
        # Both at `error`: every one of the nine is written by this prep
        # unconditionally rather than read from upstream, so a violation is a bug
        # in this repo and not a gap in someone's curation. The rule should sit
        # at zero — and it can still move, which is what makes it worth having.
        "enforcement": {"required_properties": "error", "property_types": "error"},
        "description": description,
    }


#: Declared here too, and identically, because this source writes rows into the
#: ``Drug`` table ChEMBL owns. The shared sentence lives in
#: :data:`.vocabulary.DRUG_DESCRIPTION` — fragment merging raises on a
#: contradicting scalar, which is what a second author of a description is.
CLASSES: dict[str, dict] = {
    "Drug": {"description": DRUG_DESCRIPTION},
}

RELATIONSHIPS: dict[str, dict] = {
    RELATION_METABOLISES: _declaration(
        "A gut bacterium that depleted this drug in monoculture, in the "
        "Zimmermann 2019 screen of 76 human gut strains against 271 orally "
        "administered drugs. The reverse direction from `INHIBITS_GROWTH_OF`: "
        "the bacterium is the agent and the drug is what changes. One edge per "
        "(strain, drug) cell, so two isolates of one species are two edges on "
        "one taxon, told apart by `screen_column` and `strain`."
    ),
    RELATION_NO_METABOLISM: _declaration(
        "A drug the same screen gave to this bacterium and measured **no** "
        "depletion of. Its own relationship rather than a flag, so no query "
        "counts a measured non-hit as metabolism by omission — and the "
        "population that makes 'this strain was given this drug and did nothing "
        "to it' answerable at all."
    ),
}

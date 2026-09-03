"""Maier 2018: the drug↔bug screen, and the 42,233 measured non-hits that come
with it.

This source adds the two relationships D8 has been waiting for since ChEMBL
landed — ``INHIBITS_GROWTH_OF`` and ``DOES_NOT_INHIBIT_GROWTH_OF`` — over the
published 1,197-drug × 40-strain growth screen (Maier et al., *Nature*
555:623-628, 2018; PMID 29555994). It is the first source in this graph that
states a **direct** drug→taxon effect: ChEMBL's only path from a drug to a
taxon runs through the protein it acts on, which is a different claim, and
gutMDisorder's ``ABUNDANCE_CHANGED_BY`` is an abundance observation in a host,
not a growth measurement in culture.

Five decisions this module records.

**The negatives are half the value, and they get their own relationship.** The
screen measured every one of the 1,197 × 40 cells, so a non-hit here is a
*measurement* rather than an absence of curation — the thing no other source in
this graph has for drugs. 5,592 cells are hits and 42,233 are measured
non-hits. They land as :data:`RELATION_NO_EFFECT` rather than as a flag on the
positive edge, for the reason NJC19's ``NO_EXCHANGE_WITH`` does: a refutation
stored as a property is counted as an observation by every query that does not
know to exclude it, and nothing in the query text would say so. Part D's D8
states the same rule from the other side — ``ALTERS_TAXON`` and
``ALTERS_SUBSTANCE``, "two edge types, never one". ``effect`` rides on both
edges as well, so a query that wants the population undivided has one property
to group on rather than a union of two labels.

**The hit threshold is p < 0.01, derived from the file and confirmed three
ways.** The supplementary table publishes adjusted p-values and an ``n_hit``
count per drug but never states the cutoff. :data:`HIT_THRESHOLD` reproduces
``n_hit`` on **all 1,197 rows** — 0.05 reproduces 791 of them and 0.001
reproduces 879 — and it independently reproduces the per-species
human-targeted hit counts in *both* figure source-data files (MOESM16 sheet
``5a``, 40 of 40 species; MOESM13 sheet ``1c``, 25 of 25), and the paper's own
headline: 203 of 835 human-targeted drugs hit at least one strain = **24.3%**,
against the abstract's "24% of the drugs with human targets".

**A drug reaches ChEMBL by three routes and the route is on every edge.** 842
of 1,197 join — name 455, ATC 361, salt-stripped name 26 — and 355 are minted
on their Prestwick catalogue number. The
Prestwick library names salts and catalogue forms; ChEMBL keys on the parent
molecule. :func:`drug_variants` orders the attempts the way
``njc19.name_variants`` does — what the source wrote before anything derived
from it: the exact casefolded ``pref_name``, then a level-5 ATC code, then the
name with a salt suffix removed. ``drug_join`` says which one matched, so the
weakest route is countable rather than assumed, and a drug none of them reaches
is minted on its Prestwick catalogue number rather than dropped.

**Two routes reaching two different nodes is a ledger row, never a silent
winner, and there are two shapes of it.** On **29** drugs the name route
matched a ChEMBL *salt* node while the ATC code matched its parent —
``Estradiol Valerate`` reaches CHEMBL1511 by name and CHEMBL135 (estradiol) by
ATC. That is ChEMBL's documented parent gap showing through (a salt no
mechanism row names keeps its own id, docs/model.md §ChEMBL), not a defect
here; the verbatim-first rule decides it and
``data/csv/unresolved_maier2018.csv`` names both candidates, so the count can be
read rather than trusted. The other shape runs the other way: **54 ATC codes
are claimed by two *library* entries** — ``(R)-`` and ``(S)-propranolol
hydrochloride`` share C07AA05, ``Racecadotril`` shares A06AX02 with its active
metabolite ``Thiorphan`` — and joining both to the one node that code names
would attribute one enantiomer's measurement to the other. A contested code is
a join key for neither, which is the same uniqueness rule the ChEMBL side
already applies to a code two ChEMBL nodes claim, and it is what makes the
library's 1,197 entries reach 1,197 distinct nodes rather than 1,180.

**Two of the forty organism strings are not taxon names, and they are named
here rather than left to fail.** Supplementary table 2's ``Species`` column
carries the *B. fragilis* toxigenicity phenotype inline — ``Bacteroides
fragilis nontoxigenic`` and ``Bacteroides fragilis enterotoxigenic (ET)`` —
which no ``names.dmp`` entry spells. Sending them through ``reconcile`` writes
two ``UnresolvedTaxon`` tombstones asserting NCBI has lost *Bacteroides
fragilis*, which is false, and costs 2,394 edges. :data:`SPECIES_OVERRIDES` is
the same shape as ``njc19.HOST_CELL_TYPES``: a closed, reviewable map of the
verbatim strings this file uses, with the isolate qualifier kept on the edge as
``reported_name`` and ``strain`` so nothing about the isolate is lost.
"""

from __future__ import annotations

import re

from ..drugs import atc_level5, strip_salt
from .vocabulary import DRUG_DESCRIPTION, register_source

__all__ = [
    "ASSOCIATION_RELATIONSHIPS",
    "CLASSES",
    "DRUG_PROPERTY_TYPES",
    "EVIDENCE_LEVEL",
    "GROWTH_CONTRACT",
    "GROWTH_PROPERTY_TYPES",
    "GROWTH_RELATIONSHIPS",
    "HIT_THRESHOLD",
    "PUBLICATION",
    "PUBMED_ID",
    "RANK_CEILING",
    "RELATION_INHIBITS",
    "RELATION_NO_EFFECT",
    "REPORTED_RANK",
    "SCREEN_CONCENTRATION_UM",
    "SOURCE",
    "SOURCE_RELATIONS",
    "SPECIES_OVERRIDES",
    "drug_variants",
    "effect_of",
    "nt_code_of",
    "pubchem_cid",
    "relation_for",
]

SOURCE = "maier2018"

#: **Every edge is a curator transcribing a published growth measurement.** The
#: screen itself is a laboratory assay, but what this loader reads is the
#: authors' own hit call in a supplementary table — a person asserting "this
#: drug inhibited this strain", which is Biolink's ``knowledge_assertion`` by a
#: ``manual_agent``, the same pair NJC19 and HMDB carry.
#:
#: The licence is the weakest in the graph and the token says so rather than
#: guessing. Journal supplementary material carries no separate data licence,
#: the article is not open access, and inventing ``CC-BY-4.0`` on 47,825 edges
#: would put a redistribution claim in the graph that nobody made. G3's per-edge
#: licence is what keeps that one token from contaminating everything else:
#: ``WHERE r.source_licence <> 'Maier2018-unstated'`` is the shippable cut.
register_source(
    SOURCE,
    knowledge_level="knowledge_assertion",
    agent_type="manual_agent",
    licence="Maier2018-unstated",
)

#: This source declares no taxon–condition association: it is an in-vitro
#: growth screen, not a differential-abundance corpus.
ASSOCIATION_RELATIONSHIPS: tuple[str, ...] = ()

#: The one ``evidence_level`` this source emits. Part B's ``in-vitro`` row names
#: exactly this shape — "measured in culture: growth, a metabolite assay, an MIC
#: over controls" — and the file carries no per-row design, host or assay column
#: that could move it. Stated here rather than spelled at the write site.
EVIDENCE_LEVEL: str = "in-vitro"

#: The paper, as Part D's D8 cites it. Carried as ``publications`` on every edge
#: and as an integer ``pmid``, the way CARD carries its determinant citations —
#: no ``Paper`` node is minted, because one node with 47,825 edges would
#: dominate every path query in the graph for no gain over the property.
PUBMED_ID: int = 29555994
PUBLICATION: str = f"PMID:{PUBMED_ID}"

#: Adjusted p below which the authors called a drug–strain pair a hit.
#:
#: **Derived, not read: the supplementary table publishes the p-values and an
#: ``n_hit`` count but never states the cutoff.** This value reproduces
#: ``n_hit`` on all 1,197 rows of ``S3a. Adjusted p-values``; 0.05 reproduces
#: 791 and 0.001 reproduces 879. It then reproduces two things it was not fitted
#: to — the per-species human-targeted hit counts in the two figure source-data
#: workbooks (MOESM16 ``5a``: 40 of 40; MOESM13 ``1c``: 25 of 25) and the
#: paper's abstract ("24% of the drugs with human targets", measured here at
#: 203 of 835 = 24.3%). Three independent confirmations, which is what a
#: constant this load-bearing needs: get it wrong and every edge in this source
#: is the wrong type.
HIT_THRESHOLD: float = 0.01

#: The single concentration every drug was screened at, in µM. Supplementary
#: table 1's ``screen conc. (20 µM as µg/ml)`` column restates it per drug in
#: mass units; the molar figure is one number for the whole screen, which is
#: what makes ``no-effect`` a bounded claim ("not at 20 µM") rather than an
#: unbounded one.
SCREEN_CONCENTRATION_UM: float = 20.0

#: The hit relationship, and the measured non-hit. Two types, never one — the
#: rule Part D's D8 states for the drug↔taxon layer and the rule NJC19's
#: ``NO_EXCHANGE_WITH`` already applies to the exchange layer.
RELATION_INHIBITS: str = "INHIBITS_GROWTH_OF"
RELATION_NO_EFFECT: str = "DOES_NOT_INHIBIT_GROWTH_OF"

#: The two relationships in the order the build report prints them.
GROWTH_RELATIONSHIPS: tuple[str, ...] = (RELATION_INHIBITS, RELATION_NO_EFFECT)

#: relationship -> ``(effect, source_relation)``. ``effect`` is the value a
#: query groups on when it wants the whole measured population; the
#: ``source_relation`` is the screen's own wording of the call, threshold and
#: all, so the normalisation stays reversible (G3).
SOURCE_RELATIONS: dict[str, tuple[str, str]] = {
    RELATION_INHIBITS: ("inhibited", f"screen hit (adjusted p < {HIT_THRESHOLD})"),
    RELATION_NO_EFFECT: (
        "no-effect",
        f"screened, not a hit (adjusted p >= {HIT_THRESHOLD})",
    ),
}

#: What the source says it screened. Supplementary table 2 files each row under
#: a ``Species`` name *and* a ``Strain`` designation with a DSM/ATCC number, so
#: the unit of measurement is an isolate; ``original_rank`` carries NCBI's rank
#: for whatever the name first resolved to, which is how G5's two-rank split
#: works everywhere else in this graph.
REPORTED_RANK: str = "strain-level isolate"

#: Broadest NCBI rank a growth claim may be made at. Every organism here is a
#: single cultured isolate, so — as in NJC19 — this is a guard against a
#: promotion surprise rather than a working filter.
RANK_CEILING: str = "genus"

#: The ``Species`` strings supplementary table 2 writes that are not taxon
#: names, mapped to the binomial NCBI does spell.
#:
#: Both are *Bacteroides fragilis* isolates with the toxigenicity phenotype
#: appended — the paper screened a non-toxigenic and an enterotoxigenic strain
#: side by side and the column carries the distinction inline. Neither string is
#: in ``names.dmp``, so without this map they become two ``UnresolvedTaxon``
#: tombstones each asserting NCBI has lost *Bacteroides fragilis* — a false
#: statement about the taxonomy arrived at by doing nothing — and 2,394 edges
#: go with them. Closed and enumerated rather than a suffix-stripping rule: the
#: qualifier is two hand-written phrases in one file, not a grammar, and
#: guessing at the general case is how a loader mangles the next name. The
#: strings survive verbatim on the edge as ``reported_name``, with the isolate's
#: own designation in ``strain``, so the two isolates stay distinguishable on a
#: shared taxon.
SPECIES_OVERRIDES: dict[str, str] = {
    "bacteroides fragilis nontoxigenic": "Bacteroides fragilis",
    "bacteroides fragilis enterotoxigenic (et)": "Bacteroides fragilis",
}

#: ``Akkermansia muciniphila (NT5021)`` — how ``S3a``'s column headers name a
#: screened isolate. The NT code is the join onto supplementary table 2 and is
#: the only stable half: the label is a display spelling that differs from the
#: species dictionary's own (``Fusobacterium nucleatum`` against
#: ``Fusobacterium nucleatum subsp. Nucleatum``).
_COLUMN_NT = re.compile(r"\((?P<code>NT\d+)\)\s*$")

#: ``CID100008646`` — STITCH's compound id. The leading digit is its
#: stereo-specific flag (``1`` on all 1,200 rows) and the remaining eight digits
#: are the PubChem CID, zero-padded.
_STITCH = re.compile(r"^CID(?P<flavour>\d)(?P<cid>\d{8})$")


def nt_code_of(column_header: str) -> str:
    """The ``NT`` code an ``S3a`` species column names, or ``""``.

    The four metadata columns return ``""``, which is how the reader finds where
    the species columns begin without counting them.
    """
    match = _COLUMN_NT.search((column_header or "").strip())
    return match.group("code") if match else ""


def pubchem_cid(stitch_id: str | None) -> str:
    """The PubChem CID inside a STITCH4 id, as a bare integer string.

    ``CID100008646`` -> ``8646``. Returns ``""`` for anything that is not a
    STITCH id, so a future release changing the spelling produces an empty
    property rather than a plausible wrong number.
    """
    match = _STITCH.match(str(stitch_id or "").strip())
    return str(int(match.group("cid"))) if match else ""


def drug_variants(name: str, atc_cell: str | None) -> list[tuple[str, str, str]]:
    """``(kind, key, join route)`` attempts for one Prestwick drug, in order.

    The order *is* the policy, and it is ``njc19.name_variants``' policy applied
    to a different identifier space: what the source wrote is tried before
    anything derived from it.

    ``name``
        the catalogue name verbatim, against ChEMBL's ``pref_name``.
    ``atc``
        each level-5 ATC code the row carries, against ChEMBL's ``atc_codes``.
        A real identifier rather than a spelling, and the route that reaches the
        parent molecule for the salts the catalogue names.
    ``salt-name``
        the name with a salt or hydrate suffix removed, against ``pref_name``
        again.

    ``kind`` is ``"name"`` or ``"atc"`` and says which index the caller should
    look the key up in; ``route`` is what goes on the edge.
    """
    out: list[tuple[str, str, str]] = [("name", (name or "").strip(), "name")]
    for code in atc_level5(atc_cell):
        out.append(("atc", code, "atc"))
    bare = strip_salt(name)
    if bare and bare.casefold() != (name or "").strip().casefold():
        out.append(("name", bare, "salt-name"))
    return out


def relation_for(adjusted_p: float | None) -> str | None:
    """The relationship one screen cell becomes, or ``None`` when unmeasured.

    ``None`` is the answer for the 55 cells the table writes as the literal
    string ``NA``: a drug–strain pair the screen did not measure is neither a
    hit nor a non-hit, and calling it either would invent a measurement. Those
    are ledger rows.
    """
    if adjusted_p is None:
        return None
    return RELATION_INHIBITS if adjusted_p < HIT_THRESHOLD else RELATION_NO_EFFECT


def effect_of(relationship: str) -> str:
    """``inhibited`` / ``no-effect`` for a relationship name."""
    return SOURCE_RELATIONS[relationship][0]


#: What a growth-screen edge must carry, and the applicable subset it is.
#:
#: Eight of the association contract's fourteen describe a differential-
#: abundance observation — ``direction``, the two group sizes, ``sequencing_type``,
#: ``statistical_test``, ``study_design`` — and a monoculture growth screen has
#: none of them. Declaring them would report a permanent ~100% violation meaning
#: "this is not an abundance study" rather than "this evidence is missing", the
#: same reasoning that gave CARD eight properties and ChEMBL's ``HAS_MECHANISM``
#: seven.
#:
#: ``effect`` is required alongside the provenance block because it is the one
#: field that says which of the two measurements an edge *is*, and an edge
#: without it would be a growth claim of unknown sign.
GROWTH_CONTRACT: list[str] = [
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

#: Declared types for every property a growth edge carries. The contract's nine
#: plus what a D8 or D18 query reads: how strong the call was, at what
#: concentration, which drug and isolate the row named, and how each end of the
#: edge was reached.
GROWTH_PROPERTY_TYPES: dict[str, str] = {
    **{field: "string" for field in GROWTH_CONTRACT},
    "pmid": "integer",
    "adjusted_p_value": "float",
    "screen_concentration_um": "float",
    # The drug end: what the sheet said, and how it reached a node.
    "prestwick_id": "string",
    "reported_drug_name": "string",
    "drug_class": "string",
    "drug_join": "string",
    # The taxon end: the same two questions.
    "nt_code": "string",
    "reported_name": "string",
    "strain": "string",
    "gram_stain": "string",
    "reported_rank": "string",
    "original_rank": "string",
    "resolution_status": "string",
    "taxon_join": "string",
    # Supplementary table 4's dose-response follow-up, on the 379 pairs it
    # covers and empty on the other 47,446. `validation_outcome` is the
    # authors' own confusion matrix against the screen call, so a false
    # positive and a false negative in the primary screen are both countable.
    "ic25_um": "float",
    "ic25_qualifier": "string",
    "mic_um": "float",
    "mic_qualifier": "string",
    "validation_outcome": "string",
}

#: What this source adds to the ``Drug`` node ChEMBL owns. Four columns, empty
#: on ChEMBL's 6,030 rows and filled on the ones minted here.
#:
#: They are on the *node* only for minted drugs, and that asymmetry is the
#: model's, not a shortcut: ``drug.csv`` is keyed on ``drug_id`` and the first
#: row per key wins, so a Prestwick fact about a drug ChEMBL already holds
#: cannot be written onto its node at all (the same constraint
#: docs/model.md records for MASI). ``drug_class`` therefore rides on the
#: **edge**, where it is available for every drug in the screen rather than only
#: for the third of them this source minted.
DRUG_PROPERTY_TYPES: dict[str, str] = {
    "prestwick_id": "string",
    "pubchem_cid": "string",
    "screen_drug_class": "string",
    "screen_target_species": "string",
}


def _declaration(description: str) -> dict:
    return {
        "domain": "Drug",
        "range": "Taxon",
        "required_properties": list(GROWTH_CONTRACT),
        "property_types": GROWTH_PROPERTY_TYPES,
        # Both at `error`, unlike the association contract's warn/error split:
        # every one of the nine is written by this prep unconditionally rather
        # than read from upstream, so a violation is a bug in this repo and not
        # a gap in someone's curation. The rule should sit at zero — and it can
        # still move, which is what makes it worth declaring.
        "enforcement": {"required_properties": "error", "property_types": "error"},
        "description": description,
    }


#: Declared here too, and identically, because this source writes rows into the
#: ``Drug`` table ChEMBL owns: the fragment that adds rows to a shared node type
#: declares it, so a maier2018-only build still carries the class. The shared
#: sentence lives in :data:`.vocabulary.DRUG_DESCRIPTION` — fragment merging
#: raises on a contradicting scalar, which is what a second author of a
#: description is.
CLASSES: dict[str, dict] = {
    "Drug": {"description": DRUG_DESCRIPTION},
}

RELATIONSHIPS: dict[str, dict] = {
    RELATION_INHIBITS: _declaration(
        "A drug that inhibited this gut bacterium's growth in monoculture at "
        "20 µM, in the Maier 2018 screen of 1,197 marketed drugs against 40 "
        "human gut isolates. One edge per (drug, isolate) cell; two isolates of "
        "one species are two edges on one taxon, told apart by `nt_code`."
    ),
    RELATION_NO_EFFECT: _declaration(
        "A drug the same screen measured against this bacterium and found **no** "
        "growth inhibition at 20 µM. Its own relationship rather than a flag, so "
        "no query counts a measured non-hit as an inhibition by omission — and "
        "the population that makes 'this drug was tested and did nothing' "
        "answerable at all, which no other source in this graph supports."
    ),
}

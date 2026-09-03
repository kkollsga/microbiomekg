"""MiMeDB: the metabolite half of D5's answer, and the reason the other half is
still missing.

**The finding this module exists to record: the MiMeDB v1.0 downloads carry no
microbe–metabolite association at all, so they cannot close D5.** Both bulk
files are Sequel Ace dumps of a single MySQL table each —
``SELECT * FROM microbes WHERE export = 1`` (2,174 rows) and ``SELECT * FROM
metabolites WHERE export = 1`` (27,641 rows) — and the join between them is not
in either. Measured on the files on disk: the metabolites dump contains **zero**
occurrences of the string ``MMDBm`` (a microbe id) and the microbes dump
contains **zero** occurrences of ``MMDBc`` (a metabolite id). There is no
``Microbial Sources`` column, no ``Metabolic Reactions`` table, no precursor,
product, enzyme or reaction-type field. The research document
(§1.7) named the per-microbe "download all related metabolites as CSV" button as
"the most direct route to an edge list", and that is a per-microbe web action on
a site that answers automated clients with 403 — not something either bulk file
carries.

So this loader writes **`Metabolite` nodes and nothing else**: no ``PRODUCES``,
no relationship of any kind. Inventing a taxon–metabolite edge out of the
microbes table's ``activity`` column — 43 rows saying ``Production (export)``
with no compound named anywhere — would be manufacturing the exact claim D5
asks for out of a field that does not make it. D5's status is unchanged by this
source and `docs/usecases-and-pitfalls.md` says so with the numbers.

**What it does contribute is identity, and it is measurable.** NJC19 names its
compounds in free text with **no cross-reference of any kind** — no ChEBI, HMDB,
KEGG, PubChem or InChIKey on any of its 283 — so a compound HMDB does not hold
becomes a minted ``NJC19:`` stub with no structure. MiMeDB's names close some of
those: measured on the full build, **25 of the metabolites NJC19's 8,905 edges
land on are MiMeDB nodes, carrying 279 of those edges** — ``Pectin``,
``Chitin``, ``Inulin``, ``Stachyose``, ``Menaquinone``, ``alpha-ketoglutarate``
and others — each with an InChIKey, a formula and, for about half, an HMDB
accession. That is why :data:`SELECTION_RULES` has an ``njc19-compound`` rule
and why this prep reads NJC19's spreadsheet the way ``prep_hmdb.py`` reads
Reactome's ChEBI file: the selection rule has to be decidable in one pass, and
the alternative is loading 27,641 compounds of which 12,105 are
glycerophospholipids.

**Two identity traps in the file, both of which would merge distinct compounds.**

*The ``hmdb_id`` column is neither uniformly spelled nor unique.* It holds both
the padded (``HMDB0003402``) and the legacy unpadded (``HMDB03402``) form, so a
literal join misses; and after normalising the padding, **149 accessions are
claimed by two MiMeDB records each** — ``HMDB0000158`` by both ``L-Tyrosine``
and ``D-Tyrosine``, ``HMDB0000598`` by both ``Sulfide`` and ``Sulfur``,
``HMDB0000208`` by both ``Oxoglutaric acid`` and ``alpha-Ketoglutarate``.
Joining on it unconditionally would fold a D-amino acid onto its L- enantiomer's
node and attribute one's annotations to the other. So a contested accession is
**not a join key**: both records keep their own ``MIMEDB:`` identity and the
ledger says why, which is the same rule ``reconcile`` applies to an ambiguous
organism name.

*A MiMeDB record whose accession an HMDB record already claims is not written at
all.* It would be a second node for one compound, and the first one is the one
Reactome's pathway edges and HMDB's production edges already point at. Those
rows are counted and ledgered rather than merged, because :class:`Writer`'s
first-row-per-key rule means a merged row's properties would be silently
discarded anyway — an outcome that reads like a successful join in the row
count and is not one.

**Licence: CC BY-NC 4.0** — non-commercial, which is why `source_licence` is on
the node. It is stated on `mimedb.org` and in the NAR paper; the dumps
themselves carry no licence header, so `data/raw/mimedb/PROVENANCE.md` records
it as documented-not-verified-in-file.
"""

from __future__ import annotations

from .vocabulary import register_source

__all__ = [
    "ASSOCIATION_RELATIONSHIPS",
    "CLASSES",
    "OBSERVED_FLAGS",
    "RELATIONSHIPS",
    "SELECTION_RULES",
    "SOURCE",
    "normalise_hmdb_id",
]

SOURCE = "mimedb"

#: MiMeDB curates by hand from peer-reviewed sources ("only peer-reviewed
#: sources… Exclusion criteria included non-peer-reviewed reports, animal-only
#: studies without demonstrated human analogs, and in vitro findings lacking
#: validation"), so the pair is a curator's assertion — the same as HMDB's, and
#: for the same reason. It is registered even though this source writes no edge:
#: `Metabolite.source_licence` is read from the same table, and a source whose
#: evidence model nobody had read would have to reach `not_provided`.
register_source(
    SOURCE,
    knowledge_level="knowledge_assertion",
    agent_type="manual_agent",
    licence="CC-BY-NC-4.0",
)

#: MiMeDB declares no taxon–condition association, and — the point of the module
#: docstring — no taxon–metabolite one either.
ASSOCIATION_RELATIONSHIPS: tuple[str, ...] = ()

#: **No relationship at all.** The dumps carry no association between the two
#: tables they hold; see the module docstring for the measurement. A source that
#: contributes only nodes is a legitimate outcome and is stated rather than
#: worked around.
RELATIONSHIPS: dict[str, dict] = {}

#: The two columns that mean somebody measured the compound in a human sample.
#: Both are ``1`` on exactly the same 711 rows, which is the file saying
#: "detected, and also quantified" rather than two independent facts.
OBSERVED_FLAGS: tuple[str, ...] = ("detected", "quantified")

#: Why a MiMeDB record is loaded. The whole file is not: 27,641 records of which
#: 12,105 are glycerophospholipids is a lipidomics table, and a metabolite that
#: no edge can ever reach and no query names is an unconnected node.
#:
#: ``observed``
#:     ``detected`` or ``quantified`` is ``1`` — 711 records, the ones measured
#:     in a human biospecimen.
#: ``origin-classified``
#:     ``metabolite_type`` is filled — 719 records, ``Co-metabolite`` (663) or
#:     ``Primary`` (56). This is MiMeDB's origin axis, the one thing the
#:     research document found it grades on an evidence basis, and it is the
#:     nearest this file comes to saying "microbial".
#: ``njc19-compound``
#:     its name is one NJC19 names, **and no spelling of that compound reaches a
#:     node yet** — the compounds that turn an NJC19 exchange edge from a minted
#:     stub into an identified one. The second half of the condition is not
#:     tidiness: without it this rule mints a node for a compound the graph
#:     already holds under a different spelling, and NJC19 then prefers the new
#:     one. Measured on ``Propanoate (Propionate)``, which HMDB holds as
#:     ``Propionic acid`` and MiMeDB names ``propanoic acid``: 97 NJC19
#:     propionate producers landed on a node HMDB's 12 were not on, splitting
#:     one compound's evidence in half and computing D6's MES over each half.
SELECTION_RULES: tuple[str, ...] = ("observed", "origin-classified", "njc19-compound")


def normalise_hmdb_id(raw: str | None) -> str:
    """``HMDB03402`` and ``HMDB0003402`` -> ``HMDB0003402``; anything else -> ``""``.

    HMDB widened its accessions from five digits to seven in 2018 and MiMeDB's
    column holds both spellings — 3,864 filled values across the file. A literal
    string join therefore misses every legacy id, and misses it *silently*,
    which reads as "MiMeDB has no HMDB id for this compound".
    """
    text = (raw or "").strip()
    if text in ("", "NULL"):
        return ""
    if not text.upper().startswith("HMDB"):
        return ""
    digits = text[4:]
    return f"HMDB{int(digits):07d}" if digits.isdigit() else ""


CLASSES: dict[str, dict] = {
    "Metabolite": {
        "description": "A small molecule, keyed on its ChEBI CURIE where HMDB "
        "carries a chebi_id and on its HMDB accession otherwise. `status` says "
        "whether anyone has measured it: 88.8% of HMDB is predicted or expected.",
    },
}

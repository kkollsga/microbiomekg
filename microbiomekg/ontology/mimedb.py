"""MiMeDB: the metabolite half of D5's answer, and the reason the other half is
still missing.

**The finding this module exists to record: no published MiMeDB bulk file
carries a microbe–metabolite association, in v1.0 or in v2.0, so neither can
close D5.** Every bulk download is a Sequel Ace dump of a single MySQL table —
``SELECT * FROM microbes WHERE export = 1`` and ``SELECT * FROM metabolites
WHERE export = 1`` — and the join between them is in none of them. Measured on
the bytes of all four v2 files (dumped 2025-10-08, 29,295 metabolites and 2,648
microbes): the metabolites CSV **and** XML contain **zero** occurrences of the
string ``MMDBm`` (a microbe id) and the microbes CSV **and** XML contain
**zero** occurrences of ``MMDBc`` (a metabolite id). Each control fires — every
metabolite row carries its own ``MMDBc`` id and every microbe row its own
``MMDBm``, 29,295 and 2,648 times — so the zeros are a measurement and not a
mis-spelled pattern. There is no ``Microbial Sources`` column, no ``Metabolic
Reactions`` table, no precursor, product, enzyme or reaction-type field.

**v2.0 states the size of the edge list it withholds.** Its new
``microbe_relations`` column is an integer per metabolite — MiMeDB's own count
of the microbes it relates that compound to — filled on all 29,295 rows and
summing to **830,984 pairs**, with not one microbe id anywhere in the file to
say *which*. The pairs exist in their database and are reachable only through
the site's per-metabolite web pages, which this project does not scrape. That
count rides on the node as :data:`MICROBE_RELATION_COUNT`; see its own comment
for why it is not named ``microbe_relations``.

So this loader writes **`Metabolite` nodes and nothing else**: no ``PRODUCES``,
no relationship of any kind. Inventing a taxon–metabolite edge out of the
microbes table's ``activity`` column — 115 rows in v2 (113 ``Production
(export)``, 2 ``Consumption (import)``) with no compound named anywhere — would
be manufacturing the exact claim D5 asks for out of a field that does not make
it. Nor does that column become a ``Taxon`` property: ``docs/model.md`` records
the reason under §"MiMeDB". D5's status is unchanged by this source and
`docs/usecases-and-pitfalls.md` says so with the numbers.

**What it does contribute is identity, and it is measurable.** NJC19 names its
compounds in free text with **no cross-reference of any kind** — no ChEBI, HMDB,
KEGG, PubChem or InChIKey on any of its 283 — so a compound HMDB does not hold
becomes a minted ``NJC19:`` stub with no structure. MiMeDB's names close some of
those: ``Pectin``, ``Chitin``, ``Inulin``, ``Stachyose``, ``Menaquinone``,
``alpha-ketoglutarate`` and others, each with an InChIKey, a formula and, for
about half, an HMDB accession. v2 adds four cross-references v1 had no column
for — see :data:`V2_ONLY_COLUMNS` — of which ``cmmc_inchikey`` is the one that
must never become a join key. That is why :data:`SELECTION_RULES` has an
``njc19-compound`` rule and why this prep reads NJC19's spreadsheet the way
``prep_hmdb.py`` reads Reactome's ChEBI file: the selection rule has to be
decidable in one pass, and the alternative is loading 29,295 compounds of which
12,105 are glycerophospholipids.

**Two identity traps in the file, both of which would merge distinct
compounds, and v2 kept both.**

*The ``hmdb_id`` column is neither uniformly spelled nor unique.* It holds both
the padded (``HMDB0003402``) and the legacy unpadded (``HMDB03402``) form — 258
of v2's 3,904 filled values are legacy — so a literal join misses; and after
normalising the padding, **149 accessions are claimed by two or more MiMeDB
records each, 329 records in all**: ``HMDB0000158`` by both ``L-Tyrosine`` and
``D-Tyrosine``, ``HMDB0000598`` by both ``Sulfide`` and ``Sulfur``,
``HMDB0000208`` by both ``Oxoglutaric acid`` and ``alpha-Ketoglutarate``.
Joining on it unconditionally would fold a D-amino acid onto its L- enantiomer's
node and attribute one's annotations to the other. So a contested accession is
**not a join key**: both records keep their own ``MIMEDB:`` identity and the
ledger says why, which is the same rule ``reconcile`` applies to an ambiguous
organism name.

*A MiMeDB record whose compound the graph already holds is not written at all.*
It would be a second node for one compound, and the first one is the one
Reactome's pathway edges and HMDB's production edges already point at. Those
rows are counted and ledgered rather than merged, because :class:`Writer`'s
first-row-per-key rule means a merged row's properties would be silently
discarded anyway — an outcome that reads like a successful join in the row
count and is not one.

**Licence: CC BY-NC 4.0** — non-commercial, which is why `source_licence` is on
the node. It is stated on `mimedb.org` and in the NAR papers; the dumps
themselves carry no licence header, so `data/raw/mimedb/v2/PROVENANCE.md`
records it as documented-not-verified-in-file.
"""

from __future__ import annotations

from .vocabulary import register_source

__all__ = [
    "ASSOCIATION_RELATIONSHIPS",
    "CLASSES",
    "MICROBE_RELATION_COUNT",
    "OBSERVED_FLAGS",
    "RELATIONSHIPS",
    "SELECTION_RULES",
    "SOURCE",
    "V2_ONLY_COLUMNS",
    "V2_ONLY_MICROBE_COLUMNS",
    "normalise_hmdb_id",
    "release_of",
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

#: **No relationship at all.** No published release carries an association
#: between the two tables it dumps; see the module docstring for the
#: measurement. A source that contributes only nodes is a legitimate outcome and
#: is stated rather than worked around.
RELATIONSHIPS: dict[str, dict] = {}

#: The two columns that mean somebody measured the compound in a human sample.
#: In v1 they were ``1`` on exactly the same 711 rows — the file saying
#: "detected, and also quantified" rather than two independent facts. **v2 split
#: them**: 1,674 rows are detected and 1,413 quantified, so the rule is a real
#: disjunction now and not a doubled-up single flag.
OBSERVED_FLAGS: tuple[str, ...] = ("detected", "quantified")

#: Columns v2.0 added to the metabolites dump and v1.0 has no header for. Three
#: are cross-references this graph has no other source for; the fourth is a
#: count. They are the reason to prefer v2 — the association is *not*, because
#: v2 does not carry one either.
#:
#: ``cmmc_inchikey`` is a cross-reference and **never a join key**: it is the
#: InChIKey of the *parent* compound in the Chemically Modified Microbial
#: Compounds set, and on 428 of the 1,763 rows that fill it, it differs from the
#: record's own ``moldb_inchikey``. Matching on it would fold a microbial
#: conjugate onto the compound it was made from — the same merge the contested
#: accession rule refuses, arriving through a column that looks authoritative.
V2_ONLY_COLUMNS: tuple[str, ...] = (
    "epa_substance_id",
    "epa_compound_id",
    "microbe_relations",
    "cmmc_inchikey",
)

#: Columns v2.0 added to the *microbes* dump. Nothing is loaded from that table,
#: so these exist for one reason: :func:`release_of` is asked which release a
#: file is, and the two tables grew different columns. Checking a microbes
#: header against the metabolite list alone reports every v2 microbes dump as
#: v1.0 — measured, on the fixture, before this list existed.
#:
#: ``description`` is free prose and the only place either v2 file says the word
#: "metabolite" (125 rows). It names compounds in sentences, with no column, no
#: direction and no citation, so it is not an association either — a parser over
#: it would be manufacturing D5's answer out of generated text.
V2_ONLY_MICROBE_COLUMNS: tuple[str, ...] = (
    "subspecies",
    "serotype",
    "variant",
    "basys2_id",
    "description",
)

#: The columns :func:`release_of` may key on: new in v2 **and** used by no v1
#: header. ``description`` is new to the microbes table and has been in the
#: *metabolites* table since v1, so including it reports every v1 metabolites
#: dump as v2.0 — measured, and caught by the fallback test rather than by
#: reading. A marker has to be absent from both v1 headers, not just from the
#: one table it was added to.
_RELEASE_MARKERS: frozenset[str] = (
    frozenset(V2_ONLY_COLUMNS) | frozenset(V2_ONLY_MICROBE_COLUMNS)
) - {"description"}

#: The node property carrying v2's ``microbe_relations``.
#:
#: **It is MiMeDB's own count of the microbes it relates a metabolite to, and
#: the bulk download does not enumerate them.** The number is real — 830,984
#: pairs summed over the file, up to 4,055 on a single compound — and not one of
#: the microbes is named anywhere in any published file, so nothing in this
#: graph can be derived from it. It is loaded because it is the only published
#: measurement of *how much* MiMeDB is withholding, and it is deliberately
#: **not** named ``microbe_relations``: a property under the source's own column
#: name, sitting on a node in a graph that holds zero MiMeDB edges, reads as a
#: degree. The name has to say "MiMeDB's count", so that a query returning 2,537
#: for acetic acid beside zero edges is obviously two different facts rather
#: than a contradiction.
#:
#: An absent value stays empty. Writing ``0`` would assert "MiMeDB relates this
#: compound to no microbe", which is a claim only a filled column makes.
MICROBE_RELATION_COUNT = "mimedb_microbe_relation_count"

#: Why a MiMeDB record is loaded. The whole file is not: 29,295 records of which
#: 12,105 are glycerophospholipids is a lipidomics table, and a metabolite that
#: no edge can ever reach and no query names is an unconnected node.
#:
#: ``observed``
#:     ``detected`` or ``quantified`` is ``1`` — 1,674 and 1,413 records in v2
#:     (711 apiece in v1), the ones measured in a human biospecimen.
#: ``origin-classified``
#:     ``metabolite_type`` is filled — 724 records in v2, ``Co-metabolite``
#:     (668) or ``Primary`` (56). This is MiMeDB's origin axis, the one thing
#:     the research document found it grades on an evidence basis, and it is the
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


def release_of(columns) -> str:
    """``"v2.0"`` if the header carries v2's columns, ``"v1.0"`` otherwise.

    Read off the *header*, never the filename. A filename is an operator's
    claim about a file they downloaded by hand from a site no script can reach;
    the column list is the dump's own statement of what it is. Getting this from
    the path would let a file placed under the wrong name write a false
    ``mimedb_release`` onto every node it loads, and nothing downstream could
    tell.

    **Any** v2-only column is enough, not all of them. The columns are what the
    loader actually reads — an absent one writes an empty property either way —
    so the label answers "which release is this", and a release that dropped one
    of the four would otherwise be reported as the one it is furthest from.

    Both tables' lists are consulted because one function is asked about both
    files and they grew different columns; see :data:`V2_ONLY_MICROBE_COLUMNS`
    and :data:`_RELEASE_MARKERS` for the one name that had to be excluded.
    """
    return "v2.0" if _RELEASE_MARKERS & set(columns or ()) else "v1.0"


def normalise_hmdb_id(raw: str | None) -> str:
    """``HMDB03402`` and ``HMDB0003402`` -> ``HMDB0003402``; anything else -> ``""``.

    HMDB widened its accessions from five digits to seven in 2018 and MiMeDB's
    column holds both spellings — 3,904 filled values in v2, 258 of them legacy.
    A literal string join therefore misses every legacy id, and misses it
    *silently*, which reads as "MiMeDB has no HMDB id for this compound". The
    real ``D-Tyrosine`` record is spelled ``HMDB00158``, so normalising is also
    what exposes it as contesting ``L-Tyrosine``'s accession.
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

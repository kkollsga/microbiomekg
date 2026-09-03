"""HMDB: the metabolite vocabulary, and 578 production claims keyed on free text.

This source adds the ``Metabolite`` node type and the ``PRODUCES``
relationship — D5's "which metabolites does taxon X produce, and is that
measured or predicted?". Two facts shape everything here and both are
measurements, not impressions:

* **88.8% of HMDB is `predicted` or `expected`.** ``status`` is 100% filled and
  is the most load-bearing field the file has: 98,256 expected, 95,355
  predicted, 20,924 detected, 3,385 quantified. Only 24,309 records have ever
  been observed in a human sample, and that is what :func:`evidence_level`
  reads.
* **Microbial origin is 224 metabolites, 0.10% of the file** — and it is the
  *best*-curated slice (158 quantified, 28 detected, 38 expected), the inverse
  of the file as a whole. Anyone who sized this source on "HMDB has microbial
  metabolites" needs that number in front of them before reading further — and
  then one more: **67 of the 224 name no organism at all**, so the production
  edges come from 157 records over 957 organism terms. "224 microbial
  metabolites" and "224 production claims" are different quantities.

Four decisions this module records, because each one is a place where a
plausible-looking alternative would have put wrong rows in the graph.

**The disease layer is not loaded.** ``<diseases>`` carries 27,670 rows, and
**20,020 of them — 72% — name `3-methylglutaconic aciduria type II, X-linked`**.
The next name down is `Colorectal cancer` at 831. That is a curation accident,
not biology: loading it produces one ``Disease`` node with 20,020 metabolite
edges that dominates every path query in the graph, and it would arrive with no
evidence level HMDB can justify (its associations are metabolomic, so Part B
gives them ``unknown``). The rows are counted and reported by the prep and
reach no edge. Note what is *not* being claimed — the other 7,650 rows are
probably fine; they are not loaded because the layer cannot be loaded in part
without inventing a rule for which curation accidents count.

**`PRODUCES` is not an `ASSOCIATED_WITH`.** "This organism makes this molecule"
and "this organism is differentially abundant in this disease" are different
claims, and the fourteen-property evidence contract is shaped for the second:
``direction``, ``sequencing_type`` and the two group sizes have no meaning on a
production claim. Filling them would make the audit's headline number describe
something other than what it says. ``PRODUCES`` therefore carries
:data:`PRODUCTION_CONTRACT` — the subset that *is* applicable — and is audited
against that, which is a rule that can fail because this loader writes every
one of those fields itself.

**A term broader than a family gets no edge.** HMDB's "genus" level is not a
rank: it holds genera, phyla, a class, six families, two Gram stains, a
community (`Human gut microbiota`) and a U+FB01 ligature typo. Resolving those
verbatim is not merely vague, it is wrong — NCBI files the string `Firmicutes`
as a **synonym of 1783272 `Bacillati`, a kingdom**, because of the 2024
nomenclature change, while the phylum a reader means (1239 `Bacillota`) carries
`firmicutes` only as a blast/genbank common name, which
:data:`microbiomekg.reconcile.NAME_CLASSES` deliberately excludes. So a naive
load does not produce a coarse edge, it produces "a kingdom makes butyrate".
:data:`PRODUCTION_RANK_CEILING` cuts at ``family``; everything above it lands in
the ledger *with the id and rank it resolved to*, so the decision is countable
and reversible rather than a silent drop.

**A cross-kingdom homonym is settled by the microbial context, and only when
one candidate survives it.** ``reconcile`` answers ``ambiguous`` for a name
several taxa share and hands back the candidates rather than guessing, because
C2's ``first-wins`` invents facts. HMDB's most common organism term is
`Bacillus` — a bacterial genus *and* a genus of stick insects — and `Proteus`
(a bacterium and an amphibian), `Serratia`, `Rhodococcus`, `Edwardsiella` and
`Paracoccus` are the same shape: 26 organism terms in the real file. The term
was read from ``Disposition/Source/Biological/Microbe``, so a non-microbial
candidate is not merely less likely, it is wrong, and
``scripts/prep_hmdb.py::microbial_candidate`` picks the one candidate under
Bacteria/Archaea/Fungi/Viruses. **Exactly one, never the first** — C3's point is
that a kingdom heuristic cannot separate two *bacteria*, so `Bacteroidetes` and
`Lactobacillus plantarum` stay ambiguous and reach the ledger.
"""

from __future__ import annotations

from .vocabulary import register_source

__all__ = [
    "ASSOCIATION_RELATIONSHIPS",
    "CLASSES",
    "MICROBE_PATH",
    "OBSERVED_STATUSES",
    "PRODUCTION_CONTRACT",
    "PRODUCTION_PROPERTY_TYPES",
    "PRODUCTION_RANK_CEILING",
    "RELATIONSHIPS",
    "SOURCE",
    "SOURCE_ROOT",
    "STATUSES",
    "evidence_level",
]

SOURCE = "hmdb"

#: **The claim a `PRODUCES` edge makes is a curator's, whatever the metabolite's
#: detection status.** HMDB's microbial-origin annotation is an entry in a
#: hand-built ontology tree — a person wrote "this compound comes from
#: *Escherichia coli*" — so the edge is a ``knowledge_assertion`` by a
#: ``manual_agent`` on all 224. What the `status` column changes is
#: :func:`evidence_level`: whether anyone has *measured* the compound. Those are
#: different questions and Part B keeps them in different columns on purpose;
#: collapsing them would make ``knowledge_level = 'prediction'`` mean "nobody
#: has run the assay yet", which is not what Biolink's value says.
#:
#: The licence is the reason KEGG is not the only gated source in spirit: HMDB
#: is free for non-commercial use *with citation* and grants no redistribution,
#: so `source_licence` on every edge is what lets a shippable subgraph be cut
#: later without re-deriving which rows came from where (G3).
register_source(
    SOURCE,
    knowledge_level="knowledge_assertion",
    agent_type="manual_agent",
    licence="HMDB-noncommercial",
)

#: HMDB declares no taxon–condition association. Its disease layer is not loaded
#: (see the module docstring) and ``PRODUCES`` is deliberately outside the
#: fourteen-property contract.
ASSOCIATION_RELATIONSHIPS: tuple[str, ...] = ()

#: The four values of ``<status>``, in the order the file's own counts put them.
#: 100% filled, no other spelling exists.
STATUSES: tuple[str, ...] = ("expected", "predicted", "detected", "quantified")

#: The two statuses that mean somebody ran an assay. The other two are a
#: prediction (95,355) or an expectation (98,256) — 88.8% of the file.
OBSERVED_STATUSES: frozenset[str] = frozenset({"detected", "quantified"})

#: The ontology path prefix that means microbial origin, matched as a **path**
#: and never as a term substring. A substring match on ``microb|bacter|fung``
#: returns 519 metabolites, of which 233 are
#: ``Role/Industrial application/Household products/Antimicrobial agent`` —
#: drugs that *kill* microbes, the exact opposite of the relation being loaded.
MICROBE_PATH: str = "Disposition/Source/Biological/Microbe"

#: The origin branch whose other children (`Food`, `Endogenous`, `Synthetic`,
#: `Environmental`, `Exogenous`) become ``Metabolite.origin`` rather than edges:
#: they name no organism, so there is nothing to point an edge at.
SOURCE_ROOT: str = "Disposition/Source"

#: Broadest NCBI rank a production claim may be made at. See the module
#: docstring: HMDB's organism level mixes ranks, and the resolutions above this
#: ceiling are the ones that are both vague *and*, in the `Firmicutes` case,
#: wrong. Families (`Lachnospiraceae`, `Ruminococcaceae`) are kept — they are
#: real gut clades a reader can act on.
PRODUCTION_RANK_CEILING: str = "family"


def evidence_level(status: str | None) -> str:
    """``evidence_level`` for one production edge, from the metabolite's status.

    ``in-vitro`` where the compound is ``detected`` or ``quantified`` — Part B's
    reading, "HMDB microbial-origin edges whose metabolite is
    detected/quantified" — and ``computational-predicted`` otherwise. There is
    no third outcome: ``status`` is 100% filled with four values, so an unknown
    spelling would be new data, and it takes the conservative branch rather than
    a plausible-looking ``unknown``.
    """
    return (
        "in-vitro"
        if (status or "").strip().casefold() in OBSERVED_STATUSES
        else "computational-predicted"
    )


#: What a ``PRODUCES`` edge must carry. Not :data:`EVIDENCE_CONTRACT`: eight of
#: its fourteen fields describe a differential-abundance observation and would
#: be structurally empty here, which would move the audit's headline percentage
#: without anything having gone wrong. Every field below is one this loader
#: writes itself, so a violation is a bug in the prep and not a gap upstream —
#: which is what makes the rule able to fail.
PRODUCTION_CONTRACT: list[str] = [
    "evidence_level",
    "knowledge_level",
    "agent_type",
    "primary_source",
    "source_record_id",
    "source_licence",
    "source_relation",
    "reported_name",
    "hmdb_status",
]

PRODUCTION_PROPERTY_TYPES: dict[str, str] = {
    "evidence_level": "string",
    "knowledge_level": "string",
    "agent_type": "string",
    "primary_source": "string",
    "source_record_id": "string",
    "source_licence": "string",
    "source_relation": "string",
    "reported_name": "string",
    "reported_rank": "string",
    "original_rank": "string",
    "resolution_status": "string",
    "hmdb_status": "string",
    "microbe_path": "string",
    "publications": "string",
    "n_publications": "integer",
}

CLASSES: dict[str, dict] = {
    "Metabolite": {
        "description": "A small molecule, keyed on its ChEBI CURIE where HMDB "
        "carries a chebi_id and on its HMDB accession otherwise. `status` says "
        "whether anyone has measured it: 88.8% of HMDB is predicted or expected.",
    },
}

RELATIONSHIPS: dict[str, dict] = {
    "PRODUCES": {
        "domain": "Taxon",
        "range": "Metabolite",
        "required_properties": PRODUCTION_CONTRACT,
        "property_types": PRODUCTION_PROPERTY_TYPES,
        # `warn` for the same reason the association contract uses it — the
        # build report is where a completeness number belongs — but unlike that
        # one this rule *should* sit at zero, because every field is written
        # here rather than read from upstream. tests/test_hmdb.py asserts it.
        "enforcement": {"required_properties": "warn", "property_types": "error"},
        "description": "An organism HMDB names as a source of this metabolite. "
        "One edge per (metabolite, organism term); the organism is free text in "
        "the source and carries no taxid, so `reported_name` is what was said "
        "and the edge's endpoint is what it resolved to.",
    },
}

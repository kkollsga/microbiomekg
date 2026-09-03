"""NJC19: the consumption edge D6 was dead without, and 912 explicit negatives.

This source adds ``CONSUMES``, ``DEGRADES`` and ``NO_EXCHANGE_WITH``, and writes
export events into the ``PRODUCES`` table HMDB already owned. It is the only
source in this graph that says an organism *takes a compound up*, and D6 —
Marcelino et al.'s Metabolite Exchange Score, **MES = 2·P·C / (P + C)** — is
identically zero for every metabolite until it lands, because the harmonic mean
of a producer count and a consumer count is zero whenever either is zero.

**The negatives are the second reason to load it, and they get their own edge
type.** 912 of the 9,136 curated rows are marked ``(-)``: the literature says
this organism does *not* import that compound, does not export it, or does not
degrade that macromolecule. Explicit negatives are rare enough in this field
that folding them into a property of the positive edge would make them
invisible to anyone who did not know to look — every ``MATCH
(t)-[:CONSUMES]->(m)`` would silently include the refutations. They are
:data:`NO_EXCHANGE_WITH` instead, which is what Part D's D6 contract proposed,
and ``source_relation`` says which activity was negated
(:data:`NEGATIVE_RELATIONS`). Guard G2's rule applies to them verbatim: a
negative is countable, never dropped.

Four decisions this module records.

**Species-level claims resting on genus-level literature are marked, not
mixed.** NJC19's ``Ref. #`` column carries a ``(G)`` suffix on a reference that
was read at genus level — the table's own header says so — and **2,426 of the
9,136 rows (26.6%) carry nothing but ``(G)``-marked references.** The row is
still filed against a species, so a verbatim load would present a genus-level
observation as a species-level fact, which is exactly what guard G5 exists to
stop. ``genus_level_evidence`` is a boolean on every edge and one ``WHERE``
clause separates the two populations.

**A combined activity is two edges, and its references split with it.** 180
rows read ``Consumption (import), Production (export)``, and every one of them
carries a scoped reference cell — ``import:415, 418;export:417``. Emitting one
edge would lose half the claim; emitting two with the whole cell on both would
attribute the import to the export's paper. :func:`split_references` reads the
scope, so each edge carries the references for *its own* direction.

**The six host cell types are not organisms and are not resolved.** The paper's
own scale line is "838 microbial species **+ 6 host cell types**", and the six
are ``human colonocyte``, ``human goblet cell``, ``human hepatocyte``, ``mouse
goblet cell``, ``mouse hepatocyte`` and ``mouse intestinal cell``. Sending them
through ``reconcile`` produces six ``UnresolvedTaxon`` tombstones that read like
six taxa NCBI has lost, which is a false statement about the taxonomy. They are
:data:`HOST_CELL_TYPES`, excluded by name, counted, and written to the ledger
with that reason.

**A compound name is joined to the graph's own `Metabolite` identity, and the
route is recorded.** NJC19 names compounds in free text with a parenthesised
synonym list and carries no ChEBI, HMDB, KEGG or PubChem id for any of them. The
join is an exact, casefolded name match against the ``Metabolite`` nodes HMDB
and MiMeDB already wrote, tried over :func:`name_variants` — the head name, its
conjugate acid/base spelling, its stereo-prefix-stripped form, then the
synonyms in the order the source lists them. ``metabolite_join`` on every edge
says which of those routes matched, so a conjugate match is countable rather
than assumed.

**And the conjugate fallback is the whole reason acetate has an MES at all.**
HMDB records ``Acetic acid`` (CHEBI:15366) and ``Butyric acid`` (CHEBI:30772);
NJC19 says ``Acetate`` and ``Butyrate``. Without the ``-ate`` ↔ ``-ic acid``
step the consumers land on freshly minted nodes, the producers stay on HMDB's,
and MES is 0 for both halves of every SCFA in the graph — the same trap D5's
"key note" already recorded for CHEBI:17968 vs CHEBI:30772, arriving a second
time from the other side. The fallback is deliberately **one-directional in
precedence, not in effect**: the source's own spelling is tried first, so where
the graph holds *both* protonation states as separate nodes — ``Formate``
(CHEBI:15740) and ``Formic acid`` (CHEBI:30751) — NJC19's edges attach to the
one it actually named and the split survives as two nodes rather than being
silently merged. ``metabolite_join`` = ``exact`` is what says that happened.
"""

from __future__ import annotations

import re

from .vocabulary import (
    EXCHANGE_CONTRACT,
    PRODUCTION_DESCRIPTION,
    exchange_declaration,
    register_source,
)

__all__ = [
    "ASSOCIATION_RELATIONSHIPS",
    "CLASSES",
    "EVIDENCE_LEVEL",
    "EXCHANGE_PROPERTY_TYPES",
    "EXCHANGE_RANK_CEILING",
    "EXCHANGE_RELATIONSHIPS",
    "HOST_CELL_TYPES",
    "NEGATIVE_MARKER",
    "NEGATIVE_RELATIONS",
    "POSITIVE_RELATIONS",
    "RELATIONSHIPS",
    "RELATION_BY_ACTIVITY",
    "SOURCE",
    "activity_relations",
    "name_variants",
    "split_references",
]

SOURCE = "njc19"

#: **Every NJC19 edge is a curator's assertion about an experiment.** The paper
#: is explicit that the curation basis was "experimental evidence of metabolite
#: transport or macromolecule degradation reported in literature", read by hand
#: — "a careful read of hundreds of these sources was done to discern which
#: annotations were experimentally verified". So the pair is the same as HMDB's
#: even though the claim is a different shape.
#:
#: The licence is the one genuinely unrestricted thing in this graph: the Dryad
#: deposit is CC0-1.0, so an NJC19-only subgraph can be redistributed with no
#: condition at all. That is only usable because `source_licence` rides on the
#: edge (G3) rather than on the build.
register_source(
    SOURCE,
    knowledge_level="knowledge_assertion",
    agent_type="manual_agent",
    licence="CC0-1.0",
)

#: NJC19 declares no taxon–condition association: it is a transport network, not
#: a differential-abundance corpus.
ASSOCIATION_RELATIONSHIPS: tuple[str, ...] = ()

#: The one ``evidence_level`` this source emits, and there is no derivation to
#: do. NJC19's inclusion criterion *is* the evidence tier — Part B's ``in-vitro``
#: row names it directly ("NJC19 and MASI experimentally-verified events") — and
#: the file carries no per-row assay, design or host column that could move it.
#: A source with one value is not a source with a missing one; it is stated here
#: rather than defaulted at the write site so a reader can find it.
EVIDENCE_LEVEL: str = "in-vitro"

#: NJC19's ``Metabolic activity`` vocabulary -> the relationship it becomes.
#: Closed: the column holds exactly these three atoms, alone or as the one
#: two-atom combination :func:`activity_relations` splits.
RELATION_BY_ACTIVITY: dict[str, str] = {
    "Consumption (import)": "CONSUMES",
    "Production (export)": "PRODUCES",
    "Macromolecule degradation": "DEGRADES",
}

#: ``source_relation`` for each relationship, positive and negated. A
#: ``NO_EXCHANGE_WITH`` edge is not self-describing without this: the row says
#: which of the three activities the literature refuted, and an edge type shared
#: by all three negatives would otherwise lose it.
NEGATIVE_RELATIONS: dict[str, str] = {
    "CONSUMES": "import-negative",
    "PRODUCES": "export-negative",
    "DEGRADES": "degrade-negative",
}

#: The positive spelling, same shape.
POSITIVE_RELATIONS: dict[str, str] = {
    "CONSUMES": "import",
    "PRODUCES": "export",
    "DEGRADES": "degrade",
}

#: The marker NJC19 puts in ``Metabolic activity`` for a refutation.
NEGATIVE_MARKER: str = "(-)"

#: The six rows of the ``Species`` column that are not species. NJC19's own
#: scale line is "838 microbial species + 6 host cell types"; these are the six,
#: and they are excluded by name rather than left to fail reconciliation, which
#: would file them as six taxa NCBI lost.
HOST_CELL_TYPES: frozenset[str] = frozenset({
    "human colonocyte",
    "human goblet cell",
    "human hepatocyte",
    "mouse goblet cell",
    "mouse hepatocyte",
    "mouse intestinal cell",
})

#: Broadest NCBI rank an exchange claim may be made at. NJC19 files every row
#: against a species and 823 of its 844 organism strings resolve at exactly that
#: rank, so unlike HMDB's mixed-rank organism level this ceiling is a guard
#: against a promotion surprise rather than a working filter.
EXCHANGE_RANK_CEILING: str = "genus"

#: The stereo/configuration prefixes a name may carry that the graph's own
#: ``Metabolite`` names may not. Stripped only as a **later** variant than the
#: verbatim name, so ``D-Arabinose`` never matches ``L-Arabinose`` first.
_STEREO_PREFIX = re.compile(r"^(?:l|d|dl|r|s|\[[rs]\]|\[[rs],[rs]\])-", re.IGNORECASE)

#: ``Compound name (synonym, synonym, ...)`` — NJC19's whole compound grammar.
_SYNONYMS = re.compile(r"^(?P<head>.*?)\s*\((?P<syns>.*)\)\s*$")

#: ``import:415, 418;export:417`` — the scoped reference cell every combined
#: activity row carries, and only they do (180 of 9,136).
_SCOPED_REF = re.compile(r"^(?P<scope>import|export|degradation)\s*:\s*(?P<refs>.*)$")

#: ``217(G)`` — a reference read at genus level.
_GENUS_REF = re.compile(r"\(G\)\s*$")

#: NJC19 reference-scope token -> the relationship it belongs to.
_SCOPE_RELATION: dict[str, str] = {
    "import": "CONSUMES",
    "export": "PRODUCES",
    "degradation": "DEGRADES",
}


def activity_relations(activity: str | None) -> list[tuple[str, bool]]:
    """``(relationship, negated)`` for one ``Metabolic activity`` cell.

    Returns **two** pairs for the 180 rows spelled ``Consumption (import),
    Production (export)``: one row curating both directions is two claims, and
    collapsing it to one would drop whichever half sorted second. Returns an
    empty list for a cell outside the closed vocabulary, so a new spelling in a
    future release is a countable skip rather than a silently mistyped edge.

    The ``(-)`` marker applies to the whole cell — no combined row carries it —
    and is stripped before the atoms are matched.
    """
    cell = (activity or "").strip()
    if not cell:
        return []
    negated = NEGATIVE_MARKER in cell
    cell = cell.replace(NEGATIVE_MARKER, "").strip()
    # Substring containment, not a split on the joining comma, for the reason
    # `split_study_designs` uses the same shape: two of the three atoms *contain*
    # the delimiter's neighbouring punctuation — `Consumption (import)` ends in a
    # bracket and `Macromolecule degradation` does not — so any rule that
    # reconstructs the atoms from the pieces gets one of the two wrong. It was
    # `Macromolecule degradation` that it got wrong, silently, for all 477 of its
    # rows. No key is a substring of another, so containment is unambiguous.
    out: list[tuple[str, bool]] = []
    for atom, rel in RELATION_BY_ACTIVITY.items():
        if atom in cell and (rel, negated) not in out:
            out.append((rel, negated))
    return out


def split_references(cell: str | int | None, relationship: str) -> tuple[list[str], bool]:
    """The reference ids for one relationship, and whether all of them are ``(G)``.

    NJC19's ``Ref. #`` is a comma-joined list of numbers indexing the paper's
    own Online-only Table 2 — **not PMIDs**, which is why this loader mints no
    ``Paper`` node and the ids ride on the edge as ``reference_ids``. A combined
    activity row scopes them per direction (``import:415, 418;export:417``); a
    plain row does not, and every reference in it belongs to its single
    relationship.

    The second element is ``genus_level_evidence``: true when **every**
    surviving reference carries the ``(G)`` suffix, i.e. nothing but genus-level
    literature stands behind a species-filed row. "Any" would have been the
    wrong quantifier — a row with one species-level source is a species-level
    claim with extra context.
    """
    text = str(cell if cell is not None else "").strip()
    if not text:
        return [], False
    scoped: list[str] = []
    if ";" in text or _SCOPED_REF.match(text):
        for part in text.split(";"):
            m = _SCOPED_REF.match(part.strip())
            if m is None:
                continue
            if _SCOPE_RELATION.get(m.group("scope")) == relationship:
                scoped.extend(m.group("refs").split(","))
    else:
        scoped = text.split(",")

    refs = [r.strip() for r in scoped if r.strip()]
    if not refs:
        return [], False
    return refs, all(_GENUS_REF.search(r) is not None for r in refs)


def name_variants(compound: str) -> list[tuple[str, str]]:
    """``(spelling, join route)`` candidates for one NJC19 compound cell, in order.

    The order *is* the policy, and it is the same shape as ``reconcile``'s
    exact-index-before-normalised-index rule: what the source actually wrote is
    tried before anything derived from it, and a synonym is tried after every
    derivation of the head name. Routes, in the order they are produced:

    ``exact``
        the head name verbatim — ``Butyrate``, ``Cholic acid``.
    ``conjugate``
        the head name's other protonation state, ``-ate`` <-> ``-ic acid``.
        This is what reaches HMDB's ``Butyric acid`` from NJC19's ``Butyrate``,
        and without it every short-chain fatty acid in D6 scores MES 0.
    ``stereo`` / ``stereo-conjugate``
        the head name with a leading ``L-``/``D-``/``[R]-``/``[S]-`` removed,
        and that form's conjugate.
    ``synonym``, ``synonym-conjugate``, ``synonym-stereo``
        the same three steps over each parenthesised synonym, in source order.

    Deduplicated by spelling, so a synonym that repeats a derivation keeps the
    earlier — and stronger — route label.
    """
    m = _SYNONYMS.match(compound.strip())
    head = (m.group("head") if m else compound).strip()
    synonyms = [s.strip() for s in m.group("syns").split(",")] if m else []

    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def push(spelling: str, route: str) -> None:
        spelling = spelling.strip()
        if spelling and spelling.casefold() not in seen:
            seen.add(spelling.casefold())
            out.append((spelling, route))

    def expand(base: str, prefix: str) -> None:
        push(base, prefix.rstrip("-") or "exact")
        conjugate = _conjugate(base)
        if conjugate:
            push(conjugate, f"{prefix}conjugate" if prefix else "conjugate")
        bare = _STEREO_PREFIX.sub("", base)
        if bare != base:
            push(bare, f"{prefix}stereo" if prefix else "stereo")
            bare_conjugate = _conjugate(bare)
            if bare_conjugate:
                push(bare_conjugate, f"{prefix}stereo-conjugate" if prefix
                     else "stereo-conjugate")

    expand(head, "")
    for synonym in synonyms:
        expand(synonym, "synonym-")
    return out


def _conjugate(name: str) -> str:
    """``butyrate`` <-> ``butyric acid``: the same compound, two protonation states.

    Naive by design — strip the suffix, append the other — and it is right for
    every SCFA, di- and tricarboxylate this source names, because the
    ``-ate``/``-ic acid`` pair is what IUPAC nomenclature makes it. A wrong
    guess costs nothing: the derived spelling either matches a ``Metabolite``
    name exactly or it does not, and an unmatched variant is skipped.
    """
    low = name.casefold()
    if low.endswith("ate"):
        return name[:-3] + "ic acid"
    if low.endswith("ic acid"):
        return name[:-7] + "ate"
    return ""


#: What an NJC19 exchange edge declares beyond :data:`EXCHANGE_CONTRACT`. The
#: contract's eight are required; these are the ones a query needs and an
#: absent value is a real answer for.
EXCHANGE_PROPERTY_TYPES: dict[str, str] = {
    **{field: "string" for field in EXCHANGE_CONTRACT},
    "reported_rank": "string",
    "original_rank": "string",
    "resolution_status": "string",
    "reported_compound": "string",
    "metabolite_join": "string",
    "genus_level_evidence": "bool",
    "reference_ids": "any",
    "n_references": "integer",
}

#: The three positive relationships plus the negative one, in the order the
#: build report prints them.
EXCHANGE_RELATIONSHIPS: tuple[str, ...] = (
    "PRODUCES",
    "CONSUMES",
    "DEGRADES",
    "NO_EXCHANGE_WITH",
)


#: The columns this source adds to a shared exchange declaration.
_ADDED_PROPERTY_TYPES: dict[str, str] = {
    k: v for k, v in EXCHANGE_PROPERTY_TYPES.items() if k not in EXCHANGE_CONTRACT
}


def _declaration(description: str) -> dict:
    return exchange_declaration(description, _ADDED_PROPERTY_TYPES)


CLASSES: dict[str, dict] = {
    "Metabolite": {
        "description": "A small molecule, keyed on its ChEBI CURIE where HMDB "
        "carries a chebi_id and on its HMDB accession otherwise. `status` says "
        "whether anyone has measured it: 88.8% of HMDB is predicted or expected.",
    },
}

RELATIONSHIPS: dict[str, dict] = {
    # Declared here too, and identically, because this source writes export
    # events into HMDB's table: the fragment that adds rows to a shared
    # relationship declares it, so an njc19-only build still has the rule.
    "PRODUCES": _declaration(PRODUCTION_DESCRIPTION),
    "CONSUMES": _declaration(
        "An organism NJC19 curates as importing this metabolite, from a "
        "literature report of experimentally verified transport. The edge D6's "
        "Metabolite Exchange Score is identically zero without."
    ),
    "DEGRADES": _declaration(
        "An organism NJC19 curates as degrading this macromolecule. Kept apart "
        "from CONSUMES because extracellular breakdown of a polymer and uptake "
        "of a small molecule are different claims about a community's "
        "cross-feeding, and the source separates them."
    ),
    "NO_EXCHANGE_WITH": _declaration(
        "An organism the literature reports as **not** performing an exchange: "
        "912 explicit negatives, which `source_relation` types as "
        "import-negative, export-negative or degrade-negative. Its own "
        "relationship rather than a flag on the positive edge, so no query can "
        "count a refutation as an observation by omission."
    ),
}

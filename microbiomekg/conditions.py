"""The condition column: one MONDO hub, one pairing rule, one ledger.

BugSigDB's column is named ``EFO ID`` and is neither EFO nor, in 40% of its
mentions, a disease. This module is the single place that decides three things
about a condition term, so no prep script has to re-decide them:

1. **Which node type it becomes** — :func:`condition_node_type`, keyed on the
   CURIE prefix, never on the column name (C14).
2. **Which key it gets** — the MONDO CURIE when MONDO declares an equivalence,
   the source CURIE otherwise (`docs/research/existing-graphs-and-schemas.md`
   §5(a): MONDO carries curated 1:1 equivalence axioms, so it is the hub that
   makes an EFO id from one source and a DOID id from another meet).
3. **How its verbatim label pairs with it** — :func:`pair_conditions`, which
   never positionally zips two columns that disagree on length.

Anything this module cannot answer is *reported*, never guessed: an unroutable
vocabulary and an unpairable label both come back as leftovers the caller
writes to ``data/csv/unresolved_conditions.csv``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "CONDITION_TYPES",
    "CURIE_SHAPES",
    "malformed_curie",
    "ConditionPairing",
    "MondoIndex",
    "SYNONYM_SCOPE",
    "condition_node_type",
    "curie_vocabulary",
    "pair_conditions",
    "split_curies",
]

#: CURIE prefix → the node type a term of that vocabulary becomes. A prefix
#: that is not here has **no** node type and goes to the ledger — that is the
#: point, not an omission (C14: ``NCBITAXON:568703`` is *Lacticaseibacillus
#: rhamnosus* GG, a probiotic used as an exposure, and typing it ``:Disease``
#: puts a bacterial strain in the disease list).
#:
#: * ``Disease`` — the disease vocabularies. ``DOID`` carries no BugSigDB term
#:   but is what gutMDisorder ships, and it is the half of the hub with 12,091
#:   MONDO equivalences, so it is declared with the table it belongs to.
#: * ``Phenotype`` — HP. Kept apart from ``Disease`` on the schema survey's
#:   §5(a) recommendation: PrimeKG's collapse of HPO phenotypes into one
#:   disease-ish type is a merge that cannot be undone.
#: * ``Exposure`` — what the subject was exposed to or characterised by, coded
#:   in a chemical (``CHEBI:6801`` Metformin), environmental (``ENVO``),
#:   exposure (``EXO``) or social (``GSSO``) vocabulary.
#:
#: Everything else BugSigDB puts in this column — ``GO`` processes, ``OBA``
#: measurements, ``CL`` cell types, ``PATO`` qualities, ``OBI`` protocols,
#: ``NCIT:C102763`` (a surgical procedure), ``XCO``, ``PO``, ``BTO``, ``MP``,
#: ``IDOMAL``, ``PR`` and ``NCBITAXON`` — is a real curated fact about the
#: experiment that this model has no node type for yet, and it goes to the
#: ledger rather than into a type it does not belong to.
CONDITION_TYPES: dict[str, str] = {
    "MONDO": "Disease",
    "EFO": "Disease",
    "DOID": "Disease",
    "ORPHANET": "Disease",
    "HP": "Phenotype",
    "CHEBI": "Exposure",
    "ENVO": "Exposure",
    "EXO": "Exposure",
    "GSSO": "Exposure",
}

#: Vocabulary → the shape its local id has, for the vocabularies whose shape
#: is documented. A CURIE whose prefix is here and whose id does not match is
#: **malformed at the source** — it is not "not found", and the difference
#: matters: gutMDisorder writes ``DOID:00400085``, which is 8 digits with a
#: leading double zero where DOID ids are 1–7, so no lookup will ever find it
#: and reporting it as an ordinary miss would file a typo as a coverage gap.
#:
#: A prefix that is *not* here is never called malformed. Guessing a shape for
#: a vocabulary nobody has checked would reject real ids, which is the silent
#: drop this module exists to prevent.
CURIE_SHAPES: dict[str, str] = {
    "DOID": r"\d{1,7}",
    "MONDO": r"\d{7}",
    "EFO": r"\d{7}",
    "HP": r"\d{7}",
}

_PREFIX = re.compile(r"^\s*([A-Za-z][A-Za-z0-9.]*)[:_]")
_XREF = re.compile(r"^xref:\s+(\S+)(?:\s+\{(.*)\})?\s*$")
_SYNONYM = re.compile(r'^synonym:\s+"(.*?)"\s+([A-Z]+)\b')
_SOURCE = re.compile(r'source="([^"]+)"')

#: The one xref qualifier that means "the same thing". MONDO also emits
#: ``MONDO:relatedTo`` and ``MONDO:otherHierarchy``; reading those as identity
#: is the false-merge failure the schema survey catalogues (kg-microbe #899).
EQUIVALENT_TO = "MONDO:equivalentTo"

#: The one synonym scope that means "the same disease". MONDO also emits
#: ``BROAD``, ``NARROW`` and ``RELATED``, and reading any of those as identity
#: is the false-merge failure :data:`EQUIVALENT_TO` guards against on the xref
#: side — ``RELATED`` on MONDO:0005130 includes *coeliac sprue, susceptibility
#: to*, which is a different disease.
SYNONYM_SCOPE = "EXACT"


def curie_vocabulary(curie: str) -> str:
    """``MONDO:0005265`` → ``MONDO``. ``ncbitaxon_568703`` → ``NCBITAXON``."""
    m = _PREFIX.match(curie or "")
    return m.group(1).upper() if m else ""


def malformed_curie(curie: str) -> bool:
    """Is this CURIE's local id the wrong shape for its own vocabulary?

    ``True`` only for a vocabulary in :data:`CURIE_SHAPES` whose id does not
    match. Everything else — an unknown prefix, a bare string, a vocabulary
    with no declared shape — is ``False``, because this answers "did the source
    make a typo?", not "can I resolve this?".
    """
    vocab = curie_vocabulary(curie)
    shape = CURIE_SHAPES.get(vocab)
    if shape is None:
        return False
    local = (curie or "").strip()[len(vocab) + 1 :]
    return re.fullmatch(shape, local) is None


def condition_node_type(curie: str) -> str | None:
    """The node type for a condition CURIE, or ``None`` for the ledger."""
    return CONDITION_TYPES.get(curie_vocabulary(curie))


def split_curies(cell: str | None) -> list[str]:
    """Split a multi-valued ontology cell. 329 signatures name two conditions.

    Both ``,`` and ``;`` appear as separators in this column; neither ever
    appears *inside* a CURIE, so unlike the ``Condition`` column next to it
    (see :func:`pair_conditions`) splitting on the delimiter is safe here.
    """
    return [c.strip() for c in re.split(r"[,;]", cell or "") if c.strip()]


def _split_labels(cell: str | None) -> list[str]:
    return [c.strip() for c in (cell or "").split(",") if c.strip()]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


@dataclass(frozen=True)
class ConditionPairing:
    """How one row's condition ids and condition strings lined up.

    Attributes:
        pairs: ``(curie, verbatim condition string)``. The string may be empty
            when the row gave an id and no text.
        unpaired_ids: Ids no condition string could be attached to.
        unpaired_labels: Condition strings no id could be attached to.
        method: Which rule produced ``pairs`` — ``positional``,
            ``label-matched``, ``single-id``, ``unresolved`` or ``empty``.
            Recorded so the ledger can say *why*, and so a query can count how
            much of the graph rests on each rule.
    """

    pairs: list[tuple[str, str]] = field(default_factory=list)
    unpaired_ids: list[str] = field(default_factory=list)
    unpaired_labels: list[str] = field(default_factory=list)
    method: str = "empty"


@dataclass
class MondoIndex:
    """MONDO's labels and its curated cross-ontology equivalences.

    Built from the OBO release with :meth:`from_obo`. Roughly 32k live terms
    and 118k equivalence xrefs — small enough to hold entirely.
    """

    #: live MONDO CURIE → its `name:`
    label: dict[str, str] = field(default_factory=dict)
    #: upper-cased foreign CURIE → the live MONDO CURIE it is equivalent to
    equivalent: dict[str, str] = field(default_factory=dict)
    #: MONDO CURIEs carrying `is_obsolete: true`
    obsolete: frozenset[str] = frozenset()
    #: casefolded `name:` → the live MONDO CURIE. One term per name on the
    #: 2026-09-01 release: MONDO's own labels are unique.
    by_name: dict[str, str] = field(default_factory=dict)
    #: casefolded EXACT synonym → the live MONDO CURIE, **only where exactly
    #: one term claims it**. A string two diseases both call themselves is not
    #: an identifier, and picking one of them would be the merge-on-a-shared-
    #: attribute failure the schema survey catalogues — the same rule
    #: :class:`microbiomekg.drugs.DrugIndex` applies to an ATC code.
    by_exact_synonym: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_obo(cls, path: str | Path) -> "MondoIndex":
        """Read labels and ``MONDO:equivalentTo`` xrefs out of ``mondo.obo``.

        Obsolete terms are indexed as obsolete and contribute neither a label
        nor an equivalence: an obsolete term's ``name:`` literally starts with
        the word "obsolete", so keying a Disease node on one produces a node
        called *obsolete sickle cell disease…*.

        The ``name:`` and ``EXACT`` synonym strings are indexed too, for the one
        case a CURIE-keyed hub cannot serve: a source that ships **no condition
        identifier at all**. MASI's disease export is 56 labels and nothing
        else, and :meth:`mondo_by_name` is the only route it has. That is a name
        match, which this project distrusts on principle (C1) — the difference
        is that the far side is a curated ontology's own label rather than
        another source's free text, and that the route is recorded on the node
        so it stays countable and reversible.
        """
        idx = cls()
        dead: set[str] = set()
        term_id = name = None
        is_obsolete = False
        xrefs: list[tuple[str, str]] = []
        synonyms: list[str] = []
        claimed: dict[str, set[str]] = {}
        in_term = False

        def flush() -> None:
            nonlocal term_id, name, is_obsolete, xrefs, synonyms
            if term_id and term_id.startswith("MONDO:"):
                if is_obsolete:
                    dead.add(term_id)
                else:
                    if name:
                        idx.label[term_id] = name
                        idx.by_name.setdefault(name.strip().casefold(), term_id)
                    for text in synonyms:
                        claimed.setdefault(text.strip().casefold(), set()).add(term_id)
                    for target, attrs in xrefs:
                        if EQUIVALENT_TO in _SOURCE.findall(attrs):
                            # First writer wins: a foreign id claimed by two
                            # MONDO terms is a MONDO defect, and picking the
                            # later one silently would be a coin flip.
                            idx.equivalent.setdefault(target.upper(), term_id)
            term_id = name = None
            is_obsolete = False
            xrefs = []
            synonyms = []

        with Path(path).open(encoding="utf-8") as fh:
            for raw in fh:
                line = raw.rstrip("\n")
                if line.startswith("["):
                    flush()
                    in_term = line.strip() == "[Term]"
                    continue
                if not in_term:
                    continue
                if line.startswith("id: "):
                    term_id = line[4:].strip()
                elif line.startswith("name: "):
                    name = line[6:].strip()
                elif line.strip() == "is_obsolete: true":
                    is_obsolete = True
                else:
                    m = _XREF.match(line)
                    if m:
                        xrefs.append((m.group(1), m.group(2) or ""))
                        continue
                    m = _SYNONYM.match(line)
                    if m and m.group(2) == SYNONYM_SCOPE:
                        synonyms.append(m.group(1))
        flush()
        idx.obsolete = frozenset(dead)
        # A synonym only becomes a key while exactly one live term claims it,
        # and a synonym that is some other term's own `name:` is not a key at
        # all — the label always wins, so `mondo_by_name` never answers a
        # question one term has already answered exactly.
        idx.by_exact_synonym = {
            text: next(iter(ids))
            for text, ids in claimed.items()
            if len(ids) == 1 and text not in idx.by_name
        }
        return idx

    def mondo_id(self, curie: str) -> str | None:
        """The live MONDO CURIE this term is equivalent to, or ``None``.

        A live MONDO id is its own hub key. Anything else has to be *declared*
        equivalent — a ``source="EFO:…"`` attribute on some other xref is
        provenance for that xref, not an equivalence to the EFO term, and
        reading it as one produces false merges (see the module tests).
        """
        key = (curie or "").strip().upper().replace("_", ":")
        if key in self.label:
            return key
        if key.startswith("MONDO:"):
            return None  # unknown or obsolete MONDO id: not a live key
        return self.equivalent.get(key)

    def label_for(self, curie: str) -> str | None:
        """MONDO's own name for this term, reached through equivalence."""
        hub = self.mondo_id(curie)
        return self.label.get(hub) if hub else None

    def mondo_by_name(self, label: str | None) -> tuple[str | None, str]:
        """``(live MONDO CURIE or None, the route)`` for a disease **name**.

        For a source that ships a disease label and no identifier. Two routes,
        label first:

        * ``mondo-name`` — the string is some live term's own ``name:``;
        * ``mondo-exact-synonym`` — the string is an ``EXACT`` synonym of
          exactly one live term, and is not any term's ``name:``.

        ``(None, "unmatched")`` otherwise, which is the answer for a
        misspelling (*Rheumatoid arthrits*), a label MONDO spells only as a
        ``RELATED`` synonym (*coeliac disease*) and a phrase that is not a
        disease term at all (*Skin and mucosal infections*). The caller keys
        the node on the source's own id and reports the miss; it does not
        widen the match.

        The caller is expected to pass an already-normalised string — the
        source decides what its own labels need stripping — and this method
        casefolds and nothing more.
        """
        key = (label or "").strip().casefold()
        if not key:
            return None, "unmatched"
        if key in self.by_name:
            return self.by_name[key], "mondo-name"
        if key in self.by_exact_synonym:
            return self.by_exact_synonym[key], "mondo-exact-synonym"
        return None, "unmatched"


def pair_conditions(
    ids: list[str], condition_cell: str | None, index: MondoIndex
) -> ConditionPairing:
    """Attach each condition id to the condition string that belongs to it.

    Both columns are comma-joined, and — exactly like ``Study design`` (C11) —
    one of the *values* contains a comma: ``Helminthiasis, animal``,
    ``Osteoarthritis, knee``, ``Hypertension, pregnancy-induced``. All 42 rows
    of the real dump whose two columns disagree on comma count are that shape.
    A positional zip on those rows is provably wrong, and the same id pair has
    been seen under two label orders (``MONDO:0024647,MONDO:0008171`` with
    ``Nephrolithiasis,Urolithiasis`` on one row and the reverse on another), so
    the zip is not merely incomplete — it is contradictory.

    Three rules, in order, and no fourth:

    1. **Equal counts** → pair positionally. Nothing is in doubt.
    2. **Label match** → look each id's label up in MONDO and consume the
       contiguous run of fragments whose ``", "``-join equals it. That is what
       reassembles ``Helminthiasis`` + ``animal``.
    3. **A single id** → the whole cell verbatim is its condition string. With
       one id there is no pairing decision to get wrong; this is an identity,
       not a guess.

    Whatever is left over is returned as leftovers for the ledger.
    """
    labels = _split_labels(condition_cell)
    if not ids and not labels:
        return ConditionPairing()
    if not ids:
        return ConditionPairing(unpaired_labels=labels, method="unresolved")
    if not labels:
        return ConditionPairing(pairs=[(i, "") for i in ids], method="positional")
    if len(ids) == len(labels):
        return ConditionPairing(pairs=list(zip(ids, labels)), method="positional")

    used = [False] * len(labels)
    pairs: list[tuple[str, str]] = []
    left: list[str] = []
    for curie in ids:
        target = index.label_for(curie)
        run = _find_run(labels, used, target) if target else None
        if run is None:
            left.append(curie)
            continue
        start, end = run
        for k in range(start, end):
            used[k] = True
        pairs.append((curie, ", ".join(labels[start:end])))

    spare = [text for text, taken in zip(labels, used) if not taken]
    if len(left) == 1 and len(pairs) == 0:
        # Rule 3. Only when the id is the row's *only* id: with two unpaired
        # ids there is a real choice to make and this module does not have the
        # information to make it.
        return ConditionPairing(
            pairs=[(left[0], (condition_cell or "").strip())], method="single-id"
        )
    method = "label-matched" if pairs else "unresolved"
    return ConditionPairing(
        pairs=pairs, unpaired_ids=left, unpaired_labels=spare, method=method
    )


def _find_run(
    labels: list[str], used: list[bool], target: str
) -> tuple[int, int] | None:
    """Leftmost unconsumed run of fragments whose join equals ``target``."""
    want = _norm(target)
    for start in range(len(labels)):
        if used[start]:
            continue
        for end in range(start + 1, len(labels) + 1):
            if used[end - 1]:
                break
            if _norm(", ".join(labels[start:end])) == want:
                return start, end
    return None

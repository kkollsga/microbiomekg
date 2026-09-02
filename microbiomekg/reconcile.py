"""NCBI taxonomy reconciliation: raw names and ids in, a canonical tax_id out.

Every source in this project names organisms differently — BugSigDB carries
NCBI ids, Disbiome and CARD carry free text, and all of them are older than the
current taxdump. This module is the single place that turns any of those into
the canonical key the graph uses (``Taxon.id`` = NCBI tax_id, integer), and
records *how* it got there so a caller can keep the failures instead of
dropping them.

Nothing here raises on bad input. A name that cannot be resolved comes back as
a :class:`Resolution` with ``tax_id=None`` and a status saying why, which is
what the prep scripts write to ``data/csv/unresolved_taxa.csv``.

Input files are the NCBI ``new_taxdump`` ``.dmp`` format: fields separated by
``"\\t|\\t"``, every line ending in ``"\\t|"``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

__all__ = [
    "Resolution",
    "TaxonomyIndex",
    "NAME_CLASSES",
    "RANK_LADDER",
    "rank_depth",
    "strip_authority",
]

#: Name classes from ``names.dmp`` that may be used to look a taxon up.
#: ``authority`` (the full "Genus species (Author 1895)" citation) and
#: ``in-part`` are deliberately excluded: the first never appears in a source
#: we read, and the second is explicitly *not* a name for the taxon it is
#: filed under.
NAME_CLASSES: frozenset[str] = frozenset(
    {
        "scientific name",
        "synonym",
        "equivalent name",
        "genbank synonym",
        "includes",
    }
)

#: NCBI rank vocabulary ordered broad → specific. Only the relative order
#: matters; ranks absent from this ladder (``no rank``, ``clade``) are
#: *unplaced* and handled by walking to the nearest placed ancestor.
RANK_LADDER: tuple[str, ...] = (
    "acellular root",
    "cellular root",
    "realm",
    "subrealm",
    "domain",
    "superkingdom",
    "kingdom",
    "subkingdom",
    "superphylum",
    "phylum",
    "subphylum",
    "superclass",
    "class",
    "subclass",
    "infraclass",
    "cohort",
    "subcohort",
    "superorder",
    "order",
    "suborder",
    "infraorder",
    "parvorder",
    "superfamily",
    "family",
    "subfamily",
    "tribe",
    "subtribe",
    "genus",
    "subgenus",
    "section",
    "subsection",
    "series",
    "subseries",
    "species group",
    "species subgroup",
    "species",
    "forma specialis",
    "subspecies",
    "varietas",
    "subvariety",
    "forma",
    "serogroup",
    "serotype",
    "biotype",
    "genotype",
    "morph",
    "pathogroup",
    "strain",
    "isolate",
)

_RANK_DEPTH: dict[str, int] = {r: i for i, r in enumerate(RANK_LADDER)}


def rank_depth(rank: str | None) -> int | None:
    """Position of ``rank`` on :data:`RANK_LADDER`, or ``None`` if unplaced."""
    if rank is None:
        return None
    return _RANK_DEPTH.get(rank.strip().lower())


_QUOTED_HEAD = re.compile(r'^"([^"]+)"')
_YEAR = re.compile(r"\b(?:1[6-9]\d{2}|20\d{2})\b")
_AUTHOR_TAIL = frozenset({"et", "al.", "al", "and", "&", "ex", "emend.", "corrig."})


def strip_authority(name: str) -> str:
    """Reduce an authority-decorated NCBI name to its bare taxonomic name.

    NCBI keeps some legacy binomials **only** in decorated form. The single
    most-cited renamed organism in microbiome research is one of them::

        1496 | Clostridioides difficile                        | scientific name
        1496 | Clostridium difficile (Hall and O'Toole 1935)
               Prevot 1938 (Approved Lists 1980)               | synonym

    There is no bare ``Clostridium difficile`` row anywhere in ``names.dmp``, so
    a literal lookup of the name every paper actually prints returns nothing.
    Same for *Lactobacillus plantarum*, *Lactobacillus reuteri* and *Eubacterium
    rectale*.

    The rule is deliberately narrow, because the failure mode of a greedy
    normaliser is a **wrong** id rather than none:

    * a fully quoted head is the name (``"Peptoclostridium difficile" Yutin
      and Galperin 2013``);
    * otherwise cut at the first ``(`` or the first four-digit year, whichever
      comes first, then drop trailing author tokens down to at most two words;
    * **a string with neither a parenthesis nor a year is returned unchanged.**
      That is what keeps ``Escherichia coli K-12`` from collapsing onto
      ``Escherichia coli``, and it leaves bracket and ``Candidatus`` markers
      (``[Clostridium] symbiosum``) alone — those are part of the scientific
      name, not decoration.
    """
    s = name.strip()
    m = _QUOTED_HEAD.match(s)
    if m:
        return m.group(1).strip()

    paren = s.find("(")
    year = _YEAR.search(s)
    cut = paren if paren != -1 else None
    if year is not None and (cut is None or year.start() < cut):
        cut = year.start()
    if cut is None:
        return s

    tokens = s[:cut].split()
    while len(tokens) > 2 and (
        tokens[-1].lower() in _AUTHOR_TAIL or tokens[-1][:1].isupper()
    ):
        tokens.pop()
    return " ".join(tokens)


@dataclass(frozen=True)
class Resolution:
    """The outcome of one reconciliation attempt.

    ``tax_id`` is the canonical NCBI id to key on, and is ``None`` for every
    status that did not produce one (``ambiguous``, ``deleted``,
    ``unresolved``) — a caller can branch on ``tax_id is None`` alone.

    Attributes:
        tax_id: Canonical id after ``merged.dmp`` remap and rank promotion.
        status: One of ``exact``, ``synonym``, ``merged``, ``promoted``,
            ``ambiguous``, ``deleted``, ``unresolved``.
        matched_name: The ``names.dmp`` string that matched, when a name
            lookup was performed.
        original_tax_id: The id as the source gave it (or as the name first
            resolved to), before remapping and promotion.
        original_rank: The rank of ``original_tax_id`` in the taxdump.
        candidates: Every id a name matched. Non-empty only for ``ambiguous``.
        note: Human-readable trace, for the unresolved-taxa report.
    """

    tax_id: int | None
    status: str
    matched_name: str | None = None
    original_tax_id: int | None = None
    original_rank: str | None = None
    candidates: tuple[int, ...] = ()
    note: str = ""


def _dmp_rows(path: Path) -> Iterator[list[str]]:
    """Yield the fields of each line of an NCBI ``.dmp`` file."""
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n").rstrip("\r")
            if not line:
                continue
            if line.endswith("\t|"):
                line = line[:-2]
            yield [f.strip() for f in line.split("\t|\t")]


@dataclass
class TaxonomyIndex:
    """In-memory index over an NCBI taxdump directory.

    Built with :meth:`from_taxdump`. Holds roughly 3M parent pointers, 3M
    ranks and 4.7M name keys for the full dump — about 1.5 GB of Python
    objects, which is why the prep scripts build it once and stream past it.
    """

    parent: dict[int, int] = field(default_factory=dict)
    rank: dict[int, str] = field(default_factory=dict)
    scientific_name: dict[int, str] = field(default_factory=dict)
    #: casefolded name → {tax_id: the name string as spelled in names.dmp}
    names: dict[str, dict[int, str]] = field(default_factory=dict)
    #: casefolded :func:`strip_authority` form → {tax_id: the decorated spelling}.
    #: Consulted only when `names` misses, so an exact hit always wins.
    stripped: dict[str, dict[int, str]] = field(default_factory=dict)
    merged: dict[int, int] = field(default_factory=dict)
    deleted: frozenset[int] = frozenset()

    # ---------------------------------------------------------------- build

    @classmethod
    def from_taxdump(cls, dir: Path) -> "TaxonomyIndex":
        """Read ``nodes.dmp``/``names.dmp``/``merged.dmp``/``delnodes.dmp``.

        ``nodes.dmp`` and ``names.dmp`` are required. ``merged.dmp`` and
        ``delnodes.dmp`` are optional so a small hand-written fixture can omit
        them; a missing one means "nothing merged" / "nothing deleted", never
        an error.
        """
        d = Path(dir)
        idx = cls()

        nodes = d / "nodes.dmp"
        if not nodes.is_file():
            raise FileNotFoundError(f"nodes.dmp not found under {d}")
        for row in _dmp_rows(nodes):
            if len(row) < 3:
                continue
            try:
                tid, pid = int(row[0]), int(row[1])
            except ValueError:
                continue
            idx.parent[tid] = pid
            idx.rank[tid] = row[2]

        names = d / "names.dmp"
        if not names.is_file():
            raise FileNotFoundError(f"names.dmp not found under {d}")
        for row in _dmp_rows(names):
            if len(row) < 4:
                continue
            try:
                tid = int(row[0])
            except ValueError:
                continue
            text, name_class = row[1], row[3]
            if name_class == "scientific name":
                idx.scientific_name[tid] = text
            if name_class not in NAME_CLASSES:
                continue
            key = text.casefold()
            if not key:
                continue
            idx.names.setdefault(key, {}).setdefault(tid, text)
            bare = strip_authority(text).casefold()
            if bare and bare != key:
                idx.stripped.setdefault(bare, {}).setdefault(tid, text)

        merged = d / "merged.dmp"
        if merged.is_file():
            for row in _dmp_rows(merged):
                if len(row) < 2:
                    continue
                try:
                    idx.merged[int(row[0])] = int(row[1])
                except ValueError:
                    continue

        delnodes = d / "delnodes.dmp"
        if delnodes.is_file():
            dead: set[int] = set()
            for row in _dmp_rows(delnodes):
                if not row or not row[0]:
                    continue
                try:
                    dead.add(int(row[0]))
                except ValueError:
                    continue
            idx.deleted = frozenset(dead)

        return idx

    # ------------------------------------------------------------ traversal

    def lineage(self, tax_id: int) -> list[int]:
        """``tax_id`` then each ancestor up to (and including) the root."""
        out: list[int] = []
        seen: set[int] = set()
        cur = tax_id
        while cur in self.parent and cur not in seen:
            out.append(cur)
            seen.add(cur)
            nxt = self.parent[cur]
            if nxt == cur:  # root(1) is its own parent
                break
            cur = nxt
        return out

    def _promote(self, tax_id: int, ceiling: str) -> tuple[int, bool, str]:
        """Walk ``tax_id`` up to the nearest ancestor at or above ``ceiling``.

        Returns ``(id, promoted, note)``. A taxon already at or above the
        ceiling is returned unchanged, as is an *unplaced* taxon (``no rank``,
        ``clade``) whose nearest placed ancestor is itself above the ceiling —
        that shape is an intermediate group like "Enterobacteriaceae incertae
        sedis", not a strain, and collapsing it to its family would lose a
        real node.
        """
        ceil = rank_depth(ceiling)
        if ceil is None:
            return tax_id, False, f"unknown rank_ceiling {ceiling!r}; no promotion"

        own = rank_depth(self.rank.get(tax_id))
        if own is not None and own <= ceil:
            return tax_id, False, ""

        if own is None:
            # Unplaced. Only below-ceiling if the nearest placed ancestor is.
            nearest = next(
                (
                    d
                    for a in self.lineage(tax_id)[1:]
                    if (d := rank_depth(self.rank.get(a))) is not None
                ),
                None,
            )
            if nearest is None or nearest < ceil:
                return tax_id, False, ""

        for anc in self.lineage(tax_id)[1:]:
            d = rank_depth(self.rank.get(anc))
            if d is not None and d <= ceil:
                return (
                    anc,
                    True,
                    f"promoted from {tax_id} ({self.rank.get(tax_id, '?')}) "
                    f"to {anc} ({self.rank.get(anc, '?')})",
                )
        return tax_id, False, f"no ancestor at or above {ceiling!r}; kept as given"

    # -------------------------------------------------------------- resolve

    def resolve(
        self,
        name: str | None = None,
        *,
        tax_id: int | None = None,
        rank_ceiling: str = "species",
    ) -> Resolution:
        """Reconcile a name and/or an id to a canonical NCBI tax_id.

        An explicit ``tax_id`` wins over ``name``: a source that carries both
        is trusted for the id, and the name is only used when the id is absent.

        Name lookup is case-insensitive over :data:`NAME_CLASSES`. A name
        matching more than one taxon is ``ambiguous`` and returns no id — the
        candidates are reported so a caller can disambiguate with context it
        has and this module does not.
        """
        if tax_id is not None:
            return self._resolve_id(tax_id, rank_ceiling, matched_name=None)

        if name is None:
            return Resolution(None, "unresolved", note="neither name nor tax_id given")

        key = name.strip().casefold()
        if not key:
            return Resolution(None, "unresolved", matched_name=name, note="empty name")

        # Exact index first, always: a name that is spelled in names.dmp must
        # never be answered by the normalised index, which is looser and can
        # collide (`Escherichia coli K-12` is its own taxon, not a decoration
        # of `Escherichia coli`).
        hits = self.names.get(key)
        normalised = False
        if not hits:
            hits = self.stripped.get(strip_authority(name).casefold())
            normalised = hits is not None
        if not hits:
            return Resolution(
                None, "unresolved", matched_name=name, note="no name match in names.dmp"
            )
        if len(hits) > 1:
            return Resolution(
                None,
                "ambiguous",
                matched_name=name,
                candidates=tuple(sorted(hits)),
                note=(
                    f"{len(hits)} taxa share this name"
                    + (" after authority stripping" if normalised else "")
                ),
            )

        found_id, spelled = next(iter(hits.items()))
        base = self._resolve_id(found_id, rank_ceiling, matched_name=spelled)
        notes = [n for n in (base.note,) if n]
        if normalised:
            notes.insert(0, f"matched {spelled!r} after authority stripping")
        if base.status == "exact" and self.scientific_name.get(found_id) != spelled:
            notes.append(f"matched non-scientific name of {found_id}")
            return Resolution(
                base.tax_id,
                "synonym",
                matched_name=spelled,
                original_tax_id=base.original_tax_id,
                original_rank=base.original_rank,
                note="; ".join(notes),
            )
        if normalised:
            return Resolution(
                base.tax_id,
                base.status,
                matched_name=spelled,
                original_tax_id=base.original_tax_id,
                original_rank=base.original_rank,
                candidates=base.candidates,
                note="; ".join(notes),
            )
        return base

    def _resolve_id(
        self, tax_id: int, rank_ceiling: str, matched_name: str | None
    ) -> Resolution:
        original_rank = self.rank.get(tax_id)
        notes: list[str] = []

        current = tax_id
        was_merged = False
        seen: set[int] = set()
        while current in self.merged and current not in seen:
            seen.add(current)
            nxt = self.merged[current]
            notes.append(f"merged {current} -> {nxt}")
            current, was_merged = nxt, True

        if current in self.deleted:
            return Resolution(
                None,
                "deleted",
                matched_name=matched_name,
                original_tax_id=tax_id,
                original_rank=original_rank,
                note="; ".join(notes + [f"{current} listed in delnodes.dmp"]),
            )

        if current not in self.parent:
            return Resolution(
                None,
                "unresolved",
                matched_name=matched_name,
                original_tax_id=tax_id,
                original_rank=original_rank,
                note="; ".join(notes + [f"{current} not present in nodes.dmp"]),
            )

        promoted_id, promoted, pnote = self._promote(current, rank_ceiling)
        if pnote:
            notes.append(pnote)

        status = "promoted" if promoted else ("merged" if was_merged else "exact")
        return Resolution(
            promoted_id,
            status,
            matched_name=matched_name or self.scientific_name.get(promoted_id),
            original_tax_id=tax_id,
            original_rank=original_rank,
            note="; ".join(notes),
        )

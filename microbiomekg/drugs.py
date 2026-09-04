"""Reaching an existing ``Drug`` node from a screen's own spelling of a compound.

Two published drug screens now write into the ``drug.csv`` ChEMBL owns, and both
ask it the same question: *this catalogue calls the compound* ``Ampicillin
sodium`` *— which node is that?* Maier 2018 answered it with three routes tried
verbatim-first; Zimmermann 2019 needs the same machinery over a different set of
columns. The parts that are **not** specific to either — what a level-5 ATC code
is, which suffixes are counter-ions rather than the drug's name, how a
``drug.csv`` becomes two lookup indexes, and what happens when two routes reach
two different nodes — live here so that neither source owns them and a third
does not copy them.

What stays with the source is the **order the routes are tried in**, because
that order is a claim about which of its columns is the most trustworthy
spelling, and the two files do not agree: Maier has a catalogue name and an ATC
column, Zimmermann has a screened-compound name and a parent-drug name and no
ATC at all. Each source therefore builds its own ``(kind, key, route)`` list and
hands it to :func:`join_drug`.

**The index is over whatever ``drug.csv`` holds when the source runs**, not over
ChEMBL alone, and that is the point of the prep-order dependency. Maier mints a
node for every library entry no ChEMBL route reaches; a later screen that
rebuilt its own node for the same compound would split one drug in two and make
"does this drug inhibit gut bacteria *or* get metabolised by them" unanswerable
for it — the exact question D8 asks. So a source declares the sources it must
run after in its ``DEPENDS_ON``, and this index sees their rows.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from .tables import from_list

__all__ = ["DrugIndex", "atc_level5", "join_drug", "strip_salt"]

#: A level-5 ATC code — seven characters, ``A10BA02``: the level that names one
#: substance. Level 4 (``L01BB``) names a *class* and joining on it would put
#: every drug in the class on one node, so only the seven-character form is a
#: join key. The ``Q`` prefix of a veterinary code makes it eight, and ChEMBL
#: does not carry those.
_ATC5 = re.compile(r"^[A-Z]\d{2}[A-Z]{2}\d{2}$")

#: The salt and hydrate suffixes a drug catalogue appends to a parent drug's
#: name. ChEMBL keys ``Drug`` on the parent molecule for exactly this reason
#: (docs/model.md §ChEMBL: "metformin and metformin hydrochloride are two nodes
#: with half the mechanisms each and nothing says so"), so stripping one moves
#: *towards* this graph's own identity rather than away from it — which is why
#: this route exists at all and why every source tries it **last**, after
#: whatever the source itself wrote.
_SALT_SUFFIX = re.compile(
    r"\s+(?:"
    r"hydrochlorides?|dihydrochloride|hydrobromide|hydroiodide|"
    r"sodium|potassium|calcium|magnesium|lithium|ammonium|"
    r"maleate|mesilate|mesylate|besylate|tosylate|napsylate|"
    r"sulfate|sulphate|bisulfate|succinate|tartrate|bitartrate|citrate|"
    r"acetate|phosphate|diphosphate|nitrate|fumarate|oxalate|lactate|"
    r"malate|gluconate|pamoate|embonate|stearate|palmitate|mucate|"
    r"chloride|bromide|iodide|"
    r"salt|"
    r"dihydrate|trihydrate|monohydrate|hemihydrate|hydrate"
    r")\b.*$",
    re.IGNORECASE,
)


def atc_level5(cell: str | None) -> list[str]:
    """Every level-5 ATC code in a free-text ``ATC codes`` cell.

    Two shapes reach here and both have to work. A screen's own spreadsheet
    cell is space-joined free text mixing levels — ``QJ01GB90 QJ51GB90
    QA07AA92``, ``C01EA01 G04BE01``, ``L01BB``, ``-``. ``drug.csv``'s
    ``atc_codes`` is a JSON array, because the column is a `"list"` property in
    the blueprint; reading it with the free-text splitter alone returns
    ``["C01EA01"`` and silently joins nothing.

    Only the seven-character human codes survive, in source order and
    deduplicated — a level-4 code names a class rather than a substance, and a
    veterinary ``Q`` code is eight characters and has no ChEMBL counterpart.
    """
    out: list[str] = []
    for value in from_list(cell):
        for token in re.split(r"[\s|,;]+", value.strip()):
            code = token.strip().upper()
            if _ATC5.match(code) and code not in out:
                out.append(code)
    return out


def strip_salt(name: str) -> str:
    """``Cetirizine dihydrochloride`` -> ``Cetirizine``; unchanged if no suffix.

    Deliberately naive, and it costs nothing when it is wrong: the derived
    spelling either names a ``pref_name`` exactly or it does not, and an
    unmatched variant is skipped. It is the last route every source tries, so it
    can never displace a match on what the source actually wrote.
    """
    return _SALT_SUFFIX.sub("", (name or "").strip()).strip()


class DrugIndex:
    """The two lookups a screen joins its compounds against, over one ``drug.csv``.

    :attr:`names` is casefolded ``pref_name`` -> ``drug_id`` and :attr:`atc` is
    level-5 ATC code -> ``drug_id``; :attr:`source_of` says which source wrote
    the row a join landed on, which is how a screen can report *how many of its
    compounds only have a node because the previous screen minted one*.

    **An identifier claimed by more than one node is dropped rather than
    resolved.** A code is only a join key while it names one substance, and
    picking one of two would be the merge-on-a-shared-attribute failure the
    schema survey catalogues. A *name* collision cannot arise — ``drug.csv`` is
    keyed on ``drug_id`` and the first row per key wins — so ``pref_name`` keeps
    first-seen order, and the rule bites on ATC codes only.
    """

    def __init__(
        self,
        names: dict[str, str],
        atc: dict[str, str],
        source_of: dict[str, str],
    ):
        self.names = names
        self.atc = atc
        self.source_of = source_of

    @classmethod
    def from_rows(
        cls, rows: list[dict[str, str]], *, exclude_source: str
    ) -> "DrugIndex":
        """Index the ``drug`` table's rows, skipping the rows ``exclude_source``
        wrote.

        The exclusion is not an optimisation. ``microbiomekg.tables.Table``
        given ``owner=("source", <this source>)`` drops and rewrites this
        source's rows, so a second run that indexed them would join a compound
        to a node it is about to delete — and the join route would silently
        change between the first run and every one after it.

        An empty table is an empty index, not an error: a prep run on its own,
        before the source it depends on, must mint rather than crash.
        """
        names: dict[str, str] = {}
        atc: dict[str, list[str]] = {}
        source_of: dict[str, str] = {}
        for row in rows:
            drug_id = row.get("drug_id") or ""
            source = row.get("source") or ""
            if not drug_id or source == exclude_source:
                continue
            source_of.setdefault(drug_id, source)
            name = (row.get("pref_name") or "").strip().casefold()
            if name:
                names.setdefault(name, drug_id)
            for code in atc_level5(row.get("atc_codes")):
                atc.setdefault(code, []).append(drug_id)
        return cls(
            names,
            {c: ids[0] for c, ids in atc.items() if len(set(ids)) == 1},
            source_of,
        )

    @classmethod
    def from_csv(cls, path: Path, *, exclude_source: str) -> "DrugIndex":
        """:meth:`from_rows` over a ``drug.csv``; a missing file is empty."""
        if not path.is_file():
            return cls({}, {}, {})
        with path.open(encoding="utf-8", newline="") as fh:
            return cls.from_rows(
                list(csv.DictReader(fh)), exclude_source=exclude_source
            )

    def without_atc(self, codes: object) -> "DrugIndex":
        """The same index with ``codes`` removed from the ATC lookup.

        A source drops a code its *own* catalogue gives to two entries — the
        uniqueness rule of :meth:`from_csv` applied from the other side. The
        names lookup is untouched, so a dropped code falls through to the next
        route rather than losing the compound.
        """
        return DrugIndex(
            self.names,
            {c: d for c, d in self.atc.items() if c not in codes},
            self.source_of,
        )

    def lookup(self, kind: str, key: str) -> str | None:
        """The ``drug_id`` one ``(kind, key)`` attempt reaches, or ``None``.

        ``kind`` is ``"name"`` or ``"atc"``. Names are matched casefolded; ATC
        codes are matched as written, because :func:`atc_level5` has already
        upper-cased everything it lets through.
        """
        if kind == "name":
            return self.names.get(key.strip().casefold())
        if kind == "atc":
            return self.atc.get(key.strip().upper())
        raise ValueError(f"unknown join kind {kind!r} (expected 'name' or 'atc')")


def join_drug(
    variants: list[tuple[str, str, str]], index: DrugIndex
) -> tuple[str, str, list[str]]:
    """``(drug_id or "", join route, every other node the routes reached)``.

    ``variants`` is the source's own ``(kind, key, route)`` list, in the order it
    trusts them — that order *is* the policy, and it belongs to the source.

    The first route that names a node wins. The third element is what the
    *losing* routes reached, which is only ever non-empty when two routes
    disagree; the caller ledgers those rather than letting the precedence hide
    them. On both screens loaded here every disagreement is the same one — the
    verbatim name reaches a ChEMBL *salt* node while a derived or parent
    spelling reaches the parent molecule — which is ChEMBL's documented parent
    gap showing through and not a defect in the join.

    ``"minted"`` is the route when nothing matched, so the counter the prep
    prints sums to the number of compounds rather than to the number that
    joined.
    """
    found: list[tuple[str, str]] = []
    for kind, key, route in variants:
        hit = index.lookup(kind, key)
        if hit is not None and hit not in [d for d, _ in found]:
            found.append((hit, route))
    if not found:
        return "", "minted", []
    winner, route = found[0]
    return winner, route, [d for d, _ in found[1:]]

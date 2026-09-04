"""The flat tables the blueprint loads, held in memory, and how two sources
share one.

Every prep produces the same shape: a table with a header the blueprint names
column-by-column, rows of strings, deduplicated on either a key or the whole
row. :class:`Table` is that, and :class:`Frames` is the store the preps write
into and read from — the one thing a second source makes necessary is
**merging into a table another source already wrote**, and the store is where
that happens.

Sharing a table is not an optimisation, it is the model. ``taxon_condition``
backs the single ``ASSOCIATED_WITH`` junction edge, because a blueprint
junction entry names one relationship and one input; so an association from a
second source is a *row* in that table, not a second relationship. Its
``condition_type`` column is what lets one relationship span ``Disease`` ∪
``Phenotype`` ∪ ``Exposure`` — the blueprint's ``target_type_column`` — rather
than three relationship names splitting one relation. The same goes for
``paper``: one PMID is one ``Paper`` node whoever cites it.

Nothing here touches a file. A build starts from an empty store, runs the
preps in declared order, and hands the store's tables to kglite as frames
(:meth:`Frames.typed`). Given that, the graph is a function of the raw inputs
and the declared prep order, and running one prep twice into the same store is
a no-op — :class:`Table`'s ``owner`` is what makes the second run replace the
first rather than add to it.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

import pandas as pd

__all__ = ["Frames", "Table", "as_list", "declared_types", "from_list"]


def as_list(values: Iterable[object]) -> str:
    """A multi-valued cell, as the JSON array a ``"list"`` column reads.

    A delimited cell is ambiguous the moment a value contains the delimiter,
    and 1,983 of this graph's synonym lists contain a comma — so a column
    whose cells are several values is written as JSON here, declared
    ``"list"`` in the fragment, and :meth:`Frames.typed` turns it back into
    the list itself before the graph sees it.

    **Empty in means empty out — deliberately not ``[]``.** An empty cell
    reaches the graph as an absent property and a ``[]`` cell as a present
    empty list, and this graph counts absences: ``WHERE r.publications IS
    NULL`` is 8,052 CARD edges with no citation, and an empty list would answer
    that question with zero.
    """
    items = [v for v in values if v not in (None, "")]
    return json.dumps(items, ensure_ascii=False) if items else ""


def from_list(cell: str | None) -> list[str]:
    """The values in a cell :func:`as_list` wrote, back as a list of strings.

    A prep that reads a table another prep wrote reads the store's **string
    rows**, not the graph, so a ``"list"`` column arrives as its JSON text.
    Anything that does not parse as a JSON array is one value kept whole,
    which is the right reading for a raw upstream cell that never went
    through :func:`as_list`.
    """
    text = (cell or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return [text]
        if isinstance(parsed, list):
            return [str(v) for v in parsed]
    return [text]


class Table:
    """Deduplicating row accumulator: first row per key wins, header fixed
    up front.

    ``key`` dedupes node tables on their primary key, which may be several
    columns: ``cited_taxa`` is keyed on ``(tax_id, source)`` because one taxon
    cited by two sources is two counts, not a sum with no attribution.
    ``dedupe_full`` dedupes edge tables on the *whole* row: a signature that
    names both a strain and its species resolves both to one tax_id, and the
    second is a duplicate fact, not a second observation. Genuinely parallel
    edges — the same taxon and disease from two different signatures — differ
    in ``source_record_id`` and survive.

    ``owner`` is what makes a *re-run* safe. Merging into a table this source
    already wrote would otherwise either freeze its old rows (a key-deduped
    node table), double them (a row-deduped edge table, where one added column
    changes the dedupe tuple and both copies survive) or — the case that was
    live in ``cited_taxa`` — sum this run's ``sum_fields`` onto the last run's.
    Given ``owner=("primary_source", "bugsigdb")`` the merge drops the rows
    that column says this source wrote, so a re-run replaces its own
    contribution and leaves everyone else's alone. **An ``owner`` column that
    is not part of ``key`` is not enough**: the other source's row for the
    same key wins the dedupe, this source's is dropped, and the attribution
    the column was added for is gone.
    """

    def __init__(
        self,
        name: str,
        fields: list[str],
        key: str | tuple[str, ...] | None = None,
        dedupe_full: bool = False,
        sum_fields: tuple[str, ...] = (),
        owner: tuple[str, str] | None = None,
    ):
        self.name = name
        self.fields = list(fields)
        self.key = (key,) if isinstance(key, str) else key
        self.dedupe_full = dedupe_full
        self.sum_fields = sum_fields
        self.owner = owner
        self.seen: set = set()
        self.rows: list[dict[str, str]] = []
        #: Rows another source had already written into this table.
        self.merged_in = 0
        #: Rows this source wrote on a previous run, dropped and rewritten.
        self.replaced = 0

    def absorb(self, existing: Table) -> None:
        """Take over what ``existing`` holds, the way merging into a table
        another source wrote did: a column this source does not write is
        left empty rather than dropped, a column the existing table has is
        added to every row, the existing rows come first so they win every
        dedupe, and the rows this source's ``owner`` claims are dropped."""
        for extra in (c for c in existing.fields if c not in self.fields):
            self.fields.append(extra)
        for row in existing.rows:
            if self.owner and (row.get(self.owner[0]) or "") == self.owner[1]:
                self.replaced += 1
                continue
            self.add({f: (row.get(f) or "") for f in self.fields})
        self.merged_in = len(self.rows)

    def add(self, row: Mapping[str, Any]) -> bool:
        if self.key is not None:
            k = tuple(row[f] for f in self.key)
            if not all(k):
                return False
            if k in self.seen:
                self._accumulate(k, row)
                return False
            self.seen.add(k)
        elif self.dedupe_full:
            k = tuple(row.get(f, "") for f in self.fields)
            if k in self.seen:
                return False
            self.seen.add(k)
        self.rows.append(
            {f: row.get(f, "") for f in self.fields}
            | {k: v for k, v in row.items() if k not in self.fields}
        )
        return True

    def _accumulate(self, key: tuple[str, ...], row: Mapping[str, Any]) -> None:
        """Add ``sum_fields`` of a duplicate-key row onto the row that won.

        ``unresolved_pathway_links`` is what uses it: Reactome and KEGG both
        count how many mapping rows one unmatched compound cost, and the
        ledger states the total rather than whichever source ran first.
        """
        if not self.sum_fields:
            return
        for held in self.rows:
            if tuple(held[f] for f in self.key) == key:
                for field in self.sum_fields:
                    a, b = str(held.get(field, "")), str(row.get(field, ""))
                    if a.isdigit() and b.isdigit():
                        held[field] = str(int(a) + int(b))
                return

    def __len__(self) -> int:
        return len(self.rows)


class Frames:
    """The tables of one build, by name — what the preps write into and read
    from, and what the loader is handed."""

    def __init__(self) -> None:
        self.tables: dict[str, Table] = {}

    def table(
        self,
        name: str,
        fields: list[str],
        *,
        key: str | tuple[str, ...] | None = None,
        dedupe_full: bool = False,
        merge: bool = False,
        sum_fields: tuple[str, ...] = (),
        owner: tuple[str, str] | None = None,
    ) -> Table:
        """A fresh :class:`Table`; with ``merge`` it absorbs what the store
        already holds under ``name`` (see :meth:`Table.absorb`)."""
        table = Table(name, fields, key, dedupe_full, sum_fields, owner)
        if merge and name in self.tables:
            table.absorb(self.tables[name])
        return table

    def put(self, table: Table) -> int:
        """Store ``table`` under its name, replacing what was there — the
        merge already happened in :meth:`table`. Returns its row count."""
        self.tables[table.name] = table
        return len(table.rows)

    def rows(self, name: str) -> list[dict[str, str]]:
        """The string rows under ``name``; empty when no prep wrote it."""
        table = self.tables.get(name)
        return table.rows if table else []

    def __contains__(self, name: str) -> bool:
        return name in self.tables

    def names(self) -> list[str]:
        return sorted(self.tables)

    def typed(
        self, declared: Mapping[str, Mapping[str, str]]
    ) -> dict[str, pd.DataFrame]:
        """Every table as the DataFrame the loader is handed.

        A frame is coerced to the blueprint's declared types and keeps its own
        dtype where none is declared, so two things are done here that a CSV
        reader did by itself, and that the whole-graph comparison of
        2026-09-04 showed are the only two that matter:

        - an **all-digit column is an integer column**, null where the cell
          was empty — declared ``int`` or not, because ids are rarely declared
          and a string id misses every declared-``int`` foreign key pointing
          at it (every ``Taxon`` and ``Paper`` doubled, with null properties);
        - a **declared ``list`` column is the list itself**, ``None`` where
          the cell was empty and ``[]`` where it was ``[]`` — the frame path
          wraps text as a one-element list rather than parsing it.

        Everything else stays the string the prep wrote; an empty string is a
        null to the loader, as it was in a CSV.
        """
        out: dict[str, pd.DataFrame] = {}
        for name, table in self.tables.items():
            df = pd.DataFrame(table.rows, columns=table.fields, dtype=object)
            types = declared.get(name, {})
            for col in df.columns:
                kind = types.get(col)
                if kind == "list":
                    df[col] = df[col].map(_parse_list)
                    continue
                values = df[col].map(lambda v: "" if v is None else str(v))
                if kind == "int" or _all_digits(values):
                    df[col] = pd.to_numeric(values.where(values != "", None)).astype(
                        "Int64"
                    )
                else:
                    df[col] = values
            out[name] = df
        return out


def _all_digits(values: pd.Series) -> bool:
    nonempty = values[values != ""]
    return bool(len(nonempty)) and bool(nonempty.str.fullmatch(r"-?\d+").all())


def _parse_list(cell: Any) -> list | None:
    if cell is None or cell == "":
        return None
    if isinstance(cell, list):
        return cell
    return from_list(str(cell))


def declared_types(blueprint: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """``{table: {column: type}}`` for every input a blueprint's specs read.

    Walks node specs and junction entries; a spec names its input by ``file``
    (the store's table name) or, in the older spelling, by ``csv`` (whose stem
    is the table name). Node ``properties`` and junction ``property_types``
    are the type maps; both are merged per table, since two specs reading one
    table declare the same column the same way.
    """
    out: dict[str, dict[str, str]] = {}

    def walk(spec: Any) -> None:
        if isinstance(spec, dict):
            name = spec.get("file")
            if name is None and isinstance(spec.get("csv"), str):
                name = spec["csv"].rsplit("/", 1)[-1].removesuffix(".csv")
            if isinstance(name, str):
                for key in ("properties", "property_types"):
                    types = spec.get(key)
                    if isinstance(types, dict):
                        out.setdefault(name, {}).update(
                            {c: t for c, t in types.items() if isinstance(t, str)}
                        )
            for v in spec.values():
                walk(v)
        elif isinstance(spec, list):
            for v in spec:
                walk(v)

    walk(blueprint.get("nodes", {}))
    return out

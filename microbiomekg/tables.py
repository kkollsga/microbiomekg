"""The flat CSV tables the blueprint loads, and how two sources share one.

Every prep script writes the same shape of file: a header the blueprint names
column-by-column, and rows deduplicated on either a primary key or the whole
row. :class:`Writer` is that, plus the one thing a second source makes
necessary — **merging into a table another source already wrote**.

Sharing a table is not an optimisation, it is the model. ``taxon_disease.csv``
backs a single ``ASSOCIATED_WITH`` junction edge, because a blueprint junction
entry names one relationship, one CSV and one target type (docs/model.md §8);
so an association from a second source is a *row* in that file, not a second
relationship. The same goes for ``paper.csv``: one PMID is one ``Paper`` node
whoever cites it, which is what makes "what else does this paper support?" a
one-hop query.

Merging is why ``scripts/build.py`` empties ``data/csv/`` before it runs the
prep scripts. Given that, the output is a function of the inputs and the
declared prep order, and re-running one prep script twice is a no-op.
"""

from __future__ import annotations

import csv
from pathlib import Path

__all__ = ["Writer"]


class Writer:
    """Deduplicating CSV writer: first row per key wins, header fixed up front.

    ``key`` dedupes node tables on their primary key, which may be several
    columns: ``cited_taxa.csv`` is keyed on ``(tax_id, source)`` because one
    taxon cited by two sources is two counts, not a sum with no attribution.
    ``dedupe_full`` dedupes
    edge tables on the *whole* row: a signature that names both a strain and
    its species resolves both to one tax_id, and the second is a duplicate
    fact, not a second observation. Genuinely parallel edges — the same taxon
    and disease from two different signatures — differ in ``source_record_id``
    and survive.

    ``merge`` makes the table shared: rows already in the file are read in
    first, so they keep their position and win every dedupe, and this source's
    rows are appended. A column this source does not write is left empty rather
    than dropped, and a column the *existing* file does not have is added to
    every row — so two sources may contribute different columns to one table
    without either knowing the other's schema.

    ``owner`` is what makes a *re-run* safe. Merging into a file this source
    already wrote would otherwise either freeze its old rows (a key-deduped
    node table), double them (a row-deduped edge table, where one added column
    changes the dedupe tuple and both copies survive) or — the case that was
    live in ``cited_taxa.csv`` — sum this run's ``sum_fields`` onto the last
    run's. Given ``owner=("primary_source", "bugsigdb")`` the reader drops the
    rows that column says this source wrote, so a re-run replaces its own
    contribution and leaves everyone else's alone. **An ``owner`` column that
    is not part of ``key`` is not enough**: the other source's row for the same
    key wins the dedupe, this source's is dropped, and the attribution the
    column was added for is gone.
    """

    def __init__(
        self,
        path: Path,
        fields: list[str],
        key: str | tuple[str, ...] | None = None,
        dedupe_full: bool = False,
        merge: bool = False,
        sum_fields: tuple[str, ...] = (),
        owner: tuple[str, str] | None = None,
    ):
        self.path = Path(path)
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
        if merge:
            self._read_existing()

    def _read_existing(self) -> None:
        if not self.path.is_file():
            return
        with self.path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            header = list(reader.fieldnames or ())
            existing = list(reader)
        for extra in (c for c in header if c not in self.fields):
            self.fields.append(extra)
        for row in existing:
            if self.owner and (row.get(self.owner[0]) or "") == self.owner[1]:
                self.replaced += 1
                continue
            self.add({f: (row.get(f) or "") for f in self.fields})
        self.merged_in = len(self.rows)

    def add(self, row: dict[str, str]) -> bool:
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
        self.rows.append(row)
        return True

    def _accumulate(self, key: tuple[str, ...], row: dict[str, str]) -> None:
        """Add ``sum_fields`` of a duplicate-key row onto the row that won.

        ``unresolved_pathway_links.csv`` is what uses it: Reactome and KEGG
        both count how many mapping rows one unmatched compound cost, and the
        ledger states the total rather than whichever source ran first.
        """
        if not self.sum_fields:
            return
        for held in self.rows:
            if tuple(held[f] for f in self.key) == key:
                for field in self.sum_fields:
                    a, b = held.get(field, ""), row.get(field, "")
                    if a.isdigit() and b.isdigit():
                        held[field] = str(int(a) + int(b))
                return

    def flush(self) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=self.fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(self.rows)
        return len(self.rows)

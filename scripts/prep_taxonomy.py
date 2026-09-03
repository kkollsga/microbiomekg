#!/usr/bin/env python3
"""NCBI new_taxdump -> ``data/csv/taxon.csv``.

Emits one row per taxon in the chosen scope: the canonical key (``tax_id``),
the scientific name, the rank, the parent pointer that becomes the
``HAS_PARENT`` ancestry edge, the ranked lineage columns, and a ``synonyms``
string for reconciliation and text search.

``--scope`` picks how much of the 3.0M-node taxonomy to emit:

* ``cited``     — only the taxa BugSigDB actually cites, plus their ancestors.
  Reads ``data/csv/cited_taxa.csv``, so run ``prep_bugsigdb.py`` first. This is
  the fast iteration scope (~20k nodes).
* ``microbial`` — Bacteria + Archaea + Fungi and their ancestors (~863k nodes).
  The default, and what the shipping graph uses.
* ``all``       — the whole dump (~3.0M nodes).

Every scope includes the full ancestor chain of everything it selects, so the
``parent_tax_id`` foreign key never dangles and ``-[:HAS_PARENT*1..]->`` always
reaches a domain.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from microbiomekg.rawdata import find_taxdump  # noqa: E402
from microbiomekg.reconcile import (  # noqa: E402
    NAME_CLASSES,
    TaxonomyIndex,
    _dmp_rows,
    is_placeholder_name,
)

#: Every prep that writes ``cited_taxa.csv``. This script filters the 3M-row
#: taxonomy down to what the sources cite, so a source writing that table
#: after it would have its edges pointing at vivified stubs with no name and
#: no lineage. ``tests/test_build_pipeline.py`` fails if a prep writes the
#: table and is missing here.
DEPENDS_ON: list[str] = ["bugsigdb", "card", "chembl", "gutmdisorder", "hmdb"]

#: Clade roots for ``--scope microbial``: Bacteria, Archaea, Fungi.
MICROBIAL_ROOTS = (2, 2157, 4751)

#: ``rankedlineage.dmp`` columns after the tax_id. The file's last column is
#: labelled "superkingdom" historically but holds the modern ``domain`` value
#: (``Bacteria``), so it is emitted as ``lineage_domain``.
LINEAGE_COLUMNS = (
    "lineage_name",
    "lineage_species",
    "lineage_genus",
    "lineage_family",
    "lineage_order",
    "lineage_class",
    "lineage_phylum",
    "lineage_kingdom",
    "lineage_domain",
)

FIELDS = [
    "tax_id",
    "scientific_name",
    "rank",
    "parent_tax_id",
    # Resolved, but not an organism anyone can act on: `uncultured bacterium`,
    # `Bacteroides sp.`, `[Clostridium] symbiosum`, a Candidatus. Carried as a
    # node property so a query excludes them with `WHERE NOT t.placeholder`
    # instead of string-matching the name (C9, C21.1).
    "placeholder",
    "synonyms",
    "synonym_count",
    *LINEAGE_COLUMNS[1:],
]

#: Cap on synonyms carried into the CSV. A handful of taxa have hundreds of
#: ``includes`` names; the graph only needs enough for a BM25 hit, and the
#: authoritative lookup lives in TaxonomyIndex, not in the graph.
SYNONYM_CAP = 20


def read_cited(cited_path: Path) -> set[int]:
    if not cited_path.is_file():
        return set()
    with cited_path.open(newline="", encoding="utf-8") as fh:
        return {int(r["tax_id"]) for r in csv.DictReader(fh) if r["tax_id"].isdigit()}


def select_scope(
    idx: TaxonomyIndex, scope: str, roots: tuple[int, ...], cited_path: Path
) -> set[int]:
    if scope == "all":
        return set(idx.parent)

    cited = read_cited(cited_path)
    if scope == "cited":
        if not cited:
            raise SystemExit(
                f"--scope cited needs {cited_path}; run scripts/prep_bugsigdb.py first"
            )
        seeds = set(cited)
    else:  # microbial
        children: dict[int, list[int]] = defaultdict(list)
        for tid, pid in idx.parent.items():
            if pid != tid:
                children[pid].append(tid)
        seeds = set()
        stack = [r for r in roots if r in idx.parent]
        while stack:
            n = stack.pop()
            if n in seeds:
                continue
            seeds.add(n)
            stack.extend(children[n])
        # A clade filter is a convenience, never a reason to lose a fact: 192
        # of the taxa BugSigDB cites live outside Bacteria/Archaea/Fungi
        # (viruses, protists, host plants). Without this union they become
        # untitled vivified stubs at build time, which the loader reports as a
        # warning and nothing else notices.
        outside = cited - seeds
        if outside:
            print(f"  + {len(outside):,} cited taxa outside the clade roots, kept anyway")
            seeds |= outside

    keep = set(seeds)
    for tid in seeds:
        keep.update(idx.lineage(tid))
    return keep


def read_ranked_lineage(path: Path, keep: set[int]) -> dict[int, list[str]]:
    """tax_id -> the nine lineage strings, for the taxa in scope."""
    out: dict[int, list[str]] = {}
    if not path.is_file():
        print(f"  warning: {path.name} missing; lineage columns will be blank")
        return out
    for row in _dmp_rows(path):
        if not row or not row[0].isdigit():
            continue
        tid = int(row[0])
        if tid not in keep:
            continue
        vals = row[1:10] + [""] * max(0, 10 - len(row))
        out[tid] = vals[:9]
    return out


def read_synonyms(path: Path, keep: set[int]) -> dict[int, list[str]]:
    """tax_id -> its non-scientific names, deduplicated and capped."""
    out: dict[int, list[str]] = defaultdict(list)
    sci: dict[int, str] = {}
    for row in _dmp_rows(path):
        if len(row) < 4 or not row[0].isdigit():
            continue
        tid = int(row[0])
        if tid not in keep:
            continue
        text, cls = row[1], row[3]
        if cls == "scientific name":
            sci[tid] = text
            continue
        if cls not in NAME_CLASSES:
            continue
        bucket = out[tid]
        if text not in bucket:
            bucket.append(text)
    for tid, names in out.items():
        s = sci.get(tid)
        if s in names:
            names.remove(s)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", type=Path, default=Path("data/raw"))
    ap.add_argument("--taxdump", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=Path("data/csv"))
    ap.add_argument("--scope", choices=("cited", "microbial", "all"), default="microbial")
    ap.add_argument("--cited-from", type=Path, default=None)
    ap.add_argument(
        "--roots",
        default=",".join(str(r) for r in MICROBIAL_ROOTS),
        help="Comma-separated clade roots for --scope microbial "
        "(default 2,2157,4751 = Bacteria, Archaea, Fungi; add 10239 for Viruses).",
    )
    args = ap.parse_args(argv)
    cited_path = args.cited_from or (args.out / "cited_taxa.csv")
    try:
        taxdump = args.taxdump or find_taxdump(args.raw)
    except FileNotFoundError as e:
        ap.error(str(e))

    print(f"loading taxdump from {taxdump} ...", flush=True)
    idx = TaxonomyIndex.from_taxdump(taxdump)
    print(f"  {len(idx.parent):,} taxa", flush=True)

    roots = tuple(int(r) for r in args.roots.split(",") if r.strip())
    keep = select_scope(idx, args.scope, roots, cited_path)
    print(f"scope={args.scope}: {len(keep):,} taxa in scope", flush=True)

    lineage = read_ranked_lineage(taxdump / "rankedlineage.dmp", keep)
    synonyms = read_synonyms(taxdump / "names.dmp", keep)

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "taxon.csv"
    n_truncated = n_placeholder = 0
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for tid in sorted(keep):
            parent = idx.parent.get(tid, tid)
            lin = lineage.get(tid, [""] * 9)
            syn = synonyms.get(tid, [])
            if len(syn) > SYNONYM_CAP:
                n_truncated += 1
            name = idx.scientific_name.get(tid, lin[0] or str(tid))
            placeholder = is_placeholder_name(name)
            n_placeholder += placeholder
            row = {
                "tax_id": tid,
                "scientific_name": name,
                "rank": idx.rank.get(tid, ""),
                "placeholder": "true" if placeholder else "false",
                # root(1) is its own parent in nodes.dmp; a self-edge would make
                # -[:HAS_PARENT*1..]-> non-terminating on any walk that reaches it.
                "parent_tax_id": "" if parent == tid or parent not in keep else parent,
                "synonyms": " | ".join(syn[:SYNONYM_CAP]),
                "synonym_count": len(syn),
            }
            row.update(zip(LINEAGE_COLUMNS[1:], lin[1:]))
            w.writerow(row)

    print(f"wrote {path} ({len(keep):,} rows; {n_placeholder:,} placeholder names; "
          f"{n_truncated:,} synonym lists capped at {SYNONYM_CAP})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

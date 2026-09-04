"""NCBI new_taxdump -> the ``taxon`` table.

Emits one row per taxon in the chosen scope: the canonical key (``tax_id``),
the scientific name, the rank, the parent pointer that becomes the
``HAS_PARENT`` ancestry edge, the ranked lineage columns, and a ``synonyms``
string for reconciliation and text search.

``scope`` picks how much of the 3.0M-node taxonomy to emit:

* ``cited``     — only the taxa the source preps actually cite, plus their
  ancestors. Reads the store's ``cited_taxa`` table, which every prep in
  :data:`DEPENDS_ON` writes and so runs first. This is the fast iteration scope
  (~20k nodes).
* ``microbial`` — Bacteria + Archaea + Fungi and their ancestors (~863k nodes).
  The default, and what the shipping graph uses.
* ``all``       — the whole dump (~3.0M nodes).

Every scope includes the full ancestor chain of everything it selects, so the
``parent_tax_id`` foreign key never dangles and ``-[:HAS_PARENT*1..]->`` always
reaches a domain.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from microbiomekg.rawdata import MissingInput, find_taxdump
from microbiomekg.tables import Frames, as_list
from microbiomekg.reconcile import (
    NAME_CLASSES,
    TaxonomyIndex,
    _dmp_rows,
    is_placeholder_name,
)

#: The raw files this prep reads, relative to ``--raw``, in the layout
#: ``fetch`` writes. `status` reports on exactly these. Every prep resolves
#: names against this dump; it is declared here, once, because this is the
#: prep that reads all five files.
RAW_INPUTS: list[str] = [
    "ncbi_taxonomy/nodes.dmp",
    "ncbi_taxonomy/names.dmp",
    "ncbi_taxonomy/rankedlineage.dmp",
    "ncbi_taxonomy/merged.dmp",
    "ncbi_taxonomy/delnodes.dmp",
]

#: Every prep that writes ``cited_taxa``. This prep filters the 3M-row taxonomy
#: down to what the sources cite, so a source writing that table after it would
#: have its edges pointing at vivified stubs with no name and no lineage.
#: ``tests/test_build_pipeline.py`` fails if a prep writes the table and is
#: missing here.
DEPENDS_ON: list[str] = [
    "bugsigdb",
    "card",
    "chembl",
    "gutmdisorder",
    "hmdb",
    "maier2018",
    "masi",
    "njc19",
    "zimmermann2019",
]

#: The one source that writes *node properties* onto a taxon rather than edges
#: onto it, and the table it leaves them in.
#:
#: MASI's microbe dictionary says which of the organisms it curates are used as
#: probiotics, in whom, and how far the evidence has got. Those are properties
#: of the organism, not of any interaction, and ``Taxon`` is one table — so the
#: only place they can be written is here, which is why ``masi`` is in
#: :data:`DEPENDS_ON` above alongside the sources that write ``cited_taxa``.
#: The columns are written on **every** row whether or not that table exists,
#: so the column set ``microbiomekg/blueprints/core.json`` declares does not
#: depend on which sources a build ran.
PROBIOTIC_TABLE = "taxon_probiotic"
PROBIOTIC_COLUMNS = (
    "probiotic",
    "probiotic_use_species",
    "probiotic_research_stage",
    "probiotic_reported_name",
)

#: Clade roots for ``scope="microbial"``: Bacteria, Archaea, Fungi.
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
    # The same names again, joined, and this is a kglite gap rather than a
    # choice: `build_text_index` refuses a list-valued property ("BM25 indexes
    # text: a numeric or list-valued property is not indexable"), and
    # `Taxon.synonyms` carries one of the five BM25 indexes — the lane D12 and
    # the reconciliation skill rank an old binomial through. So the list is the
    # queryable property and this is what the index reads. One join, at write
    # time, so the two cannot disagree.
    "synonyms_text",
    "synonym_count",
    *LINEAGE_COLUMNS[1:],
    # Three-state on purpose: `true` for a taxon MASI marks as a probiotic,
    # `false` for the other organisms MASI curates, and **empty for every taxon
    # MASI says nothing about**. Writing `false` everywhere would turn "this
    # database does not cover the organism" into "this organism is not a
    # probiotic", which MASI never claimed about anything.
    *PROBIOTIC_COLUMNS,
]

#: Cap on synonyms carried onto the node. A handful of taxa have hundreds of
#: ``includes`` names; the graph only needs enough for a BM25 hit, and the
#: authoritative lookup lives in TaxonomyIndex, not in the graph.
SYNONYM_CAP = 20


def read_probiotics(rows: list[dict[str, str]]) -> dict[int, dict[str, str]]:
    """``tax_id -> {column: value}`` from the table MASI's prep leaves in the
    store. An absent table is an empty map, not an error — every row gets the
    columns regardless; see :data:`PROBIOTIC_TABLE`.
    """
    out: dict[int, dict[str, str]] = {}
    for row in rows:
        if row.get("tax_id", "").isdigit():
            out[int(row["tax_id"])] = {c: (row.get(c) or "") for c in PROBIOTIC_COLUMNS}
    return out


def read_cited(rows: list[dict[str, str]]) -> set[int]:
    return {int(r["tax_id"]) for r in rows if r.get("tax_id", "").isdigit()}


def select_scope(
    idx: TaxonomyIndex,
    scope: str,
    roots: tuple[int, ...],
    cited_rows: list[dict[str, str]],
) -> set[int]:
    if scope == "all":
        return set(idx.parent)

    cited = read_cited(cited_rows)
    if scope == "cited":
        if not cited:
            raise SystemExit(
                'scope="cited" needs a cited_taxa table in the store; run a source prep first'
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
            print(
                f"  + {len(outside):,} cited taxa outside the clade roots, kept anyway"
            )
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
    """tax_id -> its non-scientific names, deduplicated; ``run`` applies the cap."""
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


def run(
    raw: Path,
    store: Frames,
    *,
    taxdump: Path | None = None,
    scope: str = "microbial",
    roots: tuple[int, ...] = MICROBIAL_ROOTS,
) -> dict[str, int]:
    """The ``taxon`` table into ``store``; returns its row count.

    ``scope`` is ``cited`` (only the taxa the store's ``cited_taxa`` table
    names), ``microbial`` (the clades under ``roots`` — Bacteria, Archaea,
    Fungi by default; add 10239 for Viruses — plus every cited taxon outside
    them) or ``all``. MASI's probiotic annotation is read off the store when
    its prep ran. Raises :class:`MissingInput` when the taxdump is not there.
    """
    try:
        taxdump = taxdump or find_taxdump(raw)
    except FileNotFoundError as e:
        raise MissingInput(str(e)) from e
    # find_taxdump keys on nodes.dmp alone; the other four declared dumps are
    # what the index reads next, and an absent one is a skip, not a traceback.
    absent = [
        n
        for n in (r.rsplit("/", 1)[1] for r in RAW_INPUTS)
        if not (taxdump / n).is_file()
    ]
    if absent:
        raise MissingInput(f"no {', '.join(absent)} in {taxdump}")

    print(f"loading taxdump from {taxdump} ...", flush=True)
    idx = TaxonomyIndex.from_taxdump(taxdump)
    print(f"  {len(idx.parent):,} taxa", flush=True)

    keep = select_scope(idx, scope, tuple(roots), store.rows("cited_taxa"))
    print(f"scope={scope}: {len(keep):,} taxa in scope", flush=True)

    lineage = read_ranked_lineage(taxdump / "rankedlineage.dmp", keep)
    synonyms = read_synonyms(taxdump / "names.dmp", keep)
    probiotics = read_probiotics(store.rows(PROBIOTIC_TABLE))
    if probiotics:
        print(f"  {len(probiotics):,} taxa carry MASI probiotic annotation")

    taxa = store.table("taxon", FIELDS, key="tax_id")
    n_truncated = n_placeholder = 0
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
            "synonyms": as_list(syn[:SYNONYM_CAP]),
            "synonyms_text": " | ".join(syn[:SYNONYM_CAP]),
            "synonym_count": len(syn),
        }
        row.update(zip(LINEAGE_COLUMNS[1:], lin[1:]))
        row.update(probiotics.get(tid, dict.fromkeys(PROBIOTIC_COLUMNS, "")))
        taxa.add({k: str(v) for k, v in row.items()})
    n = store.put(taxa)

    print(
        f"taxon: {n:,} rows; {n_placeholder:,} placeholder names; "
        f"{n_truncated:,} synonym lists capped at {SYNONYM_CAP}"
    )
    return {"taxon": n}

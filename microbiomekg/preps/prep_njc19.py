#!/usr/bin/env python3
"""NJC19's Online-only Table 5 -> the consumption edges D6 was dead without.

``data/raw/njc19/41597_2020_516_MOESM1_ESM.xlsx`` is a single sheet,
``Online-only Table 5``, of 9,141 rows: three lines of legend, a blank, a header,
and **9,136 curated metabolic associations** between an organism and a compound.
Four columns carry everything — ``Species`` (844 distinct strings, of which 6 are
host cell types), ``Small-molecule metabolite or macromolecule`` (283), a
``Metabolic activity`` drawn from a closed seven-value vocabulary, and a
``Ref. #`` indexing the paper's own Online-only Table 2. The identical file is
the only spreadsheet inside ``PMC7320173_supplementaryFiles.zip``, which
otherwise holds the three figures.

What comes out, and where each part goes:

* ``Consumption (import)`` -> ``CONSUMES``, in ``taxon_metabolite_consumed.csv``.
  This is the edge D6 exists for: **MES = 2·P·C / (P + C) is identically zero
  while C is**, so before this table landed every row of that query returned 0.0.
* ``Production (export)`` -> ``PRODUCES``, merged into HMDB's
  ``taxon_metabolite.csv``. One relationship, one table, two sources
  (:mod:`microbiomekg.tables`), told apart by ``primary_source``.
* ``Macromolecule degradation`` -> ``DEGRADES``. Kept apart from ``CONSUMES``
  because breaking down a polymer outside the cell and importing a small
  molecule are different claims about a community, and the source separates them.
* anything marked ``(-)`` -> ``NO_EXCHANGE_WITH``, with ``source_relation``
  naming the refuted activity. **912 rows**, and they are an edge type rather
  than a flag so that no ``MATCH (t)-[:CONSUMES]->(m)`` can silently count a
  refutation as an observation.

Three shapes in the file that a straight read gets wrong, each measured here and
reasoned about in :mod:`microbiomekg.ontology.njc19`:

* **180 rows carry two activities and a scoped reference cell.**
  ``Consumption (import), Production (export)`` with
  ``import:415, 418;export:417`` is two claims from two literatures, and it is
  the only combined spelling in the file.
* **2,426 rows (26.6%) stand on nothing but ``(G)``-marked references** — a
  species-filed row whose every literature source was read at genus level.
  ``genus_level_evidence`` is the boolean; guard G5 is why it is not dropped and
  not ignored.
* **Six ``Species`` values are host cell types**, not organisms. They are
  excluded by name and counted, because sending them through ``reconcile``
  produces six ``UnresolvedTaxon`` tombstones that read as six taxa NCBI lost.

The compound side is free text with **no cross-reference of any kind** — no
ChEBI, HMDB, KEGG, PubChem or InChIKey — so every compound is joined to the
graph's own ``Metabolite`` identity by name through
:func:`microbiomekg.ontology.njc19.name_variants`, and ``metabolite_join``
records which spelling matched. A compound no node holds is minted as
``NJC19:<name>``, which is most of the macromolecules: a metabolome database has
no record of pectin.
"""

from __future__ import annotations

from collections import Counter, OrderedDict
from pathlib import Path

from microbiomekg import ontology as ont
from microbiomekg.ontology import njc19 as nj
from microbiomekg.rawdata import MissingInput, find_taxdump
from microbiomekg.reconcile import TaxonomyIndex, rank_depth
from microbiomekg.tables import Frames, as_list

SOURCE = nj.SOURCE

#: Reads ``metabolite.csv``, which both of them write: the compound join has to
#: see every ``Metabolite`` node that exists before it decides to mint one, and
#: MiMeDB's names are what carry 32 of NJC19's compounds that HMDB has no record
#: of.
#: The raw files this prep reads, relative to ``--raw``, in the layout
#: ``fetch`` writes. `status` reports on exactly these.
RAW_INPUTS: list[str] = ["njc19/41597_2020_516_MOESM1_ESM.xlsx"]

DEPENDS_ON: list[str] = ["hmdb", "mimedb"]

#: The sheet the paper ships. Named rather than "the first sheet" so a future
#: supplement that adds one fails loudly instead of loading the wrong table.
SHEET = "Online-only Table 5"

#: The header cell that marks where the legend ends. The sheet opens with three
#: lines of prose and a blank row, and their column count matches the data's, so
#: a fixed skip is a silent off-by-one the day the legend grows a line.
HEADER_CELL = "Metabolic activity"

#: Column positions within a data row, after the header is found. Column 0 is
#: the legend's own indent column and is empty on every one of the 9,136 rows.
SPECIES, COMPOUND, ACTIVITY, REFERENCES = 1, 2, 3, 4

#: The relationship -> the CSV its rows go in. ``PRODUCES`` is HMDB's table.
TABLES: dict[str, str] = {
    "PRODUCES": "taxon_metabolite",
    "CONSUMES": "taxon_metabolite_consumed",
    "DEGRADES": "taxon_metabolite_degraded",
    "NO_EXCHANGE_WITH": "taxon_metabolite_absent",
}

EXCHANGE_FIELDS = [
    "evidence_level",
    "knowledge_level",
    "agent_type",
    "primary_source",
    "source_record_id",
    "source_licence",
    "source_relation",
    "reported_name",
    "reported_rank",
    "original_rank",
    "resolution_status",
    "reported_compound",
    "metabolite_join",
    "genus_level_evidence",
    "reference_ids",
    "n_references",
]

METABOLITE_FIELDS = [
    "metabolite_id",
    "name",
    "hmdb_id",
    "chebi_id",
    "kegg_id",
    "pubchem_cid",
    "inchikey",
    "status",
    "biospecimens",
    "microbial_origin",
    "origin",
    "chemical_formula",
    "secondary_accessions",
    "selection_rule",
    "source",
]

LEDGER_FIELDS = [
    "species",
    "compound",
    "activity",
    "references",
    "resolved_tax_id",
    "resolved_rank",
    "reason",
    "source",
]


def read_table(path: Path) -> list[tuple]:
    """The 9,136 data rows of ``Online-only Table 5``, legend and header removed."""
    import openpyxl

    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    if SHEET not in book.sheetnames:
        raise SystemExit(
            f"{path} has no sheet named {SHEET!r} (found {', '.join(book.sheetnames)})"
        )
    rows = list(book[SHEET].iter_rows(values_only=True))
    book.close()
    for i, row in enumerate(rows):
        if any(isinstance(c, str) and c.strip() == HEADER_CELL for c in row):
            return [r for r in rows[i + 1 :] if any(c is not None for c in r)]
    raise SystemExit(f"{path}: no header row containing {HEADER_CELL!r}")


def load_metabolite_names(rows: list[dict[str, str]]) -> dict[str, str]:
    """``casefolded name -> metabolite_id`` over every ``Metabolite`` node so far.

    First writer wins, which is HMDB and then MiMeDB in prep order — the same
    precedence the node table itself has, so the index and the graph cannot
    disagree about which node a name reaches.
    """
    names: dict[str, str] = {}
    if not rows:
        return names
    for row in rows:
        name = (row.get("name") or "").strip().casefold()
        key = row.get("metabolite_id") or ""
        # This source's own minted nodes from a previous run are excluded:
        # `Writer(owner=...)` drops and rewrites them, so a second run that
        # saw them would join its compounds to nodes it is about to delete.
        if name and key and (row.get("source") or "") != SOURCE:
            names.setdefault(name, key)
    return names


def resolve_compound(
    compound: str, names: dict[str, str]
) -> tuple[str, str, str, list[str]]:
    """``(metabolite_id, join route, display name, every spelling tried)``.

    The first variant that names a node wins, and :func:`name_variants` orders
    them so that what the source actually wrote is tried before anything derived
    from it. A compound nothing matches is minted on its head name, which is the
    honest outcome for the macromolecules: ``Pectin`` and ``Chitin`` are real
    compounds NJC19 curates degradation of and a human-metabolome database has
    no reason to hold.
    """
    variants = nj.name_variants(compound)
    head = variants[0][0] if variants else compound.strip()
    for spelling, route in variants:
        found = names.get(spelling.casefold())
        if found is not None:
            return found, route, spelling, [v for v, _ in variants]
    return f"NJC19:{head}", "minted", head, [v for v, _ in variants]


def run(
    raw: Path,
    store: Frames,
    *,
    xlsx: Path | None = None,
    taxdump: Path | None = None,
    rank_ceiling: str = "species",
) -> dict[str, int]:
    """NJC19's tables into ``store``; returns each table's row count.

    ``xlsx`` defaults to ``raw/njc19/41597_2020_516_MOESM1_ESM.xlsx``. Reads
    HMDB's ``metabolite`` table off the store. Raises :class:`MissingInput`
    when the workbook or the taxdump is not there.
    """

    xlsx = xlsx or (raw / SOURCE / "41597_2020_516_MOESM1_ESM.xlsx")
    if not xlsx.is_file():
        # Exit 3, not 2 — "this source's raw file is not on this machine" rather
        # than "this script was called wrong", so an absent file leaves the build
        # without failing it.
        raise MissingInput(f"no NJC19 supplementary xlsx at {xlsx}")
    try:
        taxdump = taxdump or find_taxdump(raw)
    except FileNotFoundError as e:
        raise MissingInput(str(e)) from e
    names = load_metabolite_names(store.rows("metabolite"))
    print(f"metabolite.csv: {len(names):,} names already have a node")

    rows = read_table(xlsx)
    print(f"read {len(rows):,} association rows from {xlsx}")

    print(f"loading taxdump from {taxdump} ...", flush=True)
    idx = TaxonomyIndex.from_taxdump(taxdump)
    print(f"  {len(idx.parent):,} taxa, {len(idx.names):,} name keys", flush=True)

    edges = {
        rel: store.table(
            table,
            ["tax_id", "metabolite_id", *EXCHANGE_FIELDS],
            dedupe_full=True,
            merge=True,
            owner=("primary_source", SOURCE),
        )
        for rel, table in TABLES.items()
    }
    metabolites = store.table(
        "metabolite",
        METABOLITE_FIELDS,
        key="metabolite_id",
        merge=True,
        owner=("source", SOURCE),
    )
    unresolved_nodes = store.table(
        "unresolved_taxa",
        [
            "unresolved_id",
            "raw_name",
            "reported_rank",
            "original_rank",
            "reported_tax_id",
            "source",
            "status",
            "candidates",
            "note",
            "n_signatures",
        ],
        key="unresolved_id",
        merge=True,
        owner=("source", SOURCE),
    )
    # C18's accounting: every input row that becomes no edge, with what it did
    # reach. Three populations live here — the six host cell types, the organism
    # strings NCBI no longer carries, and any activity outside the closed
    # vocabulary — and none of them is a drop.
    ledger = store.table(
        "unresolved_exchange",
        LEDGER_FIELDS,
        merge=True,
        owner=("source", SOURCE),
    )
    cited = store.table(
        "cited_taxa",
        ["tax_id", "source", "n_signatures"],
        key=("tax_id", "source"),
        merge=True,
        owner=("source", SOURCE),
    )

    counters: Counter[str] = Counter()
    per_relation: Counter[str] = Counter()
    joins: Counter[str] = Counter()
    resolutions: Counter[str] = Counter()
    unresolved_hits: Counter[str] = Counter()
    taxa_seen: "OrderedDict[int, int]" = OrderedDict()
    minted: dict[str, str] = {}
    #: species string -> its Resolution, so 9,136 rows cost 844 lookups.
    resolved: dict[str, object] = {}
    #: compound string -> its join, for the same reason.
    compounds: dict[str, tuple[str, str, str, list[str]]] = {}

    for row in rows:
        counters["rows"] += 1
        species = str(row[SPECIES] or "").strip()
        compound = str(row[COMPOUND] or "").strip()
        activity = str(row[ACTIVITY] or "").strip()
        references = row[REFERENCES] if len(row) > REFERENCES else None

        if not species or not compound:
            counters["incomplete_row"] += 1
            ledger.add(
                {
                    "species": species,
                    "compound": compound,
                    "activity": activity,
                    "references": str(references or ""),
                    "resolved_tax_id": "",
                    "resolved_rank": "",
                    "reason": "row names no organism or no compound",
                    "source": SOURCE,
                }
            )
            continue

        if species.casefold() in nj.HOST_CELL_TYPES:
            counters["host_cell_type"] += 1
            ledger.add(
                {
                    "species": species,
                    "compound": compound,
                    "activity": activity,
                    "references": str(references or ""),
                    "resolved_tax_id": "",
                    "resolved_rank": "",
                    "reason": "one of NJC19's six host cell types, not an organism: "
                    "resolving it would file a cell type as a taxon NCBI lost",
                    "source": SOURCE,
                }
            )
            continue

        relations = nj.activity_relations(activity)
        if len(relations) > 1:
            counters["combined_rows"] += 1
        if not relations:
            counters["unknown_activity"] += 1
            ledger.add(
                {
                    "species": species,
                    "compound": compound,
                    "activity": activity,
                    "references": str(references or ""),
                    "resolved_tax_id": "",
                    "resolved_rank": "",
                    "reason": f"metabolic activity {activity!r} is outside NJC19's "
                    f"closed vocabulary",
                    "source": SOURCE,
                }
            )
            continue

        if species not in resolved:
            resolved[species] = idx.resolve(species, rank_ceiling=rank_ceiling)
            resolutions[resolved[species].status] += 1
        res = resolved[species]
        rank = idx.rank.get(res.tax_id) or "" if res.tax_id is not None else ""

        if res.tax_id is None:
            counters["unresolved_rows"] += 1
            uid = f"unresolved:{SOURCE}:{species.casefold()}"
            unresolved_nodes.add(
                {
                    "unresolved_id": uid,
                    "raw_name": species,
                    "reported_rank": "species-level term",
                    "original_rank": res.original_rank or "",
                    "reported_tax_id": "",
                    "source": SOURCE,
                    "status": res.status,
                    "candidates": as_list(str(c) for c in res.candidates),
                    "note": res.note,
                    "n_signatures": "0",
                }
            )
            unresolved_hits[uid] += 1
            ledger.add(
                {
                    "species": species,
                    "compound": compound,
                    "activity": activity,
                    "references": str(references or ""),
                    "resolved_tax_id": "",
                    "resolved_rank": "",
                    "reason": f"taxon {res.status}: {res.note}",
                    "source": SOURCE,
                }
            )
            continue

        own = rank_depth(rank)
        ceiling = rank_depth(nj.EXCHANGE_RANK_CEILING)
        if own is None or ceiling is None or own < ceiling:
            # NJC19 files every row against a species, so this is a guard against
            # a promotion surprise rather than a working filter: a name that
            # resolved to a family would be an exchange claim about a clade,
            # which is not what the source curated.
            counters["rank_too_broad"] += 1
            ledger.add(
                {
                    "species": species,
                    "compound": compound,
                    "activity": activity,
                    "references": str(references or ""),
                    "resolved_tax_id": str(res.tax_id),
                    "resolved_rank": rank,
                    "reason": f"resolved rank {rank or 'unplaced'!r} is broader than "
                    f"{nj.EXCHANGE_RANK_CEILING!r}",
                    "source": SOURCE,
                }
            )
            continue

        if compound not in compounds:
            compounds[compound] = resolve_compound(compound, names)
            joins[compounds[compound][1]] += 1
        metabolite_id, route, display, _tried = compounds[compound]

        if route == "minted" and metabolite_id not in minted:
            minted[metabolite_id] = display
            metabolites.add(
                {
                    "metabolite_id": metabolite_id,
                    "name": display,
                    "hmdb_id": "",
                    "chebi_id": "",
                    "kegg_id": "",
                    "pubchem_cid": "",
                    "inchikey": "",
                    # No `status`: NJC19 does not grade compounds, and writing one
                    # of HMDB's four values here would put a detection claim on a
                    # record nobody detected.
                    "status": "",
                    "biospecimens": "",
                    # Not `true`. NJC19 says an organism exchanges this compound,
                    # which is not the same claim as HMDB's "this compound is of
                    # microbial origin" — pectin is exchanged and is a plant polymer.
                    "microbial_origin": "false",
                    "origin": "",
                    "chemical_formula": "",
                    "secondary_accessions": "",
                    "selection_rule": "njc19-exchange",
                    "source": SOURCE,
                }
            )

        taxa_seen[res.tax_id] = taxa_seen.get(res.tax_id, 0) + 1
        for relationship, negated in relations:
            refs, genus_level = nj.split_references(references, relationship)
            source_relation = (
                nj.NEGATIVE_RELATIONS if negated else nj.POSITIVE_RELATIONS
            )[relationship]
            target = "NO_EXCHANGE_WITH" if negated else relationship
            per_relation[target] += 1
            counters["edges"] += 1
            edges[target].add(
                {
                    "tax_id": str(res.tax_id),
                    "metabolite_id": metabolite_id,
                    "evidence_level": nj.EVIDENCE_LEVEL,
                    "knowledge_level": ont.knowledge_level(SOURCE),
                    "agent_type": ont.agent_type(SOURCE),
                    "primary_source": SOURCE,
                    "source_record_id": f"{SOURCE}:{species}|{compound}|{source_relation}",
                    "source_licence": ont.SOURCE_LICENCE.get(SOURCE, ""),
                    "source_relation": source_relation,
                    "reported_name": species,
                    "reported_rank": "species-level term",
                    "original_rank": res.original_rank or rank,
                    "resolution_status": res.status,
                    "reported_compound": compound,
                    "metabolite_join": route,
                    "genus_level_evidence": "true" if genus_level else "false",
                    "reference_ids": as_list(refs),
                    "n_references": str(len(refs)),
                }
            )

    for row in unresolved_nodes.rows:
        if row["source"] == SOURCE:
            row["n_signatures"] = str(unresolved_hits.get(row["unresolved_id"], 0))
    for tid, n in sorted(taxa_seen.items()):
        cited.add({"tax_id": str(tid), "source": SOURCE, "n_signatures": str(n)})

    tables = (*edges.values(), metabolites, unresolved_nodes, ledger, cited)
    counts = {w.name: store.put(w) for w in tables}

    genus_level = sum(
        1
        for w in edges.values()
        for r in w.rows
        if r.get("primary_source") == SOURCE and r.get("genus_level_evidence") == "true"
    )
    print(
        f"\nread {counters['rows']:,} rows -> {counters['edges']:,} edges over "
        f"{len(taxa_seen):,} taxa and {len(compounds):,} compounds"
    )
    print(
        "  by relationship: "
        + ", ".join(f"{rel} {n:,}" for rel, n in sorted(per_relation.items()))
    )
    print(
        f"  negatives kept as NO_EXCHANGE_WITH: {per_relation['NO_EXCHANGE_WITH']:,} "
        f"(never folded into the positive edge)"
    )
    print(
        f"  rows curating both directions, split into two edges: "
        f"{counters['combined_rows']:,} (their references split with them)"
    )
    print(
        f"  species-level rows standing on genus-level references only: "
        f"{genus_level:,} edges"
    )
    print(
        "  organism resolution: "
        + ", ".join(f"{s} {n:,}" for s, n in resolutions.most_common())
    )
    print(
        f"  not loaded: {counters['host_cell_type']:,} rows naming one of NJC19's "
        f"six host cell types, {counters['unresolved_rows']:,} rows whose organism "
        f"no NCBI id could be resolved for, {counters['rank_too_broad']:,} broader "
        f"than {nj.EXCHANGE_RANK_CEILING}, {counters['unknown_activity']:,} with an "
        f"activity outside the vocabulary"
    )
    print("  compound join: " + ", ".join(f"{r} {n:,}" for r, n in joins.most_common()))
    print(f"  minted {len(minted):,} Metabolite nodes for compounds no source held")
    for name, n in counts.items():
        print(f"  {name:34s} {n:>9,}")
    shared = {w.name: w.merged_in for w in tables if w.merged_in}
    if shared:
        print(
            "  merged into tables another source had written: "
            + ", ".join(f"{name} +{n:,}" for name, n in shared.items())
        )
    return counts

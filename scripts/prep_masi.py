#!/usr/bin/env python3
"""MASI v1.0's four downloads -> the curated layer under the two measured ones.

``data/raw/masi/MASI_v1.0_download_*.xlsx`` are the four tables of MASI (Zeng et
al., *Nucleic Acids Research* 49:D776, 2021, PMC7779062), downloaded by hand
because the host's TLS certificate has expired
(``data/raw/masi/PROVENANCE.md``):

* ``microbeSubstanceInteractionRecords_ver20200928`` — **12,512 rows x 24
  columns**, the interactions. Two ``Interaction_Category`` values and nothing
  else: 4,295 ``Microbes metabolize substances`` and 8,217 ``Substances alter
  microbe abundance``.
* ``microbeDiseaseAssociationRecords`` — 784 x 11, taxon–disease abundance
  associations with a PMID each.
* ``microbesInfo`` — 806 x 14, the microbe dictionary: NCBI ids at four ranks,
  and the ``if_probiotic`` / ``probiotic_use_species`` /
  ``probiotic_research_stage`` block that lands on ``Taxon``.
* ``substanceInfo`` — 1,350 x 18, the substance dictionary.

**The ``.xlsx`` files are read and the ``.txt`` twins are not**, even though the
site ships both and three of the four ``.txt`` are honest TSV. ``microbesInfo.txt``
is not: its header row contains **zero tab characters** — the columns are
space-padded to a width — and no delimiter rule recovers a table whose
``microbe_name`` values contain single spaces of their own. All four ``.xlsx``
carry one ``Sheet1`` with typed cells, so one reader serves all four and the
awkward one is not a special case.

**What comes out, and why none of it lands on a relationship a primary source
owns.** MASI is an aggregator: 5,419 of its interaction rows cite Maier 2018 and
2,884 cite Zimmermann 2019, both of which this graph loads from the papers
themselves. So this prep writes MASI's substances as their own ``Substance``
nodes, its four interaction relationships as its own, and the identity between a
MASI substance and a graph ``Drug`` as a declared ``SAME_COMPOUND_AS`` edge.
``duplicates_primary_source`` then names, per edge, every loaded primary source
that already measures that exact (taxon, compound) pair — computed here by
reading the screens' own CSVs, which is what ``DEPENDS_ON`` is for. The
reasoning is in :mod:`microbiomekg.ontology.masi`.

The disease records go into the shared ``taxon_condition.csv`` as a fourth source
of ``ASSOCIATED_WITH``, keyed through MONDO by **name** — MASI ships no
condition identifier at all, so :meth:`microbiomekg.conditions.MondoIndex.
mondo_by_name` is the only route, and the route it took is on the node as
``condition_join``.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from microbiomekg import ontology as ont  # noqa: E402
from microbiomekg.conditions import MondoIndex  # noqa: E402
from microbiomekg.drugs import DrugIndex, join_drug  # noqa: E402
from microbiomekg.ontology import masi as ms  # noqa: E402
from microbiomekg.rawdata import find_taxdump  # noqa: E402
from microbiomekg.reconcile import TaxonomyIndex  # noqa: E402
from microbiomekg.tables import Writer, as_list  # noqa: E402

SOURCE = ms.SOURCE

#: Reads ``drug.csv`` for the substance join, and the two screens' four edge
#: tables for the overlap check that fills ``duplicates_primary_source``. Naming
#: them here is not a convenience: the whole point of this source's shape is that
#: it never silently restates a measurement, and the only way to know which of
#: its rows *are* restatements is to have the measurements on disk first.
DEPENDS_ON: list[str] = ["chembl", "maier2018", "zimmermann2019"]

RAW_SUBDIR = "masi"

#: The four workbooks, by the role this script reads them in. Named rather than
#: globbed so a partial download fails on the file it is missing.
WORKBOOKS: dict[str, str] = {
    "interactions": "MASI_v1.0_download_microbeSubstanceInteractionRecords_ver20200928.xlsx",
    "diseases": "MASI_v1.0_download_microbeDiseaseAssociationRecords.xlsx",
    "microbes": "MASI_v1.0_download_microbesInfo.xlsx",
    "substances": "MASI_v1.0_download_substanceInfo.xlsx",
}

#: ``(relationship, CSV)`` for the four interaction tables, in report order.
EDGE_TABLES: dict[str, str] = {
    ms.RELATION_METABOLISES: "taxon_substance_metabolised.csv",
    ms.RELATION_NO_METABOLISM: "taxon_substance_not_metabolised.csv",
    ms.RELATION_ABUNDANCE_CHANGED: "taxon_substance_abundance.csv",
    ms.RELATION_ABUNDANCE_UNCHANGED: "taxon_substance_abundance_unchanged.csv",
}

#: The screens' own edge tables, and the source token each belongs to. Read for
#: the overlap number only; a missing file is an empty set, so a MASI-only run
#: reports "no primary source loaded to compare against" rather than "no
#: overlap", which are different findings.
SCREEN_TABLES: dict[str, tuple[str, str, str]] = {
    "drug_taxon_inhibited.csv": ("maier2018", "tax_id", "drug_id"),
    "drug_taxon_no_effect.csv": ("maier2018", "tax_id", "drug_id"),
    "taxon_drug_metabolised.csv": ("zimmermann2019", "tax_id", "drug_id"),
    "taxon_drug_not_metabolised.csv": ("zimmermann2019", "tax_id", "drug_id"),
}

EDGE_FIELDS = list(ms.INTERACTION_PROPERTY_TYPES)

SUBSTANCE_FIELDS = ["substance_id", *ms.SUBSTANCE_PROPERTY_TYPES]

#: The evidence contract in the order docs/model.md states it, then MASI's own
#: columns. The same shape ``prep_gutmdisorder.py`` writes, because it is the
#: same shared table.
ASSOCIATION_FIELDS = [
    "direction", "study_design", "evidence_level", "sequencing_type",
    "statistical_test", "group_0_size", "group_1_size", "pmid",
    "knowledge_level", "agent_type", "primary_source", "source_record_id",
    "source_licence", "source_relation",
    # Context, deliberately outside the audited contract.
    #
    # `study_id` is the **paper**, and it is filled rather than left null on
    # purpose. Every replication count in this project is
    # `count(DISTINCT r.study_id)` — D3, D10's `n_studies >= 2` clause, D17's
    # single-cohort report — and a null there counts as *zero* distinct
    # studies, so a MASI-only pair would drop out of the single-cohort
    # population while being exactly that. MASI has no study record of its own,
    # but each association cites one PMID and two associations citing one PMID
    # are one cohort, so the citation is the unit. No `Study` node is minted:
    # the export carries no title, journal or year to key one on.
    "study_id",
    # `condition_join` is on the **edge**, not on the `Disease` node, and the
    # reason is the same one that keeps a screen's `drug_class` off `Drug`:
    # `disease.csv` is shared and key-deduped, first row per `condition_id`
    # wins, so 631 of the MONDO ids MASI reaches were already written by
    # BugSigDB or gutMDisorder and a node column would read null for exactly the
    # edges it describes. The route a *source* took to a shared node is a fact
    # about that source's row, and it belongs where that row is.
    "condition_join",
    "masi_record_id", "masi_microbe_id", "microbiota_site", "association_type",
    "publications", "reported_name", "reported_rank", "original_rank",
    "reported_tax_id", "resolution_status", "taxon_id_route",
]

#: The same six-column shape ``unresolved_zimmermann2019.csv`` uses. C18's
#: accounting: every input row that becomes no edge, and every join that reached
#: something other than what it looks like it reached.
LEDGER_FIELDS = ["kind", "record_id", "subject", "detail", "reason", "source"]


def sheet_rows(path: Path) -> list[dict[str, str]]:
    """One workbook's only sheet as dicts, every cell a stripped string.

    Read with ``read_only=False`` for the reason the two screens' preps give: a
    stale dimension record makes the streaming reader return a one-cell sheet,
    and that failure looks like an empty table rather than an error. Numbers are
    stringified rather than kept — every id in these files is an accession or an
    NCBI taxid, and a ``float`` taxid formats as ``821.0``.
    """
    import openpyxl

    book = openpyxl.load_workbook(path, data_only=True)
    try:
        sheet = book[book.sheetnames[0]]
        rows = sheet.iter_rows(values_only=True)
        header = [str(c).strip() if c is not None else "" for c in next(rows)]
        out = []
        for row in rows:
            if all(c is None or str(c).strip() == "" for c in row):
                continue
            out.append({
                name: ("" if value is None else str(value).strip())
                for name, value in zip(header, row)
            })
        return out
    finally:
        book.close()


def value(row: dict[str, str], column: str) -> str:
    """A cell, with MASI's ``n.a.`` normalised to the empty string."""
    cell = row.get(column, "")
    return "" if ms.missing(cell) else cell


def screen_pairs(csv_dir: Path) -> dict[tuple[int, str], set[str]]:
    """``(tax_id, drug_id) -> {source tokens}`` over the loaded primary screens.

    Every cell of both screens, hit and measured non-hit alike, because the
    question ``duplicates_primary_source`` answers is "does this graph already
    carry a *measurement* of this pair", and a measured non-hit is one.
    """
    out: dict[tuple[int, str], set[str]] = defaultdict(set)
    for name, (source, tax_column, drug_column) in SCREEN_TABLES.items():
        path = csv_dir / name
        if not path.is_file():
            continue
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                tax_id, drug_id = row.get(tax_column, ""), row.get(drug_column, "")
                if tax_id.isdigit() and drug_id:
                    out[(int(tax_id), drug_id)].add(source)
    return out


def taxon_id_for(
    row_tax_id: str, entry: dict[str, str] | None
) -> tuple[int | None, str, str]:
    """``(tax_id, which column it came from, a disagreement note)``.

    Three sources of an id, in this order, and the order is a claim:

    1. **the record's own** ``Microbe-Tax-ID``. A source that puts an id on the
       row it is asserting is trusted for that row.
    2. **the microbe dictionary's** ``microbe_tax_id``. This is not a fallback
       worth skipping: the interaction table leaves the column ``n.a.`` on 4,965
       rows and ``microbesInfo`` recovers an id for 3,007 of them.
    3. **the dictionary's ``genus_id``**, for the 92 microbes it files under a
       genus with no id of their own — ``Blautia spp.``, ``Clostridium sp.``
       The claim is then made at the genus, which is what the dictionary says it
       knows, and ``taxon_id_route`` records that it was not the organism's own
       id.

    Where (1) and (2) disagree the record wins and the note is returned for the
    ledger. On the real file that is three microbes and 69 rows, and every one is
    the same shape: the record carries the **class** id and the dictionary the
    **phylum** id for a name NCBI spells identically at both ranks
    (*Bacteroidetes* 200643 against 976). Neither is wrong, and silently
    preferring one would make the graph's rank depend on which table was read
    first.
    """
    own = row_tax_id if row_tax_id.isdigit() else ""
    dictionary = (entry or {}).get("microbe_tax_id", "")
    dictionary = dictionary if dictionary.isdigit() else ""
    genus = (entry or {}).get("genus_id", "")
    genus = genus if genus.isdigit() else ""
    if own:
        note = (
            f"the record says {own} and microbesInfo says {dictionary}; the "
            f"record's own id is used"
            if dictionary and dictionary != own
            else ""
        )
        return int(own), "record", note
    if dictionary:
        return int(dictionary), "microbesinfo", ""
    if genus:
        return int(genus), "genus", ""
    return None, "none", ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", type=Path, default=Path("data/raw"))
    ap.add_argument("--tables", type=Path, default=None,
                    help=f"directory holding the four workbooks "
                         f"(default: <raw>/{RAW_SUBDIR}).")
    ap.add_argument("--taxdump", type=Path, default=None)
    ap.add_argument("--mondo", type=Path, default=None,
                    help="mondo.obo (default: <raw>/mondo/mondo.obo).")
    ap.add_argument("--out", type=Path, default=Path("data/csv"))
    ap.add_argument("--rank-ceiling", default="species",
                    help="Rank strains and subspecies are promoted to before "
                         "keying (C7). Ranks *above* it are untouched: MASI "
                         "curates at family, class and phylum and this source "
                         "declares no broadest-accepted rank.")
    args = ap.parse_args(argv)

    tables = args.tables or (args.raw / RAW_SUBDIR)
    missing_files = [n for n in WORKBOOKS.values() if not (tables / n).is_file()]
    if missing_files:
        # Exit 3, not 2 — "this source's raw files are not on this machine"
        # rather than "this script was called wrong", so an absent download
        # leaves the build without failing it.
        print(f"no MASI workbooks at {tables}: missing "
              f"{', '.join(missing_files)}", file=sys.stderr)
        return 3
    try:
        taxdump = args.taxdump or find_taxdump(args.raw)
    except FileNotFoundError as e:
        ap.error(str(e))

    out = args.out
    interactions = sheet_rows(tables / WORKBOOKS["interactions"])
    disease_rows = sheet_rows(tables / WORKBOOKS["diseases"])
    microbes = {r["microbe_id"]: r for r in sheet_rows(tables / WORKBOOKS["microbes"])}
    substances = {
        r["Substance_id"]: r for r in sheet_rows(tables / WORKBOOKS["substances"])
    }
    print(f"read {len(interactions):,} interaction records, "
          f"{len(disease_rows):,} disease associations, {len(microbes):,} microbes "
          f"and {len(substances):,} substances from {tables}")
    by_category = Counter(r["Interaction_Category"] for r in interactions)
    for category, n in by_category.most_common():
        print(f"  {category}: {n:,}")

    mondo_path = args.mondo or (args.raw / "mondo" / "mondo.obo")
    if mondo_path.is_file():
        print(f"loading MONDO from {mondo_path} ...", flush=True)
        mondo = MondoIndex.from_obo(mondo_path)
        print(f"  {len(mondo.label):,} live terms, "
              f"{len(mondo.by_exact_synonym):,} unambiguous exact synonyms",
              flush=True)
    else:
        mondo = MondoIndex()
        print(f"no mondo.obo at {mondo_path}; every disease keeps MASI's own id "
              f"as key and mondo_id will be null", flush=True)

    index = DrugIndex.from_csv(out / "drug.csv", exclude_source=SOURCE)
    print(f"drug.csv: {len(index.names):,} names this source may join to")
    measured = screen_pairs(out)
    print(f"primary screens on disk: {len(measured):,} measured (taxon, drug) pairs"
          if measured else
          "no primary screen tables on disk: the overlap is unmeasured, not zero")

    print(f"loading taxdump from {taxdump} ...", flush=True)
    idx = TaxonomyIndex.from_taxdump(taxdump)
    print(f"  {len(idx.parent):,} taxa, {len(idx.names):,} name keys", flush=True)

    # ------------------------------------------------------------- writers
    edges = {
        relationship: Writer(
            out / name, ["tax_id", "substance_id", *EDGE_FIELDS],
            dedupe_full=True, merge=True, owner=("primary_source", SOURCE),
        )
        for relationship, name in EDGE_TABLES.items()
    }
    substance_nodes = Writer(
        out / "substance.csv", SUBSTANCE_FIELDS,
        key="substance_id", merge=True, owner=("source", SOURCE),
    )
    condition_fields = ["condition_id", "label", "mondo_id", "mondo_label",
                        "source_id", "source_vocabulary", "source_condition"]
    diseases = Writer(
        out / "disease.csv", condition_fields, key="condition_id", merge=True
    )
    papers = Writer(
        out / "paper.csv", ["pmid", "title", "journal", "year", "doi"],
        key="pmid", merge=True,
    )
    assoc = Writer(
        out / "taxon_condition.csv",
        ["tax_id", "condition_id", "condition_type", *ASSOCIATION_FIELDS],
        dedupe_full=True, merge=True, owner=("primary_source", SOURCE),
    )
    probiotics = Writer(
        out / "taxon_probiotic.csv",
        ["tax_id", *ms.TAXON_PROBIOTIC_PROPERTIES, "source"],
        key="tax_id", merge=True, owner=("source", SOURCE),
    )
    #: tax_id -> the probiotic annotation, **merged rather than first-wins**.
    #: 806 microbe rows collapse onto 540 taxa, so several MASI organisms land
    #: on one node — *Escherichia coli* Nissle 1917 promotes onto the same 562
    #: as plain *Escherichia coli*. `Writer`'s first-row-per-key rule would then
    #: let whichever row came first decide, and it silently dropped 5 of the 46
    #: probiotic claims that way. A claim beats a non-claim: `probiotic` is true
    #: if *any* MASI row for the taxon says so, and `probiotic_reported_name`
    #: keeps every name the claim was made under.
    probiotic_claims: "OrderedDict[int, dict[str, object]]" = OrderedDict()
    unresolved_nodes = Writer(
        out / "unresolved_taxa.csv",
        ["unresolved_id", "raw_name", "reported_rank", "original_rank",
         "reported_tax_id", "source", "status", "candidates", "note",
         "n_signatures"],
        key="unresolved_id", merge=True, owner=("source", SOURCE),
    )
    ledger = Writer(
        out / f"unresolved_{SOURCE}.csv", LEDGER_FIELDS,
        # Deduplicated on the whole row: a disease MONDO does not name is one
        # finding, not the 30 identical rows its 30 associations would each
        # write. How many *records* each finding cost is a counter in the
        # report, which is where a count belongs.
        dedupe_full=True, merge=True, owner=("source", SOURCE),
    )
    cited = Writer(
        out / "cited_taxa.csv", ["tax_id", "source", "n_signatures"],
        key=("tax_id", "source"), merge=True, owner=("source", SOURCE),
    )

    def note(kind: str, record_id: str, subject: str, detail: str, why: str) -> None:
        ledger.add({"kind": kind, "record_id": record_id, "subject": subject,
                    "detail": detail, "reason": why, "source": SOURCE})

    licence = ont.SOURCE_LICENCE.get(SOURCE, "")
    knowledge = ont.knowledge_level(SOURCE)
    agent = ont.agent_type(SOURCE)
    aggregator = f"PMID:{ms.PUBMED_ID}"

    # ---------------------------------------------------------- the substances
    #: MASI substance id -> ``(drug_id, join route)``. Every one of the 1,350
    #: becomes a ``Substance`` node whether or not it reaches a ``Drug``; the
    #: node is MASI's dictionary, and the ``Drug`` is a separate identity.
    substance_join: dict[str, tuple[str, str]] = {}
    join_routes: Counter[str] = Counter()
    for sid, row in sorted(substances.items()):
        name = row.get("Substance_name", "").strip()
        category = value(row, "Substance_category")
        subcategory = value(row, "Substance_subcategory")
        if ms.is_class_substance(subcategory):
            drug_id, route, others = "", "class-not-compound", []
            note("substance", sid, name, subcategory,
                 "MASI's own subcategory files this as a class of compounds, "
                 "not a compound: joining it to one molecule is the level-4-ATC "
                 "error microbiomekg.drugs refuses")
        else:
            drug_id, route, others = join_drug(ms.substance_variants(name), index)
            if route == "minted":
                # `join_drug` says "minted" because both screens mint a node
                # when nothing matches. This source never does: an unmatched
                # substance is a `Substance` node with no `SAME_COMPOUND_AS`
                # edge, and calling that "minted" would read as a new `Drug`.
                route = "no-drug-node"
        if others:
            note("substance", sid, name, f"{route} -> {drug_id}; also "
                 f"{','.join(others)}",
                 "two join routes reached different Drug nodes; the route MASI's "
                 "own spelling took wins")
        if drug_id and "therapeutic" not in category.casefold():
            # Countable rather than forbidden. `Nicotine` and `Permethrin` are
            # the same molecules ChEMBL holds, and refusing the join would give
            # MASI a second node for a compound this graph already keys — but a
            # dietary category reaching a drug node is worth being able to
            # count, because that is where a false merge would appear first.
            note("substance", sid, name, f"{category} -> {drug_id}",
                 "a substance with no therapeutic category reached a Drug node "
                 "by name")
        join_routes[route] += 1
        substance_join[sid] = (drug_id, route)
        substance_nodes.add({
            "substance_id": ms.substance_key(sid),
            "name": name,
            "substance_category": category,
            "substance_subcategory": subcategory,
            "therapeutic_class": value(row, "Therapeutic_class"),
            "product_company": value(row, "Product_company"),
            "molecular_formula": value(row, "Molecular_formula"),
            "iupac_name": value(row, "iupacname"),
            "inchikey": value(row, "inchikey"),
            "cas": value(row, "cas_no"),
            "drugbank_id": value(row, "id_drugbank"),
            "pharmgkb_id": value(row, "id_pharmgkb"),
            "kegg_id": value(row, "id_kegg"),
            "ttd_id": value(row, "id_ttd"),
            "pubchem_cid": value(row, "id_pubchem"),
            "chemspider_id": value(row, "id_chemspider"),
            "npass_id": value(row, "id_npass"),
            "synonyms": value(row, "synonyms"),
            "drug_id": drug_id,
            "drug_join": route,
            "source": SOURCE,
            "source_licence": licence,
        })

    # ----------------------------------------------------------- the microbes
    #: ``(MASI microbe id, the record's own tax id cell)`` -> what it resolved
    #: to. Keyed on both because the record's id wins over the dictionary's and
    #: three microbes carry two different ids across their rows.
    resolved: dict[tuple[str, str], dict] = {}
    resolutions: Counter[str] = Counter()
    id_routes: Counter[str] = Counter()
    unresolved_hits: Counter[str] = Counter()

    def resolve_microbe(microbe_id: str, row_tax_id: str) -> dict:
        key = (microbe_id, row_tax_id)
        if key in resolved:
            return resolved[key]
        entry = microbes.get(microbe_id)
        if entry is None:
            note("microbe", microbe_id, row_tax_id, "",
                 "an interaction record names a microbe with no microbesInfo "
                 "row: no rank, no genus fallback and no probiotic annotation")
        tax_id, route, disagreement = taxon_id_for(row_tax_id, entry)
        if disagreement:
            note("microbe", microbe_id, (entry or {}).get("microbe_name", ""),
                 row_tax_id, disagreement)
        id_routes[route] += 1
        reported_rank = (entry or {}).get(ms.REPORTED_RANK_COLUMN, "")
        reported_rank = "" if ms.missing(reported_rank) else reported_rank.casefold()
        if route == "genus":
            # The dictionary knows the genus and not the organism, so the claim
            # is made at the genus and the rank on the edge says so rather than
            # repeating the species-level rank the dictionary asserts.
            reported_rank = "genus"
        out_entry = {
            "tax_id": None, "route": route, "reported_rank": reported_rank,
            "original_rank": "", "resolution_status": "", "reported_tax_id": "",
        }
        if tax_id is None:
            resolutions["no-taxid"] += 1
            out_entry["resolution_status"] = "unresolved"
            resolved[key] = out_entry
            return out_entry
        res = idx.resolve(tax_id=tax_id, rank_ceiling=args.rank_ceiling)
        resolutions[res.status] += 1
        out_entry.update({
            "tax_id": res.tax_id,
            "original_rank": res.original_rank or "",
            "resolution_status": res.status,
            "reported_tax_id": str(tax_id),
        })
        if res.tax_id is None:
            out_entry["note"] = res.note
        resolved[key] = out_entry
        return out_entry

    def tombstone(microbe_id: str, entry: dict, raw_name: str) -> str:
        """An ``UnresolvedTaxon`` for a microbe that reached no NCBI id.

        MASI's own accession is the key rather than the name, because 24 of its
        microbe ids are written under more than one spelling across the file
        (``Clostridioides difficile`` / ``Clostridium difficile`` /
        ``Peptoclostridium difficile`` are one id) and a name-keyed tombstone
        would split one refusal into three.
        """
        uid = f"unresolved:{SOURCE}:{microbe_id.casefold()}"
        unresolved_nodes.add({
            "unresolved_id": uid, "raw_name": raw_name or microbe_id,
            "reported_rank": entry["reported_rank"],
            "original_rank": entry["original_rank"],
            "reported_tax_id": entry["reported_tax_id"],
            "source": SOURCE, "status": entry["resolution_status"] or "unresolved",
            "candidates": "", "note": entry.get("note", "")
            or "MASI records no NCBI taxid for this microbe and its dictionary "
               "row carries neither an id nor a genus id",
            "n_signatures": "0",
        })
        unresolved_hits[uid] += 1
        return uid

    # ------------------------------------------------------- the interactions
    counters: Counter[str] = Counter()
    per_relation: Counter[str] = Counter()
    levels: Counter[str] = Counter()
    duplicated: Counter[str] = Counter()
    taxa_seen: "OrderedDict[int, int]" = OrderedDict()
    record_ids: set[str] = set()

    for row in interactions:
        counters["rows"] += 1
        category = row.get("Interaction_Category", "").strip()
        record_id = row.get("Interation_Record_ID", "").strip()
        microbe_id = row.get("MASI-Microbe-ID", "").strip()
        substance_id = row.get("MASI-Substance-chemicalD", "").strip()
        if category not in ms.CATEGORIES:
            counters["unknown_category"] += 1
            note("record", record_id, category, f"{microbe_id}|{substance_id}",
                 "an Interaction_Category this loader has not read: its "
                 "direction is unknown and guessing one would be MASI's error "
                 "becoming ours")
            continue
        if substance_id not in substances:
            counters["unknown_substance"] += 1
            note("record", record_id, substance_id, "",
                 "an interaction record names a substance with no substanceInfo "
                 "row")
            continue

        if category == ms.CATEGORY_METABOLISM:
            relationship = ms.relation_for_metabolism(
                row.get("Metabolism_Effect_on_Drug")
            )
            effect = ms.SOURCE_RELATIONS[relationship][0]
            direction = ""
        else:
            relationship = ms.relation_for_abundance(row.get("Microbe_Change"))
            if relationship is None:
                counters["untypable_change"] += 1
                note("record", record_id, row.get("Microbe_Change", ""),
                     f"{microbe_id}|{substance_id}",
                     "a Microbe_Change this model has no direction for: filing "
                     "it as a decrease would invent a sign and filing it as no "
                     "change would invert one")
                continue
            direction = ms.direction_of(row.get("Microbe_Change"))
            effect = direction or ms.SOURCE_RELATIONS[relationship][0]

        entry = resolve_microbe(microbe_id, row.get("Microbe-Tax-ID", "").strip())
        reported_name = row.get("Microbe-Name", "").strip()
        if entry["tax_id"] is None:
            counters["unresolved_microbe"] += 1
            tombstone(microbe_id, entry, reported_name)
            continue

        drug_id, drug_route = substance_join[substance_id]
        counters["on_a_drug_compound" if drug_id else "on_a_masi_only_compound"] += 1
        counters[f"taxid_from_{entry['route']}"] += 1
        pair_sources = sorted(measured.get((entry["tax_id"], drug_id), ())) if drug_id \
            else []
        if pair_sources:
            duplicated["|".join(pair_sources)] += 1

        publications, pmid = ms.publications_of(
            row.get("Reference_ID_Type"), row.get("Reference_ID")
        )
        if not publications:
            counters["no_reference"] += 1
            note("record", record_id, row.get("Reference_ID", ""),
                 f"{microbe_id}|{substance_id}",
                 "no PMID or DOI could be parsed out of the reference cell")
        level = ms.evidence_level_for(
            row.get("Experiment_System"), row.get("Experiment_Model_Species")
        )
        levels[level] += 1
        source_record_id = f"{SOURCE}:{record_id}|{microbe_id}|{substance_id}"
        if source_record_id in record_ids:
            counters["repeated_record_key"] += 1
            note("record", record_id, source_record_id, "",
                 "two rows share a (record, microbe, substance) key; the second "
                 "is a duplicate row rather than a second observation")
        record_ids.add(source_record_id)

        taxa_seen[entry["tax_id"]] = taxa_seen.get(entry["tax_id"], 0) + 1
        per_relation[relationship] += 1
        counters["edges"] += 1
        edges[relationship].add({
            "tax_id": str(entry["tax_id"]),
            "substance_id": ms.substance_key(substance_id),
            "effect": effect,
            "evidence_level": level,
            "knowledge_level": knowledge,
            "agent_type": agent,
            "primary_source": SOURCE,
            "source_record_id": source_record_id,
            "source_licence": licence,
            "source_relation": ms.SOURCE_RELATIONS[relationship][1],
            "publications": as_list(publications),
            "pmid": str(pmid) if pmid else "",
            "aggregator_publication": aggregator,
            "duplicates_primary_source": as_list(pair_sources),
            "direction": direction,
            "interaction_category": category,
            "masi_record_id": record_id,
            "masi_substance_id": substance_id,
            "substance_name": row.get("Substance-Name", "").strip(),
            "substance_category": value(row, "Substance-Category"),
            "substance_subcategory": value(row, "Substance-subCategory"),
            "drug_join": drug_route,
            "substance_exposure_details": value(row, "Substance_Exposure_Details"),
            "masi_microbe_id": microbe_id,
            "reported_name": reported_name,
            "reported_tax_id": entry["reported_tax_id"],
            "reported_rank": entry["reported_rank"],
            "original_rank": entry["original_rank"],
            "resolution_status": entry["resolution_status"],
            "taxon_id_route": entry["route"],
            "microbiota_site": value(row, "Microbiota_Site"),
            "experiment_system": value(row, "Experiment_System"),
            "experiment_model_species": value(row, "Experiment_Model_Species"),
            "model_condition": value(row, "Model_Condition/Disease"),
            "outcome": value(row, "Outcome"),
            "metabolites": value(row, "Metabolites"),
            "metabolism_type": value(row, "Metabolism_Type"),
            "metabolism_enzymes": value(row, "Metabolism_Enzymes"),
            "metabolism_effect_on_drug": value(row, "Metabolism_Effect_on_Drug"),
            "metabolism_mechanism": value(row, "Metabolism_Mechanism"),
            "microbe_change": value(row, "Microbe_Change"),
            "microbe_change_statistics": value(row, "Microbe_Change_Statistics"),
        })

    # ---------------------------------------------------------- the diseases
    condition_routes: Counter[str] = Counter()
    disease_counters: Counter[str] = Counter()
    for row in disease_rows:
        disease_counters["rows"] += 1
        record_id = row.get("Association-record-ID", "").strip()
        microbe_id = row.get("MASI-Microbe-ID", "").strip()
        disease_id = row.get("MASI-Disease-ID", "").strip()
        label = row.get("Disease-name", "").strip()
        direction = ms.direction_of(row.get("Change-of-microbe"))
        if not direction:
            disease_counters["untypable_change"] += 1
            note("association", record_id, row.get("Change-of-microbe", ""),
                 f"{microbe_id}|{disease_id}",
                 "a Change-of-microbe this model has no direction for")
            continue
        entry = resolve_microbe(microbe_id, row.get("Microbe-Tax-ID", "").strip())
        reported_name = row.get("Microbe-name", "").strip()
        if entry["tax_id"] is None:
            disease_counters["unresolved_microbe"] += 1
            tombstone(microbe_id, entry, reported_name)
            continue

        hub, route = mondo.mondo_by_name(ms.normalise_disease_name(label))
        condition_routes[route] += 1
        if hub is None:
            disease_counters["no_mondo"] += 1
            note("disease", disease_id, label, "",
                 "no live MONDO term carries this label as its name or as an "
                 "exact synonym; the disease keeps MASI's own id as key and "
                 "mondo_id is null")
        node = hub or ms.disease_key(disease_id)
        diseases.add({
            "condition_id": node,
            "label": mondo.label.get(hub or "") or label,
            "mondo_id": hub or "",
            "mondo_label": mondo.label.get(hub or "") or "",
            "source_id": ms.disease_key(disease_id),
            "source_vocabulary": "MASI",
            "source_condition": label,
        })
        publications, pmid = ms.publications_of(
            row.get("Reference-type"), row.get("Reference-ID")
        )
        if pmid:
            papers.add({"pmid": str(pmid), "title": "", "journal": "",
                        "year": "", "doi": ""})
        else:
            disease_counters["no_pmid"] += 1
            note("association", record_id, row.get("Reference-ID", ""), "",
                 "no PMID could be parsed out of the reference cell")
        taxa_seen[entry["tax_id"]] = taxa_seen.get(entry["tax_id"], 0) + 1
        disease_counters["edges"] += 1
        assoc.add({
            "tax_id": str(entry["tax_id"]),
            "condition_id": node,
            # The blueprint's `target_type_column`. MASI's disease export is
            # disease-coded throughout, and the column says so per row rather
            # than the loader inferring it.
            "condition_type": "Disease",
            "direction": direction,
            # The six the export has no column for. Left empty rather than
            # filled with a plausible string: `Association-type` is a curation
            # category ("Microbe abundance associates with disease"), not a
            # study design, and writing it into `study_design` would improve the
            # audit number by misdescribing the data — the same call
            # gutMDisorder's `Research Type` gets.
            "study_design": "", "sequencing_type": "", "statistical_test": "",
            "group_0_size": "", "group_1_size": "",
            "evidence_level": ms.DISEASE_EVIDENCE_LEVEL,
            "pmid": str(pmid) if pmid else "",
            "knowledge_level": knowledge,
            "agent_type": agent,
            "primary_source": SOURCE,
            "source_record_id": f"{SOURCE}:{record_id}",
            "source_licence": licence,
            "source_relation": f"microbe abundance {direction} in this disease",
            "study_id": f"{SOURCE}:pmid:{pmid}" if pmid else f"{SOURCE}:{record_id}",
            "condition_join": route,
            "masi_record_id": record_id,
            "masi_microbe_id": microbe_id,
            "microbiota_site": value(row, "Microbiota-site"),
            "association_type": row.get("Association-type", "").strip(),
            "publications": as_list(publications),
            "reported_name": reported_name,
            "reported_rank": entry["reported_rank"],
            "original_rank": entry["original_rank"],
            "reported_tax_id": entry["reported_tax_id"],
            "resolution_status": entry["resolution_status"],
            "taxon_id_route": entry["route"],
        })

    # --------------------------------------------------------- the probiotics
    probiotic_rows = 0
    promoted_probiotics = 0
    for microbe_id, entry in sorted(microbes.items()):
        resolution = resolve_microbe(microbe_id, entry.get("microbe_tax_id", ""))
        if resolution["tax_id"] is None:
            continue
        is_probiotic = entry.get("if_probiotic", "").strip() == "Yes"
        if is_probiotic and resolution["resolution_status"] == "promoted":
            promoted_probiotics += 1
            note("probiotic", microbe_id, entry.get("microbe_name", ""),
                 f"{resolution['reported_tax_id']} -> {resolution['tax_id']}",
                 "a probiotic MASI names below the species rank; the flag lands "
                 "on the species and probiotic_reported_name keeps the claim's "
                 "own subject")
        name = entry.get("microbe_name", "").strip()
        held = probiotic_claims.setdefault(
            resolution["tax_id"],
            {"probiotic": False, "use": [], "stage": [], "names": []},
        )
        if is_probiotic:
            if not held["probiotic"]:
                # Only a probiotic row contributes a name: recording every
                # organism that collapsed onto the taxon would make
                # `probiotic_reported_name` a list of organisms the claim was
                # *not* made about.
                held["names"] = []
            held["probiotic"] = True
            for column, key in (("probiotic_use_species", "use"),
                                ("probiotic_research_stage", "stage")):
                cell = value(entry, column)
                if cell and cell not in held[key]:
                    held[key].append(cell)
            if name and name not in held["names"]:
                held["names"].append(name)
        elif not held["probiotic"] and name and name not in held["names"]:
            held["names"].append(name)

    for tax_id, held in probiotic_claims.items():
        probiotic_rows += probiotics.add({
            "tax_id": str(tax_id),
            "probiotic": "true" if held["probiotic"] else "false",
            "probiotic_use_species": as_list(held["use"]),
            "probiotic_research_stage": as_list(held["stage"]),
            "probiotic_reported_name": as_list(held["names"]),
            "source": SOURCE,
        })

    for row in unresolved_nodes.rows:
        if row["source"] == SOURCE:
            row["n_signatures"] = str(unresolved_hits.get(row["unresolved_id"], 0))
    for tax_id, n in sorted(taxa_seen.items()):
        cited.add({"tax_id": str(tax_id), "source": SOURCE, "n_signatures": str(n)})

    written = (*edges.values(), substance_nodes, diseases, papers, assoc,
               probiotics, unresolved_nodes, ledger, cited)
    counts = {w.path.name: w.flush() for w in written}

    # -------------------------------------------------------------- the report
    print(f"\nread {counters['rows']:,} interaction records -> "
          f"{counters['edges']:,} edges over {len(taxa_seen):,} taxa and "
          f"{len(substances):,} substances")
    print("  by relationship: " + ", ".join(
        f"{rel} {per_relation[rel]:,}"
        for rel in (*ms.METABOLISM_RELATIONSHIPS, *ms.ABUNDANCE_RELATIONSHIPS)))
    print(f"  curated non-effects kept as their own relationship: "
          f"{per_relation[ms.RELATION_NO_METABOLISM]:,} + "
          f"{per_relation[ms.RELATION_ABUNDANCE_UNCHANGED]:,}")
    print("  evidence_level: " + ", ".join(
        f"{lvl} {n:,}" for lvl, n in levels.most_common()))
    total_dup = sum(duplicated.values())
    print(f"  AGGREGATOR OVERLAP: {total_dup:,} of {counters['edges']:,} edges "
          f"({100 * total_dup / max(counters['edges'], 1):.1f}%) restate a "
          f"(taxon, compound) pair a loaded primary source already measures"
          + ("" if not duplicated else " — " + ", ".join(
              f"{src} {n:,}" for src, n in duplicated.most_common())))
    print(f"  {counters['on_a_drug_compound']:,} edges land on a substance this "
          f"graph also has a Drug node for (reachable as "
          f"(:Substance)-[:{ms.RELATION_SAME_COMPOUND}]->(:Drug)); "
          f"{counters['on_a_masi_only_compound']:,} on a compound only MASI "
          f"carries")
    print(f"  substance join, over the {len(substances):,} substances: " + ", ".join(
        f"{r} {n:,}" for r, n in join_routes.most_common()))
    # Per distinct ``(microbe id, the tax id the row carried)`` pair rather than
    # per microbe: three microbes are written with two different ids across the
    # file, and the disease table and the microbe dictionary are resolved
    # through the same cache, so this total is above 806 by design.
    print("  taxon id from, per resolved microbe key: " + ", ".join(
        f"{r} {n:,}" for r, n in id_routes.most_common()))
    print("  taxon id from, per edge: " + ", ".join(
        f"{key.removeprefix('taxid_from_')} {n:,}"
        for key, n in counters.most_common() if key.startswith("taxid_from_")))
    print("  organism resolution: " + ", ".join(
        f"{s} {n:,}" for s, n in resolutions.most_common()))
    print(f"  not loaded: {counters['unresolved_microbe']:,} records on a microbe "
          f"that reached no taxon, {counters['untypable_change']:,} with a "
          f"Microbe_Change this model has no direction for, "
          f"{counters['unknown_category']:,} in an unread category, "
          f"{counters['unknown_substance']:,} naming an unknown substance")
    print(f"\n{disease_counters['rows']:,} disease associations -> "
          f"{disease_counters['edges']:,} ASSOCIATED_WITH edges")
    print("  disease id: " + ", ".join(
        f"{r} {n:,}" for r, n in condition_routes.most_common()))
    print(f"  {disease_counters['no_mondo']:,} associations on a disease no MONDO "
          f"term names; those keep MASI's own id as key")
    print(f"  every one fills 8 of the contract's 14 properties: the export has "
          f"no design, host, sequencing, test or arm-size column")
    claimed = sum(1 for held in probiotic_claims.values() if held["probiotic"])
    named = sum(
        1 for entry in microbes.values()
        if entry.get("if_probiotic", "").strip() == "Yes"
    )
    print(f"\n{probiotic_rows:,} taxa carry MASI's probiotic annotation: "
          f"{claimed} probiotic, {probiotic_rows - claimed} curated and not "
          f"marked as one, and null on every taxon MASI does not cover")
    print(f"  MASI marks {named} microbes as probiotics; {named - claimed} of "
          f"them share a taxon with another after promotion or reach none at "
          f"all, and {promoted_probiotics} of them are named below the species "
          f"rank")
    for name, n in counts.items():
        print(f"  {name:38s} {n:>9,}")
    shared = {w.path.name: w.merged_in for w in written if w.merged_in}
    if shared:
        print("  merged into tables another source had written: " + ", ".join(
            f"{name} +{n:,}" for name, n in shared.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

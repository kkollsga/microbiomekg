#!/usr/bin/env python3
"""Maier 2018's 1,197 x 40 growth screen -> the drug->taxon edges D8 was missing.

``data/raw/drug_screens/maier2018/`` holds the six supplementary workbooks of
Maier et al., *Nature* 555:623-628 (2018), PMID 29555994, extracted from Europe
PMC's supplementary bundle for PMC6108420. Four of them are read here:

* ``Supplementary_table_3.xlsx`` sheet ``S3a. Adjusted p-values`` — **the
  screen**: 1,197 drugs down, 40 gut isolates across, one adjusted p-value per
  cell, plus each drug's ``drug_class`` and its published ``n_hit``. This is the
  table every edge comes from.
* ``Supplementary_table_2.xlsx`` sheet ``S2. Species selection`` — the isolate
  dictionary: ``NT`` code to species, strain designation, culture-collection
  number and Gram stain.
* ``Supplementary_table_1.xlsx`` sheet ``S1a. Prestwick_Libery`` — the drug
  dictionary: catalogue name, STITCH4 id (a PubChem CID), ATC codes and what
  the drug targets.
* ``Supplementary_table_4.xlsx`` sheet ``S4. MICs`` — the dose-response
  follow-up on 379 of the 47,880 pairs, carrying an IC25, an MIC, their
  qualifiers, and the authors' own TP/TN/FP/FN call against the screen.

What comes out:

* every cell with ``adjusted p < 0.01`` -> ``INHIBITS_GROWTH_OF``, in
  ``drug_taxon_inhibited.csv`` — **5,592**;
* every cell at or above it -> ``DOES_NOT_INHIBIT_GROWTH_OF``, in
  ``drug_taxon_no_effect.csv`` — **42,233**. A screen measures the whole matrix,
  so a non-hit here is a measurement and not an absence of curation, and it is
  its own relationship rather than a flag for the reason NJC19's
  ``NO_EXCHANGE_WITH`` is: nothing in a ``MATCH (d)-[:INHIBITS_GROWTH_OF]->(t)``
  would say it had been silently including refutations;
* the 55 cells the sheet writes as the literal ``NA`` -> ledger rows. A pair the
  screen did not measure is neither a hit nor a non-hit;
* a drug no ChEMBL join route reaches -> a ``Drug`` node keyed on its Prestwick
  catalogue number, ``approved = false``, ``source = maier2018``. **355 of the
  1,197**; the other 842 join by name (455), by a level-5 ATC code (361) or by
  the name with a salt suffix removed (26). The library's 1,197 entries reach
  1,197 distinct ``Drug`` nodes — one each, no false merge — because an ATC code
  two library entries claim identifies neither (:func:`contested_atc_codes`).

**The hit threshold is derived, and the derivation is the interesting part.**
The sheet publishes p-values and an ``n_hit`` count and never states the cutoff.
``ontology.maier2018.HIT_THRESHOLD`` reproduces ``n_hit`` on all 1,197 rows
(0.05 reproduces 791, 0.001 reproduces 879), the per-species human-targeted hit
counts in both figure source-data workbooks, and the paper's own "24% of the
drugs with human targets". This script re-checks the ``n_hit`` half on every run
and refuses to write if it stops holding — the constant decides the *type* of
every edge in the source, so a silent drift in it is a silent inversion of the
whole layer.

**The figure source data in ``data/raw/maier2018/`` is deliberately not loaded**,
and one of its sheets is the reason to say so out loud. ``MOESM15`` sheet ``3c``
is a drug x isolate table with a concentration and a qualifier, and it reads
exactly like a hit list — but **all 29 of its drugs have ``n_hit = 0`` in the
screen, and none of its 212 pairs is a hit**. Loading it as inhibition would
have written 212 edges the same paper's own p-value matrix contradicts. The two
sheets that *are* usable (``MOESM13`` ``1c`` and ``MOESM16`` ``5a``, per-species
hit counts) are aggregates of ``S3a`` and are used as cross-checks of the
threshold rather than as rows.
"""

from __future__ import annotations

from collections import Counter, OrderedDict
from pathlib import Path

from microbiomekg import ontology as ont
from microbiomekg.drugs import DrugIndex, atc_level5, join_drug
from microbiomekg.ontology import maier2018 as mz
from microbiomekg.rawdata import MissingInput, find_taxdump
from microbiomekg.reconcile import TaxonomyIndex, rank_depth
from microbiomekg.tables import Frames, as_list

SOURCE = mz.SOURCE

#: Reads ``drug.csv``, which ChEMBL writes: the three join routes each need to
#: see every ``Drug`` node that already exists before this source decides to
#: mint one, and ChEMBL is the only other source that writes that table.
#: The raw files this prep reads, relative to ``--raw``, in the layout
#: ``fetch`` writes. `status` reports on exactly these.
RAW_INPUTS: list[str] = [
    "drug_screens/maier2018/NIHMS76168-supplement-Supplementary_table_1.xlsx",
    "drug_screens/maier2018/NIHMS76168-supplement-Supplementary_table_2.xlsx",
    "drug_screens/maier2018/NIHMS76168-supplement-Supplementary_table_3.xlsx",
    "drug_screens/maier2018/NIHMS76168-supplement-Supplementary_table_4.xlsx",
]

DEPENDS_ON: list[str] = ["chembl"]

#: ``<table number>: (filename, sheet)``. Named rather than "the first sheet" so
#: a re-extraction that reorders a workbook fails loudly instead of reading the
#: wrong table.
WORKBOOKS: dict[int, tuple[str, str]] = {
    1: ("NIHMS76168-supplement-Supplementary_table_1.xlsx", "S1a. Prestwick_Libery"),
    2: ("NIHMS76168-supplement-Supplementary_table_2.xlsx", "S2. Species selection"),
    3: ("NIHMS76168-supplement-Supplementary_table_3.xlsx", "S3a. Adjusted p-values"),
    4: ("NIHMS76168-supplement-Supplementary_table_4.xlsx", "S4. MICs"),
}

#: Where ``fetch.py`` puts the bundle. The screen sits under ``drug_screens/``
#: beside Zimmermann 2019 rather than in a directory of its own, because the two
#: are the pair Part B's W7 names and neither is the whole answer alone.
RAW_SUBDIR = Path("drug_screens") / SOURCE

#: Supplementary table 2 opens with a title line and a blank, and interleaves
#: two sub-headings (``Additional Bacteroides``, ``Laboratory E. coli
#: strains``) among its data rows. The header is found by its first cell rather
#: than by a fixed skip, and a row whose ``Species`` cell is empty is a
#: sub-heading, not an isolate.
SPECIES_HEADER_CELL = "NT data base"

EDGE_FIELDS = [
    "effect",
    "evidence_level",
    "knowledge_level",
    "agent_type",
    "primary_source",
    "source_record_id",
    "source_licence",
    "source_relation",
    "publications",
    "pmid",
    "adjusted_p_value",
    "screen_concentration_um",
    "prestwick_id",
    "reported_drug_name",
    "drug_class",
    "drug_join",
    "nt_code",
    "reported_name",
    "strain",
    "gram_stain",
    "reported_rank",
    "original_rank",
    "resolution_status",
    "taxon_join",
    "ic25_um",
    "ic25_qualifier",
    "mic_um",
    "mic_qualifier",
    "validation_outcome",
]

DRUG_FIELDS = [
    "drug_id",
    "chembl_id",
    "pref_name",
    "molecule_type",
    "max_phase",
    "first_approval",
    "atc_codes",
    "approved",
    "withdrawn",
    "therapeutic",
    "oral",
    "parenteral",
    "topical",
    "smiles",
    "salt_form",
    "salt_ids",
    "source",
    "source_licence",
    "chembl_release",
    "prestwick_id",
    "pubchem_cid",
    "screen_drug_class",
    "screen_target_species",
]

#: The same shape ``unresolved_chembl.csv`` uses. C18's accounting lives here:
#: every input cell that becomes no edge, and every drug or isolate that reached
#: something other than what it looks like it reached.
LEDGER_FIELDS = ["kind", "record_id", "subject", "detail", "reason", "source"]


def sheet_rows(path: Path, sheet: str) -> list[tuple]:
    """Every row of one named sheet, as tuples.

    Read with ``read_only=False``: three of these workbooks carry a stale
    dimension record (``A1:A1``) that the read-only reader believes, so a
    streaming read silently returns a one-cell sheet. That failure looks like an
    empty table rather than an error, which is why the whole workbook is loaded.
    """
    import openpyxl

    book = openpyxl.load_workbook(path, data_only=True)
    try:
        if sheet not in book.sheetnames:
            raise SystemExit(
                f"{path} has no sheet named {sheet!r} "
                f"(found {', '.join(book.sheetnames)})"
            )
        return list(book[sheet].iter_rows(values_only=True))
    finally:
        book.close()


def as_float(value) -> float | None:
    """A cell as a float, or ``None`` for the literal ``NA`` and for a blank.

    The screen writes ``NA`` in 55 of its 47,880 cells and openpyxl hands it
    back as a string; ``float("NA")`` raises, and a bare ``try`` around the
    whole row would have swallowed a genuinely malformed p-value with it.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_drugs(path: Path) -> dict[str, dict]:
    """``prestwick_ID -> the supplementary-table-1 row``, as a plain dict."""
    rows = sheet_rows(path, WORKBOOKS[1][1])
    header = [str(c or "").strip() for c in rows[0]]
    out: dict[str, dict] = {}
    for row in rows[1:]:
        record = dict(zip(header, row))
        key = str(record.get("prestwick_ID") or "").strip()
        if key:
            out[key] = record
    return out


def read_species(path: Path) -> dict[str, dict]:
    """``NT code -> {species, strain, source, gram_stain}`` from table 2.

    A row with an ``NT`` code and no ``Species`` is one of the two laboratory
    *E. coli* constructs (``NT5084`` wild type, ``NT5085`` the tolC deletion)
    that only the table-6 screen used; they carry no organism name here and none
    of the 40 screened columns is one of them, so they are simply absent from
    the returned map.
    """
    rows = sheet_rows(path, WORKBOOKS[2][1])
    start = next(
        (
            i
            for i, row in enumerate(rows)
            if any(isinstance(c, str) and c.strip() == SPECIES_HEADER_CELL for c in row)
        ),
        None,
    )
    if start is None:
        raise SystemExit(f"{path}: no header row containing {SPECIES_HEADER_CELL!r}")
    header = [str(c or "").strip() for c in rows[start]]
    out: dict[str, dict] = {}
    for row in rows[start + 1 :]:
        record = dict(zip(header, row))
        code = str(record.get("NT data base") or "").strip()
        species = str(record.get("Species") or "").strip()
        if not code.startswith("NT") or not species:
            continue
        out[code] = {
            "species": species,
            "strain": str(record.get("Strain") or "").strip(),
            "collection": str(record.get("Source") or "").strip(),
            "gram_stain": str(record.get("Gram stain") or "").strip(),
        }
    return out


def read_validation(path: Path) -> dict[tuple[str, str], dict]:
    """``(prestwick_ID, NT code) -> the supplementary-table-4 follow-up row``."""
    rows = sheet_rows(path, WORKBOOKS[4][1])
    header = [str(c or "").strip() for c in rows[0]]
    out: dict[tuple[str, str], dict] = {}
    for row in rows[1:]:
        record = dict(zip(header, row))
        key = (
            str(record.get("prestwick_ID") or "").strip(),
            str(record.get("NT_code") or "").strip(),
        )
        if all(key):
            out[key] = record
    return out


def read_screen(path: Path) -> tuple[list[str], list[dict]]:
    """``(NT codes in column order, one dict per drug row)`` from table 3.

    The species columns are found by :func:`ontology.maier2018.nt_code_of`
    rather than by counting the four metadata columns, so a release that adds a
    metadata column shifts nothing.
    """
    rows = sheet_rows(path, WORKBOOKS[3][1])
    header = [str(c or "").strip() for c in rows[0]]
    codes = [mz.nt_code_of(c) for c in header]
    species_at = [i for i, code in enumerate(codes) if code]
    if not species_at:
        raise SystemExit(f"{path}: no column header names an NT code")
    index = {name: i for i, name in enumerate(header)}
    out: list[dict] = []
    for row in rows[1:]:
        prestwick = str(row[index["prestwick_ID"]] or "").strip()
        if not prestwick:
            continue
        out.append(
            {
                "prestwick_ID": prestwick,
                "chemical_name": str(row[index["chemical_name"]] or "").strip(),
                "drug_class": str(row[index["drug_class"]] or "").strip(),
                "n_hit": row[index["n_hit"]],
                "cells": [(codes[i], as_float(row[i])) for i in species_at],
            }
        )
    return [codes[i] for i in species_at], out


def check_threshold(screen: list[dict]) -> int:
    """Re-derive the hit threshold against the sheet's own ``n_hit`` column.

    :data:`ontology.maier2018.HIT_THRESHOLD` decides the *type* of every edge in
    this source, and the sheet never states it — so it is checked on every run
    rather than trusted from the module. A mismatch is a hard stop: writing the
    tables anyway would invert an unknown share of 47,825 edges silently, which
    is the failure this whole loader is least able to notice afterwards.
    """
    mismatched = [
        row["prestwick_ID"]
        for row in screen
        if row["n_hit"] is not None
        and sum(1 for _c, p in row["cells"] if p is not None and p < mz.HIT_THRESHOLD)
        != int(row["n_hit"])
    ]
    if mismatched:
        raise SystemExit(
            f"HIT_THRESHOLD {mz.HIT_THRESHOLD} does not reproduce the sheet's own "
            f"n_hit on {len(mismatched)} of {len(screen)} drugs "
            f"(e.g. {', '.join(mismatched[:5])}). The threshold is derived, not "
            f"published: re-derive it before writing, because it decides which "
            f"relationship every cell becomes."
        )
    return len(screen)


def contested_atc_codes(drug_rows: dict[str, dict]) -> dict[str, list[str]]:
    """Level-5 ATC codes that **more than one library entry** claims.

    An ATC code names an active substance, and the Prestwick library screens
    stereoisomers, epimers and prodrug/active pairs as separate compounds — so
    one code covers two rows that were measured separately and gave different
    answers. Measured: 16 codes, 32 entries, among them ``(R)-`` and
    ``(S)-propranolol hydrochloride`` (C07AA05), ``(R)-`` and
    ``(S)-(-)-Atenolol`` (C07AB03), ``Chenodiol`` and ``Urosiol`` (A05AA),
    ``Racecadotril`` and its active metabolite ``Thiorphan``.

    Joining both to the one ChEMBL node the code names is not a coarse answer,
    it is a wrong one: it attributes the R-enantiomer's measurement to the
    molecule ChEMBL keys as propranolol. So a contested code is **not a join
    key for either entry**, which is the same rule
    :meth:`microbiomekg.drugs.DrugIndex.from_csv` already applies from the other
    side to a code two ChEMBL nodes claim. The entries fall through to the
    salt-strip route or are minted on their catalogue number, and each dropped code is a ledger row.
    """
    claimed: dict[str, list[str]] = {}
    for prestwick, row in drug_rows.items():
        for code in atc_level5(row.get("ATC codes")):
            claimed.setdefault(code, []).append(prestwick)
    return {code: ids for code, ids in claimed.items() if len(set(ids)) > 1}


def run(
    raw: Path,
    store: Frames,
    *,
    tables: Path | None = None,
    taxdump: Path | None = None,
    rank_ceiling: str = "species",
) -> dict[str, int]:
    """Maier 2018's tables into ``store``; returns each table's row count.

    ``tables`` defaults to ``raw/drug_screens/maier2018/``. Reads ChEMBL's
    ``drug`` table off the store. Raises :class:`MissingInput` when a
    workbook or the taxdump is not there.
    """

    tables = tables or (raw / RAW_SUBDIR)
    paths = {n: tables / filename for n, (filename, _sheet) in WORKBOOKS.items()}
    missing = sorted(p.name for p in paths.values() if not p.is_file())
    if missing:
        # Exit 3, not 2 — "this source's raw files are not on this machine"
        # rather than "this script was called wrong", so an absent bundle leaves
        # the build without failing it.
        raise MissingInput(
            f"no Maier 2018 supplementary tables under {tables} "
            f"(missing {', '.join(missing)})"
        )
    try:
        taxdump = taxdump or find_taxdump(raw)
    except FileNotFoundError as e:
        raise MissingInput(str(e)) from e
    drug_rows = read_drugs(paths[1])
    isolates = read_species(paths[2])
    validation = read_validation(paths[4])
    codes, screen = read_screen(paths[3])
    print(
        f"read {len(screen):,} drugs x {len(codes)} isolates = "
        f"{len(screen) * len(codes):,} screen cells from {paths[3].name}"
    )
    print(
        f"  {len(drug_rows):,} library entries, {len(isolates):,} isolates, "
        f"{len(validation):,} dose-response follow-ups"
    )
    check_threshold(screen)
    print(
        f"  hit threshold p < {mz.HIT_THRESHOLD} reproduces the sheet's own "
        f"n_hit on all {len(screen):,} drugs"
    )

    contested = contested_atc_codes(drug_rows)
    index = DrugIndex.from_rows(store.rows("drug"), exclude_source=SOURCE).without_atc(
        contested
    )
    print(
        f"drug.csv: {len(index.names):,} ChEMBL pref_names, "
        f"{len(index.atc):,} level-5 ATC codes claimed by exactly one ChEMBL "
        f"node and one library entry"
    )
    print(
        f"  {len(contested):,} ATC codes are claimed by two library entries and "
        f"are a join key for neither"
    )

    print(f"loading taxdump from {taxdump} ...", flush=True)
    idx = TaxonomyIndex.from_taxdump(taxdump)
    print(f"  {len(idx.parent):,} taxa, {len(idx.names):,} name keys", flush=True)

    edges = {
        mz.RELATION_INHIBITS: store.table(
            "drug_taxon_inhibited",
            ["drug_id", "tax_id", *EDGE_FIELDS],
            dedupe_full=True,
            merge=True,
            owner=("primary_source", SOURCE),
        ),
        mz.RELATION_NO_EFFECT: store.table(
            "drug_taxon_no_effect",
            ["drug_id", "tax_id", *EDGE_FIELDS],
            dedupe_full=True,
            merge=True,
            owner=("primary_source", SOURCE),
        ),
    }
    drugs = store.table(
        "drug",
        DRUG_FIELDS,
        key="drug_id",
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
    ledger = store.table(
        "unresolved_maier2018",
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

    def note(kind: str, record_id: str, subject: str, detail: str, reason: str) -> None:
        ledger.add(
            {
                "kind": kind,
                "record_id": record_id,
                "subject": subject,
                "detail": detail,
                "reason": reason,
                "source": SOURCE,
            }
        )

    for code, entries in sorted(contested.items()):
        note(
            "atc",
            code,
            ", ".join(sorted(set(entries))),
            "",
            "two library entries claim this ATC code — stereoisomers, epimers "
            "or a prodrug and its active form, measured separately — so it "
            "identifies neither and both fall through to the next route",
        )

    # ---------------------------------------------------------- the isolates
    resolved: dict[str, dict] = {}
    resolutions: Counter[str] = Counter()
    taxon_joins: Counter[str] = Counter()
    unresolved_hits: Counter[str] = Counter()
    for code in codes:
        isolate = isolates.get(code)
        if isolate is None:
            note(
                "isolate",
                code,
                code,
                "screened column with no supplementary-table-2 row",
                "the isolate dictionary names no organism for this NT code",
            )
            continue
        reported = isolate["species"]
        override = mz.SPECIES_OVERRIDES.get(reported.casefold())
        lookup = override or reported
        route = "override" if override else "exact"
        res = idx.resolve(lookup, rank_ceiling=rank_ceiling)
        resolutions[res.status] += 1
        if res.tax_id is None:
            uid = f"unresolved:{SOURCE}:{reported.casefold()}"
            unresolved_nodes.add(
                {
                    "unresolved_id": uid,
                    "raw_name": reported,
                    "reported_rank": mz.REPORTED_RANK,
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
            note(
                "isolate",
                code,
                reported,
                isolate["strain"],
                f"taxon {res.status}: {res.note}",
            )
            continue
        rank = idx.rank.get(res.tax_id) or ""
        own, ceiling = rank_depth(rank), rank_depth(mz.RANK_CEILING)
        if own is None or ceiling is None or own < ceiling:
            # Every organism here is one cultured isolate, so a resolution this
            # broad is a surprise rather than a filter — and the ledger row
            # carries the id and rank it did reach, so the ceiling is reversible.
            note(
                "isolate",
                code,
                reported,
                f"{res.tax_id} ({rank or 'unplaced'})",
                f"resolved rank is broader than {mz.RANK_CEILING!r}",
            )
            continue
        taxon_joins[route] += 1
        resolved[code] = {
            "tax_id": res.tax_id,
            "reported_name": reported,
            "strain": isolate["strain"],
            "gram_stain": isolate["gram_stain"],
            "original_rank": res.original_rank or rank,
            "resolution_status": res.status,
            "taxon_join": route,
        }

    # ------------------------------------------------------------- the drugs
    drug_joins: Counter[str] = Counter()
    minted: dict[str, str] = {}
    drug_ids: dict[str, str] = {}
    #: prestwick_ID -> the route that reached its node, so the edge can say
    #: which of the three identifier spaces the join actually used.
    drug_routes: dict[str, str] = {}
    for row in screen:
        prestwick = row["prestwick_ID"]
        library = drug_rows.get(prestwick, {})
        name = str(library.get("chemical name") or row["chemical_name"]).strip()
        atc_cell = library.get("ATC codes")
        drug_id, route, others = join_drug(mz.drug_variants(name, atc_cell), index)
        if others:
            # The name route reaches a ChEMBL *salt* node while the ATC code
            # reaches its parent, on 14 of the 415 drugs both routes answer.
            # That is ChEMBL's documented parent gap showing through, not a
            # defect here — but a precedence rule that hid it would leave the
            # graph's own count unreadable.
            note(
                "drug",
                prestwick,
                name,
                f"{route} -> {drug_id}; also {','.join(others)}",
                "two join routes reached different ChEMBL nodes; the route the "
                "source's own spelling took wins",
            )
        if not drug_id:
            if not prestwick:
                note("drug", "", name, "", "library row carries no identifier at all")
                continue
            drug_id = f"PRESTWICK:{prestwick}"
            if drug_id not in minted:
                minted[drug_id] = name
                drugs.add(
                    {
                        "drug_id": drug_id,
                        "chembl_id": "",
                        "pref_name": name,
                        "molecule_type": "",
                        "max_phase": "",
                        "first_approval": "",
                        "atc_codes": as_list(atc_level5(atc_cell)),
                        # Not `true`: the Prestwick library is "approved drugs", but
                        # `approved` in this graph means ChEMBL max_phase 4 and
                        # inheriting that claim from a catalogue's marketing copy
                        # would put an unverified regulatory status on 437 nodes.
                        "approved": "false",
                        "withdrawn": "false",
                        "therapeutic": "",
                        "oral": "",
                        "parenteral": "",
                        "topical": "",
                        "smiles": "",
                        "salt_form": "false",
                        "salt_ids": "",
                        "source": SOURCE,
                        "source_licence": ont.SOURCE_LICENCE.get(SOURCE, ""),
                        "chembl_release": "",
                        "prestwick_id": prestwick,
                        "pubchem_cid": mz.pubchem_cid(library.get("STITCH4 id")),
                        "screen_drug_class": row["drug_class"],
                        "screen_target_species": str(
                            library.get("target species") or ""
                        ),
                    }
                )
        drug_joins[route] += 1
        drug_ids[prestwick] = drug_id
        drug_routes[prestwick] = route

    # ------------------------------------------------------------- the cells
    counters: Counter[str] = Counter()
    per_relation: Counter[str] = Counter()
    taxa_seen: "OrderedDict[int, int]" = OrderedDict()
    for row in screen:
        prestwick = row["prestwick_ID"]
        drug_id = drug_ids.get(prestwick)
        library = drug_rows.get(prestwick, {})
        name = str(library.get("chemical name") or row["chemical_name"]).strip()
        for code, adjusted_p in row["cells"]:
            counters["cells"] += 1
            isolate = resolved.get(code)
            if isolate is None:
                counters["unusable_isolate"] += 1
                continue
            relationship = mz.relation_for(adjusted_p)
            if relationship is None:
                counters["not_measured"] += 1
                note(
                    "cell",
                    f"{prestwick}|{code}",
                    name,
                    isolate["reported_name"],
                    "the screen writes NA for this pair: measured as neither a "
                    "hit nor a non-hit",
                )
                continue
            if drug_id is None:
                counters["unusable_drug"] += 1
                continue
            effect, source_relation = mz.SOURCE_RELATIONS[relationship]
            follow_up = validation.get((prestwick, code), {})
            tax_id = isolate["tax_id"]
            taxa_seen[tax_id] = taxa_seen.get(tax_id, 0) + 1
            per_relation[relationship] += 1
            counters["edges"] += 1
            edges[relationship].add(
                {
                    "drug_id": drug_id,
                    "tax_id": str(tax_id),
                    "effect": effect,
                    "evidence_level": mz.EVIDENCE_LEVEL,
                    "knowledge_level": ont.knowledge_level(SOURCE),
                    "agent_type": ont.agent_type(SOURCE),
                    "primary_source": SOURCE,
                    "source_record_id": f"{SOURCE}:{prestwick}|{code}",
                    "source_licence": ont.SOURCE_LICENCE.get(SOURCE, ""),
                    "source_relation": source_relation,
                    "publications": as_list([mz.PUBLICATION]),
                    "pmid": str(mz.PUBMED_ID),
                    "adjusted_p_value": repr(adjusted_p),
                    "screen_concentration_um": repr(mz.SCREEN_CONCENTRATION_UM),
                    "prestwick_id": prestwick,
                    "reported_drug_name": name,
                    "drug_class": row["drug_class"],
                    "drug_join": drug_routes.get(prestwick, ""),
                    "nt_code": code,
                    "reported_name": isolate["reported_name"],
                    "strain": isolate["strain"],
                    "gram_stain": isolate["gram_stain"],
                    "reported_rank": mz.REPORTED_RANK,
                    "original_rank": isolate["original_rank"],
                    "resolution_status": isolate["resolution_status"],
                    "taxon_join": isolate["taxon_join"],
                    "ic25_um": _num(follow_up.get("IC25 (μM)")),
                    "ic25_qualifier": str(follow_up.get("qualifier (IC25)") or ""),
                    "mic_um": _num(follow_up.get("MIC (μM)")),
                    "mic_qualifier": str(follow_up.get("qualifier (MIC)") or ""),
                    "validation_outcome": str(
                        follow_up.get("validation outcome") or ""
                    ),
                }
            )

    for row in unresolved_nodes.rows:
        if row["source"] == SOURCE:
            row["n_signatures"] = str(unresolved_hits.get(row["unresolved_id"], 0))
    for tid, n in sorted(taxa_seen.items()):
        cited.add({"tax_id": str(tid), "source": SOURCE, "n_signatures": str(n)})

    tables_out = (*edges.values(), drugs, unresolved_nodes, ledger, cited)
    counts = {w.name: store.put(w) for w in tables_out}

    validated = sum(
        1
        for w in edges.values()
        for r in w.rows
        if r.get("primary_source") == SOURCE and r.get("validation_outcome")
    )
    print(
        f"\nread {counters['cells']:,} cells -> {counters['edges']:,} edges over "
        f"{len(taxa_seen):,} taxa and {len(drug_ids):,} drugs"
    )
    print(
        "  by relationship: "
        + ", ".join(f"{rel} {per_relation[rel]:,}" for rel in mz.GROWTH_RELATIONSHIPS)
    )
    print(
        f"  measured non-hits kept as {mz.RELATION_NO_EFFECT}: "
        f"{per_relation[mz.RELATION_NO_EFFECT]:,} (never folded into the hit edge)"
    )
    print(f"  pairs carrying the dose-response follow-up (IC25/MIC): {validated:,}")
    print(
        "  drug join: " + ", ".join(f"{r} {n:,}" for r, n in drug_joins.most_common())
    )
    print(
        "  isolate join: "
        + ", ".join(f"{r} {n:,}" for r, n in taxon_joins.most_common())
    )
    print(
        "  organism resolution: "
        + ", ".join(f"{s} {n:,}" for s, n in resolutions.most_common())
    )
    print(
        f"  not loaded: {counters['not_measured']:,} cells the screen wrote NA for, "
        f"{counters['unusable_isolate']:,} on an isolate that reached no taxon, "
        f"{counters['unusable_drug']:,} on a drug with no identifier"
    )
    print(
        f"  minted {len(minted):,} Drug nodes for library entries no ChEMBL "
        f"join route reached"
    )
    for name_, n in counts.items():
        print(f"  {name_:34s} {n:>9,}")
    shared = {w.name: w.merged_in for w in tables_out if w.merged_in}
    if shared:
        print(
            "  merged into tables another source had written: "
            + ", ".join(f"{name_} +{n:,}" for name_, n in shared.items())
        )
    return counts


def _num(value) -> str:
    """A follow-up cell as a bare number string, or ``""``.

    Table 4 writes its concentrations as text in some cells and as floats in
    others; the blueprint declares the column ``float``, and a stray unit or
    comparison operator would pin the whole property to ``string`` for the
    graph's lifetime (C16).
    """
    number = as_float(value)
    return "" if number is None else repr(number)

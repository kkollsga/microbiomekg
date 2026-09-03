#!/usr/bin/env python3
"""MiMeDB's two table dumps -> Metabolite nodes, and no edges, because there are none.

``data/raw/mimedb/`` holds two Sequel Ace exports of one MySQL table each:
``mimedb_metabolites_v1.csv`` (27,641 rows, ``SELECT * FROM metabolites WHERE
export = 1``) and ``mimedb_microbes_v1.csv`` (2,174 rows, ``SELECT * FROM
microbes WHERE export = 1``), plus the same two as zipped XML. **Neither carries
the association between them** — the measurement and its consequence for D5 are
in :mod:`microbiomekg.ontology.mimedb`, and the short version is that this
script writes ``metabolite.csv`` rows and nothing else. It emits no
``PRODUCES``, and the build report will say so with a zero rather than leaving
the reader to notice.

The microbes table is read anyway, for two things it *can* honestly answer, both
printed and neither loaded: how many of its 2,174 organisms carry an NCBI taxid
(all of them) and how many of those the loaded taxonomy still resolves. That is
the size of the taxon side of the edge list this source would supply if the
association were downloadable, and stating it is the difference between "MiMeDB
does not close D5" and "MiMeDB has nothing".

**The selection rule**, because 27,641 records is a lipidomics table and 12,105
of them are glycerophospholipids: 935 records are loaded on the full build. A record is loaded when at least one of
:data:`~microbiomekg.ontology.mimedb.SELECTION_RULES` holds — ``observed``,
``origin-classified``, ``njc19-compound`` — and ``Metabolite.selection_rule``
says which, joined with ``|``. The third rule reads NJC19's spreadsheet
directly, the way ``prep_hmdb.py`` reads ``ChEBI2Reactome.txt``: the alternative
is a second pass after NJC19 has run, and NJC19 needs these nodes to exist
before *it* runs.

Nothing is written for a record whose compound the graph already holds. Two
tests of "already holds", in this order:

* the normalised ``hmdb_id`` matches a ``Metabolite`` node's accession (or one
  of its ``secondary_accessions``) — 1,678 records over the whole file;
* the **full** ``moldb_inchikey`` matches a node's — 1,232 records. Never the
  first block alone: block 2 is stereochemistry, isotopes and protonation, so a
  skeleton match folds ``D-`` onto ``L-``;
* the name matches a ``Metabolite`` node's name, casefolded — the route NJC19
  itself uses, so a duplicate here would be a second node NJC19 might then pick.

Both are ledger rows in ``unresolved_mimedb.csv`` naming the node that already
holds the compound, so "MiMeDB added nothing here" is a count rather than an
absence. And an ``hmdb_id`` that **two** MiMeDB records claim is not used as a
join key at all: 149 accessions are contested, mostly by a D-/L- enantiomer
pair, and joining them would fold two compounds into one node.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from microbiomekg.ontology import mimedb as mm  # noqa: E402
from microbiomekg.ontology import njc19 as nj  # noqa: E402
from microbiomekg.rawdata import find_taxdump  # noqa: E402
from microbiomekg.reconcile import TaxonomyIndex  # noqa: E402
from microbiomekg.tables import Writer  # noqa: E402

SOURCE = mm.SOURCE

#: Reads ``metabolite.csv``, which HMDB writes: a MiMeDB record whose compound
#: already has a node must not mint a second one. It also *reads NJC19's raw
#: spreadsheet* for the ``njc19-compound`` selection rule, which is not a prep
#: dependency — the dependency runs the other way, and ``prep_njc19`` declares
#: it.
DEPENDS_ON: list[str] = ["hmdb"]

#: The MySQL dump writes an absent value as the four characters ``NULL``. Read
#: straight, that is the *string* "NULL" in a CSV column, which kglite loads as
#: a value and ``ontology_audit()`` counts as present.
NULL = "NULL"

METABOLITE_FIELDS = [
    "metabolite_id", "name", "hmdb_id", "chebi_id", "kegg_id", "pubchem_cid",
    "inchikey", "status", "biospecimens", "microbial_origin", "origin",
    "chemical_formula", "secondary_accessions", "selection_rule", "source",
    "mimedb_id", "mimedb_origin", "cas", "average_mass",
]

LEDGER_FIELDS = [
    "mimedb_id", "name", "hmdb_id", "metabolite_id", "reason", "source",
]


def cell(row: dict[str, str], key: str) -> str:
    """One dump cell, with ``NULL`` and whitespace resolved to ``""``."""
    value = (row.get(key) or "").strip()
    return "" if value == NULL else value


def load_metabolite_index(
    path: Path,
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """``(accession, casefolded name, InChIKey) -> metabolite_id``, three indexes.

    Rows this source wrote on a previous run are skipped — see the comment
    below; they are about to be replaced.

    Read out of the shared ``metabolite.csv`` rather than re-derived from HMDB's
    XML, for the reason ``docs/model.md`` records under ``IS_DRUG``: a consumer
    that re-derives another source's node ids from its raw input dangles
    silently the day that source changes its keying rule. The accession index
    carries ``secondary_accessions`` too — HMDB retired 80,986 ids, and MiMeDB
    was built against the older ones.
    """
    accessions: dict[str, str] = {}
    names: dict[str, str] = {}
    keys: dict[str, str] = {}
    if not path.is_file():
        return accessions, names, keys
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            key = row.get("metabolite_id") or ""
            # This source's own rows from a previous run are not "a node that
            # already holds the compound": `Writer(owner=...)` is about to drop
            # and rewrite them, so counting them here makes a second run load
            # nothing and report every record as a duplicate of itself. That is
            # the re-run failure `microbiomekg.tables` documents, reached
            # through the index instead of the writer.
            if not key or (row.get("source") or "") == SOURCE:
                continue
            for accession in (row.get("hmdb_id") or "", *(row.get("secondary_accessions") or "").split("|")):
                normalised = mm.normalise_hmdb_id(accession)
                if normalised:
                    accessions.setdefault(normalised, key)
            name = (row.get("name") or "").strip().casefold()
            if name:
                names.setdefault(name, key)
            # The full InChIKey, never its first block. Block 1 is the molecular
            # skeleton and block 2 is stereochemistry, isotopes and protonation,
            # so a skeleton match folds D- onto L- and an acid onto its own
            # conjugate base — the identity merge the contested-accession rule
            # already refuses. The full key is an exact structural identity and
            # joins 1,232 MiMeDB records to a node HMDB wrote.
            inchikey = (row.get("inchikey") or "").strip()
            if inchikey:
                keys.setdefault(inchikey, key)
    return accessions, names, keys


def njc19_wanted_names(xlsx: Path, held: dict[str, str]) -> set[str]:
    """Casefolded spellings of the NJC19 compounds **nothing in the graph holds**.

    :func:`microbiomekg.ontology.njc19.name_variants` is the authority for what
    those spellings are, so this cannot drift from the join that consumes it —
    which is the whole reason the rule reads NJC19's file here rather than
    guessing at a list of interesting compounds.

    ``held`` is what makes it "nothing holds": a compound **any** of whose
    spellings already names a node contributes none of them. Without that
    condition this rule mints a second node for a compound the graph has under
    a different spelling, and NJC19 then prefers the new one — measured, on
    ``Propanoate (Propionate)``, which HMDB holds as ``Propionic acid``
    (CHEBI:30768) and MiMeDB names ``propanoic acid``. The head name's conjugate
    is tried before any synonym, so the MiMeDB node won and NJC19's 97
    propionate producers landed on a node HMDB's 12 were not on. One compound,
    two nodes, and D6's MES computed over half its evidence each side: the exact
    failure the conjugate rule exists to prevent, re-introduced by the source
    that was supposed to help.
    """
    try:
        import openpyxl
    except ImportError:  # pragma: no cover - openpyxl is a declared dependency
        return set()
    if not xlsx.is_file():
        return set()
    book = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    wanted: set[str] = set()
    for sheet in book.sheetnames:
        for row in book[sheet].iter_rows(values_only=True):
            compound = row[2] if len(row) > 2 else None
            if not isinstance(compound, str) or not compound.strip():
                continue
            spellings = [s.casefold() for s, _route in nj.name_variants(compound)]
            if any(spelling in held for spelling in spellings):
                continue
            wanted.update(spellings)
    book.close()
    return wanted


def microbe_report(path: Path, idx: TaxonomyIndex) -> tuple[int, int, Counter]:
    """How many of MiMeDB's organisms carry a taxid this taxonomy still resolves.

    Printed, never loaded. It is the *taxon side* of the edge list this source
    would supply if the association between its two tables were downloadable,
    and quoting it is what stops "MiMeDB does not close D5" being read as
    "MiMeDB has no organisms".
    """
    statuses: Counter[str] = Counter()
    rows = 0
    with_taxid = 0
    if not path.is_file():
        return 0, 0, statuses
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            rows += 1
            taxid = cell(row, "ncbi_tax_id")
            if not taxid.isdigit():
                continue
            with_taxid += 1
            statuses[idx.resolve(tax_id=int(taxid), rank_ceiling="species").status] += 1
    return rows, with_taxid, statuses


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", type=Path, default=Path("data/raw"))
    ap.add_argument("--metabolites", type=Path, default=None,
                    help="MiMeDB metabolites CSV (default: <raw>/mimedb/mimedb_metabolites_v1.csv).")
    ap.add_argument("--microbes", type=Path, default=None,
                    help="MiMeDB microbes CSV (default: <raw>/mimedb/mimedb_microbes_v1.csv). "
                         "Reported on, never loaded: the dumps carry no link between the two.")
    ap.add_argument("--njc19", type=Path, default=None,
                    help="NJC19's Online-only Table 5 xlsx (default: "
                         "<raw>/njc19/41597_2020_516_MOESM1_ESM.xlsx). Absent means the "
                         "njc19-compound selection rule selects nothing.")
    ap.add_argument("--taxdump", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=Path("data/csv"))
    args = ap.parse_args(argv)

    metabolites_csv = args.metabolites or (args.raw / SOURCE / "mimedb_metabolites_v1.csv")
    if not metabolites_csv.is_file():
        # Exit 3, not 2: "this source's raw file is not on this machine" is a
        # different fact from "this script was called wrong". mimedb.org answers
        # automated clients with 403, so an absent file is the expected state of
        # a fresh clone.
        print(f"no mimedb_metabolites_v1.csv at {metabolites_csv}", file=sys.stderr)
        return 3
    microbes_csv = args.microbes or (args.raw / SOURCE / "mimedb_microbes_v1.csv")
    njc19_xlsx = args.njc19 or (args.raw / "njc19" / "41597_2020_516_MOESM1_ESM.xlsx")

    try:
        taxdump = args.taxdump or find_taxdump(args.raw)
    except FileNotFoundError as e:
        ap.error(str(e))

    out = args.out
    accessions, existing_names, existing_keys = load_metabolite_index(
        out / "metabolite.csv"
    )
    print(f"metabolite.csv: {len(accessions):,} HMDB accessions, "
          f"{len(existing_names):,} names and {len(existing_keys):,} InChIKeys "
          f"already have a node")

    wanted = njc19_wanted_names(njc19_xlsx, existing_names)
    if wanted:
        print(f"njc19 bridge: {len(wanted):,} compound spellings from {njc19_xlsx}")
    else:
        print(f"no {njc19_xlsx}; the njc19-compound selection rule selects nothing")

    # csv's default field limit is 131,072 characters and MiMeDB's `description`
    # column runs past it on the well-studied compounds — the read fails with
    # "field larger than field limit" a few thousand rows in, which looks like a
    # truncated file rather than a reader setting.
    csv.field_size_limit(1 << 30)
    with metabolites_csv.open(encoding="utf-8", newline="") as fh:
        records = list(csv.DictReader(fh))
    print(f"read {len(records):,} metabolite records from {metabolites_csv}")

    #: normalised accession -> the MiMeDB ids claiming it. An accession two
    #: records claim is not a join key; see the module docstring.
    claimants: dict[str, list[str]] = defaultdict(list)
    for row in records:
        normalised = mm.normalise_hmdb_id(cell(row, "hmdb_id"))
        if normalised:
            claimants[normalised].append(cell(row, "mime_id"))
    contested = {a for a, ids in claimants.items() if len(ids) > 1}

    metabolites = Writer(
        out / "metabolite.csv", METABOLITE_FIELDS,
        key="metabolite_id", merge=True, owner=("source", SOURCE),
    )
    ledger = Writer(
        out / "unresolved_mimedb.csv", LEDGER_FIELDS,
        merge=True, owner=("source", SOURCE),
    )

    counters: Counter[str] = Counter()
    rules: Counter[str] = Counter()
    origins: Counter[str] = Counter()

    for row in records:
        mime_id = cell(row, "mime_id")
        name = cell(row, "name")
        accession = mm.normalise_hmdb_id(cell(row, "hmdb_id"))
        observed = any(cell(row, f) == "1" for f in mm.OBSERVED_FLAGS)
        origin = cell(row, "metabolite_type")

        keep: list[str] = []
        if observed:
            keep.append("observed")
        if origin:
            keep.append("origin-classified")
        if name and name.casefold() in wanted and name.casefold() not in existing_names:
            keep.append("njc19-compound")
        if not keep:
            counters["not_selected"] += 1
            continue

        if accession and accession in contested:
            counters["contested_accession"] += 1
            ledger.add({
                "mimedb_id": mime_id, "name": name, "hmdb_id": accession,
                "metabolite_id": "",
                "reason": f"HMDB accession {accession} is claimed by "
                          f"{len(claimants[accession])} MiMeDB records "
                          f"({', '.join(claimants[accession])}): it is not a join key, "
                          f"and this record keeps its own MiMeDB identity",
                "source": SOURCE,
            })
            accession = ""

        inchikey = cell(row, "moldb_inchikey")
        held = accessions.get(accession) if accession else None
        if held is None and inchikey:
            held = existing_keys.get(inchikey)
        if held is None and name:
            held = existing_names.get(name.casefold())
        if held is not None:
            counters["already_held"] += 1
            ledger.add({
                "mimedb_id": mime_id, "name": name, "hmdb_id": accession,
                "metabolite_id": held,
                "reason": f"{held} already holds this compound: a second node would "
                          f"split the pathway and production edges that point at it, "
                          f"and Writer's first-row-per-key rule would discard these "
                          f"properties anyway",
                "source": SOURCE,
            })
            continue

        for rule in keep:
            rules[rule] += 1
        if origin:
            origins[origin] += 1
        counters["loaded"] += 1
        # This run's own names join the index as it goes. Two MiMeDB records
        # sharing a name would otherwise become two nodes, and NJC19's name
        # index — first writer wins — would then reach whichever sorted first.
        if name:
            existing_names.setdefault(name.casefold(), f"MIMEDB:{mime_id}")
        if inchikey:
            existing_keys.setdefault(inchikey, f"MIMEDB:{mime_id}")
        metabolites.add({
            "metabolite_id": f"MIMEDB:{mime_id}",
            "name": name,
            "hmdb_id": accession,
            "chebi_id": "",
            "kegg_id": "",
            "pubchem_cid": "",
            "inchikey": inchikey,
            # MiMeDB has no `status` column: HMDB's four-value detection status
            # is not this file's vocabulary, and writing a plausible-looking
            # value into a column another source's evidence rule reads would be
            # inventing evidence. `mimedb_origin` carries what this file does
            # grade on.
            "status": "",
            "biospecimens": "",
            "microbial_origin": "false",
            "origin": "",
            "chemical_formula": cell(row, "moldb_formula"),
            "secondary_accessions": "",
            "selection_rule": "|".join(keep),
            "source": SOURCE,
            "mimedb_id": mime_id,
            "mimedb_origin": origin,
            "cas": cell(row, "cas"),
            "average_mass": cell(row, "moldb_average_mass"),
        })

    print(f"loading taxdump from {taxdump} ...", flush=True)
    idx = TaxonomyIndex.from_taxdump(taxdump)
    microbe_rows, with_taxid, statuses = microbe_report(microbes_csv, idx)

    tables = (metabolites, ledger)
    counts = {w.path.name: w.flush() for w in tables}

    print(f"\nmetabolites: {len(records):,} records read")
    print(f"  selection rule: " + ", ".join(f"{r} {n:,}" for r, n in sorted(rules.items())))
    print(f"  loaded {counters['loaded']:,} new Metabolite nodes, "
          f"skipped {counters['not_selected']:,} that no rule selected")
    print(f"  not written because the compound already has a node: "
          f"{counters['already_held']:,}")
    print(f"  HMDB accessions two MiMeDB records claim, so not used as a join key: "
          f"{counters['contested_accession']:,} records over "
          f"{len(contested):,} accessions")
    if origins:
        print("  mimedb_origin: " + ", ".join(f"{o} {n:,}" for o, n in origins.most_common()))
    print(f"\nmicrobes: {microbe_rows:,} organisms, {with_taxid:,} with an NCBI taxid, "
          + ", ".join(f"{s} {n:,}" for s, n in statuses.most_common()))
    print("  PRODUCES edges from MiMeDB: 0 — the two dumps carry no association "
          "between them (microbiomekg/ontology/mimedb.py). D5 is unchanged by "
          "this source.")
    for name, n in counts.items():
        print(f"  {name:34s} {n:>9,}")
    shared = {w.path.name: w.merged_in for w in tables if w.merged_in}
    if shared:
        print("  merged into tables another source had written: " + ", ".join(
            f"{name} +{n:,}" for name, n in shared.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Regenerate ``tests/fixtures/mimedb_mini/mimedb_{metabolites,microbes}_v1.csv``.

Unlike the HMDB and gutMDisorder fixtures these outputs are plain CSV and are
reviewable on their own; this script exists so that the *reason for each row* is
recorded next to the row, and so the 42- and 39-column headers stay the real
dump's exactly — a fixture with a trimmed header would hide a column-name typo
in the loader.

Run it only when the fixture needs to change::

    .venv/bin/python tests/fixtures/make_mimedb_mini.py

**`mimedb_metabolites_v1.csv` rows, and what each one is for**

===============================  ==============================================
record                           the trap
===============================  ==============================================
``Pectin``                       the ``njc19-compound`` rule: NJC19's fixture
                                 degrades pectin and no HMDB record holds it, so
                                 this record is what turns a minted stub into an
                                 identified compound. Nothing else selects it —
                                 no detection flag, no ``metabolite_type``.
``Chitin``                       the same rule and **not** selected, because the
                                 NJC19 fixture never names chitin. The rule is
                                 "a compound NJC19 needs", not "a compound
                                 NJC19 might need".
``Butyrate salt``                ``hmdb_id`` = ``HMDB00011``, the **legacy
                                 five-digit spelling** of a secondary accession
                                 of HMDB's butyric acid record. Normalising the
                                 padding is what finds it; not normalising reads
                                 as "MiMeDB has no HMDB id for this".
``Acetic acid``                  no ``hmdb_id`` at all, but a name HMDB already
                                 holds: the name test, which is the one that
                                 stops a second node NJC19 would then pick.
``Ethanoic acid``                neither name nor accession matches, but the
                                 **full InChIKey** is HMDB's acetic acid
                                 (``KEY-0012-N`` — the mini HMDB fixture uses
                                 synthetic keys): the structural test. Its own
                                 ``metabolite_type`` would otherwise select it.
``L-Tyrosine`` / ``D-Tyrosine``  **both** carry ``HMDB0000158``. A contested
                                 accession is not a join key: two records, two
                                 ``MIMEDB:`` nodes, two ledger rows — never one
                                 node with the other's annotations.
``Trimethylamine oxide``         ``detected = 1``: the ``observed`` rule, and a
                                 record whose ``quantified`` says the same thing
                                 the same way (the file's two flags are one
                                 fact).
``Microbial co-metabolite``      ``metabolite_type = Co-metabolite``: the
                                 ``origin-classified`` rule, MiMeDB's only
                                 evidence-graded axis.
``PC(16:0/18:1)``                a glycerophospholipid no rule selects — 44% of
                                 the real file looks like this, and loading it
                                 whole is how a microbiome graph becomes a
                                 lipidomics table.
``NULL-valued compound``         every optional column is the literal string
                                 ``NULL``. Read straight, that is the *string*
                                 "NULL" in the graph, which the audit counts as
                                 a present value.
===============================  ==============================================

**`mimedb_microbes_v1.csv`** carries six organisms, none of which is ever
loaded — the file has no compound column, so there is no edge to write. They are
here so the resolution report the prep prints is exercised: two exact
(``Escherichia coli``, ``Akkermansia muciniphila``), one promoted from a strain
id (``Escherichia coli K-12``, taxid 83333 -> 562), one whose ``activity`` says
``Production (export)`` **with no compound anywhere on the row** — the column a
careless loader would turn into a ``PRODUCES`` edge — and two more filling out
the phenotype columns.
"""

from __future__ import annotations

import csv
from pathlib import Path

OUT = Path(__file__).resolve().parent / "mimedb_mini"

#: The real dump's 42 columns, in order.
METABOLITE_COLUMNS = [
    "id", "name", "mime_id", "export", "description", "cas", "state", "comment",
    "moldb_id", "moldb_smiles", "moldb_formula", "moldb_inchi", "moldb_inchikey",
    "moldb_iupac", "moldb_logp", "moldb_pka", "moldb_average_mass", "moldb_mono_mass",
    "moldb_alogps_solubility", "moldb_alogps_logp", "moldb_alogps_logs",
    "moldb_acceptor_count", "moldb_donor_count", "moldb_rotatable_bond_count",
    "moldb_polar_surface_area", "moldb_refractivity", "moldb_polarizability",
    "moldb_traditional_iupac", "moldb_formal_charge", "moldb_physiological_charge",
    "moldb_pka_strongest_acidic", "moldb_pka_strongest_basic", "created_at",
    "updated_at", "hmdb_id", "detected", "quantified", "predicted", "expected",
    "vmh_id", "metabolite_type", "classification",
]

#: The real dump's 39 columns, in order.
MICROBE_COLUMNS = [
    "id", "name", "microbe_id", "species", "kingdom", "phylum", "ncbi_tax_id",
    "activity", "gram", "oxygen_requirement", "created_at", "updated_at", "klass",
    "order", "family", "genus", "strain", "metabolism", "shape", "mobility",
    "flagella_presence", "number_of_membranes", "optimal_temperature",
    "temperature_range", "habitat", "biotic_relationship", "cell_arrangement",
    "sporulation", "energy_source", "superkingdom", "background", "health_type",
    "evidence_type", "data_source", "export", "human_pathogen", "genome_ids",
    "parent_id", "level",
]

#: Only the columns a row actually sets; everything else becomes ``NULL``, which
#: is what the dump writes for an absent value.
METABOLITES: list[dict[str, str]] = [
    {"id": "1", "name": "Pectin", "mime_id": "MMDBc0000239",
     "moldb_inchikey": "PECTINKEY000001-UHFFFAOYSA-N", "moldb_formula": "C6H10O7",
     "moldb_average_mass": "194.1394", "classification": "Organooxygen compounds"},
    {"id": "2", "name": "Chitin", "mime_id": "MMDBc0000235",
     "moldb_inchikey": "CHITINKEY00001-UHFFFAOYSA-N", "moldb_formula": "C8H13NO5",
     "hmdb_id": "HMDB0003362"},
    {"id": "3", "name": "Butyrate salt", "mime_id": "MMDBc0000011",
     "hmdb_id": "HMDB00011", "detected": "1", "quantified": "1",
     "moldb_inchikey": "FERIUCNNQQJTOY-UHFFFAOYSA-M", "moldb_formula": "C4H7O2"},
    {"id": "4", "name": "Acetic acid", "mime_id": "MMDBc0000012",
     "metabolite_type": "Primary", "moldb_inchikey": "MIMEDBACETIC01-UHFFFAOYSA-N",
     "moldb_formula": "C2H4O2"},
    {"id": "5", "name": "Ethanoic acid", "mime_id": "MMDBc0000013",
     "metabolite_type": "Co-metabolite", "moldb_inchikey": "KEY-0012-N",
     "moldb_formula": "C2H4O2"},
    {"id": "6", "name": "L-Tyrosine", "mime_id": "MMDBc0000158",
     "hmdb_id": "HMDB0000158", "metabolite_type": "Co-metabolite",
     "moldb_inchikey": "OUYCCCASQSFEME-QMMMGPOBSA-N", "moldb_formula": "C9H11NO3"},
    {"id": "7", "name": "D-Tyrosine", "mime_id": "MMDBc0000159",
     "hmdb_id": "HMDB0000158", "metabolite_type": "Co-metabolite",
     "moldb_inchikey": "OUYCCCASQSFEME-MRVPVSSYSA-N", "moldb_formula": "C9H11NO3"},
    {"id": "8", "name": "Trimethylamine oxide", "mime_id": "MMDBc0000014",
     "detected": "1", "quantified": "1",
     "moldb_inchikey": "UYPYRKYUKCHHIB-UHFFFAOYSA-N", "moldb_formula": "C3H9NO",
     "cas": "1184-78-7"},
    {"id": "9", "name": "Microbial co-metabolite", "mime_id": "MMDBc0000015",
     "metabolite_type": "Co-metabolite",
     "moldb_inchikey": "COMETABOLITE01-UHFFFAOYSA-N", "moldb_formula": "C7H6O2"},
    {"id": "10", "name": "PC(16:0/18:1)", "mime_id": "MMDBc0049000",
     "moldb_inchikey": "PHOSPHOLIPID01-UHFFFAOYSA-N",
     "classification": "Glycerophospholipids"},
    {"id": "11", "name": "NULL-valued compound", "mime_id": "MMDBc0000016",
     "metabolite_type": "Primary",
     "moldb_inchikey": "NULLVALUEDCMP1-UHFFFAOYSA-N"},
]

MICROBES: list[dict[str, str]] = [
    {"id": "1", "name": "Escherichia coli", "microbe_id": "MMDBm0000001",
     "species": "Escherichia coli", "ncbi_tax_id": "562", "genus": "Escherichia",
     "family": "Enterobacteriaceae", "phylum": "Pseudomonadota",
     "superkingdom": "Bacteria", "gram": "Negative",
     "oxygen_requirement": "Facultative anaerobe", "human_pathogen": "1"},
    {"id": "2", "name": "Akkermansia muciniphila", "microbe_id": "MMDBm0000002",
     "species": "Akkermansia muciniphila", "ncbi_tax_id": "239935",
     "genus": "Akkermansia", "superkingdom": "Bacteria", "gram": "Negative",
     "oxygen_requirement": "Anaerobe", "habitat": "Host-associated"},
    # A strain-level taxid: `reconcile` promotes it to 562, and this row is the
    # one that makes the prep's `promoted` count non-zero.
    {"id": "3", "name": "Escherichia coli K-12", "microbe_id": "MMDBm0000003",
     "species": "Escherichia coli", "ncbi_tax_id": "83333",
     "strain": "Escherichia coli K-12", "superkingdom": "Bacteria"},
    # `activity` says this organism produces something, and names nothing. This
    # row is the whole argument for why MiMeDB writes no PRODUCES edge: it is
    # the only column in either dump that looks like a relation, and it has no
    # object.
    {"id": "4", "name": "Faecalibacterium prausnitzii", "microbe_id": "MMDBm0000004",
     "species": "Faecalibacterium prausnitzii", "ncbi_tax_id": "853",
     "activity": "Production (export)", "data_source": "NJS16",
     "superkingdom": "Bacteria", "oxygen_requirement": "Anaerobe"},
    {"id": "5", "name": "Bacteroides thetaiotaomicron", "microbe_id": "MMDBm0000005",
     "species": "Bacteroides thetaiotaomicron", "ncbi_tax_id": "818",
     "genus": "Bacteroides", "superkingdom": "Bacteria", "gram": "Negative",
     "sporulation": "Nonsporulating"},
    {"id": "6", "name": "Bifidobacterium longum", "microbe_id": "MMDBm0000006",
     "species": "Bifidobacterium longum", "ncbi_tax_id": "216816",
     "genus": "Bifidobacterium", "superkingdom": "Bacteria", "gram": "Positive"},
]


def write(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for row in rows:
            # `export = 1` is in the dump's own WHERE clause, so every row has
            # it; everything the row does not set is the literal string NULL.
            writer.writerow({c: row.get(c, "NULL") for c in columns} | {"export": "1"})
    print(f"wrote {path} ({len(rows)} rows)")


def main() -> None:
    write(OUT / "mimedb_metabolites_v1.csv", METABOLITE_COLUMNS, METABOLITES)
    write(OUT / "mimedb_microbes_v1.csv", MICROBE_COLUMNS, MICROBES)


if __name__ == "__main__":
    main()

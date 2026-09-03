#!/usr/bin/env python3
"""Regenerate ``tests/fixtures/mimedb_mini/mimedb_{metabolites,microbes}_v{1,2}.csv``.

Unlike the HMDB and gutMDisorder fixtures these outputs are plain CSV and are
reviewable on their own; this script exists so that the *reason for each row* is
recorded next to the row, and so the headers stay the real dumps' exactly — 46
and 44 columns for v2, 42 and 39 for v1. A fixture with a trimmed header would
hide a column-name typo in the loader, and a fixture carrying only one release
would let the v1 fallback rot untested.

**Both releases are generated, because the loader reads either one.**
``prep_mimedb.py`` prefers ``data/raw/mimedb/v2/`` and falls back to the v1
files beside it, so the fallback is a code path with its own tests, not a
comment. The v2 files carry four columns v1 does not — ``epa_substance_id``,
``epa_compound_id``, ``microbe_relations``, ``cmmc_inchikey`` — and the
metabolite records are otherwise the same eleven, plus one that exists only in
v2.

**Which cells are real.** Every ``vmh_id``, ``epa_substance_id``,
``epa_compound_id`` and ``microbe_relations`` value on a record whose name
appears in the real dump is **cut verbatim from
``data/raw/mimedb/v2/mimedb_metabolites_v2.csv``** — including
``Chitin``'s semicolon-joined ``chtn; M01437; M01436``, which is why the loader
carries ``vmh_id`` as an opaque string rather than parsing it, and
``D-Tyrosine``'s legacy ``HMDB00158``, which is the real spelling of the real
contested accession. InChIKeys on records that join to the mini HMDB fixture are
synthetic (``KEY-00nn-N``), because that fixture's keys are.

**`mimedb_metabolites_v*.csv` rows, and what each one is for**

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
                                 NJC19 might need". Its real ``vmh_id`` holds
                                 **three** ids joined by ``; ``.
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
                                 (``KEY-0012-N``): the structural test. Its own
                                 ``metabolite_type`` would otherwise select it.
                                 Its ``microbe_relations`` is ``0`` — MiMeDB
                                 counting *no* related microbes, which is a
                                 different fact from the column being absent.
``L-Tyrosine`` / ``D-Tyrosine``  **both** claim ``HMDB0000158``, one padded and
                                 one legacy, exactly as the real dump spells
                                 them. A contested accession is not a join key:
                                 two records, two ``MIMEDB:`` nodes, two ledger
                                 rows — never one node with the other's
                                 annotations.
``Trimethylamine oxide``         ``detected = 1``: the ``observed`` rule. Its
                                 real ``vmh_id`` is two ids, ``M03054; tmao``.
``Microbial co-metabolite``      ``metabolite_type = Co-metabolite``: the
                                 ``origin-classified`` rule, MiMeDB's only
                                 evidence-graded axis.
``PC(16:0/18:1)``                a glycerophospholipid no rule selects — 41% of
                                 the real file looks like this, and loading it
                                 whole is how a microbiome graph becomes a
                                 lipidomics table.
``NULL-valued compound``         every optional column is the literal string
                                 ``NULL``, the v2-only four included. Read
                                 straight, that is the *string* "NULL" in the
                                 graph, which the audit counts as a present
                                 value. The real v2 dump fills
                                 ``microbe_relations`` on every row; this record
                                 exercises the absent case the dump's own NULL
                                 convention permits, so an empty count can never
                                 arrive as a ``0`` that reads as a measurement.
``Conjugated deoxycholate``      **v2 only, and the reason ``cmmc_inchikey`` is
                                 carried but never joined on.** Its
                                 ``cmmc_inchikey`` is HMDB's deoxycholic acid
                                 (``KEY-0016-N``) while its own
                                 ``moldb_inchikey`` is a different structure. On
                                 428 of the real file's 1,763 filled rows those
                                 two keys differ, so joining on ``cmmc_inchikey``
                                 would fold a modified compound onto its parent.
                                 This record must load.
===============================  ==============================================

**`mimedb_microbes_v*.csv`** carries organisms none of which is ever loaded —
the file has no compound column, so there is no edge to write. They exercise the
resolution report the prep prints: two exact (``Escherichia coli``,
``Akkermansia muciniphila``), one promoted from a strain id (``Escherichia coli
K-12``, taxid 83333 -> 562), one whose ``activity`` says ``Production (export)``
and one whose ``activity`` says ``Consumption (import)`` — **with no compound
anywhere on either row**, the column a careless loader would turn into a
``PRODUCES`` edge — and two more filling out the phenotype columns.

Two v2-only rows carry facts the v1 fixture got wrong or could not hold:

* a row whose ``data_source`` is ``NJS16`` and whose ``activity`` is empty. In
  the real dumps these two columns are **disjoint** — all 115 v2 activity rows
  have no ``data_source``, and all 63 ``NJS16`` rows have no ``activity`` — so
  the old fixture's single row carrying both encoded a provenance claim the
  files do not make;
* a fungus with **no** ``ncbi_tax_id``. Six of the real v2 file's 2,648 rows
  have none, so a report claiming every row carries one would be false.
"""

from __future__ import annotations

import csv
from pathlib import Path

OUT = Path(__file__).resolve().parent / "mimedb_mini"

#: The v1 dump's 42 columns, in order.
METABOLITE_COLUMNS_V1 = [
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

#: The v2 dump's 46 columns: v1's 42 in the same order, then four appended.
METABOLITE_COLUMNS_V2 = METABOLITE_COLUMNS_V1 + [
    "epa_substance_id", "epa_compound_id", "microbe_relations", "cmmc_inchikey",
]

#: The v1 dump's 39 columns, in order.
MICROBE_COLUMNS_V1 = [
    "id", "name", "microbe_id", "species", "kingdom", "phylum", "ncbi_tax_id",
    "activity", "gram", "oxygen_requirement", "created_at", "updated_at", "klass",
    "order", "family", "genus", "strain", "metabolism", "shape", "mobility",
    "flagella_presence", "number_of_membranes", "optimal_temperature",
    "temperature_range", "habitat", "biotic_relationship", "cell_arrangement",
    "sporulation", "energy_source", "superkingdom", "background", "health_type",
    "evidence_type", "data_source", "export", "human_pathogen", "genome_ids",
    "parent_id", "level",
]

#: The v2 dump's 44 columns: v1's 39 in the same order, then five appended.
MICROBE_COLUMNS_V2 = MICROBE_COLUMNS_V1 + [
    "subspecies", "serotype", "variant", "basys2_id", "description",
]

#: Only the columns a row actually sets; everything else becomes ``NULL``, which
#: is what the dump writes for an absent value. Keys the v1 header does not have
#: are dropped when the v1 file is written, which is what makes one record list
#: serve both releases.
METABOLITES: list[dict[str, str]] = [
    {"id": "1", "name": "Pectin", "mime_id": "MMDBc0000239",
     "moldb_inchikey": "PECTINKEY000001-UHFFFAOYSA-N", "moldb_formula": "C6H10O7",
     "moldb_average_mass": "194.1394", "classification": "Organooxygen compounds",
     "vmh_id": "pect", "microbe_relations": "67"},
    {"id": "2", "name": "Chitin", "mime_id": "MMDBc0000235",
     "moldb_inchikey": "CHITINKEY00001-UHFFFAOYSA-N", "moldb_formula": "C8H13NO5",
     "hmdb_id": "HMDB0003362", "vmh_id": "chtn; M01437; M01436",
     "epa_substance_id": "DTXSID801100881", "epa_compound_id": "DTXCID201532583",
     "microbe_relations": "36"},
    {"id": "3", "name": "Butyrate salt", "mime_id": "MMDBc0000011",
     "hmdb_id": "HMDB00011", "detected": "1", "quantified": "1",
     "moldb_inchikey": "FERIUCNNQQJTOY-UHFFFAOYSA-M", "moldb_formula": "C4H7O2",
     "vmh_id": "but", "epa_substance_id": "DTXSID8021515",
     "epa_compound_id": "DTXCID401515", "microbe_relations": "778"},
    {"id": "4", "name": "Acetic acid", "mime_id": "MMDBc0000012",
     "metabolite_type": "Primary", "moldb_inchikey": "MIMEDBACETIC01-UHFFFAOYSA-N",
     "moldb_formula": "C2H4O2", "vmh_id": "ac",
     "epa_substance_id": "DTXSID5024394", "epa_compound_id": "DTXCID304394",
     "microbe_relations": "2537"},
    {"id": "5", "name": "Ethanoic acid", "mime_id": "MMDBc0000013",
     "metabolite_type": "Co-metabolite", "moldb_inchikey": "KEY-0012-N",
     "moldb_formula": "C2H4O2", "microbe_relations": "0"},
    {"id": "6", "name": "L-Tyrosine", "mime_id": "MMDBc0000158",
     "hmdb_id": "HMDB0000158", "metabolite_type": "Co-metabolite",
     "moldb_inchikey": "OUYCCCASQSFEME-QMMMGPOBSA-N", "moldb_formula": "C9H11NO3",
     "vmh_id": "tyr_L", "epa_substance_id": "DTXSID1023730",
     "epa_compound_id": "DTXCID603730", "microbe_relations": "1743"},
    # The real v2 dump spells this one's accession in the legacy five-digit form,
    # so the record is both halves of the identity problem at once: it needs
    # padding-normalisation to be *recognised*, and once recognised it is
    # contested and therefore refused as a join key.
    {"id": "7", "name": "D-Tyrosine", "mime_id": "MMDBc0000159",
     "hmdb_id": "HMDB00158", "metabolite_type": "Co-metabolite",
     "moldb_inchikey": "OUYCCCASQSFEME-MRVPVSSYSA-N", "moldb_formula": "C9H11NO3",
     "epa_substance_id": "DTXSID50883441", "epa_compound_id": "DTXCID601022972",
     "microbe_relations": "4"},
    {"id": "8", "name": "Trimethylamine oxide", "mime_id": "MMDBc0000014",
     "detected": "1", "quantified": "1",
     "moldb_inchikey": "UYPYRKYUKCHHIB-UHFFFAOYSA-N", "moldb_formula": "C3H9NO",
     "cas": "1184-78-7", "vmh_id": "M03054; tmao",
     "epa_substance_id": "DTXSID8049678", "epa_compound_id": "DTXCID5029637",
     "microbe_relations": "146"},
    {"id": "9", "name": "Microbial co-metabolite", "mime_id": "MMDBc0000015",
     "metabolite_type": "Co-metabolite",
     "moldb_inchikey": "COMETABOLITE01-UHFFFAOYSA-N", "moldb_formula": "C7H6O2",
     "microbe_relations": "1"},
    {"id": "10", "name": "PC(16:0/18:1)", "mime_id": "MMDBc0049000",
     "moldb_inchikey": "PHOSPHOLIPID01-UHFFFAOYSA-N",
     "classification": "Glycerophospholipids", "microbe_relations": "0"},
    {"id": "11", "name": "NULL-valued compound", "mime_id": "MMDBc0000016",
     "metabolite_type": "Primary",
     "moldb_inchikey": "NULLVALUEDCMP1-UHFFFAOYSA-N"},
]

#: Records the v2 dump has and v1 does not. Keeping them separate is what makes
#: "v2 selects more than v1" a *counted* difference rather than a claim.
METABOLITES_V2_ONLY: list[dict[str, str]] = [
    {"id": "12", "name": "Conjugated deoxycholate", "mime_id": "MMDBc0060001",
     "detected": "1", "quantified": "1",
     "moldb_inchikey": "CONJDEOXYCHOL1-UHFFFAOYSA-N", "moldb_formula": "C26H43NO5",
     "cmmc_inchikey": "KEY-0016-N", "microbe_relations": "5",
     "classification": "Steroids and steroid derivatives"},
]

MICROBES: list[dict[str, str]] = [
    {"id": "1", "name": "Escherichia coli", "microbe_id": "MMDBm0000001",
     "species": "Escherichia coli", "ncbi_tax_id": "562", "genus": "Escherichia",
     "family": "Enterobacteriaceae", "phylum": "Pseudomonadota",
     "superkingdom": "Bacteria", "gram": "Negative",
     "oxygen_requirement": "Facultative anaerobe", "human_pathogen": "1",
     "basys2_id": "BASYS2-000001"},
    {"id": "2", "name": "Akkermansia muciniphila", "microbe_id": "MMDBm0000002",
     "species": "Akkermansia muciniphila", "ncbi_tax_id": "239935",
     "genus": "Akkermansia", "superkingdom": "Bacteria", "gram": "Negative",
     "oxygen_requirement": "Anaerobe", "habitat": "Host-associated",
     "description": "Akkermansia muciniphila is a mucin-degrading anaerobe of "
                    "the human gut whose metabolite output is studied in "
                    "metabolic disease. This sentence is prose: it names no "
                    "compound in a column, and nothing here is an edge."},
    # A strain-level taxid: `reconcile` promotes it to 562, and this row is the
    # one that makes the prep's `promoted` count non-zero.
    {"id": "3", "name": "Escherichia coli K-12", "microbe_id": "MMDBm0000003",
     "species": "Escherichia coli", "ncbi_tax_id": "83333",
     "strain": "Escherichia coli K-12", "superkingdom": "Bacteria",
     "subspecies": "K-12"},
    # `activity` says this organism produces something, and names nothing. This
    # row is the whole argument for why MiMeDB writes no PRODUCES edge: it is
    # the only column in either dump that looks like a relation, and it has no
    # object. Its `data_source` is empty, as it is on all 115 real activity rows.
    {"id": "4", "name": "Faecalibacterium prausnitzii", "microbe_id": "MMDBm0000004",
     "species": "Faecalibacterium prausnitzii", "ncbi_tax_id": "853",
     "activity": "Production (export)",
     "superkingdom": "Bacteria", "oxygen_requirement": "Anaerobe"},
    # The other half of the same column's vocabulary, and equally objectless.
    {"id": "5", "name": "Bacteroides thetaiotaomicron", "microbe_id": "MMDBm0000005",
     "species": "Bacteroides thetaiotaomicron", "ncbi_tax_id": "818",
     "activity": "Consumption (import)",
     "genus": "Bacteroides", "superkingdom": "Bacteria", "gram": "Negative",
     "sporulation": "Nonsporulating"},
    {"id": "6", "name": "Bifidobacterium longum", "microbe_id": "MMDBm0000006",
     "species": "Bifidobacterium longum", "ncbi_tax_id": "216816",
     "genus": "Bifidobacterium", "superkingdom": "Bacteria", "gram": "Positive"},
]

#: Rows the v2 dump has and v1 does not — see the module docstring.
MICROBES_V2_ONLY: list[dict[str, str]] = [
    {"id": "7", "name": "Clostridium perfringens", "microbe_id": "MMDBm0000007",
     "species": "Clostridium perfringens", "ncbi_tax_id": "1502",
     "data_source": "NJS16", "superkingdom": "Bacteria",
     "oxygen_requirement": "Anaerobe"},
    {"id": "8", "name": "Aureobasidium pullulans R106", "microbe_id": "MMDBm0000008",
     "species": "Aureobasidium pullulans", "kingdom": "Fungi",
     "superkingdom": "Eukaryota", "strain": "R106"},
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
    print(f"wrote {path} ({len(rows)} rows, {len(columns)} columns)")


def main() -> None:
    write(OUT / "mimedb_metabolites_v1.csv", METABOLITE_COLUMNS_V1, METABOLITES)
    write(OUT / "mimedb_microbes_v1.csv", MICROBE_COLUMNS_V1, MICROBES)
    write(OUT / "mimedb_metabolites_v2.csv", METABOLITE_COLUMNS_V2,
          METABOLITES + METABOLITES_V2_ONLY)
    write(OUT / "mimedb_microbes_v2.csv", MICROBE_COLUMNS_V2,
          MICROBES + MICROBES_V2_ONLY)


if __name__ == "__main__":
    main()

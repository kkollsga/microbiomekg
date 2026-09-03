#!/usr/bin/env python3
"""Regenerate ``tests/fixtures/maier2018_mini/`` — four cut-down workbooks.

The fixtures are committed ``.xlsx`` files, which nobody can review by reading.
This script is the reviewable half: every drug, every isolate and every screen
cell is listed below with the trap it exists to make fail loudly, and the sheet
names, the header rows and table 2's title/sub-heading rows are the real files'
exactly — the loader finds table 2's header by searching for ``NT data base``
and table 3's species columns by their ``(NT####)`` suffix, so a fixture that
tidied either would not exercise the code that reads the real workbooks.

Run it only when the fixtures need to change::

    .venv/bin/python tests/fixtures/make_maier2018_mini.py

Every organism resolves against ``tests/fixtures/taxdump_mini/`` or is here
*because* it does not, and every drug reaches a ``Drug`` node
``tests/fixtures/chembl_mini/`` produces or is here because none of the three
routes does. ``n_hit`` is **computed from the p-values below** rather than typed
in, so the loader's threshold re-derivation — which refuses to write when
``HIT_THRESHOLD`` stops reproducing that column — runs against the sheet's own
arithmetic here exactly as it does against the real one.

**The isolates (table 2)**

===========  =========================================  =========================
NT code      ``Species`` string                         the trap
===========  =========================================  =========================
NT5004       ``Bacteroides thetaiotaomicron``           the ordinary case: a name
                                                        ``names.dmp`` spells,
                                                        reached with no
                                                        derivation.
NT5003       ``Bacteroides fragilis nontoxigenic``      a **toxigenicity
                                                        phenotype inline in the
                                                        species column**. No
                                                        ``names.dmp`` entry
                                                        spells it, so without
                                                        ``SPECIES_OVERRIDES`` it
                                                        becomes a tombstone
                                                        asserting NCBI lost
                                                        *B. fragilis* — false,
                                                        and in the real file it
                                                        costs 2,394 edges.
NT5033       ``Bacteroides fragilis enterotoxigenic``   the **second isolate of
             ``(ET)``                                   the same species**: two
                                                        edges per drug on one
                                                        taxon, told apart by
                                                        ``nt_code`` and
                                                        ``strain``, never merged.
NT5084       ``Escherichia coli K-12``                  a strain designation NCBI
                                                        *does* carry: promoted to
                                                        the species with
                                                        ``original_rank`` kept as
                                                        ``strain`` (G5).
NT5028       ``Bifidobacterium longum subsp.``          a subspecies, promoted the
             ``infantis``                               same way. The screen's own
                                                        NT5028 is *subsp. longum*;
                                                        the mini taxdump carries
                                                        *infantis*, and the
                                                        promotion under test is
                                                        the same.
NT5099       ``Nonexistiblia inventata``                an organism no taxonomy
                                                        carries: an
                                                        ``UnresolvedTaxon``
                                                        tombstone **and** a ledger
                                                        row, never a drop (G2).
NT5085       *(no ``Species`` value)*                   table 2's second laboratory
                                                        *E. coli* row. It names no
                                                        organism and is not a
                                                        screened column, so the
                                                        reader must skip it
                                                        without ledgering it as a
                                                        loss.
===========  =========================================  =========================

**The drugs (tables 1 and 3)**

=============  ==============================  =============================
prestwick_ID   ``chemical name``               the trap
=============  ==============================  =============================
Prestw-1109    ``Vancomycin``                  the ``name`` route: ChEMBL
                                               knows it as ``VANCOMYCIN`` and
                                               a casefolded exact match
                                               reaches it. Hits every isolate,
                                               which is what an antibiotic row
                                               looks like in the real screen.
Prestw-1203    ``Paracetamol``                 the ``atc`` route, and a real
                                               reason it has to exist: ChEMBL's
                                               ``pref_name`` is
                                               ``ACETAMINOPHEN``, so the name
                                               route finds nothing and
                                               ``N02BE01`` is the only way to
                                               the node.
Prestw-117     ``Ampicillin sodium``           the ``salt-name`` route: the
                                               catalogue names a salt, ChEMBL
                                               keys on the parent, and the ATC
                                               cell is ``-`` so nothing but the
                                               suffix strip can get there.
Prestw-9998    ``Aspirin``                     one cell written ``NA``: the
                                               screen measured this pair as
                                               neither a hit nor a non-hit, so
                                               it must be a ledger row and
                                               **no edge of either type**.
Prestw-9999    ``Fictitine hydrochloride``     no route reaches ChEMBL: a
                                               minted ``PRESTWICK:`` node with
                                               ``approved = false``, its
                                               PubChem CID off the STITCH id,
                                               and its edges intact.
=============  ==============================  =============================

Table 4 contributes two rows, and they are the check that the authors' own
confusion matrix lands on the right relationship: a ``TP`` can only ever sit on
an ``INHIBITS_GROWTH_OF`` edge and a ``TN`` only on a
``DOES_NOT_INHIBIT_GROWTH_OF`` one. The ``>`` on the ``TN`` row is the source's
own wording for "no inhibition up to the highest concentration tested" — the
bounded negative this source exists to carry.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

OUT = Path(__file__).resolve().parent / "maier2018_mini"

#: The isolate columns of the fixture screen, in table-3 order. ``NT5085`` is
#: deliberately absent: it is in table 2 and is not a screened column, which is
#: what the real workbooks do with the two laboratory *E. coli* rows.
SCREENED = ["NT5004", "NT5003", "NT5033", "NT5084", "NT5028", "NT5099"]

#: ``NT code -> the label table 3 puts in its column header``. The label is a
#: display spelling and differs from table 2's ``Species`` string on purpose —
#: the NT code is the only stable join between the two sheets, which is why the
#: loader reads the code out of the header rather than the name.
COLUMN_LABEL = {
    "NT5004": "Bacteroides thetaiotaomicron",
    "NT5003": "Bacteroides fragilis (NT)",
    "NT5033": "Bacteroides fragilis (ET)",
    "NT5084": "E. coli wt",
    "NT5028": "Bifidobacterium longum",
    "NT5099": "Nonexistiblia inventata",
}

SPECIES_HEADER = (
    "NT data base", "Phylum", "Class", "Order", "Family", "Genus", "Species",
    "Strain", "Source", "Gram stain", "Medium preference",
    "Starting OD (96 well screen)", "Starting OD (384 well screen)",
)

SPECIES_ROWS: list[tuple] = [
    ("NT5004", "Bacteroidetes", "Bacteroidia", "Bacteroidales", "Bacteroidaceae",
     "Bacteroides", "Bacteroides thetaiotaomicron", "E50(VPI 5482)",
     "DSM No.: 2079", "negative", "mGAM", 0.01, 0.05),
    ("NT5003", "Bacteroidetes", "Bacteroidia", "Bacteroidales", "Bacteroidaceae",
     "Bacteroides", "Bacteroides fragilis nontoxigenic", "EN-2, VPI 2553",
     "DSM No.: 2151", "negative", "mGAM", 0.01, 0.05),
    ("NT5033", "Bacteroidetes", "Bacteroidia", "Bacteroidales", "Bacteroidaceae",
     "Bacteroides", "Bacteroides fragilis enterotoxigenic (ET)", "20656-2- 1",
     "ATCC No.: 43860", "negative", "mGAM", 0.01, 0.05),
    ("NT5028", "Actinobacteria", "Actinobacteria", "Bifidobacteriales",
     "Bifidobacteriaceae", "Bifidobacterium",
     "Bifidobacterium longum subsp. infantis", "type strain, E194b (Variant a)",
     "DSM No.: 20219", "positive", "mGAM", 0.01, 0.05),
    ("NT5099", "Firmicutes", "Clostridia", "Eubacteriales", "Lachnospiraceae",
     "Nonexistiblia", "Nonexistiblia inventata", "type strain",
     "DSM No.: 99999", "positive", "mGAM", 0.01, 0.05),
    ("Laboratory E. coli strains", None, None, None, None, None, None, None,
     None, None, None, None, None),
    ("NT5084", "Proteobacteria", "Gammaproteobacteria", "Enterobacterales",
     "Enterobacteriaceae", "Escherichia", "Escherichia coli K-12", "BW25113",
     "Keio collection", "negative", "LB", 0.01, 0.05),
    ("NT5085", None, None, None, None, None, None, None, None, "negative",
     "LB", 0.01, 0.05),
]

DRUG_HEADER = (
    "prestwick_ID", "chemical name", "STITCH4 id", "ATC codes", "target species",
    "dose (µmol)", "estimated intestine concentration (µM)",
    "plasma concentration (µM)", "source for plasma concentration",
    "fraction excreted in feces", "fraction excreted in urine",
    "source for excretion data", "estimated colon concentration (µM)",
    "molecular weight (g/mol)", "XLogP", "TPSA (Å²)", "Complexity",
    "Volume3D (Å³)", "screen conc. (20 µM as µg/ml)",
)

#: ``(prestwick_ID, name, STITCH4 id, ATC codes, target species)`` — the five
#: columns of table 1 the loader reads. The other fourteen are padding.
DRUG_ROWS: list[tuple] = [
    ("Prestw-1109", "Vancomycin", "CID100014969", "J01XA01", "bacteria"),
    ("Prestw-1203", "Paracetamol", "CID100001983", "N02BE01", "human"),
    ("Prestw-117", "Ampicillin sodium", "CID100006249", "-", "bacteria"),
    ("Prestw-9998", "Aspirin", "CID100002244", "B01AC06 N02BA01", "human"),
    ("Prestw-9999", "Fictitine hydrochloride", "CID100099999", "-", "human"),
]

#: ``prestwick_ID -> (drug_class, {NT code: adjusted p, or "NA"})``.
SCREEN: dict[str, tuple[str, dict[str, object]]] = {
    # An antibiotic: a hit on everything, which is the shape 144 rows of the
    # real table have.
    "Prestw-1109": ("antibiotics", {
        "NT5004": 5.038336442866676e-06, "NT5003": 8.817322808260415e-06,
        "NT5033": 8.05110203715617e-06, "NT5084": 5.038336442866676e-06,
        "NT5028": 6.453277773277476e-07, "NT5099": 1.968777209389108e-06,
    }),
    # A human-targeted drug with one hit and four measured non-hits — the 24%
    # of the real screen, and the pair table 4 validates as `TP`.
    "Prestw-1203": ("human-targeted drugs", {
        "NT5004": 5.038336442866676e-06, "NT5003": 0.9999999999999964,
        "NT5033": 0.4354997866541382, "NT5084": 0.8146121134226613,
        "NT5028": 0.3923918558461689, "NT5099": 0.5,
    }),
    "Prestw-117": ("antibiotics", {
        "NT5004": 1.002988566725697e-05, "NT5003": 5.922866839744848e-06,
        "NT5033": 6.135419048211278e-06, "NT5084": 0.0006829658048741004,
        "NT5028": 1.095230573534376e-05, "NT5099": 0.7,
    }),
    # `NA` on one pair: measured as neither a hit nor a non-hit.
    "Prestw-9998": ("human-targeted drugs", {
        "NT5004": 0.3923918558461689, "NT5003": "NA",
        "NT5033": 0.6, "NT5084": 0.7, "NT5028": 0.8, "NT5099": 0.9,
    }),
    "Prestw-9999": ("human-targeted drugs", {
        "NT5004": 0.0001, "NT5003": 0.4, "NT5033": 0.5, "NT5084": 0.6,
        "NT5028": 0.7, "NT5099": 0.8,
    }),
}

VALIDATION_HEADER = (
    "chemical_name", "prestwick_ID", "strain_name", "NT_code",
    "validation outcome", "qualifier (IC25)", "IC25 (μM)", "IC25 (μg/ml)",
    "qualifier (MIC)", "MIC (μM)", "MIC (μg/ml)",
)

VALIDATION_ROWS: list[tuple] = [
    ("Paracetamol", "Prestw-1203", "Bacteroides thetaiotaomicron", "NT5004",
     "TP", "=", 5, 0.650386115, "=", 10, 1.30077223),
    ("Paracetamol", "Prestw-1203", "Escherichia coli K-12", "NT5084",
     "TN", ">", 160, 20.81235568, ">", 160, 20.81235568),
]


def _book(sheet_title: str) -> tuple:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = sheet_title
    return book, sheet


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    book, sheet = _book("S1a. Prestwick_Libery")
    sheet.append(list(DRUG_HEADER))
    for row in DRUG_ROWS:
        sheet.append(list(row) + [None] * (len(DRUG_HEADER) - len(row)))
    book.save(OUT / "NIHMS76168-supplement-Supplementary_table_1.xlsx")

    book, sheet = _book("S2. Species selection")
    # The real sheet's title line and blank row. The loader finds its header by
    # searching for `NT data base`; a fixture without these would not exercise
    # that, and a fixed row skip would pass here and break on the real file.
    sheet.append(["Isolates of the human microbiota used in this study"])
    sheet.append([None])
    sheet.append(list(SPECIES_HEADER))
    for row in SPECIES_ROWS:
        sheet.append(list(row))
    book.save(OUT / "NIHMS76168-supplement-Supplementary_table_2.xlsx")

    book, sheet = _book("S3a. Adjusted p-values")
    sheet.append(["prestwick_ID", "chemical_name", "drug_class", "n_hit"]
                 + [f"{COLUMN_LABEL[c]} ({c})" for c in SCREENED])
    for prestwick, name, *_rest in DRUG_ROWS:
        drug_class, cells = SCREEN[prestwick]
        values = [cells[code] for code in SCREENED]
        # Computed, never typed: this is the column the loader re-derives the
        # hit threshold against, so a hand-written count would make that check
        # a tautology here and a surprise on the real file.
        n_hit = sum(1 for v in values if isinstance(v, float) and v < 0.01)
        sheet.append([prestwick, name, drug_class, n_hit, *values])
    book.save(OUT / "NIHMS76168-supplement-Supplementary_table_3.xlsx")

    book, sheet = _book("S4. MICs")
    sheet.append(list(VALIDATION_HEADER))
    for row in VALIDATION_ROWS:
        sheet.append(list(row))
    book.save(OUT / "NIHMS76168-supplement-Supplementary_table_4.xlsx")

    print(f"wrote 4 workbooks to {OUT}: {len(DRUG_ROWS)} drugs x "
          f"{len(SCREENED)} isolates = {len(DRUG_ROWS) * len(SCREENED)} cells")


if __name__ == "__main__":
    main()

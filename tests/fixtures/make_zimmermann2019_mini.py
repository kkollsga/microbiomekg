#!/usr/bin/env python3
"""Regenerate ``tests/fixtures/zimmermann2019_mini/`` — one cut-down workbook.

The fixture is a committed ``.xlsx`` file, which nobody can review by reading.
This script is the reviewable half: every strain, every drug, every screen cell
and every gene is listed below with the trap it exists to make fail loudly, and
the sheet names, the two header rows, table 1's plasmid tail and table 2's
column-description block are the real workbook's exactly — the loader finds
table 1's organisms by a header cell and an end marker, table 2's drugs by a
blank row, and table 3's five sub-columns by their labels, so a fixture that
tidied any of them would not exercise the code that reads the real file.

Run it only when the fixture needs to change::

    .venv/bin/python tests/fixtures/make_zimmermann2019_mini.py

Every organism resolves against ``tests/fixtures/taxdump_mini/`` or is here
*because* it does not, and every drug reaches a ``Drug`` node that
``tests/fixtures/chembl_mini/`` or ``tests/fixtures/maier2018_mini/`` produces,
or is here because none of the three routes does.

**The strains (table 1, and the columns of table 3 that name them)**

=====================================  ========================================
table 3 column header                  the trap
=====================================  ========================================
``Bacteroides thetaiotaomicron         the ordinary case: name + collection
VPI-5482``                             number, reached with no derivation.
``Bacteroides fragilis NCTC9343``      **two isolates of one species**: two
``Bacteroides fragilis DS-208``        edges per drug on one taxon, told apart
                                       by ``screen_column`` and ``strain``,
                                       never merged — and the reason a bare
                                       ``Bacteroides fragilis`` is *not* a join
                                       key, since it would match both.
``Control pH 7``                       **an abiotic degradation control sitting
                                       between two strain columns**, with the
                                       same five sub-columns. Its cells are a
                                       hit for the first drug. It must become
                                       no edge and one ledger row.
``Escherichia coli  K-12``             table 3 names the lineage where table 1
                                       names the Keio strain (``BW25113``), and
                                       the header carries the real file's
                                       double space. Only ``COLUMN_OVERRIDES``
                                       reaches the row.
``Escherichia coli O157:H7``           **the second column of the same species
                                       as the one above**, and the donor of the
                                       gene products below — so the gene join
                                       has to pick one of two *E. coli* columns
                                       rather than attaching to both, which is
                                       the real file's *B. thetaiotaomicron*
                                       situation in miniature.
``Bifidobacterium longum subsp.``      a **subspecies**, promoted to the species
``infantis CCUG52486``                 with ``original_rank`` kept (G5).
``Lactobacillus  reuteri CF48-3A       a **strain designation inside the species
BEI HM-102``                           name**: no ``names.dmp`` entry spells it,
                                       so ``SPECIES_OVERRIDES`` is what stops a
                                       tombstone claiming NCBI has lost
                                       *L. reuteri*.
``Faecalibacterium prausnitzii``       a **fecal isolate**: table 1's reference
                                       is the words ``fecal isolate`` and the
                                       column header carries no designation at
                                       all, so the name-only key is the only
                                       route.
``Bacteroides WH2 WH2``                an isolate NCBI holds **two** candidates
                                       for and nothing in the row chooses
                                       between: an ``UnresolvedTaxon``
                                       tombstone, a ledger row naming both, and
                                       no edges (G2).
=====================================  ========================================

Table 1 then continues into the *B. thetaiotaomicron* mutant background and a
plasmid, exactly as the real sheet does. Those are not organisms and the reader
must stop at them rather than counting them as isolates.

**The drugs (tables 2 and 3)**

============================  ==============================================
``MOLENAME``                  the trap
============================  ==============================================
``VANCOMYCIN``                the ``molename`` route: ChEMBL knows it by that
                              name and a casefolded exact match reaches it.
``PARACETAMOL``               the ``parent-name`` route, and a real reason it
                              has to exist: ChEMBL's ``pref_name`` is
                              ``ACETAMINOPHEN``, and the file's own ``name``
                              column is the only spelling that gets there.
``AMPICILLIN SODIUM``         the ``salt-name`` route: the screen names a
                              salt, ChEMBL keys on the parent, and the file's
                              ``name`` column repeats the salt spelling, so
                              nothing but the suffix strip reaches it.
``FICTITINE HYDROCHLORIDE``   **the compound only the other screen has a node
                              for.** Maier mints ``PRESTWICK:Prestw-9999``
                              for it; this prep must land on that node rather
                              than mint a second one, which is what
                              ``DEPENDS_ON = [chembl, maier2018]`` buys.
``METFORMIN HYDROCHLORIDE``   the interaction between this screen's salt
                              spellings and ``Drug``'s parent keying: ChEMBL
                              curates ``METFORMIN HYDROCHLORIDE`` and this
                              graph collapses it onto ``METFORMIN``, so the
                              screened name reaches **nothing** and the
                              parent-name column is what saves the compound.
``INVENTOL MESYLATE``         no route reaches anything: a minted
                              ``ZIMMERMANN2019:`` node with ``approved =
                              false``, its CAS and trade name off table 2, and
                              its edges intact.
============================  ==============================================

Two routes reaching **different** nodes is the one drug trap this fixture
cannot carry — every ``Drug`` here is a parent molecule, so no two spellings
can disagree. ``microbiomekg.drugs.join_drug`` is unit-tested on it in
``tests/test_drugs.py`` and the real build has three, asserted in
``tests/test_acceptance.py``.

**The cells.** ``AMPICILLIN SODIUM`` x ``Escherichia coli  K-12`` is written
**blank** — the real workbook leaves no cell out of all 20,596, and that is
worth knowing rather than trusting, so the fixture carries the case the real
file does not: it must be a ledger row and **no edge of either type**.
``PARACETAMOL`` x *B. thetaiotaomicron* sits at exactly ``p = 0.05`` and
``FICTITINE HYDROCHLORIDE`` x *L. reuteri* at exactly ``% consumed = the drug's
threshold`` — both boundaries are inclusive, and both flip the answer if the
comparison is written the other way. ``PARACETAMOL`` x *B. fragilis* DS-208 is
the near miss from the other side: significant, one point below the threshold.

**The genes (table 13).** Four rows against a sheet whose columns alternate a
parent drug with the metabolite masses detected from it, so the reader has to
filter on the ``Parent drug`` sub-header rather than take every column:

* ``Z_0152`` metabolises ``Vancomycin`` and ``Paracetamol``. Its PATRIC id
  carries NCBI taxid 83334, which promotes to *E. coli* — the species of **two**
  screened columns — and whose strain name contains only the ``O157:H7``
  column's own designation, never the other's ``BW25113``. So the gene block
  lands on exactly one of the two columns; ``Vancomycin`` is a hit there and
  ``Paracetamol`` is not.
* ``Z_2068`` metabolises ``Metformin hydrochloride``, which the screen scored as
  a **non-hit** for the same organism.

  Those last two are the disagreement this fixture exists to keep visible: the
  genes were identified by expressing a library in *E. coli*, not in the
  screened strains, so a gene can metabolise a drug its donor did not touch in
  culture. Five of the real file's 37 gene-supported pairs are that shape, and
  they sit on ``DOES_NOT_METABOLISE`` edges rather than being dropped or moved
  onto the hit edge.
* ``COLAER_00311`` names a genome (taxid 411903) no screened column is: a ledger
  row, never an attachment to the nearest organism.
* ``FAKE_0001`` carries something that is not a PATRIC id at all: a ledger row
  for the same reason, by a different path.

**The published-matrix triple this fixture satisfies is ``6,9,5``** — six drugs,
nine strain columns (the control excluded), and five of the six metabolised by
at least one of them, ``METFORMIN HYDROCHLORIDE`` being the sixth. It is printed
at the end of a run and asserted in ``tests/test_zimmermann2019.py``, so the
prep's headline gate runs against this workbook's own arithmetic on exactly the
code path the real build uses.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

OUT = Path(__file__).resolve().parent / "zimmermann2019_mini"
WORKBOOK = "41586_2019_1291_MOESM1_ESM.xlsx"

#: ``(Name, Phylum, Reference)`` — supplementary table 1's three columns, for
#: the organism block only.
STRAIN_ROWS: list[tuple[str, str, str]] = [
    ("Bifidobacterium longum subsp. Infantis", "Actinobacteria", "CCUG52486"),
    ("Bacteroides fragilis", "Bacteroidetes", "NCTC 9343"),
    ("Bacteroides fragilis", "Bacteroidetes", "DS-208"),
    ("Bacteroides thetaiotaomicron", "Bacteroidetes", "VPI-5482"),
    ("Bacteroides WH2", "Bacteroidetes", "WH2"),
    ("Faecalibacterium prausnitzii", "Firmicutes", "fecal isolate"),
    ("Lactobacillus  reuteri CF48-3A", "Firmicutes", "BEI HM-102"),
    ("Escherichia coli  ", "Proteobacteria", "BW25113"),
    ("Escherichia coli", "Proteobacteria", "O157:H7"),
]

#: Supplementary table 3's measured columns, in sheet order. The control is
#: **fourth**, between two strain columns, because that is where the real sheet
#: puts its four and it is the whole reason they cannot be found structurally.
COLUMNS: list[str] = [
    "Bacteroides thetaiotaomicron VPI-5482",
    "Bacteroides fragilis NCTC9343",
    "Bacteroides fragilis DS-208",
    "Control pH 7 ",
    "Escherichia coli  K-12",
    "Escherichia coli O157:H7",
    "Bifidobacterium longum subsp. infantis CCUG52486",
    "Lactobacillus  reuteri CF48-3A BEI HM-102",
    "Faecalibacterium prausnitzii ",
    "Bacteroides WH2 WH2",
]

#: ``MOLENAME -> (TherapeuticIndication, TradeName, cas, parent name, SMILES)``.
#: The parent ``name`` column is what makes ``PARACETAMOL`` reachable and what
#: makes ``METFORMIN HYDROCHLORIDE`` reach two nodes; where it repeats the
#: screened spelling, only the salt strip can get anywhere.
DRUG_ROWS: dict[str, tuple[str, str, str, str, str]] = {
    "VANCOMYCIN": ("antibiotic", "VANCOCIN", "1404-90-6", "Vancomycin", "CC1C(C)O"),
    "PARACETAMOL": (
        "analgesic, antipyretic",
        "TYLENOL",
        "103-90-2",
        "Acetaminophen",
        "CC(=O)Nc1ccc(O)cc1",
    ),
    "AMPICILLIN SODIUM": (
        "antibiotic",
        "OMNIPEN",
        "69-52-3",
        "Ampicillin sodium",
        "CC1(C)SC2C(N)C(=O)N2C1C(=O)[O-]",
    ),
    "FICTITINE HYDROCHLORIDE": (
        "antifictional",
        "FICTIVAN",
        "99999-99-9",
        "Fictitine hydrochloride",
        "CCN.Cl",
    ),
    "METFORMIN HYDROCHLORIDE": (
        "antidiabetic",
        "GLUCOPHAGE",
        "1115-70-4",
        "Metformin",
        "CN(C)C(=N)NC(N)=N.Cl",
    ),
    "INVENTOL MESYLATE": (
        "sedative",
        "INVENTA",
        "88888-88-8",
        "Inventol mesylate",
        "CCCO.CS(=O)(=O)O",
    ),
}

#: ``MOLENAME -> (drug adaptive FC threshold %, {column: (% consumed, p(FDR))})``.
#: A column left out of the inner dict is an ordinary non-hit filled in below; a
#: column mapped to ``None`` is written **blank**, which is the pair the screen
#: did not measure.
SCREEN: dict[str, tuple[float, dict[str, object]]] = {
    # Two hits, one of them on the control column — which is exactly what an
    # abiotic control looks like when it is read as a strain.
    "VANCOMYCIN": (
        20.0,
        {
            "Bacteroides thetaiotaomicron VPI-5482": (45.0, 0.001),
            "Bacteroides fragilis NCTC9343": (60.0, 0.01),
            "Escherichia coli O157:H7": (52.0, 0.002),
            "Control pH 7 ": (80.0, 0.001),
            "Bacteroides WH2 WH2": (50.0, 0.001),
        },
    ),
    # The p boundary, and it is this drug's **only** hit — so writing the
    # comparison as `<` takes the whole drug out of the metabolised count and
    # trips the prep's headline gate rather than only moving an edge total,
    # which is what it does on the real file (176 becomes 175).
    "PARACETAMOL": (
        25.0,
        {
            "Bacteroides thetaiotaomicron VPI-5482": (30.0, 0.05),
            # Deeply depleted and not significant, on the column whose gene the
            # gain-of-function screen says metabolises this drug: the second of the
            # fixture's two disagreements between the two experiments.
            "Escherichia coli O157:H7": (40.0, 0.2),
            # And the near miss from the other side: significant, one point below
            # the drug's own threshold. A flat 20% floor would call it a hit.
            "Bacteroides fragilis DS-208": (24.0, 0.001),
            "Escherichia coli  K-12": (28.0, 0.2),
        },
    ),
    # One measurement written blank: neither a hit nor a non-hit.
    "AMPICILLIN SODIUM": (
        20.0,
        {
            "Bifidobacterium longum subsp. infantis CCUG52486": (55.0, 0.004),
            "Escherichia coli  K-12": None,
        },
    ),
    # `% consumed` exactly at the threshold: the other inclusive boundary.
    "FICTITINE HYDROCHLORIDE": (
        30.0,
        {
            "Lactobacillus  reuteri CF48-3A BEI HM-102": (30.0, 0.02),
        },
    ),
    # No strain touches it — so the gene product table 13 names for it lands on
    # a DOES_NOT_METABOLISE edge, which is the disagreement worth keeping.
    "METFORMIN HYDROCHLORIDE": (20.0, {}),
    # The minted drug still gets its edges.
    "INVENTOL MESYLATE": (
        20.0,
        {
            "Faecalibacterium prausnitzii ": (70.0, 0.001),
        },
    ),
}

#: ``(RefSeq locus tag, PATRIC ID, Product, Protein ID, {parent drug label})``.
GENE_ROWS: list[tuple[str, str, str, str, set[str]]] = [
    (
        "Z_0152",
        "fig|83334.1.peg.149",
        "acetyl esterase (acetylxylosidase)",
        "NP_809065.1",
        {"Vancomycin", "Paracetamol"},
    ),
    (
        "Z_2068",
        "fig|83334.1.peg.2127",
        "3-oxo-5-alpha-steroid 4-dehydrogenase",
        "NP_810981.1",
        {"Metformin hydrochloride"},
    ),
    (
        "COLAER_00311",
        "fig|411903.6.peg.275",
        "hypothetical protein",
        "ZP_01771332.1",
        {"Vancomycin"},
    ),
    ("FAKE_0001", "not-a-patric-id", "invented protein", "XX_000000.1", {"Vancomycin"}),
]

#: The parent drugs table 13 scores, and the metabolite-mass column that follows
#: each — the sheet interleaves them and only the ``Parent drug`` ones are read.
GENE_DRUG_COLUMNS: list[str] = [
    "Vancomycin",
    "Paracetamol",
    "Metformin hydrochloride",
]

DRUG_HEADER = (
    "MOLENAME",
    "TherapeuticIndication",
    "TargetedRT",
    "TargetedMZ",
    "DrugPoolNumbers",
    "EstimatedColonConcentrationMaier2018uM",
    "SMILES",
    "STATUS",
    "TradeName",
    "cas",
    "iupacName",
    "name",
    "ref",
    "salt_name",
    "salt_smiles",
    "smiles",
    "source",
)

#: The block the real sheet puts *after* its data, describing its own columns.
#: A reader without the blank-row terminator returns these as drugs.
DRUG_COLUMN_DESCRIPTIONS = (
    ("MOLENAME", "Drug name"),
    ("TherapeuticIndication", "Drug therapeutic indication"),
    ("SMILES", "SMILES code of the drug"),
    ("cas", "CAS identificator"),
)

SUBHEADS = ("% consumed", "% consumed STD", "FC", "FC STD", " p(FDR)")

#: The ordinary non-hit every cell not named in :data:`SCREEN` carries.
DEFAULT_CELL = (3.0, 0.8)


def _book(title: str):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = title
    return book, sheet


def _strains(book) -> None:
    sheet = book.create_sheet("Supplementary Table 1")
    sheet.append(
        ["Supplementary Table 1: Bacterial strains and plasmids used in this study"]
    )
    sheet.append([None])
    sheet.append([None])
    sheet.append(["Name", "Phylum, genotype or description", "Reference"])
    sheet.append([None])
    # The sub-heading the real sheet opens the organism block with: a row with a
    # name and no phylum and no reference, which the reader must skip.
    sheet.append(
        ["Human gut bacteria tested for drug-metabolizing activity", None, None]
    )
    for row in STRAIN_ROWS:
        sheet.append(list(row))
    sheet.append([None])
    sheet.append([None])
    # Where the organisms stop. Everything from here is a mutant, a cloning
    # strain or a plasmid, and none of them is a taxon this graph can key.
    sheet.append(["Bacteroides thetaiotaomicron (Background: VPI 5482)", None, None])
    sheet.append(["wild type", "∆tdk", "Koropatkin et al. Structure (2008)"])
    sheet.append(["∆BT2068", "∆tdk, ∆bt2068", "This study"])
    sheet.append([None])
    sheet.append(["Plasmids", None, None])
    sheet.append(
        [
            "pZE21 (also pZE21-MCS1)",
            "Protein expression plasmid",
            "Forsberg et al. Science (2012)",
        ]
    )


def _drugs(book) -> None:
    sheet = book.create_sheet("Supplementary Table 2")
    sheet.append(
        [
            "Supplementary Table 2: Drugs used in this study, name, "
            "formula, mass, logP, chromatographic retention time."
        ]
    )
    sheet.append([None])
    sheet.append([None] * 5 + ["PMID:29555994"])
    sheet.append(list(DRUG_HEADER))
    for molename, (indication, trade, cas, parent, smiles) in DRUG_ROWS.items():
        row = dict.fromkeys(DRUG_HEADER)
        row.update(
            {
                "MOLENAME": molename,
                "TherapeuticIndication": indication,
                "TargetedRT": 1.5,
                "TargetedMZ": 300.0,
                "DrugPoolNumbers": "1  2",
                "EstimatedColonConcentrationMaier2018uM": "NaN",
                "SMILES": smiles,
                "STATUS": "USAN, INN",
                "TradeName": trade,
                "cas": cas,
                "iupacName": f"the IUPAC name of {parent}",
                "name": parent,
                "ref": "a reference",
                "salt_name": "",
                "salt_smiles": "",
                "smiles": smiles,
                "source": "synthetic",
            }
        )
        sheet.append([row[c] for c in DRUG_HEADER])
    # The blank row that terminates the data, then the sheet's description of
    # its own columns.
    sheet.append([None])
    sheet.append([None])
    for name, description in DRUG_COLUMN_DESCRIPTIONS:
        sheet.append([name, description])


def _screen(book) -> tuple[int, int, int]:
    sheet = book.create_sheet("Supplementary Table 3")
    sheet.append(
        [
            "Supplementary Table 3. Drug screen results (parent drugs), "
            "fold changes and p-values for all bacteria-drug interactions"
        ]
    )
    sheet.append([None])
    sheet.append(
        [
            None,
            None,
            "Percent change between T=12 h and t=0 h",
            None,
            "Fold changes between T=12 h and t=0 h of n=4 independent cultures",
            None,
            "p-values were calculated with unpaired two-sided Student's "
            "t-test for n=4 independent cultures and FDR-corrected for "
            "multiple hypotheses testing with Benjamini-Hochberg "
            "procedure. ",
        ]
    )
    header: list = ["DrugName", None]
    sub: list = [None, "Drug adaptive FC threshold %"]
    for label in COLUMNS:
        header += [label] + [None] * 4
        sub += [f"{s} {label}" for s in SUBHEADS]
    sheet.append(header)
    sheet.append(sub)

    metabolised = 0
    for molename, (threshold, cells) in SCREEN.items():
        row: list = [molename, threshold]
        hit_here = False
        for label in COLUMNS:
            measured = cells.get(label, DEFAULT_CELL)
            if measured is None:
                row += [None] * 5
                continue
            consumed, p = measured
            row += [consumed, 1.5, consumed / 100.0, 0.2, p]
            # Computed, never typed: this is the count the loader re-derives the
            # call rule against, so a hand-written headline would make that gate
            # a tautology here and a surprise on the real file.
            if (
                consumed >= threshold
                and p <= 0.05
                and not label.strip().startswith("Control")
            ):
                hit_here = True
        metabolised += 1 if hit_here else 0
        sheet.append(row)
    strains = [c for c in COLUMNS if not c.strip().startswith("Control")]
    return len(SCREEN), len(strains), metabolised


def _genes(book) -> None:
    sheet = book.create_sheet("Supplementary Table 13")
    sheet.append(
        [
            "Supplementary Table 13. Identified drug-metabolizing gene "
            "products from bacteria and targeted drugs. "
        ]
    )
    sheet.append([None])
    sheet.append([None])
    header: list = ["Gene", None, None, None]
    sub: list = ["RefSeq Locus Tag", "PATRIC ID", "Product", "Protein ID"]
    for drug in GENE_DRUG_COLUMNS:
        # A parent-drug column and one detected-metabolite mass column after it,
        # which is why the reader filters on the sub-header rather than counting.
        header += [drug, f"{drug}_208.1468"]
        sub += ["Parent drug", 208.147]
    sheet.append(header)
    sheet.append(sub)
    for tag, patric, product, protein, drugs in GENE_ROWS:
        row: list = [tag, patric, product, protein]
        for drug in GENE_DRUG_COLUMNS:
            row += [1 if drug in drugs else 0, 0]
        sheet.append(row)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    book, first = _book("Contents")
    first.append([None, None])
    for n, what in enumerate(
        [
            "Bacterial strains used in this study.",
            "Drugs used in this study, name, formula, mass, logP, "
            "chromatographic retention time.",
            "Drug screen results (parent drugs), fold changes and p-values for "
            "all bacteria-drug interactions.",
        ],
        start=1,
    ):
        first.append([f"Supplementary Table {n}", what])
    first.append(
        [
            "Supplementary Table 13",
            "Identified drug-metabolizing gene products from bacteria "
            "and targeted drugs. ",
        ]
    )
    _strains(book)
    _drugs(book)
    triple = _screen(book)
    _genes(book)
    book.save(OUT / WORKBOOK)
    print(
        f"wrote {OUT / WORKBOOK}: {len(SCREEN)} drugs x {len(COLUMNS)} "
        f"measured columns = {len(SCREEN) * len(COLUMNS)} cells, "
        f"{len(STRAIN_ROWS)} strains, {len(GENE_ROWS)} gene products"
    )
    print(f"  --published-matrix {triple[0]},{triple[1]},{triple[2]}")


if __name__ == "__main__":
    main()

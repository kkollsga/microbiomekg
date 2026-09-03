#!/usr/bin/env python3
"""Regenerate ``tests/fixtures/njc19_mini/41597_2020_516_MOESM1_ESM.xlsx``.

The fixture is a committed ``.xlsx``, which nobody can review by reading. This
script is the reviewable half: every row is listed below with the pitfall it
exists to make fail loudly, and the sheet name, legend and column layout are the
real file's exactly — the loader finds its header by searching for
``Metabolic activity``, so a fixture that skipped the legend would not exercise
that.

Run it only when the fixture needs to change::

    .venv/bin/python tests/fixtures/make_njc19_mini.py

Every organism resolves against ``tests/fixtures/taxdump_mini/`` or is here
*because* it does not, and every compound either names a metabolite in
``tests/fixtures/hmdb_mini/`` or is here because nothing holds it.

**Rows, and what each one is for**

===  ==================================  ====================================
row  organism / compound                 the trap
===  ==================================  ====================================
1    F. prausnitzii / Butyrate           the conjugate join: HMDB holds
                                         ``Butyric acid``, NJC19 says
                                         ``Butyrate``, and without the
                                         ``-ate`` <-> ``-ic acid`` step the
                                         SCFA half of D6 is two nodes.
2    F. prausnitzii / Acetate            a consumer for acetate — with row 3
                                         it is the only non-zero MES in the
                                         fixture, which is D6's whole claim.
3    B. thetaiotaomicron / Acetate       a producer for the same node.
4    B. thetaiotaomicron / Pectin        a compound no source holds: minted as
                                         ``NJC19:Pectin``, and the reference
                                         is ``(G)``-only, so
                                         ``genus_level_evidence`` is true on a
                                         species-filed row.
5    E. coli / Deoxycholic acid          the ``exact`` route, which must beat
                                         every derived spelling.
6    E. coli / L-Lactate (…)             two activities in one cell **and** a
                                         scoped reference cell: two edges, and
                                         the import must not carry the
                                         export's reference. Joins by
                                         ``stereo-conjugate``.
7    B. thetaiotaomicron / Succinate     ``Production (export) (-)``: a
                                         refutation, which must be a
                                         ``NO_EXCHANGE_WITH`` edge and must
                                         **not** appear as a ``PRODUCES``.
8    A. muciniphila / Mucin (…)          macromolecule degradation, minted.
9    human colonocyte / Butyrate         one of the six host cell types: a
                                         ledger row, and **no**
                                         ``UnresolvedTaxon`` — six tombstones
                                         would assert NCBI lost six taxa.
10   Bacillus / Formate                  a cross-kingdom homonym (1386 the
                                         bacterium, 55087 the stick insect).
                                         ``ambiguous``, so no edge and no
                                         guess — unlike HMDB's loader there is
                                         no microbial-context tiebreak here,
                                         because NJC19's column is already a
                                         species column and a genus in it is
                                         not evidence of anything.
11   Mycoplasma pneumoniae / Acetate     an organism NCBI renamed out from
                                         under the source (→ *Mycoplasmoides*,
                                         2018): an ``UnresolvedTaxon``
                                         tombstone, not a drop.
12   Lachnospiraceae / Acetate           a **family**, broader than
                                         ``EXCHANGE_RANK_CEILING``: ledger,
                                         with the id and rank it did reach.
13   B. longum subsp. infantis / Acetate a subspecies promoted to its species,
                                         ``original_rank`` kept as
                                         ``subspecies`` (G5).
14   E. coli / Formate                   ``Cross-feeding (unspecified)`` — an
                                         activity outside the closed
                                         vocabulary: counted, never guessed
                                         into a relationship.
15   E. coli / *(no compound)*           an incomplete row.
16   *(duplicate of row 1, byte for*     a duplicate fact, not a second
     *byte)*                             observation: ``dedupe_full`` collapses
                                         it to one edge.
===  ==================================  ====================================
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

OUT = Path(__file__).resolve().parent / "njc19_mini" / "41597_2020_516_MOESM1_ESM.xlsx"

SHEET = "Online-only Table 5"

#: The real file's three legend lines and blank row, verbatim. The last of them
#: is the only place the source defines `(G)` and `(-)`, and the loader's header
#: search exists because this block is here.
LEGEND: list[tuple] = [
    (
        "Online-only Table 5. Metabolic associations between organisms and chemical "
        "compounds in NJC19, with relevant literature sources.",
        None,
        None,
        None,
        None,
    ),
    (" Ref. #s denote references in Online-only Table 2.", None, None, None, None),
    (
        " (G) genus level information; (-) in metabolic activity denotes 'negative' "
        "information from the literature, i.e., the corresponding activity does not "
        "occur, according to the literature.",
        None,
        None,
        None,
        None,
    ),
    (None, None, None, None, None),
    (
        None,
        "Species",
        "Small-molecule metabolite or macromolecule",
        "Metabolic activity",
        "Ref. #",
    ),
]

ROWS: list[tuple] = [
    (None, "Faecalibacterium prausnitzii", "Butyrate", "Production (export)", "424"),
    (None, "Faecalibacterium prausnitzii", "Acetate", "Consumption (import)", "424"),
    (None, "Bacteroides thetaiotaomicron", "Acetate", "Production (export)", "12, 197"),
    (
        None,
        "Bacteroides thetaiotaomicron",
        "Pectin",
        "Macromolecule degradation",
        "217(G)",
    ),
    (None, "Escherichia coli", "Deoxycholic acid", "Consumption (import)", "11, 13"),
    (
        None,
        "Escherichia coli",
        "L-Lactate ([S]-Lactate, Lactate, D-Lactate, [R]-Lactate)",
        "Consumption (import), Production (export)",
        "import:415, 418;export:417",
    ),
    (
        None,
        "Bacteroides thetaiotaomicron",
        "Succinate",
        "Production (export) (-)",
        "242",
    ),
    (
        None,
        "Akkermansia muciniphila",
        "Mucin (Mucus Glycoprotein)",
        "Macromolecule degradation",
        "100",
    ),
    (None, "human colonocyte", "Butyrate", "Consumption (import)", "500"),
    (None, "Bacillus", "Formate", "Production (export)", "31"),
    (None, "Mycoplasma pneumoniae", "Acetate", "Production (export)", "77"),
    (None, "Lachnospiraceae", "Acetate", "Production (export)", "88(G)"),
    (
        None,
        "Bifidobacterium longum subsp. infantis",
        "Acetate",
        "Production (export)",
        "99",
    ),
    (None, "Escherichia coli", "Formate", "Cross-feeding (unspecified)", "404"),
    (None, "Escherichia coli", None, "Consumption (import)", "405"),
    (None, "Faecalibacterium prausnitzii", "Butyrate", "Production (export)", "424"),
]


def main() -> None:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = SHEET
    for row in [*LEGEND, *ROWS]:
        sheet.append(list(row))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    book.save(OUT)
    print(f"wrote {OUT} ({len(ROWS)} data rows)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Regenerate ``tests/fixtures/gutmdisorder_mini/{human,mouse}.xlsx``.

The fixture is committed as two ``.xlsx`` files, which nobody can review by
reading. This script is how they were made, and it is the reviewable half: real
rows cut from ``data/raw/gutmdisorder/`` by ``(workbook, index)``, plus a named
list of injected rows, each of which exists to make one pitfall fail loudly.

Run it only when the fixture needs to change, and only on a machine that has
the raw workbooks::

    .venv/bin/python tests/fixtures/make_gutmdisorder_mini.py

**Real rows kept** (every taxid in them exists in ``taxdump_mini``):

======  =====  =========  ====================================================
book    index  PMID       why it is here
======  =====  =========  ====================================================
human   201    27007700   PMID **shared with `bugsigdb_mini.csv`**, and
                          DOID:9970 → MONDO:0011122, which that fixture also
                          cites — so one paper and one disease must be one node
                          across two sources.
human   231    26230509   Four taxa at two ranks; the exact-duplicate and
                          both-direction injections hang off it.
human   81     22315951   DOID:9778 → MONDO:0005052, an assay of ``qPCR`` only
                          — the one row that must land ``observational-targeted``.
human   234    26139477   ``Research Type`` names an intervention *and* the row
                          has a DOID, so its taxa must reach a Disease **and**
                          an Intervention with a DrugBank id.
mouse   2      29290650   Observational, but mouse: ``in-vivo-model`` whatever
                          the design (G6).
mouse   3      29290650   Same PMID as mouse 2 — one paper, two studies — with
                          an intervention and a DrugBank id.
======  =====  =========  ====================================================

**Injected rows**, each named by the pitfall it exercises:

* ``human`` Literature 900 — ``DOID:00400085``, gutMDisorder's own malformed id
  (8 digits; DOID ids are 1–7). Must reach the condition ledger, and its
  association must reach the association ledger, because the study then has
  neither a disease nor an intervention.
* ``human`` Literature 901 — ``DOID:8878,DOID:8577``, the real comma-multivalued
  cell, neither of which MONDO maps: two Disease nodes keyed on their own DOID
  with ``mondo_id`` null.
* ``human`` Association, index 231, ``Bacteroides`` decrease **twice, byte for
  byte** — one edge with ``duplicate_rows = 2``.
* ``human`` Association, index 231, ``Prevotella`` increase **and** decrease —
  two edges. G4: disagreement is exposed, never resolved.
* ``human`` Association, index 901, taxid 1036 — deleted in ``delnodes.dmp``:
  an ``UnresolvedTaxon`` tombstone plus an association-ledger row, never a
  silent drop.
* ``human`` Association, index 901, taxid 541000 — merged to 216572: the edge
  must land on the survivor.
* ``human`` Association, index 901, **no NCBI id**, name ``Escherichia coli`` —
  resolved by name, the path 4.2% of BugSigDB rows also need.
* ``human`` Association, index **2.5** — not an integer within 1e-6. Rounding it
  would attach the row to study 2 or 3; it goes to the ledger instead.
* ``mouse`` Sample and Association indexes carry the real binary noise
  (``1.9999999999999``, ``3.0000000000001``). ``int()`` maps the first to **1**
  and the row lands on the wrong paper; ``round()`` is the fix, and this is what
  makes the difference visible.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "gutmdisorder"
OUT = Path(__file__).resolve().parent / "gutmdisorder_mini"
TAXDUMP = Path(__file__).resolve().parent / "taxdump_mini"

KEEP = {"human": [201, 231, 81, 234], "mouse": [2, 3]}

#: Literature rows that are not in the real file. Columns match the sheet.
EXTRA_LITERATURE = {
    "human": [
        {
            "Index": 900, "PMID": 30000001, "Journal": "Journal of Fixtures",
            "Title": "A study whose only disease id is malformed",
            "Authors": "Fixture A", "Research Type": "Gut microbiota associated with disorder",
            "Intervention": None, "Intervention Type": None, "Intervention ID": None,
            "Disorder Name": "an unmappable disorder", "DOID": "DOID:00400085",
            "Conclusion": "Nothing here should reach a Disease node.",
            "Experiment ID": None, "Experiment web site": None,
        },
        {
            "Index": 901, "PMID": 30000002, "Journal": "Journal of Fixtures",
            "Title": "A study naming two diseases in one cell",
            "Authors": "Fixture B", "Research Type": "Gut microbiota associated with disorder",
            "Intervention": None, "Intervention Type": None, "Intervention ID": None,
            "Disorder Name": "Crohn's disease,ulcerative colitis",
            "DOID": "DOID:8878,DOID:8577",
            "Conclusion": "Two ids in one cell, neither mapped by MONDO.",
            "Experiment ID": None, "Experiment web site": None,
        },
    ],
    "mouse": [],
}

EXTRA_SAMPLE = {
    "human": [
        {"Index": 900, "Sample Number": 1, "Sample Size": 12.0, "Sample Source": "stool",
         "Sex (male, female)": "6,6", "Age": "40 years old", "BMI": None,
         "Human/Mouse": "human", "Nation/Race": "Fixture", "Condition": "cases",
         "Sequencing Technology": "16S rRNA sequences", "Sequencing Platform": None,
         "Unnamed: 12": None, "Unnamed: 13": None},
        {"Index": 901, "Sample Number": 1, "Sample Size": 20.0, "Sample Source": "stool",
         "Sex (male, female)": "10,10", "Age": "40 years old", "BMI": None,
         "Human/Mouse": "human", "Nation/Race": "Fixture", "Condition": "cases",
         "Sequencing Technology": "16S rRNA sequences", "Sequencing Platform": None,
         "Unnamed: 12": None, "Unnamed: 13": None},
        {"Index": 901, "Sample Number": 2, "Sample Size": 21.0, "Sample Source": "stool",
         "Sex (male, female)": "11,10", "Age": "41 years old", "BMI": None,
         "Human/Mouse": "human", "Nation/Race": "Fixture", "Condition": "healthy",
         "Sequencing Technology": "16S rRNA sequences", "Sequencing Platform": None,
         "Unnamed: 12": None, "Unnamed: 13": None},
    ],
    "mouse": [],
}


def association(index, name, gm, taxid, rank, p, method, description, alteration):
    return {
        "index": index, "Gut Microbiota": name, "Gut Microbiata ID": gm,
        "Gut Microbiata NCBI ID": taxid, "Classification": rank, "P Value": p,
        "Statistical Method": method, "Description": description,
        "Alteration": alteration,
    }


def echo(frame: pd.DataFrame, index: int, gm: str, **changes) -> dict:
    """A real row copied verbatim, optionally with a field changed.

    The exact-duplicate case has to be *exact* — a duplicate that differs in
    one character is a near-duplicate, which this loader deliberately keeps as
    a separate edge — so it is copied from the cut rather than retyped.
    """
    row = frame[(frame["index"].round() == index) &
                (frame["Gut Microbiata ID"] == gm)].iloc[0].to_dict()
    row.update(changes)
    return row


def injected_associations(workbook: str, real: pd.DataFrame) -> list[dict]:
    if workbook == "mouse":
        return []
    return [
        # An exact duplicate of a row already in the real cut: one edge, and a
        # duplicate_rows of 2 that says the source repeated itself.
        echo(real, 231, "gm0077"),
        # The same taxon in the same study, the other way. Two edges (G4):
        # a contradiction is exposed, never resolved by a majority.
        echo(real, 231, "gm0535", **{
            "Alteration": "decrease",
            "Description": "Prevotella was less abundant in a second cohort.",
        }),
        *EXTRA_ASSOCIATION[workbook],
    ]


EXTRA_ASSOCIATION = {
    "human": [
        # Deleted taxid: a tombstone and a ledger row, never a silent drop.
        association(901, "A deleted organism", "gm9001", 1036.0, "genus", 0.01,
                    "Student's t test", "Reported under an id NCBI has deleted.",
                    "increase"),
        # Merged taxid: the edge lands on the survivor, 216572.
        association(901, "An organism under an old id", "gm9002", 541000.0, "family",
                    0.02, "Student's t test", "Reported under a merged id.", "decrease"),
        # No id at all: resolved by name.
        association(901, "Escherichia coli", "gm9003", None, "species", 0.03,
                    "Student's t test", "Reported by name with no id column.",
                    "increase"),
        # Not an integer within 1e-6: rounding it would pick a study.
        association(2.5, "Bacteroides", "gm0077", 816.0, "genus", 0.04,
                    "Student's t test", "An index that is not an integer.", "increase"),
        association(900, "Bacteroides", "gm0077", 816.0, "genus", 0.05,
                    "Student's t test",
                    "The study this belongs to has no usable disease id.", "increase"),
    ],
    "mouse": [],
}

#: The mouse workbook's real binary noise, reproduced exactly: index → the
#: float actually written in the sheet. ``int()`` truncates 1.9999999999999 to
#: 1 and files those rows under a study that is not theirs. It is applied to
#: ``Sample`` and ``Association`` only — ``Literature.Index`` is a clean int64
#: in the real file, and *that asymmetry is the pitfall*: a loader that joins on
#: equality drops 45 of 930 rows because one side is clean and the other is not.
MOUSE_NOISE = {2: 1.9999999999999, 3: 3.0000000000001}


def mini_taxids() -> set[int]:
    """Every taxid ``taxdump_mini`` can resolve, plus the ones it must fail on.

    Association rows naming a taxon outside the mini taxdump are dropped from
    the *real* cut. Keeping them would fill the fixture with tombstones that
    measure the size of the taxdump fixture rather than anything about this
    loader — while the tombstone path is exercised deliberately, by the
    injected deleted id.
    """
    live = {int(line.split("\t|")[0].strip())
            for line in (TAXDUMP / "nodes.dmp").read_text().splitlines() if line.strip()}
    merged = {int(line.split("\t|")[0].strip())
              for line in (TAXDUMP / "merged.dmp").read_text().splitlines() if line.strip()}
    return live | merged


def cut(workbook: str) -> dict[str, pd.DataFrame]:
    book = pd.ExcelFile(RAW / f"{workbook}.xlsx")
    keep = KEEP[workbook]
    known = mini_taxids()
    sheets = {}
    for sheet, column in (("Literature", "Index"), ("Sample", "Index"),
                          ("Association", "index")):
        frame = book.parse(sheet)
        index = frame[column].astype(float).round().astype(int)
        frame = frame[index.isin(keep)].copy()
        if sheet == "Association":
            taxid = frame["Gut Microbiata NCBI ID"].fillna(-1).round().astype(int)
            frame = frame[taxid.isin(known)].copy()
        if workbook == "mouse" and sheet != "Literature":
            frame[column] = index[frame.index].map(
                lambda i: MOUSE_NOISE.get(i, float(i))
            )
        extra = (
            injected_associations(workbook, frame)
            if sheet == "Association"
            else {"Literature": EXTRA_LITERATURE, "Sample": EXTRA_SAMPLE}[sheet][workbook]
        )
        if extra:
            frame = pd.concat([frame, pd.DataFrame(extra)], ignore_index=True)
        sheets[sheet] = frame
    return sheets


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for workbook in KEEP:
        sheets = cut(workbook)
        path = OUT / f"{workbook}.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for name, frame in sheets.items():
                frame.to_excel(writer, sheet_name=name, index=False)
        print(f"{path}: " + ", ".join(f"{n} {len(f)}" for n, f in sheets.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

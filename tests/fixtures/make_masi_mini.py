#!/usr/bin/env python3
"""Regenerate ``tests/fixtures/masi_mini/`` — MASI's four workbooks, cut down.

The fixture is four committed ``.xlsx`` files, which nobody can review by
reading. This script is the reviewable half: every microbe, every substance,
every interaction record and every disease association below is here *because of
a trap*, and the traps are the real file's — the column names, the ``n.a.``
spelling of absent, the two-valued ``Interaction_Category``, the non-unique
``Interation_Record_ID`` (sic) and the multi-valued reference cell are all
verbatim.

Run it only when the fixture needs to change::

    .venv/bin/python tests/fixtures/make_masi_mini.py

Every organism resolves against ``tests/fixtures/taxdump_mini/`` or is here
*because* it does not; every substance reaches a ``Drug`` node that
``tests/fixtures/chembl_mini/`` produces, or is here because it must not.

**The microbes (``microbesInfo``, and the interaction rows that name them)**

===================================  ==========================================
``microbe_id`` / name                the trap
===================================  ==========================================
``PMDBM1``                           **a strain that promotes, and a probiotic
*Escherichia coli* O157:H7           claim that must survive the promotion.**
                                     taxid 83334 is rank ``no rank`` under 562,
                                     so it promotes to *E. coli* — and it is the
                                     one MASI marks ``if_probiotic = Yes``.
``PMDBM2``                           **the collision.** Also 562, and *not*
*Escherichia coli*                   marked a probiotic. `taxon_probiotic.csv`
                                     is keyed on tax_id and first-row-per-key
                                     wins, so whichever of these two is written
                                     first used to decide — which silently
                                     dropped 5 of the real file's 46 probiotic
                                     claims. `probiotic` must come out **true**
                                     and `probiotic_reported_name` must carry
                                     both names.
``PMDBM3``                           the ordinary case: an id in the record and
*Bacteroides thetaiotaomicron*       an id in the dictionary, agreeing.
``PMDBM4``                           **``microbe_tax_id`` is ``n.a.`` and a
*Blautia* spp.                       ``genus_id`` is not.** The claim is made at
                                     the genus, `taxon_id_route` says ``genus``
                                     and `reported_rank` says ``genus`` rather
                                     than repeating the dictionary's ``Species``.
``PMDBM5``                           **the two tables disagree.** The dictionary
*Bacteroidetes*                      says 976 (phylum) and the interaction
                                     record says 200643 (class) — one name NCBI
                                     spells at both ranks. The record wins and
                                     the disagreement is a ledger row.
``PMDBM6``                           **the largest "microbe" in the real file is
Unclassified gut microbiota          not an organism.** No taxid, no genus id:
                                     an `UnresolvedTaxon` tombstone and **no
                                     edges**, which on the real file costs 388
                                     of the 404 curated non-metabolism records.
``PMDBM7``                           a second probiotic, at species rank, so the
*Bifidobacterium longum*             probiotic count is not one taxon wide.
``PMDBM99``                          **named by an interaction record and absent
*Odoribacter splanchnius*            from the dictionary.** Three microbe ids do
                                     this in the real file. No rank, no genus
                                     fallback, no probiotic row — a ledger row
                                     and a tombstone, never a guess at the
                                     spelling (Zimmermann's own sheet misspells
                                     the same organism).
===================================  ==========================================

**The substances (``substanceInfo``)**

======================  ==================================================
``Substance_id``        the trap
======================  ==================================================
``PMDBD1`` Metformin    the ``substance-name`` route, and the compound D18
                        is about: it must reach `CHEMBL:CHEMBL1431` and the
                        edges must still hang off the `Substance` node,
                        one `SAME_COMPOUND_AS` hop away.
``PMDBD2`` Ampicillin   the ``salt-name`` route: ChEMBL keys the parent and
sodium                  MASI names the salt.
``PMDBD3`` ACE          **a class, not a compound**, and MASI's own
inhibitors              subcategory says so (``Drug Class``). It must never
                        be offered to the join — matching a class onto one
                        molecule is the level-4-ATC error
                        `microbiomekg.drugs` refuses — and it must still be
                        a `Substance` node with its edges.
``PMDBD4`` Baicalin     a herbal compound no ChEMBL route reaches: a
                        `Substance` node with **no** `SAME_COMPOUND_AS`
                        edge, which is what stops MASI minting `Drug`
                        nodes for herbs.
``PMDBD5`` Aspirin      **a non-therapeutic category that reaches a Drug
                        anyway.** Filed ``Environmental Chemicals`` here as
                        16 substances are in the real file; the join is
                        allowed (it is the same molecule) and is a ledger
                        row, so a false merge would appear in a count
                        rather than in nobody's notes.
``PMDBD6`` Vancomycin   the compound **both** screens measured against
                        *B. thetaiotaomicron*, so the MASI edge for that
                        pair must name both in
                        `duplicates_primary_source`.
======================  ==================================================

**The interaction records.** Both categories, both refutation forms, both
untypable forms, and every shape of the reference cell:

* ``PMDBI1`` *B. theta* x Vancomycin, ``Microbes metabolize substances`` — the
  hit, and the **aggregator overlap**: both screens measured this pair.
* ``PMDBI2`` *E. coli* x Ampicillin sodium with ``Metabolism_Effect_on_Drug`` =
  ``Microbe does not metabolize drug`` — the curated refutation, its own
  relationship.
* ``PMDBI3`` Unclassified gut microbiota x Baicalin — **no edge**, a tombstone.
* ``PMDBI4`` *Blautia* spp. x Metformin, ``In vivo`` in a ``C57BL/6 mouse`` —
  ``in-vivo-model``, ``decreased``, reached through the **genus** id.
* ``PMDBI5`` *Bacteroidetes* x Metformin, ``In vitro`` — ``in-vitro``,
  ``increased``, and the taxid the two tables disagree on.
* ``PMDBI6`` *E. coli* x Aspirin, ``No significant change`` — the curated
  no-effect, its own relationship.
* ``PMDBI7`` *B. longum* x Baicalin, ``delay microbiota maturation`` — a change
  with no direction this model can write: **no edge**, a ledger row. Two rows of
  the real file are this.
* ``PMDBI8`` *O. splanchnius* x ACE inhibitors — the microbe with no dictionary
  row, and the substance that must not reach a `Drug`.
* ``PMDBI9`` / ``PMDBI9`` — **one record id on two rows**, which 2,891 of the
  real file's rows do. Two edges, two distinct `source_record_id`s.
* ``PMDBI10`` *B. theta* x Metformin with ``Experiment_System`` = ``n.a.`` —
  ``unknown``, never a plausible default.
* ``PMDBI11`` *E. coli* x Metformin, reference ``DOI: 10.1000/xyz`` and no PMID
  — `publications` carries the DOI and `pmid` is empty.
* ``PMDBI12`` *B. theta* x Baicalin, reference type ``PMID`` and a **bare
  number** with no prefix. This shape is not in the 2020-09-28 release — its 25
  mistyped rows carry a *DOI* under a ``PMID`` type, which ``PMDBI11`` covers
  from the other side — so this row exercises the narrow fallback that only
  fires when the type column says ``PMID`` and the whole cell is digits.
* ``PMDBI13`` *B. longum* x Vancomycin, ``Microbes rearrange substances`` — an
  ``Interaction_Category`` this loader has not read: **no edge**, a ledger row.

**The disease associations.** Every MONDO route, and the two that must miss:

* ``DIS1`` ``Colorectal cancer`` -> ``MONDO:0005575`` by **name**.
* ``DIS2`` ``Obesity`` -> ``MONDO:0011122`` (*obesity disorder*) by **exact
  synonym**.
* ``DIS3`` ``Irritable bowel syndrome (IBS)`` -> ``MONDO:0005052`` by name,
  **after the trailing abbreviation is stripped**.
* ``DIS4`` ``Animal helminthiasis`` — MONDO carries this only as a ``RELATED``
  synonym of *helminthiasis, animal*, and reading a RELATED synonym as identity
  is the same false merge ``MONDO:equivalentTo`` guards against on the xref
  side. It must **miss** and keep ``MASI:DIS4``.
* ``DIS5`` ``Rheumatoid arthrits`` — the real file's typo. It misses, and
  nothing corrects it.

One microbe–disease pair is curated in **both** directions (``PMDBM3`` x
``DIS1``), which is two edges and never a verdict (G4), and one association
sits on the unresolvable microbe.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

OUT = Path(__file__).resolve().parent / "masi_mini"

FILES = {
    "interactions": "MASI_v1.0_download_microbeSubstanceInteractionRecords_ver20200928.xlsx",
    "diseases": "MASI_v1.0_download_microbeDiseaseAssociationRecords.xlsx",
    "microbes": "MASI_v1.0_download_microbesInfo.xlsx",
    "substances": "MASI_v1.0_download_substanceInfo.xlsx",
}

NA = "n.a."

MICROBE_HEADER = [
    "microbe_id",
    "microbe_tax_id",
    "microbe_name",
    "microbe_tax_level",
    "genus_id",
    "genus_name",
    "family_id",
    "family_name",
    "superking_id",
    "superking_name",
    "if_probiotic",
    "probiotic_use_species",
    "probiotic_research_stage",
    "if_has_abundance",
]

MICROBE_ROWS: list[list[str]] = [
    [
        "PMDBM1",
        "83334",
        "Escherichia coli O157:H7",
        "Strain",
        "561",
        "Escherichia",
        "543",
        "Enterobacteriaceae",
        "2",
        "Bacteria",
        "Yes",
        "Human",
        "Clinical trial",
        "Yes",
    ],
    [
        "PMDBM2",
        "562",
        "Escherichia coli",
        "Species",
        "561",
        "Escherichia",
        "543",
        "Enterobacteriaceae",
        "2",
        "Bacteria",
        NA,
        NA,
        NA,
        "Yes",
    ],
    [
        "PMDBM3",
        "818",
        "Bacteroides thetaiotaomicron",
        "Species",
        "816",
        "Bacteroides",
        "815",
        "Bacteroidaceae",
        "2",
        "Bacteria",
        NA,
        NA,
        NA,
        "Yes",
    ],
    [
        "PMDBM4",
        NA,
        "Blautia spp.",
        "Species",
        "572511",
        "Blautia",
        "186803",
        "Lachnospiraceae",
        "2",
        "Bacteria",
        NA,
        NA,
        NA,
        "No",
    ],
    [
        "PMDBM5",
        "976",
        "Bacteroidetes",
        "phylum",
        NA,
        NA,
        NA,
        NA,
        "2",
        "Bacteria",
        NA,
        NA,
        NA,
        "Yes",
    ],
    [
        "PMDBM6",
        NA,
        "Unclassified gut microbiota",
        NA,
        NA,
        NA,
        NA,
        NA,
        NA,
        NA,
        NA,
        NA,
        NA,
        "No",
    ],
    [
        "PMDBM7",
        "216816",
        "Bifidobacterium longum",
        "Species",
        "1678",
        "Bifidobacterium",
        "31953",
        "Bifidobacteriaceae",
        "2",
        "Bacteria",
        "Yes",
        "Animal",
        "Marketed",
        "Yes",
    ],
]

SUBSTANCE_HEADER = [
    "Substance_id",
    "Substance_name",
    "Substance_category",
    "Substance_subcategory",
    "cas_no",
    "id_drugbank",
    "id_pharmgkb",
    "id_kegg",
    "id_ttd",
    "id_pubchem",
    "id_chemspider",
    "id_npass",
    "synonyms",
    "Molecular_formula",
    "inchikey",
    "iupacname",
    "Product_company",
    "Therapeutic_class",
]

#: ``(id, name, category, subcategory, cas, drugbank, pubchem, formula)`` —
#: the eight columns the fixture varies; the other ten are filled with ``n.a.``
#: because that is what the real file does for most rows.
SUBSTANCE_ROWS: list[tuple[str, str, str, str, str, str, str, str]] = [
    (
        "PMDBD1",
        "Metformin",
        "Therapeutic Substance",
        "Approved Drug",
        "657-24-9",
        "DB00331",
        "4091",
        "C4H11N5",
    ),
    (
        "PMDBD2",
        "Ampicillin sodium",
        "Therapeutic substance",
        "Approved Drug; Antibiotics",
        "69-52-3",
        "DB00415",
        "23665617",
        "C16H18N3NaO4S",
    ),
    ("PMDBD3", "ACE inhibitors", "Therapeutic Substance", "Drug Class", NA, NA, NA, NA),
    (
        "PMDBD4",
        "Baicalin",
        "Herbal Substance",
        "Medicinal Herbal Compounds",
        "21967-41-9",
        NA,
        "64982",
        "C21H18O11",
    ),
    (
        "PMDBD5",
        "Aspirin",
        "Environmental Chemicals",
        "Unclassified Substance",
        "50-78-2",
        "DB00945",
        "2244",
        "C9H8O4",
    ),
    (
        "PMDBD6",
        "Vancomycin",
        "Therapeutic Substance",
        "Approved Drug; Antibiotics",
        "1404-90-6",
        "DB00512",
        "14969",
        "C66H75Cl2N9O24",
    ),
]

INTERACTION_HEADER = [
    # `Interation_Record_ID` is the real file's spelling, typo and all.
    "Interation_Record_ID",
    "Interaction_Category",
    "MASI-Microbe-ID",
    "Microbe-Tax-ID",
    "Microbe-Name",
    "MASI-Substance-chemicalD",
    "Substance-Name",
    "Substance-Category",
    "Substance-subCategory",
    "Substance_Exposure_Details",
    "Microbiota_Site",
    "Microbe_Change",
    "Microbe_Change_Statistics",
    "Metabolites",
    "Metabolism_Type",
    "Metabolism_Enzymes",
    "Metabolism_Effect_on_Drug",
    "Experiment_System",
    "Experiment_Model_Species",
    "Model_Condition/Disease",
    "Metabolism_Mechanism",
    "Outcome",
    "Reference_ID_Type",
    "Reference_ID",
]

METABOLISM = "Microbes metabolize substances"
ABUNDANCE = "Substances alter microbe abundance"

#: One dict per record; every column not named here is ``n.a.``.
INTERACTION_ROWS: list[dict[str, str]] = [
    {
        "Interation_Record_ID": "PMDBI1",
        "Interaction_Category": METABOLISM,
        "MASI-Microbe-ID": "PMDBM3",
        "Microbe-Tax-ID": "818",
        "Microbe-Name": "Bacteroides thetaiotaomicron",
        "MASI-Substance-chemicalD": "PMDBD6",
        "Substance-Name": "Vancomycin",
        "Substance-Category": "Therapeutic Substance",
        "Substance-subCategory": "Approved Drug; Antibiotics",
        "Metabolites": "vancomycin aglycone",
        "Metabolism_Type": "Hydrolysis",
        "Metabolism_Effect_on_Drug": "Decrease Efficacy",
        "Experiment_System": "In vitro",
        "Experiment_Model_Species": "High-throughput incubation assays",
        "Reference_ID_Type": "PMID",
        "Reference_ID": "PMID: 31158845",
    },
    {
        "Interation_Record_ID": "PMDBI2",
        "Interaction_Category": METABOLISM,
        "MASI-Microbe-ID": "PMDBM2",
        "Microbe-Tax-ID": "562",
        "Microbe-Name": "Escherichia coli",
        "MASI-Substance-chemicalD": "PMDBD2",
        "Substance-Name": "Ampicillin sodium",
        "Substance-Category": "Therapeutic substance",
        "Substance-subCategory": "Approved Drug; Antibiotics",
        "Metabolism_Effect_on_Drug": "Microbe does not metabolize drug",
        "Experiment_System": "In vitro",
        "Experiment_Model_Species": "High-throughput incubation assays",
        "Reference_ID_Type": "PMID",
        "Reference_ID": "PMID: 31158845",
    },
    {
        "Interation_Record_ID": "PMDBI3",
        "Interaction_Category": METABOLISM,
        "MASI-Microbe-ID": "PMDBM6",
        "Microbe-Tax-ID": NA,
        "Microbe-Name": "Unclassified gut microbiota",
        "MASI-Substance-chemicalD": "PMDBD4",
        "Substance-Name": "Baicalin",
        "Substance-Category": "Herbal Substance",
        "Substance-subCategory": "Medicinal Herbal Compounds",
        "Metabolism_Effect_on_Drug": "Microbe does not metabolize drug",
        "Experiment_System": "In vitro",
        "Reference_ID_Type": "PMID",
        "Reference_ID": "PMID: 26569070",
    },
    {
        "Interation_Record_ID": "PMDBI4",
        "Interaction_Category": ABUNDANCE,
        "MASI-Microbe-ID": "PMDBM4",
        "Microbe-Tax-ID": NA,
        "Microbe-Name": "Blautia spp.",
        "MASI-Substance-chemicalD": "PMDBD1",
        "Substance-Name": "Metformin",
        "Substance-Category": "Therapeutic Substance",
        "Substance-subCategory": "Approved Drug",
        "Substance_Exposure_Details": "2 months of metformin treatment vs control",
        "Microbiota_Site": "Gut",
        "Microbe_Change": "Decrease",
        "Microbe_Change_Statistics": "Significantly",
        "Experiment_System": "In vivo",
        "Experiment_Model_Species": "C57BL/6 mouse",
        "Model_Condition/Disease": "Type 2 diabetes",
        "Reference_ID_Type": "PMID",
        "Reference_ID": "PMID: 28530702",
    },
    {
        "Interation_Record_ID": "PMDBI5",
        "Interaction_Category": ABUNDANCE,
        "MASI-Microbe-ID": "PMDBM5",
        "Microbe-Tax-ID": "200643",
        "Microbe-Name": "Bacteroidetes",
        "MASI-Substance-chemicalD": "PMDBD1",
        "Substance-Name": "Metformin",
        "Substance-Category": "Therapeutic Substance",
        "Substance-subCategory": "Approved Drug",
        "Microbiota_Site": "Gut",
        "Microbe_Change": "Increase",
        "Experiment_System": "In vitro",
        "Experiment_Model_Species": "Human gut microbiota ex vivo mixed "
        "culturing system",
        "Reference_ID_Type": "PMID",
        "Reference_ID": "PMID: 28530702",
    },
    {
        "Interation_Record_ID": "PMDBI6",
        "Interaction_Category": ABUNDANCE,
        "MASI-Microbe-ID": "PMDBM2",
        "Microbe-Tax-ID": "562",
        "Microbe-Name": "Escherichia coli",
        "MASI-Substance-chemicalD": "PMDBD5",
        "Substance-Name": "Aspirin",
        "Substance-Category": "Environmental Substance",
        "Substance-subCategory": "Unclassified Substance",
        "Microbe_Change": "No significant change",
        "Experiment_System": "In vitro",
        "Experiment_Model_Species": "High-throughput incubation assays",
        "Reference_ID_Type": "PMID",
        "Reference_ID": "PMID: 29555994",
    },
    {
        "Interation_Record_ID": "PMDBI7",
        "Interaction_Category": ABUNDANCE,
        "MASI-Microbe-ID": "PMDBM7",
        "Microbe-Tax-ID": "216816",
        "Microbe-Name": "Bifidobacterium longum",
        "MASI-Substance-chemicalD": "PMDBD4",
        "Substance-Name": "Baicalin",
        "Substance-Category": "Herbal Substance",
        "Substance-subCategory": "Medicinal Herbal Compounds",
        "Microbe_Change": "delay microbiota maturation",
        "Experiment_System": "In vivo",
        "Experiment_Model_Species": "Mouse",
        "Reference_ID_Type": "PMID",
        "Reference_ID": "PMID: 24033291",
    },
    {
        "Interation_Record_ID": "PMDBI8",
        "Interaction_Category": ABUNDANCE,
        "MASI-Microbe-ID": "PMDBM99",
        "Microbe-Tax-ID": NA,
        "Microbe-Name": "Odoribacter splanchnius",
        "MASI-Substance-chemicalD": "PMDBD3",
        "Substance-Name": "ACE inhibitors",
        "Substance-Category": "Therapeutic Substance",
        "Substance-subCategory": "Drug Class",
        "Microbe_Change": "Decrease",
        "Experiment_System": "In vivo",
        "Experiment_Model_Species": "Human",
        "Reference_ID_Type": "PMID",
        "Reference_ID": "PMID: 32526207",
    },
    # One record id, two microbes — the shape 2,891 real rows have.
    {
        "Interation_Record_ID": "PMDBI9",
        "Interaction_Category": ABUNDANCE,
        "MASI-Microbe-ID": "PMDBM3",
        "Microbe-Tax-ID": "818",
        "Microbe-Name": "Bacteroides thetaiotaomicron",
        "MASI-Substance-chemicalD": "PMDBD5",
        "Substance-Name": "Aspirin",
        "Substance-Category": "Environmental Substance",
        "Substance-subCategory": "Unclassified Substance",
        "Microbe_Change": "Decrease",
        "Experiment_System": "In vitro",
        "Experiment_Model_Species": "High-throughput incubation assays",
        "Reference_ID_Type": "PMID",
        "Reference_ID": "PMID: 29555994",
    },
    {
        "Interation_Record_ID": "PMDBI9",
        "Interaction_Category": ABUNDANCE,
        "MASI-Microbe-ID": "PMDBM7",
        "Microbe-Tax-ID": "216816",
        "Microbe-Name": "Bifidobacterium longum",
        "MASI-Substance-chemicalD": "PMDBD5",
        "Substance-Name": "Aspirin",
        "Substance-Category": "Environmental Substance",
        "Substance-subCategory": "Unclassified Substance",
        "Microbe_Change": "Increase",
        "Experiment_System": "In vitro",
        "Experiment_Model_Species": "High-throughput incubation assays",
        "Reference_ID_Type": "PMID",
        "Reference_ID": "PMID: 29555994",
    },
    {
        "Interation_Record_ID": "PMDBI10",
        "Interaction_Category": ABUNDANCE,
        "MASI-Microbe-ID": "PMDBM3",
        "Microbe-Tax-ID": "818",
        "Microbe-Name": "Bacteroides thetaiotaomicron",
        "MASI-Substance-chemicalD": "PMDBD1",
        "Substance-Name": "Metformin",
        "Substance-Category": "Therapeutic Substance",
        "Substance-subCategory": "Approved Drug",
        "Microbe_Change": "Decrease",
        "Experiment_System": NA,
        "Experiment_Model_Species": "Human",
        "Reference_ID_Type": "PMID",
        "Reference_ID": "PMID: 28530702; PMID: 32409589",
    },
    {
        "Interation_Record_ID": "PMDBI11",
        "Interaction_Category": ABUNDANCE,
        "MASI-Microbe-ID": "PMDBM2",
        "Microbe-Tax-ID": "562",
        "Microbe-Name": "Escherichia coli",
        "MASI-Substance-chemicalD": "PMDBD1",
        "Substance-Name": "Metformin",
        "Substance-Category": "Therapeutic Substance",
        "Substance-subCategory": "Approved Drug",
        "Microbe_Change": "Increase",
        "Experiment_System": "In vitro",
        "Experiment_Model_Species": "High-throughput incubation assays",
        "Reference_ID_Type": "DOI",
        "Reference_ID": "; DOI: 10.1000/xyz123",
    },
    {
        "Interation_Record_ID": "PMDBI12",
        "Interaction_Category": METABOLISM,
        "MASI-Microbe-ID": "PMDBM3",
        "Microbe-Tax-ID": "818",
        "Microbe-Name": "Bacteroides thetaiotaomicron",
        "MASI-Substance-chemicalD": "PMDBD4",
        "Substance-Name": "Baicalin",
        "Substance-Category": "Herbal Substance",
        "Substance-subCategory": "Medicinal Herbal Compounds",
        "Metabolites": "Baicalein",
        "Metabolism_Type": "Hydrolysis",
        "Metabolism_Effect_on_Drug": "Increase Efficacy",
        "Experiment_System": "In vitro",
        "Reference_ID_Type": "PMID",
        "Reference_ID": "26569070",
    },
    {
        "Interation_Record_ID": "PMDBI13",
        "Interaction_Category": "Microbes rearrange substances",
        "MASI-Microbe-ID": "PMDBM7",
        "Microbe-Tax-ID": "216816",
        "Microbe-Name": "Bifidobacterium longum",
        "MASI-Substance-chemicalD": "PMDBD6",
        "Substance-Name": "Vancomycin",
        "Substance-Category": "Therapeutic Substance",
        "Substance-subCategory": "Approved Drug; Antibiotics",
        "Experiment_System": "In vitro",
        "Reference_ID_Type": "PMID",
        "Reference_ID": "PMID: 31158845",
    },
]

DISEASE_HEADER = [
    "Association-record-ID",
    "Association-type",
    "MASI-Microbe-ID",
    "Microbe-Tax-ID",
    "Microbe-name",
    "Microbiota-site",
    "MASI-Disease-ID",
    "Disease-name",
    "Change-of-microbe",
    "Reference-type",
    "Reference-ID",
]

ASSOCIATION = "Microbe abundance associates with disease"

#: ``(record, microbe, tax id, name, site, disease id, disease label, change,
#: reference)``.
DISEASE_ROWS: list[tuple[str, ...]] = [
    (
        "PMDBDis1",
        "PMDBM3",
        "818",
        "Bacteroides thetaiotaomicron",
        "Gastrointestinal tract",
        "DIS1",
        "Colorectal cancer",
        "Decrease",
        "25079328",
    ),
    # The same pair, the other way: two edges, never a verdict (G4).
    (
        "PMDBDis2",
        "PMDBM3",
        "818",
        "Bacteroides thetaiotaomicron",
        "Gastrointestinal tract",
        "DIS1",
        "Colorectal cancer",
        "Increase",
        "22043294",
    ),
    (
        "PMDBDis3",
        "PMDBM2",
        "562",
        "Escherichia coli",
        "Gastrointestinal tract",
        "DIS2",
        "Obesity",
        "Increase",
        "28178201",
    ),
    (
        "PMDBDis4",
        "PMDBM4",
        NA,
        "Blautia spp.",
        "Gastrointestinal tract",
        "DIS3",
        "Irritable bowel syndrome (IBS)",
        "Decrease",
        "28039159",
    ),
    (
        "PMDBDis5",
        "PMDBM7",
        "216816",
        "Bifidobacterium longum",
        "Gastrointestinal tract",
        "DIS4",
        "Animal helminthiasis",
        "Decrease",
        "28179361",
    ),
    (
        "PMDBDis6",
        "PMDBM5",
        "976",
        "Bacteroidetes",
        "Skin",
        "DIS5",
        "Rheumatoid arthrits",
        "Increase",
        "28195358",
    ),
    # On the microbe that reaches no taxon: no edge, and the tombstone the
    # interaction table already wrote gains a second hit.
    (
        "PMDBDis7",
        "PMDBM6",
        NA,
        "Unclassified gut microbiota",
        "Gastrointestinal tract",
        "DIS1",
        "Colorectal cancer",
        "Decrease",
        "28279152",
    ),
]


def write(path: Path, header: list[str], rows: list[list]) -> None:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Sheet1"
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    book.save(path)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    write(OUT / FILES["microbes"], MICROBE_HEADER, MICROBE_ROWS)
    write(
        OUT / FILES["substances"],
        SUBSTANCE_HEADER,
        [
            [
                sid,
                name,
                category,
                subcategory,
                cas,
                drugbank,
                NA,
                NA,
                NA,
                pubchem,
                NA,
                NA,
                name.lower(),
                formula,
                NA,
                NA,
                NA,
                NA,
            ]
            for sid, name, category, subcategory, cas, drugbank, pubchem, formula in SUBSTANCE_ROWS
        ],
    )
    write(
        OUT / FILES["interactions"],
        INTERACTION_HEADER,
        [[row.get(c, NA) for c in INTERACTION_HEADER] for row in INTERACTION_ROWS],
    )
    write(
        OUT / FILES["diseases"],
        DISEASE_HEADER,
        [
            [
                record,
                ASSOCIATION,
                microbe,
                tax_id,
                name,
                site,
                disease_id,
                label,
                change,
                "PMID",
                reference,
            ]
            for record, microbe, tax_id, name, site, disease_id, label, change, reference in DISEASE_ROWS
        ],
    )
    print(
        f"wrote {len(FILES)} workbooks to {OUT}: "
        f"{len(INTERACTION_ROWS)} interaction records, "
        f"{len(DISEASE_ROWS)} disease associations, "
        f"{len(MICROBE_ROWS)} microbes, {len(SUBSTANCE_ROWS)} substances"
    )


if __name__ == "__main__":
    main()

"""The drug-join routes both published screens share.

``microbiomekg/drugs.py`` was lifted out of ``scripts/prep_maier2018.py`` when a
second screen needed the same three questions answered — what a level-5 ATC code
is, which suffixes are counter-ions, and which node one spelling reaches. The
per-source tests exercise it through a real build; what is asserted here is the
part neither of them can see from the outside: the index is built over
**whatever ``drug.csv`` holds when the source runs**, and the rules about which
identifiers are join keys at all.
"""

from __future__ import annotations

import csv
from pathlib import Path

from microbiomekg.drugs import DrugIndex, atc_level5, join_drug, strip_salt

DRUG_FIELDS = ["drug_id", "pref_name", "atc_codes", "source"]


def write_drug_csv(path: Path, rows: list[dict]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=DRUG_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_an_absent_drug_csv_is_an_empty_index_not_an_error(tmp_path):
    """A prep run before the source it depends on must mint rather than crash —
    a build that lost one source's raw files still has to produce the others."""
    index = DrugIndex.from_csv(tmp_path / "nothing.csv", exclude_source="maier2018")
    assert index.names == {} and index.atc == {} and index.source_of == {}
    assert join_drug([("name", "Vancomycin", "name")], index) == ("", "minted", [])


def test_the_index_skips_the_rows_this_source_wrote_on_a_previous_run(tmp_path):
    """`Writer(owner=("source", <this source>))` drops and rewrites this source's
    rows, so a second run that indexed them would join a compound to a node it
    is about to delete — and the recorded join route would differ between the
    first run and every one after it, which no count in the build report would
    reveal."""
    path = write_drug_csv(tmp_path / "drug.csv", [
        {"drug_id": "CHEMBL:CHEMBL262777", "pref_name": "VANCOMYCIN",
         "atc_codes": "J01XA01", "source": "chembl"},
        {"drug_id": "PRESTWICK:Prestw-9999", "pref_name": "Fictitine hydrochloride",
         "atc_codes": "", "source": "maier2018"},
    ])
    own = DrugIndex.from_csv(path, exclude_source="maier2018")
    assert "fictitine hydrochloride" not in own.names
    other = DrugIndex.from_csv(path, exclude_source="zimmermann2019")
    assert other.names["fictitine hydrochloride"] == "PRESTWICK:Prestw-9999"
    # And the source that wrote the row it landed on is readable, which is how a
    # later screen counts the compounds that only have a node because an earlier
    # screen minted one.
    assert other.source_of["PRESTWICK:Prestw-9999"] == "maier2018"


def test_an_atc_code_two_nodes_claim_is_a_join_key_for_neither(tmp_path):
    """A code is only an identifier while it names one substance. Picking one of
    two is the merge-on-a-shared-attribute failure the schema survey catalogues,
    and it is silent: the compound gets an edge, on the wrong molecule."""
    path = write_drug_csv(tmp_path / "drug.csv", [
        {"drug_id": "CHEMBL:A", "pref_name": "ALPHA", "atc_codes": "C07AA05",
         "source": "chembl"},
        {"drug_id": "CHEMBL:B", "pref_name": "BETA", "atc_codes": "C07AA05 N02BE01",
         "source": "chembl"},
    ])
    index = DrugIndex.from_csv(path, exclude_source="maier2018")
    assert "C07AA05" not in index.atc
    assert index.atc["N02BE01"] == "CHEMBL:B"
    # A *name* collision cannot arise — `drug.csv` is keyed on `drug_id` and the
    # first row per key wins — so both names stay keys.
    assert set(index.names) == {"alpha", "beta"}


def test_without_atc_applies_the_same_uniqueness_rule_from_the_other_side(tmp_path):
    """A source's own catalogue can give one code to two entries it measured
    separately (stereoisomers, a prodrug and its active form). Dropping the code
    lets both fall through to the next route instead of merging them."""
    path = write_drug_csv(tmp_path / "drug.csv", [
        {"drug_id": "CHEMBL:A", "pref_name": "PROPRANOLOL", "atc_codes": "C07AA05",
         "source": "chembl"},
    ])
    index = DrugIndex.from_csv(path, exclude_source="maier2018")
    assert index.atc["C07AA05"] == "CHEMBL:A"
    narrowed = index.without_atc({"C07AA05"})
    assert narrowed.atc == {}
    # The names lookup is untouched: a contested code loses a *route*, never the
    # compound.
    assert narrowed.names == index.names


def test_a_name_is_matched_casefolded_and_an_atc_code_upper_cased(tmp_path):
    """The two catalogues spell drugs `Vancomycin` and `VANCOMYCIN` and ChEMBL
    spells them a third way; the code is a real identifier and its case is not
    information."""
    path = write_drug_csv(tmp_path / "drug.csv", [
        {"drug_id": "CHEMBL:A", "pref_name": "VANCOMYCIN", "atc_codes": "J01XA01",
         "source": "chembl"},
    ])
    index = DrugIndex.from_csv(path, exclude_source="x")
    assert index.lookup("name", "  Vancomycin ") == "CHEMBL:A"
    assert index.lookup("atc", "j01xa01") == "CHEMBL:A"
    assert index.lookup("name", "vancomycin hydrochloride") is None


def test_the_first_route_wins_and_the_losers_are_returned_rather_than_hidden():
    """A precedence rule that silently discarded the other candidates would make
    the graph's own disagreement count unreadable. Both screens ledger these:
    every case is the verbatim name reaching a ChEMBL *salt* node while a
    derived spelling reaches its parent."""
    index = DrugIndex(
        names={"betamethasone acetate": "CHEMBL:CHEMBL1200538",
               "betamethasone": "CHEMBL:CHEMBL632"},
        atc={}, source_of={},
    )
    drug_id, route, others = join_drug([
        ("name", "Betamethasone acetate", "molename"),
        ("name", "Betamethasone", "salt-name"),
    ], index)
    assert (drug_id, route) == ("CHEMBL:CHEMBL1200538", "molename")
    assert others == ["CHEMBL:CHEMBL632"]
    # Two routes reaching the *same* node is agreement, not a disagreement.
    _id, _route, agreed = join_drug([
        ("name", "Betamethasone", "molename"),
        ("name", "Betamethasone", "salt-name"),
    ], index)
    assert agreed == []


def test_only_a_level_five_atc_code_is_a_join_key():
    """A level-4 code names a *class*: joining `L01BB` would put every
    nitrogen-mustard analogue on one node. The real cells are space-joined and
    mix levels, and the veterinary `Q` codes are eight characters and have no
    ChEMBL counterpart."""
    assert atc_level5("A07AB03") == ["A07AB03"]
    assert atc_level5("L01BB") == []
    assert atc_level5("C01EA01 G04BE01") == ["C01EA01", "G04BE01"]
    assert atc_level5("QJ01GB90 QJ51GB90 QA07AA92") == []
    assert atc_level5("-") == []
    assert atc_level5(None) == []


def test_a_salt_suffix_is_stripped_but_a_leading_counter_ion_word_is_not():
    """`Drug` is keyed on the parent molecule, so stripping a salt moves
    *towards* this graph's identity. "Sodium" as the **first** word is part of
    the drug's name, not a counter-ion, and a rule that did not know the
    difference would send `Sodium valproate` to a node named `valproate`."""
    assert strip_salt("Cetirizine dihydrochloride") == "Cetirizine"
    assert strip_salt("Quinidine hydrochloride monohydrate") == "Quinidine"
    assert strip_salt("Ampicillin") == "Ampicillin"
    assert strip_salt("Sodium valproate") == "Sodium valproate"
    assert strip_salt(None) == ""

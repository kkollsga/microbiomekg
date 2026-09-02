"""The condition column: pairing it, keying it, and routing it by vocabulary.

Guards C14 (the column named `EFO ID` is not EFO and not disease) and the
disease-hub recommendation from `docs/research/existing-graphs-and-schemas.md`
§5(a): MONDO is the canonical disease key, the source id and its vocabulary
stay as properties, and nothing is guessed.

Every MONDO stanza in `tests/fixtures/mondo_mini.obo` is copied verbatim from
the real 2026-09-01 release, so every assertion below is reproducible with a
`grep` on that file.
"""

from __future__ import annotations

import pytest

from microbiomekg.conditions import (
    malformed_curie,
    CONDITION_TYPES,
    MondoIndex,
    condition_node_type,
    curie_vocabulary,
    pair_conditions,
    split_curies,
)

from conftest import MONDO_MINI


@pytest.fixture(scope="module")
def mondo() -> MondoIndex:
    return MondoIndex.from_obo(MONDO_MINI)


# --------------------------------------------------------------------------
# The MONDO index
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "curie, label",
    [
        ("MONDO:0005052", "irritable bowel syndrome"),
        ("MONDO:0011122", "obesity disorder"),
        ("MONDO:0005575", "colorectal cancer"),
        ("MONDO:0024331", "colorectal carcinoma"),
        ("MONDO:0100096", "COVID-19"),
        ("MONDO:0025082", "helminthiasis, animal"),
    ],
)
def test_mondo_labels_are_read_from_the_obo(mondo, curie, label):
    assert mondo.label_for(curie) == label


def test_an_obsolete_mondo_term_is_not_a_live_key(mondo):
    """MONDO:0016667 is `is_obsolete: true` in the 2026-09-01 release.

    Two BugSigDB rows cite ids like it. Treating an obsolete term as live gives
    a Disease node whose label starts with the word "obsolete".
    """
    assert "MONDO:0016667" in mondo.obsolete
    assert mondo.label_for("MONDO:0016667") is None
    assert mondo.mondo_id("MONDO:0016667") is None


def test_a_live_mondo_id_is_its_own_hub_key(mondo):
    assert mondo.mondo_id("MONDO:0005052") == "MONDO:0005052"


@pytest.mark.parametrize(
    "foreign, mondo_curie",
    [
        ("EFO:0000555", "MONDO:0005052"),   # irritable bowel syndrome
        ("DOID:9778", "MONDO:0005052"),
        ("EFO:0004616", "MONDO:0005416"),   # osteoarthritis, knee
        ("DOID:4", "MONDO:0000001"),        # disease
    ],
)
def test_equivalence_xrefs_join_efo_and_doid_to_mondo(mondo, foreign, mondo_curie):
    """Only `source="MONDO:equivalentTo"` counts — MONDO's curated 1:1 axioms."""
    assert mondo.mondo_id(foreign) == mondo_curie


def test_a_source_attribute_is_not_an_equivalence(mondo):
    """`xref: DOID:4 {source="MONDO:equivalentTo", source="EFO:0000408"}` says
    MONDO:0000001 ≡ DOID:4 *as asserted by* EFO:0000408. It does not say
    MONDO:0000001 ≡ EFO:0000408.

    Reading it as one is a false merge, and it is measurable: over the real
    dump only four BugSigDB EFO ids acquire a MONDO term that way and all four
    are wrong — EFO:0000195 `Metabolic syndrome` would become MONDO:0000816
    `abdominal obesity-metabolic syndrome`, and EFO:0000180 `HIV-1 infection`
    would become MONDO:0004951 `susceptibility to HIV infection`.
    """
    assert mondo.mondo_id("EFO:0000408") is None


def test_an_unknown_curie_has_no_mondo_id(mondo):
    assert mondo.mondo_id("EFO:0000246") is None       # Age — a real BugSigDB id
    assert mondo.mondo_id("CHEBI:33281") is None
    assert mondo.mondo_id("not-a-curie") is None


# --------------------------------------------------------------------------
# C14 — pairing `Condition` against `EFO ID`
# --------------------------------------------------------------------------


def test_equal_counts_pair_positionally(mondo):
    got = pair_conditions(["EFO:0001799", "EXO:0000114"],
                          "Ethnic group,Socioeconomic status", mondo)
    assert got.pairs == [
        ("EFO:0001799", "Ethnic group"),
        ("EXO:0000114", "Socioeconomic status"),
    ]
    assert got.method == "positional"
    assert not got.unpaired_ids and not got.unpaired_labels


def test_a_comma_inside_a_condition_label_is_not_a_separator(mondo):
    """The C11 trap, in a second column: `Helminthiasis, animal` is ONE
    condition whose label contains a comma, and the column is comma-joined.

    All 42 mismatched-count rows of the real dump are this shape. A positional
    zip pairs `MONDO:0025082` with `Helminthiasis` and drops `animal`.
    """
    got = pair_conditions(["MONDO:0025082"], "Helminthiasis, animal", mondo)
    assert got.pairs == [("MONDO:0025082", "Helminthiasis, animal")]
    assert got.method == "label-matched"
    assert not got.unpaired_ids and not got.unpaired_labels


def test_label_matching_is_case_insensitive(mondo):
    got = pair_conditions(["MONDO:0005416"], "Osteoarthritis, knee", mondo)
    assert got.pairs == [("MONDO:0005416", "Osteoarthritis, knee")]


def test_label_matching_reassembles_only_the_run_that_matches(mondo):
    """Two ids, three fragments: only the run whose join equals a MONDO label
    is consumed, and the leftovers are reported rather than shuffled in."""
    got = pair_conditions(
        ["MONDO:0025082", "MONDO:0005052"],
        "Helminthiasis, animal,Irritable bowel syndrome",
        mondo,
    )
    assert sorted(got.pairs) == [
        ("MONDO:0005052", "Irritable bowel syndrome"),
        ("MONDO:0025082", "Helminthiasis, animal"),
    ]
    assert not got.unpaired_ids and not got.unpaired_labels


def test_a_single_id_owns_the_whole_condition_cell(mondo):
    """`MONDO:0001505` is `alcoholic hepatitis`; BugSigDB writes the condition
    as `Hepatitis, Alcoholic`, which no label match reassembles.

    With exactly one id there is no pairing decision to get wrong — the cell
    verbatim is that id's observed label. This is an identity, not a guess.
    """
    got = pair_conditions(["MONDO:0001505"], "Hepatitis, Alcoholic", mondo)
    assert got.pairs == [("MONDO:0001505", "Hepatitis, Alcoholic")]
    assert got.method == "single-id"
    assert not got.unpaired_ids and not got.unpaired_labels


def test_nothing_is_guessed_when_a_run_cannot_be_matched(mondo):
    """Two ids, three fragments, no label to reassemble by: the pairing is
    reported as unresolved instead of being invented."""
    got = pair_conditions(
        ["EFO:0000246", "EFO:0004340"], "Age,Body mass,index", mondo
    )
    assert got.pairs == []
    assert sorted(got.unpaired_ids) == ["EFO:0000246", "EFO:0004340"]
    assert got.unpaired_labels == ["Age", "Body mass", "index"]
    assert got.method == "unresolved"


def test_an_id_with_no_condition_string_is_still_a_pair(mondo):
    got = pair_conditions(["MONDO:0005052"], "", mondo)
    assert got.pairs == [("MONDO:0005052", "")]


def test_a_condition_string_with_no_id_is_not_dropped(mondo):
    got = pair_conditions([], "Some condition nobody coded", mondo)
    assert got.pairs == []
    assert got.unpaired_labels == ["Some condition nobody coded"]


def test_split_curies_handles_both_delimiters():
    assert split_curies("EFO:0001799,EXO:0000114") == ["EFO:0001799", "EXO:0000114"]
    assert split_curies("MONDO:0024647;MONDO:0008171") == [
        "MONDO:0024647",
        "MONDO:0008171",
    ]
    assert split_curies("") == []


# --------------------------------------------------------------------------
# C14 — routing by vocabulary
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "curie, node_type",
    [
        ("MONDO:0005575", "Disease"),
        ("EFO:1000165", "Disease"),
        ("DOID:9778", "Disease"),
        ("ORPHANET:101953", "Disease"),
        ("HP:0002745", "Phenotype"),
        ("CHEBI:33281", "Exposure"),
        ("CHEBI:6801", "Exposure"),
        ("ENVO:02500037", "Exposure"),
        ("EXO:0000114", "Exposure"),
        ("GSSO:000707", "Exposure"),
    ],
)
def test_the_prefix_picks_the_node_type(curie, node_type):
    assert condition_node_type(curie) == node_type


@pytest.mark.parametrize(
    "curie",
    [
        "NCBITAXON:568703",   # Lacticaseibacillus rhamnosus GG — an organism
        "GO:0007568",         # Aging — a biological process
        "OBA:1000110",        # Bone density — a measurement
        "CL:0000775",         # Neutrophil — a cell type
        "PATO:0000384",       # Male — a quality
        "OBI:0000711",        # Library preparation — a protocol
        "NCIT:C102763",       # Cervical cerclage — a procedure
        "XCO:0000671",        # Doxycycline under an experimental-condition id
        "PO:0009001",         # Fruit
        "BTO:0001616",        # a cell line
        "MP:0001845",         # a mouse phenotype term
        "IDOMAL:0001254",     # Population
        "PR:000000017",       # Interferon gamma
    ],
)
def test_vocabularies_with_no_node_type_are_routed_to_the_ledger(curie):
    """C14: typing all of these `:Disease` puts a *Lactobacillus* strain, a
    cell type and a surgical procedure in the disease list.

    They are not dropped — `condition_node_type` returning None is what sends
    them to `unresolved_conditions.csv` with their raw strings.
    """
    assert condition_node_type(curie) is None


def test_every_declared_node_type_is_one_of_the_three():
    assert set(CONDITION_TYPES.values()) == {"Disease", "Phenotype", "Exposure"}


def test_curie_vocabulary_reads_the_prefix():
    assert curie_vocabulary("MONDO:0005575") == "MONDO"
    assert curie_vocabulary("ncbitaxon_568703") == "NCBITAXON"
    assert curie_vocabulary("not a curie") == ""


# --------------------------------------------------------------------------
# CURIE shape — a malformed id is reported, never resolved
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "curie",
    [
        "DOID:585",        # 3 digits
        "DOID:0060180",    # 7 digits with leading zeros — the normal padded form
        "DOID:9",          # 1 digit
        "MONDO:0005148",
        "EFO:0000246",
        "HP:0002745",
    ],
)
def test_a_wellformed_curie_is_not_malformed(curie):
    assert malformed_curie(curie) is False


@pytest.mark.parametrize(
    "curie, why",
    [
        ("DOID:00400085", "8 digits with a leading double zero — gutMDisorder's own typo"),
        ("DOID:", "no local id at all"),
        ("DOID:9970a", "a trailing character"),
        ("MONDO:12", "MONDO ids are 7 digits"),
    ],
)
def test_a_malformed_curie_is_reported(curie, why):
    assert malformed_curie(curie) is True, why


def test_a_vocabulary_with_no_declared_shape_is_never_called_malformed():
    """The check exists to catch a typo in a vocabulary we know the shape of.
    Guessing a shape for one we do not would reject real ids — which is the
    silent drop this project forbids — so an unknown prefix is well-formed by
    definition and is routed by :func:`condition_node_type` as usual."""
    assert malformed_curie("BTO:0000759") is False
    assert malformed_curie("IDOMAL:0000633") is False


def test_a_malformed_doid_has_no_mondo_equivalence(mondo):
    """The one in the real data: `DOID:00400085`. It must not accidentally
    match anything, and the caller must be able to tell "malformed" from
    "simply not in MONDO" — the first is a source defect, the second is not."""
    assert mondo.mondo_id("DOID:00400085") is None
    assert malformed_curie("DOID:00400085") is True
    assert malformed_curie("DOID:9552") is False and mondo.mondo_id("DOID:9552") is None

"""One test per taxonomy pitfall, against the real interface.

Every tax_id below was read out of the real NCBI ``new_taxdump`` (2026-09-02
build) and copied verbatim into ``tests/fixtures/taxdump_mini/``. Nothing is
invented; each assertion is reproducible with a ``grep`` on the fixture.
The pitfall each test guards is named in
``docs/usecases-and-pitfalls.md`` Part C.
"""

from __future__ import annotations

import pytest

from microbiomekg.reconcile import Resolution, TaxonomyIndex

from conftest import TAXDUMP_MINI, read_dmp

RESOLVED_STATUSES = frozenset({"exact", "synonym", "merged", "promoted"})
UNRESOLVED_STATUSES = frozenset({"ambiguous", "deleted", "unresolved"})
ALL_STATUSES = RESOLVED_STATUSES | UNRESOLVED_STATUSES


@pytest.fixture(scope="module")
def index(taxdump_dir) -> TaxonomyIndex:
    return TaxonomyIndex.from_taxdump(taxdump_dir)


# --------------------------------------------------------------------------
# C1 — name classes
# --------------------------------------------------------------------------


def test_scientific_name_resolves_exact(index):
    """C1: the plain scientific name is the exact case."""
    r = index.resolve("Escherichia coli")
    assert r.status == "exact"
    assert r.tax_id == 562
    assert r.matched_name == "Escherichia coli"
    assert r.candidates == ()


def test_lookup_is_case_insensitive(index):
    """C1: papers write `escherichia coli`, `E. COLI`, `Escherichia Coli`."""
    for spelling in ("escherichia coli", "ESCHERICHIA COLI", "Escherichia Coli"):
        r = index.resolve(spelling)
        assert r.tax_id == 562, f"{spelling!r} did not resolve to 562"


def test_includes_class_is_searched(index):
    """C1: `includes` is a lookup class. `bacterium 10a` is filed under 562."""
    r = index.resolve("bacterium 10a")
    assert r.tax_id == 562
    assert r.status == "synonym", "a non-scientific-name match is not `exact`"
    assert r.matched_name == "bacterium 10a"


def test_authority_class_is_not_a_lookup_class(index):
    """C1: `Lactobacillus plantari` exists ONLY inside an `authority` string.

    The real row is::

        1590 | "Lactobacillus plantari" (sic) (Orla-Jensen 1919) ... | | authority |

    It is a recorded misspelling, not a name anyone used. Matching the
    `authority` class would make it resolve to 1590.
    """
    r = index.resolve("Lactobacillus plantari")
    assert r.status == "unresolved"
    assert r.tax_id is None


# --------------------------------------------------------------------------
# C2 / C3 — homonyms
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, candidates",
    [
        ("Bacillus", (1386, 55087)),        # bacteria / walking sticks
        ("Proteus", (583, 210425)),         # enterobacteria / salamanders
        ("Morganella", (581, 90690, 108061)),  # bacteria / fungi / scale insects
    ],
)
def test_homonym_genus_is_ambiguous(index, name, candidates):
    """C2: never first-wins. All candidates, no tax_id."""
    r = index.resolve(name)
    assert r.status == "ambiguous"
    assert r.tax_id is None
    assert tuple(sorted(r.candidates)) == tuple(sorted(candidates))


@pytest.mark.parametrize(
    "name, candidates",
    [
        # Both are bacteria, so "prefer the bacterial candidate" does not save you.
        ("Bacteroides corrodens", (539, 827)),   # Eikenella / Campylobacter ureolyticus
        ("Bacillus brevis", (1393, 2815668)),    # Brevibacillus / a stick insect
    ],
)
def test_intra_bacterial_homonym_is_ambiguous(index, name, candidates):
    """C3: the collision is inside the bacteria, not across kingdoms."""
    r = index.resolve(name)
    assert r.status == "ambiguous"
    assert r.tax_id is None
    assert tuple(sorted(r.candidates)) == tuple(sorted(candidates))


# --------------------------------------------------------------------------
# C4 / C5 — renamed taxa and authority-decorated synonyms
# --------------------------------------------------------------------------

# (legacy name used in papers, tax_id, is the bare form present in names.dmp?)
LEGACY_NAMES = [
    ("Clostridium difficile", 1496, False),
    ("Propionibacterium acnes", 1747, True),
    ("Ruminococcus gnavus", 33038, True),
    ("Lactobacillus reuteri", 1598, False),
    ("Lactobacillus plantarum", 1590, False),
    ("Lactobacillus rhamnosus", 47715, True),
    ("Eubacterium rectale", 39491, False),
]


@pytest.mark.parametrize("name, tax_id, bare_synonym_exists", LEGACY_NAMES)
def test_legacy_binomial_resolves_via_authority_stripping(
    index, name, tax_id, bare_synonym_exists
):
    """C4: the 2020 renames, including the four NCBI keeps only decorated.

    For 1496, 1598, 1590 and 39491 the bare binomial is absent from
    ``names.dmp`` — only the authority-decorated `synonym` row exists — so a
    literal name-class index returns `unresolved` for *Clostridium
    difficile*, the most-cited renamed organism in the field.
    """
    r = index.resolve(name)
    assert r.status == "synonym", f"{name!r} came back {r.status!r}"
    assert r.tax_id == tax_id
    assert r.candidates == ()


@pytest.mark.parametrize(
    "name, tax_id",
    [(n, t) for n, t, bare in LEGACY_NAMES if not bare],
)
def test_decorated_only_synonym_records_the_normalisation(index, name, tax_id):
    """C4/C20.2: the match needed authority stripping — say so in `note`.

    `status` cannot carry it (the enum has no value for "matched after
    normalisation"), so `note` is the only place the audit trail can live.
    """
    r = index.resolve(name)
    assert r.tax_id == tax_id
    assert r.note, f"{name!r} matched only after normalisation but note is empty"


@pytest.mark.parametrize(
    "name, tax_id",
    [
        # A greedy normaliser maps "Escherichia coli K-12" -> "escherichia coli",
        # which makes the normalised index ambiguous between 562 and 83333.
        ("Escherichia coli", 562),
        ("Escherichia coli K-12", 83333),
    ],
)
def test_exact_match_beats_normalised_match(index, name, tax_id):
    """C5: consult the exact index first; normalise only on a miss."""
    r = index.resolve(name, rank_ceiling="strain")
    assert r.status == "exact", f"{name!r} came back {r.status!r}, not exact"
    assert r.tax_id == tax_id


# --------------------------------------------------------------------------
# C6 — merged, deleted, unknown ids
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "old, new",
    [
        (1440055, 1496),   # a retired Clostridioides difficile id
        (1581190, 1496),   # a second one
        (1129128, 1598),
        (299639, 47715),
        (83834, 1590),
        (105824, 853),
    ],
)
def test_merged_id_resolves_to_survivor(index, old, new):
    """C6: merged.dmp maps old -> survivor; the original must be kept."""
    r = index.resolve(tax_id=old)
    assert r.status == "merged"
    assert r.tax_id == new
    assert r.original_tax_id == old, "dropping the original makes the merge unauditable"


@pytest.mark.parametrize("dead", [1009, 1029, 1036])
def test_deleted_id_has_no_tax_id(index, dead):
    """C6: delnodes.dmp ids were withdrawn with no successor."""
    r = index.resolve(tax_id=dead)
    assert r.status == "deleted"
    assert r.tax_id is None, "inventing a survivor is worse than admitting the loss"
    assert r.original_tax_id == dead


def test_unknown_id_is_unresolved(index):
    """C6: an id in none of nodes/merged/delnodes."""
    r = index.resolve(tax_id=999999999)
    assert r.status == "unresolved"
    assert r.tax_id is None
    assert r.original_tax_id == 999999999


# --------------------------------------------------------------------------
# C7 — promotion
# --------------------------------------------------------------------------


def test_strain_promotes_to_species(index):
    """C7: 83333 `Escherichia coli K-12`, rank strain, parent 562."""
    r = index.resolve(tax_id=83333)
    assert r.status == "promoted"
    assert r.tax_id == 562
    assert r.original_tax_id == 83333
    assert r.original_rank == "strain"


def test_subspecies_promotes_to_species(index):
    """C7: 1682 `Bifidobacterium longum subsp. infantis` -> 216816."""
    r = index.resolve(tax_id=1682)
    assert r.status == "promoted"
    assert r.tax_id == 216816
    assert r.original_tax_id == 1682
    assert r.original_rank == "subspecies"


def test_strain_name_promotes_too(index):
    """C7: promotion is a property of the taxon, not of the lookup route."""
    r = index.resolve("Escherichia coli K-12")
    assert r.status == "promoted"
    assert r.tax_id == 562
    assert r.original_tax_id == 83333


@pytest.mark.parametrize(
    "tax_id, rank",
    [
        (1386, "genus"),      # Bacillus
        (186803, "family"),   # Lachnospiraceae
        (562, "species"),     # Escherichia coli, exactly at the ceiling
    ],
)
def test_rank_at_or_above_ceiling_is_not_promoted(index, tax_id, rank):
    """C7: promotion is downward-only; a genus is already above species."""
    r = index.resolve(tax_id=tax_id)
    assert r.status == "exact"
    assert r.tax_id == tax_id
    assert r.original_rank == rank


def test_rank_ceiling_genus_promotes_a_species(index):
    """C7: the ceiling is a parameter, not a constant."""
    r = index.resolve(tax_id=562, rank_ceiling="genus")
    assert r.status == "promoted"
    assert r.tax_id == 561, "Escherichia"
    assert r.original_tax_id == 562
    assert r.original_rank == "species"


# --------------------------------------------------------------------------
# C8 — rank-less nodes
# --------------------------------------------------------------------------


def test_promotion_terminates_at_self_parent_root(index):
    """C8: `1 | 1 | no rank` — root is its own parent.

    A promotion loop without a self-parent guard spins here forever; the
    120 s pytest ceiling turns that into a failure rather than a wedged run.
    """
    r = index.resolve(tax_id=1)
    assert r.status in ALL_STATUSES
    assert r.tax_id == 1


@pytest.mark.parametrize(
    "tax_id, rank",
    [
        (131567, "cellular root"),  # a rank string most rank tables lack
        (1783257, "clade"),         # PVC group, in the Akkermansia lineage
        (48479, "no rank"),         # environmental samples, parent of 77133
        (2646097, "no rank"),       # unclassified Bacteroides, parent of 29523
    ],
)
def test_rankless_and_clade_nodes_do_not_break_resolution(index, tax_id, rank):
    """C8: the lineage is not a rank ladder; 23 fixture nodes are `clade`."""
    r = index.resolve(tax_id=tax_id)
    assert r.status == "exact"
    assert r.tax_id == tax_id
    assert r.original_rank == rank


def test_species_whose_parent_is_rankless_still_resolves(index):
    """C8: 77133's parent is `environmental samples` (no rank), not a genus."""
    r = index.resolve(tax_id=77133)
    assert r.status == "exact"
    assert r.tax_id == 77133


# --------------------------------------------------------------------------
# C9 — placeholder names
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, tax_id",
    [
        ("uncultured bacterium", 77133),
        ("Bacteroides sp.", 29523),
        ("[Clostridium] symbiosum", 1512),
        ("Candidatus Cibiobacter qucibialis", 2500537),
    ],
)
def test_placeholder_names_resolve_verbatim(index, name, tax_id):
    """C9: brackets and `Candidatus` are part of the scientific name string."""
    r = index.resolve(name)
    assert r.status == "exact"
    assert r.tax_id == tax_id
    assert r.matched_name == name


def test_unbracketed_name_resolves_through_the_synonym_row(index):
    """C9: NCBI files the unbracketed form as a real `synonym` — for 1512.

    It is not a normalisation the resolver has to invent, and it must not be:
    the bracket marker is per-taxon curation, so whether the plain binomial
    exists is a fact about `names.dmp`, not a rule.
    """
    r = index.resolve("Clostridium symbiosum")
    assert r.tax_id == 1512
    assert r.status == "synonym"


def test_stripping_the_candidatus_prefix_does_not_match(index):
    """C9: `Candidatus` has no such synonym row — stripping it invents a hit."""
    r = index.resolve("Cibiobacter qucibialis")
    assert r.status == "unresolved"
    assert r.tax_id is None


# --------------------------------------------------------------------------
# Interface contract
# --------------------------------------------------------------------------


def test_tax_id_wins_over_name(index):
    """Both given: the id decides. The name here points somewhere else."""
    r = index.resolve("Escherichia coli", tax_id=1496)
    assert r.tax_id == 1496
    assert r.status == "exact"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "Bacillus"},                    # ambiguous
        {"tax_id": 1009},                        # deleted
        {"tax_id": 999999999},                   # unresolved
        {"name": "not an organism at all"},      # unresolved
    ],
)
def test_no_tax_id_for_unresolved_statuses(index, kwargs):
    r = index.resolve(**kwargs)
    assert r.status in UNRESOLVED_STATUSES
    assert r.tax_id is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {},                                   # neither name nor id
        {"name": ""},
        {"name": "NA"},                       # BugSigDB's spelling of missing
        {"name": None, "tax_id": None},
        {"name": "Bacillus", "rank_ceiling": "not-a-rank"},
        {"tax_id": -1},
        {"tax_id": 0},
        {"name": "x" * 5000},
        {"name": "Escherichia\tcoli\n"},
    ],
)
def test_resolve_never_raises(index, kwargs):
    """The interface says it never raises: a bad input is a Resolution, not an exception."""
    r = index.resolve(**kwargs)
    assert isinstance(r, Resolution)
    assert r.status in ALL_STATUSES


def test_status_vocabulary_is_exactly_the_declared_one(index):
    """Every status the fixture can produce is in the declared enum."""
    probes = [
        {"name": "Escherichia coli"},
        {"name": "Ruminococcus gnavus"},
        {"tax_id": 1440055},
        {"tax_id": 83333},
        {"name": "Bacillus"},
        {"tax_id": 1009},
        {"tax_id": 999999999},
    ]
    seen = {index.resolve(**p).status for p in probes}
    assert seen <= ALL_STATUSES
    assert seen == ALL_STATUSES, f"fixture failed to exercise {ALL_STATUSES - seen}"


def test_candidates_is_a_tuple_of_ints(index):
    r = index.resolve("Morganella")
    assert isinstance(r.candidates, tuple)
    assert all(isinstance(c, int) and not isinstance(c, bool) for c in r.candidates)


# --------------------------------------------------------------------------
# Fixture self-checks — these fail if the fixture itself drifts
# --------------------------------------------------------------------------


@pytest.mark.fixture
def test_fixture_taxdump_is_in_real_ncbi_format():
    """tab-pipe-tab separated, trailing tab-pipe. Nothing hand-typed."""
    for name in ("names.dmp", "nodes.dmp", "merged.dmp", "delnodes.dmp"):
        raw = (TAXDUMP_MINI / name).read_text(encoding="utf-8")
        assert raw.endswith("|\n"), f"{name} lost its trailing tab-pipe"
        for line in raw.splitlines():
            assert line.endswith("\t|"), f"{name}: {line!r}"
            assert line.split("\t|")[0].strip().isdigit()


@pytest.mark.fixture
def test_fixture_contains_the_pitfall_taxa():
    ids = {int(r[0]) for r in read_dmp(TAXDUMP_MINI / "nodes.dmp")}
    required = {
        1, 131567, 562, 83333, 1496, 1747, 33038, 1598, 1590, 47715, 39491,
        853, 216816, 1682, 1386, 55087, 583, 210425, 581, 90690, 108061,
        539, 827, 1393, 2815668, 29523, 77133, 1512, 2500537,
    }
    assert required <= ids, f"fixture lost {sorted(required - ids)}"
    assert 1440055 not in ids, "a merged id must not be a live node"
    assert 1009 not in ids, "a deleted id must not be a live node"

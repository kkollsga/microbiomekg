"""ChEMBL: approved drugs, their protein targets, and the salt trap between them.

Every assertion here is a *failure mode first*. The fixture
(``tests/fixtures/chembl_mini/``, three JSONL files in ChEMBL's own REST shape)
carries one row per trap from ``docs/research/source-formats.md`` §6, and the
loader is measured against what each trap would silently do:

* **keying a drug on ``molecule_chembl_id``** splits one drug across its salt
  forms — 1,626 mechanism rows in the real file name a salt, so metformin and
  metformin hydrochloride become two ``Drug`` nodes with half the mechanisms
  each, and no query says so;
* **filtering mechanisms to the molecules file** drops 49% of the mechanism
  rows, because ``mechanism.jsonl`` names 5,954 molecules and
  ``molecule_max_phase4.jsonl`` holds 3,025 of them;
* **comparing ``max_phase`` across the two files** silently fails: it is the
  integer ``4`` on a mechanism row and the string ``"4.0"`` on a molecule row,
  so ``==`` is false for every pair;
* **writing every ``PubMed`` ``ref_id`` as ``PMID:<id>``** mints
  ``PMID:https://www.ncbi.nlm.nih.gov/...`` from the two rows whose id is a URL;
* **a junction row whose endpoint does not exist vivifies a stub node** — so a
  target taxid the loaded taxonomy does not carry must become a ledger row, not
  an edge to a made-up ``Taxon``.

The second half is what this source is *for*: `ProteinTarget.tax_id` is the
only field in ChEMBL that touches a microbe, and it is what makes D8's "which
drugs hit bacterial targets" answerable at all. It is one leg of that query and
not the main one — binding a protein an organism has is a different claim from
stopping that organism growing — and the direct drug↔taxon layer came from the
two published screens instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from prep_support import append_rows, load_graph_for, rows_of, run_prep

from conftest import BUGSIGDB_MINI, MONDO_MINI, TAXDUMP_MINI

kglite = pytest.importorskip("kglite")

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "chembl_mini"
SCRIPTS = ROOT / "scripts"
PREPS_DIR = ROOT / "microbiomekg" / "preps"
PREP = PREPS_DIR / "prep_chembl.py"
GUTMD_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "gutmdisorder_mini"


for _needed in (PREP, FIXTURE / "mechanism.jsonl"):
    if not _needed.exists():
        pytest.skip(f"{_needed} does not exist yet", allow_module_level=True)

from microbiomekg.preps.prep_chembl import drug_key, parent_index  # noqa: E402

from microbiomekg.ontology import EVIDENCE_LEVEL_VALUES  # noqa: E402
from microbiomekg.ontology.chembl import (  # noqa: E402
    LICENCE,
    RELEASE,
    evidence_level,
    max_phase,
    publication_curie,
)

SOURCE = "chembl"

# --------------------------------------------------------------------------
# Golden values, derived from the fixture by hand and asserted exactly.
# --------------------------------------------------------------------------

MECHANISM_ROWS = 30
#: 28 of the 30 reach a target; two have a null `target_chembl_id` and a null
#: `action_type`, which is 7.6% of the real file.
MECHANISM_EDGES = 28
TARGETLESS_MECHANISMS = 2

#: 12 molecule rows collapse to 11 nodes (metformin hydrochloride folds onto
#: metformin), plus 2 minimal nodes for mechanism molecules the molecules file
#: does not carry.
DRUG_NODES = 13
APPROVED_DRUGS = 11
UNAPPROVED_DRUGS = 2
COLLAPSED_SALTS = 1

PROTEIN_TARGETS = 10
#: Only the three targets whose organism is in the loaded taxonomy. The six
#: human targets cite 9606, which `taxdump_mini` does not carry, and one target
#: has no `tax_id` at all — seven ledger rows, zero vivified taxa.
OF_ORGANISM_EDGES = 3
TARGETS_WITHOUT_TAXON = 7

#: 7 target-organism rows + 2 targetless mechanisms + 1 non-numeric PubMed
#: ref + 4 interventions that matched no ChEMBL name.
LEDGER_ROWS = 14
UNLINKED_INTERVENTIONS = 4
IS_DRUG_EDGES = 2

EVIDENCE_SPLIT = {"interventional-rct": 11, "in-vitro": 12, "unknown": 5}

#: The two rows gutMDisorder's mini workbook does not curate but its real
#: workbook does. Appended to the intervention table in gutMDisorder's own
#: column shape rather than editing another source's fixture: the real
#: `intervention.csv` carries Metformin (DB00331) and Vancomycin, and without a
#: drug-named intervention there is nothing for `IS_DRUG` to link.
EXTRA_INTERVENTIONS = [
    {
        "intervention_id": "INTERVENTION:metformin",
        "label": "Metformin",
        "intervention_type": "Drug",
        "drugbank_id": "DB00331",
        "source": "gutmdisorder",
    },
    {
        "intervention_id": "INTERVENTION:vancomycin",
        "label": "Vancomycin",
        "intervention_type": "Drug",
        "drugbank_id": "DB00512",
        "source": "gutmdisorder",
    },
    # ChEMBL knows this molecule as ASPIRIN. An exact match is the whole rule,
    # so this is a ledger row, not a link — see the test that says why.
    {
        "intervention_id": "INTERVENTION:acetylsalicylic-acid",
        "label": "Acetylsalicylic acid",
        "intervention_type": "Drug",
        "drugbank_id": "DB00945",
        "source": "gutmdisorder",
    },
    # gutMDisorder's own comma-multivalued shape (`Clarithromycin,Metronidazole`
    # in the real workbook): two drugs in one label, both of which ChEMBL knows.
    {
        "intervention_id": "INTERVENTION:ampicillin-vancomycin",
        "label": "Ampicillin,Vancomycin",
        "intervention_type": "Drug",
        "drugbank_id": "",
        "source": "gutmdisorder",
    },
]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Three sources through their real prep scripts, then the real blueprint."""
    work = tmp_path_factory.mktemp("chembl")
    csv_dir = work / "csv"
    csv_dir.mkdir()

    def run(script, *args):
        return run_prep(script, *args)

    run(
        PREPS_DIR / "prep_bugsigdb.py",
        "--raw",
        str(BUGSIGDB_MINI),
        "--taxdump",
        str(TAXDUMP_MINI),
        "--mondo",
        str(MONDO_MINI),
        "--out",
        str(csv_dir),
    )
    run(
        PREPS_DIR / "prep_gutmdisorder.py",
        "--workbooks",
        str(GUTMD_FIXTURE),
        "--taxdump",
        str(TAXDUMP_MINI),
        "--mondo",
        str(MONDO_MINI),
        "--out",
        str(csv_dir),
    )
    append_rows(csv_dir, "intervention", EXTRA_INTERVENTIONS)

    prep = run(
        PREP,
        "--chembl",
        str(FIXTURE),
        "--taxdump",
        str(TAXDUMP_MINI),
        "--out",
        str(csv_dir),
    )
    run(
        PREPS_DIR / "prep_taxonomy.py",
        "--taxdump",
        str(TAXDUMP_MINI),
        "--out",
        str(csv_dir),
        "--scope",
        "cited",
        "--cited-from",
        str(csv_dir / "cited_taxa.csv"),
    )

    sources = ["bugsigdb", "gutmdisorder", SOURCE]
    graph = load_graph_for(csv_dir, sources)
    return graph, csv_dir, prep.stdout


@pytest.fixture(scope="module")
def graph(built):
    return built[0]


@pytest.fixture(scope="module")
def csv_dir(built):
    return built[1]


@pytest.fixture(scope="module")
def prep_output(built):
    return built[2]


def rows(graph, query):
    return list(graph.cypher(query))


def one(graph, query):
    result = rows(graph, query)
    assert result, f"query returned no rows:\n{query}"
    return result[0]


def table(csv_dir, name):
    return rows_of(csv_dir, name)


def ledger(csv_dir, kind=None):
    got = [r for r in table(csv_dir, "unresolved_chembl.csv")]
    return [r for r in got if kind is None or r["kind"] == kind]


# --------------------------------------------------------------------------
# `max_phase` — the same field with two types in two files
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        (4, 4),
        ("4.0", 4),
        ("4", 4),
        (4.0, 4),
        (-1, -1),
        ("-1.0", -1),
        (None, None),
        ("", None),
        ("NA", None),
    ],
)
def test_max_phase_normalises_both_spellings(value, expected):
    assert max_phase(value) == expected


def test_the_two_spellings_are_not_equal_until_they_are_normalised():
    """`mechanism.max_phase` is the integer 4 and `molecule.max_phase` is the
    string "4.0". A build that compares them raw finds no approved molecule at
    all and reports it as a coverage gap."""
    assert 4 != "4.0"
    assert max_phase(4) == max_phase("4.0")


# --------------------------------------------------------------------------
# The salt trap — one drug must not become several nodes
# --------------------------------------------------------------------------


def test_parent_index_maps_a_salt_onto_its_parent():
    mechanisms = [
        {"molecule_chembl_id": "CHEMBL1703", "parent_molecule_chembl_id": "CHEMBL1431"},
        {"molecule_chembl_id": "CHEMBL1431", "parent_molecule_chembl_id": "CHEMBL1431"},
    ]
    parents = parent_index(mechanisms)
    assert parents == {"CHEMBL1703": "CHEMBL1431"}
    assert drug_key("CHEMBL1703", parents) == "CHEMBL:CHEMBL1431"
    assert drug_key("CHEMBL1431", parents) == "CHEMBL:CHEMBL1431"


def test_a_molecule_with_no_parent_evidence_keeps_its_own_id():
    """`molecule_max_phase4.jsonl` carries no `molecule_hierarchy` field, so a
    molecule no mechanism names has no parent evidence anywhere in the fetched
    subset. Inventing one would be a guess; the id is kept as given."""
    assert drug_key("CHEMBL25", {}) == "CHEMBL:CHEMBL25"


def test_the_salt_and_its_parent_are_one_drug_node(graph):
    """1,626 real mechanism rows name a salt. Keyed on `molecule_chembl_id`,
    metformin's mechanisms split across two nodes and every count over them —
    "how many targets does this drug have?" — is silently halved."""
    assert not rows(graph, "MATCH (d:Drug {id: 'CHEMBL:CHEMBL1703'}) RETURN d")
    result = one(
        graph,
        "MATCH (d:Drug {id: 'CHEMBL:CHEMBL1431'}) "
        "RETURN d.title AS name, d.salt_ids AS salts, d.approved AS approved",
    )
    assert result["name"] == "METFORMIN"
    assert result["salts"] == ["CHEMBL1703"]
    assert result["approved"] is True


def test_the_edge_from_a_salt_row_keeps_the_id_the_source_wrote(graph):
    """Keying on the parent is a normalisation, and every normalisation in this
    graph stays reversible: the salt id the mechanism row actually carried is on
    the edge, so "which salt form was this curated against?" survives."""
    result = one(
        graph,
        "MATCH (:Drug {id: 'CHEMBL:CHEMBL1431'})-[r:HAS_MECHANISM]->() "
        "WHERE r.reported_molecule_chembl_id <> 'CHEMBL1431' "
        "RETURN r.reported_molecule_chembl_id AS reported, r.source_record_id AS mec",
    )
    assert result["reported"] == "CHEMBL1703"
    assert result["mec"] == "3"


def test_the_drug_node_count_is_the_collapsed_union(graph, prep_output):
    result = one(
        graph,
        "MATCH (d:Drug) RETURN count(d) AS drugs, "
        "sum(CASE WHEN d.approved THEN 1 ELSE 0 END) AS approved",
    )
    assert result["drugs"] == DRUG_NODES
    assert result["approved"] == APPROVED_DRUGS
    assert f"{COLLAPSED_SALTS} salt form(s) folded onto a parent" in prep_output


# --------------------------------------------------------------------------
# The molecule file does not cover the mechanism file
# --------------------------------------------------------------------------


def test_a_mechanism_naming_an_unlisted_molecule_still_becomes_an_edge(graph):
    """`mechanism.jsonl` names 5,954 molecules; the max_phase-4 file holds
    3,025. Filtering mechanisms to the molecules file drops 49% of them, and
    those drops are silent. A minimal node flagged `approved = false` keeps the
    mechanism and makes the gap one WHERE clause away."""
    result = rows(
        graph,
        "MATCH (d:Drug) WHERE NOT d.approved "
        "RETURN d.id AS id, d.title AS name, d.max_phase AS phase",
    )
    assert {r["id"] for r in result} == {"CHEMBL:CHEMBL9999901", "CHEMBL:CHEMBL9999903"}
    assert len(result) == UNAPPROVED_DRUGS
    # No name and no approval year: the molecules file is where those live.
    assert all(not r["name"] for r in result)
    reached = one(
        graph,
        "MATCH (d:Drug)-[r:HAS_MECHANISM]->() WHERE NOT d.approved RETURN count(r) AS edges",
    )
    assert reached["edges"] == 4


def test_an_unapproved_drugs_key_is_still_the_parent(graph):
    """mec 19 names CHEMBL9999902 with parent CHEMBL9999903, and neither is in
    the molecules file. The parent rule does not depend on the molecule being
    approved, or a salt of an unapproved drug becomes its own node."""
    result = one(
        graph,
        "MATCH (d:Drug {id: 'CHEMBL:CHEMBL9999903'})-[r:HAS_MECHANISM]->(t:ProteinTarget) "
        "RETURN r.reported_molecule_chembl_id AS reported, t.id AS target",
    )
    assert result["reported"] == "CHEMBL9999902"
    assert result["target"] == "CHEMBL:CHEMBL1795148"


# --------------------------------------------------------------------------
# The mechanism edge and its evidence
# --------------------------------------------------------------------------


def test_every_mechanism_row_is_an_edge_or_a_ledger_row(graph, csv_dir, prep_output):
    """C18. 577 real mechanism rows (7.6%) have a null target and a null action
    type — real curated mechanisms with no protein endpoint. They are recorded,
    never written as a dangling edge and never dropped."""
    edges = one(graph, "MATCH ()-[r:HAS_MECHANISM]->() RETURN count(r) AS n")["n"]
    targetless = ledger(csv_dir, "mechanism_without_target")
    assert edges == MECHANISM_EDGES
    assert len(targetless) == TARGETLESS_MECHANISMS
    assert edges + len(targetless) == MECHANISM_ROWS
    # The mechanism sentence is what would be lost, so it is what is recorded.
    assert {r["detail"] for r in targetless} == {
        "Osmotic laxative",
        "Prostaglandin synthesis inhibitor, target unresolved",
    }
    assert f"{MECHANISM_ROWS:,} mechanism rows" in prep_output


def test_parallel_mechanisms_on_one_pair_stay_parallel(graph):
    """Ampicillin binds PBP3 as an inhibitor and as a binding agent: two curated
    assertions with two mec_ids and two references. Collapsing them to one edge
    would drop a reference and a curator's distinction."""
    result = rows(
        graph,
        "MATCH (:Drug {id: 'CHEMBL:CHEMBL174'})-[r:HAS_MECHANISM]->"
        "(:ProteinTarget {id: 'CHEMBL:CHEMBL3623'}) "
        "RETURN r.action_type AS action, r.source_record_id AS mec "
        "ORDER BY mec",
    )
    assert [(r["action"], r["mec"]) for r in result] == [
        ("INHIBITOR", "6"),
        ("BINDING AGENT", "7"),
    ]


@pytest.mark.parametrize(
    "phase, ref_types, expected",
    [
        (4, ("DailyMed",), "interventional-rct"),
        (4, ("FDA", "PubMed"), "interventional-rct"),
        (4, ("EMA",), "interventional-rct"),
        (4, ("PMDA",), "interventional-rct"),
        (4, ("PubMed",), "in-vitro"),
        (4, ("PubMed", "DOI"), "in-vitro"),
        (4, ("PMC",), "in-vitro"),
        # An approved label is what makes it interventional; phase 2 with the
        # same reference is not an approved clinical use.
        (2, ("DailyMed",), "unknown"),
        (4, (), "unknown"),
        (4, ("Wikipedia",), "unknown"),
        # Strict: "the only references are literature". One Wikipedia entry in
        # the set means the mechanism is not carried by papers alone.
        (4, ("PubMed", "Wikipedia"), "unknown"),
        (4, ("ISBN",), "unknown"),
    ],
)
def test_evidence_level_follows_part_bs_table(phase, ref_types, expected):
    assert evidence_level(phase, ref_types) == expected


def test_no_mechanism_is_ever_computationally_predicted():
    """Part B, verbatim: "Never `computational-predicted` — nothing in this
    subset is predicted." Every ChEMBL mechanism is a curated assertion."""
    levels = {
        evidence_level(phase, refs)
        for phase in (-1, 1, 2, 3, 4)
        for refs in ((), ("PubMed",), ("DailyMed",), ("Other",), ("PubMed", "FDA"))
    }
    assert levels <= {"interventional-rct", "in-vitro", "unknown"}
    assert levels <= set(EVIDENCE_LEVEL_VALUES)


def test_the_evidence_split_over_the_built_edges(graph):
    result = {
        r["level"]: r["edges"]
        for r in rows(
            graph,
            "MATCH ()-[r:HAS_MECHANISM]->() "
            "RETURN r.evidence_level AS level, count(r) AS edges",
        )
    }
    assert result == EVIDENCE_SPLIT
    assert set(result) <= set(EVIDENCE_LEVEL_VALUES)


def test_every_edge_carries_its_provenance_and_the_share_alike_licence(graph):
    """G3, and the licence is not decoration: ChEMBL is CC BY-SA 3.0, so this
    slice is what forces a derived graph to share alike. Carrying it per edge is
    what lets the rest of the graph be redistributed on its own terms."""
    result = rows(
        graph,
        "MATCH ()-[r:HAS_MECHANISM]->() RETURN DISTINCT r.primary_source AS source, "
        "r.source_licence AS licence, r.knowledge_level AS kl, r.agent_type AS agent, "
        "r.chembl_release AS release",
    )
    assert result == [
        {
            "source": SOURCE,
            "licence": LICENCE,
            "kl": "knowledge_assertion",
            "agent": "manual_agent",
            "release": RELEASE,
        }
    ]
    assert LICENCE == "CC-BY-SA-3.0"


def test_the_chembl_ids_are_preserved_verbatim(graph):
    """The FTP `REQUIRED.ATTRIBUTION` asks that ChEMBL IDs be preserved and the
    release displayed. Both are contract, not courtesy."""
    result = one(
        graph,
        "MATCH (d:Drug {id: 'CHEMBL:CHEMBL1431'}) "
        "RETURN d.chembl_id AS chembl_id, d.source_licence AS licence, "
        "d.chembl_release AS release",
    )
    assert result == {"chembl_id": "CHEMBL1431", "licence": LICENCE, "release": RELEASE}


# --------------------------------------------------------------------------
# References — typed provenance, and the one that is a URL
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ref, expected",
    [
        ({"ref_type": "PubMed", "ref_id": "18336310"}, "PMID:18336310"),
        (
            {"ref_type": "DOI", "ref_id": "10.1056/NEJMra0907219"},
            "DOI:10.1056/NEJMra0907219",
        ),
        # The trap: two real rows put a PMC URL in a PubMed ref_id.
        (
            {
                "ref_type": "PubMed",
                "ref_id": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4804253/",
            },
            None,
        ),
        ({"ref_type": "DailyMed", "ref_id": "setid=abc"}, None),
        ({"ref_type": "PubMed", "ref_id": ""}, None),
    ],
)
def test_a_pubmed_ref_id_is_a_pmid_only_when_it_is_digits(ref, expected):
    assert publication_curie(ref) == expected


def test_the_url_shaped_pubmed_ref_reaches_the_ledger_and_no_publication(
    graph, csv_dir
):
    """Writing it through would mint `PMID:https://www.ncbi.nlm.nih.gov/...`,
    which no PMID lookup resolves and no reader would notice."""
    entries = ledger(csv_dir, "malformed_reference")
    assert len(entries) == 1
    assert entries[0]["record_id"] == "9"
    assert "PubMed" in entries[0]["detail"]
    result = one(
        graph,
        "MATCH ()-[r:HAS_MECHANISM]->() WHERE r.source_record_id = '9' "
        "RETURN r.publications AS pubs, r.evidence_level AS level",
    )
    assert result["pubs"] is None
    assert result["level"] == "in-vitro"


def test_publications_and_regulatory_refs_are_two_different_claims(graph):
    """A DailyMed label and a PubMed paper are not the same kind of evidence,
    and `evidence_level` reads them differently, so they are two properties."""
    result = one(
        graph,
        "MATCH ()-[r:HAS_MECHANISM]->() WHERE r.source_record_id = '5' "
        "RETURN r.publications AS pubs, r.regulatory_refs AS regs, "
        "r.evidence_level AS level",
    )
    assert result["pubs"] == ["PMID:222"]
    assert any("dailymed" in r for r in result["regs"])
    assert result["level"] == "interventional-rct"


def test_several_publications_are_a_list_property(graph):
    """`publications` is a native list, so a per-citation question is a query.

    It was a `|`-joined string until kglite 0.16.22 gave the blueprint a
    `"list"` column type; the prep writes a JSON array and the fragment
    declares it, so `UNWIND` and `IN` work without a re-parse."""
    result = one(
        graph,
        "MATCH ()-[r:HAS_MECHANISM]->() WHERE r.source_record_id = '12' "
        "RETURN r.publications AS pubs",
    )
    assert result["pubs"] == ["PMID:555", "DOI:10.1000/acarbose"]
    assert (
        one(
            graph,
            "MATCH ()-[r:HAS_MECHANISM]->() WHERE 'DOI:10.1000/acarbose' IN r.publications "
            "RETURN count(r) AS n",
        )["n"]
        == 1
    )


# --------------------------------------------------------------------------
# ProteinTarget and the taxon join — D8's partial answer
# --------------------------------------------------------------------------


def test_a_bacterial_target_reaches_the_taxon_it_names(graph):
    """This is the whole reason ChEMBL is in a microbiome graph: 865 real
    mechanism rows point at a non-human target, and `ProteinTarget.tax_id` is
    the only field in ChEMBL that touches a microbe."""
    result = rows(
        graph,
        "MATCH (d:Drug)-[:HAS_MECHANISM]->(p:ProteinTarget)-[:OF_ORGANISM]->(t:Taxon) "
        "RETURN DISTINCT d.title AS drug, p.title AS target, t.id AS tax_id, "
        "t.title AS organism ORDER BY drug, tax_id",
    )
    assert {r["tax_id"] for r in result} == {2, 562, 1282}
    assert ("VANCOMYCIN", 1282) in {(r["drug"], r["tax_id"]) for r in result}


def test_the_organism_edge_keeps_the_id_chembl_gave(graph):
    result = one(
        graph,
        "MATCH (:ProteinTarget {id: 'CHEMBL:CHEMBL1795148'})-[r:OF_ORGANISM]->(t:Taxon) "
        "RETURN t.id AS tax_id, r.reported_tax_id AS reported, "
        "r.resolution_status AS status, r.organism AS organism",
    )
    assert result == {
        "tax_id": 1282,
        "reported": 1282,
        "status": "exact",
        "organism": "Staphylococcus epidermidis",
    }


def test_a_taxid_the_taxonomy_does_not_carry_is_a_ledger_row_not_a_stub(graph, csv_dir):
    """The junction loader **vivifies** a stub node for a missing endpoint —
    silently, with one warning. Writing an unresolved taxid through would mint
    `Taxon` nodes whose title is their own id, and every taxon count in the
    graph would be wrong."""
    entries = ledger(csv_dir, "target_without_taxon")
    assert len(entries) == TARGETS_WITHOUT_TAXON
    assert one(graph, "MATCH ()-[r:OF_ORGANISM]->() RETURN count(r) AS n")["n"] == (
        OF_ORGANISM_EDGES
    )
    # A vivified Taxon carries its own id as its title and no rank.
    assert not rows(graph, "MATCH (t:Taxon) WHERE t.scientific_name IS NULL RETURN t")


def test_a_target_with_no_taxid_is_still_a_node_with_its_mechanisms(graph):
    """1.6% of real targets carry no `tax_id`. The target is real and its
    mechanisms are real; only the organism edge is missing."""
    result = one(
        graph,
        "MATCH (p:ProteinTarget {id: 'CHEMBL:CHEMBL612545'})<-[r:HAS_MECHANISM]-() "
        "RETURN count(r) AS mechanisms, p.tax_id AS tax_id, p.organism AS organism",
    )
    assert result["mechanisms"] == 2
    assert result["tax_id"] is None
    assert result["organism"] is None


def test_uniprot_accessions_come_from_the_components(graph):
    """Only 1,075 of 1,518 real targets are a single protein; the rest are
    families, complexes, or not proteins at all. A complex has several
    accessions and an organism-level target has none."""
    result = {
        r["id"]: r
        for r in rows(
            graph,
            "MATCH (p:ProteinTarget) RETURN p.id AS id, p.uniprot AS uniprot, "
            "p.n_components AS n, p.target_type AS type",
        )
    }
    assert result["CHEMBL:CHEMBL2095165"]["uniprot"] == ["O43451", "P14410"]
    assert result["CHEMBL:CHEMBL2095165"]["n"] == 2
    assert result["CHEMBL:CHEMBL3623"]["uniprot"] == ["P0AD68"]
    assert result["CHEMBL:CHEMBL2364701"]["uniprot"] is None
    assert result["CHEMBL:CHEMBL2364701"]["n"] == 0
    assert len(result) == PROTEIN_TARGETS


def test_the_target_taxa_reach_the_cited_taxa_table(csv_dir):
    """`cited_taxa.csv` is what tells the taxonomy build which taxa to keep. A
    target organism missing from it becomes a dangling junction endpoint — and
    the loader vivifies those rather than complaining."""
    cited = {r["tax_id"] for r in table(csv_dir, "cited_taxa.csv")}
    assert {"2", "562", "1282"} <= cited
    # 9606 did not resolve in this taxdump, so it is not claimed as cited.
    assert "9606" not in cited


# --------------------------------------------------------------------------
# Interventions — making gutMDisorder's DrugBank ids linkable
# --------------------------------------------------------------------------


def test_an_intervention_naming_a_drug_links_to_it(graph):
    """gutMDisorder curates `Metformin` as an intervention and ChEMBL knows
    METFORMIN as CHEMBL1431. Without the link the same drug is two unconnected
    nodes and D18's metformin confounding check cannot start from either."""
    result = rows(
        graph,
        "MATCH (i:Intervention)-[r:IS_DRUG]->(d:Drug) "
        "RETURN i.id AS intervention, d.id AS drug, r.match_method AS method, "
        "r.matched_name AS matched ORDER BY intervention",
    )
    assert len(result) == IS_DRUG_EDGES
    assert result[0] == {
        "intervention": "INTERVENTION:metformin",
        "drug": "CHEMBL:CHEMBL1431",
        "method": "pref_name",
        "matched": "METFORMIN",
    }
    assert result[1]["drug"] == "CHEMBL:CHEMBL262777"


def test_the_drugbank_route_does_not_exist_in_this_subset(graph, csv_dir, prep_output):
    """The brief's first choice was the DrugBank id both sides were expected to
    carry. The fetched molecule JSONL carries **no** cross-references at all —
    `only=` trimmed the response to 13 fields and DrugBank was not among them —
    so every link is a name match, and the ledger says so rather than leaving
    the reader to assume an id match happened."""
    assert "no DrugBank cross-reference" in prep_output
    methods = {
        r["method"]
        for r in rows(
            graph, "MATCH ()-[r:IS_DRUG]->() RETURN DISTINCT r.match_method AS method"
        )
    }
    assert methods == {"pref_name"}


def test_a_synonym_is_not_an_exact_match_and_is_ledgered(csv_dir):
    """gutMDisorder writes `Acetylsalicylic acid`; ChEMBL's `pref_name` is
    ASPIRIN. Accepting that as a match means accepting every other name-based
    merge in this repo's pitfall list, so it is a ledger row — with the drug it
    would have matched named, so the miss is actionable rather than mysterious."""
    entries = {r["subject"]: r for r in ledger(csv_dir, "intervention_unlinked")}
    assert len(entries) == UNLINKED_INTERVENTIONS
    assert "Acetylsalicylic acid" in entries
    assert "exact" in entries["Acetylsalicylic acid"]["reason"]


def test_a_multi_drug_label_is_ledgered_with_the_drugs_it_names(csv_dir):
    """gutMDisorder's `Intervention` cell is comma-multivalued
    (`Clarithromycin,Metronidazole` in the real workbook). Splitting it and
    linking both parts would invent an intervention the source never curated;
    the ledger names the parts so the loss is countable."""
    entries = {r["subject"]: r for r in ledger(csv_dir, "intervention_unlinked")}
    row = entries["Ampicillin,Vancomycin"]
    assert "CHEMBL:CHEMBL174" in row["detail"]
    assert "CHEMBL:CHEMBL262777" in row["detail"]
    assert "comma" in row["reason"]


def test_the_link_rate_is_reported(prep_output):
    """A build log that only reports successes cannot be audited: the number
    that matters here is how *few* of gutMDisorder's interventions ChEMBL
    knows by name."""
    assert f"{IS_DRUG_EDGES} of 6 intervention(s)" in prep_output


# --------------------------------------------------------------------------
# The ontology and the accounting
# --------------------------------------------------------------------------


def test_the_ledger_accounts_for_everything_that_became_no_edge(csv_dir):
    assert len(ledger(csv_dir)) == LEDGER_ROWS
    assert {r["kind"] for r in ledger(csv_dir)} == {
        "mechanism_without_target",
        "malformed_reference",
        "target_without_taxon",
        "intervention_unlinked",
    }


def test_the_mechanism_contract_is_complete_because_we_write_it(graph):
    """These seven are ours, not upstream's — the prep writes them on every
    edge unconditionally — so the rule is declared at `error` and a violation
    is a regression here rather than a gap in ChEMBL."""
    audit = {
        r["rule"]: r
        for r in rows(
            graph,
            "CALL ontology_audit() YIELD rule, severity, violations, total "
            "RETURN rule, severity, violations, total",
        )
    }
    rule = audit["HAS_MECHANISM.required_properties"]
    assert rule["severity"] == "error"
    assert rule["violations"] == 0
    assert rule["total"] == MECHANISM_EDGES


def test_the_audit_has_no_vacuous_rule_for_this_build(graph):
    """A rule with a zero denominator is a gate that cannot fail — which is how
    a new source's relationship silently audits nothing."""
    for r in rows(graph, "CALL ontology_audit() YIELD rule, total RETURN rule, total"):
        assert r["total"] > 0, f"{r['rule']} audits nothing"


def test_the_prep_reports_what_it_did_not_load(prep_output):
    for phrase in ("not loaded:", "mechanism rows", "evidence levels:"):
        assert phrase in prep_output

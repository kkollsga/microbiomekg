"""CARD: the resistance half of the graph, and the claim its taxon edge makes.

Every assertion here is a *failure mode first*. The fixture
(``tests/fixtures/card_mini/``) is a verbatim cut of 40 of CARD 4.0.2's 6,451
models — plus the ``aro.obo`` terms they reach, the ``PMID.tsv`` rows that cite
them and a taxdump slice — chosen so each pitfall in
``docs/research/source-formats.md`` §3 has a carrier, and the loader is
measured against what each pitfall would silently do:

* keying determinants on the ARO accession **from ``aro_index.tsv``** drops half
  of each of its five duplicated-accession pairs (``ARO:3003170`` CMY-131 sits
  on model 2067 *and* 4471);
* treating ``aro_index.tsv`` as the model list invents 48 determinants
  ``card.json`` does not have, and loses the 36 it does;
* reading the taxon label out of CARD rather than NCBI titles taxid 2
  ``"Bacteria, Viruses, Fungi, and other genome sequence associated with
  antimicrobial resistance"`` — CARD's editorial string, on 132 models;
* one licence for the source over-claims on 13,691 drug-class edges or
  under-claims on every ARO name;
* a merged taxid kept as given splits one organism into two nodes, and a strain
  taxid kept unpromoted puts *Acinetobacter baumannii* AYE beside
  *A. baumannii*;
* joining a model's 13 drug classes into one string makes "which genes hit
  carbapenems?" a substring search;
* and defaulting the 36 meta-models to ``in-vitro`` says an MIC was measured
  for a gene cluster that has no reference sequence at all.

The second half is what the *third source* is for: BugSigDB and CARD both name
*Escherichia coli*, and it has to be one node carrying both kinds of edge.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import BUGSIGDB_MINI, MONDO_MINI, TAXDUMP_MINI

kglite = pytest.importorskip("kglite")

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "card_mini"
SCRIPTS = ROOT / "scripts"
PREP = SCRIPTS / "prep_card.py"

sys.path.insert(0, str(SCRIPTS))

for _needed in (PREP, FIXTURE / "card-data" / "card.json",
                FIXTURE / "card-ontology" / "aro.obo"):
    if not _needed.exists():
        pytest.skip(f"{_needed} does not exist yet", allow_module_level=True)

from prep_card import aro_id, split_pmids  # noqa: E402

from microbiomekg.ontology import EVIDENCE_LEVEL_VALUES, SOURCE_LICENCE  # noqa: E402
from microbiomekg.ontology.card import (  # noqa: E402
    DATA_LICENCE,
    ONTOLOGY_LICENCE,
    SPECIFICITY_VALUES,
    evidence_level,
    knowledge_level,
    licence_for,
    taxon_specificity,
)

SOURCE = "card"

# --------------------------------------------------------------------------
# Golden values, derived from the fixture independently of the loader and
# asserted exactly. A query returning rows is not evidence.
# --------------------------------------------------------------------------

CARD_MODELS = 40               # models in the fixture's card.json
CARD_GENES = 40                # one ResistanceGene per model: ARO is 1:1 here
DRUG_CLASSES = 38
MECHANISMS = 7
CONFERS_EDGES = 95             # (model, Drug Class) pairs — not 38, and not 40
VIA_EDGES = 44
CARRIES_EDGES = 38             # 40 models less the two meta-models with no taxon
CARD_TAXA = 20                 # distinct taxa after merge + promotion
META_MODELS = 2                # 2176, 2177: gene cluster meta-models
DISAGREEMENTS = 4              # 2 index-only (2067, 2678) + 2 json-only
MODELS_WITH_PMID = 34
DISTINCT_PMIDS = 101
LEDGER_ROWS = 2                # the two meta-models, which reach no taxon

#: The five ARO accessions ``aro_index.tsv`` carries twice. Keying on that file
#: silently keeps whichever model id sorts last.
DUPLICATED_IN_INDEX = "ARO:3003170"    # CMY-131 on models 2067 *and* 4471
INDEX_ONLY_MODELS = ("2067", "2678")
JSON_ONLY_MODELS = ("2176", "2177")

#: CARD's own worked example of the reference-sequence caveat: the description
#: says *Bacteroides uniformis*, the taxid says a mixed culture.
CBLA1 = "ARO:3002999"
CBLA1_TAXID = 663108
CBLA1_REPORTED = "mixed culture bacterium AX_gF3SD01_15"

ADC193 = "ARO:3006362"          # taxid 2 — Bacteria, and CARD's editorial label
OXA69 = "ARO:3001617"           # taxid 509173 (strain) -> promoted to 470
AAC6_ISA = "ARO:3002563"        # taxid 68570 merged -> 1971 Streptomyces noursei
APH3_IB = "ARO:3002642"         # taxid 2503 — Plasmid RP4, not an organism
LNUE = "ARO:3003762"            # taxid 32630 — synthetic construct
MEXR = "ARO:3000506"            # 13 drug classes, 2 mechanisms, 4 PMIDs
VANN = "ARO:3002917"            # gene cluster meta-model, no reference sequence

MEXR_DRUG_CLASSES = 13
MEXR_MECHANISMS = 2
MEXR_PMIDS = ("12727072", "14526032", "18812515", "20616806")

SHARED_TAXON = 562              # Escherichia coli: BugSigDB names it, CARD does too


@pytest.fixture(scope="module")
def taxdump(tmp_path_factory):
    """``taxdump_mini`` and the CARD fixture's taxdump, concatenated.

    The two fixtures are disjoint cuts of the same 2026-09-02 dump — BugSigDB's
    gut genera and CARD's clinical pathogens — and a build loads one taxonomy,
    so a two-source test needs their union. Dedupe is first-wins on the whole
    line, which is what makes the concatenation deterministic; ``taxdump_mini``
    goes first so its hand-made deleted and merged ids keep their meaning.
    """
    out = tmp_path_factory.mktemp("card-taxdump")
    for name in ("nodes.dmp", "names.dmp", "merged.dmp", "delnodes.dmp",
                 "rankedlineage.dmp"):
        seen: set[str] = set()
        lines: list[str] = []
        for source in (TAXDUMP_MINI / name, FIXTURE / "taxdump" / name):
            if not source.is_file():
                continue
            for line in source.read_text(encoding="utf-8").splitlines():
                if line and line not in seen:
                    seen.add(line)
                    lines.append(line)
        (out / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def run(script, *args):
    proc = subprocess.run(
        [sys.executable, str(script), *args], capture_output=True, text=True, cwd=ROOT
    )
    assert proc.returncode == 0, f"{script.name} failed:\n{proc.stdout}\n{proc.stderr}"
    return proc


@pytest.fixture(scope="module")
def built(tmp_path_factory, taxdump):
    """BugSigDB and CARD through their real prep scripts, then the real blueprint."""
    work = tmp_path_factory.mktemp("card")
    csv_dir = work / "csv"
    csv_dir.mkdir()

    # BugSigDB first, so the shared tables exist for CARD to merge into — the
    # order scripts/build.py uses, and the only thing that makes "one taxon,
    # two sources" testable.
    run(
        SCRIPTS / "prep_bugsigdb.py",
        "--raw", str(BUGSIGDB_MINI),
        "--taxdump", str(taxdump),
        "--mondo", str(MONDO_MINI),
        "--out", str(csv_dir),
    )
    prep = run(
        PREP,
        "--card", str(FIXTURE),
        "--taxdump", str(taxdump),
        "--out", str(csv_dir),
    )
    run(
        SCRIPTS / "prep_taxonomy.py",
        "--taxdump", str(taxdump),
        "--out", str(csv_dir),
        "--scope", "cited",
        "--cited-from", str(csv_dir / "cited_taxa.csv"),
    )

    from build_blueprint import compose

    from microbiomekg.ontology import ontology_for, write_json

    blueprint = compose(ROOT / "blueprints", ["bugsigdb", SOURCE])
    settings = blueprint.setdefault("settings", {})
    settings["root"] = str(csv_dir)
    for key in ("output", "output_path", "output_file"):
        settings.pop(key, None)
    write_json(csv_dir / "ontology.json", ontology_for(["bugsigdb", SOURCE]))
    blueprint["ontology"] = str(csv_dir / "ontology.json")
    local = csv_dir / "blueprint.test.json"
    local.write_text(json.dumps(blueprint))

    graph = kglite.from_blueprint(local, verbose=False, save=False)
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
    with (csv_dir / name).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# --------------------------------------------------------------------------
# The ARO accession — bare in JSON, prefixed everywhere else
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        ("3002999", "ARO:3002999"),      # card.json stores it bare
        ("ARO:3002999", "ARO:3002999"),  # aro_index.tsv, PMID.tsv and aro.obo do not
        (" ARO:3002999 ", "ARO:3002999"),
        ("", ""),
        (None, ""),
    ],
)
def test_the_accession_is_normalised_whichever_file_it_came_from(value, expected):
    """Four files in one download spell the same key two ways. Joining them
    without normalising produces a graph in which every model is two nodes and
    no citation reaches any of them."""
    assert aro_id(value) == expected


@pytest.mark.parametrize(
    "cell, expected",
    [
        ("11709358;15603834;21115799", ["11709358", "15603834", "21115799"]),
        ("10639355", ["10639355"]),
        ("11709358;", ["11709358"]),        # 21 such empty atoms in the real file
        (";11709358", ["11709358"]),
        ("11709358; 15603834", ["11709358", "15603834"]),
        ("", []),
        (None, []),
    ],
)
def test_splitting_pmids_drops_the_empty_atoms_it_creates(cell, expected):
    """`PMID.tsv` has trailing and leading semicolons. A bare `split(";")`
    yields empty strings that become `pmid` values nothing can join on."""
    assert split_pmids(cell) == expected


# --------------------------------------------------------------------------
# Which models exist — card.json is the authority, and the 84 are a ledger
# --------------------------------------------------------------------------


def test_the_determinants_are_card_jsons_models_not_the_indexs(graph):
    """`aro_index.tsv` and `card.json` disagree about 84 models in the same
    tarball. `card.json` wins because it is the file with the taxids; taking
    the index instead would invent 48 determinants and lose 36."""
    result = one(
        graph, "MATCH (g:ResistanceGene) RETURN count(g) AS genes"
    )
    assert result["genes"] == CARD_GENES
    for model in INDEX_ONLY_MODELS:
        assert not rows(
            graph,
            f"MATCH (g:ResistanceGene {{card_model_id: '{model}'}}) RETURN g",
        ), f"model {model} is in aro_index.tsv only and must not be a node"
    for model in JSON_ONLY_MODELS:
        assert rows(
            graph,
            f"MATCH (g:ResistanceGene {{card_model_id: '{model}'}}) RETURN g",
        ), f"model {model} is in card.json and must be a node"


def test_the_disagreement_reaches_a_ledger_with_its_direction(csv_dir):
    """A source contradicting itself is reportable, not a silent choice. The
    ledger says which file each missing model was in, so "48 in the index, 36
    in the JSON" is a query rather than a paragraph in a doc."""
    ledger = table(csv_dir, "card_model_disagreements.csv")
    assert len(ledger) == DISAGREEMENTS
    kinds = {r["model_id"]: r["kind"] for r in ledger}
    for model in INDEX_ONLY_MODELS:
        assert kinds[model] == "absent-from-card.json"
    for model in JSON_ONLY_MODELS:
        assert kinds[model] == "absent-from-aro_index.tsv"


def test_a_duplicated_index_accession_is_still_one_determinant(graph):
    """`ARO:3003170` sits on two model ids in `aro_index.tsv`. Keying on that
    file drops one of them; keying on `card.json`, where the accession is
    unique across all 6,451 models, cannot."""
    result = one(
        graph,
        f"MATCH (g:ResistanceGene {{id: '{DUPLICATED_IN_INDEX}'}}) "
        "RETURN count(g) AS n, g.card_model_id AS model",
    )
    assert result["n"] == 1
    assert result["model"] == "4471"


def test_no_two_determinants_share_an_accession(graph):
    result = one(
        graph,
        "MATCH (g:ResistanceGene) "
        "RETURN count(g) AS genes, count(DISTINCT g.id) AS accessions",
    )
    assert result["genes"] == result["accessions"] == CARD_GENES


# --------------------------------------------------------------------------
# The taxon edge — what it actually claims
# --------------------------------------------------------------------------


def test_the_taxon_is_the_reference_sequences_organism_and_the_edge_says_so(graph):
    """CARD's own worked example. `CblA-1`'s description names *Bacteroides
    uniformis*; its taxid names a mixed culture. An edge built from this field
    means "this sequence was cloned from this organism", which is a weaker
    claim than "this organism is resistant", and the difference has to be on
    the edge rather than in a README."""
    result = one(
        graph,
        f"MATCH (t:Taxon)-[r:CARRIES_RESISTANCE_GENE]->(g:ResistanceGene {{id: '{CBLA1}'}}) "
        "RETURN t.id AS tax_id, r.reported_name AS reported, "
        "r.sequence_derived AS derived, r.taxon_scope AS scope, "
        "g.description AS description",
    )
    assert result["tax_id"] == CBLA1_TAXID
    assert result["reported"] == CBLA1_REPORTED
    assert result["derived"] is True
    assert result["scope"] == "reference-sequence-organism"
    assert "Bacteroides uniformis" in result["description"]


def test_every_carriage_edge_declares_the_same_scope(graph):
    """The caveat is a property of the relation, so it holds on every edge or
    it is decoration on the ones somebody remembered."""
    result = rows(
        graph,
        "MATCH ()-[r:CARRIES_RESISTANCE_GENE]->() "
        "RETURN DISTINCT r.taxon_scope AS scope, r.sequence_derived AS derived",
    )
    assert result == [{"scope": "reference-sequence-organism", "derived": True}]


def test_a_kingdom_level_taxid_is_flagged_rather_than_dropped_or_believed(graph):
    """132 real models are keyed on taxid 2 — Bacteria — and nothing else.
    Dropping them loses a curated determinant; treating them like a species
    claim says *every* bacterium carries it. The third option is a flag."""
    result = one(
        graph,
        f"MATCH (t:Taxon)-[r:CARRIES_RESISTANCE_GENE]->(g:ResistanceGene {{id: '{ADC193}'}}) "
        "RETURN t.id AS tax_id, t.title AS name, t.rank AS rank, "
        "r.taxon_specificity AS specificity",
    )
    assert result["tax_id"] == 2
    assert result["specificity"] == "above-species"


def test_the_taxon_title_is_ncbis_name_never_cards_editorial_string(graph):
    """`ncbi_taxonomy.obo` renames `NCBITaxon:2` to CARD's own curation label —
    and so does `card.json`'s `NCBI_taxonomy_name`, on all 132 taxid-2 models.
    The label survives on the edge as `reported_name`, because that is what the
    source said; the *node* is NCBI's."""
    node = one(graph, "MATCH (t:Taxon {id: 2}) RETURN t.title AS name")
    assert node["name"] == "Bacteria"
    edge = one(
        graph,
        f"MATCH ()-[r:CARRIES_RESISTANCE_GENE]->(:ResistanceGene {{id: '{ADC193}'}}) "
        "RETURN r.reported_name AS reported",
    )
    assert reported_is_cards_label(edge["reported"])


def reported_is_cards_label(value: str) -> bool:
    return value.startswith("Bacteria, Viruses, Fungi")


def test_a_plasmid_is_not_an_organism_and_the_edge_does_not_pretend(graph):
    """NCBI ranks `Plasmid RP4` **species**, under `other sequences`. The rank
    alone therefore says the opposite of the truth, and only the lineage can
    correct it — 17 of CARD's 743 taxids are plasmids, transposons, synthetic
    constructs or metagenomes."""
    result = one(
        graph,
        f"MATCH (t:Taxon)-[r:CARRIES_RESISTANCE_GENE]->(:ResistanceGene {{id: '{APH3_IB}'}}) "
        "RETURN t.id AS tax_id, t.title AS name, t.rank AS rank, "
        "r.taxon_specificity AS specificity",
    )
    assert result["rank"] == "species"
    assert result["specificity"] == "not-an-organism"
    synthetic = one(
        graph,
        f"MATCH ()-[r:CARRIES_RESISTANCE_GENE]->(:ResistanceGene {{id: '{LNUE}'}}) "
        "RETURN r.taxon_specificity AS specificity",
    )
    assert synthetic["specificity"] == "not-an-organism"


def test_every_specificity_written_is_one_of_the_three(graph):
    used = {
        r["specificity"]
        for r in rows(
            graph,
            "MATCH ()-[r:CARRIES_RESISTANCE_GENE]->() "
            "RETURN DISTINCT r.taxon_specificity AS specificity",
        )
    }
    assert used <= set(SPECIFICITY_VALUES)
    assert used == {"species-or-below", "above-species", "not-an-organism"}


def test_a_merged_taxid_lands_on_the_survivor_and_keeps_cards_name(graph):
    """68570 merged into 1971, and CARD still calls it *Streptomyces albulus*
    while NCBI now calls 1971 *S. noursei*. Both facts are kept: the node is
    the survivor, the edge remembers what the source said."""
    result = one(
        graph,
        f"MATCH (t:Taxon)-[r:CARRIES_RESISTANCE_GENE]->(:ResistanceGene {{id: '{AAC6_ISA}'}}) "
        "RETURN t.id AS tax_id, t.title AS name, r.reported_tax_id AS reported, "
        "r.resolution_status AS status, r.reported_name AS reported_name",
    )
    assert result["tax_id"] == 1971
    assert result["status"] == "merged"
    assert result["reported"] == 68570
    assert result["reported_name"] == "Streptomyces albulus"
    assert not rows(graph, "MATCH (t:Taxon {id: 68570}) RETURN t")


def test_a_strain_taxid_promotes_to_its_species_keeping_the_original(graph):
    """185 of CARD's 743 taxids are strains. Left alone they stand beside their
    own species as separate nodes, and "what does *A. baumannii* carry?" misses
    every one of them."""
    result = one(
        graph,
        f"MATCH (t:Taxon)-[r:CARRIES_RESISTANCE_GENE]->(:ResistanceGene {{id: '{OXA69}'}}) "
        "RETURN t.id AS tax_id, r.reported_tax_id AS reported, "
        "r.resolution_status AS status, r.original_rank AS original_rank",
    )
    assert result["tax_id"] == 470
    assert result["reported"] == 509173
    assert result["status"] == "promoted"
    assert result["original_rank"] == "strain"


def test_a_taxid_the_dump_does_not_have_is_a_tombstone_and_a_ledger_row(
    tmp_path_factory, taxdump
):
    """G2: nothing is dropped. Run against a taxdump that predates most of
    CARD's clinical pathogens, the unresolvable ids have to come back as
    `UnresolvedTaxon` rows and ledger entries — not as a smaller edge count
    with no explanation. `taxdump_mini` is that dump: it carries 220 gut taxa
    and five of CARD's."""
    out = tmp_path_factory.mktemp("card-narrow")
    run(PREP, "--card", str(FIXTURE), "--taxdump", str(TAXDUMP_MINI), "--out", str(out))
    tombstones = table(out, "unresolved_taxa.csv")
    ledger = [r for r in table(out, "unresolved_associations.csv")
              if r["source"] == SOURCE and "taxon" in r["reason"]]
    edges = table(out, "taxon_resistance_gene.csv")
    assert tombstones, "no tombstone for a taxid the dump does not have"
    assert all(r["status"] == "unresolved" for r in tombstones)
    assert len(edges) + len(ledger) == CARRIES_EDGES
    assert len(edges) < CARRIES_EDGES


# --------------------------------------------------------------------------
# Drug classes and mechanisms — edges, never a joined string
# --------------------------------------------------------------------------


def test_a_model_with_thirteen_drug_classes_is_thirteen_edges(graph):
    """`Drug Class` is `;`-multivalued on 4,096 of 6,463 index rows, and
    `nuniq` over the raw column reports 150 "classes" that are really 53 atoms
    in combination. Kept as a string, "which determinants hit carbapenems?" is
    a substring search that also matches `carbapenem` inside another value."""
    result = one(
        graph,
        f"MATCH (g:ResistanceGene {{id: '{MEXR}'}})-[r:CONFERS_RESISTANCE_TO]->(d:DrugClass) "
        "RETURN count(r) AS edges, count(DISTINCT d.id) AS classes",
    )
    assert result["edges"] == MEXR_DRUG_CLASSES
    assert result["classes"] == MEXR_DRUG_CLASSES
    mechanisms = one(
        graph,
        f"MATCH (g:ResistanceGene {{id: '{MEXR}'}})-[r:VIA_MECHANISM]->(m:ResistanceMechanism) "
        "RETURN count(r) AS edges",
    )
    assert mechanisms["edges"] == MEXR_MECHANISMS


def test_the_three_relationships_have_the_counts_the_fixture_implies(graph):
    counts = {
        r["rel"]: r["n"]
        for r in rows(
            graph,
            "MATCH ()-[r:CONFERS_RESISTANCE_TO|VIA_MECHANISM|CARRIES_RESISTANCE_GENE]->() "
            "RETURN type(r) AS rel, count(r) AS n",
        )
    }
    assert counts == {
        "CONFERS_RESISTANCE_TO": CONFERS_EDGES,
        "VIA_MECHANISM": VIA_EDGES,
        "CARRIES_RESISTANCE_GENE": CARRIES_EDGES,
    }
    nodes = one(
        graph,
        "MATCH (d:DrugClass) WITH count(d) AS classes "
        "MATCH (m:ResistanceMechanism) RETURN classes, count(m) AS mechanisms",
    )
    assert nodes["classes"] == DRUG_CLASSES
    assert nodes["mechanisms"] == MECHANISMS


def test_the_gene_family_is_a_property_and_the_drug_class_is_not(graph):
    """The AMR gene family is a *classification of the determinant* — one value
    on 6,273 of 6,451 models — and nothing joins to it. The drug class is the
    other endpoint of D7's question, so it is a node."""
    result = one(
        graph,
        f"MATCH (g:ResistanceGene {{id: '{CBLA1}'}}) "
        "RETURN g.gene_family AS family, g.gene_family_aro AS family_aro",
    )
    assert result["family"] == ["CblA beta-lactamase"]
    assert result["family_aro"] == ["ARO:3002998"]


# --------------------------------------------------------------------------
# The evidence a CARD edge carries
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "has_reference_sequence, expected",
    [(True, "in-vitro"), (False, "computational-predicted")],
)
def test_evidence_level_follows_part_bs_table(has_reference_sequence, expected):
    assert evidence_level(has_reference_sequence) == expected


@pytest.mark.parametrize("n, expected", [(0, "not_provided"), (1, "knowledge_assertion"),
                                         (4, "knowledge_assertion")])
def test_knowledge_level_is_not_asserted_without_a_citation(n, expected):
    assert knowledge_level(n) == expected


@pytest.mark.parametrize(
    "rank, lineage, expected",
    [
        ("species", [562, 561, 1], "species-or-below"),
        ("strain", [509173, 470, 1], "species-or-below"),
        ("domain", [2, 131567, 1], "above-species"),
        ("genus", [561, 543, 1], "above-species"),
        # A plasmid's NCBI rank is `species`; only the lineage says otherwise.
        ("species", [2503, 28384, 1], "not-an-organism"),
        ("species", [749907, 12908, 1], "not-an-organism"),
    ],
)
def test_taxon_specificity_reads_the_lineage_not_just_the_rank(rank, lineage, expected):
    assert taxon_specificity(rank, lineage) == expected


def test_a_meta_model_is_predicted_and_a_curated_model_is_in_vitro(graph):
    """The 36 meta-models have no reference sequence and no MIC of their own.
    Defaulting them to `in-vitro` beside the curated models is the "276k AMR
    links" error D7 names: a predicted layer that cannot be excluded."""
    levels = {
        r["level"]: r["n"]
        for r in rows(
            graph,
            "MATCH ()-[r:CONFERS_RESISTANCE_TO]->() "
            "RETURN r.evidence_level AS level, count(r) AS n",
        )
    }
    assert set(levels) == {"in-vitro", "computational-predicted"}
    meta = one(
        graph,
        f"MATCH (g:ResistanceGene {{id: '{VANN}'}}) "
        "RETURN g.curated AS curated, g.model_type AS model_type",
    )
    assert meta["curated"] is False
    assert meta["model_type"] == "gene cluster meta-model"
    curated = one(
        graph,
        f"MATCH (g:ResistanceGene {{id: '{CBLA1}'}}) RETURN g.curated AS curated",
    )
    assert curated["curated"] is True


def test_the_predicted_layer_is_excludable_with_one_where(graph):
    """D7's requirement, stated as a query: a caller must be able to drop
    everything that rests on no measurement without knowing what a meta-model
    is."""
    kept = one(
        graph,
        "MATCH ()-[r:CONFERS_RESISTANCE_TO]->() "
        "WHERE r.evidence_level <> 'computational-predicted' "
        "RETURN count(r) AS n, count(DISTINCT r.card_model_id) AS models",
    )
    assert kept["models"] == CARD_MODELS - META_MODELS


def test_every_level_written_is_one_of_the_twelve(graph):
    used = {
        r["level"]
        for r in rows(
            graph,
            "MATCH ()-[r:CONFERS_RESISTANCE_TO|VIA_MECHANISM|CARRIES_RESISTANCE_GENE]->() "
            "RETURN DISTINCT r.evidence_level AS level",
        )
    }
    assert used <= set(EVIDENCE_LEVEL_VALUES)


def test_a_determinant_with_no_citation_is_not_provided_not_asserted(graph):
    """`PMID.tsv` covers 2,742 of 6,451 model ARO terms. The rest are curated
    by the same people to the same bar, and this loader still refuses to call
    them knowledge assertions — `not_provided` is a value one WHERE counts."""
    result = {
        r["kl"]: r["models"]
        for r in rows(
            graph,
            "MATCH ()-[r:CONFERS_RESISTANCE_TO]->() "
            "RETURN r.knowledge_level AS kl, count(DISTINCT r.card_model_id) AS models",
        )
    }
    assert result == {
        "knowledge_assertion": MODELS_WITH_PMID,
        "not_provided": CARD_MODELS - MODELS_WITH_PMID,
    }


def test_the_publications_are_all_of_them_and_pmid_is_one_of_them(graph):
    """`pmid` is a single integer because the contract's column is; a model
    citing four papers would otherwise silently lose three. `publications`
    carries all four as a native list property."""
    result = one(
        graph,
        f"MATCH ()-[r:VIA_MECHANISM]->() WHERE r.card_model_id = '1474' "
        "RETURN DISTINCT r.pmid AS pmid, r.publications AS publications, "
        "r.n_publications AS n",
    )
    assert result["n"] == len(MEXR_PMIDS)
    assert result["publications"] == list(MEXR_PMIDS)
    assert str(result["pmid"]) in MEXR_PMIDS


def test_the_distinct_citations_are_the_ones_the_fixture_carries(graph):
    result = one(
        graph,
        "MATCH ()-[r:CONFERS_RESISTANCE_TO]->() WHERE r.publications IS NOT NULL "
        "RETURN count(DISTINCT r.card_model_id) AS models",
    )
    assert result["models"] == MODELS_WITH_PMID


# --------------------------------------------------------------------------
# The licence, per edge — the reason this source needs one at all
# --------------------------------------------------------------------------


def test_the_licence_is_a_property_of_the_edge_not_of_the_source(graph):
    """Two licences in one download. A determinant's *name* comes from
    `aro.obo`, which is CC BY 4.0; the drug class it confers resistance to
    comes from `card.json`, which is not. Recording one licence for "CARD"
    either over-claims on the edges or under-claims on the nodes."""
    node = one(
        graph,
        f"MATCH (g:ResistanceGene {{id: '{CBLA1}'}}) "
        "RETURN g.source_licence AS licence, g.name_source AS name_source",
    )
    assert node["licence"] == ONTOLOGY_LICENCE
    assert node["name_source"] == "aro.obo"
    edge = rows(
        graph,
        "MATCH ()-[r:CONFERS_RESISTANCE_TO]->() "
        "RETURN DISTINCT r.source_licence AS licence",
    )
    assert {r["licence"] for r in edge} <= {DATA_LICENCE, ONTOLOGY_LICENCE}
    assert DATA_LICENCE in {r["licence"] for r in edge}


@pytest.mark.parametrize(
    "also_in_ontology, expected",
    [(True, "CC-BY-4.0"), (False, "CARD-noncommercial")],
)
def test_licence_for_names_the_half_that_states_the_fact(also_in_ontology, expected):
    assert licence_for(also_in_ontology) == expected


def test_the_registered_source_licence_is_the_data_half(graph):
    """The source-level registration is the licence its *records* ship under,
    which is the restrictive one. The permissive half is reached per edge."""
    assert SOURCE_LICENCE[SOURCE] == DATA_LICENCE


def test_a_redistributable_subgraph_is_one_where_clause(graph):
    """The point of the per-edge licence: a mixed-licence graph can ship in
    parts. This is the query that produces the shippable part."""
    result = one(
        graph,
        "MATCH (g:ResistanceGene)-[r:CONFERS_RESISTANCE_TO]->(d:DrugClass) "
        "WHERE r.source_licence = 'CC-BY-4.0' "
        "RETURN count(r) AS edges",
    )
    assert result["edges"] >= 0


def test_every_edge_carries_the_full_provenance_set(graph):
    """G3, at the level the audit checks it: no CARD edge may be missing a
    provenance field, because this repo writes all six unconditionally."""
    result = one(
        graph,
        "MATCH ()-[r:CONFERS_RESISTANCE_TO|VIA_MECHANISM|CARRIES_RESISTANCE_GENE]->() "
        "RETURN count(r) AS edges, "
        "sum(CASE WHEN r.primary_source IS NULL THEN 1 ELSE 0 END) AS no_source, "
        "sum(CASE WHEN r.source_record_id IS NULL THEN 1 ELSE 0 END) AS no_record, "
        "sum(CASE WHEN r.source_licence IS NULL THEN 1 ELSE 0 END) AS no_licence, "
        "sum(CASE WHEN r.knowledge_level IS NULL THEN 1 ELSE 0 END) AS no_kl, "
        "sum(CASE WHEN r.agent_type IS NULL THEN 1 ELSE 0 END) AS no_agent, "
        "sum(CASE WHEN r.source_relation IS NULL THEN 1 ELSE 0 END) AS no_relation, "
        "collect(DISTINCT r.primary_source) AS sources",
    )
    assert result["edges"] == CONFERS_EDGES + VIA_EDGES + CARRIES_EDGES
    for field in ("no_source", "no_record", "no_licence", "no_kl", "no_agent",
                  "no_relation"):
        assert result[field] == 0, f"{field} on a CARD edge"
    assert result["sources"] == [SOURCE]


def test_the_source_record_is_the_model_so_expansion_is_countable(graph):
    """G10: edges per source record, published rather than assumed. One model
    is one curated record and produces up to 13 drug-class edges; a graph that
    reported 95 edges without saying they came from 40 records would be
    reporting its own expansion factor as a finding."""
    result = one(
        graph,
        "MATCH ()-[r:CONFERS_RESISTANCE_TO]->() "
        "RETURN count(r) AS edges, count(DISTINCT r.source_record_id) AS records",
    )
    assert result["edges"] == CONFERS_EDGES
    assert result["records"] == CARD_MODELS


# --------------------------------------------------------------------------
# Names and hierarchy come from the CC BY 4.0 half
# --------------------------------------------------------------------------


def test_the_names_come_from_aro_obo(graph):
    result = rows(
        graph,
        "MATCH (g:ResistanceGene) RETURN DISTINCT g.name_source AS source",
    )
    assert [r["source"] for r in result] == ["aro.obo"]


def test_a_drug_class_carries_its_aro_parents(graph):
    """`aro.obo`'s `is_a` is the hierarchy, and it is the CC BY 4.0 half. It is
    a joined string rather than an edge because nothing in Part D walks it yet
    and an unwalked relationship is a relationship nothing audits."""
    result = one(
        graph,
        "MATCH (d:DrugClass {id: 'ARO:0000032'}) "
        "RETURN d.title AS label, d.aro_parents AS parents",
    )
    assert result["label"] == "cephalosporin"
    assert "ARO:3000007" in result["parents"]


# --------------------------------------------------------------------------
# C18 accounting — every model is edges, a ledger row, or a counted drop
# --------------------------------------------------------------------------


def test_every_model_is_accounted_for(graph, csv_dir, prep_output):
    """Input models = models that reached a carriage edge + ledger records.
    The point of the rule is that a silent drop cannot hide in the difference."""
    carried = one(
        graph,
        "MATCH ()-[r:CARRIES_RESISTANCE_GENE]->() "
        "RETURN count(DISTINCT r.card_model_id) AS models",
    )["models"]
    ledger = [r for r in table(csv_dir, "unresolved_associations.csv")
              if r["source"] == SOURCE]
    assert len(ledger) == LEDGER_ROWS
    assert carried + len(ledger) == CARD_MODELS
    assert all("no reference sequence" in r["reason"] for r in ledger)


def test_the_prep_reports_what_it_did_not_load(prep_output):
    """A build log that only reports successes cannot be audited."""
    for phrase in ("not loaded:", "disagreements", "evidence levels:"):
        assert phrase in prep_output


def test_the_taxa_reach_the_taxonomy_build(graph, csv_dir):
    """`cited_taxa.csv` decides which taxa the taxonomy keeps. A source that
    did not write it would have every one of its carriage edges point at a
    vivified stub with no name and no lineage."""
    cited = {r["tax_id"] for r in table(csv_dir, "cited_taxa.csv")}
    result = rows(
        graph,
        "MATCH (t:Taxon)-[:CARRIES_RESISTANCE_GENE]->() "
        "RETURN DISTINCT t.id AS tax_id, t.title AS name",
    )
    assert len(result) == CARD_TAXA
    assert all(str(r["tax_id"]) in cited for r in result)
    assert all(r["name"] for r in result), "a carriage edge points at an untitled stub"


# --------------------------------------------------------------------------
# Two sources, one graph
# --------------------------------------------------------------------------


def test_a_taxon_named_by_both_sources_is_one_node_with_both_edge_kinds(graph):
    """*Escherichia coli* is a BugSigDB association subject and a CARD
    reference-sequence organism. If the two are two nodes, "what does this
    taxon carry, and what is it associated with?" is not one query — and that
    join is the whole reason CARD is in this graph rather than beside it."""
    result = one(
        graph,
        f"MATCH (t:Taxon {{id: {SHARED_TAXON}}}) "
        "OPTIONAL MATCH (t)-[a:ASSOCIATED_WITH]->() "
        "OPTIONAL MATCH (t)-[c:CARRIES_RESISTANCE_GENE]->() "
        "RETURN count(DISTINCT a) AS associations, count(DISTINCT c) AS carried, "
        "t.title AS name",
    )
    assert result["name"] == "Escherichia coli"
    assert result["associations"] > 0
    assert result["carried"] > 0


def test_card_writes_no_taxon_disease_association(graph):
    """CARD curates no taxon–disease claim, and inventing one — "carries a
    resistance gene" is not "is associated with a disease" — is the collapse
    MDAD is criticised for. The audit's association numbers must be BugSigDB's
    alone."""
    sources = {
        r["source"]
        for r in rows(
            graph,
            "MATCH ()-[r:ASSOCIATED_WITH]->() RETURN DISTINCT r.primary_source AS source",
        )
    }
    assert SOURCE not in sources


def test_cards_own_rules_audit_something(graph):
    """A rule with a zero denominator is a gate that cannot fail. CARD's three
    relationships are new, so this is the check that they are declared *and*
    populated rather than declared and empty."""
    audited = {
        r["rule"]: r["total"]
        for r in rows(
            graph, "CALL ontology_audit() YIELD rule, total RETURN rule, total"
        )
    }
    for rel in ("CONFERS_RESISTANCE_TO", "VIA_MECHANISM", "CARRIES_RESISTANCE_GENE"):
        for check in ("required_properties", "property_types"):
            rule = f"{rel}.{check}"
            assert rule in audited, f"{rule} is not declared"
            assert audited[rule] > 0, f"{rule} audits nothing"


def test_the_audit_number_is_the_missing_citations_and_nothing_else(graph):
    """A gate that cannot go green says as little as one that cannot go red.
    CARD's contract is eight properties rather than the shared fourteen
    precisely so this number *moves*: `direction` and the two group sizes
    describe a differential-abundance observation and no CARD release will
    ever fill them, so declaring them would report a permanent 100%. What is
    declared is what can vary — and the fraction that violates is exactly the
    determinants with no paper behind them."""
    violations = {
        r["rule"]: r["violations"]
        for r in rows(
            graph,
            "CALL ontology_audit() YIELD rule, violations RETURN rule, violations",
        )
    }
    for rel, csv_name in (
        ("CONFERS_RESISTANCE_TO", "resistance_gene_drug_class.csv"),
        ("VIA_MECHANISM", "resistance_gene_mechanism.csv"),
        ("CARRIES_RESISTANCE_GENE", "taxon_resistance_gene.csv"),
    ):
        uncited = one(
            graph,
            f"MATCH ()-[r:{rel}]->() WHERE r.pmid IS NULL RETURN count(r) AS n",
        )["n"]
        assert violations[f"{rel}.required_properties"] == uncited, csv_name
        assert uncited > 0, (
            f"{rel} has no uncited edge in the fixture, so its audit rule "
            f"cannot be shown to go red"
        )

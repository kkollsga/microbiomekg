"""KEGG: a licence gate that has to actually gate, and four ids that lie.

KEGG is not a public database — a graph carrying its content cannot be
published — so the whole slice is off by default and every row it writes says
so. The tests here are in two halves.

The first half is the **gate**, and it is tested the way a gate has to be: by
building the same fixture twice, once without the flag and once with it, and
diffing what changed. A flag whose only evidence is that it was passed is not a
gate. The build without it must contain no ``KEGG:`` node, no row carrying
``source_licence = 'KEGG-restricted'``, and — the part that is easy to get
wrong — **the same metabolites** as the build with it, because a metabolite
selected *because* KEGG links it would be a KEGG-derived row sitting in a graph
built without the flag.

The second half is the ids. ``conv/compound/pubchem`` returns PubChem
*Substance* ids where HMDB's ``pubchem_compound_id`` is a *Compound* id;
``list_pathway_hsa.tsv`` is the same maps under a second key;
``link_compound_pathway.tsv`` prefixes both columns; and HMDB carries one
lowercase ``kegg_id``, eight ``D`` (drug) ids and two ``G`` (glycan) ids that
cannot join a compound list at all. Each of those, loaded naively, produces a
graph that looks right.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import TAXDUMP_MINI

kglite = pytest.importorskip("kglite")

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
HMDB_MINI = FIXTURES / "hmdb_mini" / "hmdb_metabolites.xml"
REACTOME_MINI = FIXTURES / "reactome_mini"
KEGG_MINI = FIXTURES / "kegg_mini"
SCRIPTS = ROOT / "scripts"
PREPS_DIR = ROOT / "microbiomekg" / "preps"
PREP = PREPS_DIR / "prep_kegg.py"


for _needed in (PREP, KEGG_MINI / "list_pathway.tsv", HMDB_MINI):
    if not _needed.exists():
        pytest.skip(f"{_needed} does not exist yet", allow_module_level=True)

from microbiomekg.ontology import kegg as kg  # noqa: E402
from microbiomekg.ontology import SOURCE_LICENCE  # noqa: E402

SOURCE = "kegg"

#: Exit code for "not on this machine, or not asked for" — see scripts/build.py.
MISSING_INPUT = 3

KEGG_PATHWAY_NODES = 4
KEGG_IN_PATHWAY = 6  # 8 link rows: one undeclared map, one unselected compound
KEGG_LEDGER_ROWS = 2


def run(script, *args, expect=0):
    proc = subprocess.run(
        [sys.executable, str(script), *args], capture_output=True, text=True, cwd=ROOT
    )
    assert proc.returncode == expect, (
        f"{script.name} exited {proc.returncode}, expected {expect}:\n"
        f"{proc.stdout}\n{proc.stderr}"
    )
    return proc


def prep_sources(csv_dir: Path, with_kegg: bool) -> str:
    """HMDB, Reactome and (optionally) KEGG, in the order the build runs them."""
    run(
        PREPS_DIR / "prep_hmdb.py",
        "--xml",
        str(HMDB_MINI),
        "--taxdump",
        str(TAXDUMP_MINI),
        "--reactome",
        str(REACTOME_MINI),
        "--out",
        str(csv_dir),
    )
    gate = ["--with-kegg"] if with_kegg else []
    kegg = run(
        PREP,
        "--kegg",
        str(KEGG_MINI),
        "--out",
        str(csv_dir),
        *gate,
        expect=0 if with_kegg else MISSING_INPUT,
    )
    run(
        PREPS_DIR / "prep_reactome.py",
        "--reactome",
        str(REACTOME_MINI),
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
    return kegg.stdout + kegg.stderr


def load(csv_dir: Path, sources: list[str]):
    from microbiomekg.fragments import compose

    from microbiomekg.ontology import ontology_for, write_json

    blueprint = compose(ROOT / "microbiomekg" / "blueprints", sources)
    settings = blueprint.setdefault("settings", {})
    settings["root"] = str(csv_dir)
    for key in ("output", "output_path", "output_file"):
        settings.pop(key, None)
    write_json(csv_dir / "ontology.json", ontology_for(sources))
    blueprint["ontology"] = str(csv_dir / "ontology.json")
    local = csv_dir / "blueprint.test.json"
    local.write_text(json.dumps(blueprint))
    return kglite.from_blueprint(local, verbose=False, save=False)


@pytest.fixture(scope="module")
def gated(tmp_path_factory):
    """The default build: the flag is not passed, so KEGG loads nothing."""
    csv_dir = tmp_path_factory.mktemp("kegg-gated") / "csv"
    csv_dir.mkdir()
    output = prep_sources(csv_dir, with_kegg=False)
    return load(csv_dir, ["hmdb", "reactome"]), csv_dir, output


@pytest.fixture(scope="module")
def opted_in(tmp_path_factory):
    """The same fixture with ``--with-kegg``."""
    csv_dir = tmp_path_factory.mktemp("kegg-on") / "csv"
    csv_dir.mkdir()
    output = prep_sources(csv_dir, with_kegg=True)
    return load(csv_dir, ["hmdb", "reactome", SOURCE]), csv_dir, output


def rows(graph, query):
    return list(graph.cypher(query))


def one(graph, query):
    result = rows(graph, query)
    assert result, f"query returned no rows:\n{query}"
    return result[0]


def table(csv_dir, name):
    path = csv_dir / name
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# --------------------------------------------------------------------------
# The gate — tested by diffing two builds, not by trusting the flag
# --------------------------------------------------------------------------


def test_the_prep_refuses_without_the_flag_and_says_why(gated):
    """It exits `MISSING_INPUT`, the same code an absent raw file uses, because
    the build's response is the same: leave the source out and say so. Exiting
    0 with no rows would look identical to a successful empty load."""
    output = gated[2]
    assert kg.BUILD_FLAG in output
    assert "cannot be published" in output


def test_the_default_build_carries_no_kegg_row_anywhere(gated):
    """The claim the licence rests on, checked over the whole graph rather than
    over the tables KEGG was expected to touch."""
    graph = gated[0]
    assert not rows(graph, "MATCH (p:Pathway) WHERE p.id STARTS WITH 'KEGG:' RETURN p")
    assert not rows(
        graph,
        "MATCH ()-[r]->() WHERE r.source_licence = 'KEGG-restricted' RETURN r LIMIT 1",
    )
    assert not rows(
        graph,
        "MATCH ()-[r]->() WHERE r.primary_source = 'kegg' RETURN r LIMIT 1",
    )


def test_the_flag_adds_kegg_rows_and_nothing_else(gated, opted_in):
    """The flag's blast radius must be exactly the licence boundary. In
    particular the **metabolite set is identical**: `prep_hmdb.py`'s selection
    rule deliberately never consults KEGG, because a metabolite kept because
    KEGG links it would be a KEGG-derived row in a graph built without the
    flag."""
    before = {
        (r["metabolite_id"], r["selection_rule"])
        for r in table(gated[1], "metabolite.csv")
    }
    after = {
        (r["metabolite_id"], r["selection_rule"])
        for r in table(opted_in[1], "metabolite.csv")
    }
    assert before == after and before

    def counts(graph):
        return {
            r["t"]: r["n"]
            for r in rows(graph, "MATCH (n) RETURN labels(n)[0] AS t, count(n) AS n")
        }

    off, on = counts(gated[0]), counts(opted_in[0])
    assert set(off) == set(on)
    assert on["Pathway"] - off["Pathway"] == KEGG_PATHWAY_NODES
    assert {t: n for t, n in on.items() if t != "Pathway"} == {
        t: n for t, n in off.items() if t != "Pathway"
    }


def test_every_kegg_row_carries_the_restricted_licence(opted_in):
    """G3: a per-edge licence is what lets a mixed-licence graph be cut into a
    shippable part by one WHERE clause instead of a rebuild."""
    graph = opted_in[0]
    edges = rows(
        graph,
        "MATCH ()-[r:IN_PATHWAY]->() WHERE r.primary_source = 'kegg' "
        "RETURN DISTINCT r.source_licence AS licence, r.evidence_level AS level, "
        "r.knowledge_level AS kl, r.agent_type AS agent, r.evidence_code AS code",
    )
    assert edges == [
        {
            "licence": "KEGG-restricted",
            # KEGG ships no per-link evidence field of any kind; `unknown` is a
            # countable value where a fabricated code would be indistinguishable
            # from Reactome's real one.
            "level": "unknown",
            "kl": "knowledge_assertion",
            "agent": "manual_agent",
            "code": None,
        }
    ]
    assert SOURCE_LICENCE[SOURCE] == "KEGG-restricted"
    nodes = rows(
        graph,
        "MATCH (p:Pathway) WHERE p.pathway_source = 'kegg' "
        "RETURN DISTINCT p.source_licence AS licence",
    )
    assert nodes == [{"licence": "KEGG-restricted"}]


def test_kegg_declares_no_class_or_relationship_of_its_own(opted_in):
    """Why the gate is cheap: KEGG writes rows into Reactome's `Pathway` and
    `IN_PATHWAY`, so composing its fragment into a build that did not run the
    prep costs nothing — no node type loaded empty, no audit rule at 0/0."""
    assert kg.CLASSES == {} and kg.RELATIONSHIPS == {}
    shared = one(
        opted_in[0],
        "MATCH ()-[r:IN_PATHWAY]->() RETURN count(r) AS edges, "
        "count(DISTINCT r.primary_source) AS sources",
    )
    assert shared["sources"] == 2, "one relationship, one CSV, two contributors"
    assert shared["edges"] == 8 + KEGG_IN_PATHWAY


# --------------------------------------------------------------------------
# The four ids that look right and are not
# --------------------------------------------------------------------------


def test_the_single_lowercase_kegg_id_still_joins(opted_in):
    """HMDB 5.0 carries exactly one lowercase `kegg_id` (`c0338`) among 5,900.
    A case-sensitive join loses that metabolite's pathway edges and nothing
    anywhere says it happened."""
    result = rows(
        opted_in[0],
        "MATCH (m:Metabolite {id: 'CHEBI:32816'})-[r:IN_PATHWAY]->(p:Pathway) "
        "WHERE r.primary_source = 'kegg' RETURN m.kegg_id AS kegg, p.id AS pathway",
    )
    assert result == [{"kegg": "c00022", "pathway": "KEGG:map00010"}]


def test_the_hsa_pathway_list_is_not_loaded_beside_the_map_list(opted_in):
    """`list_pathway_hsa.tsv` is the same maps with the species appended to the
    name. Loading both yields two Pathway nodes for one biological pathway, and
    a query that counts pathways then double-counts silently."""
    graph = opted_in[0]
    assert not rows(
        graph, "MATCH (p:Pathway) WHERE p.id STARTS WITH 'KEGG:hsa' RETURN p"
    )
    assert (
        one(
            graph,
            "MATCH (p:Pathway) WHERE p.pathway_source = 'kegg' RETURN count(p) AS n",
        )["n"]
        == KEGG_PATHWAY_NODES
    )
    assert not rows(
        graph,
        "MATCH (p:Pathway) WHERE p.title CONTAINS 'Homo sapiens (human)' RETURN p",
    )


def test_the_pubchem_conversion_is_not_loaded(opted_in):
    """`conv/compound/pubchem` returns PubChem **Substance** ids: `C00001`
    (water) maps to `pubchem:3303` where water's **Compound** id is 962.
    Written beside HMDB's `pubchem_compound_id`, which is a CID, every KEGG
    compound would point at the wrong PubChem record and 3303 would look like a
    perfectly valid identifier."""
    assert "NOT loaded: those are PubChem Substance ids" in opted_in[2]
    assert not rows(
        opted_in[0], "MATCH (m:Metabolite) WHERE m.pubchem_cid = 3303 RETURN m"
    )


def test_the_namespace_prefixes_are_stripped_from_both_columns(opted_in):
    """`path:map00010` and `cpd:C00022`. Strip one and not the other and the
    compound key never matches HMDB's bare `C00022` — an empty join, no error."""
    graph = opted_in[0]
    assert not rows(graph, "MATCH (p:Pathway) WHERE p.id CONTAINS 'path:' RETURN p")
    assert one(
        graph,
        "MATCH (p:Pathway {id: 'KEGG:map00650'}) RETURN p.title AS name, "
        "p.source_id AS source_id",
    ) == {"name": "Butanoate metabolism", "source_id": "map00650"}


def test_withdrawn_and_wrong_namespace_ids_are_counted_apart(opted_in):
    """Two different facts. A `C` id absent from the compound list is one KEGG
    has withdrawn since HMDB 5.0 — 27 in the real data, the measurable cost of
    HMDB being four years old. A `D` (drug) or `G` (glycan) id was never going
    to be in a *compound* list, so counting it as withdrawn overstates the
    decay by 10 ids that are simply in another namespace."""
    output = opted_in[2]
    assert (
        "no longer in list_compound.tsv (withdrawn upstream since HMDB 5.0): C00626"
        in output
    )
    assert "not compound ids at all (D = drug, G = glycan)" in output
    assert ": D00109" in output
    # And the third bucket, which the real data made necessary: HMDB's one
    # lowercase kegg_id is `c0338`, which upper-cases to a **four**-digit
    # `C0338` — not miscased, not a KEGG identifier at all. Filing it under
    # "withdrawn" would blame KEGG for HMDB's typo.
    assert "are not a KEGG identifier at all" in output


def test_a_link_whose_compound_is_not_selected_reaches_the_ledger(opted_in):
    """The consequence of not letting KEGG steer the selection rule: KEGG links
    6,688 compounds and the graph has metabolites for a fraction of them. The
    shortfall is a count, not a silent difference between two builds."""
    ledger = [
        r
        for r in table(opted_in[1], "unresolved_pathway_links.csv")
        if r["primary_source"] == SOURCE
    ]
    assert len(ledger) == KEGG_LEDGER_ROWS
    reasons = {r["source_id"]: r["reason"] for r in ledger}
    assert "no Metabolite node" in reasons["KEGG:C00031"]
    assert "does not declare" in reasons["KEGG:map00999"]
    assert (
        one(
            opted_in[0],
            "MATCH ()-[r:IN_PATHWAY]->() WHERE r.primary_source = 'kegg' "
            "RETURN count(r) AS n",
        )["n"]
        == KEGG_IN_PATHWAY
    )


def test_no_taxon_reaches_a_kegg_pathway(opted_in):
    """`/list/organism` was retired upstream and the roster that replaced it
    lost the lineage column, so there is no taxid in any of the six files. A
    taxon–pathway edge from KEGG would have to be invented."""
    assert "list_genome.tsv NOT loaded" in opted_in[2]
    assert not rows(
        opted_in[0],
        "MATCH (t:Taxon)-[r]->(p:Pathway) WHERE p.pathway_source = 'kegg' RETURN r",
    )

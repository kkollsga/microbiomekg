"""Reactome: a DAG that looks like a tree, and 87.7% orthology projection.

The fixture (``tests/fixtures/reactome_mini/``) is three headerless TSVs in the
shipped 3- and 6-column layouts, each row a pitfall from
``docs/research/source-formats.md`` §4:

* a child with **two** parents — a loader modelling the hierarchy as a tree
  drops one of them, and there are 388 such children in the real file;
* a pathway that appears in ``ChEBI2Reactome.txt`` and **not** in
  ``ReactomePathways.txt`` — dropped by a loader that requires the node first,
  nameless in one that mints it from the id alone;
* a pathway name with a trailing space, in both files;
* a mapping row whose species column contradicts its own id infix;
* a ChEBI id no HMDB record carries, which can reach no metabolite because the
  mapping files carry no compound name to mint one from.

And the reading that is part of the answer rather than a caveat on it:
Reactome's species are 16 model organisms, so an ``IN_PATHWAY`` hit says the
*metabolite* takes part in a human pathway and never that the taxon runs it.
:func:`test_d13_shaped_path_is_capability_not_production` is that sentence as a
query.
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
SCRIPTS = ROOT / "scripts"
PREP = SCRIPTS / "prep_reactome.py"

sys.path.insert(0, str(SCRIPTS))

for _needed in (PREP, REACTOME_MINI / "ReactomePathways.txt", HMDB_MINI):
    if not _needed.exists():
        pytest.skip(f"{_needed} does not exist yet", allow_module_level=True)

from microbiomekg.ontology.reactome import EVIDENCE_CODES, evidence_for  # noqa: E402

SOURCE = "reactome"

# --------------------------------------------------------------------------
# Golden values, derived from the fixture by hand.
# --------------------------------------------------------------------------

PATHWAY_NODES = 9        # 8 declared + 1 minted from a mapping row
HIERARCHY_EDGES = 7      # 8 rows, one naming an undeclared pathway
IN_PATHWAY_EDGES = 8     # 9 mapping rows, one ChEBI with no metabolite
LEDGER_ROWS = 2
MULTI_PARENT_CHILD = "REACT:R-HSA-192105"
MINTED = "REACT:R-SCE-9865878"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    work = tmp_path_factory.mktemp("reactome")
    csv_dir = work / "csv"
    csv_dir.mkdir()

    def run(script, *args):
        proc = subprocess.run(
            [sys.executable, str(script), *args], capture_output=True, text=True, cwd=ROOT
        )
        assert proc.returncode == 0, f"{script.name} failed:\n{proc.stdout}\n{proc.stderr}"
        return proc

    # HMDB first: IN_PATHWAY joins through the metabolite table it writes,
    # which is what this prep's DEPENDS_ON declares.
    run(
        SCRIPTS / "prep_hmdb.py",
        "--xml", str(HMDB_MINI),
        "--taxdump", str(TAXDUMP_MINI),
        "--reactome", str(REACTOME_MINI),
        "--out", str(csv_dir),
    )
    prep = run(PREP, "--reactome", str(REACTOME_MINI), "--out", str(csv_dir))
    run(
        SCRIPTS / "prep_taxonomy.py",
        "--taxdump", str(TAXDUMP_MINI),
        "--out", str(csv_dir),
        "--scope", "cited",
        "--cited-from", str(csv_dir / "cited_taxa.csv"),
    )

    from build_blueprint import compose

    from microbiomekg.ontology import ontology_for, write_json

    sources = ["hmdb", SOURCE]
    blueprint = compose(ROOT / "blueprints", sources)
    settings = blueprint.setdefault("settings", {})
    settings["root"] = str(csv_dir)
    for key in ("output", "output_path", "output_file"):
        settings.pop(key, None)
    write_json(csv_dir / "ontology.json", ontology_for(sources))
    blueprint["ontology"] = str(csv_dir / "ontology.json")
    local = csv_dir / "blueprint.test.json"
    local.write_text(json.dumps(blueprint))

    return kglite.from_blueprint(local, verbose=False, save=False), csv_dir, prep.stdout


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
# The hierarchy — a DAG, and the edges a tree model loses
# --------------------------------------------------------------------------


def test_a_child_keeps_every_parent(graph):
    """388 of Reactome's 23,188 children have more than one parent. A loader
    that keeps one — or an ontology declaring `cardinality: {max: 1}` — drops
    the others with no warning, and an ancestry walk then returns a subtree
    rather than the DAG it was asked for."""
    parents = {
        r["parent"]
        for r in rows(
            graph,
            f"MATCH (c:Pathway {{id: '{MULTI_PARENT_CHILD}'}})"
            "-[:PART_OF_PATHWAY]->(p:Pathway) RETURN p.id AS parent",
        )
    }
    assert parents == {"REACT:R-HSA-8978868", "REACT:R-HSA-1430728"}


def test_the_hierarchy_is_walkable_transitively(graph):
    """`ancestry`, not `transitive`: nothing stores the closure, so the walk is
    `*1..` and declaring a stored closure would report ~100% violations."""
    reached = {
        r["ancestor"]
        for r in rows(
            graph,
            "MATCH (c:Pathway {id: 'REACT:R-HSA-70326'})-[:PART_OF_PATHWAY*1..]->"
            "(p:Pathway) RETURN DISTINCT p.id AS ancestor",
        )
    }
    assert reached == {"REACT:R-HSA-71387", "REACT:R-HSA-1430728"}


def test_a_hierarchy_row_with_an_undeclared_endpoint_reaches_the_ledger(graph, csv_dir):
    """The relation file is two bare ids and carries no name, so an endpoint
    the pathway list does not declare cannot be minted from it."""
    ledger = table(csv_dir, "unresolved_pathway_links.csv")
    orphan = [r for r in ledger if r["source_id"] == "R-HSA-9999999"]
    assert len(orphan) == 1 and "hierarchy row" in orphan[0]["reason"]
    assert not rows(graph, "MATCH (p:Pathway {id: 'REACT:R-HSA-9999999'}) RETURN p")
    assert one(
        graph, "MATCH ()-[r:PART_OF_PATHWAY]->() RETURN count(r) AS n"
    )["n"] == HIERARCHY_EDGES


# --------------------------------------------------------------------------
# Pathway nodes, including the one that is only in a mapping file
# --------------------------------------------------------------------------


def test_a_pathway_only_in_a_mapping_file_is_minted_with_its_name_and_species(graph):
    """`R-SCE-9865878` is in both mapping files and missing from
    `ReactomePathways.txt`. A loader requiring the node first drops the rows;
    one minting from the id alone produces a nameless, speciesless node. The
    name and species are in columns 4 and 6 of the row that needed it."""
    result = one(
        graph,
        f"MATCH (p:Pathway {{id: '{MINTED}'}}) RETURN p.title AS name, "
        "p.species AS species, p.pathway_source AS source",
    )
    assert result == {"name": "Complex III assembly",
                      "species": "Saccharomyces cerevisiae", "source": SOURCE}
    assert one(graph, "MATCH (p:Pathway) RETURN count(p) AS n")["n"] == PATHWAY_NODES


def test_trailing_whitespace_is_stripped_from_names(graph):
    """204 names in `ReactomePathways.txt` carry a trailing space, and so does
    the mapping files' name column — which is compared against it whenever a
    node has to be minted."""
    result = one(
        graph,
        "MATCH (p:Pathway {id: 'REACT:R-HSA-192105'}) RETURN p.title AS name",
    )
    assert result["name"] == "Synthesis of bile acids and bile salts"


def test_a_species_column_contradicting_its_own_id_infix_is_counted(prep_output):
    """§4's fifth pitfall: the species is stated twice and the loader must
    check rather than read one arbitrarily. The fixture's `R-MMU-70326` row
    claims `Homo sapiens`, which would put the wrong species on an edge."""
    assert "1 rows where the infix and the species column disagree" in prep_output


# --------------------------------------------------------------------------
# The evidence code — the cleanest knowledge_level signal in the increment
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code, expected",
    [
        ("TAS", ("unknown", "knowledge_assertion", "manual_agent", "ECO:0000304")),
        ("IEA", ("computational-predicted", "logical_entailment", "automated_agent",
                 "ECO:0000501")),
        ("tas", ("unknown", "knowledge_assertion", "manual_agent", "ECO:0000304")),
        ("", ("unknown", "not_provided", "not_provided", "")),
        (None, ("unknown", "not_provided", "not_provided", "")),
        ("NAS", ("unknown", "not_provided", "not_provided", "")),
    ],
)
def test_the_evidence_code_maps_to_part_bs_vocabulary(code, expected):
    """An unrecognised code answers `not_provided` rather than inheriting TAS's
    curator authority. The column has held exactly two values in every row of
    both mapping files, so a third would be new data."""
    assert evidence_for(code) == expected


def test_tas_is_not_given_a_plausible_looking_observational_level():
    """Part B is explicit: the ladder describes an abundance observation and a
    pathway membership is not one. `unknown` is a countable value; a fabricated
    level is the F10 failure the schema survey names."""
    assert EVIDENCE_CODES["TAS"][0] == "unknown"
    assert EVIDENCE_CODES["IEA"][0] == "computational-predicted"


def test_the_projection_share_is_visible_on_the_edges(graph):
    """87.7% of `ChEBI2Reactome.txt` is IEA — an orthology projection from
    human, not a read paper. If that is not on the edge, a consumer cannot tell
    a curated membership from a propagated one, and the file offers no other
    signal."""
    counts = {
        (r["code"], r["kl"], r["agent"]): r["n"]
        for r in rows(
            graph,
            "MATCH ()-[r:IN_PATHWAY]->() WHERE r.primary_source = 'reactome' "
            "RETURN r.evidence_code AS code, r.knowledge_level AS kl, "
            "r.agent_type AS agent, count(r) AS n",
        )
    }
    assert counts == {
        ("TAS", "knowledge_assertion", "manual_agent"): 4,
        ("IEA", "logical_entailment", "automated_agent"): 4,
    }


def test_every_edge_carries_cc0_and_its_provenance(graph):
    """G3. CC0 is what makes Reactome the pathway source that can ship, and the
    licence is per edge so a mixed-licence graph can be cut in parts."""
    result = rows(
        graph,
        "MATCH ()-[r:IN_PATHWAY]->() WHERE r.primary_source = 'reactome' "
        "RETURN DISTINCT r.source_licence AS licence, r.source_relation AS relation",
    )
    assert result == [{"licence": "CC0-1.0", "relation": "ChEBI2Reactome"}]
    assert one(
        graph,
        "MATCH ()-[r:IN_PATHWAY]->() RETURN count(r) AS n, "
        "sum(CASE WHEN r.source_record_id IS NULL THEN 1 ELSE 0 END) AS no_record",
    ) == {"n": IN_PATHWAY_EDGES, "no_record": 0}


# --------------------------------------------------------------------------
# What cannot be joined, and what is deliberately not read
# --------------------------------------------------------------------------


def test_a_chebi_id_no_metabolite_carries_reaches_the_ledger(graph, csv_dir):
    """Reactome maps 3,260 ChEBI ids and HMDB carries 13,562; only 1,114 are in
    both. Minting the rest would give bare CURIE nodes with no name, no status
    and no biospecimen — the mapping files carry no compound name at all."""
    ledger = [r for r in table(csv_dir, "unresolved_pathway_links.csv")
              if r["source_id"] == "CHEBI:100241"]
    assert len(ledger) == 1 and "no Metabolite node" in ledger[0]["reason"]
    assert not rows(graph, "MATCH (m:Metabolite {id: 'CHEBI:100241'}) RETURN m")
    assert len(table(csv_dir, "unresolved_pathway_links.csv")) == LEDGER_ROWS


def test_the_all_levels_file_is_not_loaded(prep_output):
    """It is not a superset with extra compounds — it is the same 3,260
    compounds propagated up the hierarchy, 307,049 rows carrying the
    information of 113,779. That ancestry is already PART_OF_PATHWAY."""
    assert "ChEBI2Reactome_All_Levels.txt NOT loaded" in prep_output


def test_ncbi2reactome_is_gene_not_taxonomy_and_is_not_loaded(graph, prep_output):
    """73,767 numeric ids over a 16-species pathway set: there is no world in
    which those are taxa. Reading them as taxids would wire that many imaginary
    organisms into the graph."""
    assert "NCBI2Reactome.txt NOT loaded" in prep_output
    assert not rows(graph, "MATCH (t:Taxon)-[r]->(p:Pathway) RETURN r LIMIT 1")


# --------------------------------------------------------------------------
# D13's shape, and the qualifier that is part of its answer
# --------------------------------------------------------------------------


def test_d13_shaped_path_is_capability_not_production(graph):
    """`(Taxon)-[:PRODUCES]->(Metabolite)-[:IN_PATHWAY]->(Pathway)` resolves —
    and every pathway it reaches belongs to a model organism, never a gut
    commensal, because Reactome has none. The row says the *metabolite* takes
    part in a human pathway; it is not evidence the taxon runs it."""
    result = rows(
        graph,
        """
        MATCH (t:Taxon)-[p:PRODUCES]->(m:Metabolite)-[:IN_PATHWAY]->(pw:Pathway)
        RETURN DISTINCT pw.species AS species
        """,
    )
    species = {r["species"] for r in result}
    assert species, "no taxon reaches a pathway at all"
    assert species <= {"Homo sapiens", "Mus musculus", "Saccharomyces cerevisiae"}


def test_no_rule_this_source_declares_audits_nothing(graph):
    totals = {
        r["rule"]: r["total"]
        for r in rows(graph, "CALL ontology_audit() YIELD rule, total RETURN rule, total")
    }
    mine = {rule: n for rule, n in totals.items()
            if rule.split(".")[0] in ("IN_PATHWAY", "PART_OF_PATHWAY")}
    assert mine, "the audit reports no rule for this source's relationships"
    for rule, n in mine.items():
        assert n > 0, f"{rule} audits nothing"
    assert totals.get("IN_PATHWAY.required_properties") == IN_PATHWAY_EDGES

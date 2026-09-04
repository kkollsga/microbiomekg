"""``microbiomekg.coverage`` — scoring an external curated set against the
graph without loading it (docs/benchmarks.md G6).

Offline: the readers run over tables written in-test in the two sources'
real shapes, reconciliation runs over the taxdump and MONDO minis, and the
score runs over the BugSigDB mini graph, with the references cut from one of
its own edges so the expected coverage is known exactly.
"""

from __future__ import annotations

import json

import pytest
from conftest import BUGSIGDB_MINI, MONDO_MINI, TAXDUMP_MINI

from microbiomekg import coverage
from microbiomekg.conditions import MondoIndex
from microbiomekg.reconcile import TaxonomyIndex

HMDAD_ROWS = (
    "Disease\tMicrobe\tPosition\tEvidence\tPMID\n"
    "Colon cancer\tCollinsella aerofaciens\tGastrointestinal tract\tIncrease\t7574628\n"
    "Colon cancer\tCollinsella aerofaciens\tGastrointestinal tract\tIncrease\t7574628\n"
    "Irritable bowel syndrome(IBS)\tBacteroides\tGut\tDecrease\t1\n"
    "Periodontal\tFusobacterium\tSubgingival\tIncrease\t9495612\n"
)


def _peryton(**over):
    row = {
        "group_two": "Healthy Controls",
        "relationship_name": "Increased",
        "microbe_scientific_name": "Bacteroides",
        "microbe_ncbi_tax_id": 816,
        "disease_mesh_heading": "Ulcerative Colitis",
        "disease_name": "Ulcerative Colitis",
        "disease_mesh_id": "MESH:D003093",
    }
    row.update(over)
    return row


def test_hmdad_reader_dedupes_and_normalises_direction(tmp_path):
    path = tmp_path / "data_download.txt"
    path.write_text(HMDAD_ROWS)
    refs = coverage.read_hmdad(path)
    assert len(refs) == 3  # the duplicate row collapsed
    assert refs[0] == coverage.Reference(
        "Collinsella aerofaciens", "Colon cancer", "increased"
    )
    assert refs[1].direction == "decreased"


def test_peryton_reader_keeps_only_the_healthy_comparator_and_ids(tmp_path):
    rows = [
        _peryton(),
        _peryton(),  # duplicate
        _peryton(group_two="Crohn Disease"),  # disease vs disease: out
        _peryton(relationship_name="Present"),  # not a direction
        _peryton(disease_mesh_id="MESH:D003424", disease_mesh_heading="Crohn Disease"),
    ]
    path = tmp_path / "associations.json"
    path.write_text(json.dumps(rows))
    refs = coverage.read_peryton(path)
    assert len(refs) == 3
    assert refs[0].tax_id == 816 and refs[0].disease_curie == "MESH:D003093"
    assert refs[0].direction == "increased"
    assert [r.direction for r in refs] == ["increased", None, "increased"]


def test_disease_names_lose_only_a_trailing_parenthetical():
    assert coverage.disease_key("Irritable bowel syndrome(IBS)") == (
        "Irritable bowel syndrome"
    )
    assert coverage.disease_key("Colon cancer") == "Colon cancer"


@pytest.fixture(scope="module")
def built():
    from microbiomekg import pipeline
    from microbiomekg.preps import prep_bugsigdb, prep_taxonomy
    from microbiomekg.tables import Frames

    store = Frames()
    prep_bugsigdb.run(BUGSIGDB_MINI, store, taxdump=TAXDUMP_MINI, mondo=MONDO_MINI)
    prep_taxonomy.run(BUGSIGDB_MINI.parent, store, taxdump=TAXDUMP_MINI, scope="cited")
    graph, _ = pipeline.load_graph(store, ["bugsigdb"], verbose=False)
    return graph


def test_a_pair_the_graph_holds_is_covered_and_an_invented_one_is_not(built):
    layer = coverage.association_layer(built)
    assert layer, "the mini graph has no MONDO-keyed association edge to score against"
    (tax_id, mondo), reports = next(iter(layer.items()))
    idx = TaxonomyIndex.from_taxdump(TAXDUMP_MINI)
    mondo_index = MondoIndex.from_obo(MONDO_MINI)
    name = idx.scientific_name[tax_id]
    label = mondo_index.label[mondo]
    direction = reports[0][0]
    refs = [
        coverage.Reference(name, label, direction),
        coverage.Reference(name, label, None, tax_id=tax_id, disease_curie=mondo),
        coverage.Reference("Not a taxon anyone named", label, "increased"),
        coverage.Reference(name, "Not a disease MONDO spells", "increased"),
    ]
    resolved = coverage.resolve(refs, idx, mondo_index)
    assert [r.pair for r in resolved] == [(tax_id, mondo), (tax_id, mondo), None, None]
    s = coverage.score("mini", resolved, layer)
    assert (s.references, s.pairs_resolvable, s.pairs_covered) == (4, 2, 2)
    assert s.coverage == 1.0
    assert sum(s.evidence.values()) == 2 * len(reports)
    # Only the first reference states a direction, and it is the graph's own.
    assert (s.direction_comparable, s.direction_agree) == (1, 1)
    assert "unresolved" in s.taxon_statuses or "ambiguous" in s.taxon_statuses
    assert s.disease_routes.get("unmatched") == 1
    assert "pairs covered" in coverage.report(s)


def test_a_contradicted_direction_is_counted_not_resolved(built):
    layer = coverage.association_layer(built)
    (tax_id, mondo), reports = next(
        (k, v) for k, v in layer.items() if len({d for d, _ in v if d}) == 1
    )
    only = next(d for d, _ in reports if d)
    other = "decreased" if only == "increased" else "increased"
    ref = coverage.Reference("x", "y", other, tax_id=tax_id, disease_curie=mondo)
    resolved = [coverage.Resolved(ref, tax_id, "exact", mondo, "equivalence")]
    s = coverage.score("mini", resolved, layer)
    assert (s.direction_comparable, s.direction_contradict, s.direction_agree) == (
        1,
        1,
        0,
    )


def test_an_absent_set_is_a_missing_input_naming_the_fetch(tmp_path):
    from microbiomekg.rawdata import MissingInput

    with pytest.raises(MissingInput) as absent:
        coverage.read_set("hmdad", tmp_path)
    assert "--only hmdad" in str(absent.value)

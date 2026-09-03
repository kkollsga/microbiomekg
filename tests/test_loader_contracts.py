"""kglite loader behaviours this project's model depends on.

These test the engine, not this repo, and they run whether or not the
implementation exists. Each one exists because the model would be silently
wrong if the behaviour changed: parallel evidence edges are the whole point
(Part C13), and an integer tax_id key is what every query joins on (C16).
"""

from __future__ import annotations

import csv
import json
import os

import pandas as pd
import pytest

kglite = pytest.importorskip("kglite")


def _write(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


@pytest.fixture
def parallel_edge_blueprint(tmp_path):
    """Ten parallel `A1 -[:LINKS]-> B1` edges, loaded through a junction CSV."""
    _write(tmp_path / "a.csv", ["id", "name"], [(i, f"A{i}") for i in (1, 2, 3)])
    _write(tmp_path / "b.csv", ["id", "name"], [(i, f"B{i}") for i in (1, 2, 3)])
    _write(tmp_path / "j.csv", ["a_id", "b_id", "pmid"], [(1, 1, 100 + k) for k in range(10)])
    blueprint = {
        "settings": {"root": str(tmp_path)},
        "nodes": {
            "B": {"csv": "b.csv", "pk": "id", "title": "name",
                  "properties": {"name": "string"}},
            "A": {
                "csv": "a.csv", "pk": "id", "title": "name",
                "properties": {"name": "string"},
                "connections": {"junction_edges": {"LINKS": {
                    "csv": "j.csv", "source_fk": "a_id",
                    "target": "B", "target_fk": "b_id",
                    "properties": ["pmid"], "property_types": {"pmid": "int"},
                }}},
            },
        },
    }
    path = tmp_path / "blueprint.json"
    path.write_text(json.dumps(blueprint))
    return path


def test_junction_loader_keeps_parallel_edges(parallel_edge_blueprint):
    """C13: two studies are two edges, and the loader must not merge them."""
    graph = kglite.from_blueprint(parallel_edge_blueprint, save=False)
    n = list(graph.cypher("MATCH ()-[r:LINKS]->() RETURN count(r) AS n"))[0]["n"]
    assert n == 10, f"the junction loader collapsed 10 parallel edges into {n}"


def test_junction_loader_keeps_parallel_edges_across_a_chunk_boundary(
    parallel_edge_blueprint, monkeypatch
):
    """C13, at the boundary that used to silently discard evidence.

    Until kglite 0.16.22 the junction loader decided per chunk whether the
    connection type was new: the first chunk registered it and every later
    chunk merged by endpoints, folding its rows onto the edges the first chunk
    had created. Ten identical `A1 -> B1` rows through a three-row chunk gave
    three edges, and this project's ~118k-row `taxon_disease.csv` lost 7.7% of
    its associations against the 100,000-row default — with no warning.

    The chunk size is a memory bound again, so it must not change the graph.
    Three rows per chunk over ten rows is four chunks: if the regime is ever
    re-decided per chunk this returns 3 and the build's whole evidence
    multiplicity is back in question.
    """
    monkeypatch.setenv("KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE", "3")
    graph = kglite.from_blueprint(parallel_edge_blueprint, save=False)
    n = list(graph.cypher("MATCH ()-[r:LINKS]->() RETURN count(r) AS n"))[0]["n"]
    assert n == 10, (
        f"the chunk size changed the result: 10 parallel edges loaded as {n} "
        f"at 3 rows per chunk. This is the kglite<0.16.22 defect returning, and "
        f"the build has no chunk-size override left to hide it."
    )


def test_junction_loader_keeps_edge_properties_across_a_chunk_boundary(
    parallel_edge_blueprint, monkeypatch
):
    """The same defect's other half: the survivors' properties were overwritten.

    Merging by endpoints did not only drop rows, it wrote each later row's
    values onto the edge the first chunk had made — so the three survivors
    carried the *last* chunk's `pmid`. Ten distinct pmids must come back.
    """
    monkeypatch.setenv("KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE", "3")
    graph = kglite.from_blueprint(parallel_edge_blueprint, save=False)
    pmids = sorted(
        r["p"] for r in graph.cypher("MATCH ()-[r:LINKS]->() RETURN r.pmid AS p")
    )
    assert pmids == list(range(100, 110)), (
        f"the chunk boundary rewrote edge properties: got {pmids}"
    )


def test_integer_ids_survive_a_nan_in_the_column():
    """C16: a pandas NaN makes the id column float64 — the NaN row is skipped."""
    df = pd.DataFrame({"tax_id": [562, 1496, float("nan")], "name": ["a", "b", "c"]})
    assert df["tax_id"].dtype == "float64"
    graph = kglite.KnowledgeGraph()
    with pytest.warns(UserWarning):
        report = graph.add_nodes(df, "Taxon", "tax_id", "name")
    assert report["nodes_created"] == 2
    assert report["nodes_skipped"] == 1, (
        "the NaN row is dropped; a loader that ignores nodes_skipped never learns"
    )
    got = list(graph.cypher("MATCH (t:Taxon) RETURN t.tax_id AS v"))
    assert {r["v"] for r in got} == {562, 1496}
    assert all(isinstance(r["v"], int) for r in got), "whole-number floats must coerce"


def test_a_nan_pins_a_property_to_float_for_the_whole_graph():
    """C16: the first CSV loaded fixes the property's type, forever."""
    graph = kglite.KnowledgeGraph()
    graph.add_nodes(
        pd.DataFrame({"id": ["s1", "s2"], "n": [15, None]}), "Signature", "id"
    )
    with pytest.warns(UserWarning, match="Type mismatch"):
        graph.add_nodes(
            pd.DataFrame({"id": ["s3"], "n": pd.array([15], dtype="Int64")}),
            "Signature",
            "id",
        )


def test_a_string_tax_id_does_not_match_an_integer_comparison():
    """C16: the silent empty result — no error, no rows."""
    graph = kglite.KnowledgeGraph()
    graph.add_nodes(pd.DataFrame({"tax_id": ["562"], "n": ["E. coli"]}), "Taxon", "tax_id", "n")
    assert list(graph.cypher("MATCH (t:Taxon) WHERE t.tax_id = 562 RETURN t.n AS n")) == []
    assert list(graph.cypher("MATCH (t:Taxon) WHERE t.tax_id = '562' RETURN t.n AS n"))

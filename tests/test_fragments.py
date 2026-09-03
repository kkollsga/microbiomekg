"""The loader framework: fragments compose, and a contradiction is an error.

The blueprint and the ontology are single documents that every source has to
appear in, which makes them the one place two agents adding two sources
collide. They are therefore authored as fragments and composed — and the whole
value of that is in the merge *rule*, not in the file split: a merger that let
the last fragment win would turn a real disagreement about which CSV backs
``Disease`` into a silently different graph.

So the rule is asserted here, in both of its uses.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from microbiomekg.fragments import FragmentConflict, merge_fragments

ROOT = Path(__file__).resolve().parents[1]
FRAGMENTS = ROOT / "blueprints"
BLUEPRINT = ROOT / "blueprint.json"
BUILD_BLUEPRINT = ROOT / "scripts" / "build_blueprint.py"


# --------------------------------------------------------------------------
# The merge rule
# --------------------------------------------------------------------------


def test_two_fragments_may_declare_the_same_thing():
    """That is how a source says "I write rows into this table too"."""
    merged = merge_fragments(
        [
            ("a.json", {"nodes": {"Disease": {"csv": "disease.csv", "pk": "condition_id"}}}),
            ("b.json", {"nodes": {"Disease": {"csv": "disease.csv", "pk": "condition_id"}}}),
        ]
    )
    assert merged == {"nodes": {"Disease": {"csv": "disease.csv", "pk": "condition_id"}}}


def test_a_fragment_may_add_to_a_node_another_fragment_owns():
    merged = merge_fragments(
        [
            ("core.json", {"nodes": {"Taxon": {"csv": "taxon.csv", "properties": {"rank": "string"}}}}),
            ("later.json", {"nodes": {"Taxon": {"properties": {"placeholder": "bool"}}}}),
        ]
    )
    assert merged["nodes"]["Taxon"] == {
        "csv": "taxon.csv",
        "properties": {"rank": "string", "placeholder": "bool"},
    }


def test_a_contradiction_is_an_error_naming_both_fragments():
    with pytest.raises(FragmentConflict) as excinfo:
        merge_fragments(
            [
                ("core.json", {"nodes": {"Disease": {"csv": "disease.csv"}}}),
                ("rogue.json", {"nodes": {"Disease": {"csv": "my_diseases.csv"}}}),
            ]
        )
    message = str(excinfo.value)
    assert "nodes.Disease.csv" in message
    assert "core.json" in message and "rogue.json" in message


def test_a_property_redeclared_with_a_different_type_is_an_error():
    """The failure this catches is silent otherwise: a column loaded as a
    string in one build and an int in the next changes what `= 851` matches."""
    with pytest.raises(FragmentConflict):
        merge_fragments(
            [
                ("a.json", {"nodes": {"X": {"properties": {"pmid": "int"}}}}),
                ("b.json", {"nodes": {"X": {"properties": {"pmid": "string"}}}}),
            ]
        )


def test_two_junction_edges_under_one_node_are_both_kept():
    """Keyed by relationship name: `ASSOCIATED_WITH` and a second source's
    `ABUNDANCE_CHANGED_BY` are different relations off the same node type."""
    merged = merge_fragments(
        [
            ("a.json", {"nodes": {"Taxon": {"connections": {"junction_edges": {
                "ASSOCIATED_WITH": {"csv": "taxon_condition.csv"}}}}}}),
            ("b.json", {"nodes": {"Taxon": {"connections": {"junction_edges": {
                "ABUNDANCE_CHANGED_BY": {"csv": "taxon_intervention.csv"}}}}}}),
        ]
    )
    assert set(merged["nodes"]["Taxon"]["connections"]["junction_edges"]) == {
        "ASSOCIATED_WITH",
        "ABUNDANCE_CHANGED_BY",
    }


def test_the_same_relationship_backed_by_two_csvs_is_an_error():
    """A junction entry names one relationship, one CSV and one target type,
    so a second source's edges of the same relationship are *rows in that
    CSV*, not a second entry. Getting that wrong must not be silent."""
    with pytest.raises(FragmentConflict):
        merge_fragments(
            [
                ("a.json", {"nodes": {"Taxon": {"connections": {"junction_edges": {
                    "ASSOCIATED_WITH": {"csv": "taxon_condition.csv"}}}}}}),
                ("b.json", {"nodes": {"Taxon": {"connections": {"junction_edges": {
                    "ASSOCIATED_WITH": {"csv": "gutmdisorder_disease.csv"}}}}}}),
            ]
        )


def test_a_shared_property_list_is_an_ordered_union_not_a_concatenation():
    """A shared junction edge's `properties` list is declared by the fragment
    that owns the shape and extended by the sources that add columns to the
    same CSV; neither should have to know about the other's entries."""
    merged = merge_fragments(
        [
            ("a.json", {"e": {"properties": ["direction", "pmid"]}}),
            ("b.json", {"e": {"properties": ["pmid", "p_value"]}}),
        ]
    )
    assert merged["e"]["properties"] == ["direction", "pmid", "p_value"]


def test_merging_is_deterministic_in_the_order_given():
    a = ("a.json", {"nodes": {"A": {"properties": {"x": "int"}}}})
    b = ("b.json", {"nodes": {"B": {"properties": {"y": "int"}}}})
    assert json.dumps(merge_fragments([a, b])) == json.dumps(merge_fragments([a, b]))


def test_a_fragment_is_not_mutated_by_the_merge():
    """The merger deep-copies; a fragment that came out of `json.loads` in one
    build step must not be a shared mutable held by the next."""
    fragment = {"nodes": {"A": {"properties": {"x": "int"}}}}
    merged = merge_fragments([("a.json", fragment), ("b.json", {"nodes": {"A": {"properties": {"y": "int"}}}})])
    assert fragment == {"nodes": {"A": {"properties": {"x": "int"}}}}
    assert set(merged["nodes"]["A"]["properties"]) == {"x", "y"}


# --------------------------------------------------------------------------
# The composed artifacts
# --------------------------------------------------------------------------


def test_the_checked_in_blueprint_matches_its_fragments():
    """A drifted `blueprint.json` loads a different graph than the fragments
    describe, and nothing else here would catch it. Regenerate with
    `python scripts/build_blueprint.py`."""
    if not FRAGMENTS.is_dir():
        pytest.skip("no blueprints/ directory")
    proc = subprocess.run(
        [sys.executable, str(BUILD_BLUEPRINT), "--check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_every_fragment_is_a_blueprint_shaped_document():
    for path in sorted(FRAGMENTS.glob("*.json")):
        document = json.loads(path.read_text())
        assert "nodes" in document, f"{path.name} declares no node types"
        assert document.get("_doc"), (
            f"{path.name} has no `_doc`: a fragment has to say which source it "
            f"is and which tables it writes, or the next agent has to diff it "
            f"against the others to find out"
        )


def test_the_spine_fragment_is_composed_first():
    """`core.json` is what a source fragment adds *to*, so it is composed
    first — which is also the order the conflict message reads in."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_blueprint import fragment_paths

    paths = fragment_paths(FRAGMENTS)
    assert paths[0].stem == "core"
    assert [p.stem for p in paths[1:]] == sorted(p.stem for p in paths[1:])


# --------------------------------------------------------------------------
# A key the loader does not read
# --------------------------------------------------------------------------


def _load_report(blueprint: dict, root: Path, tmp_path: Path, capfd) -> str:
    """Load ``blueprint`` against ``root`` and return the build report text.

    ``root`` may be empty: a node spec whose CSV is not there is an *error*
    line, not a raised exception, and the unknown-key scan runs at parse time
    regardless. That is what makes this a fast whole-fragment-set gate rather
    than something only a four-minute build can answer.

    ``capfd``, not ``capsys``: the report is written by the Rust extension
    straight to the process's file descriptors, so a Python-level redirect
    sees none of it and the gate would pass on an empty string.
    """
    kglite = pytest.importorskip("kglite")

    document = dict(blueprint)
    settings = {k: v for k, v in (document.get("settings") or {}).items()
                if k not in ("output", "output_path", "output_file")}
    settings["root"] = str(root)
    document["settings"] = settings
    document.pop("ontology", None)
    path = tmp_path / "blueprint.json"
    path.write_text(json.dumps(document))
    capfd.readouterr()
    kglite.from_blueprint(path, verbose=True, save=False)
    out, err = capfd.readouterr()
    return out + err


def test_no_fragment_declares_a_key_the_loader_does_not_read(tmp_path, capfd):
    """A misspelt key was dropped by the parser and the build reported success.

    kglite 0.16.22 reports it instead, with a near-miss suggestion — a
    `"lables"` costs every label it carries and used to say nothing. Composing
    the whole fragment set against an empty CSV root is enough to hear it, so
    this runs in milliseconds rather than behind a build.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_blueprint import compose

    report = _load_report(compose(FRAGMENTS), tmp_path / "empty", tmp_path, capfd)
    offending = [line for line in report.splitlines() if "unknown key" in line]
    assert not offending, (
        "a blueprint fragment declares a key the loader ignores:\n  "
        + "\n  ".join(offending)
    )


def test_the_unknown_key_gate_can_fail(tmp_path, capfd):
    """The same scan, over a fragment set with one typo, must see it.

    Without this the test above is green on any release that stops reporting
    unknown keys — which is exactly the silence it was added to end.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_blueprint import compose

    document = compose(FRAGMENTS)
    document["nodes"]["Taxon"]["lables"] = ["Organism"]
    report = _load_report(document, tmp_path / "empty", tmp_path, capfd)
    assert any("unknown key" in line and "lables" in line
               for line in report.splitlines()), (
        "the loader no longer reports an unknown blueprint key, so the gate "
        f"above cannot fail:\n{report}"
    )

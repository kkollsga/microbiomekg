"""``microbiomekg.tables`` — the in-memory tables, their merge semantics, and
the typing step that hands them to the loader as frames.

The 2026-09-04 whole-graph comparison found exactly two ways a frame differs
from the CSV the loader used to read: a string id column splits the id space
(every Taxon doubled), and a declared list column arrives as text (the
absent / ``[]`` / list distinction collapses). Both are asserted here, the
second end to end through ``from_blueprint(frames=)``.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from microbiomekg.tables import Frames, Table, as_list, declared_types, from_list

kglite = pytest.importorskip("kglite")


def test_key_dedupe_keeps_the_first_row_and_drops_an_empty_key():
    t = Table("x", ["id", "v"], key="id")
    assert t.add({"id": "1", "v": "a"})
    assert not t.add({"id": "1", "v": "b"})
    assert not t.add({"id": "", "v": "c"})
    assert t.rows == [{"id": "1", "v": "a"}]


def test_full_row_dedupe_keeps_parallel_rows_that_differ_anywhere():
    t = Table("e", ["a", "b", "rec"], dedupe_full=True)
    assert t.add({"a": "1", "b": "2", "rec": "s1"})
    assert not t.add({"a": "1", "b": "2", "rec": "s1"})
    assert t.add({"a": "1", "b": "2", "rec": "s2"})
    assert len(t) == 2


def test_sum_fields_accumulate_onto_the_winning_row():
    t = Table("ledger", ["k", "rows"], key="k", sum_fields=("rows",))
    t.add({"k": "c1", "rows": "3"})
    t.add({"k": "c1", "rows": "4"})
    assert t.rows == [{"k": "c1", "rows": "7"}]


def test_merge_unions_the_header_puts_existing_rows_first_and_replaces_own():
    """The re-run rule: a second run of one source replaces its own rows and
    leaves the other source's alone, in the other source's position."""
    store = Frames()
    a = store.table("paper", ["pmid", "title", "source"], key="pmid")
    a.add({"pmid": "1", "title": "A", "source": "s1"})
    a.add({"pmid": "2", "title": "B", "source": "s1"})
    store.put(a)
    b = store.table(
        "paper",
        ["pmid", "journal", "source"],
        key="pmid",
        merge=True,
        owner=("source", "s2"),
    )
    b.add({"pmid": "2", "journal": "J", "source": "s2"})  # loses to s1's row 2
    b.add({"pmid": "3", "journal": "K", "source": "s2"})
    store.put(b)
    assert b.fields == ["pmid", "journal", "source", "title"]
    assert [r["pmid"] for r in store.rows("paper")] == ["1", "2", "3"]
    assert store.rows("paper")[1] == {
        "pmid": "2",
        "journal": "",
        "source": "s1",
        "title": "B",
    }
    assert b.merged_in == 2 and b.replaced == 0
    # s2 runs again: its row 3 is dropped and rewritten, nothing doubles.
    c = store.table(
        "paper",
        ["pmid", "journal", "source"],
        key="pmid",
        merge=True,
        owner=("source", "s2"),
    )
    c.add({"pmid": "3", "journal": "K2", "source": "s2"})
    store.put(c)
    assert c.replaced == 1
    assert [(r["pmid"], r["journal"]) for r in store.rows("paper")] == [
        ("1", ""),
        ("2", ""),
        ("3", "K2"),
    ]


def test_as_list_and_from_list_keep_the_three_way_distinction():
    assert as_list([]) == "" and as_list(["a", "", None]) == '["a"]'
    assert from_list("") == [] and from_list('["a","b"]') == ["a", "b"]
    assert from_list("bare") == ["bare"]


def test_typed_infers_integer_ids_and_parses_declared_lists():
    store = Frames()
    t = store.table(
        "taxon", ["tax_id", "parent", "name", "synonyms", "n"], key="tax_id"
    )
    t.add({"tax_id": "1", "parent": "", "name": "root", "synonyms": "", "n": "0"})
    t.add(
        {
            "tax_id": "2",
            "parent": "1",
            "name": "x",
            "synonyms": as_list(["a", "b"]),
            "n": "2",
        }
    )
    t.add({"tax_id": "3", "parent": "1", "name": "y", "synonyms": "[]", "n": ""})
    store.put(t)
    frames = store.typed({"taxon": {"synonyms": "list", "n": "int"}})
    df = frames["taxon"]
    assert str(df["tax_id"].dtype) == "Int64" and str(df["parent"].dtype) == "Int64"
    assert df["parent"].isna().tolist() == [True, False, False]
    assert df["synonyms"].tolist()[0] is None
    assert df["synonyms"].tolist()[1] == ["a", "b"] and df["synonyms"].tolist()[2] == []
    assert str(df["n"].dtype) == "Int64" and df["n"].isna().tolist() == [
        False,
        False,
        True,
    ]
    assert df["name"].tolist() == ["root", "x", "y"]


def test_declared_types_reads_both_spellings():
    bp = {
        "nodes": {
            "T": {
                "csv": "taxon.csv",
                "properties": {"rank": "string", "synonyms": "list"},
                "connections": {
                    "junction_edges": {
                        "R": {
                            "file": "taxon_condition",
                            "properties": ["p"],
                            "property_types": {"p": "int"},
                        }
                    }
                },
            }
        }
    }
    assert declared_types(bp) == {
        "taxon": {"rank": "string", "synonyms": "list"},
        "taxon_condition": {"p": "int"},
    }


def test_the_three_way_distinction_survives_the_frame_path(tmp_path):
    """Absent is null, ``[]`` is a present empty list, a list is a list — the
    property CARD's 8,052 uncited edges depend on — through the real loader."""
    store = Frames()
    t = store.table("thing", ["id", "pubs"], key="id")
    t.add({"id": "1", "pubs": ""})
    t.add({"id": "2", "pubs": "[]"})
    t.add({"id": "3", "pubs": as_list(["PMID:1", "PMID:2"])})
    store.put(t)
    bp = {
        "settings": {"root": str(tmp_path)},
        "files": {"thing": {"format": "frame"}},
        "nodes": {
            "Thing": {"file": "thing", "pk": "id", "properties": {"pubs": "list"}}
        },
    }
    (tmp_path / "bp.json").write_text(json.dumps(bp))
    g = kglite.from_blueprint(
        tmp_path / "bp.json", frames=store.typed(declared_types(bp)), save=False
    )
    q = lambda c: list(g.cypher(c))  # noqa: E731
    assert q("MATCH (n:Thing) WHERE n.pubs IS NULL RETURN count(*) AS n")[0]["n"] == 1
    assert q("MATCH (n:Thing) WHERE n.pubs = [] RETURN count(*) AS n")[0]["n"] == 1
    assert q("MATCH (n:Thing {id: 3}) RETURN size(n.pubs) AS n")[0]["n"] == 2


def test_an_untyped_id_column_splits_the_id_space(tmp_path):
    """Why the digit rule exists: hand the same rows over with the id as text
    and the declared-int foreign key misses every node."""
    rows = pd.DataFrame(
        {"id": ["1", "2"], "parent": pd.array([None, 1], dtype="Int64")}
    )
    bp = {
        "settings": {"root": str(tmp_path)},
        "files": {"t": {"format": "frame"}},
        "nodes": {
            "T": {
                "file": "t",
                "pk": "id",
                "properties": {"parent": "int"},
                "connections": {"fk_edges": {"P": {"fk": "parent", "target": "T"}}},
            }
        },
    }
    (tmp_path / "bp.json").write_text(json.dumps(bp))
    g = kglite.from_blueprint(tmp_path / "bp.json", frames={"t": rows}, save=False)
    assert list(g.cypher("MATCH (n:T) RETURN count(*) AS n"))[0]["n"] > 2
    store = Frames()
    t = store.table("t", ["id", "parent"], key="id")
    t.add({"id": "1", "parent": ""})
    t.add({"id": "2", "parent": "1"})
    store.put(t)
    g = kglite.from_blueprint(
        tmp_path / "bp.json", frames=store.typed(declared_types(bp)), save=False
    )
    assert list(g.cypher("MATCH (n:T) RETURN count(*) AS n"))[0]["n"] == 2

"""``microbiomekg/pipeline.py``'s own machinery: prep order, the store, the report.

This is about the *build*, not about a source. Each thing it tests failed
silently before it was tested:

* preps ran in **name** order, so ``prep_chembl`` read gutMDisorder's
  ``intervention`` table before ``prep_gutmdisorder`` wrote it and the
  ``IS_DRUG`` relationship loaded zero edges — with its ontology rule
  reporting 0 / 0, the gate-that-cannot-fail this project treats as worse
  than no gate;
* the composed blueprint's paths were bound to the default directory, so a
  build into a temp directory loaded the default one and reported *its*
  numbers — now every input is a frame handed over by name, and the load
  blueprint carries no path at all;
* ``cited_taxa`` had no column saying which source wrote a row, so a prep
  re-run added its mention counts to its own previous ones;
* the G10 expansion factor covered three relationship names spelled out in a
  tuple, so every relationship a later source added was outside the report
  that exists to say what an edge count means.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import BUGSIGDB_MINI, MONDO_MINI, TAXDUMP_MINI
from microbiomekg import pipeline
from microbiomekg.tables import Frames

ROOT = Path(__file__).resolve().parents[1]
FRAGMENTS = ROOT / "microbiomekg" / "blueprints"
PREPS_DIR = ROOT / "microbiomekg" / "preps"


def names(preps: list[Path]) -> list[str]:
    return [p.stem.removeprefix("prep_") for p in preps]


def write_preps(directory: Path, declared: dict[str, list[str]]) -> None:
    """A directory of prep scripts that declare ``declared`` and nothing else."""
    for name, deps in declared.items():
        (directory / f"prep_{name}.py").write_text(
            f'"""A prep script that exists only to be ordered."""\n'
            f"DEPENDS_ON = {deps!r}\n",
            encoding="utf-8",
        )


def bugsigdb_into(store: Frames) -> dict[str, int]:
    from microbiomekg.preps import prep_bugsigdb

    return prep_bugsigdb.run(
        BUGSIGDB_MINI, store, taxdump=TAXDUMP_MINI, mondo=MONDO_MINI
    )


# --------------------------------------------------------------------------
# The declared order
# --------------------------------------------------------------------------


def test_every_prep_script_declares_its_dependencies():
    for script in sorted(PREPS_DIR.glob("prep_*.py")):
        deps = pipeline.declared_dependencies(script)
        assert isinstance(deps, tuple), script.name
        assert all(isinstance(d, str) for d in deps), script.name


def test_chembl_runs_after_the_source_whose_table_it_reads():
    """The bug that motivated declared order: ``IS_DRUG`` joins ChEMBL drugs to
    gutMDisorder interventions and read an ``intervention`` table that did not
    exist yet."""
    order = names(pipeline.order_preps(PREPS_DIR))
    assert order.index("gutmdisorder") < order.index("chembl")


def test_the_taxonomy_runs_after_every_source_that_writes_cited_taxa():
    """The taxonomy's ``cited`` scope is read from the table every source
    contributes to, so it goes last among the writers — and the declaration
    is checked against what the modules actually say."""
    writers = {
        script.stem.removeprefix("prep_")
        for script in PREPS_DIR.glob("prep_*.py")
        if "cited_taxa" in script.read_text(encoding="utf-8")
        and script.stem != "prep_taxonomy"
    }
    assert writers, "no prep writes cited_taxa — this test stopped measuring"
    declared = set(pipeline.declared_dependencies(PREPS_DIR / "prep_taxonomy.py"))
    assert writers <= declared, (
        f"prep_taxonomy.py's DEPENDS_ON is missing {sorted(writers - declared)}"
    )
    order = names(pipeline.order_preps(PREPS_DIR))
    assert all(order.index(w) < order.index("taxonomy") for w in writers)


def test_the_order_respects_every_declared_edge():
    order = names(pipeline.order_preps(PREPS_DIR))
    assert sorted(order) == sorted(
        p.stem.removeprefix("prep_") for p in PREPS_DIR.glob("prep_*.py")
    )
    for script in PREPS_DIR.glob("prep_*.py"):
        me = script.stem.removeprefix("prep_")
        for dep in pipeline.declared_dependencies(script):
            assert order.index(dep) < order.index(me), f"{dep} must precede {me}"


def test_the_order_is_deterministic_and_breaks_ties_by_name(tmp_path):
    write_preps(tmp_path, {"c": [], "a": [], "b": ["c"]})
    assert names(pipeline.order_preps(tmp_path)) == ["a", "c", "b"]
    assert names(pipeline.order_preps(tmp_path)) == names(
        pipeline.order_preps(tmp_path)
    )


def test_a_dependency_cycle_is_an_error_not_an_arbitrary_order(tmp_path):
    write_preps(tmp_path, {"a": ["b"], "b": ["c"], "c": ["a"]})
    with pytest.raises(SystemExit) as excinfo:
        pipeline.order_preps(tmp_path)
    assert "cycle" in str(excinfo.value)
    assert "a -> b -> c -> a" in str(excinfo.value)


def test_a_dependency_on_a_prep_that_does_not_exist_is_an_error(tmp_path):
    write_preps(tmp_path, {"a": ["ghost"]})
    with pytest.raises(SystemExit) as excinfo:
        pipeline.order_preps(tmp_path)
    assert "ghost" in str(excinfo.value)


def test_a_prep_without_the_declaration_is_an_error(tmp_path):
    (tmp_path / "prep_silent.py").write_text('"""no DEPENDS_ON"""\n')
    with pytest.raises(SystemExit) as excinfo:
        pipeline.order_preps(tmp_path)
    assert "prep_silent.py" in str(excinfo.value)
    assert "DEPENDS_ON" in str(excinfo.value)


def test_reading_the_declaration_does_not_import_the_module(tmp_path):
    """Importing a prep would run its imports (pandas, the taxdump reader) and
    any module-level side effect; the declaration is parsed off the source
    instead, so a prep that raises on import still orders correctly."""
    (tmp_path / "prep_loud.py").write_text(
        'DEPENDS_ON = ["quiet"]\nraise RuntimeError("imported")\n'
    )
    (tmp_path / "prep_quiet.py").write_text("DEPENDS_ON = []\n")
    assert names(pipeline.order_preps(tmp_path)) == ["quiet", "loud"]


# --------------------------------------------------------------------------
# The store, and the load blueprint bound to it
# --------------------------------------------------------------------------


def test_the_load_blueprint_declares_every_input_as_a_frame(tmp_path):
    """The composed blueprint says ``csv`` per spec and ``settings.root``
    points at a directory; the copy the build loads says ``file`` per spec
    with a ``files`` entry of format ``frame`` for each, no root, no output,
    and the ontology by absolute path — so what gets loaded is what the
    store holds, never a directory that happens to exist."""
    from microbiomekg.fragments import compose

    composed = compose(FRAGMENTS)
    store = Frames()
    bugsigdb_into(store)
    ontology = tmp_path / "ontology.json"
    loaded = pipeline.load_blueprint(composed, store, ontology)
    assert loaded["ontology"] == str(ontology)
    assert "root" not in loaded["settings"] and "output" not in loaded["settings"]
    text = json.dumps(loaded["nodes"])
    assert '"csv"' not in text
    assert loaded["nodes"]["Taxon"]["file"] == "taxon"
    assert loaded["files"]["taxon"] == {"format": "frame"}
    junction = loaded["nodes"]["Taxon"]["connections"]["junction_edges"][
        "ASSOCIATED_WITH"
    ]
    assert junction["file"] == "taxon_condition"
    assert set(loaded["files"]) >= {"taxon", "taxon_condition", "disease", "paper"}
    # The composed document is not mutated, and declares no root: there is no
    # directory a build reads, only the store.
    assert "root" not in composed.get("settings", {})
    assert set(composed["files"]) >= {"taxon", "taxon_condition", "disease", "paper"}


def test_a_build_from_the_fixture_reports_the_fixture(fixture_raw, capsys):
    """The end-to-end form: a build pointed at a 43-row fixture laid out as a
    raw root must report 43 signatures, one source loaded, and every other
    source skipped for its absent input."""
    result = pipeline.build(fixture_raw, scope="cited", save=False)
    out = capsys.readouterr().out
    assert result.graph is not None and result.report is not None
    assert result.loaded == ["bugsigdb"], result.loaded
    assert result.report.node_count("Signature") == 43
    assert "  Signature                    43" in out, out
    assert "taxon" in result.store and "signature" in result.store
    assert len(result.store.rows("signature")) == 43
    assert "hmdb" in result.skipped and "masi" in result.skipped


def test_re_running_a_prep_leaves_the_store_unchanged():
    """The shared tables are *merged into*, so a prep run twice must replace
    its own contribution rather than add to it. Every table but one did, by
    deduping on a key or on the whole row; ``cited_taxa`` accumulated
    ``n_signatures`` across runs instead, because it had no column saying which
    source wrote a row. A doubled count is invisible — the *set* of taxa is
    what the taxonomy build reads — so nothing downstream fails and the number
    is simply wrong."""
    store = Frames()
    bugsigdb_into(store)
    first = {
        name: (t.fields, [dict(r) for r in t.rows]) for name, t in store.tables.items()
    }
    assert "cited_taxa" in first
    bugsigdb_into(store)
    second = {
        name: (t.fields, [dict(r) for r in t.rows]) for name, t in store.tables.items()
    }
    assert sorted(second) == sorted(first)
    differing = sorted(name for name in first if first[name] != second[name])
    assert differing == [], f"a re-run changed {differing}"


def test_the_cited_taxa_table_says_which_source_claimed_each_taxon():
    """The column that makes the re-run safe is also the one that makes the
    table readable: a taxon two sources cite is two rows with two counts, not
    one row carrying a sum nobody can attribute."""
    store = Frames()
    bugsigdb_into(store)
    rows = store.rows("cited_taxa")
    assert rows, "cited_taxa is empty"
    assert {"tax_id", "source", "n_signatures"} <= set(rows[0])
    assert {row["source"] for row in rows} == {"bugsigdb"}


# --------------------------------------------------------------------------
# The expansion report covers every declared relationship
# --------------------------------------------------------------------------


def test_the_expansion_report_covers_every_declared_relationship():
    """Every relationship any fragment declares — junction and FK — has a row
    in G10's report, with the tables its records came from."""
    declared = pipeline.declared_relationships(FRAGMENTS)
    in_fragments: set[str] = set()
    for path in FRAGMENTS.glob("*.json"):
        for spec in json.loads(path.read_text()).get("nodes", {}).values():
            connections = spec.get("connections", {})
            in_fragments.update(connections.get("junction_edges", {}))
            in_fragments.update(connections.get("fk_edges", {}))
    assert in_fragments, "no fragment declares a relationship — vacuous"
    assert set(declared) == in_fragments
    for rel, spec in declared.items():
        assert spec.inputs, f"{rel} names no input table"
        assert spec.fragments, f"{rel} is declared by no fragment"


def test_every_input_a_fragment_names_is_a_table_the_store_holds(fixture_raw):
    """For every source a build loaded, every table its fragment reads is in
    the store — the rule `sources_with_tables` applies, checked the other
    way round after a real build."""
    result = pipeline.build(fixture_raw, scope="cited", save=False)
    assert result.loaded
    for source in ("core", *result.loaded):
        for name in pipeline.fragment_inputs(FRAGMENTS, source):
            if source == "core" and name not in result.store:
                continue  # the spine's absent tables are pruned, and reported
            assert name in result.store, f"{source} reads {name}, not in the store"


def test_a_licence_gated_source_is_not_reported_as_loaded_without_its_flag():
    """KEGG's fragment declares no table of its own — it writes rows into
    Reactome's ``pathway`` and ``metabolite_pathway`` — so "all my tables are
    present" was true of it in any build that ran Reactome, and a build once
    printed `kegg` under "sources loaded" while carrying none of it. The graph
    was right and the report was not, which for a licence gate is the part
    that matters."""
    import argparse

    args = argparse.Namespace(with_kegg=False)
    assert not pipeline.opted_into("kegg", args)
    store = Frames()
    for name in ("pathway", "metabolite_pathway"):
        store.put(store.table(name, ["id"]))
    assert "kegg" not in pipeline.sources_with_tables(
        FRAGMENTS,
        [
            s
            for s in ("reactome", "kegg")
            if s not in pipeline.LICENCE_GATED or pipeline.opted_into(s, args)
        ],
        store,
    )
    assert pipeline.opted_into("kegg", argparse.Namespace(with_kegg=True))
    assert pipeline.prep_options("kegg", "microbial", frozenset({"kegg"})) == {
        "opted_in": True
    }


def test_the_expansion_report_names_every_relationship_it_declared(fixture_raw, capsys):
    """A relationship the build loaded no edges for is a *line* in G10, not an
    absence — that is how ``IS_DRUG`` sat at zero unnoticed."""
    result = pipeline.build(fixture_raw, scope="cited", save=False)
    out = capsys.readouterr().out
    section = out.split("expansion factor")[1]
    for rel in pipeline.declared_relationships(FRAGMENTS, result.loaded):
        assert rel in section, f"{rel} is not in the G10 report"
    rows = {r["rel"] for r in result.report.expansion}
    assert rows == set(pipeline.declared_relationships(FRAGMENTS, result.loaded))


def test_the_report_prints_the_per_field_census(fixture_raw, capsys):
    """The audit's single percentage is not the number this project is about.

    A `required_properties` rule rolls a fourteen-field contract into one
    figure, and the per-field breakdown used to be a Cypher query somebody had
    to know to run — so the build reported "15.5% incomplete" and nothing said
    which field. `{by: 'property'}` is in the report now, and it prints the
    complete fields too, so a field at zero is stated rather than inferred.
    """
    pipeline.build(fixture_raw, scope="cited", save=False)
    out = capsys.readouterr().out
    section = out.split("per-field census")[1].split("expansion factor")[0]
    assert "ASSOCIATED_WITH.required_properties" in section
    for field in ("group_0_size", "study_design", "pmid"):
        assert field in section, f"{field} is not in the census"
    assert "(complete)" in section, (
        "a field nothing fails must appear at zero — a census that only lists "
        "failures cannot say a field is complete, which is half of what it is for"
    )


# --------------------------------------------------------------------------
# The vector lane is opt-in, and the default build must not carry it
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def both_builds(tmp_path_factory, fixture_raw) -> dict[str, tuple[Path, str]]:
    """The same fixture built twice: the default, and with the vector lane.

    One fixture rather than two tests each running a build, because the point
    is the *difference* between two graphs built from identical input — the
    only variable is the flag.
    """
    import contextlib
    import io

    out = tmp_path_factory.mktemp("vector-lane")
    built: dict[str, tuple[Path, str]] = {}
    for name, with_vectors in (("default", False), ("with_vectors", True)):
        kgl = out / f"{name}.kgl"
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            pipeline.build(
                fixture_raw,
                scope="cited",
                out=kgl,
                save=True,
                with_vectors=with_vectors,
            )
        assert kgl.is_file()
        built[name] = (kgl, buffer.getvalue())
    return built


def test_the_default_build_carries_the_bm25_lane_and_no_vectors(both_builds):
    """The default is BM25-only, and says so.

    The gate against the default drifting back: the vector lane costs +82.6 s
    of build, +165.9 MB of `.kgl` and +2.5 GB of serving RSS (2026-09-03
    capture) to buy query-time tolerance for a misspelt name — nothing the
    load-time reconciliation in `microbiomekg/reconcile.py` uses. A build that
    quietly re-acquired it would be paying all of that by accident.
    """
    kglite = pytest.importorskip("kglite")
    path, stdout = both_builds["default"]
    graph = kglite.load(str(path))

    assert graph.list_embeddings() == []
    for node_type, prop, _ef in pipeline.VECTOR_INDEXES:
        assert graph.embedding_dim(node_type, prop) is None, f"{node_type}.{prop}"
        assert not graph.has_vector_index(node_type, prop), f"{node_type}.{prop}"
    # The BM25 lane is not gated: five indexes for 276 ms and 14.3 MB.
    for node_type, prop in pipeline.TEXT_INDEXES:
        assert graph.has_text_index(node_type, prop), f"{node_type}.{prop}"

    # And the report says which flag turns the missing lane on, because the
    # absence is otherwise only discoverable by a query that fails.
    assert "vector indexes: skipped (--with-vectors opts in)" in stdout, stdout


def test_the_flagged_build_carries_both_lanes(both_builds):
    kglite = pytest.importorskip("kglite")
    path, stdout = both_builds["with_vectors"]
    graph = kglite.load(str(path))

    stores = {(s["node_type"], s["text_column"]) for s in graph.list_embeddings()}
    assert stores == {
        (node_type, prop) for node_type, prop, _ in pipeline.VECTOR_INDEXES
    }
    for node_type, prop, _ef in pipeline.VECTOR_INDEXES:
        assert graph.embedding_dim(node_type, prop) == 256, f"{node_type}.{prop}"
        assert graph.has_vector_index(node_type, prop), f"{node_type}.{prop}"
    for node_type, prop in pipeline.TEXT_INDEXES:
        assert graph.has_text_index(node_type, prop), f"{node_type}.{prop}"
    assert "vector indexes: skipped" not in stdout, stdout


def test_text_score_raises_on_the_default_graph_and_answers_on_the_flagged_one(
    both_builds,
):
    """The consequence a consumer meets, asserted rather than described.

    `text_score()` over a graph with no vector store does **not** score 0.0 —
    it raises, taking the whole query down, including a `score_fuse()` whose
    BM25 lane would have answered on its own. So a hybrid lookup has to ask
    `embedding_dim(...)` and route, not catch; that is what the MCP
    reconciliation skill must branch on and what `tests/test_semantic_lookup.py`
    skips on.
    """
    kglite = pytest.importorskip("kglite")
    from microbiomekg.embedder import CharGramEmbedder

    query = (
        "MATCH (t:Taxon) RETURN t.id AS id, "
        "text_score(t, 'scientific_name', $q) AS score ORDER BY score DESC LIMIT 1"
    )
    graphs = {}
    for name, (path, _stdout) in both_builds.items():
        graphs[name] = kglite.load(str(path))
        graphs[name].set_embedder(CharGramEmbedder())

    with pytest.raises(Exception) as excinfo:
        list(graphs["default"].cypher(query, params={"q": "Bacteroides frajilis"}))
    assert "embedding" in str(excinfo.value).lower(), excinfo.value

    rows = list(
        graphs["with_vectors"].cypher(query, params={"q": "Bacteroides frajilis"})
    )
    assert rows and rows[0]["score"] > 0.0, rows


# --------------------------------------------------------------------------
# Absent input is a skip for every prep, and a build with nothing in it
# succeeds and says so
# --------------------------------------------------------------------------

PREPS = sorted(PREPS_DIR.glob("prep_*.py"))
assert PREPS, "the prep glob found nothing — this parametrisation would be vacuous"


@pytest.mark.parametrize("prep", PREPS, ids=[p.stem for p in PREPS])
def test_every_prep_reports_an_absent_input_as_a_skip(tmp_path, prep):
    """The one channel the build reads as "skip this source": a converted prep
    raises ``MissingInput`` naming what it wanted; a prep not yet converted
    exits 3 (argparse's 2 would be read as fatal) and says so on stderr."""
    from microbiomekg.rawdata import MissingInput

    raw = tmp_path / "raw"
    raw.mkdir()
    name = prep.stem.removeprefix("prep_")
    module = importlib.import_module(f"microbiomekg.preps.{prep.stem}")
    if hasattr(module, "run"):
        with pytest.raises(MissingInput) as absent:
            module.run(
                raw, Frames(), **pipeline.prep_options(name, "microbial", frozenset())
            )
        assert str(absent.value).strip(), (
            f"{prep.name} said nothing about what it wanted"
        )
        return
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            f"microbiomekg.preps.{prep.stem}",
            "--raw",
            str(raw),
            "--out",
            str(tmp_path / "csv"),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == pipeline.MISSING_INPUT, (
        f"{prep.name} exited {proc.returncode}, not {pipeline.MISSING_INPUT}:\n"
        f"{proc.stderr}"
    )
    assert proc.stderr.strip(), f"{prep.name} said nothing about what it wanted"
    assert "usage:" not in proc.stderr, f"{prep.name} refused through argparse"


def test_a_prep_with_its_own_file_but_no_taxdump_is_a_skip(tmp_path):
    """The class, not the instance: nine preps check their own file before the
    taxdump, so an empty directory never reaches their taxdump lookup. With the
    source's own file present and no taxdump, the lookup is reached — and it
    must still be a skip naming the dump, not a usage error."""
    from microbiomekg.preps import prep_hmdb
    from microbiomekg.rawdata import MissingInput

    raw = tmp_path / "raw"
    (raw / "hmdb").mkdir(parents=True)
    (raw / "hmdb" / "hmdb_metabolites.xml").write_bytes(
        (
            ROOT / "tests" / "fixtures" / "hmdb_mini" / "hmdb_metabolites.xml"
        ).read_bytes()
    )
    with pytest.raises(MissingInput) as absent:
        prep_hmdb.run(raw, Frames())
    assert "nodes.dmp" in str(absent.value)


def test_a_build_with_nothing_in_it_succeeds_and_reports_every_source_absent(
    tmp_path, capsys
):
    """docs/design/library-pipeline.md rule 2: absent means skipped, loudly.
    An empty data directory is the fresh-clone state, and the build's answer
    to it is a to-do list, not a traceback — no graph file, and every source
    named as skipped."""
    raw = tmp_path / "raw"
    raw.mkdir()
    out = tmp_path / "graph" / "x.kgl"
    result = pipeline.build(raw, out=out, save=True)
    printed = capsys.readouterr().out
    assert result.graph is None and result.out is None
    assert not out.exists(), "a build that loaded nothing wrote a graph"
    for prep in PREPS:
        source = prep.stem.removeprefix("prep_")
        assert f"{source}: raw input absent" in printed, source
        assert source in result.skipped
    assert "nothing loaded" in printed
    assert "no graph written" in printed
    assert result.store.names() == []


def test_a_build_from_a_taxdump_alone_is_a_taxonomy_only_graph(tmp_path, capsys):
    """The taxdump fetches automatically, so "only the taxdump" is the first
    state a fresh clone reaches after ``fetch``. It builds — a Taxon spine and
    nothing else — and the report says that is what it is."""
    raw = tmp_path / "raw" / "ncbi"
    raw.mkdir(parents=True)
    for f in TAXDUMP_MINI.iterdir():
        (raw / f.name).write_bytes(f.read_bytes())
    result = pipeline.build(tmp_path / "raw", save=False)
    printed = capsys.readouterr().out
    assert result.taxonomy_only and result.loaded == []
    assert "taxonomy-only" in printed, printed
    assert result.report.node_count("Taxon") == 170
    assert result.report.node_count("Signature") == 0
    assert result.store.names() == ["taxon"]

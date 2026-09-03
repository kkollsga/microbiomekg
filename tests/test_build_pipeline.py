"""``scripts/build.py``'s own machinery: prep order, the CSV root, the report.

This is about the *build script*, not about a source. Each thing it tests
failed silently before it was tested:

* prep scripts ran in **name** order, so ``prep_chembl`` read gutMDisorder's
  ``intervention.csv`` before ``prep_gutmdisorder`` wrote it and the ``IS_DRUG``
  relationship loaded zero edges — with its ontology rule reporting 0 / 0, the
  gate-that-cannot-fail this project treats as worse than no gate;
* ``--csv`` was accepted and then ignored, because the composed blueprint's
  ``settings.root`` still said ``./data/csv`` — so a build into a temp
  directory loaded the default one and reported *its* numbers;
* ``cited_taxa.csv`` had no column saying which source wrote a row, so a prep
  re-run added its mention counts to its own previous ones;
* the G10 expansion factor covered three relationship names spelled out in a
  tuple, so every relationship a later source added was outside the report
  that exists to say what an edge count means.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import BUGSIGDB_MINI, MONDO_MINI, TAXDUMP_MINI

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FRAGMENTS = ROOT / "blueprints"

sys.path.insert(0, str(SCRIPTS))

build = pytest.importorskip("build", reason="scripts/build.py does not exist yet")


@pytest.fixture(scope="module")
def fixture_csvs(tmp_path_factory) -> Path:
    """A CSV directory built from the 43-row fixture, not from ``data/csv``."""
    csv_dir = tmp_path_factory.mktemp("fixture-csv")
    for script, extra in (
        (SCRIPTS / "prep_bugsigdb.py", ["--mondo", str(MONDO_MINI)]),
        (SCRIPTS / "prep_taxonomy.py", ["--scope", "cited",
                                        "--cited-from", str(csv_dir / "cited_taxa.csv")]),
    ):
        proc = subprocess.run(
            [sys.executable, str(script), "--raw", str(BUGSIGDB_MINI),
             "--taxdump", str(TAXDUMP_MINI), "--out", str(csv_dir), *extra],
            capture_output=True, text=True, cwd=ROOT,
        )
        assert proc.returncode == 0, f"{script.name}:\n{proc.stdout}\n{proc.stderr}"
    return csv_dir


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


# --------------------------------------------------------------------------
# The declared order
# --------------------------------------------------------------------------


def test_every_prep_script_declares_its_dependencies():
    """A prep with no ``DEPENDS_ON`` is a prep whose position in the build is
    an accident of its filename. The declaration is required rather than
    defaulted to empty, so adding a source forces the question to be answered."""
    for script in sorted(SCRIPTS.glob("prep_*.py")):
        assert isinstance(build.declared_dependencies(script), tuple), script.name


def test_chembl_runs_after_the_source_whose_table_it_reads():
    """``prep_chembl`` writes ``IS_DRUG`` by reading gutMDisorder's
    ``intervention.csv``. In name order it ran first, the table was not there,
    and the relationship loaded zero edges."""
    order = names(build.order_preps(SCRIPTS))
    assert order.index("gutmdisorder") < order.index("chembl")


def test_the_taxonomy_runs_after_every_source_that_writes_cited_taxa():
    """``prep_taxonomy`` filters the 3M-row taxonomy down to what the sources
    cite, so a source that writes ``cited_taxa.csv`` after it has its edges
    pointing at vivified stubs with no name and no lineage."""
    writers = {
        script.stem.removeprefix("prep_")
        for script in SCRIPTS.glob("prep_*.py")
        if "cited_taxa.csv" in script.read_text(encoding="utf-8")
        and script.name != "prep_taxonomy.py"
    }
    assert writers, "no prep writes cited_taxa.csv — this test stopped measuring"
    declared = set(build.declared_dependencies(SCRIPTS / "prep_taxonomy.py"))
    assert writers <= declared, (
        f"{sorted(writers - declared)} write cited_taxa.csv but prep_taxonomy "
        f"does not declare them, so the build may run the taxonomy first"
    )
    order = names(build.order_preps(SCRIPTS))
    assert all(order.index(w) < order.index("taxonomy") for w in writers)


def test_the_order_respects_every_declared_edge():
    order = names(build.order_preps(SCRIPTS))
    assert sorted(order) == sorted(
        p.stem.removeprefix("prep_") for p in SCRIPTS.glob("prep_*.py")
    )
    for script in SCRIPTS.glob("prep_*.py"):
        source = script.stem.removeprefix("prep_")
        for dep in build.declared_dependencies(script):
            assert order.index(dep) < order.index(source), f"{source} before {dep}"


def test_the_order_is_deterministic_and_breaks_ties_by_name(tmp_path):
    """Two preps with no relation between them have no *correct* order, so the
    build picks one and always picks the same one: a build whose output depends
    on dictionary iteration is not reproducible."""
    write_preps(tmp_path, {"zulu": [], "alpha": [], "mike": ["zulu"]})
    assert names(build.order_preps(tmp_path)) == ["alpha", "zulu", "mike"]
    assert names(build.order_preps(tmp_path)) == ["alpha", "zulu", "mike"]


def test_a_dependency_cycle_is_an_error_not_an_arbitrary_order(tmp_path):
    """Picking a winner would produce a build that half-works and never says
    which half."""
    write_preps(tmp_path, {"one": ["two"], "two": ["one"], "free": []})
    with pytest.raises(SystemExit) as excinfo:
        build.order_preps(tmp_path)
    assert "one" in str(excinfo.value) and "two" in str(excinfo.value)
    assert "free" not in str(excinfo.value)


def test_a_dependency_on_a_prep_that_does_not_exist_is_an_error(tmp_path):
    write_preps(tmp_path, {"one": ["ghost"]})
    with pytest.raises(SystemExit) as excinfo:
        build.order_preps(tmp_path)
    assert "ghost" in str(excinfo.value)


def test_a_prep_without_the_declaration_is_an_error(tmp_path):
    (tmp_path / "prep_silent.py").write_text("X = 1\n", encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        build.order_preps(tmp_path)
    assert "DEPENDS_ON" in str(excinfo.value)


def test_reading_the_declaration_does_not_import_the_module(tmp_path):
    """The declaration is read off the source, not by importing it: importing
    every prep to ask about its order would drag in pandas, the taxdump reader
    and each module's argument parser before the build has started."""
    (tmp_path / "prep_explosive.py").write_text(
        "DEPENDS_ON = ['a']\nraise RuntimeError('imported')\n", encoding="utf-8"
    )
    assert build.declared_dependencies(tmp_path / "prep_explosive.py") == ("a",)


# --------------------------------------------------------------------------
# --csv: the directory the build loads from
# --------------------------------------------------------------------------


def test_the_load_blueprint_binds_its_paths_to_this_builds_directories(tmp_path):
    """``--csv`` was accepted and ignored: the composed blueprint's
    ``settings.root`` stayed ``./data/csv``, so a build into a temp directory
    loaded the default one and reported the default build's numbers as if they
    were the temp build's."""
    composed = {
        "settings": {"root": "./data/csv", "output": "graph/x.kgl"},
        "ontology": "ontology.json",
        "nodes": {},
    }
    csv_dir = tmp_path / "elsewhere"
    csv_dir.mkdir()
    out = build.write_load_blueprint(
        composed, csv_dir, csv_dir / "ontology.json", tmp_path / "load.json"
    )
    loaded = json.loads(out.read_text())
    assert loaded["settings"]["root"] == str(csv_dir)
    assert loaded["ontology"] == str(csv_dir / "ontology.json")
    # Dropped, not rewritten: the build saves through `graph.save(--out)`, and a
    # relative output would resolve against the CSV directory.
    assert "output" not in loaded["settings"]
    # The composed document is not mutated: it is also what gets written to the
    # checked-in blueprint.json, where `./data/csv` is correct.
    assert composed["settings"]["root"] == "./data/csv"


def test_a_build_into_a_temp_csv_directory_loads_that_directory(tmp_path, fixture_csvs):
    """The end-to-end form, and the one that would have caught the bug: a build
    pointed at a 43-row fixture must report 43 signatures. Pointed at the
    default directory it reports 14,846, so the assertion cannot pass by
    accident on a machine that has the real CSVs."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "build.py"), "--skip-prep",
         "--csv", str(fixture_csvs), "--no-save"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "  Signature                    43" in proc.stdout, proc.stdout


# --------------------------------------------------------------------------
# Re-running one prep replaces its own rows
# --------------------------------------------------------------------------


def test_re_running_a_prep_leaves_the_csv_directory_unchanged(tmp_path):
    """The shared tables are *merged into*, so a prep run twice must replace
    its own contribution rather than add to it. Every table but one did, by
    deduping on a key or on the whole row; ``cited_taxa.csv`` accumulated
    ``n_signatures`` across runs instead, because it had no column saying which
    source wrote a row. A doubled count is invisible — the *set* of taxa is
    what the taxonomy build reads — so nothing downstream fails and the number
    is simply wrong."""
    def prep_once() -> dict[str, str]:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "prep_bugsigdb.py"),
             "--raw", str(BUGSIGDB_MINI), "--taxdump", str(TAXDUMP_MINI),
             "--mondo", str(MONDO_MINI), "--out", str(tmp_path)],
            capture_output=True, text=True, cwd=ROOT,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        return {p.name: p.read_text(encoding="utf-8")
                for p in sorted(tmp_path.glob("*.csv"))}

    first = prep_once()
    assert "cited_taxa.csv" in first
    second = prep_once()
    assert sorted(second) == sorted(first)
    differing = sorted(name for name in first if first[name] != second[name])
    assert differing == [], f"a re-run changed {differing}"


def test_the_cited_taxa_table_says_which_source_claimed_each_taxon(tmp_path):
    """The column that makes the re-run safe is also the one that makes the
    table readable: a taxon two sources cite is two rows with two counts, not
    one row carrying a sum nobody can attribute."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "prep_bugsigdb.py"),
         "--raw", str(BUGSIGDB_MINI), "--taxdump", str(TAXDUMP_MINI),
         "--mondo", str(MONDO_MINI), "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    with (tmp_path / "cited_taxa.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows, "cited_taxa.csv is empty"
    assert {"tax_id", "source", "n_signatures"} <= set(rows[0])
    assert {row["source"] for row in rows} == {"bugsigdb"}
    # One row per (taxon, source): the key the owner column completes.
    keys = [(row["tax_id"], row["source"]) for row in rows]
    assert len(set(keys)) == len(keys)


# --------------------------------------------------------------------------
# G10 — the expansion factor, over every relationship the fragments declare
# --------------------------------------------------------------------------


def test_the_expansion_report_covers_every_declared_relationship():
    """G10 is "edges per source record, published rather than assumed". The
    report named three relationships in a tuple, which was the whole graph when
    it was written and is a fifth of it now — so the number that says what an
    edge count means was missing for every relationship four later sources
    added, including the one that was loading zero edges."""
    declared = build.declared_relationships(FRAGMENTS)
    assert {"ASSOCIATED_WITH", "IN_CONDITION", "AT_BODY_SITE",
            "ABUNDANCE_CHANGED_BY", "IS_DRUG", "PRODUCES", "HAS_MECHANISM",
            "CARRIES_RESISTANCE_GENE", "CONFERS_RESISTANCE_TO", "IN_PATHWAY",
            "PART_OF_PATHWAY", "REPORTED_BY", "HAS_PARENT"} <= set(declared)
    for rel, spec in declared.items():
        assert spec.csvs, f"{rel} names no CSV to count records in"
        assert spec.fragments, f"{rel} is declared by no fragment"
    # One relationship name, two CSVs: a taxon mention that resolved and one
    # that did not are the same edge type from two tables, and a report keyed
    # on the name alone would count the rows of whichever it saw last.
    assert build.declared_relationships(FRAGMENTS)["REPORTED_BY"].csvs == (
        "taxon_signature.csv", "unresolved_taxon_signature.csv"
    )
    # An `fk_edges` relationship has no junction CSV of its own: its records
    # are the rows of the node table carrying the foreign key.
    assert declared["HAS_PARENT"].csvs == ("taxon.csv",)


def test_every_csv_a_fragment_names_is_one_the_report_can_count():
    """The report reads its record counts off the fragments, so a relationship
    whose CSV a fragment misnames would be reported as zero records rather than
    as an error."""
    csv_dir = ROOT / "data" / "csv"
    if not (csv_dir / "taxon_condition.csv").is_file():
        pytest.skip("no built CSVs — run scripts/build.py first")
    missing = sorted(
        name
        for spec in build.declared_relationships(FRAGMENTS).values()
        for name in spec.csvs
        if not (csv_dir / name).is_file()
    )
    assert missing == []


def test_the_record_count_is_rows_and_not_newlines(tmp_path):
    """G10's denominator was newlines, and six of these tables carry quoted ones.

    ``signature.csv`` is 14,846 rows and 15,820 newlines — a BugSigDB title
    with a line break in it — so the report printed
    ``PART_OF_STUDY 14,846 edges / 15,820 rows = 0.9x``: an FK edge expanding
    to *less* than one edge per row, which cannot happen and was the counter
    rather than the loader. Also `taxon_condition.csv` (49), `study.csv` (92),
    `drug_target.csv` (34), `taxon_intervention.csv` (35) and `paper.csv` (1).
    """
    path = tmp_path / "t.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "text"])
        writer.writerows(
            [(i, ["plain", "two\nlines", 'a "quoted" word', "a,b"][i % 4])
             for i in range(400)]
        )
    with path.open(encoding="utf-8", newline="") as fh:
        real = sum(1 for _ in csv.reader(fh)) - 1
    assert real == 400
    assert path.read_bytes().count(b"\n") - 1 > real, (
        "this fixture must contain quoted newlines or it measures nothing"
    )
    assert build.csv_rows(path) == real


def test_the_record_count_survives_a_chunk_boundary(tmp_path):
    """The scan is chunked at 1 MiB and the quote state has to cross it."""
    path = tmp_path / "big.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "text"])
        writer.writerows([(i, "pad " * 8 + "two\nlines") for i in range(40_000)])
    assert path.stat().st_size > (1 << 20), "smaller than one chunk: no boundary"
    with path.open(encoding="utf-8", newline="") as fh:
        assert build.csv_rows(path) == sum(1 for _ in csv.reader(fh)) - 1


def test_the_expansion_report_names_every_relationship_it_declared(
    tmp_path, fixture_csvs
):
    """The report is what publishes G10, so it is asserted from the build's own
    output rather than from the function behind it. A relationship the build
    loaded **zero** edges for gets a line too — that absence is the finding."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "build.py"), "--skip-prep",
         "--csv", str(fixture_csvs), "--no-save"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    section = proc.stdout.split("expansion factor (G10)")[1]
    for rel in ("ASSOCIATED_WITH", "IN_CONDITION", "REPORTED_BY",
                "HAS_PARENT", "PART_OF_STUDY", "PUBLISHED_AS", "AT_BODY_SITE"):
        assert rel in section, f"{rel} is declared and unreported"


# --------------------------------------------------------------------------
# The vector lane is opt-in, and the default build must not carry it
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def both_builds(tmp_path_factory, fixture_csvs) -> dict[str, tuple[Path, str]]:
    """The same fixture CSVs built twice: the default, and ``--with-vectors``.

    One fixture rather than two tests each running a build, because the point
    is the *difference* between two graphs built from identical input — the
    only variable is the flag.
    """
    out = tmp_path_factory.mktemp("vector-lane")
    built: dict[str, tuple[Path, str]] = {}
    for name, extra in (("default", []), ("with_vectors", ["--with-vectors"])):
        kgl = out / f"{name}.kgl"
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "build.py"), "--skip-prep",
             "--csv", str(fixture_csvs), "--out", str(kgl), *extra],
            capture_output=True, text=True, cwd=ROOT,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        built[name] = (kgl, proc.stdout)
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
    for node_type, prop, _ef in build.VECTOR_INDEXES:
        assert graph.embedding_dim(node_type, prop) is None, f"{node_type}.{prop}"
        assert not graph.has_vector_index(node_type, prop), f"{node_type}.{prop}"
    # The BM25 lane is not gated: five indexes for 276 ms and 14.3 MB.
    for node_type, prop in build.TEXT_INDEXES:
        assert graph.has_text_index(node_type, prop), f"{node_type}.{prop}"

    # And the report says which flag turns the missing lane on, because the
    # absence is otherwise only discoverable by a query that fails.
    assert "vector indexes: skipped (--with-vectors opts in)" in stdout, stdout


def test_the_flagged_build_carries_both_lanes(both_builds):
    kglite = pytest.importorskip("kglite")
    path, stdout = both_builds["with_vectors"]
    graph = kglite.load(str(path))

    stores = {(s["node_type"], s["text_column"]) for s in graph.list_embeddings()}
    assert stores == {(node_type, prop) for node_type, prop, _ in build.VECTOR_INDEXES}
    for node_type, prop, _ef in build.VECTOR_INDEXES:
        assert graph.embedding_dim(node_type, prop) == 256, f"{node_type}.{prop}"
        assert graph.has_vector_index(node_type, prop), f"{node_type}.{prop}"
    for node_type, prop in build.TEXT_INDEXES:
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

    rows = list(graphs["with_vectors"].cypher(query, params={"q": "Bacteroides frajilis"}))
    assert rows and rows[0]["score"] > 0.0, rows

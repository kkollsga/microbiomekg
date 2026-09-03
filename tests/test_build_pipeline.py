"""``scripts/build.py``'s own machinery: the order the prep scripts run in.

This is about the *build script*, not about a source. Prep scripts ran in
**name** order, so ``prep_chembl`` read gutMDisorder's ``intervention.csv``
before ``prep_gutmdisorder`` wrote it and the ``IS_DRUG`` relationship loaded
zero edges — with its ontology rule reporting 0 / 0, the gate-that-cannot-fail
this project treats as worse than no gate. The order is declared per prep and
sorted here instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS))

build = pytest.importorskip("build", reason="scripts/build.py does not exist yet")


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

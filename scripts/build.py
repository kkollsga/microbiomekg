#!/usr/bin/env python3
"""The whole build: raw files in, ``graph/microbiomekg.kgl`` and a report out.

Six steps, in this order and for these reasons:

1. **Prep each source.** Every ``scripts/prep_<source>.py`` writes flat CSVs
   into ``data/csv/``, sharing the tables it shares (``paper.csv``,
   ``disease.csv``, ``taxon_disease.csv``, …) with whoever else writes them —
   see :mod:`microbiomekg.tables`. The directory is emptied first, so the
   output is a function of the raw inputs and this order, not of what a
   previous run left behind. A **licence-gated** source (:data:`LICENCE_GATED`)
   is skipped unless its flag is passed — ``--with-kegg`` today.
2. **In declared dependency order.** A prep that reads a table another prep
   writes says so in its own ``DEPENDS_ON``, and :func:`order_preps`
   topologically sorts them (independent preps keep name order; a cycle is an
   error). Name order got this wrong twice over: ``prep_taxonomy`` reads the
   ``cited_taxa.csv`` every source contributes to, and ``prep_chembl`` reads
   gutMDisorder's ``intervention.csv`` — which sorts *after* it, so ``IS_DRUG``
   loaded zero edges and its ontology rule audited nothing.
3. **Compose the blueprint** from ``blueprints/*.json`` into ``blueprint.json``
   — the checked-in declaration, whose ``settings.root`` is the default
   ``./data/csv``. A ``blueprint.load.json`` beside the CSVs carries the same
   document with every path bound to *this* build's directories, so ``--csv``
   is what gets loaded rather than what gets ignored.
4. **Load** that copy, with ``KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE`` raised
   above the junction row count — see the note on that constant below. Not
   optional.
5. **Build the BM25 indexes** docs/model.md §6 lists.
6. **Report** node and edge counts, the ontology audit, the per-source
   expansion factor (G10), and save.

Run it with the repo's venv from the repo root::

    .venv/bin/python scripts/build.py --scope microbial
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

#: kglite's blueprint junction loader streams each junction CSV in 100,000-row
#: chunks and calls the connect path once per chunk; parallel edges are written
#: on the *first* call for a relationship type and deduplicated on every call
#: after it. ``taxon_disease.csv`` is ~100k rows of deliberately parallel edges
#: — the independent observations this graph exists to keep — so a default
#: build silently drops every repeat of a pair it saw in the first chunk, with
#: no warning and no error. Setting the chunk size above the row count restores
#: the exact count (verified both ways).
#:
#: This is a workaround for a kglite defect, not a tuning knob: the chunk
#: boundary changes the *result*, not just the memory profile. Remove it when
#: the fix ships.
JUNCTION_CHUNK_SIZE = "1000000"

#: docs/model.md §6. ``(node type, property)`` — the everyday lookup, the
#: reconciliation-by-old-name index, and the three free-text entry points.
#: ``Study.title`` is not indexed (identical to ``Paper.title``), nor is
#: ``BodySite.label`` (237 values: an exact match is better), nor any numeric
#: or CURIE field.
TEXT_INDEXES: tuple[tuple[str, str], ...] = (
    ("Taxon", "scientific_name"),
    ("Taxon", "synonyms"),
    ("Disease", "label"),
    ("Signature", "description"),
    ("Paper", "title"),
)


#: Exit code a prep script uses for "my raw input is not on this machine".
#: Distinct from a real failure so the build can go on without that source
#: rather than either dying or silently loading nothing.
MISSING_INPUT = 3

#: source -> the flag that opts into it. A licence-gated source is **off by
#: default** and its prep refuses to run without the flag, exiting
#: ``MISSING_INPUT`` — so it leaves the build by the same path an absent raw
#: file does, and no extra machinery is needed here. KEGG is the only one: it
#: is explicitly not a public database, so a graph carrying its content cannot
#: be published (docs/sources.md, "Redistribution"). The operator opts in; the
#: build never decides for them.
LICENCE_GATED: dict[str, str] = {"kegg": "--with-kegg"}


def run(script: Path, *args: str) -> int:
    print(f"\n=== {script.name} {' '.join(args)}", flush=True)
    proc = subprocess.run([sys.executable, str(script), *args], cwd=ROOT)
    if proc.returncode not in (0, MISSING_INPUT):
        raise SystemExit(f"{script.name} failed with exit code {proc.returncode}")
    return proc.returncode


def declared_dependencies(script: Path) -> tuple[str, ...]:
    """The ``DEPENDS_ON`` list a prep module declares, read off its source.

    Parsed rather than imported: asking eight prep modules about their order
    by importing them would run pandas, the taxdump reader and each module's
    argument parser before the build has done anything. The declaration is
    **required** — a prep with none would be positioned by its filename, which
    is the accident this replaced.
    """
    tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
    for node in tree.body:
        targets = (
            node.targets if isinstance(node, ast.Assign)
            else [node.target] if isinstance(node, ast.AnnAssign) and node.value
            else []
        )
        if any(isinstance(t, ast.Name) and t.id == "DEPENDS_ON" for t in targets):
            return tuple(ast.literal_eval(node.value))
    raise SystemExit(
        f"{script.name} declares no module-level DEPENDS_ON — every prep says "
        f"which other preps' tables it reads, even when the answer is []"
    )


def order_preps(scripts: Path) -> list[Path]:
    """Every ``prep_<source>.py``, ordered so a prep runs after what it reads.

    Discovered rather than listed: adding a source is adding a file, which is
    the same rule the blueprint fragments and the ontology package follow. What
    a file cannot say is *when* it has to run, and name order got that wrong in
    the one place it mattered — ``prep_chembl`` reads gutMDisorder's
    ``intervention.csv`` and sorts before it, so ``IS_DRUG`` loaded zero edges
    and its ontology rule audited nothing.

    Independent preps keep name order, so the build is reproducible; a cycle is
    a :class:`SystemExit`, because picking a winner produces a build that
    half-works and never says which half.
    """
    preps = {p.stem.removeprefix("prep_"): p for p in scripts.glob("prep_*.py")}
    deps = {name: set(declared_dependencies(p)) for name, p in preps.items()}
    unknown = sorted({d for ds in deps.values() for d in ds} - set(preps))
    if unknown:
        raise SystemExit(
            f"prep dependency on {', '.join(unknown)}, for which {scripts} has "
            f"no prep script"
        )

    ordered: list[Path] = []
    while deps:
        ready = sorted(name for name, need in deps.items() if not need & set(deps))
        if not ready:
            raise SystemExit(
                f"prep dependency cycle among {', '.join(sorted(deps))}"
            )
        for name in ready:
            ordered.append(preps[name])
            del deps[name]
    return ordered


def prep_arguments(source: str, args: argparse.Namespace) -> list[str]:
    """What a prep needs beyond ``--raw`` and ``--out``.

    Only the taxonomy has any: it emits a *scope* of the 3M-row dump rather
    than a source's rows, and the ``cited`` scope is read from the file every
    other prep contributes to.
    """
    if source != "taxonomy":
        return []
    return [
        "--scope", args.scope,
        "--cited-from", str(args.csv / "cited_taxa.csv"),
    ]


def clear_csv(csv_dir: Path) -> int:
    """Empty the CSV directory: shared tables are *merged into*, so a stale
    file from a source that no longer writes it would survive forever."""
    stale = sorted(csv_dir.glob("*.csv"))
    for path in stale:
        path.unlink()
    return len(stale)


def fragment_csvs(fragments: Path, source: str) -> set[str]:
    """Every CSV filename ``blueprints/<source>.json`` names, at any depth."""
    def walk(value) -> set[str]:
        if isinstance(value, dict):
            found = {value["csv"]} if isinstance(value.get("csv"), str) else set()
            return found.union(*(walk(v) for v in value.values()), set())
        if isinstance(value, list):
            return set().union(*(walk(v) for v in value), set())
        return set()

    return walk(json.loads((fragments / f"{source}.json").read_text(encoding="utf-8")))


def sources_with_tables(fragments: Path, sources: list[str], csv_dir: Path) -> list[str]:
    """The sources whose declared CSVs are all in ``csv_dir``.

    The same rule the prep loop's ``MISSING_INPUT`` branch applies, asked of
    the directory instead of the exit code — because ``--skip-prep`` runs no
    prep and so hears no exit code at all. A blueprint naming a CSV that is not
    there loads that node type as empty, and an ontology rule over an empty
    type reports 0 / 0: a gate that cannot fail, which this project treats as
    worse than no gate.
    """
    return [s for s in sources
            if all((csv_dir / name).is_file() for name in fragment_csvs(fragments, s))]


def write_load_blueprint(
    blueprint: dict, csv_dir: Path, ontology: Path, out: Path
) -> Path:
    """The composed blueprint, bound to the directories *this* build uses.

    ``blueprint.json`` is the declaration the fragments compose to, and its
    paths are written relative to the repo root: ``settings.root`` is
    ``./data/csv``. A build given ``--csv`` somewhere else used to load that
    file unchanged and silently report the **default** directory's graph, so a
    temp-directory build was indistinguishable from the real one until someone
    read its numbers. The copy this writes sits beside the CSVs it names and
    every path in it is absolute.

    ``settings.output`` is dropped rather than rewritten: the build saves
    through ``graph.save(--out)``, and a relative output here would resolve
    against the CSV directory and write the graph in among its inputs.
    """
    document = dict(blueprint)
    settings = {k: v for k, v in document.get("settings", {}).items()
                if k not in ("output", "output_path", "output_file")}
    settings["root"] = str(csv_dir)
    document["settings"] = settings
    document["ontology"] = str(ontology)
    out.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return out


def report(graph, sources: list[str]) -> None:
    def rows(query):
        return list(graph.cypher(query))

    print("\n--- nodes")
    for r in rows("MATCH (n) RETURN labels(n)[0] AS t, count(n) AS n ORDER BY n DESC"):
        print(f"  {r['t']:<20s} {r['n']:>10,}")
    print("\n--- edges")
    for r in rows("MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS n ORDER BY n DESC"):
        print(f"  {r['t']:<28s} {r['n']:>10,}")

    print("\n--- ontology_audit()")
    audit = rows(
        "CALL ontology_audit() YIELD rule, severity, violations, exempted, total, pct "
        "RETURN rule, severity, violations, exempted, total, pct ORDER BY pct DESC, rule"
    )
    for r in audit:
        if r["violations"] or r["severity"] == "error":
            print(
                f"  {r['rule']:<46s} {r['severity']:<6s} "
                f"{r['violations']:>8,} / {r['total']:>8,}  {r['pct']:>6.2f}%"
            )
    quiet = sum(1 for r in audit if not r["violations"] and r["severity"] != "error")
    print(f"  … {quiet} further rules at 0 violations")

    # G10: edges per source record, published rather than assumed. An
    # expansion factor is how a curated source turns into a big-looking graph,
    # and it is the number that says whether "N million edges" means anything.
    print("\n--- expansion factor (G10): association edges per source record")
    for rel in ("ASSOCIATED_WITH", "ASSOCIATED_WITH_PHENOTYPE", "ASSOCIATED_WITH_EXPOSURE"):
        for r in rows(
            f"MATCH ()-[r:{rel}]->() "
            "RETURN r.primary_source AS source, count(r) AS edges, "
            "count(DISTINCT r.source_record_id) AS records ORDER BY edges DESC"
        ):
            ratio = r["edges"] / r["records"] if r["records"] else 0.0
            print(
                f"  {rel:<28s} {str(r['source']):<14s} "
                f"{r['edges']:>8,} edges / {r['records']:>7,} records = {ratio:5.1f}x"
            )
    print(f"\nsources loaded: {', '.join(sources) or '(none detected)'}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", type=Path, default=ROOT / "data/raw")
    ap.add_argument("--csv", type=Path, default=ROOT / "data/csv")
    ap.add_argument("--scope", default="microbial", choices=("cited", "microbial", "all"))
    ap.add_argument("--out", type=Path, default=ROOT / "graph/microbiomekg.kgl")
    ap.add_argument(
        "--skip-prep",
        action="store_true",
        help="Load the CSVs already in --csv. For iterating on the blueprint or "
        "the ontology without re-reading 3M taxonomy rows.",
    )
    ap.add_argument("--no-save", action="store_true")
    for source, flag in LICENCE_GATED.items():
        ap.add_argument(
            flag, action="store_true",
            help=f"Include the {source} slice. Off by default: its licence "
                 f"forbids redistributing a graph that carries it.",
        )
    args = ap.parse_args(argv)

    scripts = ROOT / "scripts"
    preps = order_preps(scripts)
    sources = [
        p.stem.removeprefix("prep_") for p in preps if p.name != "prep_taxonomy.py"
    ]
    skipped: set[str] = set()

    if not args.skip_prep:
        args.csv.mkdir(parents=True, exist_ok=True)
        removed = clear_csv(args.csv)
        print(f"cleared {removed} CSV(s) from {args.csv}")
        for prep in preps:
            source = prep.stem.removeprefix("prep_")
            flag = LICENCE_GATED.get(source)
            opted_in = flag is not None and getattr(args, flag[2:].replace("-", "_"))
            gate = [flag] if opted_in else []
            code = run(
                prep, "--raw", str(args.raw), "--out", str(args.csv),
                *prep_arguments(source, args), *gate,
            )
            if code == MISSING_INPUT:
                print(f"    ... {source}: raw input absent or not opted into, "
                      f"skipping this source")
                skipped.add(source)

    # A source that did not run, and a source whose tables are not in --csv,
    # are left out of both declarations for the same reason: a blueprint naming
    # a CSV that is not there loads that node type as empty, and an ontology
    # rule over an empty type reports 0 / 0 — a gate that cannot fail, which
    # this project treats as worse than no gate.
    fragments = ROOT / "blueprints"
    loaded = sources_with_tables(
        fragments, [s for s in sources if s not in skipped], args.csv
    )

    from build_blueprint import compose

    # The checked-in artifact is the *whole* fragment set, always: it is a
    # function of `blueprints/` alone, `tests/test_fragments.py` gates it
    # against drift, and a build that happened to skip a source must not
    # rewrite it into a partial one. What varies per build is the copy loaded
    # below, which is not checked in.
    full = compose(fragments)
    (ROOT / "blueprint.json").write_text(
        json.dumps(full, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\n=== blueprint.json <- blueprints/ ({len(full.get('nodes', {}))} node types)")

    # Written where the load blueprint's `ontology` key points, so the
    # declarations are a build-time gate rather than a document — and written
    # into --csv for the same reason the blueprint copy is: a partial build
    # writing a partial ontology over the shared path would leave every later
    # full build gated on a subset of its own rules.
    from microbiomekg.ontology import ontology_for, write_json

    ontology = write_json(args.csv / "ontology.json", ontology_for(loaded))
    print(f"=== ontology -> {ontology}")

    os.environ["KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE"] = JUNCTION_CHUNK_SIZE
    import kglite

    blueprint = write_load_blueprint(
        compose(fragments, loaded) if loaded != sources else full,
        args.csv, ontology, args.csv / "blueprint.load.json",
    )
    print(f"\n=== from_blueprint (chunk size {JUNCTION_CHUNK_SIZE})", flush=True)
    print(f"    {blueprint} (root {args.csv})")
    t0 = time.time()
    graph = kglite.from_blueprint(blueprint, verbose=True, save=False)
    print(f"loaded in {time.time() - t0:.1f}s")

    print("\n--- text indexes")
    for node_type, prop in TEXT_INDEXES:
        stats = graph.build_text_index(node_type, prop)
        print(
            f"  {node_type}.{prop:<18s} {stats.get('indexed', 0):>9,} docs, "
            f"{stats.get('terms', 0):>8,} terms, {stats.get('skipped', 0):>5,} skipped"
        )

    report(graph, loaded)

    if not args.no_save:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        graph.save(str(args.out))
        print(f"\nsaved {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

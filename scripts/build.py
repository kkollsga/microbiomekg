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
2. **Taxonomy last.** ``prep_taxonomy.py`` reads ``cited_taxa.csv``, which
   every source contributes to, so it cannot run until they all have.
3. **Compose the blueprint** from ``blueprints/*.json``.
4. **Load**, with ``KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE`` raised above the
   junction row count — see the note on that constant below. Not optional.
5. **Build the BM25 indexes** docs/model.md §6 lists.
6. **Report** node and edge counts, the ontology audit, the per-source
   expansion factor (G10), and save.

Run it with the repo's venv from the repo root::

    .venv/bin/python scripts/build.py --scope microbial
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

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


def source_preps(scripts: Path) -> list[Path]:
    """Every ``prep_<source>.py`` except the taxonomy, in name order.

    Discovered rather than listed: adding a source is adding a file, which is
    the same rule the blueprint fragments and the ontology package follow.
    """
    return sorted(p for p in scripts.glob("prep_*.py") if p.name != "prep_taxonomy.py")


def clear_csv(csv_dir: Path) -> int:
    """Empty the CSV directory: shared tables are *merged into*, so a stale
    file from a source that no longer writes it would survive forever."""
    stale = sorted(csv_dir.glob("*.csv"))
    for path in stale:
        path.unlink()
    return len(stale)


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
    preps = source_preps(scripts)
    sources = [p.stem.removeprefix("prep_") for p in preps]
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
            if run(prep, "--raw", str(args.raw), "--out", str(args.csv), *gate) == MISSING_INPUT:
                print(f"    ... {source}: raw input absent or not opted into, "
                      f"skipping this source")
                skipped.add(source)
        run(
            scripts / "prep_taxonomy.py",
            "--raw", str(args.raw),
            "--out", str(args.csv),
            "--scope", args.scope,
            "--cited-from", str(args.csv / "cited_taxa.csv"),
        )

    # A skipped source is left out of both declarations. A blueprint naming a
    # CSV that is not there loads that node type as empty, and an ontology rule
    # over an empty type reports 0 / 0 — a gate that cannot fail, which this
    # project treats as worse than no gate.
    loaded = [s for s in sources if s not in skipped]
    partial = ["--sources", *loaded] if skipped else []
    run(scripts / "build_blueprint.py", *partial)

    # Written where the blueprint's `ontology` key points, so the declarations
    # are a build-time gate rather than a document.
    from microbiomekg.ontology import ontology_for, write_json

    document = ontology_for(loaded) if skipped else None
    print(f"\n=== ontology -> {write_json(ROOT / 'ontology.json', document)}")

    os.environ["KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE"] = JUNCTION_CHUNK_SIZE
    import kglite

    print(f"\n=== from_blueprint (chunk size {JUNCTION_CHUNK_SIZE})", flush=True)
    t0 = time.time()
    graph = kglite.from_blueprint(ROOT / "blueprint.json", verbose=True, save=False)
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

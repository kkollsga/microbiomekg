#!/usr/bin/env python3
"""The whole build: raw files in, ``graph/microbiomekg.kgl`` and a report out.

Six steps, in this order and for these reasons:

1. **Prep each source.** Every ``microbiomekg/preps/prep_<source>.py`` writes flat CSVs
   into ``data/csv/``, sharing the tables it shares (``paper.csv``,
   ``disease.csv``, ``taxon_condition.csv``, …) with whoever else writes them —
   see :mod:`microbiomekg.tables`. The directory is emptied first, so the
   output is a function of the raw inputs and this order, not of what a
   previous run left behind. A **licence-gated** source (:data:`LICENCE_GATED`)
   is skipped unless its flag is passed — ``--with-kegg`` today. A source whose
   raw input is absent exits ``MISSING_INPUT`` and is skipped the same way; if
   that leaves no ``taxon.csv`` at all, the build reports every skip, writes
   no graph, and exits 0 — an empty data directory is the fresh-clone state,
   not an error. A directory holding only the taxdump builds the Taxon spine
   and says "taxonomy-only".
2. **In declared dependency order.** A prep that reads a table another prep
   writes says so in its own ``DEPENDS_ON``, and :func:`order_preps`
   topologically sorts them (independent preps keep name order; a cycle is an
   error). Name order got this wrong twice over: ``prep_taxonomy`` reads the
   ``cited_taxa.csv`` every source contributes to, and ``prep_chembl`` reads
   gutMDisorder's ``intervention.csv`` — which sorts *after* it, so ``IS_DRUG``
   loaded zero edges and its ontology rule audited nothing.
3. **Compose the blueprint** from ``microbiomekg/blueprints/*.json`` into ``blueprint.json``
   — the checked-in declaration, whose ``settings.root`` is the default
   ``./data/csv``. A ``blueprint.load.json`` beside the CSVs carries the same
   document with every path bound to *this* build's directories, so ``--csv``
   is what gets loaded rather than what gets ignored.
4. **Load** that copy. Junction streaming is a memory bound and nothing
   more, as of kglite 0.16.22: until then the loader re-decided per chunk
   whether a connection type was new, so this build had to raise
   ``KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE`` above the junction row count or
   lose 7.7% of its association edges. ``tests/test_loader_contracts.py``
   holds the engine to it.
5. **Build the BM25 indexes** docs/model.md §6 lists. Unconditional — five
   indexes for 276 ms and 14.3 MB. The **vector** lane (§6b) is not: it is
   opt-in behind ``--with-vectors`` — the same shape of gate as ``--with-kegg``
   for a different reason, cost rather than licence — and the report says so
   when it was skipped.
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
from typing import NamedTuple

from microbiomekg.fragments import FRAGMENTS_DIR, compose
from microbiomekg.rawdata import MISSING_INPUT

#: The preps ship inside the package; each is run as ``-m microbiomekg.preps.<name>``.
PREPS_DIR = Path(__file__).resolve().parent / "preps"

#: docs/model.md §6. ``(node type, property)`` — the everyday lookup, the
#: reconciliation-by-old-name index, and the three free-text entry points.
#: Unconditional, unlike the vector lane below: all five together cost 276 ms
#: and 14.3 MB of ``.kgl`` (2026-09-03 capture, §4), which is not a cost worth
#: a flag.
#: ``Study.title`` is not indexed (identical to ``Paper.title``), nor is
#: ``BodySite.label`` (237 values: an exact match is better), nor any numeric
#: or CURIE field.
TEXT_INDEXES: tuple[tuple[str, str], ...] = (
    ("Taxon", "scientific_name"),
    # ``synonyms_text``, not ``synonyms``: the property is a native list since
    # the blueprint learned the type, and `build_text_index` refuses a
    # list-valued property. ``prep_taxonomy.py`` writes both from one source
    # list — the list is what a query reads, this is what BM25 reads.
    ("Taxon", "synonyms_text"),
    ("Disease", "label"),
    ("Signature", "description"),
    ("Paper", "title"),
)

#: docs/model.md §6b. ``(node type, property)`` — the vector lane, over the
#: same two identity columns the reconciliation queries hit. Written with
#: :class:`microbiomekg.embedder.CharGramEmbedder`: a deterministic character-
#: n-gram hasher, **not** a semantic model. It exists because the lookup this
#: graph needs is a misspelt name (``Clostridium dificile``), which BM25's
#: whole-token lane cannot reach and n-gram cosine can; and because a
#: downloaded model would make the build depend on the network.
#:
#: **Off by default — ``--with-vectors`` opts in.** What it buys is query-time
#: tolerance for a *misspelt* name; load-time reconciliation
#: (``microbiomekg/reconcile.py``) matches exactly, through synonyms, through
#: authority stripping and through merged-id remapping, and never touches a
#: vector. Measured 2026-09-03 at ``--scope microbial`` over all 864,110 taxon
#: names (bench/results/2026-09-03-ten-sources.md §3 and §4): 28.2 s to embed,
#: 54.4 s to build the HNSW index — 82.6 s in all — and ``.kgl`` 46.7 MB ->
#: 212.7 MB (+165.9 MB), load 1.03 s -> 2.41 s, serving RSS 1.2 GB -> 3.7 GB.
#: When the lane *is* built the store covers every taxon rather than the ~7,910
#: carrying an association edge: an operator who has opted into the cost wants
#: to resolve the name in front of them, which is routinely a taxon no edge in
#: this graph mentions.
#:
#: The third element is ``ef_search``, and on ``Taxon`` it is **not** the
#: kglite default. Hashed character n-grams are the "unclustered
#: high-dimensional" corpus kglite's semantic-search guide warns about, and at
#: the default ``ef_search=64`` the HNSW index misses badly rather than
#: approximately: ``Citrobacter frundii`` returned a top hit at cosine 0.428
#: while *Citrobacter freundii* sat at 0.808, unfound. It is silent — Cypher
#: pushes ``ORDER BY text_score(...) DESC LIMIT n`` into the index, so the
#: wrong answer arrives as an ordinary result set. At 512 all five of this
#: project's reconciliation fixtures agree with an exact scan, at 1-2 ms
#: against the exact scan's 21 ms. Measured 2026-09-03; see docs/model.md §8.
VECTOR_INDEXES: tuple[tuple[str, str, int], ...] = (
    ("Taxon", "scientific_name", 512),
    ("Disease", "label", 512),
)


#: source -> the flag that opts into it. A licence-gated source is **off by
#: default** and its prep refuses to run without the flag, exiting
#: ``MISSING_INPUT`` — so it leaves the build by the same path an absent raw
#: file does, and no extra machinery is needed here. KEGG is the only one: it
#: is explicitly not a public database, so a graph carrying its content cannot
#: be published (docs/sources.md, "Redistribution"). The operator opts in; the
#: build never decides for them.
LICENCE_GATED: dict[str, str] = {"kegg": "--with-kegg"}


def opted_into(source: str, args: argparse.Namespace) -> bool:
    """Was ``--with-<source>`` passed for a licence-gated source?"""
    flag = LICENCE_GATED.get(source)
    return flag is not None and bool(getattr(args, flag[2:].replace("-", "_")))


def run(script: Path, *args: str) -> int:
    """Run one prep as a subprocess and return its exit code.

    ``-m microbiomekg.preps.<name>`` rather than the file path, so the prep
    imports the package the same way whether it is installed or a checkout;
    the package's parent goes on ``PYTHONPATH`` for the checkout case.
    """
    print(f"\n=== {script.name} {' '.join(args)}", flush=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(PREPS_DIR.parent.parent)]
        + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    proc = subprocess.run(
        [sys.executable, "-m", f"microbiomekg.preps.{script.stem}", *args], env=env
    )
    if proc.returncode not in (0, MISSING_INPUT):
        raise SystemExit(f"{script.name} failed with exit code {proc.returncode}")
    return proc.returncode


def declared(script: Path, name: str) -> tuple[str, ...] | None:
    """A module-level ``name = [...]`` a prep declares, read off its source.

    Parsed rather than imported: asking twelve prep modules about themselves
    by importing them would run pandas, the taxdump reader and each module's
    argument parser before the build has done anything. ``None`` when the
    module has no such assignment.
    """
    tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
    for node in tree.body:
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target]
            if isinstance(node, ast.AnnAssign) and node.value
            else []
        )
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            return tuple(ast.literal_eval(node.value))
    return None


def declared_dependencies(script: Path) -> tuple[str, ...]:
    """The ``DEPENDS_ON`` list a prep declares. **Required** — a prep with
    none would be positioned by its filename, which is the accident this
    replaced."""
    deps = declared(script, "DEPENDS_ON")
    if deps is None:
        raise SystemExit(
            f"{script.name} declares no module-level DEPENDS_ON — every prep says "
            f"which other preps' tables it reads, even when the answer is []"
        )
    return deps


def declared_inputs(script: Path) -> tuple[str, ...]:
    """The ``RAW_INPUTS`` a prep declares: the files it reads under ``--raw``,
    as raw-relative paths, in the layout ``fetch`` writes. **Required** — it
    is what ``status`` reports on, so a prep without one is a source the
    operator cannot be told how to complete."""
    inputs = declared(script, "RAW_INPUTS")
    if inputs is None:
        raise SystemExit(
            f"{script.name} declares no module-level RAW_INPUTS — every prep names "
            f"the raw files it reads so `status` can say which are missing"
        )
    return inputs


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
            raise SystemExit(f"prep dependency cycle among {', '.join(sorted(deps))}")
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
        "--scope",
        args.scope,
        "--cited-from",
        str(args.csv / "cited_taxa.csv"),
    ]


def clear_csv(csv_dir: Path) -> int:
    """Empty the CSV directory: shared tables are *merged into*, so a stale
    file from a source that no longer writes it would survive forever."""
    stale = sorted(csv_dir.glob("*.csv"))
    for path in stale:
        path.unlink()
    return len(stale)


def fragment_csvs(fragments: Path, source: str) -> set[str]:
    """Every CSV filename ``microbiomekg/blueprints/<source>.json`` names, at any depth."""

    def walk(value) -> set[str]:
        if isinstance(value, dict):
            found = {value["csv"]} if isinstance(value.get("csv"), str) else set()
            return found.union(*(walk(v) for v in value.values()), set())
        if isinstance(value, list):
            return set().union(*(walk(v) for v in value), set())
        return set()

    return walk(json.loads((fragments / f"{source}.json").read_text(encoding="utf-8")))


def sources_with_tables(
    fragments: Path, sources: list[str], csv_dir: Path
) -> list[str]:
    """The sources whose declared CSVs are all in ``csv_dir``.

    The same rule the prep loop's ``MISSING_INPUT`` branch applies, asked of
    the directory instead of the exit code — because ``--skip-prep`` runs no
    prep and so hears no exit code at all. A blueprint naming a CSV that is not
    there loads that node type as empty, and an ontology rule over an empty
    type reports 0 / 0: a gate that cannot fail, which this project treats as
    worse than no gate.

    The rule is "all of my CSVs are here", and a source that declares only
    *shared* tables passes it whether or not it wrote a row. KEGG is exactly
    that — its fragment adds no key of its own, only `pathway.csv` and
    `metabolite_pathway.csv`, which Reactome writes — so a ``--skip-prep``
    build listed it under "sources loaded" while carrying none of it. Harmless
    to the graph and not harmless to say: the whole point of the licence gate
    is that a build states whether it carries KEGG. So a licence-gated source
    is included only when its flag was passed, which is the same answer the
    prep loop's exit code gives.
    """
    return [
        s
        for s in sources
        if all((csv_dir / name).is_file() for name in fragment_csvs(fragments, s))
    ]


#: One relationship as the fragments declare it: the CSVs whose rows the loader
#: read to make it, and the fragments that asked for it. Two fragments may
#: declare one name (``ASSOCIATED_WITH`` is core's shape and gutMDisorder's
#: extra columns) and one name may be backed by two tables (``REPORTED_BY``
#: loads from the resolved and the unresolved taxon mentions alike).
class Relationship(NamedTuple):
    name: str
    csvs: tuple[str, ...]
    fragments: tuple[str, ...]


def declared_relationships(
    fragments: Path, sources: list[str] | None = None
) -> dict[str, Relationship]:
    """Every relationship the fragments declare, junction and FK alike.

    Read off the fragments rather than listed here, for the reason the G10
    report exists: a list goes stale silently, and a relationship missing from
    the expansion table is exactly the one whose edge count nobody checked.
    A ``fk_edges`` relationship has no junction table — its records are the
    rows of the node CSV carrying the foreign key.

    ``sources`` narrows it the way :func:`microbiomekg.fragments.compose` does, so the
    report covers what *this* build declared: a line for a relationship no
    source in the build writes would be a zero that means nothing, and the
    zeros this report is for are the ones that mean something.
    """
    wanted = None if sources is None else {"core", *sources}
    declared_by: dict[str, list[str]] = {}
    for path in sorted(fragments.glob("*.json")):
        if wanted is not None and path.stem not in wanted:
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        for spec in document.get("nodes", {}).values():
            connections = spec.get("connections", {})
            for kind in ("junction_edges", "fk_edges"):
                for rel in connections.get(kind, {}):
                    declared_by.setdefault(rel, []).append(path.stem)

    csvs: dict[str, set[str]] = {}
    for spec in compose(fragments, sources).get("nodes", {}).values():
        connections = spec.get("connections", {})
        for rel, edge in connections.get("junction_edges", {}).items():
            csvs.setdefault(rel, set()).add(edge["csv"])
        for rel in connections.get("fk_edges", {}):
            if spec.get("csv"):
                csvs.setdefault(rel, set()).add(spec["csv"])

    return {
        rel: Relationship(
            rel, tuple(sorted(names)), tuple(dict.fromkeys(declared_by.get(rel, ())))
        )
        for rel, names in sorted(csvs.items())
    }


def csv_rows(path: Path) -> int:
    """Data rows in a CSV, or ``-1`` when it is not there.

    Counted in binary chunks rather than through :mod:`csv`, because
    ``taxon.csv`` is 128 MB and this runs for every declared relationship — but
    counting bare newlines over-counts, because six of these tables *do* carry
    quoted newlines: a BugSigDB title, a study abstract fragment, a MASI drug
    name. ``signature.csv`` is 14,846 rows and 15,820 newlines, and the G10
    report printed ``PART_OF_STUDY 14,846 edges / 15,820 rows = 0.9x`` — an
    expansion factor below one, which is not a thing an FK edge can do. The
    loader reads them correctly; only this counter did not.

    So the scan tracks whether it is inside a quoted field. RFC 4180 escapes a
    quote by doubling it, and a doubled quote toggles the state twice, which is
    the same as not toggling it — so no lookahead is needed.
    """
    if not path.is_file():
        return -1
    lines = 0
    outside = True
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            # Split on the quote character and count newlines in the segments
            # that are outside a quoted field — every count runs in C, so this
            # stays a streaming scan rather than a per-byte Python loop.
            for segment in chunk.split(b'"'):
                if outside:
                    lines += segment.count(b"\n")
                outside = not outside
            outside = not outside  # the split's last segment does not
    return max(lines - 1, 0)  # end at a quote


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
    settings = {
        k: v
        for k, v in document.get("settings", {}).items()
        if k not in ("output", "output_path", "output_file")
    }
    settings["root"] = str(csv_dir)
    document["settings"] = settings
    document["ontology"] = str(ontology)
    out.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return out


def prune_absent_tables(blueprint: dict, csv_dir: Path) -> tuple[dict, list[str]]:
    """Drop every node type and junction whose CSV is not in ``csv_dir``.

    ``sources_with_tables`` keeps a *source* out when its CSVs are missing, but
    the spine's tables — ``paper.csv``, ``disease.csv``, ``taxon_condition.csv``
    — are written by whichever sources ran, so a build that loaded no
    association source has a spine declaring node types with nothing behind
    them. The loader reads those as empty types and the index step then asks
    for a ``Disease`` that does not exist. Pruning keeps the rule the rest of
    the build runs on: no node type loaded empty, and no audit rule over one.
    Returns the pruned document and the dropped names, node types and
    junctions alike.
    """
    dropped: list[str] = []

    def keep(spec: dict) -> bool:
        csv_name = spec.get("csv")
        return not isinstance(csv_name, str) or (csv_dir / csv_name).is_file()

    nodes: dict = {}
    for name, spec in blueprint.get("nodes", {}).items():
        if not keep(spec):
            dropped.append(name)
            continue
        junctions = spec.get("connections", {}).get("junction_edges", {})
        gone = [j for j, jspec in junctions.items() if not keep(jspec)]
        if gone:
            dropped.extend(gone)
            spec = dict(spec)
            spec["connections"] = dict(spec["connections"])
            spec["connections"]["junction_edges"] = {
                j: v for j, v in junctions.items() if j not in gone
            }
        nodes[name] = spec
    if not dropped:
        return blueprint, []
    pruned = dict(blueprint)
    pruned["nodes"] = nodes
    return pruned, sorted(dropped)


def prune_ontology(ontology: dict, dropped: list[str]) -> dict:
    """The declaration without the classes and rules ``dropped`` emptied.

    A concrete class with no node type behind it is a loader warning; a rule
    whose domain, range or relationship was dropped audits ``0 / 0``. Both are
    the same defect a partial build's per-source pruning already prevents.
    """
    gone = set(dropped)
    classes = {
        name: spec
        for name, spec in ontology.get("classes", {}).items()
        if spec.get("abstract") or name not in gone
    }
    relationships = {
        name: spec
        for name, spec in ontology.get("relationships", {}).items()
        if name not in gone
        and spec.get("domain") not in gone
        and spec.get("range") not in gone
    }
    return {**ontology, "classes": classes, "relationships": relationships}


def report(graph, sources: list[str], fragments: Path, csv_dir: Path) -> None:
    def rows(query):
        return list(graph.cypher(query))

    print("\n--- nodes")
    for r in rows("MATCH (n) RETURN labels(n)[0] AS t, count(n) AS n ORDER BY n DESC"):
        print(f"  {r['t']:<20s} {r['n']:>10,}")
    print("\n--- edges")
    for r in rows(
        "MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS n ORDER BY n DESC"
    ):
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

    # The number the whole project rests on, per field rather than per edge.
    # A `required_properties` rule reports one percentage over a fourteen-field
    # contract, and a reader who takes it for "14% of the fields are missing"
    # is wrong in both directions: an edge missing three fields counts once,
    # and a field nothing fails is invisible. `by: 'property'` fans the rule
    # into one row per *declared* property, zero-violation rows included, so
    # "which fields are the gap" is an answer rather than an inference.
    #
    # It is a **census, not a partition**: an edge missing `group_0_size` and
    # `group_1_size` is counted under both, so these rows sum to more than the
    # aggregate above and adding them up is a mistake.
    print("\n--- per-field census (ontology_audit({by: 'property'}))")
    print("    One row per declared property, including the ones nothing fails.")
    print("    A census, not a partition: an edge missing three fields is in")
    print("    three rows, so these do not sum back to the rule's violations.")
    census = rows(
        "CALL ontology_audit({by: 'property'}) "
        "YIELD rule, property, violations, total, pct "
        "WHERE rule ENDS WITH '.required_properties' AND property IS NOT NULL "
        "RETURN rule, property, violations, total, pct "
        "ORDER BY rule, violations DESC, property"
    )
    for rule in dict.fromkeys(r["rule"] for r in census):
        fields = [r for r in census if r["rule"] == rule]
        if not any(r["violations"] for r in fields):
            continue
        print(f"  {rule}")
        for r in fields:
            complete = "" if r["violations"] else "   (complete)"
            print(
                f"    {r['property']:<24s} {r['violations']:>8,} / "
                f"{r['total']:>8,}  {r['pct']:>6.2f}%{complete}"
            )
    clean = [
        rule
        for rule in dict.fromkeys(r["rule"] for r in census)
        if not any(r["violations"] for r in census if r["rule"] == rule)
    ]
    print(
        f"  … {len(clean)} further required_properties rules with every field complete"
    )

    # G10: edges per source record, published rather than assumed. An
    # expansion factor is how a curated source turns into a big-looking graph,
    # and it is the number that says whether "N million edges" means anything.
    # Every relationship the fragments declare gets a line, including one the
    # build loaded no edges for — that absence is the finding, and it is how
    # `IS_DRUG` sat at zero through a release with its audit reporting 0 / 0.
    print("\n--- expansion factor (G10): edges per source record, for every")
    print("    relationship the fragments declare. `records` is the distinct")
    print("    source_record_id where the edge carries one, else the input rows")
    print("    of the CSV(s) it was loaded from, marked `rows`.")
    for rel, spec in declared_relationships(fragments, sources).items():
        if not any((csv_dir / name).is_file() for name in spec.csvs):
            # Not the zero-edge finding above: no source wrote this CSV, so
            # the loader was never asked for the relationship. A taxonomy-only
            # build has no `taxon_condition.csv`, and querying the type it
            # would have made only draws an unknown-type warning.
            print(f"  {rel:<28s} no CSV in this build ({', '.join(spec.csvs)})")
            continue
        rows_in = sum(max(csv_rows(csv_dir / name), 0) for name in spec.csvs)
        breakdown = rows(
            f"MATCH ()-[r:{rel}]->() "
            "RETURN r.primary_source AS source, count(r) AS edges, "
            "count(DISTINCT r.source_record_id) AS records ORDER BY edges DESC"
        )
        if not breakdown:
            print(
                f"  {rel:<28s} {'-':<14s} {0:>9,} edges / {rows_in:>9,} rows "
                f"— declared by {', '.join(spec.fragments)}, loaded nothing"
            )
            continue
        for r in breakdown:
            records, unit = (
                (r["records"], "records") if r["records"] else (rows_in, "rows")
            )
            ratio = r["edges"] / records if records else 0.0
            print(
                f"  {rel:<28s} {str(r['source'] or '-'):<14s} "
                f"{r['edges']:>9,} edges / {records:>9,} {unit:<7s} = {ratio:5.1f}x"
            )
    print(f"\nsources loaded: {', '.join(sources) or '(none detected)'}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", type=Path, default=Path("data/raw"))
    ap.add_argument("--csv", type=Path, default=Path("data/csv"))
    ap.add_argument(
        "--scope", default="microbial", choices=("cited", "microbial", "all")
    )
    ap.add_argument("--out", type=Path, default=Path("graph/microbiomekg.kgl"))
    ap.add_argument(
        "--skip-prep",
        action="store_true",
        help="Load the CSVs already in --csv. For iterating on the blueprint or "
        "the ontology without re-reading 3M taxonomy rows.",
    )
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument(
        "--with-vectors",
        action="store_true",
        help="Include the character-n-gram vector lane (VECTOR_INDEXES). Off by "
        "default: it serves query-time misspelling tolerance only, and "
        "costs +82.6 s of build, +165.9 MB of .kgl and +2.5 GB of "
        "serving RSS. Reconciliation at load time never uses it.",
    )
    for source, flag in LICENCE_GATED.items():
        ap.add_argument(
            flag,
            action="store_true",
            help=f"Include the {source} slice. Off by default: its licence "
            f"forbids redistributing a graph that carries it.",
        )
    args = ap.parse_args(argv)

    preps = order_preps(PREPS_DIR)
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
            gate = [LICENCE_GATED[source]] if opted_into(source, args) else []
            code = run(
                prep,
                "--raw",
                str(args.raw),
                "--out",
                str(args.csv),
                *prep_arguments(source, args),
                *gate,
            )
            if code == MISSING_INPUT:
                print(
                    f"    ... {source}: raw input absent or not opted into, "
                    f"skipping this source"
                )
                skipped.add(source)

    # Every prep needs the taxdump, so a build whose taxonomy prep skipped has
    # nothing at all — and an empty data directory is the fresh-clone state,
    # not an error. The answer to it is a to-do list: every source named as
    # skipped above, no graph written, exit 0. A graph file would have to be
    # either empty or stale, and both read as "built" to whoever opens it.
    if not (args.csv / "taxon.csv").is_file():
        print(
            f"\n=== nothing loaded: {len(skipped) or 'every'} source(s) skipped, "
            "no graph written"
        )
        print("    Each skipped source printed the file it wanted and where it")
        print("    comes from. `scripts/fetch.py` fills what it can; docs/sources.md")
        print("    has the rest.")
        return 0

    # A source that did not run, and a source whose tables are not in --csv,
    # are left out of both declarations for the same reason: a blueprint naming
    # a CSV that is not there loads that node type as empty, and an ontology
    # rule over an empty type reports 0 / 0 — a gate that cannot fail, which
    # this project treats as worse than no gate.
    fragments = FRAGMENTS_DIR
    loaded = sources_with_tables(
        fragments,
        [
            s
            for s in sources
            if s not in skipped and (s not in LICENCE_GATED or opted_into(s, args))
        ],
        args.csv,
    )

    # The checked-in `blueprint.json` is the *whole* fragment set and is not
    # written here: `make gate` composes it in `--check` mode, so a fragment
    # edit that was never composed cannot reach a commit, and a build that
    # happened to skip a source cannot rewrite it into a partial one. What
    # varies per build is the copy loaded below, beside the CSVs.
    full = compose(fragments)
    print(
        f"\n=== blueprint <- {fragments.name}/ ({len(full.get('nodes', {}))} node types)"
    )

    # Written where the load blueprint's `ontology` key points, so the
    # declarations are a build-time gate rather than a document — and written
    # into --csv for the same reason the blueprint copy is: a partial build
    # writing a partial ontology over the shared path would leave every later
    # full build gated on a subset of its own rules.
    from microbiomekg.ontology import ontology_for, write_json

    document, pruned = prune_absent_tables(
        compose(fragments, loaded) if loaded != sources else full, args.csv
    )
    if pruned:
        print(f"=== spine tables absent, dropped from the load: {', '.join(pruned)}")
    if not loaded:
        print("=== taxonomy-only build: no association source loaded")
    ontology = write_json(
        args.csv / "ontology.json", prune_ontology(ontology_for(loaded), pruned)
    )
    print(f"=== ontology -> {ontology}")

    import kglite

    blueprint = write_load_blueprint(
        document, args.csv, ontology, args.csv / "blueprint.load.json"
    )
    print("\n=== from_blueprint", flush=True)
    print(f"    {blueprint} (root {args.csv})")
    t0 = time.time()
    graph = kglite.from_blueprint(blueprint, verbose=True, save=False)
    print(f"loaded in {time.time() - t0:.1f}s")

    print("\n--- text indexes")
    present = set(graph.node_types)
    for node_type, prop in TEXT_INDEXES:
        if node_type not in present:
            print(f"  {node_type}.{prop:<18s} skipped: no {node_type} in this build")
            continue
        stats = graph.build_text_index(node_type, prop)
        print(
            f"  {node_type}.{prop:<18s} {stats.get('indexed', 0):>9,} docs, "
            f"{stats.get('terms', 0):>8,} terms, {stats.get('skipped', 0):>5,} skipped"
        )

    if args.with_vectors:
        # After the BM25 pass, because the two lanes index the same columns and
        # a `score_fuse` query needs both present; before `report`, so the audit
        # and the save see one finished graph.
        from microbiomekg.embedder import CharGramEmbedder

        print("\n--- vector indexes (character-n-gram, see microbiomekg/embedder.py)")
        graph.set_embedder(CharGramEmbedder())
        for node_type, prop, ef_search in VECTOR_INDEXES:
            t0 = time.time()
            stats = graph.embed_texts(node_type, prop, show_progress=False)
            t_embed = time.time() - t0
            t0 = time.time()
            index = graph.build_vector_index(node_type, prop, ef_search=ef_search)
            print(
                f"  {node_type}.{prop:<18s} {stats.get('embedded', 0):>9,} vectors, "
                f"dim {stats.get('dimension', 0)}, {stats.get('skipped', 0):>5,} skipped, "
                f"embed {t_embed:.1f}s, hnsw {time.time() - t0:.1f}s "
                f"({index.get('indexed', 0):,} indexed)"
            )
    else:
        # Named in the report rather than merely absent from it: on the graph a
        # default build produces, `text_score()` *raises* — "vector_score(): no
        # embedding 'scientific_name_emb' found for node type 'Taxon'" — so a
        # consumer who did not know the lane was skipped meets a failed query
        # rather than a missing feature. The costs are the 2026-09-03 capture's
        # (bench/results/2026-09-03-ten-sources.md §3, §4).
        print("\n--- vector indexes: skipped (--with-vectors opts in)")
        print(
            "    Query-time misspelling tolerance only — reconciliation at "
            "load time uses exact names,"
        )
        print(
            "    synonyms and authority stripping, and never touches vectors. "
            "Enabling it costs"
        )
        print(
            "    +82.6 s of build (28.2 s embed + 54.4 s HNSW), .kgl 46.7 MB "
            "-> 212.7 MB (+165.9 MB),"
        )
        print("    load 1.03 s -> 2.41 s and serving RSS 1.2 GB -> 3.7 GB.")

    report(graph, loaded, fragments, args.csv)

    if not args.no_save:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        graph.save(str(args.out))
        print(f"\nsaved {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""The whole build: raw files in, ``graph/microbiomekg.kgl`` and a report out.

Six steps, in this order and for these reasons:

1. **Prep each source, in memory.** Every ``microbiomekg/preps/prep_<source>.py``
   is a module whose ``run(raw, store, ...)`` puts its tables into one
   :class:`microbiomekg.tables.Frames` store, sharing the tables it shares
   (``paper``, ``disease``, ``taxon_condition``, …) with whoever else writes
   them — see :mod:`microbiomekg.tables`. A build starts from an empty store,
   so its graph is a function of the raw inputs and this order, not of what
   a previous run left behind. A **licence-gated** source (:data:`LICENCE_GATED`)
   is skipped unless its flag is passed — ``--with-kegg`` today. A source
   whose raw input is absent raises :class:`~microbiomekg.rawdata.MissingInput`
   and is skipped the same way; if that leaves no ``taxon`` table at all, the
   build reports every skip, writes no graph, and exits 0 — an empty data
   directory is the fresh-clone state, not an error. A directory holding only
   the taxdump builds the Taxon spine and says "taxonomy-only".
2. **In declared dependency order.** A prep that reads a table another prep
   writes says so in its own ``DEPENDS_ON``, and :func:`order_preps`
   topologically sorts them (independent preps keep name order; a cycle is an
   error). Name order got this wrong twice over: ``prep_taxonomy`` reads the
   ``cited_taxa`` table every source contributes to, and ``prep_chembl`` reads
   gutMDisorder's ``intervention`` — which sorts *after* it, so ``IS_DRUG``
   loaded zero edges and its ontology rule audited nothing.
3. **Compose the blueprint** from ``microbiomekg/blueprints/*.json``. The
   copy this build loads declares every table the store holds as a ``files``
   entry of ``{"format": "frame"}``, and is written to a temporary directory
   only because the engine reads a blueprint by path.
4. **Load** it with ``frames=``: the store's tables, typed once for the
   loader (:meth:`microbiomekg.tables.Frames.typed`). Junction streaming is a
   memory bound and nothing more, as of kglite 0.16.22: until then the loader
   re-decided per chunk whether a connection type was new, so this build had
   to raise ``KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE`` above the junction row
   count or lose 7.7% of its association edges.
   ``tests/test_loader_contracts.py`` holds the engine to it.
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
import csv
import importlib
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from microbiomekg.fragments import FRAGMENTS_DIR, compose
from microbiomekg.rawdata import MISSING_INPUT, MissingInput
from microbiomekg.tables import Frames, Table, declared_types

#: The preps ship inside the package; one module per source.
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
#: default** and its prep refuses to run without the flag, raising
#: :class:`MissingInput` — so it leaves the build by the same path an absent
#: raw file does, and no extra machinery is needed here. KEGG is the only one:
#: it is explicitly not a public database, so a graph carrying its content
#: cannot be published (docs/sources.md, "Redistribution"). The operator opts
#: in; the build never decides for them.
LICENCE_GATED: dict[str, str] = {"kegg": "--with-kegg"}


def opted_into(source: str, args: argparse.Namespace) -> bool:
    """Was ``--with-<source>`` passed for a licence-gated source?"""
    flag = LICENCE_GATED.get(source)
    return flag is not None and bool(getattr(args, flag[2:].replace("-", "_")))


# ---------------------------------------------------------------------------
# The preps: declared order, declared inputs, and running one
# ---------------------------------------------------------------------------


def declared(script: Path, name: str) -> tuple[str, ...] | None:
    """A module-level ``name = [...]`` a prep declares, read off its source.

    Parsed rather than imported: asking twelve prep modules about themselves
    by importing them would run pandas, the taxdump reader and each module's
    imports before the build has done anything. ``None`` when the module has
    no such assignment.
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
    """The ``RAW_INPUTS`` a prep declares: the files it reads under the raw
    root, as raw-relative paths, in the layout ``fetch`` writes. **Required**
    — it is what ``status`` reports on, so a prep without one is a source the
    operator cannot be told how to complete."""
    inputs = declared(script, "RAW_INPUTS")
    if inputs is None:
        raise SystemExit(
            f"{script.name} declares no module-level RAW_INPUTS — every prep names "
            f"the raw files it reads so `status` can say which are missing"
        )
    return inputs


def order_preps(scripts: Path) -> list[Path]:
    """Every ``prep_*.py`` under ``scripts``, in an order that satisfies each
    one's ``DEPENDS_ON``.

    Topological, ties broken by name so the order is stable across machines,
    and a cycle is an error rather than an arbitrary choice: a build whose
    order silently changed is a build whose shared tables silently changed.
    """
    preps = {p.stem.removeprefix("prep_"): p for p in sorted(scripts.glob("prep_*.py"))}
    deps = {name: declared_dependencies(path) for name, path in preps.items()}
    for name, wanted in deps.items():
        unknown = [d for d in wanted if d not in preps]
        if unknown:
            raise SystemExit(
                f"prep_{name}.py depends on {unknown}, which no prep_*.py provides"
            )
    ordered: list[str] = []
    state: dict[str, int] = {}

    def visit(name: str, trail: tuple[str, ...]) -> None:
        if state.get(name) == 2:
            return
        if state.get(name) == 1:
            cycle = " -> ".join((*trail[trail.index(name) :], name))
            raise SystemExit(f"prep dependency cycle: {cycle}")
        state[name] = 1
        for dep in sorted(deps[name]):
            visit(dep, (*trail, name))
        state[name] = 2
        ordered.append(name)

    for name in sorted(preps):
        visit(name, ())
    return [preps[name] for name in ordered]


def prep_module(name: str):
    return importlib.import_module(f"microbiomekg.preps.prep_{name}")


def prep_options(source: str, scope: str, gates: frozenset[str]) -> dict:
    """What a prep's ``run`` takes beyond ``raw`` and the store.

    The taxonomy takes the *scope* of the 3M-row dump; a licence-gated source
    takes whether it was opted into.
    """
    if source == "taxonomy":
        return {"scope": scope}
    if source in LICENCE_GATED:
        return {"opted_in": source in gates}
    return {}


def run_prep(
    source: str, raw: Path, store: Frames, *, scope: str, gates: frozenset[str]
) -> bool:
    """Run one source's prep into ``store``; ``False`` when it was skipped.

    A converted prep is a function call. A prep not yet converted still runs
    as a subprocess writing CSVs (:func:`run_prep_via_csv`), and its tables
    are read into the store afterwards — the transitional path, deleted with
    the last conversion.
    """
    print(f"\n=== prep_{source}", flush=True)
    module = prep_module(source)
    if not hasattr(module, "run"):
        return run_prep_via_csv(source, raw, store, scope=scope, gates=gates)
    try:
        module.run(raw, store, **prep_options(source, scope, gates))
    except MissingInput as absent:
        print(str(absent), file=sys.stderr)
        print(
            f"    ... {source}: raw input absent or not opted into, skipping this source"
        )
        return False
    return True


def run_prep_via_csv(
    source: str, raw: Path, store: Frames, *, scope: str, gates: frozenset[str]
) -> bool:
    """Transitional: a prep that still writes CSVs runs as a subprocess against
    a scratch directory mirroring the store, and what it wrote is read back.

    The mirror is written before the run because such a prep reads other
    preps' tables from its ``--out`` directory, and read back whole after it
    because it may have merged into any of them.
    """
    with tempfile.TemporaryDirectory(prefix=f"microbiomekg-{source}-") as scratch:
        csv_dir = Path(scratch)
        export_csv(store, csv_dir)
        args = ["--raw", str(raw), "--out", str(csv_dir)]
        if source == "taxonomy":
            args += ["--scope", scope, "--cited-from", str(csv_dir / "cited_taxa.csv")]
        if source in gates:
            args.append(LICENCE_GATED[source])
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(PREPS_DIR.parent.parent)]
            + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
        )
        proc = subprocess.run(
            [sys.executable, "-m", f"microbiomekg.preps.prep_{source}", *args], env=env
        )
        if proc.returncode == MISSING_INPUT:
            print(
                f"    ... {source}: raw input absent or not opted into, "
                f"skipping this source"
            )
            return False
        if proc.returncode != 0:
            raise SystemExit(f"prep_{source} failed with exit code {proc.returncode}")
        ingest_csv(store, csv_dir)
    return True


def export_csv(store: Frames, csv_dir: Path) -> None:
    """Transitional: every table in ``store`` as a CSV in ``csv_dir``."""
    for name, table in store.tables.items():
        with (csv_dir / f"{name}.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=table.fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(table.rows)


def ingest_csv(store: Frames, csv_dir: Path) -> None:
    """Transitional: every CSV in ``csv_dir`` replaces the store's table."""
    for path in sorted(csv_dir.glob("*.csv")):
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            table = Table(path.stem, list(reader.fieldnames or ()))
            table.rows = [
                {f: (row.get(f) or "") for f in table.fields} for row in reader
            ]
        store.put(table)


# ---------------------------------------------------------------------------
# What the fragments declare, against what the store holds
# ---------------------------------------------------------------------------


def input_name(spec: dict) -> str | None:
    """The store table a spec reads: its ``file``, or its ``csv``'s stem."""
    if isinstance(spec.get("file"), str):
        return spec["file"]
    if isinstance(spec.get("csv"), str):
        return Path(spec["csv"]).stem
    return None


def fragment_inputs(fragments: Path, source: str) -> set[str]:
    """Every table ``microbiomekg/blueprints/<source>.json`` reads, at any depth."""

    def walk(value) -> set[str]:
        if isinstance(value, dict):
            name = input_name(value)
            found = {name} if name else set()
            return found.union(*(walk(v) for v in value.values()), set())
        if isinstance(value, list):
            return set().union(*(walk(v) for v in value), set())
        return set()

    return walk(json.loads((fragments / f"{source}.json").read_text(encoding="utf-8")))


def sources_with_tables(
    fragments: Path, sources: list[str], store: Frames
) -> list[str]:
    """The sources whose declared tables are all in ``store``.

    The same rule the prep loop's skip applies, asked of the store instead of
    the exception — a blueprint naming a table that is not there loads that
    node type as empty, and an ontology rule over an empty type reports
    0 / 0: a gate that cannot fail, which this project treats as worse than
    no gate.

    The rule is "all of my tables are here", and a source that declares only
    *shared* tables passes it whether or not it wrote a row. KEGG is exactly
    that — its fragment adds no key of its own, only ``pathway`` and
    ``metabolite_pathway``, which Reactome writes — so a build that skipped
    it would have listed it under "sources loaded" while carrying none of it.
    The whole point of the licence gate is that a build states whether it
    carries KEGG, so a licence-gated source is included only when its prep
    ran, which is the same answer the skip gives.
    """
    return [
        s
        for s in sources
        if all(name in store for name in fragment_inputs(fragments, s))
    ]


class Relationship(NamedTuple):
    name: str
    inputs: tuple[str, ...]
    fragments: tuple[str, ...]


def declared_relationships(
    fragments: Path, sources: list[str] | None = None
) -> dict[str, Relationship]:
    """Every relationship the fragments declare, junction and FK alike.

    Read off the fragments rather than listed here, for the reason the G10
    report exists: a list goes stale silently, and a relationship missing from
    the expansion table is exactly the one whose edge count nobody checked.
    A ``fk_edges`` relationship has no junction table — its records are the
    rows of the node table carrying the foreign key.

    ``sources`` narrows it the way :func:`microbiomekg.fragments.compose` does,
    so the report covers what *this* build declared: a line for a relationship
    no source in the build writes would be a zero that means nothing, and the
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

    inputs: dict[str, set[str]] = {}
    for spec in compose(fragments, sources).get("nodes", {}).values():
        connections = spec.get("connections", {})
        for rel, edge in connections.get("junction_edges", {}).items():
            name = input_name(edge)
            if name:
                inputs.setdefault(rel, set()).add(name)
        for rel in connections.get("fk_edges", {}):
            name = input_name(spec)
            if name:
                inputs.setdefault(rel, set()).add(name)

    return {
        rel: Relationship(
            rel, tuple(sorted(names)), tuple(dict.fromkeys(declared_by.get(rel, ())))
        )
        for rel, names in sorted(inputs.items())
    }


def load_blueprint(blueprint: dict, store: Frames, ontology: Path) -> dict:
    """The composed blueprint, bound to *this* build's store.

    Every spec's input becomes a ``file`` reference to a ``files`` entry of
    ``{"format": "frame"}`` — the older ``csv`` spelling is rewritten on the
    way, so a fragment not yet converted loads the same. ``settings.output``
    is dropped rather than rewritten: the build saves through
    ``graph.save(--out)``. The ontology document is named by absolute path.
    """
    document = json.loads(json.dumps(blueprint))
    files: dict[str, dict] = dict(document.get("files", {}))

    def rewrite(value) -> None:
        if isinstance(value, dict):
            name = input_name(value)
            if name is not None:
                value.pop("csv", None)
                value["file"] = name
                files.setdefault(name, {"format": "frame"})
            for v in value.values():
                rewrite(v)
        elif isinstance(value, list):
            for v in value:
                rewrite(v)

    rewrite(document.get("nodes", {}))
    document["files"] = files
    settings = {
        k: v
        for k, v in document.get("settings", {}).items()
        if k not in ("output", "output_path", "output_file", "root")
    }
    document["settings"] = settings
    document["ontology"] = str(ontology)
    return document


def prune_absent_tables(blueprint: dict, store: Frames) -> tuple[dict, list[str]]:
    """Drop every node type and junction whose table is not in ``store``.

    ``sources_with_tables`` keeps a *source* out when its tables are missing,
    but the spine's tables — ``paper``, ``disease``, ``taxon_condition`` — are
    written by whichever sources ran, so a build that loaded no association
    source has a spine declaring node types with nothing behind them. The
    loader reads those as empty types and the index step then asks for a
    ``Disease`` that does not exist. Pruning keeps the rule the rest of the
    build runs on: no node type loaded empty, and no audit rule over one.
    Returns the pruned document and the dropped names, node types and
    junctions alike.
    """
    dropped: list[str] = []

    def keep(spec: dict) -> bool:
        name = input_name(spec)
        return name is None or name in store

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


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------


@dataclass
class BuildReport:
    """What :func:`measure` read off a finished graph — data, printed by
    :func:`print_report`, so :func:`build` can hand it back as an object."""

    sources: list[str]
    nodes: list[dict]
    edges: list[dict]
    audit: list[dict]
    census: list[dict]
    expansion: list[dict]

    def node_count(self, label: str) -> int:
        return next((r["n"] for r in self.nodes if r["t"] == label), 0)

    def edge_count(self, relationship: str) -> int:
        return next((r["n"] for r in self.edges if r["t"] == relationship), 0)


@dataclass
class BuildResult:
    """What a build produced. ``graph`` is ``None`` when nothing loaded — the
    empty-directory case — and then ``skipped`` names every source. ``store``
    holds every table the preps produced, ledgers included."""

    graph: object | None
    report: BuildReport | None
    loaded: list[str]
    skipped: list[str]
    out: Path | None
    taxonomy_only: bool = False
    store: Frames = field(default_factory=Frames)


def measure(graph, sources: list[str], fragments: Path, store: Frames) -> BuildReport:
    """Read the counts, the audit, the per-field census and G10 off ``graph``."""

    def rows(query):
        return list(graph.cypher(query))

    nodes = rows("MATCH (n) RETURN labels(n)[0] AS t, count(n) AS n ORDER BY n DESC")
    edges = rows("MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS n ORDER BY n DESC")
    audit = rows(
        "CALL ontology_audit() YIELD rule, severity, violations, exempted, total, pct "
        "RETURN rule, severity, violations, exempted, total, pct ORDER BY pct DESC, rule"
    )
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
    census = rows(
        "CALL ontology_audit({by: 'property'}) "
        "YIELD rule, property, violations, total, pct "
        "WHERE rule ENDS WITH '.required_properties' AND property IS NOT NULL "
        "RETURN rule, property, violations, total, pct "
        "ORDER BY rule, violations DESC, property"
    )
    # G10: edges per source record, published rather than assumed. An
    # expansion factor is how a curated source turns into a big-looking graph,
    # and it is the number that says whether "N million edges" means anything.
    # Every relationship the fragments declare gets a row, including one the
    # build loaded no edges for — that absence is the finding, and it is how
    # `IS_DRUG` sat at zero through a release with its audit reporting 0 / 0.
    expansion: list[dict] = []
    for rel, spec in declared_relationships(fragments, sources).items():
        if not any(name in store for name in spec.inputs):
            # Not the zero-edge finding above: no source wrote this table, so
            # the loader was never asked for the relationship. A taxonomy-only
            # build has no `taxon_condition`, and querying the type it would
            # have made only draws an unknown-type warning.
            expansion.append({"rel": rel, "no_input": list(spec.inputs)})
            continue
        rows_in = sum(len(store.rows(name)) for name in spec.inputs)
        breakdown = rows(
            f"MATCH ()-[r:{rel}]->() "
            "RETURN r.primary_source AS source, count(r) AS edges, "
            "count(DISTINCT r.source_record_id) AS records ORDER BY edges DESC"
        )
        if not breakdown:
            expansion.append(
                {"rel": rel, "rows": rows_in, "fragments": list(spec.fragments)}
            )
            continue
        for r in breakdown:
            records, unit = (
                (r["records"], "records") if r["records"] else (rows_in, "rows")
            )
            expansion.append(
                {
                    "rel": rel,
                    "source": r["source"],
                    "edges": r["edges"],
                    "records": records,
                    "unit": unit,
                    "ratio": r["edges"] / records if records else 0.0,
                }
            )
    return BuildReport(list(sources), nodes, edges, audit, census, expansion)


def print_report(report: BuildReport) -> None:
    print("\n--- nodes")
    for r in report.nodes:
        print(f"  {r['t']:<20s} {r['n']:>10,}")
    print("\n--- edges")
    for r in report.edges:
        print(f"  {r['t']:<28s} {r['n']:>10,}")

    print("\n--- ontology_audit()")
    for r in report.audit:
        if r["violations"] or r["severity"] == "error":
            print(
                f"  {r['rule']:<46s} {r['severity']:<6s} "
                f"{r['violations']:>8,} / {r['total']:>8,}  {r['pct']:>6.2f}%"
            )
    quiet = sum(
        1 for r in report.audit if not r["violations"] and r["severity"] != "error"
    )
    print(f"  … {quiet} further rules at 0 violations")

    print("\n--- per-field census (ontology_audit({by: 'property'}))")
    print("    One row per declared property, including the ones nothing fails.")
    print("    A census, not a partition: an edge missing three fields is in")
    print("    three rows, so these do not sum back to the rule's violations.")
    census = report.census
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

    print("\n--- expansion factor (G10): edges per source record, for every")
    print("    relationship the fragments declare. `records` is the distinct")
    print("    source_record_id where the edge carries one, else the input rows")
    print("    of the table(s) it was loaded from, marked `rows`.")
    for r in report.expansion:
        rel = r["rel"]
        if "no_input" in r:
            print(f"  {rel:<28s} no table in this build ({', '.join(r['no_input'])})")
        elif "edges" not in r:
            print(
                f"  {rel:<28s} {'-':<14s} {0:>9,} edges / {r['rows']:>9,} rows "
                f"— declared by {', '.join(r['fragments'])}, loaded nothing"
            )
        else:
            print(
                f"  {rel:<28s} {str(r['source'] or '-'):<14s} "
                f"{r['edges']:>9,} edges / {r['records']:>9,} {r['unit']:<7s} "
                f"= {r['ratio']:5.1f}x"
            )
    print(f"\nsources loaded: {', '.join(report.sources) or '(none detected)'}")


def report(graph, sources: list[str], fragments: Path, store: Frames) -> BuildReport:
    """Measure and print, and hand the measurement back."""
    measured = measure(graph, sources, fragments, store)
    print_report(measured)
    return measured


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------


def load_graph(
    store: Frames,
    loaded: list[str],
    *,
    fragments: Path = FRAGMENTS_DIR,
    verbose: bool = True,
):
    """The graph for what ``store`` holds, declared for ``loaded`` sources.

    Composes the blueprint (the whole fragment set when every source loaded,
    the spine plus ``loaded`` otherwise), prunes the spine's tables the store
    lacks, writes the ontology and the load blueprint to a temporary
    directory — the engine reads a blueprint by path — and loads with the
    store's tables typed as frames. Returns ``(graph, pruned)``.
    """
    from microbiomekg.ontology import ontology_for, write_json

    sources = sorted(
        p.stem.removeprefix("prep_")
        for p in fragments.glob("*.json")
        if p.stem != "core"
    )
    document = (
        compose(fragments, loaded) if sorted(loaded) != sources else compose(fragments)
    )
    document, pruned = prune_absent_tables(document, store)
    if pruned:
        print(f"=== spine tables absent, dropped from the load: {', '.join(pruned)}")
    import kglite

    with tempfile.TemporaryDirectory(prefix="microbiomekg-load-") as scratch:
        ontology = write_json(
            Path(scratch) / "ontology.json",
            prune_ontology(ontology_for(loaded), pruned),
        )
        bound = load_blueprint(document, store, ontology)
        path = Path(scratch) / "blueprint.load.json"
        path.write_text(json.dumps(bound, indent=2) + "\n", encoding="utf-8")
        frames = {
            name: frame
            for name, frame in store.typed(declared_types(bound)).items()
            if name in bound["files"]
        }
        print(f"\n=== from_blueprint ({len(frames)} frames handed over)", flush=True)
        t0 = time.time()
        graph = kglite.from_blueprint(path, frames=frames, verbose=verbose, save=False)
        print(f"loaded in {time.time() - t0:.1f}s")
    return graph, pruned


def build(
    raw: Path,
    *,
    scope: str = "microbial",
    out: Path | None = None,
    save: bool = True,
    with_vectors: bool = False,
    gates: frozenset[str] = frozenset(),
    store: Frames | None = None,
) -> BuildResult:
    """The whole build, as a function: raw files in, a graph and a report out.

    ``gates`` names the licence-gated sources opted into (``{"kegg"}`` for
    ``--with-kegg``). ``save`` writes ``out`` (default
    ``graph/microbiomekg.kgl``) after the report. Prints as it goes — the
    build is minutes long and the report is its record — and returns what it
    made, so :mod:`microbiomekg.api` can hand the graph to a caller.
    """
    raw = Path(raw).resolve()
    out = (Path(out) if out is not None else Path("graph/microbiomekg.kgl")).resolve()
    store = store if store is not None else Frames()
    preps = order_preps(PREPS_DIR)
    sources = [
        p.stem.removeprefix("prep_") for p in preps if p.name != "prep_taxonomy.py"
    ]
    skipped: list[str] = []

    for prep in preps:
        source = prep.stem.removeprefix("prep_")
        if not run_prep(source, raw, store, scope=scope, gates=gates):
            skipped.append(source)

    # Every prep needs the taxdump, so a build whose taxonomy prep skipped has
    # nothing at all — and an empty data directory is the fresh-clone state,
    # not an error. The answer to it is a to-do list: every source named as
    # skipped above, no graph written, exit 0. A graph file would have to be
    # either empty or stale, and both read as "built" to whoever opens it.
    if "taxon" not in store:
        print(
            f"\n=== nothing loaded: {len(skipped) or 'every'} source(s) skipped, "
            "no graph written"
        )
        print("    Each skipped source printed the file it wanted and where it")
        print("    comes from. `microbiomekg status` lists them; `microbiomekg fetch`")
        print("    fills what it can, and docs/sources.md has the rest.")
        return BuildResult(None, None, [], skipped, None, store=store)

    # A source that did not run, and a source whose tables are not in the
    # store, are left out of both declarations for the same reason: a
    # blueprint naming a table that is not there loads that node type as
    # empty, and an ontology rule over an empty type reports 0 / 0 — a gate
    # that cannot fail, which this project treats as worse than no gate.
    fragments = FRAGMENTS_DIR
    loaded = sources_with_tables(
        fragments,
        [
            s
            for s in sources
            if s not in skipped and (s not in LICENCE_GATED or s in gates)
        ],
        store,
    )
    print(f"\n=== blueprint <- {fragments.name}/ ({len(loaded)} sources loaded)")
    if not loaded:
        print("=== taxonomy-only build: no association source loaded")
    graph, _ = load_graph(store, loaded, fragments=fragments)

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

    if with_vectors:
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

    measured = report(graph, loaded, fragments, store)

    if save:
        out.parent.mkdir(parents=True, exist_ok=True)
        graph.save(str(out))
        print(f"\nsaved {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return BuildResult(
        graph, measured, loaded, skipped, out if save else None, not loaded, store
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", type=Path, default=Path("data/raw"))
    ap.add_argument(
        "--scope", default="microbial", choices=("cited", "microbial", "all")
    )
    ap.add_argument("--out", type=Path, default=Path("graph/microbiomekg.kgl"))
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
    build(
        args.raw,
        scope=args.scope,
        out=args.out,
        save=not args.no_save,
        with_vectors=args.with_vectors,
        gates=frozenset(s for s in LICENCE_GATED if opted_into(s, args)),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

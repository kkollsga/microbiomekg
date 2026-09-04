"""Coverage against an external curated set — scored against, never loaded.

``docs/benchmarks.md`` G6 asks how much of two published microbe–disease
curations this graph independently asserts: HMDAD (Ma et al. 2017; 483 rows,
licence unstated) and Peryton (Skoufos et al. 2021; 7,977 rows, CC BY-NC).
Neither can be loaded — one has no licence and the other forbids commercial
redistribution in an MIT repo — so this module reads a set, reconciles it the
way the preps reconcile their own rows, and reports three numbers:

1. **coverage** — the fraction of the set's (taxon, disease) pairs that the
   graph carries an ``ASSOCIATED_WITH`` edge for, after the taxon has resolved
   to an NCBI ``tax_id`` and the disease to a MONDO term;
2. the **evidence histogram** of the covered pairs — which ``evidence_level``
   values the graph's own reports of those pairs carry;
3. **direction** — of the covered pairs where both sides state one, how many
   the graph's reports agree with, contradict, or split on.

What is *not* measured is as important. A pair whose taxon or disease does
not resolve is reported as unresolved and left out of the denominator, so the
coverage number is about the graph and not about the reconciler — and the
resolution rates are printed beside it so a reader can see how much was left
out. No name is hand-mapped: a disease label MONDO does not spell is a miss,
not a curation task, because the number is only worth having if it can be
re-run without judgement.

Two decisions about the sets, made before any number was read:

* HMDAD's 483 rows carry duplicates; the denominator is its **450** distinct
  ``(disease, microbe, direction)`` rows.
* Peryton curates disease-vs-disease comparisons as well as disease-vs-healthy
  ones (``group_two``). Only the rows whose comparator is ``Healthy Controls``
  are a fact of the same shape as this graph's edges, so only they count.
  Peryton's ``Increased`` / ``Decreased`` is the abundance of group one (the
  disease group) relative to group two, which is the same reading as
  BugSigDB's group-one-relative ``increased`` / ``decreased``; ``Present`` /
  ``Absent`` are not directions and are excluded from the direction metric.

Run as ``python -m microbiomekg.coverage --set hmdad`` against a built graph;
the JSON it writes is what the benchmark page's ``claim external:`` rows
point at.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from microbiomekg.conditions import MondoIndex
from microbiomekg.rawdata import MissingInput, find_mondo, find_taxdump
from microbiomekg.reconcile import TaxonomyIndex

#: Where each set's raw file lives under ``data/raw/``, and how it is read.
SETS: dict[str, tuple[str, str]] = {
    "hmdad": ("hmdad/data_download.txt", "read_hmdad"),
    "peryton": ("peryton/associations.json", "read_peryton"),
}

#: The two sources' direction words -> this graph's. HMDAD says ``Increase``,
#: Peryton ``Increased``; anything else (Peryton's ``Present`` / ``Absent``)
#: is not a direction.
DIRECTIONS = {
    "increase": "increased",
    "increased": "increased",
    "decrease": "decreased",
    "decreased": "decreased",
}
PERYTON_COMPARATOR = "Healthy Controls"

_PARENTHETICAL = re.compile(r"\s*\([^)]*\)\s*")


@dataclass(frozen=True)
class Reference:
    """One curated claim: a microbe, a disease, and the direction if stated.

    ``tax_id`` and ``disease_curie`` are what the *source* supplied — Peryton
    ships NCBI and MeSH ids, HMDAD ships names only — and are used before the
    name when present.
    """

    microbe: str
    disease: str
    direction: str | None
    tax_id: int | None = None
    disease_curie: str | None = None


@dataclass
class Resolved:
    ref: Reference
    tax_id: int | None
    taxon_status: str
    mondo: str | None
    disease_route: str

    @property
    def pair(self) -> tuple[int, str] | None:
        if self.tax_id is None or self.mondo is None:
            return None
        return self.tax_id, self.mondo


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------


def read_hmdad(path: Path) -> list[Reference]:
    """HMDAD's ``data_download.txt``: ``Disease, Microbe, Position, Evidence,
    PMID``, tab-separated, 483 rows of which 450 are distinct on
    ``(disease, microbe, direction)``. ``Evidence`` is ``Increase`` /
    ``Decrease``."""
    out: dict[tuple[str, str, str | None], Reference] = {}
    with Path(path).open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            direction = DIRECTIONS.get((row.get("Evidence") or "").strip().lower())
            ref = Reference(
                microbe=(row.get("Microbe") or "").strip(),
                disease=(row.get("Disease") or "").strip(),
                direction=direction,
            )
            if ref.microbe and ref.disease:
                out.setdefault((ref.disease, ref.microbe, ref.direction), ref)
    return list(out.values())


def read_peryton(path: Path) -> list[Reference]:
    """Peryton's ``/api/associations`` export (one JSON list, 7,977 rows),
    kept to the rows whose comparator is ``Healthy Controls`` and de-duplicated
    on ``(tax_id, MeSH id, direction)``."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[tuple, Reference] = {}
    for row in rows:
        if (row.get("group_two") or "").strip() != PERYTON_COMPARATOR:
            continue
        direction = DIRECTIONS.get((row.get("relationship_name") or "").strip().lower())
        tax_id = row.get("microbe_ncbi_tax_id")
        ref = Reference(
            microbe=(row.get("microbe_scientific_name") or "").strip(),
            disease=(
                row.get("disease_mesh_heading") or row.get("disease_name") or ""
            ).strip(),
            direction=direction,
            tax_id=int(tax_id) if tax_id not in (None, "") else None,
            disease_curie=(row.get("disease_mesh_id") or "").strip() or None,
        )
        key = (ref.tax_id or ref.microbe, ref.disease_curie or ref.disease, direction)
        out.setdefault(key, ref)
    return list(out.values())


def read_set(name: str, raw: Path) -> list[Reference]:
    rel, reader = SETS[name]
    path = Path(raw) / rel
    if not path.is_file():
        raise MissingInput(f"no {rel} under {raw} (microbiomekg fetch --only {name})")
    return globals()[reader](path)


# ---------------------------------------------------------------------------
# Reconciliation, the preps' way
# ---------------------------------------------------------------------------


def disease_key(label: str) -> str:
    """The one normalisation applied to a disease *name*: a trailing
    parenthetical (``Irritable bowel syndrome(IBS)``) is dropped. Nothing
    else — a label MONDO does not spell is a miss."""
    return _PARENTHETICAL.sub(" ", label).strip()


def resolve(
    refs: list[Reference], idx: TaxonomyIndex, mondo: MondoIndex
) -> list[Resolved]:
    out = []
    for ref in refs:
        if ref.tax_id is not None:
            res = idx.resolve(tax_id=ref.tax_id, rank_ceiling="species")
        else:
            res = idx.resolve(ref.microbe, rank_ceiling="species")
        if ref.disease_curie:
            hub = mondo.mondo_id(ref.disease_curie)
            route = "equivalence" if hub else "unmatched"
            if hub is None:
                hub, route = mondo.mondo_by_name(disease_key(ref.disease))
        else:
            hub, route = mondo.mondo_by_name(disease_key(ref.disease))
        out.append(Resolved(ref, res.tax_id, res.status, hub, route))
    return out


# ---------------------------------------------------------------------------
# The graph's side, and the score
# ---------------------------------------------------------------------------


def association_layer(graph) -> dict[tuple[int, str], list[tuple[str, str]]]:
    """``(tax_id, MONDO id) -> [(direction, evidence_level), ...]`` over every
    ``Taxon -[:ASSOCIATED_WITH]-> Disease`` edge whose disease has a MONDO key
    (as its own id or as ``mondo_id``)."""
    layer: dict[tuple[int, str], list[tuple[str, str]]] = defaultdict(list)
    query = (
        "MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease) "
        "RETURN t.id AS tax_id, d.id AS id, d.mondo_id AS mondo, "
        "r.direction AS direction, r.evidence_level AS evidence"
    )
    for row in graph.cypher(query).to_list():
        hub = row["mondo"] or (
            row["id"] if str(row["id"]).startswith("MONDO:") else None
        )
        if hub is None or row["tax_id"] is None:
            continue
        layer[(int(row["tax_id"]), hub)].append(
            (row["direction"] or "", row["evidence"] or "")
        )
    return layer


@dataclass
class Score:
    set_name: str
    references: int
    taxa_resolved: int
    diseases_resolved: int
    pairs_resolvable: int
    pairs_covered: int
    evidence: dict[str, int] = field(default_factory=dict)
    direction_comparable: int = 0
    direction_agree: int = 0
    direction_contradict: int = 0
    direction_split: int = 0
    taxon_statuses: dict[str, int] = field(default_factory=dict)
    disease_routes: dict[str, int] = field(default_factory=dict)

    @property
    def coverage(self) -> float:
        return (
            self.pairs_covered / self.pairs_resolvable if self.pairs_resolvable else 0.0
        )


def score(set_name: str, resolved: list[Resolved], layer: dict) -> Score:
    taxon_statuses = Counter(r.taxon_status for r in resolved)
    disease_routes = Counter(r.disease_route for r in resolved)
    resolvable = [r for r in resolved if r.pair is not None]
    covered = [r for r in resolvable if r.pair in layer]
    evidence: Counter = Counter()
    for r in covered:
        for _, ev in layer[r.pair]:
            evidence[ev or "(absent)"] += 1
    comparable = agree = contradict = split = 0
    for r in covered:
        if r.ref.direction is None:
            continue
        dirs = {d for d, _ in layer[r.pair] if d}
        if not dirs:
            continue
        comparable += 1
        if dirs == {r.ref.direction}:
            agree += 1
        elif r.ref.direction in dirs:
            split += 1
        else:
            contradict += 1
    return Score(
        set_name=set_name,
        references=len(resolved),
        taxa_resolved=sum(1 for r in resolved if r.tax_id is not None),
        diseases_resolved=sum(1 for r in resolved if r.mondo is not None),
        pairs_resolvable=len(resolvable),
        pairs_covered=len(covered),
        evidence=dict(evidence.most_common()),
        direction_comparable=comparable,
        direction_agree=agree,
        direction_contradict=contradict,
        direction_split=split,
        taxon_statuses=dict(taxon_statuses.most_common()),
        disease_routes=dict(disease_routes.most_common()),
    )


def report(s: Score) -> str:
    pct = lambda a, b: f"{100.0 * a / b:.1f}%" if b else "n/a"  # noqa: E731
    lines = [
        f"=== {s.set_name}: {s.references:,} curated claims",
        f"  taxa resolved      {s.taxa_resolved:>6,}  {pct(s.taxa_resolved, s.references)}  {s.taxon_statuses}",
        f"  diseases resolved  {s.diseases_resolved:>6,}  {pct(s.diseases_resolved, s.references)}  {s.disease_routes}",
        f"  pairs resolvable   {s.pairs_resolvable:>6,}",
        f"  pairs covered      {s.pairs_covered:>6,}  {pct(s.pairs_covered, s.pairs_resolvable)} of resolvable, {pct(s.pairs_covered, s.references)} of all",
        f"  evidence of covered pairs' reports: {s.evidence}",
        f"  direction: {s.direction_comparable:,} comparable — agree {s.direction_agree:,}, contradict {s.direction_contradict:,}, split {s.direction_split:,}",
    ]
    return "\n".join(lines)


def run(
    set_name: str, raw: Path, graph, *, idx: TaxonomyIndex, mondo: MondoIndex
) -> Score:
    refs = read_set(set_name, raw)
    resolved = resolve(refs, idx, mondo)
    return score(set_name, resolved, association_layer(graph))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--graph", type=Path, default=Path("graph/microbiomekg.kgl"))
    ap.add_argument("--set", action="append", choices=sorted(SETS), dest="sets")
    ap.add_argument("--out", type=Path, help="write the scores as JSON here")
    args = ap.parse_args(argv)
    import kglite

    raw = args.data / "raw"
    graph = kglite.load(str(args.graph))
    idx = TaxonomyIndex.from_taxdump(find_taxdump(raw))
    mondo = MondoIndex.from_obo(find_mondo(raw))
    layer = association_layer(graph)
    scores = []
    for name in args.sets or sorted(SETS):
        try:
            refs = read_set(name, raw)
        except MissingInput as absent:
            print(str(absent), file=sys.stderr)
            continue
        s = score(name, resolve(refs, idx, mondo), layer)
        print(report(s))
        scores.append(asdict(s) | {"coverage": round(s.coverage, 4)})
    if args.out:
        args.out.write_text(
            json.dumps({"graph": args.graph.name, "sets": scores}, indent=1) + "\n"
        )
        print(f"wrote {args.out}")
    return 0 if scores else 3


if __name__ == "__main__":
    raise SystemExit(main())

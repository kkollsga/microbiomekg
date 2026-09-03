#!/usr/bin/env python3
"""KEGG's compound→map links -> Pathway nodes and IN_PATHWAY rows. Off by default.

**This script refuses to run without ``--with-kegg``.** KEGG is not a public
database: academic users may use the website, a service built on it needs an
academic service-provider licence, and non-academic use needs a commercial one
(docs/sources.md §7). A graph carrying KEGG content cannot be published, so the
default build produces none of it, and ``scripts/build.py`` forwards the flag
rather than deciding for the operator. The refusal exits **3**, the same code a
missing raw input uses, because the build's response is the same: leave the
source out and say so. Every row written carries
``source_licence = 'KEGG-restricted'``, so a shippable subgraph can be cut by
one ``WHERE`` clause instead of a rebuild.

Three files are read and three are deliberately not:

* ``list_pathway.tsv`` (587 rows) becomes ``Pathway`` nodes keyed
  ``KEGG:map…``. **``list_pathway_hsa.tsv`` is not loaded**: its 372 rows are
  the same maps with the species appended to the name
  (`Metabolic pathways - Homo sapiens (human)`), so loading both yields two
  nodes for one biological pathway.
* ``link_compound_pathway.tsv`` (19,647 rows) becomes ``IN_PATHWAY``. Both
  columns are namespace-prefixed (`path:map00010`, `cpd:C00022`) and the
  prefixes are stripped, or the compound key never matches HMDB's bare
  `C00022`. Every row uses the `map` (reference) prefix, never `hsa`.
* ``list_compound.tsv`` (19,626 rows) is read **only to check HMDB's ids
  against it**, not to name anything: its second column is a `"; "`-joined
  synonym list on 8,777 rows, so loading it as a name produces
  `"NAD+; NAD; Nicotinamide adenine dinucleotide; DPN; …"`. What it answers is
  how many of HMDB's KEGG ids KEGG has since withdrawn — the measurable cost of
  HMDB 5.0 being four years old — and those are reported, not dropped silently.
  Three buckets, kept apart because they blame different parties: a well-formed
  `C\\d{5}` absent from the list is KEGG's withdrawal, a `D`/`G` id was never
  going to be in a *compound* list, and a string that is not a KEGG identifier
  at all (`c0338`, four digits) is HMDB's typo.
* ``conv_compound_pubchem.tsv`` is **not loaded**. It returns PubChem
  *Substance* ids: `C00001` (water) maps to `pubchem:3303` where water's
  PubChem **CID** is 962. Writing those beside HMDB's `pubchem_compound_id`,
  which is a CID, would point every KEGG compound at the wrong PubChem record
  and look entirely plausible doing it.
* ``list_genome.tsv`` is **not loaded**: no taxid. ``/list/organism`` was
  retired upstream and the roster that replaced it lost the lineage column, so
  there is no taxon–pathway edge to be had from KEGG at all.

The join runs through ``metabolite.csv``'s ``kegg_id``, and the metabolite
selection rule in ``scripts/prep_hmdb.py`` deliberately never consults KEGG —
a metabolite kept *because* KEGG links it would be a KEGG-derived row sitting
in a graph built without the flag. So a KEGG link whose compound is not already
a selected metabolite reaches no edge and is counted into
``unresolved_pathway_links.csv``.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from microbiomekg import ontology as ont  # noqa: E402
from microbiomekg.ontology import kegg as kg  # noqa: E402
from microbiomekg.tables import Writer  # noqa: E402

SOURCE = kg.SOURCE

#: A KEGG compound id is `C` and exactly five digits. HMDB's one lowercase
#: `kegg_id` is `c0338`, which upper-cases to `C0338` — **four** digits, so it
#: is not merely miscased, it is not a KEGG identifier at all. Counting it as
#: "withdrawn upstream" would blame KEGG for HMDB's typo.
COMPOUND_ID = re.compile(r"^C\d{5}$")

PATHWAY_FIELDS = [
    "pathway_id", "name", "species", "pathway_source", "source_licence", "source_id",
]
LINK_FIELDS = [
    "evidence_level", "knowledge_level", "agent_type", "primary_source",
    "source_record_id", "source_licence", "source_relation", "evidence_code",
    "eco_id", "species",
]


def rows(path: Path, columns: int) -> list[list[str]]:
    out: list[list[str]] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            fields = [f.strip() for f in line.rstrip("\n").split("\t")]
            if len(fields) >= columns and fields[0]:
                out.append(fields)
    return out


def strip_prefix(value: str) -> str:
    """`path:map00010` -> `map00010`, `cpd:C00022` -> `C00022`."""
    return value.split(":", 1)[1] if ":" in value else value


def metabolite_index(path: Path) -> tuple[dict[str, str], int]:
    """Upper-cased KEGG compound id -> ``metabolite_id``.

    Upper-cased because HMDB carries exactly one lowercase `kegg_id`, `c0338`,
    where every other value is `C…`. Case-folding the key is the difference
    between that metabolite joining and it silently not.
    """
    if not path.is_file():
        return {}, 0
    index: dict[str, str] = {}
    rows_read = 0
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            rows_read += 1
            kegg = (row.get("kegg_id") or "").strip().upper()
            if kegg:
                index.setdefault(kegg, row["metabolite_id"])
    return index, rows_read


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", type=Path, default=Path("data/raw"))
    ap.add_argument("--kegg", type=Path, default=None,
                    help="Directory holding the KEGG TSVs (default: <raw>/kegg).")
    ap.add_argument("--out", type=Path, default=Path("data/csv"))
    ap.add_argument(
        "--with-kegg", action="store_true",
        help="Required. Without it this source loads nothing: KEGG's licence "
             "forbids redistributing a graph that carries it.",
    )
    args = ap.parse_args(argv)

    if not args.with_kegg:
        print(
            f"{SOURCE} is licence-gated and was not asked for: pass {kg.BUILD_FLAG} "
            f"to include it. KEGG is not a public database and a graph carrying it "
            f"cannot be published (docs/sources.md section 7).",
            file=sys.stderr,
        )
        return 3

    src = args.kegg or (args.raw / SOURCE)
    needed = ("list_pathway.tsv", "link_compound_pathway.tsv", "list_compound.tsv")
    missing = [n for n in needed if not (src / n).is_file()]
    if missing:
        print(f"no {', '.join(missing)} under {src}", file=sys.stderr)
        return 3

    licence = ont.SOURCE_LICENCE.get(SOURCE, "")
    out = args.out
    pathways = Writer(
        out / "pathway.csv", PATHWAY_FIELDS,
        key="pathway_id", merge=True, owner=("pathway_source", SOURCE),
    )
    links = Writer(
        out / "metabolite_pathway.csv", ["metabolite_id", "pathway_id", *LINK_FIELDS],
        dedupe_full=True, merge=True, owner=("primary_source", SOURCE),
    )
    # Aggregated per compound, not per link row — see prep_reactome.py: the
    # same fact restated once per map is a large file and a worse ledger.
    ledger = Writer(
        out / "unresolved_pathway_links.csv",
        ["source_id", "pathway_id", "reason", "rows", "primary_source"],
        key="source_id", merge=True, sum_fields=("rows",),
        owner=("primary_source", SOURCE),
    )

    counters: Counter[str] = Counter()
    compounds = {r[0] for r in rows(src / "list_compound.tsv", 1)}

    declared: set[str] = set()
    for map_id, name in ((r[0], r[1]) for r in rows(src / "list_pathway.tsv", 2)):
        counters["pathway_rows"] += 1
        declared.add(map_id)
        pathways.add({
            "pathway_id": f"KEGG:{map_id}",
            "name": name,
            # Reference maps are species-neutral by construction — that is what
            # the `map` prefix means — so the column is empty rather than
            # carrying a species KEGG does not claim.
            "species": "",
            "pathway_source": SOURCE,
            "source_licence": licence,
            "source_id": map_id,
        })

    metabolites, metabolite_rows = metabolite_index(out / "metabolite.csv")
    if not metabolite_rows:
        print(f"no metabolite.csv under {out}: pathway nodes load, but no "
              f"IN_PATHWAY edge can be joined")
    # Two different facts, kept apart. A `C` id absent from the compound list
    # is one KEGG has withdrawn since HMDB 5.0 (2021) — 27 in the real data, the
    # measurable cost of HMDB's age. A `D` (drug) or `G` (glycan) id was never
    # going to be in a *compound* list at all, so counting it as withdrawn would
    # overstate the decay by 10 ids that are simply in another namespace.
    malformed = sorted(k for k in metabolites if not COMPOUND_ID.match(k)
                       and not k.startswith(("D", "G")))
    withdrawn = sorted(k for k in metabolites
                       if COMPOUND_ID.match(k) and k not in compounds)
    other_namespace = sorted(k for k in metabolites if k.startswith(("D", "G")))

    for pathway_raw, compound_raw in ((r[0], r[1]) for r in
                                      rows(src / "link_compound_pathway.tsv", 2)):
        counters["link_rows"] += 1
        map_id, compound = strip_prefix(pathway_raw), strip_prefix(compound_raw)
        if map_id not in declared:
            counters["link_without_pathway"] += 1
            ledger.add({
                "source_id": f"KEGG:{map_id}", "pathway_id": f"KEGG:{map_id}",
                "reason": "link names a map list_pathway.tsv does not declare",
                "rows": "1", "primary_source": SOURCE,
            })
            continue
        target = metabolites.get(compound.upper())
        if target is None:
            counters["link_without_metabolite"] += 1
            ledger.add({
                "source_id": f"KEGG:{compound}", "pathway_id": f"KEGG:{map_id}",
                "reason": "no Metabolite node: the HMDB selection rule does not "
                          "consult KEGG, so a compound KEGG links but HMDB did not "
                          "select reaches no edge",
                "rows": "1", "primary_source": SOURCE,
            })
            continue
        links.add({
            "metabolite_id": target,
            "pathway_id": f"KEGG:{map_id}",
            "evidence_level": kg.EVIDENCE_LEVEL,
            "knowledge_level": ont.knowledge_level(SOURCE),
            "agent_type": ont.agent_type(SOURCE),
            "primary_source": SOURCE,
            "source_record_id": f"{SOURCE}:{compound}:{map_id}",
            "source_licence": licence,
            "source_relation": "link/compound/pathway",
            # KEGG ships no per-link evidence field of any kind. Empty is the
            # honest value; a fabricated code would be indistinguishable from
            # Reactome's real one in a query.
            "evidence_code": "",
            "eco_id": "",
            "species": "",
        })
        counters["in_pathway"] += 1

    tables = (pathways, links, ledger)
    counts = {w.path.name: w.flush() for w in tables}

    print(f"\nread {counters['pathway_rows']:,} reference maps, "
          f"{counters['link_rows']:,} compound-map links, "
          f"{len(compounds):,} compounds")
    print(f"  edges: {counters['in_pathway']:,} IN_PATHWAY against "
          f"{metabolite_rows:,} metabolite rows ({len(metabolites):,} carry a kegg_id)")
    print(f"  not loaded: {counters['link_without_metabolite']:,} links whose compound "
          f"is not a selected metabolite, {counters['link_without_pathway']:,} links "
          f"naming an undeclared map")
    print(f"  {len(withdrawn):,} of the {len(metabolites):,} KEGG ids HMDB carries are "
          f"no longer in list_compound.tsv (withdrawn upstream since HMDB 5.0)"
          + (": " + ", ".join(withdrawn[:8]) + ("…" if len(withdrawn) > 8 else "")
             if withdrawn else ""))
    print(f"  {len(malformed):,} are not a KEGG identifier at all"
          + (": " + ", ".join(malformed) if malformed else ""))
    print(f"  {len(other_namespace):,} are not compound ids at all (D = drug, "
          f"G = glycan) and can never join a compound list"
          + (": " + ", ".join(other_namespace[:8]) if other_namespace else ""))
    print("  conv_compound_pubchem.tsv NOT loaded: those are PubChem Substance "
          "ids, not Compound ids")
    print("  list_genome.tsv NOT loaded: no taxid, so no taxon-pathway edge exists")
    print(f"  every row carries source_licence={licence!r}")
    for name, n in counts.items():
        print(f"  {name:34s} {n:>9,}")
    shared = {w.path.name: w.merged_in for w in tables if w.merged_in}
    if shared:
        print("  merged into tables another source had written: " + ", ".join(
            f"{name} +{n:,}" for name, n in shared.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

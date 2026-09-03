#!/usr/bin/env python3
"""Reactome's five headerless TSVs -> the Pathway nodes, the DAG and IN_PATHWAY.

``ReactomePathways.txt`` (23,603 rows: id, name, species),
``ReactomePathwaysRelation.txt`` (23,717 rows: parent, child) and
``ChEBI2Reactome.txt`` (113,779 rows sharing one 6-column layout with the other
mapping files: source_id, pathway_id, url, pathway_name, evidence_code,
species). CC0, so this is the only pathway source in the increment that can
ship.

Four things here are pitfalls from ``docs/research/source-formats.md`` §4 and
each is handled where it says:

* **The hierarchy is a DAG.** 388 of 23,188 children have more than one parent.
  Every parent is written; a loader keeping one per child would silently lose
  those edges, and the ontology declares no ``cardinality`` cap for the same
  reason.
* **`R-SCE-9865878` is in both mapping files and missing from
  `ReactomePathways.txt`.** A loader that requires the node to pre-exist drops
  those rows; one that mints it from the mapping row alone gets a nameless,
  speciesless pathway. The mapping rows carry the name in column 4 and the
  species in column 6, so the node is minted **from those** and counted.
* **`ChEBI2Reactome_All_Levels.txt` is not loaded.** It is not a superset with
  extra compounds — it is the same 3,260 compounds propagated up the hierarchy,
  307,049 rows carrying the information of 113,779. The ancestry it encodes is
  already in ``PART_OF_PATHWAY``, and loading both would triple the edge count
  without adding a fact.
* **Trailing whitespace in pathway names**, 204 rows in the pathway file and
  more inside the mapping files' name column. Stripped everywhere, because the
  two files are compared by name when a node has to be minted.

``NCBI2Reactome.txt`` is **NCBI Gene**, not NCBI Taxonomy, and is not loaded at
all — see :mod:`microbiomekg.ontology.reactome`. Reading its 73,767 numeric ids
as taxids would wire that many imaginary organisms into a 16-species pathway
set, and 22 of them are not even gene ids but nucleotide accessions.

The ``IN_PATHWAY`` join runs through ``metabolite.csv``, which
``microbiomekg/preps/prep_hmdb.py`` writes — hence ``DEPENDS_ON = ["hmdb"]``, which is what
orders the build.
A ChEBI id Reactome maps and HMDB has no record of reaches no edge — there is
no compound name anywhere in the mapping files, so a minted ``Metabolite``
would be a bare CURIE with no name, no status and no biospecimen. Those are
counted into ``unresolved_pathway_links.csv`` rather than dropped.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

from microbiomekg import ontology as ont
from microbiomekg.ontology import reactome as rx
from microbiomekg.tables import Writer

SOURCE = rx.SOURCE

#: ``IN_PATHWAY`` joins through ``metabolite.csv``, which ``prep_hmdb``
#: writes; a ChEBI id no loaded metabolite carries reaches no edge.
DEPENDS_ON: list[str] = ["hmdb"]

#: `R-HSA-1234`: the three-letter infix is the species. 16 of them, all model
#: organisms — there is not a gut commensal in the set.
PATHWAY_ID = re.compile(r"^R-([A-Z]{3})-\d+$")

PATHWAY_FIELDS = [
    "pathway_id",
    "name",
    "species",
    "pathway_source",
    "source_licence",
    "source_id",
]
LINK_FIELDS = [
    "evidence_level",
    "knowledge_level",
    "agent_type",
    "primary_source",
    "source_record_id",
    "source_licence",
    "source_relation",
    "evidence_code",
    "eco_id",
    "species",
]


def rows(path: Path, columns: int) -> list[list[str]]:
    """Every line of a headerless TSV, split and stripped, short lines skipped."""
    out: list[list[str]] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            fields = [f.strip() for f in line.rstrip("\n").split("\t")]
            if len(fields) >= columns and fields[0]:
                out.append(fields)
    return out


def metabolite_index(path: Path) -> tuple[dict[str, str], int]:
    """``CHEBI:<n>`` -> ``metabolite_id``, from the metabolite table.

    Returns the index and the number of metabolite rows read, so "the join
    found nothing" and "there was nothing to join against" stay distinguishable
    in the report.
    """
    if not path.is_file():
        return {}, 0
    index: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        rows_read = 0
        for row in csv.DictReader(fh):
            rows_read += 1
            chebi = (row.get("chebi_id") or "").strip()
            if chebi:
                index.setdefault(chebi, row["metabolite_id"])
    return index, rows_read


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", type=Path, default=Path("data/raw"))
    ap.add_argument(
        "--reactome",
        type=Path,
        default=None,
        help="Directory holding the five TSVs (default: <raw>/reactome).",
    )
    ap.add_argument("--out", type=Path, default=Path("data/csv"))
    args = ap.parse_args(argv)

    src = args.reactome or (args.raw / SOURCE)
    needed = (
        "ReactomePathways.txt",
        "ReactomePathwaysRelation.txt",
        "ChEBI2Reactome.txt",
    )
    missing = [n for n in needed if not (src / n).is_file()]
    if missing:
        print(f"no {', '.join(missing)} under {src}", file=sys.stderr)
        return 3

    licence = ont.SOURCE_LICENCE.get(SOURCE, "")
    out = args.out
    pathways = Writer(
        out / "pathway.csv",
        PATHWAY_FIELDS,
        key="pathway_id",
        merge=True,
        owner=("pathway_source", SOURCE),
    )
    hierarchy = Writer(
        out / "pathway_pathway.csv",
        [
            "pathway_id",
            "parent_pathway_id",
            "primary_source",
            "source_licence",
            "source_relation",
        ],
        dedupe_full=True,
        merge=True,
        owner=("primary_source", SOURCE),
    )
    links = Writer(
        out / "metabolite_pathway.csv",
        ["metabolite_id", "pathway_id", *LINK_FIELDS],
        dedupe_full=True,
        merge=True,
        owner=("primary_source", SOURCE),
    )
    # Aggregated per source id, not per row. 77,649 of the 113,779 mapping
    # rows name a ChEBI id no Metabolite carries, and 2,146 distinct compounds
    # account for all of them — a row-per-row ledger would be a 15 MB file
    # restating one fact 36 times each. `rows` carries the count and
    # `pathway_id` one example, so nothing about the loss is unrecoverable.
    ledger = Writer(
        out / "unresolved_pathway_links.csv",
        ["source_id", "pathway_id", "reason", "rows", "primary_source"],
        key="source_id",
        merge=True,
        sum_fields=("rows",),
        owner=("primary_source", SOURCE),
    )

    counters: Counter[str] = Counter()
    codes: Counter[str] = Counter()
    seen_missing: set[str] = set()
    species_of_infix: dict[str, str] = {}

    def check_species(pathway_id: str, species: str) -> None:
        """Assert the id's three-letter infix and the species column agree.

        The species is stated twice in every file — `R-HSA-…` and
        `Homo sapiens` — and §4's fifth pitfall asks that the loader check
        rather than read one of them arbitrarily. It is called for every
        mapping row as well as every pathway row, because a mapping row's
        species is what an ``IN_PATHWAY`` edge carries: a row that disagrees
        with its own id would put the wrong species on the edge. The first
        species seen for an infix is the one it is held to, and the count is
        reported.
        """
        match = PATHWAY_ID.match(pathway_id)
        if not match or not species:
            return
        if species_of_infix.setdefault(match.group(1), species) != species:
            counters["species_infix_disagreement"] += 1

    def declare(pathway_id: str, name: str, species: str) -> None:
        check_species(pathway_id, species)
        pathways.add(
            {
                "pathway_id": f"REACT:{pathway_id}",
                "name": name,
                "species": species,
                "pathway_source": SOURCE,
                "source_licence": licence,
                "source_id": pathway_id,
            }
        )

    declared: set[str] = set()
    for pathway_id, name, species in (
        r[:3] for r in rows(src / "ReactomePathways.txt", 3)
    ):
        counters["pathway_rows"] += 1
        declared.add(pathway_id)
        declare(pathway_id, name, species)

    # The relation file is two bare ids: unlike the mapping files it carries no
    # name and no species, so an endpoint the pathway list does not declare
    # cannot be minted from it and reaches the ledger instead.
    for parent, child in (r[:2] for r in rows(src / "ReactomePathwaysRelation.txt", 2)):
        counters["relation_rows"] += 1
        if parent not in declared or child not in declared:
            counters["hierarchy_undeclared_endpoint"] += 1
            ledger.add(
                {
                    "source_id": child,
                    "pathway_id": parent,
                    "reason": "hierarchy row names a pathway ReactomePathways.txt does "
                    "not declare, and the relation file carries no name to "
                    "mint one from",
                    "rows": "1",
                    "primary_source": SOURCE,
                }
            )
            continue
        hierarchy.add(
            {
                "pathway_id": f"REACT:{child}",
                "parent_pathway_id": f"REACT:{parent}",
                "primary_source": SOURCE,
                "source_licence": licence,
                "source_relation": "ReactomePathwaysRelation",
            }
        )
        counters["hierarchy"] += 1

    metabolites, metabolite_rows = metabolite_index(out / "metabolite.csv")
    if not metabolite_rows:
        print(
            f"no metabolite.csv under {out}: pathway nodes and the hierarchy load, "
            f"but no IN_PATHWAY edge can be joined"
        )

    for row in rows(src / "ChEBI2Reactome.txt", 6):
        chebi, pathway_id, _url, name, code, species = row[:6]
        counters["chebi_rows"] += 1
        codes[code] += 1
        check_species(pathway_id, species)
        curie = f"CHEBI:{chebi}"
        if pathway_id not in declared:
            # The R-SCE-9865878 case: present in both mapping files, absent from
            # the pathway list. Minted from this row's own name and species
            # columns, which is the only place they exist.
            counters["pathway_minted_from_mapping"] += 1
            declared.add(pathway_id)
            declare(pathway_id, name, species)
        target = metabolites.get(curie)
        if target is None:
            counters["chebi_without_metabolite"] += 1
            if curie not in seen_missing:
                seen_missing.add(curie)
                counters["chebi_ids_without_metabolite"] += 1
            ledger.add(
                {
                    "source_id": curie,
                    "pathway_id": f"REACT:{pathway_id}",
                    "reason": "no Metabolite node: HMDB has no record carrying this "
                    "ChEBI id, and the mapping files carry no compound name "
                    "to mint one from",
                    "rows": "1",
                    "primary_source": SOURCE,
                }
            )
            continue
        level, knowledge, agent, eco = rx.evidence_for(code)
        links.add(
            {
                "metabolite_id": target,
                "pathway_id": f"REACT:{pathway_id}",
                "evidence_level": level,
                "knowledge_level": knowledge,
                "agent_type": agent,
                "primary_source": SOURCE,
                "source_record_id": f"{SOURCE}:{chebi}:{pathway_id}",
                "source_licence": licence,
                "source_relation": "ChEBI2Reactome",
                "evidence_code": code,
                "eco_id": eco,
                "species": species,
            }
        )
        counters["in_pathway"] += 1

    tables = (pathways, hierarchy, links, ledger)
    counts = {w.path.name: w.flush() for w in tables}

    print(
        f"\nread {counters['pathway_rows']:,} pathways, "
        f"{counters['relation_rows']:,} hierarchy rows, "
        f"{counters['chebi_rows']:,} ChEBI mapping rows"
    )
    print(
        f"  {len(species_of_infix)} species by id infix; "
        f"{counters['species_infix_disagreement']:,} rows where the infix and the "
        f"species column disagree"
    )
    print(
        f"  hierarchy: {counters['hierarchy']:,} PART_OF_PATHWAY edges "
        f"(a DAG — a child may have several parents)"
    )
    print(
        f"  edges: {counters['in_pathway']:,} IN_PATHWAY against "
        f"{metabolite_rows:,} metabolite rows"
    )
    print(
        "  evidence codes: "
        + ", ".join(
            f"{code} {n:,} ({100 * n / max(counters['chebi_rows'], 1):.1f}%)"
            for code, n in codes.most_common()
        )
    )
    print(
        f"  not loaded: {counters['chebi_without_metabolite']:,} mapping rows over "
        f"{counters['chebi_ids_without_metabolite']:,} ChEBI ids no Metabolite "
        f"carries, "
        f"{counters['hierarchy_undeclared_endpoint']:,} hierarchy rows with an "
        f"undeclared endpoint"
    )
    print(
        f"  minted from a mapping row: {counters['pathway_minted_from_mapping']:,} "
        f"pathways absent from ReactomePathways.txt"
    )
    print(
        "  ChEBI2Reactome_All_Levels.txt NOT loaded: same 3,260 compounds "
        "propagated up the hierarchy, which PART_OF_PATHWAY already carries"
    )
    print("  NCBI2Reactome.txt NOT loaded: those are NCBI *Gene* ids, not taxids")
    for name, n in counts.items():
        print(f"  {name:34s} {n:>9,}")
    shared = {w.path.name: w.merged_in for w in tables if w.merged_in}
    if shared:
        print(
            "  merged into tables another source had written: "
            + ", ".join(f"{name} +{n:,}" for name, n in shared.items())
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

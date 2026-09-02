#!/usr/bin/env python3
"""BugSigDB full_dump.csv -> the flat CSVs blueprint.json loads.

One BugSigDB row is one *signature*: a set of taxa that moved in one direction
in one experiment. This script fans that row out into the node and edge tables
the graph wants, routes every taxon through
:class:`microbiomekg.reconcile.TaxonomyIndex`, and writes what failed to
``unresolved_taxa.csv`` rather than dropping it.

Run this **before** ``prep_taxonomy.py``: it writes ``cited_taxa.csv``, which
is what ``prep_taxonomy.py --scope cited`` filters the taxonomy down to.

Two gotchas in the export, both silent if you get them wrong:

* the two taxon columns use **different delimiters** — ``MetaPhlAn taxon
  names`` separates taxa with ``,`` while ``NCBI Taxonomy IDs`` separates them
  with ``;`` (both use ``|`` between lineage ranks). Verified: pairing them
  that way aligns on all 14,225 rows that carry taxa; pairing them with the
  same delimiter misaligns 11,273 of them.
* missing values are the literal string ``"NA"``. They must become an *empty*
  CSV cell, because kglite treats an empty cell as an absent property, and an
  absent property is what the ontology's ``required_properties`` audit counts.
  Passing ``"NA"`` through would make every evidence gap look filled.

And one in the loader, which the build command has to work around: kglite's
blueprint junction loader streams in 100,000-row chunks and *deduplicates
parallel edges from the second chunk onwards*. ``taxon_disease.csv`` is
~118k rows of deliberately parallel edges, so a default build silently loses
~7.7% of them. Build with::

    KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE=1000000 python -c \\
        "import kglite; kglite.from_blueprint('blueprint.json', verbose=True)"
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from microbiomekg import ontology as ont  # noqa: E402
from microbiomekg.rawdata import find_bugsigdb_dump, find_taxdump  # noqa: E402
from microbiomekg.reconcile import Resolution, TaxonomyIndex  # noqa: E402

SOURCE = "bugsigdb"

#: MetaPhlAn rank prefix -> NCBI rank name.
RANK_PREFIX = {
    "k__": "kingdom",
    "p__": "phylum",
    "c__": "class",
    "o__": "order",
    "f__": "family",
    "g__": "genus",
    "s__": "species",
    "t__": "strain",
}


def na(value: str | None) -> str:
    """BugSigDB's ``"NA"`` (and whitespace) -> the empty cell kglite reads as absent."""
    v = (value or "").strip()
    return "" if v in ("NA", "N/A", "nan", "None") else v


def as_int(value: str | None) -> str:
    """Keep a cell only if it is a plain integer; otherwise blank it."""
    v = na(value)
    return v if v.isdigit() else ""


def slug(text: str, prefix: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return f"{prefix}:{s}" if s else ""


def normalise_doi(value: str | None) -> str:
    """`https://doi.org/10.1/X`, `doi:10.1/X` and `10.1/X` are one DOI.

    DOIs are case-insensitive by specification, and the three upstream spellings
    all appear in BugSigDB's DOI column, so an un-normalised value makes the
    same paper look like three.
    """
    v = na(value)
    if not v:
        return ""
    v = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/", "", v, flags=re.I)
    v = re.sub(r"^doi:\s*", "", v, flags=re.I)
    return v.strip().lower()


def curie_ontology(curie: str) -> str:
    """``MONDO:0005265`` -> ``MONDO``. The column is named "EFO ID" but carries
    twelve different vocabularies (MONDO 48%, EFO 36%, HP, GO, CHEBI, ...), so
    the prefix is kept as data instead of being assumed."""
    m = re.match(r"([A-Za-z]+)[:_]", curie)
    return m.group(1).upper() if m else ""


def split_curies(cell: str) -> list[str]:
    """Split a multi-valued ontology cell. 329 signatures name two conditions."""
    return [c.strip() for c in re.split(r"[,;]", cell) if c.strip()]


def split_taxa(names_cell: str, ids_cell: str) -> list[tuple[str, str]]:
    """Pair the two taxon columns, honouring their different delimiters.

    Returns ``(name_lineage, id_lineage)`` pairs, each still ``|``-joined. When
    the two columns disagree on length the ids win and the names are dropped —
    a wrong name attached to a right id is worse than no name, and the id
    carries its own name through the taxdump.
    """
    ids = [t.strip() for t in ids_cell.split(";") if t.strip()]
    names = [t.strip() for t in names_cell.split(",") if t.strip()]
    if not ids:
        # 4.2% of rows carry no id column at all. Zipping against an empty list
        # would drop the whole row's taxa without a word; those names are the
        # ones reconciliation exists for.
        return [(n, "") for n in names]
    if len(names) != len(ids):
        names = [""] * len(ids)
    return list(zip(names, ids))


def terminal(lineage: str) -> str:
    return lineage.split("|")[-1].strip() if lineage else ""


def reported_rank(name_terminal: str) -> str:
    return RANK_PREFIX.get(name_terminal[:3], "")


def strip_prefix(name_terminal: str) -> str:
    return name_terminal[3:] if name_terminal[:3] in RANK_PREFIX else name_terminal


class Writer:
    """Deduplicating CSV writer: first row per key wins, header fixed up front.

    ``key`` dedupes node tables on their primary key. ``dedupe_full`` dedupes
    edge tables on the *whole* row: a signature that names both a strain and
    its species resolves both to one tax_id, and the second is a duplicate
    fact, not a second observation. Genuinely parallel edges — the same taxon
    and disease from two different signatures — differ in ``signature_id`` and
    survive.
    """

    def __init__(
        self, path: Path, fields: list[str], key: str | None = None, dedupe_full: bool = False
    ):
        self.path = path
        self.fields = fields
        self.key = key
        self.dedupe_full = dedupe_full
        self.seen: set = set()
        self.rows: list[dict[str, str]] = []

    def add(self, row: dict[str, str]) -> bool:
        if self.key is not None:
            k = row[self.key]
            if not k or k in self.seen:
                return False
            self.seen.add(k)
        elif self.dedupe_full:
            k = tuple(row.get(f, "") for f in self.fields)
            if k in self.seen:
                return False
            self.seen.add(k)
        self.rows.append(row)
        return True

    def flush(self) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=self.fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(self.rows)
        return len(self.rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    # One `--raw` root for both prep scripts; `--dump`/`--taxdump` override it.
    ap.add_argument("--raw", type=Path, default=Path("data/raw"))
    ap.add_argument("--dump", type=Path, default=None)
    ap.add_argument("--taxdump", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=Path("data/csv"))
    ap.add_argument(
        "--rank-ceiling",
        default="species",
        help="Promote anything more specific than this to its nearest ancestor at "
        "or above it (default: species).",
    )
    ap.add_argument(
        "--ontology-json",
        type=Path,
        default=Path("ontology.json"),
        help="Where to write the define_ontology document the blueprint gate reads.",
    )
    ap.add_argument("--limit", type=int, default=0, help="Only read N rows (smoke tests).")
    args = ap.parse_args(argv)

    try:
        dump = args.dump or find_bugsigdb_dump(args.raw)
        taxdump = args.taxdump or find_taxdump(args.raw)
    except FileNotFoundError as e:
        ap.error(str(e))
    print(f"reading {dump}", flush=True)
    print(f"loading taxdump from {taxdump} ...", flush=True)
    idx = TaxonomyIndex.from_taxdump(taxdump)
    print(f"  {len(idx.parent):,} taxa, {len(idx.names):,} name keys", flush=True)

    out = args.out
    studies = Writer(
        out / "study.csv",
        ["study_id", "study_number", "title", "journal", "year", "doi", "url",
         "authors", "keywords", "pmid", "pmid_raw"],
        key="study_id",
    )
    papers = Writer(out / "paper.csv", ["pmid", "title", "journal", "year", "doi"], key="pmid")
    diseases = Writer(
        out / "disease.csv", ["disease_id", "label", "source_id", "ontology"], key="disease_id"
    )
    bodysites = Writer(
        out / "bodysite.csv", ["bodysite_id", "label", "source_id", "ontology"], key="bodysite_id"
    )
    signatures = Writer(
        out / "signature.csv",
        ["signature_id", "study_id", "experiment", "signature", "description",
         "direction", "study_design", "evidence_level", "host_species", "location",
         "group_0_name", "group_1_name", "group_0_size", "group_1_size",
         "group_1_definition", "sequencing_type", "variable_region", "sequencing_platform",
         "data_transformation", "statistical_test", "significance_threshold",
         "mht_correction", "lda_score_above", "matched_on", "confounders",
         "shannon", "chao1", "richness", "curator", "curated_date", "source_figure",
         "state", "pmid", "n_taxa", "n_unresolved", "source"],
        key="signature_id",
    )
    sig_condition = Writer(
        out / "signature_condition.csv", ["signature_id", "disease_id"], dedupe_full=True
    )
    sig_bodysite = Writer(
        out / "signature_bodysite.csv", ["signature_id", "bodysite_id"], dedupe_full=True
    )
    reported = Writer(
        out / "taxon_signature.csv",
        ["tax_id", "signature_id", "reported_name", "reported_rank", "original_rank",
         "reported_tax_id", "resolution_status", "resolution_normalized",
         "resolution_note", "direction", "source"],
        dedupe_full=True,
    )
    reported_unres = Writer(
        out / "unresolved_taxon_signature.csv",
        ["unresolved_id", "signature_id", "reported_name", "reported_rank",
         "original_rank", "reported_tax_id", "resolution_status",
         "resolution_normalized", "resolution_note", "direction", "source"],
        dedupe_full=True,
    )
    unresolved_nodes = Writer(
        out / "unresolved_taxa.csv",
        ["unresolved_id", "raw_name", "reported_rank", "original_rank",
         "reported_tax_id", "source", "status", "candidates", "note", "n_signatures"],
        key="unresolved_id",
    )
    assoc = Writer(
        out / "taxon_disease.csv",
        ["tax_id", "disease_id", "direction", "study_design", "evidence_level",
         "sequencing_type", "statistical_test", "group_0_size", "group_1_size",
         "pmid", "source", "signature_id", "study_id", "host_species", "body_site",
         "significance_threshold", "mht_correction"],
        dedupe_full=True,
    )

    cited: "OrderedDict[int, int]" = OrderedDict()
    unresolved_hits: dict[str, int] = {}
    n_rows = n_pairs = n_resolved = 0

    with dump.open("r", newline="", encoding="utf-8") as fh:
        first = fh.readline()
        if not first.lstrip().startswith("#"):
            fh.seek(0)  # comment banner is normally line 1; tolerate its absence
        reader = csv.DictReader(fh)
        for row in reader:
            n_rows += 1
            if args.limit and n_rows > args.limit:
                n_rows -= 1
                break

            bsdb = na(row.get("BSDB ID"))
            if not bsdb:
                continue
            study_id = bsdb.split("/")[0]  # "bsdb:11/1/1" -> "bsdb:11"
            parts = bsdb.split("/")
            experiment = parts[1] if len(parts) > 2 else ""
            signature_no = parts[2] if len(parts) > 2 else ""

            pmid = as_int(row.get("PMID"))
            studies.add(
                {
                    "study_id": study_id,
                    "study_number": study_id.split(":")[-1],
                    "title": na(row.get("Title")),
                    "journal": na(row.get("Journal")),
                    "year": as_int(row.get("Year")),
                    "doi": normalise_doi(row.get("DOI")),
                    "url": na(row.get("URL")),
                    "authors": na(row.get("Authors list")),
                    "keywords": na(row.get("Keywords")),
                    "pmid": pmid,
                    # A handful of rows put a DOI or a PMC id in the PMID column;
                    # keep the raw string so the loss is visible, not silent.
                    "pmid_raw": na(row.get("PMID")),
                }
            )
            if pmid:
                papers.add(
                    {
                        "pmid": pmid,
                        "title": na(row.get("Title")),
                        "journal": na(row.get("Journal")),
                        "year": as_int(row.get("Year")),
                        "doi": normalise_doi(row.get("DOI")),
                    }
                )

            design = na(row.get("Study design"))
            seq_type = na(row.get("Sequencing type"))
            host = na(row.get("Host species"))
            direction = na(row.get("Abundance in Group 1"))
            level = ont.evidence_level(design, seq_type, host)
            g0 = as_int(row.get("Group 0 sample size"))
            g1 = as_int(row.get("Group 1 sample size"))
            stat = na(row.get("Statistical test"))

            condition_label = na(row.get("Condition"))
            disease_ids: list[str] = []
            for curie in split_curies(na(row.get("EFO ID"))):
                disease_ids.append(curie)
                diseases.add(
                    {
                        "disease_id": curie,
                        "label": condition_label or curie,
                        "source_id": curie,
                        "ontology": curie_ontology(curie),
                    }
                )
            if not disease_ids and condition_label:
                sid = slug(condition_label, "cond")
                if sid:
                    disease_ids.append(sid)
                    diseases.add(
                        {"disease_id": sid, "label": condition_label,
                         "source_id": "", "ontology": ""}
                    )

            site_label = na(row.get("Body site"))
            site_ids: list[str] = []
            for curie in split_curies(na(row.get("UBERON ID"))):
                site_ids.append(curie)
                bodysites.add(
                    {"bodysite_id": curie, "label": site_label or curie,
                     "source_id": curie, "ontology": curie_ontology(curie)}
                )
            if not site_ids and site_label:
                sid = slug(site_label, "site")
                if sid:
                    site_ids.append(sid)
                    bodysites.add(
                        {"bodysite_id": sid, "label": site_label, "source_id": "", "ontology": ""}
                    )

            for did in disease_ids:
                sig_condition.add({"signature_id": bsdb, "disease_id": did})
            for sid in site_ids:
                sig_bodysite.add({"signature_id": bsdb, "bodysite_id": sid})

            pairs = split_taxa(na(row.get("MetaPhlAn taxon names")), na(row.get("NCBI Taxonomy IDs")))
            n_here = n_unres_here = 0
            for name_lin, id_lin in pairs:
                n_pairs += 1
                n_here += 1
                raw_id = terminal(id_lin)
                name_term = terminal(name_lin)
                rank = reported_rank(name_term)
                pretty = strip_prefix(name_term)

                if raw_id.isdigit():
                    res: Resolution = idx.resolve(
                        tax_id=int(raw_id), rank_ceiling=args.rank_ceiling
                    )
                else:
                    res = idx.resolve(pretty or None, rank_ceiling=args.rank_ceiling)
                reported_name = pretty or idx.scientific_name.get(res.tax_id or -1) or raw_id

                # Two ranks, two claims, both kept (C21.4). `reported_rank` is
                # the source's: MetaPhlAn's prefix vocabulary has no
                # `subspecies`, so it files 1682 under `t__` = strain.
                # `original_rank` is NCBI's own rank for the id as given, which
                # is the one a rank query should trust.
                base = {
                    "signature_id": bsdb,
                    "reported_name": reported_name,
                    "reported_rank": rank,
                    "original_rank": res.original_rank or "",
                    "reported_tax_id": raw_id,
                    "resolution_status": res.status,
                    "resolution_normalized": "true" if res.normalized else "false",
                    "resolution_note": res.note,
                    "direction": direction,
                    "source": SOURCE,
                }

                if res.tax_id is None:
                    n_unres_here += 1
                    uid = f"unresolved:{SOURCE}:{raw_id or slug(reported_name, 'name')[5:]}"
                    unresolved_nodes.add(
                        {
                            "unresolved_id": uid,
                            "raw_name": reported_name,
                            "reported_rank": rank,
                            "original_rank": res.original_rank or "",
                            "reported_tax_id": raw_id,
                            "source": SOURCE,
                            "status": res.status,
                            "candidates": "|".join(str(c) for c in res.candidates),
                            "note": res.note,
                            "n_signatures": "0",
                        }
                    )
                    unresolved_hits[uid] = unresolved_hits.get(uid, 0) + 1
                    reported_unres.add({"unresolved_id": uid, **base})
                    continue

                n_resolved += 1
                cited[res.tax_id] = cited.get(res.tax_id, 0) + 1
                reported.add({"tax_id": str(res.tax_id), **base})

                for did in disease_ids:
                    assoc.add(
                        {
                            "tax_id": str(res.tax_id),
                            "disease_id": did,
                            "direction": direction,
                            "study_design": design,
                            "evidence_level": level,
                            "sequencing_type": seq_type,
                            "statistical_test": stat,
                            "group_0_size": g0,
                            "group_1_size": g1,
                            "pmid": pmid,
                            "source": SOURCE,
                            # The source's own record id for this assertion —
                            # part of the evidence contract, not just context.
                            "signature_id": bsdb,
                            "study_id": study_id,
                            "host_species": host,
                            "body_site": site_ids[0] if site_ids else "",
                            "significance_threshold": na(row.get("Significance threshold")),
                            "mht_correction": na(row.get("MHT correction")),
                        }
                    )

            signatures.add(
                {
                    "signature_id": bsdb,
                    "study_id": study_id,
                    "experiment": experiment,
                    "signature": signature_no,
                    "description": na(row.get("Description")),
                    "direction": direction,
                    "study_design": design,
                    "evidence_level": level,
                    "host_species": host,
                    "location": na(row.get("Location of subjects")),
                    "group_0_name": na(row.get("Group 0 name")),
                    "group_1_name": na(row.get("Group 1 name")),
                    "group_0_size": g0,
                    "group_1_size": g1,
                    "group_1_definition": na(row.get("Group 1 definition")),
                    "sequencing_type": seq_type,
                    "variable_region": na(row.get("16S variable region")),
                    "sequencing_platform": na(row.get("Sequencing platform")),
                    "data_transformation": na(row.get("Data transformation")),
                    "statistical_test": stat,
                    "significance_threshold": na(row.get("Significance threshold")),
                    "mht_correction": na(row.get("MHT correction")),
                    "lda_score_above": na(row.get("LDA Score above")),
                    "matched_on": na(row.get("Matched on")),
                    "confounders": na(row.get("Confounders controlled for")),
                    "shannon": na(row.get("Shannon")),
                    "chao1": na(row.get("Chao1")),
                    "richness": na(row.get("Richness")),
                    "curator": na(row.get("Curator")),
                    "curated_date": na(row.get("Curated date")),
                    "source_figure": na(row.get("Source")),
                    "state": na(row.get("State")),
                    "pmid": pmid,
                    "n_taxa": str(n_here),
                    "n_unresolved": str(n_unres_here),
                    "source": SOURCE,
                }
            )

    for r in unresolved_nodes.rows:
        r["n_signatures"] = str(unresolved_hits.get(r["unresolved_id"], 0))

    cited_writer = Writer(out / "cited_taxa.csv", ["tax_id", "n_signatures"])
    for tid, n in sorted(cited.items()):
        cited_writer.add({"tax_id": str(tid), "n_signatures": str(n)})

    counts = {w.path.name: w.flush() for w in (
        studies, papers, diseases, bodysites, signatures, sig_condition, sig_bodysite,
        reported, reported_unres, unresolved_nodes, assoc, cited_writer)}

    ont_path = ont.write_json(args.ontology_json)

    print(f"\nread {n_rows:,} signature rows, {n_pairs:,} taxon mentions "
          f"({n_resolved:,} resolved, {n_pairs - n_resolved:,} unresolved)")
    for name, n in counts.items():
        print(f"  {name:34s} {n:>9,}")
    print(f"  {ont_path.name:34s}  (ontology document)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

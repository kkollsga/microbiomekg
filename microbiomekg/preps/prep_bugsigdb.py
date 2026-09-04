"""BugSigDB ``full_dump_main.csv`` -> the tables the blueprint loads.

One BugSigDB row is one *signature*: a set of taxa that moved in one direction
in one experiment. This prep fans that row out into the node and edge tables
the graph wants, routes every taxon through
:class:`microbiomekg.reconcile.TaxonomyIndex`, and writes what failed to the
``unresolved_taxa`` table rather than dropping it.

It runs **before** ``prep_taxonomy``: it writes ``cited_taxa``, which is what
``prep_taxonomy``'s ``scope="cited"`` filters the taxonomy down to.

Three gotchas in the export, all silent if you get them wrong:

* the two taxon columns use **different delimiters** — ``MetaPhlAn taxon
  names`` separates taxa with ``,`` while ``NCBI Taxonomy IDs`` separates them
  with ``;`` (both use ``|`` between lineage ranks). Verified: pairing them
  that way aligns on all 14,225 rows that carry taxa; pairing them with the
  same delimiter misaligns 11,273 of them.
* missing values are the literal string ``"NA"``. They must become an *empty*
  cell, because kglite loads an empty cell as an absent property, and an
  absent property is what the ontology's ``required_properties`` audit counts.
  Passing ``"NA"`` through would make every evidence gap look filled.
* the column named ``EFO ID`` is neither EFO nor, in 40% of its mentions, a
  disease, and the ``Condition`` column beside it is comma-joined with commas
  *inside* some of its values. Both are :mod:`microbiomekg.conditions`'
  problem, not this prep's: it decides the node type, the key and the
  pairing, and anything it cannot answer lands in the ``unresolved_conditions``
  table rather than in a node type it does not belong to.

Several tables — ``paper``, ``study``, the three condition tables,
``taxon_condition``, ``cited_taxa`` and the two ledgers — are *shared* with the
other sources and opened with ``merge=True``, so running this prep before or
after another source's gives the same table. :mod:`microbiomekg.pipeline`
orders the preps by ``DEPENDS_ON``.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, OrderedDict
from pathlib import Path

from microbiomekg import ontology as ont
from microbiomekg.conditions import (
    MondoIndex,
    condition_node_type,
    curie_vocabulary,
    pair_conditions,
    split_curies,
)
from microbiomekg.rawdata import MissingInput, find_bugsigdb_dump, find_taxdump
from microbiomekg.reconcile import Resolution, TaxonomyIndex
from microbiomekg.tables import Frames, as_list

SOURCE = "bugsigdb"

#: The raw files this prep reads, relative to ``--raw``, in the layout
#: ``fetch`` writes. `status` reports on exactly these.
RAW_INPUTS: list[str] = ["bugsigdb/full_dump_main.csv"]

#: Reads no other prep's table: BugSigDB is the spine and runs first.
DEPENDS_ON: list[str] = []

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


def run(
    raw: Path,
    store: Frames,
    *,
    dump: Path | None = None,
    taxdump: Path | None = None,
    mondo: Path | None = None,
    rank_ceiling: str = "species",
    limit: int = 0,
) -> dict[str, int]:
    """BugSigDB's tables into ``store``; returns each table's row count.

    ``raw`` is the data root (``raw/bugsigdb/full_dump_main.csv`` and the
    taxdump under it) — or, for a fixture, the dump file itself. ``mondo``
    defaults to ``raw/mondo/mondo.obo``; absent, every condition keeps its
    own CURIE as key and ``mondo_id`` is null everywhere, and the build says
    so. ``limit`` reads only the first N rows (smoke tests). Raises
    :class:`MissingInput` when the dump or the taxdump is not there.
    """
    try:
        dump = dump or find_bugsigdb_dump(raw)
        taxdump = taxdump or find_taxdump(raw)
    except FileNotFoundError as e:
        # "The raw files are not on this machine" is a different fact from a
        # defect, and the build acts on the difference by leaving this source
        # out of the blueprint rather than declaring node types with nothing
        # behind them.
        raise MissingInput(str(e)) from e
    print(f"reading {dump}", flush=True)
    print(f"loading taxdump from {taxdump} ...", flush=True)
    idx = TaxonomyIndex.from_taxdump(taxdump)
    print(f"  {len(idx.parent):,} taxa, {len(idx.names):,} name keys", flush=True)

    mondo_path = mondo or (raw / "mondo" / "mondo.obo")
    if mondo_path.is_file():
        print(f"loading MONDO from {mondo_path} ...", flush=True)
        mondo = MondoIndex.from_obo(mondo_path)
        print(
            f"  {len(mondo.label):,} live terms, {len(mondo.equivalent):,} "
            f"equivalences, {len(mondo.obsolete):,} obsolete",
            flush=True,
        )
    else:
        mondo = MondoIndex()
        print(
            f"no mondo.obo at {mondo_path}; every condition keeps its own CURIE "
            f"as key and mondo_id will be null",
            flush=True,
        )

    studies = store.table(
        "study",
        [
            "study_id",
            "study_number",
            "title",
            "journal",
            "year",
            "doi",
            "url",
            "authors",
            "keywords",
            "pmid",
            "pmid_raw",
        ],
        key="study_id",
        merge=True,
    )
    papers = store.table(
        "paper",
        ["pmid", "title", "journal", "year", "doi"],
        key="pmid",
        merge=True,
    )
    # One table per condition node type (C14). The key is the MONDO CURIE when
    # MONDO declares an equivalence and the source CURIE otherwise; the source
    # id and its vocabulary stay as properties either way, so
    # `WHERE d.source_vocabulary = 'EFO'` is still expressible.
    condition_fields = [
        "condition_id",
        "label",
        "mondo_id",
        "mondo_label",
        "source_id",
        "source_vocabulary",
        "source_condition",
    ]
    conditions = {
        "Disease": store.table(
            "disease", condition_fields, key="condition_id", merge=True
        ),
        "Phenotype": store.table(
            "phenotype", condition_fields, key="condition_id", merge=True
        ),
        "Exposure": store.table(
            "exposure", condition_fields, key="condition_id", merge=True
        ),
    }
    # Nothing is dropped and nothing is guessed: a vocabulary with no node type
    # and a condition string no id could be attached to both land here, with
    # the raw strings and the reason.
    unresolved_conditions = store.table(
        "unresolved_conditions",
        [
            "signature_id",
            "source_id",
            "source_vocabulary",
            "raw_condition",
            "pairing_method",
            "reason",
            "source",
        ],
        dedupe_full=True,
        merge=True,
        owner=("source", SOURCE),
    )
    bodysites = store.table(
        "bodysite",
        ["bodysite_id", "label", "source_id", "ontology"],
        key="bodysite_id",
    )
    signatures = store.table(
        "signature",
        [
            "signature_id",
            "study_id",
            "experiment",
            "signature",
            "description",
            "direction",
            "study_design",
            "evidence_level",
            "host_species",
            "location",
            "group_0_name",
            "group_1_name",
            "group_0_size",
            "group_1_size",
            "group_1_definition",
            "sequencing_type",
            "variable_region",
            "sequencing_platform",
            "data_transformation",
            "statistical_test",
            "significance_threshold",
            "mht_correction",
            "lda_score_above",
            "matched_on",
            "confounders",
            "antibiotics_exclusion",
            "shannon",
            "chao1",
            "richness",
            "curator",
            "curated_date",
            "source_figure",
            "state",
            "pmid",
            "n_taxa",
            "n_unresolved",
            "source",
        ],
        key="signature_id",
    )
    # One junction table over the three condition node types. `condition_type`
    # is the blueprint's `target_type_column`: it routes each row to Disease,
    # Phenotype or Exposure, so one relationship spans the union instead of
    # three names splitting it (docs/model.md section 8). The column is routing
    # only — it is not in the edge's `properties`, so it never lands as an edge
    # property; the target node's own label is what a query narrows on.
    sig_condition = store.table(
        "signature_condition",
        ["signature_id", "condition_id", "condition_type"],
        dedupe_full=True,
    )
    sig_bodysite = store.table(
        "signature_bodysite",
        ["signature_id", "bodysite_id"],
        dedupe_full=True,
    )
    reported = store.table(
        "taxon_signature",
        [
            "tax_id",
            "signature_id",
            "reported_name",
            "reported_rank",
            "original_rank",
            "reported_tax_id",
            "resolution_status",
            "resolution_normalized",
            "resolution_note",
            "direction",
            "source",
        ],
        dedupe_full=True,
    )
    reported_unres = store.table(
        "unresolved_taxon_signature",
        [
            "unresolved_id",
            "signature_id",
            "reported_name",
            "reported_rank",
            "original_rank",
            "reported_tax_id",
            "resolution_status",
            "resolution_normalized",
            "resolution_note",
            "direction",
            "source",
        ],
        dedupe_full=True,
    )
    unresolved_nodes = store.table(
        "unresolved_taxa",
        [
            "unresolved_id",
            "raw_name",
            "reported_rank",
            "original_rank",
            "reported_tax_id",
            "source",
            "status",
            "candidates",
            "note",
            "n_signatures",
        ],
        key="unresolved_id",
        merge=True,
        owner=("source", SOURCE),
    )
    assoc_fields = [
        "tax_id",
        "condition_id",
        "condition_type",
        "direction",
        "study_design",
        "evidence_level",
        "sequencing_type",
        "statistical_test",
        "group_0_size",
        "group_1_size",
        "pmid",
        "knowledge_level",
        "agent_type",
        "primary_source",
        "source_record_id",
        "source_licence",
        "source_relation",
        "signature_id",
        "study_id",
        "host_species",
        "body_site",
        "significance_threshold",
        "mht_correction",
    ]
    assoc = store.table(
        "taxon_condition",
        assoc_fields,
        dedupe_full=True,
        merge=True,
        owner=("primary_source", SOURCE),
    )

    cited: "OrderedDict[int, int]" = OrderedDict()
    unresolved_hits: dict[str, int] = {}
    pairing_methods: Counter[str] = Counter()
    no_mondo_terms: set[str] = set()
    n_rows = n_pairs = n_resolved = n_unroutable = 0

    with dump.open("r", newline="", encoding="utf-8") as fh:
        first = fh.readline()
        if not first.lstrip().startswith("#"):
            fh.seek(0)  # comment banner is normally line 1; tolerate its absence
        reader = csv.DictReader(fh)
        for row in reader:
            n_rows += 1
            if limit and n_rows > limit:
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
            paired = pair_conditions(
                split_curies(na(row.get("EFO ID"))), condition_label, mondo
            )
            pairing_methods[paired.method] += 1
            # condition node type -> the keys this row links to
            row_conditions: dict[str, list[str]] = {k: [] for k in conditions}
            for curie, verbatim in paired.pairs:
                node_type = condition_node_type(curie)
                vocab = curie_vocabulary(curie)
                if node_type is None:
                    n_unroutable += 1
                    unresolved_conditions.add(
                        {
                            "signature_id": bsdb,
                            "source_id": curie,
                            "source_vocabulary": vocab,
                            "raw_condition": verbatim,
                            "pairing_method": paired.method,
                            "reason": "no node type for this vocabulary",
                            "source": SOURCE,
                        }
                    )
                    continue
                hub = mondo.mondo_id(curie)
                if hub is None:
                    no_mondo_terms.add(curie)
                key = hub or curie
                row_conditions[node_type].append(key)
                conditions[node_type].add(
                    {
                        "condition_id": key,
                        # MONDO's name where there is one; the source's own
                        # string is one observed spelling among several
                        # (MONDO:0002009 arrives as both `Major depressive
                        # disorder` and `Unipolar depression`).
                        "label": mondo.label_for(curie) or verbatim or curie,
                        "mondo_id": hub or "",
                        "mondo_label": mondo.label_for(curie) or "",
                        "source_id": curie,
                        "source_vocabulary": vocab,
                        "source_condition": verbatim,
                    }
                )
            for curie in paired.unpaired_ids:
                unresolved_conditions.add(
                    {
                        "signature_id": bsdb,
                        "source_id": curie,
                        "source_vocabulary": curie_vocabulary(curie),
                        "raw_condition": "",
                        "pairing_method": paired.method,
                        "reason": "no condition string could be paired to this id",
                        "source": SOURCE,
                    }
                )
            for text in paired.unpaired_labels:
                unresolved_conditions.add(
                    {
                        "signature_id": bsdb,
                        "source_id": "",
                        "source_vocabulary": "",
                        "raw_condition": text,
                        "pairing_method": paired.method,
                        "reason": "no id could be paired to this condition string",
                        "source": SOURCE,
                    }
                )

            site_label = na(row.get("Body site"))
            site_ids: list[str] = []
            for curie in split_curies(na(row.get("UBERON ID"))):
                site_ids.append(curie)
                bodysites.add(
                    {
                        "bodysite_id": curie,
                        "label": site_label or curie,
                        "source_id": curie,
                        "ontology": curie_vocabulary(curie),
                    }
                )
            if not site_ids and site_label:
                sid = slug(site_label, "site")
                if sid:
                    site_ids.append(sid)
                    bodysites.add(
                        {
                            "bodysite_id": sid,
                            "label": site_label,
                            "source_id": "",
                            "ontology": "",
                        }
                    )

            for node_type, keys in row_conditions.items():
                for key in keys:
                    sig_condition.add(
                        {
                            "signature_id": bsdb,
                            "condition_id": key,
                            "condition_type": node_type,
                        }
                    )
            for sid in site_ids:
                sig_bodysite.add({"signature_id": bsdb, "bodysite_id": sid})

            pairs = split_taxa(
                na(row.get("MetaPhlAn taxon names")), na(row.get("NCBI Taxonomy IDs"))
            )
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
                        tax_id=int(raw_id), rank_ceiling=rank_ceiling
                    )
                else:
                    res = idx.resolve(pretty or None, rank_ceiling=rank_ceiling)
                reported_name = (
                    pretty or idx.scientific_name.get(res.tax_id or -1) or raw_id
                )

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
                            "candidates": as_list(str(c) for c in res.candidates),
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

                for node_type, keys in row_conditions.items():
                    for key in keys:
                        assoc.add(
                            {
                                "tax_id": str(res.tax_id),
                                "condition_id": key,
                                "condition_type": node_type,
                                "direction": direction,
                                "study_design": design,
                                "evidence_level": level,
                                "sequencing_type": seq_type,
                                "statistical_test": stat,
                                "group_0_size": g0,
                                "group_1_size": g1,
                                "pmid": pmid,
                                # The interoperable half of the evidence
                                # contract: what kind of claim this is, and who
                                # made it. Constant for BugSigDB, derived from
                                # the source token rather than typed in, so the
                                # next source cannot pick up this one's answer.
                                "knowledge_level": ont.knowledge_level(SOURCE),
                                "agent_type": ont.agent_type(SOURCE),
                                "primary_source": SOURCE,
                                # The source's own primary key for this
                                # assertion — what makes the edge re-verifiable
                                # and diffable across a source refresh.
                                "source_record_id": bsdb,
                                "source_licence": ont.SOURCE_LICENCE.get(SOURCE, ""),
                                # The relation as the source words it, kept
                                # beside the normalised `direction` so the
                                # normalisation stays recoverable. Absent when
                                # the source reports no direction, so the gap
                                # is counted rather than papered over.
                                "source_relation": (
                                    f"abundance in group 1 {direction}"
                                    if direction
                                    else ""
                                ),
                                # Still the join key onto the Signature node,
                                # and deliberately outside the contract: the
                                # audited provenance field is `source_record_id`.
                                "signature_id": bsdb,
                                "study_id": study_id,
                                "host_species": host,
                                "body_site": site_ids[0] if site_ids else "",
                                "significance_threshold": na(
                                    row.get("Significance threshold")
                                ),
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
                    # G7 is "confounder control is schema, not metadata": all
                    # three columns are queryable per signature, so "which
                    # studies for disease Y controlled for medication" is one
                    # query (D11). 26 differentially abundant ASVs in T2D
                    # became 0 after matching on host variables, and this is
                    # the only surveyed source that records the fact at all.
                    "antibiotics_exclusion": na(row.get("Antibiotics exclusion")),
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

    cited_writer = store.table(
        "cited_taxa",
        ["tax_id", "source", "n_signatures"],
        key=("tax_id", "source"),
        merge=True,
        owner=("source", SOURCE),
    )
    for tid, n in sorted(cited.items()):
        cited_writer.add({"tax_id": str(tid), "source": SOURCE, "n_signatures": str(n)})

    counts = {
        w.name: store.put(w)
        for w in (
            studies,
            papers,
            *conditions.values(),
            bodysites,
            signatures,
            sig_condition,
            sig_bodysite,
            reported,
            reported_unres,
            unresolved_nodes,
            assoc,
            unresolved_conditions,
            cited_writer,
        )
    }

    n_terms = sum(len(w.seen) for w in conditions.values())
    print(
        f"\nread {n_rows:,} signature rows, {n_pairs:,} taxon mentions "
        f"({n_resolved:,} resolved, {n_pairs - n_resolved:,} unresolved)"
    )
    print(
        f"conditions: {n_terms:,} terms typed, {len(no_mondo_terms):,} of them "
        f"with no MONDO equivalence (own CURIE as key, mondo_id null); "
        f"{n_unroutable:,} mentions in vocabularies with no node type"
    )
    print(
        "  condition pairing: "
        + ", ".join(f"{m} {n:,}" for m, n in sorted(pairing_methods.items()))
    )
    for name, n in counts.items():
        print(f"  {name:34s} {n:>9,}")
    shared = {
        w.name: w.merged_in
        for w in (
            studies,
            papers,
            *conditions.values(),
            unresolved_nodes,
            assoc,
            unresolved_conditions,
            cited_writer,
        )
        if w.merged_in
    }
    if shared:
        print(
            "  merged into tables another source had written: "
            + ", ".join(f"{name} +{n:,}" for name, n in shared.items())
        )
    return counts

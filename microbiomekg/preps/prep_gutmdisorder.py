"""gutMDisorder's two workbooks -> the tables the build's store loads.

``human.xlsx`` and ``mouse.xlsx``, three sheets each, joined on one key with
three spellings: ``Literature.Index`` ← ``Sample.Index`` ←
``Association.index`` (lowercase ``i`` on Association, in both workbooks). One
Literature row is a study, 1–8 Sample rows are its arms, and 1–N Association
rows are the taxa it reports.

Everything below that is not obvious is a pitfall from
``docs/research/source-formats.md`` §1, and each is handled where it says:

* **The mouse workbook's index columns are floats with binary noise.**
  ``Sample.Index`` and ``Association.index`` hold ``63.0000000000001`` and
  ``33.9999999999999`` while ``Literature.Index`` is a clean int. An equality
  join drops 45 of 930 association rows; ``int()`` recovers all but one and
  maps ``33.9999999999999`` to **33**, attaching that association to the
  *wrong paper*. :func:`study_index` rounds, and **rejects** anything more than
  1e-6 from an integer to the ledger rather than guessing which paper it meant.
* **An Association row has no reference to a Sample row.** There is no arm key,
  so group sizes cannot be per-association the way BugSigDB's can. They are
  carried as the *study's* arm sizes with ``sample_size_scope`` saying so, and
  ``group_0_size``/``group_1_size`` are left empty — which the audit counts,
  correctly. Silently picking ``Sample Number == 1`` as the control would
  invent a fact.
* **Duplicate and self-contradicting association rows.** 22 fully identical
  human rows, 76 duplicate (index, gm id, alteration) triples, and 15
  (index, taxon) pairs carrying **both** directions. Exact duplicates collapse
  to one edge carrying ``duplicate_rows``; near-duplicates and both-direction
  pairs stay as separate edges, because G4 says disagreement is exposed and
  never resolved.
* **`DOID:00400085` is malformed** (8 digits, DOID ids are 1–7) and one human
  cell is comma-multivalued. Both go through :mod:`microbiomekg.conditions`,
  which routes DOIDs onto the MONDO hub — 11,258 DOID equivalences, the half of
  the hub BugSigDB's EFO ids could not use.
* **Two taxids are deleted and 16 are merged.** Both route through
  :mod:`microbiomekg.reconcile`, the same policy BugSigDB uses, so a taxon
  cited by both sources is one node.

The whole mouse workbook lands as ``in-vivo-model`` whatever its design (G6),
and ``study_design`` is empty on every edge because gutMDisorder records none —
``Research Type`` is a curation category, not a design, and writing it into the
design column would make the audit look better by misdescribing the data.
"""

from __future__ import annotations

import math
from collections import Counter, OrderedDict
from pathlib import Path

import pandas as pd

from microbiomekg import ontology as ont
from microbiomekg.conditions import (
    MondoIndex,
    condition_node_type,
    curie_vocabulary,
    malformed_curie,
    pair_conditions,
    split_curies,
)
from microbiomekg.ontology import gutmdisorder as gmd
from microbiomekg.rawdata import MissingInput, find_mondo, find_taxdump
from microbiomekg.reconcile import TaxonomyIndex
from microbiomekg.tables import Frames, as_list

SOURCE = gmd.SOURCE

#: The raw files this prep reads, relative to ``--raw``, in the layout
#: ``fetch`` writes. `status` reports on exactly these.
RAW_INPUTS: list[str] = [
    "gutmdisorder/human.xlsx",
    "gutmdisorder/mouse.xlsx",
    "mondo/mondo.obo",
]

#: Reads no other prep's table. ``prep_chembl`` reads *this* one's
#: ``intervention`` table and declares the dependency on its side.
DEPENDS_ON: list[str] = []

#: Workbook → the host every one of its rows is about. gutMDisorder's own
#: `Human/Mouse` column agrees with the file it is in, so the file is the fact.
HOST_SPECIES = {"human": "Homo sapiens", "mouse": "Mus musculus"}

#: How far an index may sit from an integer and still be that integer. The real
#: deviations are ~1e-13 (float noise from a spreadsheet round-trip); anything
#: larger is not noise, and there is no honest way to decide which study a row
#: numbered 2.5 belongs to.
INDEX_TOLERANCE = 1e-6

#: `Alteration` has exactly two values. Normalised so that `r.direction` means
#: the same thing on a gutMDisorder edge as on a BugSigDB one, with the source's
#: own sentence kept in `source_relation`.
DIRECTIONS = {"increase": "increased", "decrease": "decreased"}


def text(value) -> str:
    """A cell as a stripped string; NaN, ``None`` and whitespace become empty.

    gutMDisorder has no literal ``NA``/``N/A`` spellings — missing is genuinely
    empty — but pandas turns an empty cell into ``NaN``, and the store
    stringifies cells, so a ``NaN`` would land as the *string* ``"nan"``, which
    kglite would load as a value and the audit would count as present.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def study_index(value) -> int | None:
    """The join key, or ``None`` when the cell is not an integer.

    ``round()``, never ``int()``: truncation maps ``33.9999999999999`` to 33
    and attaches that association to the wrong paper — a silent wrong answer,
    and the worst failure this loader can produce.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    nearest = round(number)
    return int(nearest) if abs(number - nearest) <= INDEX_TOLERANCE else None


def slug(value: str) -> str:
    keep = [c if c.isalnum() else "-" for c in value.strip().lower()]
    return "-".join(part for part in "".join(keep).split("-") if part)


def study_key(workbook: str, index: int) -> str:
    return f"STUDY:{SOURCE}-{workbook}-{index}"


def as_int(value) -> str:
    """A cell as an integer string, or empty. Sample sizes are floats in the
    sheet (``13.0``) because the column has nulls."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return (
        str(int(round(number)))
        if abs(number - round(number)) <= INDEX_TOLERANCE
        else ""
    )


def as_float(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    try:
        return repr(float(value))
    except (TypeError, ValueError):
        return ""


ASSOCIATION_FIELDS = [
    # The evidence contract, in the order docs/model.md states it.
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
    # Context, deliberately outside the audited contract.
    "study_id",
    "host_species",
    "p_value",
    "research_type",
    "study_sample_size",
    "study_arm_sizes",
    "sample_size_scope",
    "reported_name",
    "reported_rank",
    "original_rank",
    "reported_tax_id",
    "resolution_status",
    "duplicate_rows",
]


class Sheets:
    """One workbook's three sheets, with the index column already resolved."""

    def __init__(self, path: Path, workbook: str):
        book = pd.ExcelFile(path)
        self.workbook = workbook
        self.literature = book.parse("Literature")
        self.sample = book.parse("Sample")
        self.association = book.parse("Association")
        self.bad_index: list[tuple[str, object]] = []

    def indexed(self, frame: pd.DataFrame, column: str, sheet: str):
        """Yield ``(index, row)``, sending non-integral index cells to the
        ledger instead of rounding them into some other study."""
        for _, row in frame.iterrows():
            index = study_index(row.get(column))
            if index is None:
                self.bad_index.append((sheet, row.get(column)))
                continue
            yield index, row


def run(
    raw: Path,
    store: Frames,
    *,
    workbooks: Path | None = None,
    taxdump: Path | None = None,
    mondo: Path | None = None,
    rank_ceiling: str = "species",
) -> dict[str, int]:
    """gutMDisorder's tables into ``store``; returns each table's row count.

    ``workbooks`` defaults to ``raw/gutmdisorder/`` (``human.xlsx``, ``mouse.xlsx``);
    ``mondo`` to ``raw/mondo/mondo.obo``. Raises :class:`MissingInput` when a
    workbook, ``mondo.obo`` or the taxdump is not there.
    """

    books = workbooks or (raw / SOURCE)
    missing = [w for w in HOST_SPECIES if not (books / f"{w}.xlsx").is_file()]
    if missing:
        # "This source's raw files are not on this machine" is a skip the build
        # reports, never a defect: the source leaves the blueprint rather than
        # declaring node types with nothing behind them.
        raise MissingInput(
            f"no {', '.join(w + '.xlsx' for w in missing)} under {books}"
        )
    try:
        mondo_path = find_mondo(raw, mondo)
        taxdump = taxdump or find_taxdump(raw)
    except FileNotFoundError as e:
        raise MissingInput(str(e)) from e

    print(f"reading {books}/{{human,mouse}}.xlsx", flush=True)
    print(f"loading taxdump from {taxdump} ...", flush=True)
    idx = TaxonomyIndex.from_taxdump(taxdump)
    print(f"  {len(idx.parent):,} taxa, {len(idx.names):,} name keys", flush=True)

    mondo = MondoIndex.from_obo(mondo_path)
    print(
        f"loaded MONDO: {len(mondo.label):,} live terms, "
        f"{len(mondo.equivalent):,} equivalences",
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
            "source",
            "workbook",
            "research_type",
            "intervention",
            "intervention_type",
            "conclusion",
            "host_species",
            "experiment_id",
            "n_arms",
            "sample_size_total",
            "arm_sizes",
            "sample_source",
            "sample_conditions",
            "sequencing_technology",
            "sequencing_platform",
        ],
        key="study_id",
        merge=True,
        owner=("source", SOURCE),
    )
    papers = store.table(
        "paper",
        ["pmid", "title", "journal", "year", "doi"],
        key="pmid",
        merge=True,
    )
    condition_fields = [
        "condition_id",
        "label",
        "mondo_id",
        "mondo_label",
        "source_id",
        "source_vocabulary",
        "source_condition",
    ]
    diseases = store.table("disease", condition_fields, key="condition_id", merge=True)
    interventions = store.table(
        "intervention",
        ["intervention_id", "label", "intervention_type", "drugbank_id", "source"],
        key="intervention_id",
        merge=True,
        owner=("source", SOURCE),
    )
    assoc = store.table(
        "taxon_condition",
        ["tax_id", "condition_id", "condition_type", *ASSOCIATION_FIELDS],
        dedupe_full=True,
        merge=True,
        owner=("primary_source", SOURCE),
    )
    changed_by = store.table(
        "taxon_intervention",
        ["tax_id", "intervention_id", *ASSOCIATION_FIELDS],
        dedupe_full=True,
        merge=True,
        owner=("primary_source", SOURCE),
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
    # C18's accounting, for the rows that become no edge at all. gutMDisorder
    # has no Signature node to hang an unresolved taxon off — BugSigDB's
    # tombstones are wired to theirs by REPORTED_BY — so the association it
    # would have carried is recorded here instead of vanishing.
    unresolved_assoc = store.table(
        "unresolved_associations",
        [
            "workbook",
            "study_index",
            "source_record_id",
            "reported_name",
            "reported_tax_id",
            "reason",
            "source",
        ],
        merge=True,
        owner=("source", SOURCE),
    )
    cited = store.table(
        "cited_taxa",
        ["tax_id", "source", "n_signatures"],
        key=("tax_id", "source"),
        merge=True,
        owner=("source", SOURCE),
    )

    counters: Counter[str] = Counter()
    taxa_seen: "OrderedDict[int, int]" = OrderedDict()
    unresolved_hits: Counter[str] = Counter()
    levels: Counter[str] = Counter()

    for workbook, host in HOST_SPECIES.items():
        sheets = Sheets(books / f"{workbook}.xlsx", workbook)

        # --- arms, grouped at study level: there is no per-association link
        arms: dict[int, list[pd.Series]] = {}
        for index, row in sheets.indexed(sheets.sample, "Index", "Sample"):
            arms.setdefault(index, []).append(row)

        # --- studies, their diseases and their interventions
        study_diseases: dict[int, list[str]] = {}
        study_interventions: dict[int, list[str]] = {}
        study_meta: dict[int, dict[str, str]] = {}
        for index, row in sheets.indexed(sheets.literature, "Index", "Literature"):
            key = study_key(workbook, index)
            counters["studies"] += 1
            group = arms.get(index, [])
            sizes = [as_int(a.get("Sample Size")) for a in group]
            technologies = [text(a.get("Sequencing Technology")) for a in group]
            technology = "; ".join(sorted({t for t in technologies if t}))
            research_type = text(row.get("Research Type"))
            pmid = as_int(row.get("PMID"))
            meta = {
                "study_id": key,
                "pmid": pmid,
                "research_type": research_type,
                "host_species": host,
                "sequencing_type": gmd.sequencing_type(technology),
                "evidence_level": gmd.evidence_level(
                    workbook, research_type, technology
                ),
                "sample_size_total": str(sum(int(s) for s in sizes if s))
                if any(sizes)
                else "",
                "arm_sizes": as_list(sizes),
            }
            study_meta[index] = meta
            levels[meta["evidence_level"]] += 1

            studies.add(
                {
                    "study_id": key,
                    "study_number": str(index),
                    "title": text(row.get("Title")),
                    "journal": text(row.get("Journal")),
                    "year": "",
                    "doi": "",
                    "url": text(row.get("Experiment web site")),
                    "authors": text(row.get("Authors")),
                    "keywords": "",
                    "pmid": pmid,
                    "pmid_raw": text(row.get("PMID")),
                    "source": SOURCE,
                    "workbook": workbook,
                    "research_type": research_type,
                    "intervention": text(row.get("Intervention")),
                    "intervention_type": text(row.get("Intervention Type")),
                    "conclusion": text(row.get("Conclusion")),
                    "host_species": host,
                    "experiment_id": text(row.get("Experiment ID")),
                    "n_arms": str(len(group)),
                    "sample_size_total": meta["sample_size_total"],
                    "arm_sizes": meta["arm_sizes"],
                    "sample_source": "; ".join(
                        sorted(
                            {
                                text(a.get("Sample Source"))
                                for a in group
                                if text(a.get("Sample Source"))
                            }
                        )
                    ),
                    "sample_conditions": "; ".join(
                        sorted(
                            {
                                text(a.get("Condition"))
                                for a in group
                                if text(a.get("Condition"))
                            }
                        )
                    ),
                    "sequencing_technology": technology,
                    "sequencing_platform": "; ".join(
                        sorted(
                            {
                                text(a.get("Sequencing Platform"))
                                for a in group
                                if text(a.get("Sequencing Platform"))
                            }
                        )
                    ),
                }
            )
            if pmid:
                papers.add(
                    {
                        "pmid": pmid,
                        "title": text(row.get("Title")),
                        "journal": text(row.get("Journal")),
                        "year": "",
                        "doi": "",
                    }
                )
                counters["papers"] += 1

            # --- the disease endpoint, through the MONDO hub
            #
            # The same pairing policy BugSigDB's condition column uses, for the
            # same reason: exactly one human cell is `DOID:8878,DOID:8577`
            # against `Disorder Name` = "Crohn's disease,ulcerative colitis",
            # and the two columns must not be zipped when they disagree on
            # length. One module decides this for every source.
            disorder = text(row.get("Disorder Name"))
            paired = pair_conditions(
                split_curies(text(row.get("DOID"))), disorder, mondo
            )
            keys: list[str] = []
            for curie, verbatim in paired.pairs:
                if malformed_curie(curie):
                    counters["malformed_doid"] += 1
                    unresolved_conditions.add(
                        {
                            "signature_id": key,
                            "source_id": curie,
                            "source_vocabulary": curie_vocabulary(curie),
                            "raw_condition": verbatim,
                            "pairing_method": paired.method,
                            "reason": "malformed id for its vocabulary",
                            "source": SOURCE,
                        }
                    )
                    continue
                if condition_node_type(curie) != "Disease":
                    counters["unroutable_condition"] += 1
                    unresolved_conditions.add(
                        {
                            "signature_id": key,
                            "source_id": curie,
                            "source_vocabulary": curie_vocabulary(curie),
                            "raw_condition": verbatim,
                            "pairing_method": paired.method,
                            "reason": "no Disease node type for this vocabulary",
                            "source": SOURCE,
                        }
                    )
                    continue
                hub = mondo.mondo_id(curie)
                if hub is None:
                    counters["doid_without_mondo"] += 1
                node = hub or curie
                keys.append(node)
                # MONDO's own name wins wherever there is one; the source's
                # string is one observed spelling among several and is kept in
                # `source_condition` either way.
                diseases.add(
                    {
                        "condition_id": node,
                        "label": mondo.label_for(curie) or verbatim or curie,
                        "mondo_id": hub or "",
                        "mondo_label": mondo.label_for(curie) or "",
                        "source_id": curie,
                        "source_vocabulary": curie_vocabulary(curie),
                        "source_condition": verbatim,
                    }
                )
            for curie in paired.unpaired_ids:
                counters["unpaired_condition"] += 1
                unresolved_conditions.add(
                    {
                        "signature_id": key,
                        "source_id": curie,
                        "source_vocabulary": curie_vocabulary(curie),
                        "raw_condition": "",
                        "pairing_method": paired.method,
                        "reason": "no disorder name could be paired to this id",
                        "source": SOURCE,
                    }
                )
            for spare in paired.unpaired_labels:
                counters["unpaired_condition"] += 1
                unresolved_conditions.add(
                    {
                        "signature_id": key,
                        "source_id": "",
                        "source_vocabulary": "",
                        "raw_condition": spare,
                        "pairing_method": paired.method,
                        "reason": "no id could be paired to this disorder name",
                        "source": SOURCE,
                    }
                )
            study_diseases[index] = keys

            name = text(row.get("Intervention"))
            if name:
                iid = f"INTERVENTION:{slug(name)}"
                interventions.add(
                    {
                        "intervention_id": iid,
                        "label": name,
                        "intervention_type": text(row.get("Intervention Type")),
                        "drugbank_id": text(row.get("Intervention ID")),
                        "source": SOURCE,
                    }
                )
                study_interventions[index] = [iid]

        # --- associations. Exact duplicates are counted, not repeated.
        rows: "OrderedDict[tuple, list]" = OrderedDict()
        for index, row in sheets.indexed(sheets.association, "index", "Association"):
            signature = (
                index,
                text(row.get("Gut Microbiota")),
                text(row.get("Gut Microbiata ID")),
                text(row.get("Gut Microbiata NCBI ID")),
                text(row.get("Classification")),
                as_float(row.get("P Value")),
                text(row.get("Statistical Method")),
                text(row.get("Description")),
                text(row.get("Alteration")),
            )
            counters["association_rows"] += 1
            if signature in rows:
                rows[signature][1] += 1
                counters["duplicate_rows"] += 1
            else:
                rows[signature] = [row, 1]

        for signature, (row, repeats) in rows.items():
            index = signature[0]
            meta = study_meta.get(index)
            record = f"{SOURCE}:{workbook}:{index}:{signature[2] or signature[1]}"
            reported_name = text(row.get("Gut Microbiota"))
            raw_id = as_int(row.get("Gut Microbiata NCBI ID"))
            if meta is None:
                counters["association_without_study"] += 1
                unresolved_assoc.add(
                    {
                        "workbook": workbook,
                        "study_index": str(index),
                        "source_record_id": record,
                        "reported_name": reported_name,
                        "reported_tax_id": raw_id,
                        "reason": "no Literature row carries this index",
                        "source": SOURCE,
                    }
                )
                continue

            if raw_id:
                res = idx.resolve(tax_id=int(raw_id), rank_ceiling=rank_ceiling)
            else:
                res = idx.resolve(reported_name or None, rank_ceiling=rank_ceiling)
            if res.tax_id is None:
                counters["unresolved_taxa"] += 1
                uid = f"unresolved:{SOURCE}:{raw_id or slug(reported_name)}"
                unresolved_nodes.add(
                    {
                        "unresolved_id": uid,
                        "raw_name": reported_name or raw_id,
                        "reported_rank": text(row.get("Classification")),
                        "original_rank": res.original_rank or "",
                        "reported_tax_id": raw_id,
                        "source": SOURCE,
                        "status": res.status,
                        "candidates": as_list(str(c) for c in res.candidates),
                        "note": res.note,
                        "n_signatures": "0",
                    }
                )
                unresolved_hits[uid] += 1
                unresolved_assoc.add(
                    {
                        "workbook": workbook,
                        "study_index": str(index),
                        "source_record_id": record,
                        "reported_name": reported_name,
                        "reported_tax_id": raw_id,
                        "reason": f"taxon {res.status}: {res.note}",
                        "source": SOURCE,
                    }
                )
                continue

            direction = DIRECTIONS.get(text(row.get("Alteration")).casefold(), "")
            edge = {
                "direction": direction,
                # gutMDisorder records no study design; `Research Type` is a
                # curation category, not a design (module docstring). The gap
                # is counted instead, which is what the audit is for.
                "study_design": "",
                "evidence_level": meta["evidence_level"],
                "sequencing_type": meta["sequencing_type"],
                "statistical_test": text(row.get("Statistical Method")),
                # Empty, deliberately: an Association row has no link to a
                # Sample row, so no per-association size exists. The study's
                # arms are carried below, scoped by `sample_size_scope`.
                "group_0_size": "",
                "group_1_size": "",
                "pmid": meta["pmid"],
                "knowledge_level": ont.knowledge_level(SOURCE),
                "agent_type": ont.agent_type(SOURCE),
                "primary_source": SOURCE,
                "source_record_id": record,
                "source_licence": ont.SOURCE_LICENCE.get(SOURCE, ""),
                # The source's own sentence about this result, kept verbatim
                # beside the two-valued `direction` so the normalisation stays
                # reversible.
                "source_relation": text(row.get("Description")),
                "study_id": meta["study_id"],
                "host_species": meta["host_species"],
                "p_value": as_float(row.get("P Value")),
                "research_type": meta["research_type"],
                "study_sample_size": meta["sample_size_total"],
                "study_arm_sizes": meta["arm_sizes"],
                "sample_size_scope": "study-level (not per-association)",
                "reported_name": reported_name,
                "reported_rank": text(row.get("Classification")),
                "original_rank": res.original_rank or "",
                "reported_tax_id": raw_id,
                "resolution_status": res.status,
                "duplicate_rows": str(repeats),
            }

            taxa_seen[res.tax_id] = taxa_seen.get(res.tax_id, 0) + 1
            targets = 0
            for condition in study_diseases.get(index, []):
                # Every gutMDisorder condition is disease-coded: the source's
                # own column is a disease name and `condition_node_type` has
                # routed all 1,636 of them to `Disease`. The column is still
                # written rather than assumed, because it is what the loader
                # reads to pick this row's target type.
                assoc.add(
                    {
                        "tax_id": str(res.tax_id),
                        "condition_id": condition,
                        "condition_type": "Disease",
                        **edge,
                    }
                )
                counters["associated_with"] += 1
                targets += 1
            for iid in study_interventions.get(index, []):
                changed_by.add(
                    {"tax_id": str(res.tax_id), "intervention_id": iid, **edge}
                )
                counters["abundance_changed_by"] += 1
                targets += 1
            if not targets:
                counters["association_without_endpoint"] += 1
                unresolved_assoc.add(
                    {
                        "workbook": workbook,
                        "study_index": str(index),
                        "source_record_id": record,
                        "reported_name": reported_name,
                        "reported_tax_id": raw_id,
                        "reason": "study has neither a usable DOID nor an intervention",
                        "source": SOURCE,
                    }
                )

        for sheet, value in sheets.bad_index:
            counters["non_integral_index"] += 1
            unresolved_assoc.add(
                {
                    "workbook": workbook,
                    "study_index": text(value),
                    "source_record_id": "",
                    "reported_name": "",
                    "reported_tax_id": "",
                    "reason": f"{sheet} row index is not an integer within "
                    f"{INDEX_TOLERANCE:g} — rounding it would attach the row "
                    f"to some other study",
                    "source": SOURCE,
                }
            )

    for row in unresolved_nodes.rows:
        if row["source"] == SOURCE:
            row["n_signatures"] = str(unresolved_hits.get(row["unresolved_id"], 0))
    for tid, n in sorted(taxa_seen.items()):
        cited.add({"tax_id": str(tid), "source": SOURCE, "n_signatures": str(n)})

    tables = (
        studies,
        papers,
        diseases,
        interventions,
        assoc,
        changed_by,
        unresolved_nodes,
        unresolved_conditions,
        unresolved_assoc,
        cited,
    )
    counts = {w.name: store.put(w) for w in tables}

    print(
        f"\nread {counters['association_rows']:,} association rows across "
        f"{counters['studies']:,} studies "
        f"({counters['duplicate_rows']:,} exact duplicates collapsed)"
    )
    print(
        f"  edges: {counters['associated_with']:,} ASSOCIATED_WITH, "
        f"{counters['abundance_changed_by']:,} ABUNDANCE_CHANGED_BY"
    )
    print(
        f"  not loaded: {counters['association_without_endpoint']:,} rows whose "
        f"study has no DOID and no intervention, "
        f"{counters['unresolved_taxa']:,} unresolved taxa, "
        f"{counters['non_integral_index']:,} non-integral index cells, "
        f"{counters['association_without_study']:,} orphan indexes"
    )
    print(
        f"  conditions: {counters['malformed_doid']:,} malformed DOIDs, "
        f"{counters['doid_without_mondo']:,} DOID mentions with no MONDO "
        f"equivalence (own CURIE as key)"
    )
    print(
        "  evidence levels: "
        + ", ".join(f"{lvl} {n:,}" for lvl, n in sorted(levels.items()))
    )
    for name, n in counts.items():
        print(f"  {name:34s} {n:>9,}")
    shared = {w.name: w.merged_in for w in tables if w.merged_in}
    if shared:
        print(
            "  merged into tables another source had written: "
            + ", ".join(f"{name} +{n:,}" for name, n in shared.items())
        )
    return counts

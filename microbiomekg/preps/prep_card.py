#!/usr/bin/env python3
"""CARD's model store and ARO ontology -> the flat CSVs blueprint.json loads.

Two directories from one download and two licences: ``card-data/card.json`` is
the model store (© McMaster, non-commercial) and ``card-ontology/aro.obo`` is
the term graph (CC BY 4.0). This script reads exactly three files —
``card.json``, ``aro_index.tsv`` and ``PMID.tsv`` from the first, ``aro.obo``
from the second — and writes six tables plus two ledgers.

Everything below that is not obvious is a pitfall from
``docs/research/source-formats.md`` §3, and each is handled where it says:

* **``card.json`` is the model authority, not ``aro_index.tsv``.** They
  disagree about 84 models in the same tarball: 48 are in the index and absent
  from the JSON, 36 are in the JSON and absent from the index. The JSON wins
  because it is the only file with the taxids, and because those 36 are exactly
  the 36 meta-models — dropping them would drop a whole model *type*. The
  index is read only to detect the disagreement, which goes to
  ``card_model_disagreements.csv`` rather than being resolved silently.
* **The ARO accession is bare in the JSON and prefixed everywhere else.**
  :func:`aro_id` normalises on read; without it every determinant is two nodes
  and no citation reaches either.
* **``ARO Accession`` is duplicated on 5 rows of ``aro_index.tsv``** — the same
  term under two model ids. It is *not* duplicated in ``card.json`` (6,451
  accessions over 6,451 models), which is the second reason to key on the JSON.
* **``aro.obo`` is the naming authority.** It names all 6,451 model terms and
  all 587 categories, it is the redistributable half, and its ``is_a`` lines
  are the only hierarchy in the download. Where it and ``card.json`` disagree
  about a name the OBO wins and the disagreement is written to the same ledger.
  (On the 2026-08-11 release they never disagree; the ledger is the detector,
  not a prediction.)
* **The taxon is the reference sequence's organism.** Every carriage edge
  carries ``sequence_derived``, ``taxon_scope`` and ``taxon_specificity``, and
  the last of those is read off the *lineage* because a plasmid's NCBI rank is
  ``species`` (see :func:`microbiomekg.ontology.card.taxon_specificity`).
* **CARD's own taxon labels are not NCBI's.** ``ncbi_taxonomy.obo`` renames
  ``NCBITaxon:2``, and so does ``card.json``'s ``NCBI_taxonomy_name`` on all 132
  taxid-2 models. Nothing here reads a taxon *name* from CARD: the node comes
  from the taxdump and CARD's string is kept on the edge as ``reported_name``.
* **Splitting ``PMID.tsv`` yields empty atoms** from leading and trailing
  semicolons (21 in the real file). :func:`split_pmids` drops them.

CARD curates no taxon–disease association, so this script writes nothing into
``taxon_condition.csv``. What it shares with the other sources is
``cited_taxa.csv`` (which decides what the taxonomy build keeps) and
``unresolved_taxa.csv`` / ``unresolved_associations.csv`` (C18's accounting).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

from microbiomekg import ontology as ont
from microbiomekg.ontology import card
from microbiomekg.rawdata import find_taxdump, missing_input
from microbiomekg.reconcile import TaxonomyIndex
from microbiomekg.tables import Writer, as_list

SOURCE = card.SOURCE

#: Reads no other prep's table. It contributes to ``cited_taxa.csv``, which
#: is why ``prep_taxonomy`` declares *this* script rather than the reverse.
DEPENDS_ON: list[str] = []

#: ARO category class names, and the table each one lands in. ``AMR Gene
#: Family`` has no table: it is a classification *of* the determinant that
#: nothing joins to, so it stays a property (docs/model.md §1).
DRUG_CLASS = "Drug Class"
MECHANISM = "Resistance Mechanism"
GENE_FAMILY = "AMR Gene Family"

#: ``aro.obo`` ``def:`` lines carry their references as ``[PMID:123, ...]``.
_DEF_PMID = re.compile(r"PMID:(\d+)")


def aro_id(value: str | None) -> str:
    """``3002999`` or ``ARO:3002999`` -> ``ARO:3002999``.

    ``card.json`` stores the accession bare; ``aro_index.tsv``, ``PMID.tsv``
    and ``aro.obo`` store it prefixed. Joining the four without normalising
    produces a graph in which every determinant is two nodes.
    """
    text = (value or "").strip()
    if not text:
        return ""
    return text if text.startswith("ARO:") else f"ARO:{text}"


def split_pmids(cell: str | None) -> list[str]:
    """Split a ``PMID.tsv`` cell, dropping the atoms the split invents.

    961 rows are ``;``-multivalued and some carry a leading or trailing
    separator, which a bare ``split(";")`` turns into empty strings — 21 of
    them in the real file. An empty ``pmid`` is not a citation, and one written
    through would make the audit count a gap as filled.
    """
    if not cell:
        return []
    out: list[str] = []
    for atom in str(cell).split(";"):
        text = atom.strip()
        if text and text not in out:
            out.append(text)
    return out


def parse_obo(path: Path) -> dict[str, dict[str, list[str]]]:
    """``aro.obo`` -> ``{term id: {tag: [values]}}``.

    Deliberately minimal: this reads ``name``, ``def`` and ``is_a`` and ignores
    everything else. A full OBO parser would be a dependency and a second
    vocabulary to keep true; what the graph needs from the CC BY 4.0 half is
    the name, the citation and the parent pointer.
    """
    terms: dict[str, dict[str, list[str]]] = {}
    current: dict[str, list[str]] | None = None
    in_term = False
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line.startswith("[") and line.endswith("]"):
                _stash(terms, current)
                in_term = line == "[Term]"
                current = {} if in_term else None
                continue
            if not in_term or current is None:
                continue
            if not line.strip():
                _stash(terms, current)
                in_term, current = False, None
                continue
            tag, _, value = line.partition(": ")
            current.setdefault(tag, []).append(value)
    _stash(terms, current)
    return terms


def _stash(terms: dict, current: dict | None) -> None:
    if current and current.get("id"):
        terms[current["id"][0].strip()] = current


def obo_name(terms: dict, term_id: str) -> str:
    values = terms.get(term_id, {}).get("name", [])
    return values[0].strip() if values else ""


def obo_parents(terms: dict, term_id: str) -> list[str]:
    """The term's ``is_a`` parents, ids only (an OBO line is ``id ! name``)."""
    return [
        line.split("!")[0].strip() for line in terms.get(term_id, {}).get("is_a", [])
    ]


def obo_pmids(terms: dict, term_id: str) -> list[str]:
    """PMIDs from the term's ``def:`` dbxref bracket.

    ``aro.obo`` carries 3,459 distinct PMIDs there against ``PMID.tsv``'s
    3,543, and the two sets are not nested — a determinant may be cited in one
    and not the other, so both are read and the union is what the edge shows.
    """
    out: list[str] = []
    for value in terms.get(term_id, {}).get("def", []):
        for pmid in _DEF_PMID.findall(value):
            if pmid not in out:
                out.append(pmid)
    return out


def categories(model: dict, class_name: str) -> list[tuple[str, str]]:
    """``(ARO id, name)`` of a model's categories of one class, in file order."""
    out: list[tuple[str, str]] = []
    for entry in (model.get("ARO_category") or {}).values():
        if entry.get("category_aro_class_name") == class_name:
            out.append(
                (
                    aro_id(entry.get("category_aro_accession")),
                    (entry.get("category_aro_name") or "").strip(),
                )
            )
    return out


def reference_sequence(model: dict) -> dict:
    """The model's single reference sequence, or ``{}`` for a meta-model.

    6,415 of 6,451 models have exactly **one** sequence and no model has more
    than one distinct taxon, so "the" sequence is well defined; the 36 without
    one are the efflux-pump and gene-cluster meta-models.
    """
    sequences = (model.get("model_sequences") or {}).get("sequence") or {}
    for entry in sequences.values():
        if entry.get("NCBI_taxonomy"):
            return entry
    return {}


#: Every column a CARD edge carries: the eight-property contract
#: (:data:`microbiomekg.ontology.card.CARD_EVIDENCE_CONTRACT`) plus the model
#: context that is not evidence.
EDGE_FIELDS = [
    *card.CARD_EVIDENCE_CONTRACT,
    "card_model_id",
    "model_type",
    "curated",
    "publications",
    "n_publications",
]

#: The carriage edge adds what the taxon resolution learned, and the three
#: properties that say what the edge actually claims.
CARRIES_FIELDS = [
    *EDGE_FIELDS,
    "sequence_derived",
    "taxon_scope",
    "taxon_specificity",
    "reported_name",
    "reported_tax_id",
    "resolution_status",
    "original_rank",
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", type=Path, default=Path("data/raw"))
    ap.add_argument(
        "--card",
        type=Path,
        default=None,
        help="Directory holding card-data/ and card-ontology/ (default: <raw>/card).",
    )
    ap.add_argument("--taxdump", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=Path("data/csv"))
    ap.add_argument("--rank-ceiling", default="species")
    args = ap.parse_args(argv)

    root = args.card or (args.raw / SOURCE)
    models_path = root / "card-data" / "card.json"
    index_path = root / "card-data" / "aro_index.tsv"
    pmid_path = root / "card-data" / "PMID.tsv"
    obo_path = root / "card-ontology" / "aro.obo"
    missing = [
        p for p in (models_path, index_path, pmid_path, obo_path) if not p.is_file()
    ]
    if missing:
        # Exit 3, not 2: "this source's raw files are not on this machine" is a
        # different fact from "this script was called wrong", and
        # scripts/build.py acts on the difference by skipping the source and
        # leaving it out of the blueprint rather than declaring an empty one.
        print(f"missing {', '.join(str(p) for p in missing)}", file=sys.stderr)
        return 3
    try:
        taxdump = args.taxdump or find_taxdump(args.raw)
    except FileNotFoundError as e:
        return missing_input(e)

    print(f"reading {models_path}", flush=True)
    document = json.loads(models_path.read_text(encoding="utf-8"))
    version = document.get("_version", "")
    models = {k: v for k, v in document.items() if not k.startswith("_")}
    print(f"  CARD {version}: {len(models):,} models", flush=True)

    terms = parse_obo(obo_path)
    print(f"  aro.obo: {len(terms):,} terms", flush=True)

    citations: dict[str, list[str]] = {}
    with pmid_path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            citations[aro_id(row.get("ARO Accession"))] = split_pmids(row.get("PMID"))

    index_models: dict[str, str] = {}
    with index_path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            index_models[(row.get("Model ID") or "").strip()] = aro_id(
                row.get("ARO Accession")
            )

    print(f"loading taxdump from {taxdump} ...", flush=True)
    idx = TaxonomyIndex.from_taxdump(taxdump)
    print(f"  {len(idx.parent):,} taxa, {len(idx.names):,} name keys", flush=True)

    out = args.out
    genes = Writer(
        out / "resistance_gene.csv",
        [
            "aro_id",
            "name",
            "card_short_name",
            "description",
            "gene_family",
            "gene_family_aro",
            "model_type",
            "card_model_id",
            "curated",
            "protein_accession",
            "dna_accession",
            "aro_parents",
            "name_source",
            "publications",
            "n_publications",
            "source",
            "source_licence",
        ],
        key="aro_id",
        merge=True,
        owner=("source", SOURCE),
    )
    drug_classes = Writer(
        out / "drug_class.csv",
        ["drug_class_id", "label", "aro_parents", "source", "source_licence"],
        key="drug_class_id",
        merge=True,
        owner=("source", SOURCE),
    )
    mechanisms = Writer(
        out / "resistance_mechanism.csv",
        ["mechanism_id", "label", "aro_parents", "source", "source_licence"],
        key="mechanism_id",
        merge=True,
        owner=("source", SOURCE),
    )
    confers = Writer(
        out / "resistance_gene_drug_class.csv",
        ["aro_id", "drug_class_id", *EDGE_FIELDS],
        dedupe_full=True,
        merge=True,
        owner=("primary_source", SOURCE),
    )
    via = Writer(
        out / "resistance_gene_mechanism.csv",
        ["aro_id", "mechanism_id", *EDGE_FIELDS],
        dedupe_full=True,
        merge=True,
        owner=("primary_source", SOURCE),
    )
    carries = Writer(
        out / "taxon_resistance_gene.csv",
        ["tax_id", "aro_id", *CARRIES_FIELDS],
        dedupe_full=True,
        merge=True,
        owner=("primary_source", SOURCE),
    )
    unresolved_nodes = Writer(
        out / "unresolved_taxa.csv",
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
    # C18's accounting, shared with the other sources: a model that becomes no
    # carriage edge is recorded here rather than vanishing into the difference
    # between 6,451 models and 6,415 edges.
    unresolved_assoc = Writer(
        out / "unresolved_associations.csv",
        ["source_record_id", "reported_name", "reported_tax_id", "reason", "source"],
        merge=True,
        owner=("source", SOURCE),
    )
    # The source contradicting itself, which is neither a dropped row nor a
    # resolution — it is a fact about the release, and it is reportable.
    disagreements = Writer(
        out / "card_model_disagreements.csv",
        ["model_id", "aro_id", "kind", "card_json", "aro_index", "source"],
        dedupe_full=True,
    )
    cited = Writer(
        out / "cited_taxa.csv",
        ["tax_id", "source", "n_signatures"],
        key=("tax_id", "source"),
        merge=True,
        owner=("source", SOURCE),
    )

    counters: Counter[str] = Counter()
    levels: Counter[str] = Counter()
    specificity: Counter[str] = Counter()
    taxa_seen: "OrderedDict[int, int]" = OrderedDict()
    unresolved_hits: Counter[str] = Counter()
    seen_classes: dict[str, str] = {}
    seen_mechanisms: dict[str, str] = {}

    # --- the 84: which models each file has that the other does not
    for model_id in sorted(set(index_models) - set(models), key=_as_int):
        counters["index_only"] += 1
        disagreements.add(
            {
                "model_id": model_id,
                "aro_id": index_models[model_id],
                "kind": "absent-from-card.json",
                "card_json": "",
                "aro_index": index_models[model_id],
                "source": SOURCE,
            }
        )
    for model_id in sorted(set(models) - set(index_models), key=_as_int):
        counters["json_only"] += 1
        disagreements.add(
            {
                "model_id": model_id,
                "aro_id": aro_id(models[model_id]["ARO_accession"]),
                "kind": "absent-from-aro_index.tsv",
                "card_json": aro_id(models[model_id]["ARO_accession"]),
                "aro_index": "",
                "source": SOURCE,
            }
        )

    for model_id in sorted(models, key=_as_int):
        model = models[model_id]
        term = aro_id(model.get("ARO_accession"))
        counters["models"] += 1

        # aro.obo is the naming authority: it is the CC BY 4.0 half, it covers
        # every model term, and a name taken from it can be redistributed.
        card_name = (model.get("ARO_name") or "").strip()
        ontology_name = obo_name(terms, term)
        if ontology_name and card_name and ontology_name != card_name:
            counters["name_disagreement"] += 1
            disagreements.add(
                {
                    "model_id": model_id,
                    "aro_id": term,
                    "kind": "name-differs",
                    "card_json": card_name,
                    "aro_index": ontology_name,
                    "source": SOURCE,
                }
            )
        name = ontology_name or card_name
        name_source = "aro.obo" if ontology_name else "card.json"

        sequence = reference_sequence(model)
        curated = bool(sequence)
        level = card.evidence_level(curated)
        levels[level] += 1
        if not curated:
            counters["meta_models"] += 1

        publications = citations.get(term, [])
        for pmid in obo_pmids(terms, term):
            if pmid not in publications:
                publications.append(pmid)
                counters["pmid_only_in_obo"] += 1
        if publications:
            counters["models_with_citation"] += 1

        family = categories(model, GENE_FAMILY)
        genes.add(
            {
                "aro_id": term,
                "name": name,
                "card_short_name": (model.get("CARD_short_name") or "").strip(),
                "description": (model.get("ARO_description") or "").strip(),
                "gene_family": as_list(n for _, n in family),
                "gene_family_aro": as_list(a for a, _ in family),
                "model_type": (model.get("model_type") or "").strip(),
                "card_model_id": model_id,
                "curated": "true" if curated else "false",
                "protein_accession": (sequence.get("protein_sequence") or {}).get(
                    "accession", ""
                ),
                "dna_accession": (sequence.get("dna_sequence") or {}).get(
                    "accession", ""
                ),
                "aro_parents": as_list(obo_parents(terms, term)),
                "name_source": name_source,
                "publications": as_list(publications),
                "n_publications": str(len(publications)),
                "source": SOURCE,
                # The node's own facts — name, parents — are aro.obo's, and that
                # half is redistributable whatever the edges built from card.json
                # are.
                "source_licence": card.ONTOLOGY_LICENCE,
            }
        )

        edge = {
            "evidence_level": level,
            # Single-valued because the contract's column is an int. It is *a*
            # citation for this determinant, not a claim to be the principal
            # one; `publications` carries the whole set.
            "pmid": publications[0] if publications else "",
            "knowledge_level": card.knowledge_level(len(publications)),
            "agent_type": ont.agent_type(SOURCE),
            "primary_source": SOURCE,
            # The curated record is the model, so G10's expansion factor reads
            # "13 drug-class edges from 1 record" rather than 13 records.
            "source_record_id": f"{SOURCE}:model:{model_id}",
            "source_licence": "",
            "source_relation": "",
            "card_model_id": model_id,
            "model_type": (model.get("model_type") or "").strip(),
            "curated": "true" if curated else "false",
            "publications": as_list(publications),
            "n_publications": str(len(publications)),
        }

        for accession, label in categories(model, DRUG_CLASS):
            if accession not in seen_classes:
                seen_classes[accession] = label
                drug_classes.add(
                    {
                        "drug_class_id": accession,
                        "label": obo_name(terms, accession) or label,
                        "aro_parents": as_list(obo_parents(terms, accession)),
                        "source": SOURCE,
                        "source_licence": card.ONTOLOGY_LICENCE,
                    }
                )
            also = _stated_in_obo(
                terms, term, "confers_resistance_to_drug_class", accession
            )
            confers.add(
                {
                    "aro_id": term,
                    "drug_class_id": accession,
                    **edge,
                    "source_licence": card.licence_for(also),
                    "source_relation": (
                        "aro.obo:confers_resistance_to_drug_class"
                        if also
                        else "card.json:ARO_category:Drug Class"
                    ),
                }
            )
            counters["confers_resistance_to"] += 1

        for accession, label in categories(model, MECHANISM):
            if accession not in seen_mechanisms:
                seen_mechanisms[accession] = label
                mechanisms.add(
                    {
                        "mechanism_id": accession,
                        "label": obo_name(terms, accession) or label,
                        "aro_parents": as_list(obo_parents(terms, accession)),
                        "source": SOURCE,
                        "source_licence": card.ONTOLOGY_LICENCE,
                    }
                )
            via.add(
                {
                    "aro_id": term,
                    "mechanism_id": accession,
                    **edge,
                    "source_licence": card.DATA_LICENCE,
                    "source_relation": "card.json:ARO_category:Resistance Mechanism",
                }
            )
            counters["via_mechanism"] += 1

        if not curated:
            counters["without_reference_sequence"] += 1
            unresolved_assoc.add(
                {
                    "source_record_id": edge["source_record_id"],
                    "reported_name": name,
                    "reported_tax_id": "",
                    "reason": f"{model.get('model_type')} has no reference sequence, "
                    f"so no organism to attach it to",
                    "source": SOURCE,
                }
            )
            continue

        taxonomy = sequence.get("NCBI_taxonomy") or {}
        raw_id = (taxonomy.get("NCBI_taxonomy_id") or "").strip()
        # CARD's own label for the taxon, kept on the edge and never used to
        # look anything up: on all 132 taxid-2 models it is the curation string
        # "Bacteria, Viruses, Fungi, and other genome sequence associated with
        # antimicrobial resistance", which is not a taxon name.
        reported_name = (taxonomy.get("NCBI_taxonomy_name") or "").strip()
        resolution = idx.resolve(tax_id=int(raw_id), rank_ceiling=args.rank_ceiling)
        if resolution.tax_id is None:
            counters["unresolved_taxa"] += 1
            uid = f"unresolved:{SOURCE}:{raw_id}"
            unresolved_nodes.add(
                {
                    "unresolved_id": uid,
                    "raw_name": reported_name or raw_id,
                    "reported_rank": "",
                    "original_rank": resolution.original_rank or "",
                    "reported_tax_id": raw_id,
                    "source": SOURCE,
                    "status": resolution.status,
                    "candidates": "|".join(str(c) for c in resolution.candidates),
                    "note": resolution.note,
                    "n_signatures": "0",
                }
            )
            unresolved_hits[uid] += 1
            unresolved_assoc.add(
                {
                    "source_record_id": edge["source_record_id"],
                    "reported_name": reported_name,
                    "reported_tax_id": raw_id,
                    "reason": f"taxon {resolution.status}: {resolution.note}",
                    "source": SOURCE,
                }
            )
            continue

        scope = card.taxon_specificity(
            idx.rank.get(resolution.tax_id), idx.lineage(resolution.tax_id)
        )
        specificity[scope] += 1
        carries.add(
            {
                "tax_id": str(resolution.tax_id),
                "aro_id": term,
                **edge,
                "source_licence": card.DATA_LICENCE,
                "source_relation": "card.json:model_sequences.NCBI_taxonomy",
                "sequence_derived": "true",
                "taxon_scope": "reference-sequence-organism",
                "taxon_specificity": scope,
                "reported_name": reported_name,
                "reported_tax_id": raw_id,
                "resolution_status": resolution.status,
                "original_rank": resolution.original_rank or "",
            }
        )
        counters["carries_resistance_gene"] += 1
        taxa_seen[resolution.tax_id] = taxa_seen.get(resolution.tax_id, 0) + 1

    for row in unresolved_nodes.rows:
        if row["source"] == SOURCE:
            row["n_signatures"] = str(unresolved_hits.get(row["unresolved_id"], 0))
    for tid, n in sorted(taxa_seen.items()):
        cited.add({"tax_id": str(tid), "source": SOURCE, "n_signatures": str(n)})

    tables = (
        genes,
        drug_classes,
        mechanisms,
        confers,
        via,
        carries,
        unresolved_nodes,
        unresolved_assoc,
        disagreements,
        cited,
    )
    counts = {w.path.name: w.flush() for w in tables}

    print(f"\nread {counters['models']:,} models from card.json (CARD {version})")
    print(
        f"  edges: {counters['confers_resistance_to']:,} CONFERS_RESISTANCE_TO, "
        f"{counters['via_mechanism']:,} VIA_MECHANISM, "
        f"{counters['carries_resistance_gene']:,} CARRIES_RESISTANCE_GENE"
    )
    print(
        f"  not loaded: {counters['without_reference_sequence']:,} meta-models with "
        f"no reference sequence, {counters['unresolved_taxa']:,} unresolved taxa"
    )
    print(
        f"  disagreements with aro_index.tsv: {counters['index_only']:,} models the "
        f"index has and card.json does not, {counters['json_only']:,} the other way, "
        f"{counters['name_disagreement']:,} name differences"
    )
    print(
        f"  citations: {counters['models_with_citation']:,} models with at least one "
        f"PMID ({counters['pmid_only_in_obo']:,} found only in aro.obo defs)"
    )
    print(
        "  evidence levels: "
        + ", ".join(f"{lvl} {n:,}" for lvl, n in sorted(levels.items()))
    )
    print(
        "  reference-sequence taxa: "
        + ", ".join(f"{k} {n:,}" for k, n in sorted(specificity.items()))
    )
    for name, n in counts.items():
        print(f"  {name:34s} {n:>9,}")
    shared = {w.path.name: w.merged_in for w in tables if w.merged_in}
    if shared:
        print(
            "  merged into tables another source had written: "
            + ", ".join(f"{name} +{n:,}" for name, n in shared.items())
        )
    return 0


def _stated_in_obo(terms: dict, term_id: str, relation: str, target: str) -> bool:
    """Does ``aro.obo`` state this relation too?

    It is the licence question, not a data question: a fact both halves of the
    download state may be redistributed under CC BY 4.0, and a fact only
    ``card.json`` states may not. ``aro.obo`` covers 37 of the 6,451 models
    here, so the answer is usually no — which is itself the finding.
    """
    for line in terms.get(term_id, {}).get("relationship", []):
        parts = line.split()
        if len(parts) >= 2 and parts[0] == relation and parts[1] == target:
            return True
    return False


def _as_int(value: str) -> int:
    """Model ids are numeric strings; sorting them as strings puts 10 before 2
    and makes the ledger's order depend on nothing a reader can predict."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


if __name__ == "__main__":
    raise SystemExit(main())

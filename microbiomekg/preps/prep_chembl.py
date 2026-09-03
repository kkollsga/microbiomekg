#!/usr/bin/env python3
"""ChEMBL's three JSONL files -> the flat CSVs blueprint.json loads.

``mechanism.jsonl`` is the edge list, ``molecule_max_phase4.jsonl`` names the
approved half of its molecules, and ``target.jsonl`` carries the one field that
makes ChEMBL a microbiome source at all: ``tax_id``, on 98.4% of targets, 124 of
them non-human.

Everything below that is not obvious is a pitfall from
``docs/research/source-formats.md`` §6, and each is handled where it says:

* **A drug keyed on ``molecule_chembl_id`` splits across its salt forms.** 1,626
  mechanism rows name a salt rather than the free base, and 38 (molecule,
  target, action) triples already repeat up to 5×. ``Drug`` is keyed on the
  **parent**, which every mechanism row carries; the salt id stays on the edge
  as ``reported_molecule_chembl_id`` so the normalisation is reversible. The
  molecule file has no ``molecule_hierarchy`` field at all, so a molecule no
  mechanism names has no parent evidence anywhere in the fetched subset and
  keeps its own id — never a guessed parent.
* **The molecule file does not cover the mechanism file.** 5,954 molecules are
  named by a mechanism and 3,025 of them are in the max_phase-4 file. Filtering
  the mechanisms to that file would drop 49% of them silently; loading them
  against nothing would mint nameless drugs indistinguishable from approved
  ones. Both halves load, and ``Drug.approved`` is the one WHERE clause that
  tells them apart.
* **``max_phase`` is the integer 4 on a mechanism row and the string ``"4.0"``
  on a molecule row.** :func:`~microbiomekg.ontology.chembl.max_phase`
  normalises both; comparing them raw finds no approved molecule at all.
* **577 mechanism rows have a null target and a null action type.** They are
  real curated mechanisms with no protein endpoint, so they become a ledger row
  carrying the mechanism sentence, never a dangling edge.
* **Two ``PubMed`` references carry a URL in ``ref_id``.** Validated against
  digits before being written as ``PMID:<id>``.
* **The molfile is 60% of the molecule file and nothing uses it.** Dropped at
  parse time; the canonical SMILES is kept.

Two behaviours are this loader's own and neither is upstream's fault:

**A junction endpoint that does not exist is vivified as a stub node**, so a
target whose ``tax_id`` the loaded taxonomy does not carry must reach the
ledger rather than the edge table — otherwise the graph grows ``Taxon`` nodes
whose only name is their own id. Every target taxid is resolved through
:mod:`microbiomekg.reconcile` first, and only resolved ones are written.

**``IS_DRUG`` needs a table another source writes.** ``intervention.csv`` is
gutMDisorder's, so this script declares ``DEPENDS_ON = ["gutmdisorder"]`` and
``scripts/build.py`` runs the preps in declared order. It used to run them in
*name* order, which puts this one first: the table was not there, the link was
empty, and the relationship reached the graph with zero edges and an ontology
rule auditing nothing. Run standalone against a directory that has no
``intervention.csv`` the link is still empty — and still reported as such.
"""

from __future__ import annotations

import argparse
import csv as csvmod
import json
import sys
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from microbiomekg import ontology as ont
from microbiomekg.ontology import chembl as chem
from microbiomekg.rawdata import find_taxdump, missing_input
from microbiomekg.reconcile import TaxonomyIndex
from microbiomekg.tables import Writer, as_list

SOURCE = chem.SOURCE

#: ``IS_DRUG`` joins ``intervention.csv`` — gutMDisorder's table — to this
#: source's drugs, so that prep has to have run. Declared rather than
#: implied by the filename: in name order this script sorts *first*, the
#: table was absent, and the relationship loaded zero edges.
DEPENDS_ON: list[str] = ["gutmdisorder"]

#: The three files ``scripts/fetch.py`` pulls from the ChEMBL REST API.
MECHANISM_FILE = "mechanism.jsonl"
MOLECULE_FILE = "molecule_max_phase4.jsonl"
TARGET_FILE = "target.jsonl"


def text(value: Any) -> str:
    """A JSON value as a stripped string; ``None`` becomes empty.

    ``None`` must not reach the CSV as the string ``"None"``: kglite would load
    it as a value and the audit would count it as present.
    """
    return "" if value is None else str(value).strip()


def flag(value: Any) -> str:
    """A ChEMBL flag as the ``"true"``/``"false"`` the blueprint's ``bool`` reads.

    ChEMBL spells booleans three ways — JSON ``true``, the integers ``1``/``0``
    on the mechanism flags, and ``null`` — and an empty string is the only
    honest rendering of the third.
    """
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return "true" if value.strip().casefold() in ("true", "1", "yes") else "false"
    return "true" if bool(value) else "false"


def read_jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def parent_index(mechanisms: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """``molecule_chembl_id`` → ``parent_molecule_chembl_id``, salts only.

    This is the whole of the hierarchy information the fetched subset has:
    ``molecule_max_phase4.jsonl`` carries no ``molecule_hierarchy`` field, while
    every mechanism row carries its molecule's parent. Only the pairs that
    actually *differ* are recorded, so the map answers "is this id a salt?" as
    well as "of what?".
    """
    parents: dict[str, str] = {}
    for row in mechanisms:
        molecule = text(row.get("molecule_chembl_id"))
        parent = text(row.get("parent_molecule_chembl_id"))
        if molecule and parent and molecule != parent:
            parents[molecule] = parent
    return parents


def drug_key(molecule_chembl_id: str, parents: Mapping[str, str]) -> str:
    """The ``Drug`` pk for a molecule id: the parent's CURIE where one is known.

    A molecule with no parent evidence keeps its own id. That is not a claim
    that it is a free base — it is the absence of a claim either way, which is
    the only thing the fetched files support.
    """
    return f"CHEMBL:{parents.get(molecule_chembl_id, molecule_chembl_id)}"


def atc_codes(molecule: Mapping[str, Any]) -> str:
    return as_list(text(c) for c in (molecule.get("atc_classifications") or []) if c)


def smiles(molecule: Mapping[str, Any]) -> str:
    """The canonical SMILES, never the molfile.

    ``molecule_structures.molfile`` is a multi-kilobyte MOL block on 3,417 of
    the 4,225 records — 60% of the file — and nothing in this model reads it.
    """
    return text((molecule.get("molecule_structures") or {}).get("canonical_smiles"))


def accessions(target: Mapping[str, Any]) -> list[str]:
    """UniProt accessions from ``target_components``, in file order.

    Not from ``target_component_xrefs``, which mixes PDBe, InterPro and three
    flavours of GO in one list keyed by ``xref_src_db``.
    """
    seen: "OrderedDict[str, None]" = OrderedDict()
    for component in target.get("target_components") or []:
        accession = text(component.get("accession"))
        if accession:
            seen.setdefault(accession, None)
    return list(seen)


def reference_types(mechanism: Mapping[str, Any]) -> list[str]:
    return [text(r.get("ref_type")) for r in (mechanism.get("mechanism_refs") or [])]


def regulatory_urls(mechanism: Mapping[str, Any]) -> list[str]:
    """The label/formulary references, as URLs.

    Kept apart from ``publications`` because they are a different knowledge
    claim: a DailyMed entry is a regulator's approved label, not a paper, and
    ``evidence_level`` reads the two differently.
    """
    urls: list[str] = []
    for ref in mechanism.get("mechanism_refs") or []:
        if text(ref.get("ref_type")) in chem.REGULATORY_REF_TYPES:
            urls.append(text(ref.get("ref_url")) or text(ref.get("ref_id")))
    return [u for u in urls if u]


DRUG_FIELDS = [
    "drug_id",
    "chembl_id",
    "pref_name",
    "molecule_type",
    "max_phase",
    "first_approval",
    "atc_codes",
    "approved",
    "withdrawn",
    "therapeutic",
    "oral",
    "parenteral",
    "topical",
    "smiles",
    "salt_form",
    "salt_ids",
    "source",
    "source_licence",
    "chembl_release",
]

TARGET_FIELDS = [
    "target_id",
    "chembl_id",
    "pref_name",
    "target_type",
    "organism",
    "tax_id",
    "uniprot",
    "n_components",
    "species_group",
    "source",
    "source_licence",
    "chembl_release",
]

MECHANISM_FIELDS = [
    # The seven the ontology requires, first and in declaration order.
    "evidence_level",
    "knowledge_level",
    "agent_type",
    "primary_source",
    "source_record_id",
    "source_licence",
    "source_relation",
    # What ChEMBL curated, deliberately outside the required set.
    "action_type",
    "mechanism_of_action",
    "publications",
    "regulatory_refs",
    "clinical_phase",
    "direct_interaction",
    "disease_efficacy",
    "mechanism_comment",
    "selectivity_comment",
    "reported_molecule_chembl_id",
    "chembl_release",
]

LEDGER_FIELDS = ["kind", "record_id", "subject", "detail", "reason", "source"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", type=Path, default=Path("data/raw"))
    ap.add_argument(
        "--chembl",
        type=Path,
        default=None,
        help=f"Directory holding {MECHANISM_FILE}, {MOLECULE_FILE} and "
        f"{TARGET_FILE} (default: <raw>/chembl).",
    )
    ap.add_argument("--taxdump", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=Path("data/csv"))
    ap.add_argument(
        "--interventions",
        type=Path,
        default=None,
        help="gutMDisorder's intervention table, read to link Intervention "
        "nodes to Drug nodes (default: <out>/intervention.csv).",
    )
    ap.add_argument("--rank-ceiling", default="species")
    args = ap.parse_args(argv)

    raw = args.chembl or (args.raw / SOURCE)
    missing = [
        n
        for n in (MECHANISM_FILE, MOLECULE_FILE, TARGET_FILE)
        if not (raw / n).is_file()
    ]
    if missing:
        # Exit 3, not 2: "this source's raw files are not on this machine" is a
        # different fact from "this script was called wrong", and
        # scripts/build.py acts on the difference by skipping the source and
        # leaving it out of the blueprint rather than declaring an empty one.
        print(f"no {', '.join(missing)} under {raw}", file=sys.stderr)
        return 3
    try:
        taxdump = args.taxdump or find_taxdump(args.raw)
    except FileNotFoundError as e:
        return missing_input(e)

    print(f"reading {raw}/{{mechanism,molecule_max_phase4,target}}.jsonl", flush=True)
    mechanisms = list(read_jsonl(raw / MECHANISM_FILE))
    molecules = {
        text(m["molecule_chembl_id"]): m for m in read_jsonl(raw / MOLECULE_FILE)
    }
    targets = {text(t["target_chembl_id"]): t for t in read_jsonl(raw / TARGET_FILE)}
    print(
        f"  {len(mechanisms):,} mechanism rows, {len(molecules):,} approved "
        f"molecules, {len(targets):,} targets",
        flush=True,
    )

    print(f"loading taxdump from {taxdump} ...", flush=True)
    idx = TaxonomyIndex.from_taxdump(taxdump)
    print(f"  {len(idx.parent):,} taxa, {len(idx.names):,} name keys", flush=True)

    out = args.out
    drugs = Writer(out / "drug.csv", DRUG_FIELDS, key="drug_id")
    protein_targets = Writer(out / "protein_target.csv", TARGET_FIELDS, key="target_id")
    mechanism_edges = Writer(
        out / "drug_target.csv", ["drug_id", "target_id", *MECHANISM_FIELDS]
    )
    organism_edges = Writer(
        out / "protein_target_taxon.csv",
        [
            "target_id",
            "tax_id",
            "reported_tax_id",
            "resolution_status",
            "organism",
            "primary_source",
            "source_licence",
        ],
        dedupe_full=True,
    )
    drug_links = Writer(
        out / "intervention_drug.csv",
        [
            "intervention_id",
            "drug_id",
            "match_method",
            "matched_name",
            "drugbank_id",
            "primary_source",
            "source_licence",
        ],
        key="intervention_id",
    )
    ledger = Writer(out / "unresolved_chembl.csv", LEDGER_FIELDS)
    cited = Writer(
        out / "cited_taxa.csv",
        ["tax_id", "source", "n_signatures"],
        key=("tax_id", "source"),
        merge=True,
        owner=("source", SOURCE),
    )

    counters: Counter[str] = Counter()
    levels: Counter[str] = Counter()
    taxa_seen: Counter[int] = Counter()

    # ---------------------------------------------------------------- drugs
    #
    # The node set is the union of the approved molecules and the molecules a
    # mechanism names, collapsed onto parents. Neither half alone is right:
    # source-formats.md §6 pitfall 1 asks for an explicit decision rather than
    # half of each, and this is it — load both, flag which is which.
    parents = parent_index(mechanisms)
    by_key: "OrderedDict[str, list[str]]" = OrderedDict()
    for molecule_id in molecules:
        by_key.setdefault(drug_key(molecule_id, parents), []).append(molecule_id)
    for row in mechanisms:
        by_key.setdefault(drug_key(text(row["molecule_chembl_id"]), parents), [])

    for key, molecule_ids in by_key.items():
        chembl_id = key.split(":", 1)[1]
        own = [m for m in molecule_ids if m == chembl_id]
        # Properties come from the parent's own record where there is one. The
        # fallback exists because it is *representable*, not because ChEMBL 37
        # needs it: every known salt in this release has its parent in the
        # molecule file too, so `salt_form` is 0 here and would stop being 0 the
        # day a release ships a salt whose parent is not approved.
        source_id = own[0] if own else (molecule_ids[0] if molecule_ids else "")
        molecule = molecules.get(source_id, {})
        salt_ids = [m for m in molecule_ids if m != chembl_id]
        counters["salts_folded"] += len(salt_ids)
        if molecule_ids and not own:
            counters["salt_form_properties"] += 1
        if not molecule:
            counters["unapproved_drugs"] += 1
        drugs.add(
            {
                "drug_id": key,
                "chembl_id": chembl_id,
                "pref_name": text(molecule.get("pref_name")),
                "molecule_type": text(molecule.get("molecule_type")),
                "max_phase": text(chem.max_phase(molecule.get("max_phase"))),
                "first_approval": text(molecule.get("first_approval")),
                "atc_codes": atc_codes(molecule),
                "approved": flag(bool(molecule)),
                "withdrawn": flag(molecule.get("withdrawn_flag")) if molecule else "",
                "therapeutic": flag(molecule.get("therapeutic_flag"))
                if molecule
                else "",
                "oral": flag(molecule.get("oral")) if molecule else "",
                "parenteral": flag(molecule.get("parenteral")) if molecule else "",
                "topical": flag(molecule.get("topical")) if molecule else "",
                "smiles": smiles(molecule) if molecule else "",
                "salt_form": flag(bool(molecule_ids) and not own),
                "salt_ids": as_list(salt_ids),
                "source": SOURCE,
                "source_licence": chem.LICENCE,
                "chembl_release": chem.RELEASE,
            }
        )

    # -------------------------------------------------------------- targets
    #
    # `cited_taxa.csv` is what tells prep_taxonomy which taxa to keep, and a
    # taxon it does not name is a taxon the OF_ORGANISM junction *vivifies*.
    # So it is filled here, beside the edge it has to cover, rather than in the
    # mechanism loop where the two could drift apart.
    mechanisms_per_target: Counter[str] = Counter(
        text(row.get("target_chembl_id"))
        for row in mechanisms
        if text(row.get("target_chembl_id"))
    )
    for target_id, target in targets.items():
        uniprot = accessions(target)
        organism = text(target.get("organism"))
        raw_tax = target.get("tax_id")
        protein_targets.add(
            {
                "target_id": f"CHEMBL:{target_id}",
                "chembl_id": target_id,
                "pref_name": text(target.get("pref_name")),
                "target_type": text(target.get("target_type")),
                "organism": organism,
                "tax_id": text(raw_tax),
                "uniprot": as_list(uniprot),
                "n_components": str(len(target.get("target_components") or [])),
                "species_group": flag(target.get("species_group_flag")),
                "source": SOURCE,
                "source_licence": chem.LICENCE,
                "chembl_release": chem.RELEASE,
            }
        )
        if raw_tax in (None, ""):
            counters["target_without_taxid"] += 1
            ledger.add(
                {
                    "kind": "target_without_taxon",
                    "record_id": target_id,
                    "subject": organism,
                    "detail": "",
                    "reason": "target carries no tax_id",
                    "source": SOURCE,
                }
            )
            continue
        resolution = idx.resolve(tax_id=int(raw_tax), rank_ceiling=args.rank_ceiling)
        if resolution.tax_id is None:
            # Never written through: a junction row whose endpoint is missing
            # vivifies a stub Taxon whose only name is its own id, and every
            # taxon count in the graph is then wrong.
            counters["target_taxon_unresolved"] += 1
            ledger.add(
                {
                    "kind": "target_without_taxon",
                    "record_id": target_id,
                    "subject": organism,
                    "detail": text(raw_tax),
                    "reason": f"tax_id {raw_tax} {resolution.status}: {resolution.note}",
                    "source": SOURCE,
                }
            )
            continue
        organism_edges.add(
            {
                "target_id": f"CHEMBL:{target_id}",
                "tax_id": str(resolution.tax_id),
                "reported_tax_id": text(raw_tax),
                "resolution_status": resolution.status,
                "organism": organism,
                "primary_source": SOURCE,
                "source_licence": chem.LICENCE,
            }
        )
        counters["of_organism"] += 1
        taxa_seen[resolution.tax_id] += mechanisms_per_target.get(target_id, 0)

    # ----------------------------------------------------------- mechanisms
    for row in mechanisms:
        counters["mechanism_rows"] += 1
        mec_id = text(row.get("mec_id"))
        molecule_id = text(row.get("molecule_chembl_id"))
        key = drug_key(molecule_id, parents)
        target_id = text(row.get("target_chembl_id"))
        refs = reference_types(row)
        level = chem.evidence_level(row.get("max_phase"), refs)
        if not target_id:
            counters["mechanism_without_target"] += 1
            ledger.add(
                {
                    "kind": "mechanism_without_target",
                    "record_id": mec_id,
                    "subject": key,
                    "detail": text(row.get("mechanism_of_action")),
                    "reason": "mechanism has no target_chembl_id — a curated mechanism "
                    "with no protein endpoint, not a missing edge",
                    "source": SOURCE,
                }
            )
            continue
        publications: list[str] = []
        for ref in row.get("mechanism_refs") or []:
            curie = chem.publication_curie(ref)
            if curie:
                publications.append(curie)
            elif text(ref.get("ref_type")) in chem.PUBLICATION_PREFIXES:
                counters["malformed_reference"] += 1
                ledger.add(
                    {
                        "kind": "malformed_reference",
                        "record_id": mec_id,
                        "subject": text(ref.get("ref_id")),
                        "detail": f"ref_type {text(ref.get('ref_type'))}",
                        "reason": "ref_id is not an identifier for its ref_type",
                        "source": SOURCE,
                    }
                )
        levels[level] += 1
        counters["has_mechanism"] += 1
        mechanism_edges.add(
            {
                "drug_id": key,
                "target_id": f"CHEMBL:{target_id}",
                "evidence_level": level,
                "knowledge_level": ont.knowledge_level(SOURCE),
                "agent_type": ont.agent_type(SOURCE),
                "primary_source": SOURCE,
                "source_record_id": mec_id,
                "source_licence": chem.LICENCE,
                # ChEMBL's own sentence about this mechanism, kept verbatim beside
                # the normalised `action_type` so the normalisation is reversible.
                "source_relation": text(row.get("mechanism_of_action")),
                "action_type": text(row.get("action_type")),
                "mechanism_of_action": text(row.get("mechanism_of_action")),
                "publications": as_list(publications),
                "regulatory_refs": as_list(regulatory_urls(row)),
                "clinical_phase": text(chem.max_phase(row.get("max_phase"))),
                "direct_interaction": flag(row.get("direct_interaction")),
                "disease_efficacy": flag(row.get("disease_efficacy")),
                "mechanism_comment": text(row.get("mechanism_comment")),
                "selectivity_comment": text(row.get("selectivity_comment")),
                # The id the source wrote, which is a salt on 1,626 real rows.
                "reported_molecule_chembl_id": molecule_id,
                "chembl_release": chem.RELEASE,
            }
        )

    # -------------------------------------------------- interventions -> drugs
    interventions_path = args.interventions or (out / "intervention.csv")
    linked, considered = link_interventions(
        interventions_path, molecules, parents, drug_links, ledger, counters
    )

    for tax_id, n in sorted(taxa_seen.items()):
        cited.add({"tax_id": str(tax_id), "source": SOURCE, "n_signatures": str(n)})

    tables = (
        drugs,
        protein_targets,
        mechanism_edges,
        organism_edges,
        drug_links,
        ledger,
        cited,
    )
    counts = {w.path.name: w.flush() for w in tables}

    print(
        f"\nread {counters['mechanism_rows']:,} mechanism rows over "
        f"{len(by_key):,} drugs and {len(targets):,} targets "
        f"({counters['salts_folded']:,} salt form(s) folded onto a parent, "
        f"{counters['salt_form_properties']:,} of them the only record of "
        f"their parent)"
    )
    print(
        f"  edges: {counters['has_mechanism']:,} HAS_MECHANISM, "
        f"{counters['of_organism']:,} OF_ORGANISM, {linked:,} IS_DRUG"
    )
    print(
        f"  not loaded: {counters['mechanism_without_target']:,} mechanisms with no "
        f"target, {counters['target_without_taxid']:,} targets with no tax_id, "
        f"{counters['target_taxon_unresolved']:,} target taxids the taxonomy does "
        f"not carry, {counters['malformed_reference']:,} malformed references"
    )
    print(
        f"  drugs: {counters['unapproved_drugs']:,} named only by a mechanism "
        f"(approved=false); the rest are max_phase 4"
    )
    print(
        "  evidence levels: "
        + ", ".join(f"{level} {n:,}" for level, n in sorted(levels.items()))
    )
    print(
        f"  interventions: linked {linked:,} of {considered:,} intervention(s) by "
        f"exact ChEMBL pref_name — the molecule subset carries "
        f"no DrugBank cross-reference, so the id route does not exist"
    )
    for name, n in counts.items():
        print(f"  {name:34s} {n:>9,}")
    shared = {w.path.name: w.merged_in for w in tables if w.merged_in}
    if shared:
        print(
            "  merged into tables another source had written: "
            + ", ".join(f"{name} +{n:,}" for name, n in shared.items())
        )
    # Printed rather than assumed: CC BY-SA 3.0 asks for the citation and the
    # release number, and a build log is where an operator sees what the graph
    # they just made is bound by.
    print(f"  attribution ({chem.LICENCE}): {chem.ATTRIBUTION}")
    return 0


def name_index(
    molecules: Mapping[str, Mapping[str, Any]], parents: Mapping[str, str]
) -> dict[str, tuple[str, str]]:
    """Casefolded ChEMBL ``pref_name`` → ``(drug_id, the name as ChEMBL spells it)``.

    A salt's name indexes onto its parent's node, so ``Metformin hydrochloride``
    reaches the same drug ``Metformin`` does — a different spelling of the same
    molecule, not a different molecule. A name reaching two *different* drugs is
    dropped from the index rather than resolved: picking one would be the
    first-wins merge C2 catalogues. (Measured on ChEMBL 37: none of the 4,225
    names collide.)
    """
    hits: dict[str, set[str]] = defaultdict(set)
    spelling: dict[str, str] = {}
    for molecule_id, molecule in molecules.items():
        name = text(molecule.get("pref_name"))
        if not name:
            continue
        key = name.casefold()
        hits[key].add(drug_key(molecule_id, parents))
        spelling.setdefault(key, name)
    return {k: (next(iter(v)), spelling[k]) for k, v in hits.items() if len(v) == 1}


def link_interventions(
    path: Path,
    molecules: Mapping[str, Mapping[str, Any]],
    parents: Mapping[str, str],
    drug_links: Writer,
    ledger: Writer,
    counters: Counter,
) -> tuple[int, int]:
    """Link ``Intervention`` nodes to ``Drug`` nodes by exact name.

    The intended route was the DrugBank id both sides were expected to carry.
    The fetched molecule JSONL carries **no** cross-references at all — the
    REST pull's ``only=`` kept 13 of 34 fields and DrugBank was not among them —
    so the only available join is the name, and a name join is the thing this
    repo's pitfall list argues against everywhere else. It is therefore **exact,
    casefolded, whole-label**, and every near miss is a ledger row naming the
    drugs it would have reached: `Acetylsalicylic acid` is ASPIRIN to ChEMBL and
    a comma-multivalued cell names two drugs, and accepting either would invent
    an intervention gutMDisorder never curated.
    """
    if not path.is_file():
        print(
            f"\nno intervention table at {path} — no Intervention nodes to link "
            f"(gutMDisorder has not written it; scripts/build.py orders the "
            f"preps so that it has, so this is a standalone run)",
            file=sys.stderr,
            flush=True,
        )
        return 0, 0

    index = name_index(molecules, parents)
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csvmod.DictReader(fh))
    linked = 0
    for row in rows:
        label = (row.get("label") or "").strip()
        intervention_id = (row.get("intervention_id") or "").strip()
        if not intervention_id:
            continue
        hit = index.get(label.casefold())
        if hit:
            drug_id, matched = hit
            drug_links.add(
                {
                    "intervention_id": intervention_id,
                    "drug_id": drug_id,
                    "match_method": "pref_name",
                    "matched_name": matched,
                    "drugbank_id": (row.get("drugbank_id") or "").strip(),
                    "primary_source": SOURCE,
                    "source_licence": chem.LICENCE,
                }
            )
            linked += 1
            continue
        counters["intervention_unlinked"] += 1
        parts = [p.strip() for p in label.split(",") if p.strip()]
        found = [index[p.casefold()][0] for p in parts if p.casefold() in index]
        if len(parts) > 1 and found:
            reason = (
                "comma-multivalued label: the cell names several drugs and "
                "the intervention is the combination, which ChEMBL has no "
                "molecule for"
            )
        else:
            reason = (
                "no exact ChEMBL pref_name match — a synonym or a "
                "non-molecular intervention, never a fuzzy match"
            )
        ledger.add(
            {
                "kind": "intervention_unlinked",
                "record_id": intervention_id,
                "subject": label,
                "detail": "|".join(found),
                "reason": reason,
                "source": SOURCE,
            }
        )
    return linked, len(rows)


if __name__ == "__main__":
    raise SystemExit(main())

"""HMDB's 6.5 GB XML -> 7,773 Metabolite nodes and 578 production edges.

``data/raw/hmdb/hmdb_metabolites.xml`` is one 6,486,862,079-byte XML document
holding 217,920 ``<metabolite>`` records in the ``http://www.hmdb.ca``
namespace. It is streamed with ``iterparse`` and cleared per record —
``ET.parse`` on this file is an out-of-memory error, not a slow load — and one
pass answers everything below, because ``<chebi_id>`` sits at the end of a
record and the selection rule needs it.

**The selection rule, and why there is one.** Loading all 217,920 would be
loading a chemistry database into a microbiome graph: 88.8% of HMDB is
``predicted`` or ``expected``, and the pathway layer's 49,604 SMPDB ids are
dominated by auto-generated per-drug and per-disease "action pathways", i.e.
a per-compound artefact rather than a vocabulary. A metabolite is loaded when
it satisfies at least one of:

``microbial-origin``
    it carries the ontology path ``Disposition/Source/Biological/Microbe`` —
    **224 records**, the only ones that can produce a ``PRODUCES`` edge, and
    **67 of them name no organism beneath it**, so 157 records over 957
    organism terms are what the 578 edges come from;
``feces``
    ``Feces`` is in ``biospecimen_locations`` — 6,791 records, the gut slice,
    and the second-largest biospecimen class in the file;
``reactome-chebi``
    its ``chebi_id`` is one of the 3,260 ChEBI ids ``ChEBI2Reactome.txt``
    carries — the only HMDB records a Reactome pathway edge can ever reach.

Which rule kept a record is written to ``Metabolite.selection_rule`` (joined
with ``|`` when several did), so the rule is countable in the graph rather than
described in a docstring. Nothing else is loaded, and the counts are printed.

Deliberately **not** loaded, each for a stated reason:

* **The disease layer.** 20,020 of its 27,670 rows carry the single name
  ``3-methylglutaconic aciduria type II, X-linked`` — 72% of it — where the
  next name down has 831. One ``Disease`` node with 20,020 metabolite edges
  would dominate every path query in the graph. Counted and reported here.
* **`Paper` nodes.** HMDB's references are free-text citation strings with a
  ``pubmed_id``; minting a ``Paper`` from one gives a node with no title, which
  is what the ``paper`` table is keyed and BM25-indexed on. The PMIDs ride on
  the edge as ``publications`` instead, so D5 still answers "which citation".
* **`protein_associations`, `normal_concentrations`, `abnormal_concentrations`,
  the SMPDB pathway layer.** Real data, no node type in this increment.

The organism strings are the hard part and :mod:`microbiomekg.ontology.hmdb`
carries the reasoning: HMDB names organisms as free text at two levels with no
taxid anywhere, the "genus" level is not a rank, and the string ``Firmicutes``
resolves through ``names.dmp`` to a **kingdom**. Everything that cannot become
an honest edge lands in the ``unresolved_production`` table with the id and rank
it did reach, so the decision is countable and reversible.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from collections import Counter, OrderedDict
from dataclasses import replace
from pathlib import Path

from microbiomekg import ontology as ont
from microbiomekg.ontology import hmdb as hm
from microbiomekg.rawdata import MissingInput, find_taxdump
from microbiomekg.reconcile import TaxonomyIndex, rank_depth
from microbiomekg.tables import Frames, as_list

SOURCE = hm.SOURCE

#: The raw files this prep reads, relative to ``--raw``, in the layout
#: ``fetch`` writes. `status` reports on exactly these.
RAW_INPUTS: list[str] = ["hmdb/hmdb_metabolites.xml"]

#: Reads no other prep's table. It writes ``metabolite``, which KEGG, Reactome,
#: MiMeDB and NJC19 join through and therefore declare.
DEPENDS_ON: list[str] = []

#: Every element in the file carries it, so every ``find`` needs it.
NS = "{http://www.hmdb.ca}"

#: The biospecimen string that makes a metabolite gut-relevant. A closed
#: 18-value list; this is the second-largest class after Blood.
FECES = "Feces"

#: The ontology path prefix, as a tuple, so a match is a prefix comparison on
#: terms rather than a substring search on a joined string (which would also
#: match `Antimicrobial agent`).
MICROBE_PREFIX: tuple[str, ...] = tuple(hm.MICROBE_PATH.split("/"))
SOURCE_PREFIX: tuple[str, ...] = tuple(hm.SOURCE_ROOT.split("/"))

#: How many PMIDs an edge carries. HMDB's `general_references` runs to 1.2M
#: rows over the file and a single well-studied compound can carry hundreds;
#: `n_publications` keeps the true count beside the truncated list, so the cap
#: is visible rather than silently changing what "how many papers" answers.
MAX_PUBLICATIONS = 25

#: Progress cadence. A silent 6.5 GB pass is indistinguishable from a hang.
PROGRESS_EVERY = 20_000

#: The NCBI roots a `Disposition/Source/Biological/Microbe` term can plausibly
#: sit under. Used only to break a *cross-kingdom* homonym, and only when
#: exactly one candidate is under one of them — see :func:`microbial_candidate`.
MICROBIAL_ROOTS: frozenset[int] = frozenset(
    {
        2,  # Bacteria
        2157,  # Archaea
        4751,  # Fungi
        10239,  # Viruses
    }
)

METABOLITE_FIELDS = [
    "metabolite_id",
    "name",
    "hmdb_id",
    "chebi_id",
    "kegg_id",
    "pubchem_cid",
    "inchikey",
    "status",
    "biospecimens",
    "microbial_origin",
    "origin",
    "chemical_formula",
    "secondary_accessions",
    "selection_rule",
    "source",
]

PRODUCES_FIELDS = [
    "evidence_level",
    "knowledge_level",
    "agent_type",
    "primary_source",
    "source_record_id",
    "source_licence",
    "source_relation",
    "reported_name",
    "reported_rank",
    "original_rank",
    "resolution_status",
    "hmdb_status",
    "microbe_path",
    "publications",
    "n_publications",
]


def text(el, tag: str) -> str:
    """A child element's text, stripped. Empty for a missing or empty element.

    HMDB writes an absent value as ``<definition/>``, whose ``.text`` is
    ``None`` rather than ``''`` — so it is guarded here, once, rather than at
    every ``strip``/compare site that would otherwise trip on it.
    """
    child = el.find(NS + tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def texts(el, path: str, tag: str) -> list[str]:
    """Every ``<tag>`` under the ``/``-joined container ``path``, empties dropped."""
    holder = el.find("/".join(NS + part for part in path.split("/")))
    if holder is None:
        return []
    return [
        c.text.strip() for c in holder.findall(NS + tag) if c.text and c.text.strip()
    ]


def child_count(el, container: str, tag: str) -> int:
    holder = el.find(NS + container)
    return 0 if holder is None else len(holder.findall(NS + tag))


def term_paths(node, prefix: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    """Every root-to-node path of terms under one ``<root>``/``<descendant>``.

    Terms have no ids. ``<parent_id>`` is an internal HMDB cvterm number that is
    not unique to the metabolite and appears nowhere else in the file, so the
    only key a term has is its path — which is also why origin is matched as a
    path prefix and never as a term substring.
    """
    term = text(node, "term")
    path = prefix + (term,) if term else prefix
    out = [path]
    kids = node.find(NS + "descendants")
    if kids is not None:
        for kid in kids.findall(NS + "descendant"):
            out.extend(term_paths(kid, path))
    return out


def is_microbial(paths: list[tuple[str, ...]]) -> bool:
    """Does this metabolite carry the microbial-origin path at all?

    Deliberately **not** the same question as :func:`microbe_terms`. 224
    metabolites carry `Disposition/Source/Biological/Microbe`; only 157 of them
    name an organism beneath it. The other 67 are a real origin claim with
    nothing to point an edge at, and reading "224 microbial metabolites" as
    "224 production edges" is the arithmetic that number invites.
    """
    return any(p[: len(MICROBE_PREFIX)] == MICROBE_PREFIX for p in paths)


def microbe_terms(paths: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    """Every named organism *under* the Microbe node, most specific first."""
    return sorted(
        (
            p
            for p in paths
            if len(p) > len(MICROBE_PREFIX)
            and p[: len(MICROBE_PREFIX)] == MICROBE_PREFIX
        ),
        key=len,
        reverse=True,
    )


def microbial_candidate(idx: TaxonomyIndex, candidates: tuple[int, ...]) -> int | None:
    """The one candidate under Bacteria/Archaea/Fungi/Viruses, or ``None``.

    `reconcile` answers ``ambiguous`` for a name several taxa share and returns
    the candidates rather than guessing, "so a caller can disambiguate with
    context it has and this module does not". This is that context, and it is
    strong: the term was read from
    ``Disposition/Source/Biological/Microbe``, so a non-microbial candidate is
    not merely less likely, it is wrong. HMDB's most common organism term,
    `Bacillus` (13 metabolites), is a bacterial genus *and* a genus of stick
    insects; `Proteus` (6) is a bacterium and an amphibian; `Serratia`,
    `Rhodococcus`, `Edwardsiella` and `Paracoccus` are the same shape.

    **Exactly one**, never the first. C2's warning is against `first-wins`, and
    C3's is that a kingdom heuristic cannot separate two *bacteria* — so
    `Bacteroidetes` (976 and 200643, both bacterial) and `Lactobacillus
    plantarum` (1590 and 1385856) stay ambiguous and reach the ledger, which is
    the correct outcome rather than a shortfall.
    """
    hits = [c for c in candidates if MICROBIAL_ROOTS & set(idx.lineage(c))]
    return hits[0] if len(hits) == 1 else None


def covered(path: tuple[str, ...], resolved: set[tuple[str, ...]]) -> bool:
    """Did a **deeper** term of this metabolite already become an edge?

    A metabolite listing both ``Microbe/Escherichia`` and
    ``Microbe/Escherichia/Escherichia coli`` is making one claim about one
    organism at two levels of detail, not two claims: emitting both would
    double the evidence for it and put a genus edge beside its own species edge
    in D5's output. So the genus is suppressed — but **only when the species
    actually resolved**. That condition is the whole point of the function. A
    plain "keep the leaf" rule loses the claim entirely whenever the only child
    is one of HMDB's misspellings (`Akkermansia/Akkermansia muciniphilia`,
    `Citrobacter/Citrobacter frundii`), which is a silent drop of a resolvable
    genus the source did name.
    """
    return any(q != path and q[: len(path)] == path for q in resolved)


def origins(paths: list[tuple[str, ...]]) -> list[str]:
    """The direct children of ``Disposition/Source`` — where a compound comes from.

    ``Biological`` is kept alongside ``Food``/``Endogenous``/``Synthetic``/
    ``Environmental``/``Exogenous`` rather than dropped for being the branch
    that carries ``Microbe``: it is a real origin claim, and
    ``microbial_origin`` is the separate boolean for the narrower one.
    """
    n = len(SOURCE_PREFIX)
    return sorted({p[n] for p in paths if len(p) == n + 1 and p[:n] == SOURCE_PREFIX})


def publications(el) -> tuple[str, int]:
    """``PMID:…|PMID:…`` from ``general_references``, and the true count."""
    holder = el.find(NS + "general_references")
    if holder is None:
        return "", 0
    seen: "OrderedDict[str, None]" = OrderedDict()
    for ref in holder.findall(NS + "reference"):
        pmid = text(ref, "pubmed_id")
        if pmid.isdigit():
            seen.setdefault(f"PMID:{pmid}", None)
    ids = list(seen)
    return as_list(ids[:MAX_PUBLICATIONS]), len(ids)


def reactome_chebi_ids(path: Path) -> set[str]:
    """The bare ChEBI ids ``ChEBI2Reactome.txt`` maps, as strings.

    The file is headerless and tab-separated with the compound id in column 1,
    unprefixed. Reading it here rather than in ``prep_reactome.py`` is what
    makes the selection rule decidable in HMDB's single pass — the alternative
    is a second 6.5 GB read after Reactome has run.
    """
    ids: set[str] = set()
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            first = line.split("\t", 1)[0].strip()
            if first:
                ids.add(first)
    return ids


def metabolite_key(chebi: str, accession: str) -> str:
    return f"CHEBI:{chebi}" if chebi else f"HMDB:{accession}"


def run(
    raw: Path,
    store: Frames,
    *,
    xml: Path | None = None,
    taxdump: Path | None = None,
    reactome: Path | None = None,
    rank_ceiling: str = "species",
) -> dict[str, int]:
    """HMDB's tables into ``store``; returns each table's row count.

    ``xml`` defaults to ``raw/hmdb/hmdb_metabolites.xml``; ``reactome`` to
    ``raw/reactome/`` (its ``ChEBI2Reactome.txt`` feeds a selection rule, and
    is optional). Raises :class:`MissingInput` when the XML or the taxdump is
    not there.
    """

    xml = xml or (raw / SOURCE / "hmdb_metabolites.xml")
    if not xml.is_file():
        # "This source's raw files are not on this machine" is a skip the build
        # reports, never a defect: the source leaves the blueprint rather than
        # declaring node types with nothing behind them.
        raise MissingInput(f"no hmdb_metabolites.xml at {xml}")
    try:
        taxdump = taxdump or find_taxdump(raw)
    except FileNotFoundError as e:
        raise MissingInput(str(e)) from e

    chebi_path = (reactome or (raw / "reactome")) / "ChEBI2Reactome.txt"
    if chebi_path.is_file():
        reactome_chebi = reactome_chebi_ids(chebi_path)
        print(f"reactome bridge: {len(reactome_chebi):,} ChEBI ids from {chebi_path}")
    else:
        reactome_chebi = set()
        print(f"no {chebi_path}; the reactome-chebi selection rule selects nothing")

    print(f"loading taxdump from {taxdump} ...", flush=True)
    idx = TaxonomyIndex.from_taxdump(taxdump)
    print(f"  {len(idx.parent):,} taxa, {len(idx.names):,} name keys", flush=True)
    metabolites = store.table(
        "metabolite",
        METABOLITE_FIELDS,
        key="metabolite_id",
        merge=True,
        owner=("source", SOURCE),
    )
    produces = store.table(
        "taxon_metabolite",
        ["tax_id", "metabolite_id", *PRODUCES_FIELDS],
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
    # C18's accounting for the rows that become no edge: an organism term that
    # resolved to nothing, one that resolved above the production rank ceiling,
    # and a metabolite whose ChEBI key another accession already claimed. Each
    # carries what it *did* reach, so none of them is a drop.
    ledger = store.table(
        "unresolved_production",
        [
            "accession",
            "metabolite_id",
            "reported_name",
            "microbe_path",
            "reported_rank",
            "resolved_tax_id",
            "resolved_rank",
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
    rules: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    levels: Counter[str] = Counter()
    unresolved_hits: Counter[str] = Counter()
    taxa_seen: "OrderedDict[int, int]" = OrderedDict()
    #: ChEBI key -> the accession that claimed it first. HMDB has 13,701
    #: chebi_id values over 13,562 distinct ids, so a handful of records share
    #: one compound identity and merge onto one node; the loser's edges still
    #: land on that node, only its scalar properties are dropped.
    chebi_owner: dict[str, str] = {}

    started = time.time()
    context = ET.iterparse(str(xml), events=("start", "end"))
    _, root = next(context)
    for event, el in context:
        if event != "end" or el.tag != NS + "metabolite":
            continue
        counters["records"] += 1
        if counters["records"] % PROGRESS_EVERY == 0:
            print(
                f"  {counters['records']:,} records, {len(metabolites.rows):,} kept "
                f"({time.time() - started:.0f}s)",
                flush=True,
            )

        accession = text(el, "accession")
        status = text(el, "status")
        statuses[status] += 1
        chebi = text(el, "chebi_id")
        biospecimens = texts(
            el, "biological_properties/biospecimen_locations", "biospecimen"
        )
        counters["disease_rows"] += child_count(el, "diseases", "disease")

        ontology_el = el.find(NS + "ontology")
        paths: list[tuple[str, ...]] = []
        if ontology_el is not None:
            for r in ontology_el.findall(NS + "root"):
                if text(r, "term") == SOURCE_PREFIX[0]:
                    paths.extend(term_paths(r))
        terms = microbe_terms(paths)
        microbial = is_microbial(paths)
        if microbial and not terms:
            counters["microbial_without_an_organism"] += 1

        keep: list[str] = []
        if microbial:
            keep.append("microbial-origin")
        if FECES in biospecimens:
            keep.append("feces")
        if chebi and chebi in reactome_chebi:
            keep.append("reactome-chebi")
        if not keep:
            counters["not_selected"] += 1
            el.clear()
            root.clear()
            continue
        for rule in keep:
            rules[rule] += 1

        key = metabolite_key(chebi, accession)
        owner = chebi_owner.get(key)
        if owner is None:
            chebi_owner[key] = accession
        elif owner != accession:
            counters["chebi_key_shared"] += 1
            ledger.add(
                {
                    "accession": accession,
                    "metabolite_id": key,
                    "reported_name": "",
                    "microbe_path": "",
                    "reported_rank": "",
                    "resolved_tax_id": "",
                    "resolved_rank": "",
                    "reason": f"chebi_id already keyed by {owner}: the two HMDB records "
                    f"are one Metabolite node and only {owner}'s properties survive",
                    "source": SOURCE,
                }
            )

        metabolites.add(
            {
                "metabolite_id": key,
                "name": text(el, "name"),
                "hmdb_id": accession,
                "chebi_id": f"CHEBI:{chebi}" if chebi else "",
                "kegg_id": text(el, "kegg_id"),
                "pubchem_cid": text(el, "pubchem_compound_id"),
                "inchikey": text(el, "inchikey"),
                "status": status,
                "biospecimens": as_list(biospecimens),
                "microbial_origin": "true" if microbial else "false",
                "origin": as_list(origins(paths)),
                "chemical_formula": text(el, "chemical_formula"),
                # The redirect table: 80,986 retired ids across the file, without
                # which a citation of `HMDB00001` finds nothing.
                "secondary_accessions": as_list(
                    texts(el, "secondary_accessions", "accession")
                ),
                "selection_rule": as_list(keep),
                "source": SOURCE,
            }
        )

        if not terms:
            el.clear()
            root.clear()
            continue

        refs, n_refs = publications(el)
        level = hm.evidence_level(status)

        # Two phases, because whether a genus term becomes an edge depends on
        # what happened to its species. Phase one resolves every term and
        # decides whether it *could* be an edge; phase two emits, suppressing a
        # term only where a deeper one of the same metabolite succeeded.
        verdicts: dict[tuple[str, ...], tuple] = {}
        for path in terms:
            name = path[-1]
            res = idx.resolve(name, rank_ceiling=rank_ceiling)
            if res.status == "ambiguous":
                pick = microbial_candidate(idx, res.candidates)
                if pick is not None:
                    counters["kingdom_disambiguated"] += 1
                    res = replace(
                        idx.resolve(tax_id=pick, rank_ceiling=rank_ceiling),
                        matched_name=name,
                        status="kingdom-disambiguated",
                        note=f"{len(res.candidates)} taxa share this name; "
                        f"{pick} is the only one under Bacteria/Archaea/"
                        f"Fungi/Viruses and the term is a microbial-origin term",
                    )
            if res.tax_id is None:
                verdicts[path] = (res, "", f"taxon {res.status}: {res.note}")
                continue
            rank = idx.rank.get(res.tax_id) or ""
            own, ceiling = rank_depth(rank), rank_depth(hm.PRODUCTION_RANK_CEILING)
            if own is None or ceiling is None or own < ceiling:
                # Broader than a family. `Firmicutes` is what makes this a
                # correctness rule rather than a tidiness one: NCBI files that
                # string as a synonym of the *kingdom* Bacillati, so the edge a
                # naive load writes is not vague, it is false.
                verdicts[path] = (
                    res,
                    rank,
                    (
                        f"resolved rank {rank or 'unplaced'!r} is broader than "
                        f"{hm.PRODUCTION_RANK_CEILING!r}: HMDB's organism level mixes "
                        f"ranks and a claim this broad is not a production claim"
                    ),
                )
                continue
            verdicts[path] = (res, rank, None)

        resolved = {p for p, (_, _, reason) in verdicts.items() if reason is None}
        #: tax_id -> the term that already claimed it for *this* metabolite.
        #: Two terms of one metabolite reaching one taxon are one claim spelled
        #: two ways, not two observations — HMDB's `Biﬁdobacterium` (U+FB01)
        #: sits beside its own correctly spelled sibling, and `str.casefold`
        #: folds the ligature to `fi`, so both resolve to 1678. Emitting both
        #: would double the evidence for one annotation.
        claimed: dict[int, str] = {}
        # Deepest term first, and among equals the one whose string *is* the
        # NCBI name it matched: that is what makes the correctly spelled sibling
        # win the tie rather than whichever the XML happened to list first.
        for path in sorted(
            terms,
            key=lambda p: (-len(p), (verdicts[p][0].matched_name or "") != p[-1]),
        ):
            counters["microbe_terms"] += 1
            res, rank, reason = verdicts[path]
            name = path[-1]
            depth = len(path) - len(MICROBE_PREFIX)
            reported_rank = "species-level term" if depth > 1 else "genus-level term"

            if reason is None and covered(path, resolved):
                counters["covered_by_deeper_term"] += 1
                continue
            if reason is None and res.tax_id in claimed:
                counters["duplicate_organism"] += 1
                ledger.add(
                    {
                        "accession": accession,
                        "metabolite_id": key,
                        "reported_name": name,
                        "microbe_path": "/".join(path),
                        "reported_rank": reported_rank,
                        "resolved_tax_id": str(res.tax_id),
                        "resolved_rank": rank,
                        "reason": f"the same NCBI taxon is already claimed for this "
                        f"metabolite by {claimed[res.tax_id]!r}: one annotation "
                        f"spelled two ways, not two observations",
                        "source": SOURCE,
                    }
                )
                continue
            if reason is not None:
                if res.tax_id is None:
                    counters["unresolved_terms"] += 1
                    uid = f"unresolved:{SOURCE}:{name.casefold()}"
                    unresolved_nodes.add(
                        {
                            "unresolved_id": uid,
                            "raw_name": name,
                            "reported_rank": reported_rank,
                            "original_rank": res.original_rank or "",
                            "reported_tax_id": "",
                            "source": SOURCE,
                            "status": res.status,
                            "candidates": as_list(str(c) for c in res.candidates),
                            "note": res.note,
                            "n_signatures": "0",
                        }
                    )
                    unresolved_hits[uid] += 1
                else:
                    counters["rank_too_broad"] += 1
                ledger.add(
                    {
                        "accession": accession,
                        "metabolite_id": key,
                        "reported_name": name,
                        "microbe_path": "/".join(path),
                        "reported_rank": reported_rank,
                        "resolved_tax_id": str(res.tax_id or ""),
                        "resolved_rank": rank,
                        "reason": reason,
                        "source": SOURCE,
                    }
                )
                continue

            counters["produces"] += 1
            levels[level] += 1
            claimed[res.tax_id] = name
            taxa_seen[res.tax_id] = taxa_seen.get(res.tax_id, 0) + 1
            produces.add(
                {
                    "tax_id": str(res.tax_id),
                    "metabolite_id": key,
                    "evidence_level": level,
                    "knowledge_level": ont.knowledge_level(SOURCE),
                    "agent_type": ont.agent_type(SOURCE),
                    "primary_source": SOURCE,
                    "source_record_id": f"{SOURCE}:{accession}:{'/'.join(path[len(MICROBE_PREFIX) :])}",
                    "source_licence": ont.SOURCE_LICENCE.get(SOURCE, ""),
                    "source_relation": hm.MICROBE_PATH,
                    "reported_name": name,
                    "reported_rank": reported_rank,
                    "original_rank": res.original_rank or rank,
                    "resolution_status": res.status,
                    "hmdb_status": status,
                    "microbe_path": "/".join(path),
                    "publications": refs,
                    "n_publications": str(n_refs),
                }
            )

        el.clear()
        root.clear()

    for row in unresolved_nodes.rows:
        if row["source"] == SOURCE:
            row["n_signatures"] = str(unresolved_hits.get(row["unresolved_id"], 0))
    for tid, n in sorted(taxa_seen.items()):
        cited.add({"tax_id": str(tid), "source": SOURCE, "n_signatures": str(n)})

    tables = (metabolites, produces, unresolved_nodes, ledger, cited)
    counts = {w.name: store.put(w) for w in tables}

    print(f"\nread {counters['records']:,} metabolites in {time.time() - started:.0f}s")
    print(
        "  status: "
        + ", ".join(f"{s or '(empty)'} {n:,}" for s, n in statuses.most_common())
    )
    observed = sum(statuses[s] for s in hm.OBSERVED_STATUSES)
    if counters["records"]:
        print(
            f"  {counters['records'] - observed:,} of {counters['records']:,} "
            f"({100 * (counters['records'] - observed) / counters['records']:.1f}%) "
            f"have never been observed in a sample"
        )
    print(
        "  selection rule: " + ", ".join(f"{r} {n:,}" for r, n in sorted(rules.items()))
    )
    print(
        f"  kept {counts['metabolite']:,} metabolites, "
        f"skipped {counters['not_selected']:,} that no rule selected"
    )
    print(
        f"  production: {counters['microbe_terms']:,} organism terms -> "
        f"{counters['produces']:,} PRODUCES edges; "
        f"{counters['microbial_without_an_organism']:,} microbial-origin "
        f"metabolites name no organism at all and can carry none"
    )
    print(
        f"  not loaded: {counters['unresolved_terms']:,} organism terms no NCBI id "
        f"could be resolved for, {counters['rank_too_broad']:,} resolved broader than "
        f"{hm.PRODUCTION_RANK_CEILING}, {counters['chebi_key_shared']:,} records whose "
        f"ChEBI key another accession claimed"
    )
    print(
        f"  cross-kingdom homonyms resolved by the microbial context: "
        f"{counters['kingdom_disambiguated']:,} terms"
    )
    print(
        f"  suppressed as duplicate detail: {counters['covered_by_deeper_term']:,} "
        f"terms whose own species-level term became the edge, "
        f"{counters['duplicate_organism']:,} spelled a taxon the same metabolite "
        f"had already claimed"
    )
    print(
        f"  disease layer NOT loaded: {counters['disease_rows']:,} rows "
        f"(20,020 of them carry one disease name in the full file)"
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

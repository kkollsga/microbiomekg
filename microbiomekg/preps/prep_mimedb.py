"""MiMeDB's two table dumps -> Metabolite nodes, and no edges, because there are none.

``data/raw/mimedb/v2/`` holds two Sequel Ace exports of one MySQL table each —
``mimedb_metabolites_v2.csv`` (29,295 rows, ``SELECT * FROM metabolites WHERE
export = 1``) and ``mimedb_microbes_v2.csv`` (2,648 rows, ``SELECT * FROM
microbes WHERE export = 1``), plus the same two as XML. ``data/raw/mimedb/``
holds the v1.0 pair beside them. **Neither release carries the association
between its two tables** — the measurement and its consequence for D5 are in
:mod:`microbiomekg.ontology.mimedb`, and the short version is that this prep
puts rows into the ``metabolite`` table and nothing else. It emits no ``PRODUCES``, and
the build report will say so with a zero rather than leaving the reader to
notice.

**v2.0 is read where it is present and v1.0 is the fallback**, resolved by
:func:`default_inputs`. Which one was read is stated in this prep's own output
*and* on every node it writes, as ``Metabolite.mimedb_release``: the build
report is a terminal scroll and the graph outlives it, so a consumer asking
"which MiMeDB is in here" must be able to ask the graph. The label comes from
:func:`~microbiomekg.ontology.mimedb.release_of`, which reads the header rather
than the filename.

What v2 changed, all of it measured on the files:

* 1,654 more metabolite records and 474 more organisms — every v1 ``microbe_id``
  is still present, so it is a superset;
* four new metabolite columns (:data:`~microbiomekg.ontology.mimedb.V2_ONLY_COLUMNS`),
  three of them cross-references this graph has no other source for;
* ``detected`` and ``quantified`` are no longer the same 711 rows — they are
  1,674 and 1,413 — so the ``observed`` rule is a real disjunction;
* **still no join.** ``microbe_relations`` counts related microbes (830,984
  summed) and names none of them.

The microbes table is read anyway, for what it *can* honestly answer, all
printed and none loaded: how many of its organisms carry an NCBI taxid, how many
of those the loaded taxonomy resolves, and how many rows fill the ``activity``
column that names a direction and no compound. That is the size of the taxon
side of the edge list this source would supply if the association were
downloadable, and stating it is the difference between "MiMeDB does not close
D5" and "MiMeDB has nothing".

**The selection rule**, because 29,295 records is a lipidomics table and 12,105
of them are glycerophospholipids. A record is loaded when at least one of
:data:`~microbiomekg.ontology.mimedb.SELECTION_RULES` holds — ``observed``,
``origin-classified``, ``njc19-compound`` — and ``Metabolite.selection_rule``
says which, joined with ``|``. The third rule reads NJC19's spreadsheet
directly, the way ``prep_hmdb.py`` reads ``ChEBI2Reactome.txt``: the alternative
is a second pass after NJC19 has run, and NJC19 needs these nodes to exist
before *it* runs.

Nothing is written for a record whose compound the graph already holds. Three
tests of "already holds", in this order:

* the normalised ``hmdb_id`` matches a ``Metabolite`` node's accession (or one
  of its ``secondary_accessions``);
* the **full** ``moldb_inchikey`` matches a node's. Never the first block alone:
  block 2 is stereochemistry, isotopes and protonation, so a skeleton match
  folds ``D-`` onto ``L-``. And never ``cmmc_inchikey``, which is a *different*
  compound's key on 428 rows — see
  :data:`~microbiomekg.ontology.mimedb.V2_ONLY_COLUMNS`;
* the name matches a ``Metabolite`` node's name, casefolded — the route NJC19
  itself uses, so a duplicate here would be a second node NJC19 might then pick.

A record any of them catches is a row in the ``unresolved_mimedb`` ledger table
naming the node that already holds the compound, so "MiMeDB added nothing here"
is a count rather than an
absence. And an ``hmdb_id`` that **two** MiMeDB records claim is not used as a
join key at all: 149 accessions are contested over 329 records, mostly by a
D-/L- enantiomer pair, and joining them would fold two compounds into one node.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from microbiomekg.ontology import mimedb as mm
from microbiomekg.ontology import njc19 as nj
from microbiomekg.rawdata import MissingInput, find_taxdump
from microbiomekg.reconcile import TaxonomyIndex
from microbiomekg.tables import Frames, as_list, from_list

SOURCE = mm.SOURCE

#: Where the loader looks, in order. v2.0 is the release this project reads;
#: v1.0 stays as the fallback because it is the one `scripts/fetch.py` can
#: actually obtain without an operator (v1's bulk files were captured by the
#: Wayback Machine; v2's were not, and mimedb.org is Cloudflare-challenged).
RELEASE_DIRS: tuple[tuple[str, str], ...] = (("v2", "v2"), ("", "v1"))

#: The raw files this prep reads, relative to ``--raw``, in the layout
#: ``fetch`` writes. `status` reports on exactly these: the v1.0 files beside
#: `v2/` are a fallback the prep accepts (:data:`RELEASE_DIRS`), not the state
#: `status` asks for.
RAW_INPUTS: list[str] = [
    "mimedb/v2/mimedb_metabolites_v2.csv",
    "mimedb/v2/mimedb_microbes_v2.csv",
]

#: Reads the ``metabolite`` table HMDB puts in the store: a MiMeDB record whose
#: compound already has a node must not mint a second one. It also *reads
#: NJC19's raw spreadsheet* for the ``njc19-compound`` selection rule, which is
#: not a prep dependency — the dependency runs the other way, and ``prep_njc19``
#: declares it.
DEPENDS_ON: list[str] = ["hmdb"]

#: The MySQL dump writes an absent value as the four characters ``NULL``. Read
#: straight, that is the *string* "NULL" in a CSV column, which kglite loads as
#: a value and ``ontology_audit()`` counts as present.
NULL = "NULL"

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
    "mimedb_id",
    "mimedb_origin",
    "cas",
    "average_mass",
    "mimedb_release",
    "vmh_id",
    "cmmc_inchikey",
    "epa_substance_id",
    "epa_compound_id",
    mm.MICROBE_RELATION_COUNT,
]

LEDGER_FIELDS = [
    "mimedb_id",
    "name",
    "hmdb_id",
    "metabolite_id",
    "reason",
    "source",
]


def cell(row: dict[str, str], key: str) -> str:
    """One dump cell, with ``NULL`` and whitespace resolved to ``""``."""
    value = (row.get(key) or "").strip()
    return "" if value == NULL else value


def load_metabolite_index(
    rows: list[dict[str, str]],
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """``(accession, casefolded name, InChIKey) -> metabolite_id``, three indexes.

    Rows this source wrote on a previous run are skipped (the loop says why).

    Read off the store's shared ``metabolite`` table rather than re-derived from HMDB's
    XML, for the reason ``docs/model.md`` records under ``IS_DRUG``: a consumer
    that re-derives another source's node ids from its raw input dangles
    silently the day that source changes its keying rule. The accession index
    carries ``secondary_accessions`` too — HMDB retired 80,986 ids, and MiMeDB
    was built against the older ones.
    """
    accessions: dict[str, str] = {}
    names: dict[str, str] = {}
    keys: dict[str, str] = {}
    if not rows:
        return accessions, names, keys
    for row in rows:
        key = row.get("metabolite_id") or ""
        # This source's own rows from a previous run are not "a node that
        # already holds the compound": `Table(owner=...)` is about to drop
        # and rewrite them, so counting them here makes a second run load
        # nothing and report every record as a duplicate of itself. That is
        # the re-run failure `Table.owner` exists to prevent, reached through
        # the index instead of the merge.
        if not key or (row.get("source") or "") == SOURCE:
            continue
        for accession in (
            row.get("hmdb_id") or "",
            *from_list(row.get("secondary_accessions")),
        ):
            normalised = mm.normalise_hmdb_id(accession)
            if normalised:
                accessions.setdefault(normalised, key)
        name = (row.get("name") or "").strip().casefold()
        if name:
            names.setdefault(name, key)
        # The full InChIKey, never its first block. Block 1 is the molecular
        # skeleton and block 2 is stereochemistry, isotopes and protonation,
        # so a skeleton match folds D- onto L- and an acid onto its own
        # conjugate base — the identity merge the contested-accession rule
        # already refuses. The full key is an exact structural identity and
        # joins 1,232 MiMeDB records to a node HMDB wrote.
        inchikey = (row.get("inchikey") or "").strip()
        if inchikey:
            keys.setdefault(inchikey, key)
    return accessions, names, keys


def njc19_wanted_names(xlsx: Path, held: dict[str, str]) -> set[str]:
    """Casefolded spellings of the NJC19 compounds **nothing in the graph holds**.

    :func:`microbiomekg.ontology.njc19.name_variants` is the authority for what
    those spellings are, so this cannot drift from the join that consumes it —
    which is the whole reason the rule reads NJC19's file here rather than
    guessing at a list of interesting compounds.

    ``held`` is what makes it "nothing holds": a compound **any** of whose
    spellings already names a node contributes none of them. Without that
    condition this rule mints a second node for a compound the graph has under
    a different spelling, and NJC19 then prefers the new one — measured, on
    ``Propanoate (Propionate)``, which HMDB holds as ``Propionic acid``
    (CHEBI:30768) and MiMeDB names ``propanoic acid``. The head name's conjugate
    is tried before any synonym, so the MiMeDB node won and NJC19's 97
    propionate producers landed on a node HMDB's 12 were not on. One compound,
    two nodes, and D6's MES computed over half its evidence each side: the exact
    failure the conjugate rule exists to prevent, re-introduced by the source
    that was supposed to help.
    """
    try:
        import openpyxl
    except ImportError:  # pragma: no cover - openpyxl is a declared dependency
        return set()
    if not xlsx.is_file():
        return set()
    book = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    wanted: set[str] = set()
    for sheet in book.sheetnames:
        for row in book[sheet].iter_rows(values_only=True):
            compound = row[2] if len(row) > 2 else None
            if not isinstance(compound, str) or not compound.strip():
                continue
            spellings = [s.casefold() for s, _route in nj.name_variants(compound)]
            if any(spelling in held for spelling in spellings):
                continue
            wanted.update(spellings)
    book.close()
    return wanted


def default_inputs(raw: Path) -> tuple[Path, Path]:
    """``(metabolites, microbes)`` for the newest release present under ``raw``.

    v2.0 first, then v1.0. The *metabolites* file decides, because it is the one
    that writes nodes: a directory holding only a v2 microbes dump is not a v2
    build, and silently pairing a v2 microbes table with a v1 metabolites table
    would report organism counts from one release beside compound counts from
    another. The pair always comes from one directory.
    """
    for sub, tag in RELEASE_DIRS:
        base = raw / SOURCE / sub if sub else raw / SOURCE
        metabolites = base / f"mimedb_metabolites_{tag}.csv"
        if metabolites.is_file():
            return metabolites, base / f"mimedb_microbes_{tag}.csv"
    # Nothing on disk: name the preferred location, so the message a fresh
    # clone prints is the one that tells the operator where to put v2.
    base = raw / SOURCE / RELEASE_DIRS[0][0]
    return (
        base / f"mimedb_metabolites_{RELEASE_DIRS[0][1]}.csv",
        base / f"mimedb_microbes_{RELEASE_DIRS[0][1]}.csv",
    )


def microbe_report(
    path: Path, idx: TaxonomyIndex
) -> tuple[int, int, Counter, Counter, str]:
    """How many of MiMeDB's organisms carry a taxid this taxonomy still resolves.

    Printed, never loaded. It is the *taxon side* of the edge list this source
    would supply if the association between its two tables were downloadable,
    and quoting it is what stops "MiMeDB does not close D5" being read as
    "MiMeDB has no organisms".

    The ``activity`` counter is reported for the opposite reason: it is the only
    column in either dump that reads like a relation, and counting it here is
    what makes "we looked at it and it names no compound" checkable. It becomes
    neither an edge nor a property — see ``docs/model.md`` §"MiMeDB".
    """
    statuses: Counter[str] = Counter()
    activity: Counter[str] = Counter()
    rows = 0
    with_taxid = 0
    if not path.is_file():
        return 0, 0, statuses, activity, "v1.0"
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        release = mm.release_of(reader.fieldnames)
        for row in reader:
            rows += 1
            if act := cell(row, "activity"):
                activity[act] += 1
            taxid = cell(row, "ncbi_tax_id")
            if not taxid.isdigit():
                continue
            with_taxid += 1
            statuses[idx.resolve(tax_id=int(taxid), rank_ceiling="species").status] += 1
    return rows, with_taxid, statuses, activity, release


def run(
    raw: Path,
    store: Frames,
    *,
    metabolites: Path | None = None,
    microbes: Path | None = None,
    njc19: Path | None = None,
    taxdump: Path | None = None,
) -> dict[str, int]:
    """MiMeDB's tables into ``store``; returns each table's row count.

    v2.0 under ``raw/mimedb/v2/`` first, the v1.0 files beside it as the
    documented fallback. Reads HMDB's ``metabolite`` table off the store and
    NJC19's raw spreadsheet for a selection rule. Raises :class:`MissingInput`
    when the metabolites dump or the taxdump is not there.
    """

    default_metabolites, default_microbes = default_inputs(raw)
    metabolites_csv = metabolites or default_metabolites
    if not metabolites_csv.is_file():
        # "This source's raw file is not on this machine" is a skip the build
        # reports, never a defect.
        raise MissingInput(
            f"no MiMeDB metabolites dump at {metabolites_csv}\n"
            f"  place mimedb_metabolites_v2.csv and mimedb_microbes_v2.csv "
            f"(with their .xml siblings) from https://mimedb.org/downloads into "
            f"{raw / SOURCE / 'v2'}/ — see data/raw/mimedb/v2/PROVENANCE.md"
        )
    microbes_csv = microbes or default_microbes
    if not microbes_csv.is_file():
        raise MissingInput(
            f"no MiMeDB microbes dump at {microbes_csv} beside {metabolites_csv.name}"
        )
    njc19_xlsx = njc19 or (raw / "njc19" / "41597_2020_516_MOESM1_ESM.xlsx")

    try:
        taxdump = taxdump or find_taxdump(raw)
    except FileNotFoundError as e:
        raise MissingInput(str(e)) from e
    accessions, existing_names, existing_keys = load_metabolite_index(
        store.rows("metabolite")
    )
    print(
        f"metabolite table: {len(accessions):,} HMDB accessions, "
        f"{len(existing_names):,} names and {len(existing_keys):,} InChIKeys "
        f"already have a node"
    )

    wanted = njc19_wanted_names(njc19_xlsx, existing_names)
    if wanted:
        print(f"njc19 bridge: {len(wanted):,} compound spellings from {njc19_xlsx}")
    else:
        print(f"no {njc19_xlsx}; the njc19-compound selection rule selects nothing")

    # csv's default field limit is 131,072 characters and MiMeDB's `description`
    # column runs past it on the well-studied compounds — the read fails with
    # "field larger than field limit" a few thousand rows in, which looks like a
    # truncated file rather than a reader setting.
    csv.field_size_limit(1 << 30)
    with metabolites_csv.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        # The release is read off the header, not the path: see
        # `microbiomekg.ontology.mimedb.release_of`.
        release = mm.release_of(reader.fieldnames)
        records = list(reader)
    print(
        f"MiMeDB {release}: read {len(records):,} metabolite records "
        f"from {metabolites_csv}"
    )

    # normalised accession -> the MiMeDB ids claiming it. An accession two
    # records claim is not a join key; see the module docstring.
    claimants: dict[str, list[str]] = defaultdict(list)
    for row in records:
        normalised = mm.normalise_hmdb_id(cell(row, "hmdb_id"))
        if normalised:
            claimants[normalised].append(cell(row, "mime_id"))
    contested = {a for a, ids in claimants.items() if len(ids) > 1}

    metabolites = store.table(
        "metabolite",
        METABOLITE_FIELDS,
        key="metabolite_id",
        merge=True,
        owner=("source", SOURCE),
    )
    ledger = store.table(
        "unresolved_mimedb",
        LEDGER_FIELDS,
        merge=True,
        owner=("source", SOURCE),
    )

    counters: Counter[str] = Counter()
    rules: Counter[str] = Counter()
    origins: Counter[str] = Counter()

    for row in records:
        mime_id = cell(row, "mime_id")
        name = cell(row, "name")
        accession = mm.normalise_hmdb_id(cell(row, "hmdb_id"))
        observed = any(cell(row, f) == "1" for f in mm.OBSERVED_FLAGS)
        origin = cell(row, "metabolite_type")

        keep: list[str] = []
        if observed:
            keep.append("observed")
        if origin:
            keep.append("origin-classified")
        if name and name.casefold() in wanted and name.casefold() not in existing_names:
            keep.append("njc19-compound")
        if not keep:
            counters["not_selected"] += 1
            continue

        if accession and accession in contested:
            counters["contested_accession"] += 1
            ledger.add(
                {
                    "mimedb_id": mime_id,
                    "name": name,
                    "hmdb_id": accession,
                    "metabolite_id": "",
                    "reason": f"HMDB accession {accession} is claimed by "
                    f"{len(claimants[accession])} MiMeDB records "
                    f"({', '.join(claimants[accession])}): it is not a join key, "
                    f"and this record keeps its own MiMeDB identity",
                    "source": SOURCE,
                }
            )
            accession = ""

        inchikey = cell(row, "moldb_inchikey")
        held = accessions.get(accession) if accession else None
        if held is None and inchikey:
            held = existing_keys.get(inchikey)
        if held is None and name:
            held = existing_names.get(name.casefold())
        if held is not None:
            counters["already_held"] += 1
            ledger.add(
                {
                    "mimedb_id": mime_id,
                    "name": name,
                    "hmdb_id": accession,
                    "metabolite_id": held,
                    "reason": f"{held} already holds this compound: a second node would "
                    f"split the pathway and production edges that point at it, "
                    f"and Table's first-row-per-key rule would discard these "
                    f"properties anyway",
                    "source": SOURCE,
                }
            )
            continue

        for rule in keep:
            rules[rule] += 1
        if origin:
            origins[origin] += 1
        counters["loaded"] += 1
        relation_count = cell(row, "microbe_relations")
        if relation_count.isdigit():
            counters["relations_counted"] += int(relation_count)
        else:
            relation_count = ""
        # This run's own names join the index as it goes. Two MiMeDB records
        # sharing a name would otherwise become two nodes, and NJC19's name
        # index — first writer wins — would then reach whichever sorted first.
        if name:
            existing_names.setdefault(name.casefold(), f"MIMEDB:{mime_id}")
        if inchikey:
            existing_keys.setdefault(inchikey, f"MIMEDB:{mime_id}")
        metabolites.add(
            {
                "metabolite_id": f"MIMEDB:{mime_id}",
                "name": name,
                "hmdb_id": accession,
                "chebi_id": "",
                "kegg_id": "",
                "pubchem_cid": "",
                "inchikey": inchikey,
                # MiMeDB has no `status` column: HMDB's four-value detection status
                # is not this file's vocabulary, and writing a plausible-looking
                # value into a column another source's evidence rule reads would be
                # inventing evidence. `mimedb_origin` carries what this file does
                # grade on.
                "status": "",
                "biospecimens": "",
                "microbial_origin": "false",
                "origin": "",
                "chemical_formula": cell(row, "moldb_formula"),
                "secondary_accessions": "",
                "selection_rule": as_list(keep),
                "source": SOURCE,
                "mimedb_id": mime_id,
                "mimedb_origin": origin,
                "cas": cell(row, "cas"),
                "average_mass": cell(row, "moldb_average_mass"),
                "mimedb_release": release,
                # Carried verbatim, never parsed: 83 rows of the real v2 file hold
                # several VMH ids joined by "; ", so this is a list in a string and
                # a consumer that wants one has to say which.
                "vmh_id": cell(row, "vmh_id"),
                # A cross-reference, and deliberately not one of the three
                # "already holds" tests above — on 428 rows it is a *different*
                # compound's key. See mimedb.V2_ONLY_COLUMNS.
                "cmmc_inchikey": cell(row, "cmmc_inchikey"),
                "epa_substance_id": cell(row, "epa_substance_id"),
                "epa_compound_id": cell(row, "epa_compound_id"),
                # Empty on v1, which has no such column, and empty on a v2 row that
                # leaves it NULL. Never 0: that would be MiMeDB asserting no related
                # microbe, which only a filled cell says.
                mm.MICROBE_RELATION_COUNT: relation_count,
            }
        )

    print(f"loading taxdump from {taxdump} ...", flush=True)
    idx = TaxonomyIndex.from_taxdump(taxdump)
    microbe_rows, with_taxid, statuses, activity, microbe_release = microbe_report(
        microbes_csv, idx
    )

    tables = (metabolites, ledger)
    counts = {w.name: store.put(w) for w in tables}

    print(f"\nmetabolites: {len(records):,} records read from MiMeDB {release}")
    print(
        "  selection rule: " + ", ".join(f"{r} {n:,}" for r, n in sorted(rules.items()))
    )
    print(
        f"  loaded {counters['loaded']:,} new Metabolite nodes, "
        f"skipped {counters['not_selected']:,} that no rule selected"
    )
    print(
        f"  not written because the compound already has a node: "
        f"{counters['already_held']:,}"
    )
    print(
        f"  HMDB accessions two MiMeDB records claim, so not used as a join key: "
        f"{counters['contested_accession']:,} records over "
        f"{len(contested):,} accessions"
    )
    if origins:
        print(
            "  mimedb_origin: "
            + ", ".join(f"{o} {n:,}" for o, n in origins.most_common())
        )
    # The one number in the whole download that sizes the association, stated
    # beside the zero it does not close. See mimedb.MICROBE_RELATION_COUNT.
    print(
        f"  microbe_relations: {counters['relations_counted']:,} taxon-metabolite "
        f"pairs counted, 0 enumerated — MiMeDB's own count over the loaded "
        f"records, with no microbe id anywhere in any published file"
    )
    print(
        f"\nmicrobes: {microbe_rows:,} organisms, {with_taxid:,} with an NCBI taxid, "
        + ", ".join(f"{s} {n:,}" for s, n in statuses.most_common())
        + f" (MiMeDB {microbe_release})"
    )
    if activity:
        print(
            "  activity: "
            + ", ".join(f"{n:,} {a}" for a, n in activity.most_common())
            + " — names no compound, so neither an edge nor a Taxon property"
        )
    print(
        "  PRODUCES edges from MiMeDB: 0 — no published release carries an "
        "association between its two tables (microbiomekg/ontology/mimedb.py). "
        "D5 is unchanged by this source."
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

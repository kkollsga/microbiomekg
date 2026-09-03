# Sources

Every raw input to the graph: where it came from, what may legally be done with
it, what shape it arrives in, and whether `scripts/fetch.py` actually got it.

Fetched **2026-09-02**. Re-run with `python3 scripts/fetch.py` (or
`uv run --no-sync --with requests python3 scripts/fetch.py`); complete files are
skipped, partial ones resume. `data/raw/manifest.json` carries the per-file URL,
byte count, sha256, timestamp and status — it is the machine-readable twin of
this document, and the authority if the two disagree.

**Status legend** — `fetched`: on disk and checksummed. `manual`: the operator
must download it by hand; the exact blocker is recorded. `unreachable`: the host
did not answer; the exact error is recorded.

## Summary

| # | Source | Status | On disk | Path |
|---|--------|--------|--------:|------|
| 1 | NCBI Taxonomy | fetched | 1.1 GB | `data/raw/ncbi_taxonomy/` |
| 2 | BugSigDB | fetched | 46 MB | `data/raw/bugsigdb/` |
| 3 | Disbiome | **unreachable** | — | — |
| 4 | HMDB | fetched manually (user, browser) | 6.5 GB | `data/raw/hmdb/hmdb_metabolites.xml` |
| 5 | CARD | fetched | 72 MB | `data/raw/card/` |
| 6 | Reactome | fetched | 86 MB | `data/raw/reactome/` |
| 7 | KEGG | fetched | 2.4 MB | `data/raw/kegg/` |
| 8 | ChEMBL | fetched (REST subset) | 44 MB | `data/raw/chembl/` |
| 9 | gutMDisorder | fetched (Wayback 2020 snapshot) | 2.4 MB | `data/raw/gutmdisorder/` |
| 10 | PubMed / PubChem | not fetched (by design) | — | — |
| 11 | MONDO | fetched | 53 MB | `data/raw/mondo/` |
| 12 | MiMeDB | fetched manually (user, browser) | 53 MB | `data/raw/mimedb/` |
| 13 | NJC19 | fetched manually (user, browser) | 738 KB | `data/raw/njc19/` |
| 14 | MASI | fetched manually (user, browser) — **substances only** | 1.3 MB | `data/raw/masi/` |

Total on disk: **7.5 GB** across 73 files. **13 of 14 sources usable; only
Disbiome is blocked** — its origin is down and, unlike gutMDisorder, no archived
copy of its JSON API has ever existed (Wayback has never captured one, confirmed
by a domain-wide CDX query; see `data/raw/disbiome/PROVENANCE.md`).

**"Usable" is not "answers the question it was fetched for", and two of the last
three do not.** The three were fetched to close three named gaps
(`docs/usecases-and-pitfalls.md` Part B), and the outcome is one for three:

| Source | Fetched to close | What the download turned out to be | Loaded |
|---|---|---|---|
| MiMeDB | **D5**, per-taxon metabolite production | two MySQL tables with **no join between them** — zero `MMDBm` ids in the metabolites dump, zero `MMDBc` ids in the microbes dump | 935 `Metabolite` nodes, **no edges** |
| NJC19 | **D6**, consumption / cross-feeding | exactly what it says: 9,136 curated directed events, 912 of them negative | 8,905 edges over 820 taxa — D6 answered |
| MASI | **D8 / D18**, drug↔taxon | the **substance dictionary** — 1,350 rows, no organism column, no interaction column | nothing |

Each raw directory carries a `PROVENANCE.md` with the file-level profile, the
column lists, and the measurement behind the middle column. D5 moved anyway —
NJC19's export half is nearly five times HMDB's whole yield — but it moved on
the source fetched for D6, not the one fetched for it.

## Redistribution: what blocks shipping a built graph

Three sources restrict onward distribution. This matters the moment the built
`.kgl` leaves this machine.

- **KEGG — the hard blocker.** KEGG is explicitly "not a public database, nor is
  it a publicly funded database". Academic users may use the *website*; anyone
  providing a service on top of it needs an academic service-provider licence,
  and any non-academic use needs a commercial licence from Pathway Solutions.
  A graph containing KEGG pathway/compound content cannot be published freely.
  Keep KEGG-derived nodes and edges behind a build flag so a distributable graph
  can be produced without them.
- **ChEMBL — CC BY-SA 3.0, i.e. copyleft.** Redistribution is permitted, but a
  derived work incorporating ChEMBL must itself be shared under CC BY-SA. If any
  part of the graph is meant to be more permissively licensed, the ChEMBL slice
  is what forces the whole thing to share-alike. Attribution is also mandatory:
  cite Mendez et al. 2019, preserve ChEMBL IDs, display the release number (37).
- **HMDB** is free for academic/non-commercial use only, and does not grant
  redistribution — so HMDB-derived content should not ship in a public graph
  even once someone downloads it by hand.
- **CARD data** may be reproduced by academic/government/non-profit users, but
  the terms ask that materials be used "as is" and unmodified — which sits
  awkwardly with reshaping them into graph rows. The CARD **ontologies**
  (`aro.obo` and friends) carry an explicit CC BY 4.0 exception and are safe;
  prefer the ontology bundle over `card.json` wherever both would serve.

**MiMeDB is a fourth restriction: CC BY-NC 4.0**, non-commercial, the same shape
as HMDB's. It reaches only `Metabolite` nodes (935 of the 8,754), so a
commercially redistributable cut is one `WHERE m.source <> 'mimedb'` — which is
only true because `source` is on the node. The licence is **documented upstream
and not verifiable in-file**: neither dump carries a licence header.

**MASI's licence is genuinely unknown** — unstated in the files and unstated by
the database, which is a second reason nothing from it was loaded: a
`source_licence` would have to be invented for every row, and guard G3 only
works because nobody guesses it.

NCBI Taxonomy (public domain), Reactome (CC0), BugSigDB (CC BY 4.0) and **NJC19
(CC0-1.0)** place no obstacle in the way of redistribution. NJC19 is the only
fully unrestricted *association* source in the graph, which is what makes a
CC0-only subgraph — 8,905 exchange edges over 820 taxa — cuttable on its own
terms.

---

## 1. NCBI Taxonomy

- **URL** — `https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/new_taxdump/new_taxdump.tar.gz`
  (plus the `.md5` sibling)
- **Licence** — US Government work, public domain. No restriction on use or
  redistribution; citation requested, not required.
- **Format** — gzipped tar of `.dmp` files: pipe-delimited with `\t|\t`
  separators and a trailing `\t|`, no header row.
- **Size** — 160,754,260 B archive; 941 MB extracted (the five files we keep).
- **Status** — **fetched**, md5 verified against the published digest
  (`c529466d7d6d3c2069d07988f9a3ad97`, dump of 2026-09-02).

> **This file is rebuilt daily and the figures above move with it.** A rebuilt
> member can keep its byte count while changing content, so `fetch.py` ties each
> extracted `.dmp` to the sha256 of the archive it came from and re-extracts
> whenever the archive changes; the `.md5` sidecar is always refetched rather
> than cached, because at a constant 53 bytes its size can never reveal that it
> is stale. Expect these numbers to differ on a later run — that is the source
> moving, not a fault.

Only the five members the graph needs are unpacked; the rest of the tarball is
left inside it:

| File | Bytes | Rows |
|------|------:|-----:|
| `names.dmp` | 284,232,912 | 4,746,518 |
| `nodes.dmp` | 285,314,099 | 2,993,228 |
| `rankedlineage.dmp` | 397,296,008 | 2,993,228 |
| `merged.dmp` | 1,900,963 | 100,911 |
| `delnodes.dmp` | 7,611,539 | 778,118 |

`merged.dmp` and `delnodes.dmp` are what let the prep step resolve taxids that
other sources cite but NCBI has since merged or retired — without them, stale
taxids in BugSigDB or CARD silently drop rows.

## 2. BugSigDB

- **URL** — `https://raw.githubusercontent.com/waldronlab/BugSigDBExports/v1.3.1/full_dump.csv`
  (versioned, preferred) and `.../main/full_dump.csv` (rolling)
- **Licence** — CC BY 4.0, declared in the file's own first line. Cite
  Geistlinger et al. 2023, *Nat Biotechnol*, doi:10.1038/s41587-023-01872-y.
- **Format** — CSV, 51 columns. Line 1 is a `#` banner (timestamp, licence,
  URL); line 2 is the real header. Any reader must skip one line before parsing.
  Columns include Study design, PMID, DOI, Condition, EFO ID, body site with
  UBERON ID, both group sample sizes, sequencing type and abundance direction —
  i.e. exactly the evidence fields this project is built around.
- **Status** — **fetched**, both variants.

| File | Bytes | Data rows | Export timestamp |
|------|------:|----------:|------------------|
| `full_dump_v1.3.1.csv` | 16,241,290 | 7,425 | 2026-04-24 00:41 UTC |
| `full_dump_main.csv` | 32,437,371 | 14,846 | 2026-09-02 20:58 UTC |

**Which to use.** Release **v1.3.1** carries no release *assets* — the versioned
export is the file at the git tag, which is what is fetched here. It is the
reproducible choice and should be the default input. `main` is regenerated
hourly by a cron job and has since roughly doubled; it is the current data but
is not a fixed reference. Both are kept so a build can be pinned or refreshed
deliberately.

Two notes for the prep step. The v1.3.1 release notes advertise 8,153 rows where
the file parses to 7,425 — the counts are not directly comparable, so trust the
parsed number, not the release note. And rows contain embedded newlines inside
quoted fields, so `wc -l` overcounts; use a real CSV reader.

Stable DOI-versioned releases also exist on Zenodo
(`10.5281/zenodo.5606165`) if a citable pin is wanted later.

## 3. Disbiome

- **URL** — `https://disbiome.ugent.be/export/{experiment,organism,disease,method,sample,publication}`
- **Licence** — could not be established; the site is unreachable. Disbiome is
  an academic resource (Janssens et al. 2018, *BMC Microbiology*).
- **Format** — historically JSON arrays from the `/export/*` endpoints.
- **Status** — **unreachable**.

The host does not complete a TCP connection. `disbiome.ugent.be` resolves
(`ddcm04.ugent.be`, 157.193.244.183) but every attempt times out at connect,
with no HTTP response at all:

```
ConnectTimeout: HTTPSConnectionPool(host='disbiome.ugent.be', port=443):
Max retries exceeded with url: / (Caused by ConnectTimeoutError(...,
'Connection to disbiome.ugent.be timed out. (connect timeout=60)'))
```

Tried, all with the full browser header set: the front page (60 s),
`/export/experiment` (60 s) and `/main.bundle.js` (120 s, to grep the SPA for the
real API path). All three failed identically at the socket. Earlier the same day
the same endpoints did answer, returning the Angular SPA's HTML rather than JSON
even with `Accept: application/json`, so the JSON API had *already* stopped
serving before the host went dark.

Because the failure is at connect, no header, User-Agent, trailing-slash variant
or timeout can change the outcome — this needs the host to come back. Retry
later; if it answers HTML again rather than JSON, pull `main.bundle.js` and grep
it for the current endpoint. **The graph is built without Disbiome.**

## 4. HMDB

- **URL** — `https://hmdb.ca/system/downloads/current/hmdb_metabolites.zip`
  (download page: `https://hmdb.ca/downloads`)
- **Licence** — per the downloads page (read by the user 2026-09-02): "offered
  to the public as a freely available resource"; use and re-distribution for
  *commercial* purposes requires the authors' permission and acknowledgement;
  citation requested for significant downloads. Non-commercial redistribution
  with citation is therefore permitted.
- **Format** — ZIP containing one large XML document (HMDB 5.0, XML dated
  2021-11-17).
- **Status** — **fetched manually by the user** (browser download; the
  Cloudflare challenge below blocks every non-browser client).
  `data/raw/hmdb/hmdb_metabolites.xml`, 6,486,862,079 bytes, uncompressed.

Every request to `hmdb.ca` returns **HTTP 403** with `server: cloudflare` and
`cf-mitigated: challenge`, serving the "Just a moment…" interstitial. This was
tried with the complete browser header set — `User-Agent`, `Accept`,
`Accept-Language`, `Accept-Encoding`, `Referer: https://hmdb.ca/downloads`,
`Sec-Fetch-*`, `sec-ch-ua*`, `Upgrade-Insecure-Requests` — and the response is
unchanged. The challenge is `cType: 'managed'`, meaning Cloudflare requires
JavaScript execution and a cookie round-trip; **no header set can satisfy it**,
so this is not a fixable request-shaping problem. It blocks the whole domain,
which is also why the licence text could not be re-read programmatically.

**Operator action (done 2026-09-02).** The file was downloaded by hand from
<https://hmdb.ca/downloads> in a normal browser and unpacked into
`data/raw/hmdb/`. `fetch.py` detects either `hmdb_metabolites.zip` or the
unpacked `hmdb_metabolites.xml`, records it with status `manual-present`, and
does not re-attempt the blocked download. Repeat this by hand on any machine
starting from an empty `data/raw/`. `hmdb_proteins.zip` is **not** needed.

## 5. CARD

- **URL** — `https://card.mcmaster.ca/latest/data` (→ `card-data.tar.bz2`) and
  `https://card.mcmaster.ca/latest/ontology` (→ `card-ontology.tar.bz2`)
- **Licence** — two different terms in one download, and the difference matters:
  - **Data**: © McMaster University. Academic, government and non-profit users
    may reproduce it free of charge, provided it is used "as is" and unmodified,
    with McMaster credited. Commercial use or reproduction is prohibited without
    a written licence and fee.
  - **Ontologies**: explicit exception — "Ontologies at the Comprehensive
    Antibiotic Resistance Database are freely available under the Creative
    Commons CC-BY license version 4.0". `aro.obo`/`aro.json`/`aro.owl` are
    therefore the redistribution-safe half.
- **Format** — bzip2 tarballs. Data: `card.json` plus TSVs and FASTA. Ontology:
  OBO/OWL/JSON/TSV for ARO, MO, RO, VIRO and an NCBI-taxonomy slice.
- **Size** — 4,366,637 B + 1,159,321 B compressed; 72 MB extracted (36 files).
- **Status** — **fetched** and extracted into `card/card-data/` and
  `card/card-ontology/`.

Useful members: `aro_index.tsv` (6,464 rows, ARO ↔ gene/model), `PMID.tsv`
(the citing papers, feeding the evidence model), `aro_categories_index.tsv`
(drug class and resistance mechanism), and `card-ontology/aro.obo` (the term
graph, CC BY 4.0).

## 6. Reactome

- **URL** — `https://reactome.org/download/current/{ReactomePathways,ReactomePathwaysRelation,ChEBI2Reactome,ChEBI2Reactome_All_Levels,NCBI2Reactome}.txt`
- **Licence** — **CC0** (public domain dedication). Verbatim from the licence
  agreement: "All data in the Reactome database and files derived from that data
  are licensed under the Creative Commons Public Domain Dedication (CC0). User
  may copy, modify, and distribute these data, even for commercial purposes,
  without asking for permission." Attribution encouraged, not required. (Note
  this covers *data*; Reactome's illustrations are CC BY 4.0 and its software
  Apache-2.0 — neither is used here.)
- **Format** — headerless tab-separated text.
- **Status** — **fetched**, all five.

| File | Bytes | Rows |
|------|------:|-----:|
| `ReactomePathways.txt` | 1,592,393 | 23,603 |
| `ReactomePathwaysRelation.txt` | 634,259 | — |
| `ChEBI2Reactome.txt` | 14,459,535 | 113,779 |
| `ChEBI2Reactome_All_Levels.txt` | 37,553,966 | — |
| `NCBI2Reactome.txt` | 35,534,151 | 269,113 |

All species are included, not just human — filter on the trailing species column
(`Homo sapiens`, `Bos taurus`, …) during prep.

## 7. KEGG

- **URL** — `https://rest.kegg.jp` only. No FTP, no bulk download.
- **Licence** — **restrictive; see "Redistribution" above.** © Kanehisa
  Laboratories. Academic users may freely use the KEGG website; academic users
  providing a *service* on top of KEGG need an academic service-provider
  licence; non-academic use requires a commercial licence from Pathway
  Solutions. KEGG is explicitly not a public database. Do not redistribute
  KEGG-derived graph content.
- **Format** — headerless TSV, two or three columns.
- **Status** — **fetched** (5 of the 6 endpoints requested; one is retired
  upstream — see below).
- **Politeness** — sequential requests, 1 s apart, as the terms expect.

| Endpoint | File | Bytes | Rows |
|----------|------|------:|-----:|
| `/list/pathway` | `list_pathway.tsv` | 22,083 | 587 |
| `/list/pathway/hsa` | `list_pathway_hsa.tsv` | 22,117 | 372 |
| `/list/compound` | `list_compound.tsv` | 986,723 | 19,626 |
| `/link/compound/pathway` | `link_compound_pathway.tsv` | 491,175 | 19,647 |
| `/conv/compound/pubchem` | `conv_compound_pubchem.tsv` | 513,026 | 19,494 |
| `/list/genome` | `list_genome.tsv` | 480,870 | 11,945 |

**Deviation: `/list/organism` is retired.** It answers **HTTP 400** as of
2026-09-02, as does `/list/organism/` and `/list/org`. `/list/genome` is the
live organism roster and is fetched instead — but it is *not* an equivalent
substitute: it returns two columns (`T01001`, `hsa; Homo sapiens (human)`)
where `/list/organism` returned four, and the missing one is the **taxonomic
lineage**. KEGG organism codes therefore have to be joined to NCBI taxids by
another route (name matching against `names.dmp`, or per-organism
`/get/genome:Txxxxx` lookups) before KEGG pathways can be attached to taxa.
That join is a prep-step decision, not a fetch problem.

## 8. ChEMBL

- **URL** — REST API at `https://www.ebi.ac.uk/chembl/api/data/`, plus two files
  from `https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/latest/`
- **Licence** — **CC BY-SA 3.0** (copyleft — see "Redistribution" above). The
  FTP `REQUIRED.ATTRIBUTION` asks that ChEMBL IDs be preserved and the release
  number displayed, and that publications cite Mendez et al. 2019, *Nucleic
  Acids Res* 47(D1):D930–D940. Release: **ChEMBL 37**.
- **Format** — JSONL (one JSON object per line) for the API pulls; TSV for the
  UniProt mapping.
- **Status** — **fetched** (REST subset; the SQLite dump is deliberately
  skipped).
- **Politeness** — 0.25 s between calls (≤ 4 req/s, inside the ≤ 5 req/s budget),
  with backoff on 429.

| File | Bytes | Rows | Source |
|------|------:|-----:|--------|
| `mechanism.jsonl` | 5,483,897 | 7,561 | `/mechanism.json`, paged at 1,000 |
| `molecule_max_phase4.jsonl` | 12,842,542 | 4,225 | `/molecule.json?max_phase=4`, field-trimmed |
| `target.jsonl` | 23,746,166 | 1,518 | `/target.json`, only ids cited by mechanisms |
| `chembl_uniprot_mapping.txt` | 1,254,330 | 17,258 | FTP |
| `LICENSE` | 21,142 | — | FTP (kept as the licence of record) |

`mechanism.jsonl` is the drug→target edge list. Targets are not fetched wholesale
(18,552 exist); only the 1,518 actually referenced by a mechanism, batched 50 ids
at a time through `target_chembl_id__in`. The molecule pull uses `only=` to keep
13 of 34 fields — verified to genuinely trim the response rather than be ignored.

**`chembl_37_sqlite.tar.gz` (5.76 GB) is not fetched by default.** It sits behind
`--chembl-sqlite`. Nothing in the current model needs it; the REST subset above
supplies the drug→target edges at 44 MB instead of 5.76 GB.

## 9. gutMDisorder

- **URL** — origin `http://bio-annotation.cn/gutMDisorder/` (down); bytes came
  from Wayback Machine snapshots of the site's own bulk exports — see the
  update below for the exact snapshot URLs.
- **Licence** — unstated by the site; the NAR 2020 paper says only "freely
  available". Treat as unknown until the authors are asked.
- **Format** — XLSX, one workbook each for human and mouse.
- **Status** — **fetched** (2020 v1 snapshot). The *origin* remains unreachable:

DNS resolves (`47.76.215.223`) but the host **refuses the connection** on both
ports, immediately — this is a refusal, not a timeout:

```
ConnectionError: HTTPConnectionPool(host='bio-annotation.cn', port=80):
Max retries exceeded with url: /gutMDisorder/ (Caused by NewConnectionError(
'Failed to establish a new connection: [Errno 61] Connection refused'))
```

Tried `http://` and `https://` with the full browser header set, and
`http://www.bio-annotation.cn/` separately. All refused in under half a second.
As with Disbiome, the failure precedes HTTP, so no request shaping helps — but
unlike Disbiome, an archived copy of the bulk export exists, so the data is
usable anyway.

**Update 2026-09-02 (coordinator):** the origin stays down, but the site's own
bulk exports were captured by the Wayback Machine and downloaded from the
exact snapshot URLs (browser User-Agent; playback returns 429 intermittently,
retry after a pause):

| File | Snapshot | Bytes | sha256 | Sheets (rows) |
|---|---|---:|---|---|
| `data/raw/gutmdisorder/human.xlsx` | 20200812224039 | 1,643,490 | 4e0984d2…7dfceae | Literature 325, Sample 724, Association 2,263 |
| `data/raw/gutmdisorder/mouse.xlsx` | 20200812224042 | 728,405 | 68ceb9f1…8bac30c504 | Literature 190, Sample 563, Association 930 |

This is the 2020 (v1) release; the 2022 update (gutMDisorder 2.0) was never
archived. Association rows carry `Gut Microbiata NCBI ID`, `Classification`
(rank), `P Value`, `Statistical Method`, `Alteration` (increase/decrease);
Literature rows carry `PMID`, `DOID`, `Research Type`, `Intervention`.
Licence: unstated by the site; the NAR 2020 paper says "freely available".

## 10. PubMed / PubChem

- **Status** — **not fetched, by design.**

No bulk download is taken from either. Paper identifiers arrive already attached
to the evidence rows of the other sources — PMIDs in BugSigDB's `PMID` column and
in CARD's `PMID.tsv` — and compound cross-references come from KEGG's
`/conv/compound/pubchem` (19,494 KEGG compound → PubChem SID mappings). Pulling
the full PubMed or PubChem corpus would add tens of gigabytes to resolve
identifiers the graph already has.

If paper *metadata* (title, journal, year) is wanted beyond what BugSigDB already
carries, fetch it per-PMID from NCBI E-utilities at build time rather than in
bulk. Both resources are public domain, so nothing here is a licence decision.

## 12. MiMeDB

- **URL** — `https://mimedb.org/downloads` (the CSV and XML dumps). The site
  answers automated clients with **403**, the same Cloudflare posture HMDB has,
  so the four files arrived by hand.
- **Licence** — **CC BY-NC 4.0**, non-commercial. Stated on `mimedb.org` and in
  the NAR papers; **no licence header, copyright line or terms URL appears in
  any of the four files**, so it is documented-upstream and unverified-in-file.
  Treated as binding regardless, and carried per node as `source_licence`.
- **Format** — two MySQL table dumps, each as CSV and as zipped XML.
- **Status** — **fetched manually**; profiled in
  `data/raw/mimedb/PROVENANCE.md`; **loaded as `Metabolite` nodes only.**

| File | Bytes | sha256 | Rows |
|---|---:|---|---:|
| `mimedb_metabolites_v1.csv` | 47,064,986 | `38646178…39d7f3c8` | 27,641 |
| `mimedb_metabolites_v1.xml.zip` | 5,529,818 | `8de2bfa7…6eef32d5` | same rows |
| `mimedb_microbes_v1.csv` | 861,977 | `fa7c4756…6a9e8ab9` | 2,174 |
| `mimedb_microbes_v1.xml.zip` | 166,824 | `d4bd4228…4fb58314` | same rows |

The XML headers are the only version statement anywhere in the download, and
they are precise: a Sequel Ace dump of database `mimedb` taken **2024-03-19**,
whose queries are `SELECT * FROM metabolites WHERE export = 1` and `SELECT *
FROM microbes WHERE export = 1`. So this is **v1.0**, not the v2.0 the 2026 NAR
paper describes.

**The finding: there is no association between the two tables, so this source
cannot answer D5.** The research document (§1.7) sizes MiMeDB by its *Microbial
Sources* and *Metabolic Reactions* categories — precursor, product, enzyme,
enzyme's source organism, reaction type. Neither is in these files. Measured on
the bytes: the metabolites dump contains the string `MMDBm` **0 times**, the
microbes dump contains `MMDBc` **0 times** and `metabolite` **0 times**, and
neither has a precursor, product, enzyme or reaction column. The only column in
either that looks like a relation is `microbes.activity` — `NULL` on 2,129 of
2,174 rows, `Production (export)` on 43 — **which names no compound**. Deriving
an edge from it would manufacture exactly the claim D5 asks for out of a field
that does not make it, so `scripts/prep_mimedb.py` declares no relationship at
all and the build report prints `PRODUCES edges from MiMeDB: 0`.

**What it does contribute is compound identity, and it is measurable.** NJC19
carries no ChEBI, HMDB, KEGG or PubChem id for any of its 283 compounds, so its
join to the graph is by name; MiMeDB's names are what give some of those
compounds a node with an InChIKey and a formula instead of a minted stub. 935
nodes are loaded under a three-rule selection — `observed` (`detected` or
`quantified` = 1), `origin-classified` (`metabolite_type` filled), and
`njc19-compound` (a spelling NJC19 uses that **nothing in the graph already
answers**) — and `Metabolite.selection_rule` records which.

Two identity traps in the `hmdb_id` column, both of which merge distinct
compounds if taken literally: it holds **both** the padded (`HMDB0003402`) and
the legacy five-digit (`HMDB03402`) spelling, and after normalising that,
**149 accessions are claimed by two MiMeDB records each** — `HMDB0000158` by
both `L-Tyrosine` and `D-Tyrosine`, `HMDB0000598` by `Sulfide` and `Sulfur`. A
contested accession is not used as a join key. Full details, column lists and
distributions: `data/raw/mimedb/PROVENANCE.md`.

## 13. NJC19

- **URL** — the Scientific Data article's supplementary file,
  `https://static-content.springer.com/esm/art%3A10.1038%2Fs41597-020-0516-5/MediaObjects/41597_2020_516_MOESM1_ESM.xlsx`,
  plus PMC's supplementary bundle for PMC7320173. Data deposit:
  Dryad doi:10.5061/dryad.dr7sqv9v8.
- **Licence** — **CC0-1.0**, verified via the Dryad API (recorded in
  `docs/research/researcher-workflows.md` §1.10). Not verifiable from the files:
  the xlsx carries no licence sheet or document property. The only fully
  unrestricted association source in the graph.
- **Format** — one XLSX worksheet.
- **Status** — **fetched manually; loaded**, and it is the source that closed
  D6.

| File | Bytes | sha256 |
|---|---:|---|
| `41597_2020_516_MOESM1_ESM.xlsx` | 238,565 | `8ed11149…cd9c2abe` |
| `PMC7320173_supplementaryFiles.zip` | 516,630 | `e4d349dc…1b1eeec1` |

The zip holds seven entries — the three figures at two resolutions each, and
`41597_2020_516_MOESM1_ESM.xlsx` **byte-identical to the loose copy**. One
spreadsheet, not two; the loader reads the loose one.

**`Online-only Table 5`**: 9,141 rows — three legend lines, a blank, a header,
and **9,136 curated metabolic associations**. Five columns, of which column A is
empty on every data row (it is the legend's indent). `Species` holds 844
free-text names with **no taxid**; `Small-molecule metabolite or macromolecule`
holds 283 names in a `Head (synonym, synonym)` grammar with **no cross-reference
of any kind**; `Metabolic activity` is a closed seven-value vocabulary; `Ref. #`
indexes the paper's own Online-only Table 2 and is **not PMIDs**, so no `Paper`
node is minted.

Three shapes a straight read gets wrong, all three defined by the sheet's own
legend:

- **912 rows carry a `(-)` marker** — the literature says the activity does
  *not* occur. Matching the published count exactly. They load as their own
  relationship, `NO_EXCHANGE_WITH`, rather than a flag on the positive edge.
- **180 rows carry two activities**, `Consumption (import), Production
  (export)`, and every one of them also carries a *scoped* reference cell
  (`import:415, 418;export:417`) so the two literatures stay separable.
- **`(G)` lives in the reference column, not the species column**, and marks a
  reference read at genus level. 3,018 rows carry at least one; **2,426 (26.6%)
  carry nothing else** — a species-filed row whose entire basis is genus-level
  literature. Every edge carries `genus_level_evidence` (guard G5).

Six `Species` values are **host cell types**, not organisms (`human colonocyte`,
`human goblet cell`, `human hepatocyte`, `mouse goblet cell`, `mouse
hepatocyte`, `mouse intestinal cell`) — matching the paper's "838 microbial
species + 6 host cell types" exactly. They are excluded by name rather than left
to fail reconciliation, which would file six cell types as six taxa NCBI lost.
Of the 838 species names, **823 resolve and every one lands at rank `species`**
(670 exact, 151 synonym, 2 promoted); the 15 that do not are nomenclatural churn
— eight *Mycoplasma* species from the 2018 split, three *Lactobacillus* species
from the 2020 one, and two names two taxa share, which are refused rather than
guessed. Full profile: `data/raw/njc19/PROVENANCE.md`.

## 14. MASI

- **URL** — `https://masi.idrblab.net/` (download page). The site has an
  **expired TLS certificate**; the two files arrived by hand.
- **Licence** — **unknown.** No licence line, copyright notice, terms URL or
  document property in either file, and the database states none
  (`docs/research/researcher-workflows.md` §1.11: "No separate database
  license").
- **Format** — one table, as tab-separated text and as XLSX.
- **Status** — **fetched manually; NOT loaded.** No prep script, no blueprint
  fragment, no ontology module.

| File | Bytes | sha256 |
|---|---:|---|
| `MASI_v1.0_download_substanceInfo.txt` | 872,454 | `d526701f…631e9fa8` |
| `MASI_v1.0_download_substanceInfo.xlsx` | 438,118 | `ad8aa6f2…0ba2223d` |

**The two are the same table in two encodings** — 1,350 data rows, the same 18
columns in the same order — and the filename says what it is: `substanceInfo`.
It is the **substance dictionary**, and it names **no bacterium anywhere**:
there is no organism column, no interaction column, no effect, no direction and
no PubMed id. The two edge sets the research document sizes MASI by
(bacteria→substance **4,001** pairs, substance→bacteria **7,770**) are in
neither file.

So **D8 and D18 stay `partial` on exactly the two legs they already had** —
ChEMBL's drug→bacterial-protein mechanism and gutMDisorder's intervention edge
joined to ChEMBL by name — and `tests/test_acceptance.py` asserts that, including
that `MATCH (d:Drug)-[r]-(t:Taxon)` still returns **0**. Loading the substances
anyway would add 1,350 unconnected nodes; the ones ChEMBL already has cannot be
enriched, because `drug.csv` is keyed on the ChEMBL id and the first row per key
wins. The one true statement derivable from the file — "MASI curates at least
one experimentally determined microbiota interaction for this substance", its
stated inclusion criterion — names no organism and so answers neither query.

What would close them is MASI's separate interaction downloads, and Part D
already specifies how they must land: **two edge types, `ALTERS_TAXON` and
`ALTERS_SUBSTANCE`, never one**, because collapsing them conflates antimicrobial
killing with drug metabolism. Full profile: `data/raw/masi/PROVENANCE.md`.

---

## How `scripts/fetch.py` behaves

- **Browser session by default.** Every request — not only retries — carries the
  full header set (`User-Agent`, `Accept`, `Accept-Language`, `Accept-Encoding`,
  `Sec-Fetch-*`, `sec-ch-ua*`, `Upgrade-Insecure-Requests`) with `Referer` set
  per host to that site's front page.
- **Sizing and resumption speak identity encoding.** `Content-Length` describes
  bytes on the wire, but `requests` transparently decodes gzip, so a compressed
  response writes *more* bytes than the header advertises
  (raw.githubusercontent.com: 1,708,429 gzipped vs 16,241,290 plain). Every HEAD
  and every ranged GET sends `Accept-Encoding: identity` so the advertised length
  is the length actually written and byte offsets line up.
- **A bare filename means complete.** Downloads land in `<name>.part` and are
  renamed only once the body is whole, so a partial file can never be mistaken
  for a finished one.
- **Resume** uses HTTP Range where the server advertises `Accept-Ranges: bytes`,
  and restarts cleanly where it does not. Verified end-to-end: a file truncated
  to 8,000,000 of 16,241,290 bytes resumed and came out byte-identical
  (sha256 `af84bfca…`) to the full download.
- **Failures are recorded, not fatal.** A dead source is written to the manifest
  with its exact error and the run continues.
- **Hand-placed files are adopted, not overwritten.** Where a host blocks
  automated download (HMDB), an operator-supplied file is detected, hashed and
  recorded as `manual-present` instead of re-attempting the 403.
- **gutMDisorder is fetched from Wayback**, since its origin refuses
  connections; playback is rate-limited, so the two requests are spaced 8 s
  apart and the origin is only probed if a file is missing.
- **Large files are not re-hashed needlessly.** A SHA-256 is recomputed only
  when size or mtime has moved, so the 6.5 GB HMDB drop costs one hash, not one
  per run.

### Flags

| Flag | Effect |
|------|--------|
| `--chembl-sqlite` | also pull the 5.76 GB ChEMBL SQLite dump |
| `--only SOURCE` | run one source (repeatable) |
| `--force` | re-download even when a complete file is present |

Source names: `ncbi`, `bugsigdb`, `disbiome`, `hmdb`, `card`, `reactome`,
`kegg`, `chembl`, `gutmdisorder`, `pubmed`.

## 11. MONDO (disease id hub) — added by the coordinator, 2026-09-02

- **URL** — `https://github.com/monarch-initiative/mondo/releases/latest/download/mondo.obo`
  (release 2026-09-01; the `mondo.sssom.tsv` asset is not published on this
  release, HTTP 404).
- **Licence** — CC BY 4.0.
- **Format** — OBO. Equivalences are `xref:` lines carrying
  `source="MONDO:equivalentTo"`: 2,400 to EFO (BugSigDB's disease ids) and
  12,091 to DOID (gutMDisorder's), plus MeSH/NCIT/UMLS.
- **Status** — fetched. `data/raw/mondo/mondo.obo`, 53,134,854 bytes, sha256 in
  `data/raw/mondo/PROVENANCE.md`.
- **Why** — the schema survey (`docs/research/existing-graphs-and-schemas.md`)
  recommends MONDO as the canonical disease key with source ids kept as
  properties; without it, the same condition arrives as an EFO id from one
  source and a DOID from another and never joins.

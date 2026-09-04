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
| 12 | MiMeDB | fetched manually (user, browser) — v2.0 loaded, v1.0 kept as fallback | 230 MB | `data/raw/mimedb/v2/`, `data/raw/mimedb/` |
| 13 | NJC19 | fetched manually (user, browser) | 738 KB | `data/raw/njc19/` |
| 14 | MASI | fetched manually (user, browser) — all four tables | 7.1 MB | `data/raw/masi/` |
| 15 | Maier 2018 drug screen | fetched | 1.0 MB | `data/raw/drug_screens/maier2018/` |
| 16 | Zimmermann 2019 drug-metabolism screen | fetched | 40 MB | `data/raw/drug_screens/zimmermann2019/` |

Total on disk: **7.5 GB** across 88 files. **15 of 16 sources usable; only
Disbiome is blocked** — its origin is down and, unlike gutMDisorder, no archived
copy of its JSON API has ever existed (Wayback has never captured one, confirmed
by a domain-wide CDX query; see `data/raw/disbiome/PROVENANCE.md`).

**"Usable" is not "answers the question it was fetched for", and one of these
five still does not.** Five sources were fetched to close three named gaps
(`docs/usecases-and-pitfalls.md` Part B), and the outcome is four for five —
including the two that arrived as the *substitute* for the source that was
wrongly written off, and which arrived first and answered better:

| Source | Fetched to close | What the download turned out to be | Loaded |
|---|---|---|---|
| MiMeDB | **D5**, per-taxon metabolite production | two MySQL tables with **no join between them**, in v1.0 **and** in v2.0 — zero `MMDBm` ids in the metabolites dump, zero `MMDBc` ids in the microbes dump, CSV and XML alike. v2.0 added a `microbe_relations` **count** (830,984 pairs) that names none of them | 1,237 `Metabolite` nodes, **no edges** |
| NJC19 | **D6**, consumption / cross-feeding | exactly what it says: 9,136 curated directed events, 912 of them negative | 8,905 edges over 820 taxa — D6 answered |
| MASI | **D8 / D18**, drug↔taxon | all four tables, and **an aggregator**: 66.4% of its 12,512 interaction rows cite one of the two screens below, and 62.5% of the edges it produces restate a pair one of them already *measured* | **13,122 edges** over 542 taxa, 1,350 `Substance` nodes and probiotic annotation on 540 taxa — none of it on a relationship a screen owns |
| Maier 2018 | **D8 / D18**, drug↔taxon — fetched while MASI's interaction tables were believed unrecoverable | the whole published screen: 1,197 drugs x 40 gut isolates, one adjusted p-value per cell | **47,825 edges** over 38 taxa and 1,197 drugs — the first direct `Drug`–`Taxon` edge in the graph |
| Zimmermann 2019 | **D8**, the *other* direction — does the bug change the drug | the whole published screen again: 271 oral drugs x 76 gut strains, with each drug's own depletion threshold | **20,054 edges** over 66 taxa and 271 drugs — the first `Taxon`–`Drug` edge, and what closed D8 |

Each raw directory carries a `PROVENANCE.md` with the file-level profile, the
column lists, and the measurement behind the middle column. D5 moved anyway —
NJC19's export half is nearly five times HMDB's whole yield — but it moved on
the source fetched for D6, not the one fetched for it. D8 moved on the two
sources fetched *because MASI was thought to have failed*, and that turned out
to be the better order: the aggregator arrived after the primary sources it
aggregates, so the graph could **measure** the overlap instead of accumulating
it (§14). Had MASI landed first, 7,161 restatements would have been
indistinguishable from measurements.

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
as HMDB's. It reaches only `Metabolite` nodes (1,237 of the 9,056), so a
commercially redistributable cut is one `WHERE m.source <> 'mimedb'` — which is
only true because `source` is on the node. The licence is **documented upstream
and not verifiable in-file**: none of the six dumps across the two releases
carries a licence header, and the v2.0 downloads page that states it has never
been fetched — it is behind the same Cloudflare challenge as the files.

**MASI's licence is genuinely unknown** — unstated in all eight files and
unstated by the database. It is a fifth restriction rather than a reason not to
load: every MASI edge carries `source_licence = 'MASI-unstated'`, a real token
that says what is known, and because G3 puts the licence on the edge the
redistributable cut is one `WHERE`. It is deliberately a *third* unstated token
beside `Maier2018-unstated` and `Zimmermann2019-unstated`, because three
unstated permissions are three permissions and excluding one is no reason to
lose the others.

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

- **URL** — `https://mimedb.org/downloads` (the CSV and XML dumps). The site is
  behind an **interactive Cloudflare challenge**, the same posture HMDB has, so
  no client that does not run JavaScript can reach it and every file arrived by
  hand.
- **Licence** — **CC BY-NC 4.0**, non-commercial, and **not verified**. None of
  the files across either release carries a licence header, copyright line or
  terms URL, and the downloads page that states it has never been fetched
  either — it is behind the same challenge. The statement is from `mimedb.org`
  and the NAR papers, recorded in `docs/research/researcher-workflows.md` §1.7.
  Treated as binding regardless, and carried per node as `source_licence`.
- **Format** — two MySQL table dumps, each as CSV and as XML.
- **Status** — **fetched manually**; **v2.0 is the release loaded**, with v1.0
  kept beside it as the fallback. Profiled in
  `data/raw/mimedb/v2/PROVENANCE.md` (v1.0: `data/raw/mimedb/PROVENANCE.md`);
  **loaded as `Metabolite` nodes only.**

### v2.0 — the loaded release

| File | Bytes | sha256 | Rows |
|---|---:|---|---:|
| `mimedb_metabolites_v2.csv` | 53,541,177 | `97d2d0cc…8fe16ba3` | 29,295 |
| `mimedb_metabolites_v2.xml` | 109,403,982 | `6781aced…9648fe02` | same rows |
| `mimedb_microbes_v2.csv` | 5,277,049 | `152bd573…354d1671` | 2,648 |
| `mimedb_microbes_v2.xml` | 9,539,893 | `7c6c8714…7de07734` | same rows |

Downloaded by the user in a browser on **2026-09-03**. The XML headers are the
only version statement anywhere in the download, and they are precise: a Sequel
Ace dump of database `mimedb` taken **2025-10-08**, whose queries are `SELECT *
FROM metabolites WHERE export = 1` and `SELECT * FROM microbes WHERE export = 1`
— the same tool, host and queries as v1.0's 2024-03-19 dump. Nothing in any file
states a version number; the release is established by the dump date, the row
counts and four new columns.

**The `export = 1` filter matters on the microbe side.** The NAR paper sizes
v2.0 at 3,725 microbes; this dump has 2,648. The metabolites dump's 29,295
matches the paper exactly. So the metabolite table is published whole and the
microbe table is not.

v1.0 (`data/raw/mimedb/`, dumped 2024-03-19) is 27,641 metabolites and 2,174
microbes, in the same four-file shape with the XML zipped. Every v1 `microbe_id`
is present in v2, so v2 is a strict superset by organism.

### The finding: no published release has the pair table

**Neither v1.0 nor v2.0 carries an association between its two tables, so this
source cannot answer D5 — and no other bulk file publishes those pairs
either.** The research document (§1.7) sizes MiMeDB by its *Microbial Sources*
and *Metabolic Reactions* categories — precursor, product, enzyme, enzyme's
source organism, reaction type — and puts v2.0 at 25,276 curated reactions.
Neither category is in any of these files.

Measured on the bytes of all four v2 files, with the control counted in the same
pass, because a zero from a pattern that matches nothing is not a measurement:

| pattern | metabolites CSV | metabolites XML | microbes CSV | microbes XML |
|---|---:|---:|---:|---:|
| `MMDBc` (a **metabolite** id) | 29,295 | 29,295 | **0** | **0** |
| `MMDBm` (a **microbe** id) | **0** | **0** | 2,648 | 2,648 |

Each id appears exactly once per row of its own table and never once in the
other's. There is no precursor, product, enzyme, reaction or source-organism
column in either. The same two zeros hold on v1.0.

**v2.0 publishes the *size* of the association and not its contents.** Its new
`microbe_relations` column is an integer per metabolite — MiMeDB's own count of
related microbes — filled on all 29,295 rows, minimum 0, maximum 4,055,
**summing to 830,984 taxon–metabolite pairs**, with no microbe id anywhere in
the file to say which. It is loaded as
`Metabolite.mimedb_microbe_relation_count`, deliberately not under the source's
own column name: a property called `microbe_relations` on a node in a graph
holding zero MiMeDB edges reads as a degree.

**Those 830,984 pairs are reachable only through the site's per-metabolite web
pages** — the per-microbe "download all related metabolites as CSV" button the
research document named is the same relation from the other side. Both are web
actions behind the Cloudflare challenge, and **this project does not scrape
them.** So the question is closed rather than open: it is not that the right
bulk file has not been found, it is that the pairs are not in a bulk file.

The only column in either table that looks like a relation is
`microbes.activity`, empty on 2,533 of 2,648 rows, `Production (export)` on 113
and `Consumption (import)` on 2 — **naming no compound**. Deriving an edge from
it would manufacture exactly the claim D5 asks for out of a field that does not
make it, so `microbiomekg/preps/prep_mimedb.py` declares no relationship at all, does not
load the column in any other form either (`docs/model.md` §"MiMeDB" gives the
reason), and the build report prints `PRODUCES edges from MiMeDB: 0`.

The string `metabolite` does appear 125 times in the v2 microbes dump, all of it
inside the new free-text `description` column — generated prose with no compound
column, no direction and no citation. That is not an association either.

### What it does contribute: compound identity

NJC19 carries no ChEBI, HMDB, KEGG or PubChem id for any of its 283 compounds,
so its join to the graph is by name; MiMeDB's names are what give some of those
compounds a node with an InChIKey and a formula instead of a minted stub.
**1,237 nodes** are loaded under a three-rule selection — `observed` (`detected`
or `quantified` = 1), `origin-classified` (`metabolite_type` filled), and
`njc19-compound` (a spelling NJC19 uses that **nothing in the graph already
answers**) — and `Metabolite.selection_rule` records which. Every node also
carries `mimedb_release`, so a graph that outlives its build log can still say
which release is in it.

v2 added three cross-references this graph has no other source for, all now on
the node: `vmh_id` (Virtual Metabolic Human; 83 rows of the file hold several
ids joined by `; `, so it is stored verbatim rather than parsed) and the EPA
DSSTox pair `epa_substance_id` / `epa_compound_id`.

Three identity traps in the file, all of which merge distinct compounds if taken
literally. `hmdb_id` holds **both** the padded (`HMDB0003402`) and the legacy
five-digit (`HMDB03402`) spelling — 258 of 3,904 filled values are legacy — and
after normalising that, **149 accessions are claimed by two or more MiMeDB
records each, over 329 records**: `HMDB0000158` by both `L-Tyrosine` and
`D-Tyrosine`, `HMDB0000598` by `Sulfide` and `Sulfur`. A contested accession is
not used as a join key. And **new in v2**, `cmmc_inchikey` is *not* the record's
own structure — it is the parent compound's key in the Chemically Modified
Microbial Compounds set, and differs from the row's own `moldb_inchikey` on 428
of the 1,763 rows that fill it, so it is carried as a cross-reference and never
matched on. Full details, column lists and distributions:
`data/raw/mimedb/v2/PROVENANCE.md`.

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

- **URL** — `https://www.aiddlab.com/MASI/downloadFiles/<filename>`, linked from
  `https://www.aiddlab.com/MASI/download.html`. The host's **TLS certificate is
  expired**, which is why no programmatic fetch reaches it and why the Wayback
  Machine holds only one of the eight files; all eight arrived by hand on
  **2026-09-03**, through the browser's certificate warning.
- **Licence** — **unknown.** No licence line, copyright notice, terms URL or
  document property in any of the eight files, and the database states none
  (`docs/research/researcher-workflows.md` §1.11: "No separate database
  license"). Every MASI edge carries `source_licence = 'MASI-unstated'`.
- **Format** — four tables, each as tab-separated text and as XLSX.
- **Status** — **fetched manually; loaded.** `microbiomekg/preps/prep_masi.py`,
  `microbiomekg/blueprints/masi.json`, `microbiomekg/ontology/masi.py`, `tests/test_masi.py`.
- Paper: Zeng et al., *Nucleic Acids Research* 49:D776 (2021), **PMID 33313900**.

| File | Bytes | sha256 |
|---|---:|---|
| `..._microbeSubstanceInteractionRecords_ver20200928.xlsx` | 1,433,420 | `d54c255b…5061413566` |
| `..._microbeDiseaseAssociationRecords.xlsx` | 54,229 | `9d28d7ea…f2e7e1635f` |
| `..._microbesInfo.xlsx` | 75,513 | `b3b4f8e4…b35d9530ca` |
| `..._substanceInfo.xlsx` | 438,118 | `ad8aa6f2…0ba2223d` |

The `.txt` twins are on disk too and carry the same data; their checksums are in
`data/raw/masi/PROVENANCE.md`.

### The retraction this section owes

**The 2026-09-02 version of this section said the interaction tables were
"unrecoverable". That was wrong, and the mechanism of the error is worth
keeping.** `www.aiddlab.com` is not a dead host — its certificate expired. Every
fetch attempt failed at the TLS handshake and was recorded as unreachable; the
Wayback Machine will not archive a host it cannot handshake with either, so the
domain-wide CDX query returned only the one file a person had once saved by
hand, and the two facts corroborated each other into a wrong conclusion. A
browser asks the user and then proceeds. **A negative reached by two mechanisms
that share a cause is one observation, not two** — and the cheap experiment that
would have settled it (`curl -k`) was never run before the claim was committed
to three documents.

### The `.xlsx` is read and the `.txt` is not

Three of the four `.txt` files are honest TSV. **`microbesInfo.txt` is not**: its
header row contains **zero tab characters**, its columns are space-padded to a
width, and its values contain single spaces of their own
(`Bifidobacterium ruminatum`), so no delimiter rule recovers it. All four
`.xlsx` carry one `Sheet1` with typed cells and the same header, so one reader
serves all four and the awkward one is not a special case — which matters most
on the 24-column interaction table, where a mis-split moves a p-value into a
mechanism field.

### What is in the four tables

| Table | Rows × cols | What it carries |
|---|---|---|
| interaction records | **12,512 × 24** | two `Interaction_Category` values — `Substances alter microbe abundance` 8,217 and `Microbes metabolize substances` 4,295 — giving exactly the 7,770 and 4,001 distinct pairs the research document sizes MASI by. So this **is** the complete published interaction set. |
| disease associations | 784 × 11 | taxon–disease abundance changes with a PMID each, 56 diseases named and **never coded**: no DOID, MONDO or EFO column anywhere. |
| microbe dictionary | 806 × 14 | NCBI ids at four ranks — which recovers a taxid for 3,007 interaction rows the interaction table leaves at `n.a.` — plus `if_probiotic` on 46 organisms. |
| substance dictionary | 1,350 × 18 | eight cross-reference columns, **none of which reaches anything**: there is no ChEMBL id, and the fetched ChEMBL molecule JSONL carries no cross-references at all. |

### MASI is an aggregator, and 62.5% of what it says was already measured here

**5,419 of its interaction rows cite PMID 29555994 (Maier 2018) and 2,884 cite
PMID 31158845 (Zimmermann 2019)** — 66.4% of the file — and both papers are
already in this graph, loaded from their own supplementary tables with all
47,825 and 20,054 *measured* cells, negatives included. Resolved to (taxon,
compound) pairs, **7,161 of the 11,456 edges MASI produces restate a pair one of
those two screens already measures.**

That number, not a preference about node types, is why MASI's substances are
`Substance` nodes and its four interaction relationships are its own
(`docs/model.md` §MASI). Had its metabolism records landed on `METABOLISES`,
`MATCH (t:Taxon)-[:METABOLISES]->(d:Drug)` — the query D8 is written as — would
have counted a curated restatement and a measured screen cell as two
observations, with nothing in the query text to say so.
`duplicates_primary_source` names the overlapping source on every edge, so
"what does MASI *add*" is one `WHERE r.duplicates_primary_source IS NULL`.

### What it loaded

**11,456 interaction edges over 542 taxa and 1,350 substances**, as four
relationships: `METABOLISES_SUBSTANCE` 3,356, `DOES_NOT_METABOLISE_SUBSTANCE`
16, `ABUNDANCE_CHANGED_BY_SUBSTANCE` 7,579, `ABUNDANCE_UNCHANGED_BY_SUBSTANCE`
505. Plus **883 `SAME_COMPOUND_AS` edges** onto the `Drug` nodes ChEMBL and the
two screens own, **783 `ASSOCIATED_WITH` edges** into the shared taxon–condition
table as its fourth source, and MASI's probiotic annotation on **540 `Taxon`
nodes** (44 of them `probiotic = true`).

`evidence_level` is derived per row from `Experiment_System` and
`Experiment_Model_Species` rather than defaulted: **`in-vitro` 8,272, `unknown`
2,249, `in-vivo-model` 935**. The disease half is `unknown` on all 783, because
that export has no design, host, sequencing, test or arm-size column — 8 of the
fourteen contract properties are fillable and the other six describe a study
this source does not describe.

**What it refuses.** 1,048 interaction records name a microbe that reaches no
NCBI id — 474 of them `Unclassified gut microbiota` and 311 `Unidentified gut
microbes`, which is why only 16 of the 404 curated *non*-metabolism statements
survive; 8 records carry a `Microbe_Change` with no direction this model can
write; 15 of the 56 diseases reach no MONDO term and keep `MASI:DIS<n>`. All of
it is in the `unresolved_masi` table on the build result and the `UnresolvedTaxon` tombstones.

## 15. Maier 2018 — the drug screen, and the source that actually closed D8

- **URL** — Europe PMC's supplementary bundle for the author manuscript,
  `https://www.ebi.ac.uk/europepmc/webservices/rest/PMC6108420/supplementaryFiles`,
  a zip holding the six `NIHMS76168-supplement-Supplementary_table_*.xlsx`
  workbooks and their information guide. Paper: Maier et al., *Nature*
  555:623-628 (2018), doi:10.1038/nature25979, **PMID 29555994**.
- **Licence** — **unstated.** Journal supplementary material of a subscription
  article: no licence line, no terms URL and no document property in any of the
  six workbooks, and Nature states none for supplementary files. Every edge
  carries `source_licence = 'Maier2018-unstated'` rather than an invented
  permissive token, which is what makes `WHERE r.source_licence <>
  'Maier2018-unstated'` the redistributable cut (G3).
- **Format** — six XLSX workbooks, eight sheets between them.
- **Status** — **fetched; loaded**, and it is the source that closed D8's
  drug→taxon leg after MASI's interaction tables proved unrecoverable.

| File | Bytes | sha256 |
|---|---:|---|
| `NIHMS76168-supplement-Supplementary_table_1.xlsx` | 206,502 | `c5415eea…a654eb04` |
| `NIHMS76168-supplement-Supplementary_table_2.xlsx` | 52,255 | `d0109fa9…75b0dbca` |
| `NIHMS76168-supplement-Supplementary_table_3.xlsx` | 508,728 | `c3590a0c…29c55506` |
| `NIHMS76168-supplement-Supplementary_table_4.xlsx` | 62,825 | `f400d411…b8104630` |
| `NIHMS76168-supplement-Supplementary_table_5.xlsx` | 50,753 | `aafa75ce…b7c69089` |
| `NIHMS76168-supplement-Supplementary_table_6.xlsx` | 109,425 | `3d001519…15ba6a26` |

**What each sheet is, and which four are read.**

| Sheet | Shape | Loaded |
|---|---|---|
| `S1a. Prestwick_Libery` | 1,200 library entries: catalogue name, STITCH4 id (a PubChem CID on all 1,200), ATC codes, target species, dose, estimated intestinal concentration, physicochemistry | yes — the drug dictionary |
| `S1b. Additional_Chemicals` | 79 catalogue numbers and suppliers for the follow-up compounds | no: a purchasing list |
| `S2. Species selection` | 44 isolates: `NT` code, full lineage, species, strain designation, DSM/ATCC number, Gram stain, medium | yes — the isolate dictionary |
| **`S3a. Adjusted p-values`** | **1,197 drugs x 40 isolates, one adjusted p-value per cell, plus `drug_class` and `n_hit`** | **yes — every edge comes from here** |
| `S3b. Antibacterial_activity` | 40 drugs with a literature check on whether antibacterial activity was already reported, and the lowest MIC found | no: a drug-level annotation, no organism |
| `S4. MICs` | 379 dose-response follow-ups: 25 drugs x 27 isolates with IC25, MIC, both qualifiers, and the authors' TP/TN/FP/FN call against the screen | yes — merged onto the 379 pairs it covers |
| `S5. Enriched SE among ABX` | 69 UMLS side-effect concepts enriched among antibiotics | no: names no organism |
| `S6. Adjusted p-values` | the tolC screen: 1,197 drugs x 4 strains, two of them the *E. coli* K-12 wild type and its ΔtolC deletion | no: `NT5085` is a laboratory deletion mutant, not a taxon, and the other two species are already in `S3a` |

**Every cell of the matrix was measured, and that is the whole point.** 47,880
cells: **5,592 hits, 42,233 measured non-hits, 55 written `NA`**. No other
source in this graph carries a drug negative at all — MASI would have curated
positives only, and gutMDisorder curates what somebody chose to publish. The two
populations load as **two relationships**, `INHIBITS_GROWTH_OF` and
`DOES_NOT_INHIBIT_GROWTH_OF`, never as a flag on one: Part D's D8 states that
rule for this layer and NJC19's `NO_EXCHANGE_WITH` already applies it to the
exchange layer. The 55 `NA` cells become neither and are ledger rows — a pair
the screen did not measure is not a non-hit.

**The hit threshold is derived, because the sheet never states it.** `S3a`
publishes adjusted p-values and an `n_hit` count per drug. **`p < 0.01`
reproduces `n_hit` on all 1,197 rows** (0.05 reproduces 791, 0.001 reproduces
879), and then reproduces three things it was not fitted to: the per-species
human-targeted hit counts in *both* figure source-data workbooks (`MOESM16`
sheet `5a`, 40 of 40 isolates; `MOESM13` sheet `1c`, 25 of 25), the paper's own
abstract (203 of 835 human-targeted drugs hit at least one strain = **24.3%**
against its "24%"), and `S4`'s independent confusion matrix — its 170 `TP`/`FP`
rows all land on a hit edge and its 209 `TN`/`FN` rows all on a non-hit edge,
379 for 379, using a column that had no part in deriving the threshold.
`microbiomekg/preps/prep_maier2018.py` re-derives the first of those on every run and
**refuses to write** if it stops holding, because the constant decides the type
of every edge in the source.

**The drug side joins ChEMBL by three routes and none of them is a guess.**
Tried in order — what the source wrote before anything derived from it: the
exact casefolded `pref_name` (**455** drugs), a level-5 ATC code (**390**), the
name with a salt or hydrate suffix removed (**22**). **867 of 1,197 = 72.4%**;
the other **330** become `Drug` nodes keyed on their Prestwick catalogue number
with `approved = false`. Only the seven-character ATC form is a join key — level
4 names a *class*, and joining `L01BB` would put every nitrogen-mustard analogue
on one node. `drug_join` is on every edge, so the weakest route is countable.

**39 drugs are reached by two routes that disagree, and the ledger says so.**
In every case the name route lands on a ChEMBL *salt* node while the ATC code
lands on its parent — `Estradiol Valerate` reaches CHEMBL1511 by name and
CHEMBL135 (estradiol) by ATC. That is ChEMBL's own documented parent gap showing
through (a salt no mechanism row names keeps its own id, `docs/model.md`
§ChEMBL), not a defect here; the verbatim-first rule decides it and
the `unresolved_maier2018` table on the build result names both candidates, so the count is read
rather than trusted.

**The organism column is the second-cleanest of any source here, and its two
failures are not taxonomy failures.** 38 of the 40 screened isolates resolve
verbatim (24 exact, 12 synonym, 4 promoted — every one at rank `species` after
promotion). The two that do not are `Bacteroides fragilis nontoxigenic` and
`Bacteroides fragilis enterotoxigenic (ET)`: supplementary table 2 writes the
**toxigenicity phenotype inside the species column**, and no `names.dmp` entry
spells either string. They are a closed two-entry override
(`microbiomekg.ontology.maier2018.SPECIES_OVERRIDES`, the same shape as NJC19's
six host cell types) rather than two `UnresolvedTaxon` tombstones asserting NCBI
has lost *Bacteroides fragilis* — which is false, and which would cost 2,394
edges. The strings survive verbatim on the edge as `reported_name`, with the
isolate's own designation in `strain`, so the two isolates stay distinguishable
on one taxon. **40 isolates collapse to 38 taxa** — the two *B. fragilis* rows
and the two *E. coli* rows (IAI1 and ED1a) — and each collapse is two parallel
edges per drug, not one.

**The figure source data in `data/raw/maier2018/` is deliberately not loaded,
and one of its sheets is the reason to say so.** `MOESM13/14/15/16_ESM.xlsx` are
the four figure source-data workbooks from the Springer static host, fetched
separately. `MOESM15` sheet `3c` is a drug x isolate table with a concentration
and a `=`/`<` qualifier and reads exactly like a hit list — but **all 29 of its
drugs have `n_hit = 0` in the screen, and none of its 212 pairs is a hit.**
Loading it as inhibition would have written 212 edges the same paper's own
p-value matrix contradicts. `MOESM13` `1c` and `MOESM16` `5a` are per-species
hit *counts*, aggregates of `S3a`, and are used as cross-checks of the derived
threshold rather than as rows; `MOESM14` `2b` and `MOESM15` `3a`/`3b` are
distribution curves with no entity pair; `MOESM16` `5b` is drug x *E. coli*
gene, and this graph has no gene node type for a chemical-genomics score.

## 16. Zimmermann 2019 — the metabolism screen, and the source that closed D8

- **URL** —
  `https://static-content.springer.com/esm/art%3A10.1038%2Fs41586-019-1291-3/MediaObjects/41586_2019_1291_MOESM1_ESM.xlsx`.
  Paper: Zimmermann et al., *Nature* 570:462-467 (2019),
  doi:10.1038/s41586-019-1291-3, **PMID 31158845**.
- **Licence** — **unstated**, on the same terms as Maier: journal supplementary
  material of a subscription article, no licence line, no terms URL, no document
  property. Every edge carries `source_licence = 'Zimmermann2019-unstated'` —
  a *different* token from Maier's, because two subscription articles are two
  permissions and a reader excluding one has no reason to lose the other.
- **Format** — one XLSX workbook, 39,986,145 bytes, sha256 `91dd7962…4a2fe66d`,
  21 sheets.
- **Status** — **fetched; loaded**, and it is the source that closed D8's
  metabolism leg — W7's *other* direction, the one Maier cannot answer.

**What each sheet is, and which four are read.** The full 21-sheet profile is in
`data/raw/drug_screens/PROVENANCE.md`; the four that matter here:

| Sheet | Shape | Loaded |
|---|---|---|
| **`Supplementary Table 3`** | **271 drugs x 80 measured columns, five sub-columns each (`% consumed`, its STD, `FC`, its STD, ` p(FDR)`), plus each drug's own `Drug adaptive FC threshold %`. 21,680 cells, none blank** | **yes — every edge comes from here** |
| `Supplementary Table 1` | 76 screened organisms with a phylum and a collection number, then the mutant background, cloning strains and plasmids | yes — the strain dictionary |
| `Supplementary Table 2` | 271 drugs x 117 columns: screened name, therapeutic indication, CAS, trade name, SMILES, the **parent drug's** name, and 85 functional-group counts — then a blank row and a block describing its own columns | yes — the drug dictionary |
| `Supplementary Table 13` | 30 bacterial gene products x 20 parent drugs, binary, with RefSeq locus tag, PATRIC id and protein id | yes — as **edge properties**, not a node type |

The other seventeen are mouse pharmacokinetics, fecal-community slopes,
metagenomic sample tables, primers, a purchasing list, a BLAST search and the
metabolite feature matrices. The last of those is the one worth naming:
**`Supplementary Table 6` is 6,573 mass-to-charge features named
`Bisacodyl_183.0685`, with no compound identity of any kind** — no name, no
ChEBI, HMDB, KEGG or PubChem id, no InChIKey — so nothing in it can become a
`Metabolite` node this graph could join to HMDB, MiMeDB or NJC19. It reads like
the obvious second layer and it is not one.

**Four of the eighty measured columns are not organisms.** `Control pH 4`
through `Control pH 7` sit *between* strain columns, carry the same five
sub-columns, and produce **38 apparent hits between them** under the very rule
that calls a real one — they are the abiotic-degradation controls. Nothing
structural separates them, so a reader that walked the column blocks would write
1,084 cells of chemistry as microbial metabolism and would report 80 screened
"strains" against the paper's 76. They are excluded by label and ledgered, and
excluding them is what makes the published 76 reproduce from the sheet.

**The call rule is derived, and the file publishes only half of it.** Column B
gives each drug its own `Drug adaptive FC threshold %` (20 for 124 of the 271,
higher for the rest), so the depletion cutoff is read rather than guessed. The
comparison and the significance cutoff are not, and both matter: **`% consumed
>= the drug's own threshold` with `p(FDR) <= 0.05` reproduces the paper's
headline exactly — 176 of 271 drugs (65%) metabolised by at least one strain.**
`p < 0.05` gives 175 (fourteen cells sit at exactly 0.05), `p <= 0.01` gives
133, and using the 20% floor instead of the per-drug threshold gives 190.
`microbiomekg/preps/prep_zimmermann2019.py` re-derives the 176 on every run and **refuses
to write** when it stops holding. A second check from a sheet with no part in
the derivation: all 20 parent drugs supplementary table 13 names a gene for are
among the 176 — true at 0.01 as well, false at 0.001, so it rules out an
over-strict cutoff without separating 0.05 from 0.01, and it is recorded as the
weaker check it is.

**20,054 edges: `METABOLISES` 2,575, `DOES_NOT_METABOLISE` 17,479**, over 66
taxa and 271 drugs. Every cell of the matrix was measured — 21,680 in, 1,084 on
the control columns, 542 on the two strains that reach no taxon, **0 unmeasured**
— so the negatives are again the larger half and again a *measurement*. They are
their own relationship for the reason `DOES_NOT_INHIBIT_GROWTH_OF` and
`NO_EXCHANGE_WITH` are.

**The drug side joins by three routes and 17 of them land on the other screen's
nodes.** Tried verbatim-first: the screened `MOLENAME` (**195**), the file's own
parent-drug `name` column (**43**), the screened name with a salt suffix removed
(**10**). **248 of 271 = 91.5%**; the other **23** become `Drug` nodes keyed
`ZIMMERMANN2019:<screened name>` with `approved = false`. There is no ATC route
because supplementary table 2 has no ATC column, and no CAS route because the
CAS cell is multi-valued with inline annotations (`34381-68-5, 37517-30-9
[acebutolol]`) and parsing an identifier out of it would be a grammar. Of the
248 that join, **231 reach a ChEMBL node and 17 reach one Maier 2018 minted** —
which is why `prep_zimmermann2019.py` declares `DEPENDS_ON = ["chembl",
"maier2018"]`. Running first would mint a second node for each of those 17 and
split one drug in two along exactly the seam D8 asks across. Three compounds are
reached by two routes that disagree (the screened name lands on a ChEMBL salt
record, the parent name on its parent) and each is a ledger row.

**Two of the 76 strain names stay unresolved on purpose.** 74 reach a taxon (51
exact, 21 synonym, 2 promoted), collapsing to **66 taxa** — seven *B. fragilis*
isolates and three *B. thetaiotaomicron* are one taxon each, and each collapse
is parallel edges told apart by `screen_column` and `strain`. Five names are
corrected by
`microbiomekg.ontology.zimmermann2019.SPECIES_OVERRIDES`, and **every correction
is confirmed by something other than the spelling**: three by the row's own DSM
number (`Pretovella copri`/DSM18205 → *Prevotella copri*; `Bryantia
formataxigens`/DSM14469 → *Bryantella formatexigens*; `Eubacterium
biforme`/DSM3989 → *Holdemanella biformis*, which `names.dmp` still spells at
strain level), one because *Odoribacter splanchnicus* is the only name in all of
`names.dmp` at edit distance 1 from `Odoribacter splanchnius`, and one because
the binomial is a verbatim prefix of `Lactobacillus  reuteri CF48-3A`.
`Bacteroides WH2` and `Bifidobacterium ruminatum` meet neither test — NCBI holds
**two** candidates for each (`Bacteroides sp. WH2` 311784 against *B.
cellulosilyticus* WH2 1268240; *B. ruminantium* 78346 against *B. ruminale*, a
synonym of *B. thermophilum* 33905) and neither row carries a collection number
to choose with — so they are `UnresolvedTaxon` tombstones carrying both
candidate ids, at a cost of 271 measurements each. Guessing would attribute a
whole row to an organism nobody screened, and no count would show it.

**The gene products are loaded and there is still no `Gene` node.**
Supplementary table 13's 30 gene products carry real identifiers and cover 37
(organism, drug) pairs, and they ride on the edge as `gene_locus_tags`,
`gene_products`, `gene_protein_ids` and `n_gene_products`. They were identified
in a gain-of-function library expressed in *E. coli*, not in the 76 screened
strains, and **5 of the 37 pairs disagree with the screen** — a gene metabolised
the drug in *E. coli* while its donor strain did not deplete it in culture.
Those five sit on `DOES_NOT_METABOLISE` edges where they are visible rather than
being dropped or moved. `docs/model.md` records why a node type would not earn
its place and what would change that.

## 17. Reference sets — scored against, never loaded

Files `microbiomekg fetch` can pull that no prep reads: nothing in the graph
comes from them, `status` does not report them, and their only use is a row in
`docs/benchmarks.md`. Each has a fetcher in `download.SOURCES` and no
`FETCHES` entry, the shape `disbiome` established.

- **Duvallet 2017** (`--only duvallet2017`) — Duvallet et al., *Nat Commun*
  8:1784 (2017), CC BY 4.0; supplementary file S3, the genera significant in
  the same direction in at least two diseases. 14,911 bytes from the authors'
  MicrobiomeHD repository into `data/raw/duvallet2017/`; provenance beside it.
  Cut to `tests/fixtures/duvallet2017_genera.tsv` by
  `tests/fixtures/make_duvallet2017_reference.py`; scored in G7.

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
`kegg`, `chembl`, `gutmdisorder`, `mimedb`, `njc19`, `masi`, `drug_screens`,
`mondo`, `pubmed`.

## 11. MONDO (disease id hub) — added by the coordinator, 2026-09-02

- **URL** — `https://github.com/monarch-initiative/mondo/releases/latest/download/mondo.obo`
  (release 2026-09-01; the `mondo.sssom.tsv` asset is not published on this
  release, HTTP 404).
- **Licence** — CC BY 4.0.
- **Format** — OBO. Equivalences are `xref:` lines carrying
  `source="MONDO:equivalentTo"`: 2,400 to EFO (BugSigDB's disease ids) and
  12,091 to DOID (gutMDisorder's), plus MeSH/NCIT/UMLS.
- **Status** — fetched by `microbiomekg fetch --only mondo` (the BugSigDB and
  gutMDisorder fetchers pull it too). `data/raw/mondo/mondo.obo`, 53,134,854
  bytes, sha256 in `data/raw/mondo/PROVENANCE.md`.
- **Declared by** — `prep_bugsigdb`, `prep_gutmdisorder` and `prep_masi`, each
  in its `RAW_INPUTS`; an absent file skips the source with the reason, it no
  longer degrades every disease to its source's own id.
- **Why** — the schema survey (`docs/research/existing-graphs-and-schemas.md`)
  recommends MONDO as the canonical disease key with source ids kept as
  properties; without it, the same condition arrives as an EFO id from one
  source and a DOID from another and never joins.

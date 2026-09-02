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
| 4 | HMDB | **manual** | — | `data/raw/hmdb/` (expected) |
| 5 | CARD | fetched | 72 MB | `data/raw/card/` |
| 6 | Reactome | fetched | 86 MB | `data/raw/reactome/` |
| 7 | KEGG | fetched | 2.4 MB | `data/raw/kegg/` |
| 8 | ChEMBL | fetched (REST subset) | 44 MB | `data/raw/chembl/` |
| 9 | gutMDisorder | **unreachable** | — | — |
| 10 | PubMed / PubChem | not fetched (by design) | — | — |

Total on disk: **1.3 GB** across 61 files. 8 of 10 sources usable; 2 blocked.

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

NCBI Taxonomy (public domain), Reactome (CC0) and BugSigDB (CC BY 4.0) place no
obstacle in the way of redistribution.

---

## 1. NCBI Taxonomy

- **URL** — `https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/new_taxdump/new_taxdump.tar.gz`
  (plus the `.md5` sibling)
- **Licence** — US Government work, public domain. No restriction on use or
  redistribution; citation requested, not required.
- **Format** — gzipped tar of `.dmp` files: pipe-delimited with `\t|\t`
  separators and a trailing `\t|`, no header row.
- **Size** — 160,755,049 B archive; 977 MB extracted (the five files we keep).
- **Status** — **fetched**, md5 verified against the published digest
  (`3838e1c791844a5449f69c560a638215`).

Only the five members the graph needs are unpacked; the rest of the tarball is
left inside it:

| File | Bytes | Rows |
|------|------:|-----:|
| `names.dmp` | 284,230,285 | 4,746,472 |
| `nodes.dmp` | 285,303,865 | 2,993,226 |
| `rankedlineage.dmp` | 397,295,649 | 2,993,226 |
| `merged.dmp` | 1,900,944 | 100,910 |
| `delnodes.dmp` | 7,611,559 | 778,120 |

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

**Operator action:** download `hmdb_metabolites.zip` by hand from
<https://hmdb.ca/downloads> in a normal browser and drop it into
`data/raw/hmdb/`. `fetch.py` will then leave it alone and record it.
`hmdb_proteins.zip` is **not** needed.

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

- **URL** — `http://bio-annotation.cn/gutMDisorder/`
- **Licence** — could not be established; the host is down.
- **Status** — **unreachable**.

DNS resolves (`47.76.215.223`) but the host **refuses the connection** on both
ports, immediately — this is a refusal, not a timeout:

```
ConnectionError: HTTPConnectionPool(host='bio-annotation.cn', port=80):
Max retries exceeded with url: /gutMDisorder/ (Caused by NewConnectionError(
'Failed to establish a new connection: [Errno 61] Connection refused'))
```

Tried `http://` and `https://` with the full browser header set, and
`http://www.bio-annotation.cn/` separately. All refused in under half a second.
As with Disbiome, the failure precedes HTTP, so no request shaping helps.
**The graph is built without gutMDisorder.** Retry the download page later.

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

### Flags

| Flag | Effect |
|------|--------|
| `--chembl-sqlite` | also pull the 5.76 GB ChEMBL SQLite dump |
| `--only SOURCE` | run one source (repeatable) |
| `--force` | re-download even when a complete file is present |

Source names: `ncbi`, `bugsigdb`, `disbiome`, `hmdb`, `card`, `reactome`,
`kegg`, `chembl`, `gutmdisorder`, `pubmed`.

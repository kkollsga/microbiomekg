# MicrobiomeKG performance capture — 2026-09-03 (ten-sources)

Produced by `bench/bench.py`; see `bench/README.md` for what each cell means and how to reproduce it. Every sample of every cell is in the `.json` beside this file.

## Capture metadata

| | |
|---|---|
| captured | 2026-09-03 07:49:17+0200 |
| source set | **ten-sources** |
| machine | Mac16,10, Apple M4, 16.0 GB |
| OS / Python | macOS-26.6.2-arm64-arm-64bit-Mach-O / 3.14.3 |
| kglite | 0.16.21 (`cp310-abi3-macosx_11_0_arm64` — released wheel) |
| repo HEAD | `b36c965 fix: correct two counts the docs got wrong about the metabolism screen` (2 uncommitted paths) |
| load average | 1.88 at start, 5.95 at end (1 min) |
| harness wall time | 9.1 min |
| graph timed | `/Volumes/EksternalHome/coding-cache/microbiomekg-bench/full.kgl` (212.7 MB, written 2026-09-03 07:56:21) |
| graph size | 932,372 nodes, 1,311,540 edges |
| edge sources in that graph | bugsigdb, card, chembl, gutmdisorder, hmdb, maier2018, njc19, reactome, zimmermann2019 |

Taken under whatever load the machine had (protocol item 9); the load average above is that record. Every timing below is from the released PyPI wheel — no debug extension was built for any number here.

> **Machine state.** Taken while a second agent was actively working in this repo — builds and the pytest suite ran alongside the capture, which is why the 1-minute load average moved from 1.88 to 5.95 across the run. The control cells price that: the same four controls read `ctrl_unwind_200k` 10.00 ms, `ctrl_unwind_20k` 871 µs, `ctrl_unwind_case_20k` 1.49 ms and `ctrl_sha256_16mib` 4.94 ms in a quiet-machine run 40 minutes earlier (1-minute load ~1.2), against 11.85 ms / 966 µs / 1.64 ms / 5.46 ms here. All four moved **the same way, by +10% to +18%, including the one that never enters kglite** — so read every timing in sections 5 and 7 as carrying roughly that much machine-load inflation, and compare a later capture through its own controls rather than against these absolutes.
> 
> **Two independent full builds of this source set produced identical graphs** (932,372 nodes / 1,311,540 edges), one before and one after the fix to the build segmentation, which is the cross-check that the numbers below describe a reproducible artifact rather than one run's accident.

## 1. Build — `scripts/build.py` end to end

Wall time **5.4 min** (exit 0), writing 1,379,915 CSV rows across 54 tables and a 212.5 MB `.kgl`.

Sources the build itself reports loading: **bugsigdb, card, gutmdisorder, hmdb, chembl, mimedb, reactome, maier2018, njc19, zimmermann2019**.

Statistic: **single run**. A build is a once-per-event cost that reads 7.5 GB of raw input; it is reported as the one wall time it took, not as a distribution, and the segment times below are that same run carved at the phase markers `scripts/build.py` flushes.

| segment | seconds | share | peak RSS (tree) | peak RSS (build proc) |
|---|---|---|---|---|
| `startup` | 0.0 | 0.0% | 2 MB | 2 MB |
| `prep_bugsigdb.py` | 9.3 | 2.9% | 3,033 MB | 28 MB |
| `prep_card.py` | 7.6 | 2.3% | 2,900 MB | 28 MB |
| `prep_gutmdisorder.py` | 10.0 | 3.1% | 3,113 MB | 28 MB |
| `prep_hmdb.py` | 82.9 | 25.5% | 2,741 MB | 28 MB |
| `prep_chembl.py` | 7.6 | 2.3% | 2,745 MB | 15 MB |
| `prep_kegg.py` | 0.1 | 0.0% | — | — |
| `prep_mimedb.py` | 8.1 | 2.5% | 2,856 MB | 15 MB |
| `prep_reactome.py` | 11.8 | 3.6% | 159 MB | 15 MB |
| `prep_maier2018.py` | 8.1 | 2.5% | 2,834 MB | 15 MB |
| `prep_njc19.py` | 8.0 | 2.5% | 2,739 MB | 15 MB |
| `prep_zimmermann2019.py` | 65.0 | 20.0% | 4,329 MB | 15 MB |
| `prep_taxonomy.py` | 15.3 | 4.7% | 3,451 MB | 16 MB |
| `blueprint` | 0.0 | 0.0% | — | — |
| `ontology` | 0.0 | 0.0% | — | — |
| `from_blueprint` | 2.9 | 0.9% | 1,337 MB | 1,337 MB |
| `bm25_indexes` | 0.3 | 0.1% | 1,399 MB | 1,399 MB |
| `vector_indexes` | 84.0 | 25.8% | 2,423 MB | 2,423 MB |
| `report` | 4.2 | 1.3% | 5,197 MB | 5,197 MB |
| `save` | 0.1 | 0.0% | 0 MB | 0 MB |

Peak RSS: **5,197 MB** for the build process itself (the one that loads the graph and builds the indexes), **5,197 MB** for the whole process tree at its widest moment. Sampled from `ps` every 200 ms — the prep scripts are child processes, and `getrusage(RUSAGE_CHILDREN)` cannot tell them apart from the parent — it is read anyway as the cross-check (5,449 MB from `getrusage(RUSAGE_CHILDREN)`); a large disagreement would mean the sampler missed a spike between two ticks.

`scripts/build.py` prints its `saved …` line **after** `graph.save()` returns, so the save's own time sits inside the `report` segment above it and the `save` row is only the tail between that line and process exit. Section 3 measures `save()` directly and is the number to quote.

### CSV rows written (top 15 tables)

| table | rows |
|---|---|
| `taxon.csv` | 864,110 |
| `taxon_signature.csv` | 114,726 |
| `taxon_disease.csv` | 105,146 |
| `drug_taxon_no_effect.csv` | 42,233 |
| `metabolite_pathway.csv` | 36,130 |
| `pathway_pathway.csv` | 23,717 |
| `pathway.csv` | 23,604 |
| `taxon_drug_not_metabolised.csv` | 17,479 |
| `signature.csv` | 15,820 |
| `signature_bodysite.csv` | 15,376 |
| `resistance_gene_drug_class.csv` | 13,691 |
| `signature_condition.csv` | 12,843 |
| `cited_taxa.csv` | 10,529 |
| `metabolite.csv` | 8,754 |
| `drug_target.csv` | 7,018 |

## 2. Load from blueprint — `from_blueprint` alone

| | |
|---|---|
| `from_blueprint` | **2.74 s** |
| nodes / edges | 932,372 / 1,311,540 |
| peak RSS after the load | 1,432 MB |
| peak RSS of the whole child (load + all indexes + saves) | 4,695 MB |

Statistic: **single run**, in a fresh child process that does nothing else first — this is the load separated from the prep, which is the separation section 1's segment table cannot make (the build process has already read and written 228 MB of CSV by the time it loads).

## 3. Save / load round trip

| variant | `.kgl` | `save()` | 
|---|---|---|
| BM25 lane only | 46.7 MB | 653.95 ms |
| BM25 + vector lane | 212.7 MB | 2.73 s |
| **the vector lane's delta** | **+166.1 MB** | **+2.08 s** |

| load | `.kgl` | first touch after the write | warm repeats | peak RSS |
|---|---|---|---|---|
| BM25 lane only | 46.7 MB | 1.22 s | 1.03 s | 1,215 MB |
| BM25 + vector lane | 212.7 MB | 2.37 s | 2.41 s | 3,708 MB |
| **the vector lane's delta** | **+166.1 MB** | **+1.14 s** | **+1.39 s** | |

Statistic: **mean of fresh processes** for the warm column (a once-per-event cost — one load per process, so no sample is warmed by the one before it except through the page cache), **single run** for the first-touch column and for every `save()`.

**Neither load column is a cold-cache number, and no number here is.** Dropping the macOS unified buffer cache needs `sudo purge`; this harness has no sudo and does not ask for it. What the two columns actually separate is *pages in cache because the save just wrote them* from *pages in cache because an earlier load just read them* — a real difference, but not the cold/warm one. A genuine cold load on this machine is **not measured**, and is not estimated here either.

## 4. Index build — each index alone, with the bytes it adds

| index | lane | build time | documents | terms / dim | `.kgl` after | size it added |
|---|---|---|---|---|---|---|
| `BM25 Taxon.scientific_name` | bm25 | 212.63 ms | 864,110 | 443,098 terms | 44.0 MB | **+11.6 MB** |
| `BM25 Taxon.synonyms` | bm25 | 47.18 ms | 103,181 | 98,659 terms | 46.1 MB | **+2.1 MB** |
| `BM25 Disease.label` | bm25 | 212.2 µs | 808 | 952 terms | 46.1 MB | **-0.0 MB** |
| `BM25 Signature.description` | bm25 | 13.57 ms | 14,425 | 6,383 terms | 46.6 MB | **+0.5 MB** |
| `BM25 Paper.title` | bm25 | 2.34 ms | 2,486 | 4,372 terms | 46.7 MB | **+0.1 MB** |
| `vector Taxon.scientific_name` | vector | 82.58 s | 864,110 | dim 256, ef_search 512 | 212.5 MB | **+165.9 MB** |
| `vector Disease.label` | vector | 39.83 ms | 808 | dim 256, ef_search 512 | 212.7 MB | **+0.2 MB** |

The vector lane's time splits two ways:

| index | embed | HNSW build | vectors indexed |
|---|---|---|---|
| `vector Taxon.scientific_name` | 28.24 s | 54.35 s | 864,110 |
| `vector Disease.label` | 25.03 ms | 14.80 ms | 808 |

Statistic: **single run each**. Every row is one index built once on a graph that already carries the rows above it, then saved to its own file — so the size column is the difference between two real files rather than an estimate. The deltas are therefore **cumulative and order-dependent** (`save()` consolidates the whole graph on the way out); the order is `scripts/build.py`'s. A delta under ~0.1 MB is at the level of save-to-save compression variance and can come out negative — read those rows as "this index costs nothing on disk", not as a saving.

## 5. Query — every `answerable-now` / `partial` Part D acceptance query

Extracted from `docs/usecases-and-pitfalls.md` Part D at run time and run as authored — these are the contract's own queries, not synthetic ones. A section with several statements contributes one cell each, numbered in document order: `D15.1` is the audit call, `D15.2` the per-field census it rolls up.

| cell | rows | statistic | value | min | median | mean | p95 | max | n |
|---|---|---|---|---|---|---|---|---|---|
| `D1` | 25 | min | **20.97 ms** | 20.97 ms | 21.34 ms | 22.42 ms | 28.16 ms | 29.58 ms | 60 |
| `D2` | 40 | min | **89.6 µs** | 89.6 µs | 90.7 µs | 91.2 µs | 93.5 µs | 126.1 µs | 300 |
| `D3` | 25 | min | **192.34 ms** | 192.34 ms | 196.74 ms | 200.84 ms | 213.93 ms | 230.59 ms | 15 |
| `D4.1` | 30 | min | **151.09 ms** | 151.09 ms | 153.54 ms | 158.14 ms | 167.28 ms | 194.09 ms | 15 |
| `D4.2` | 1,380 | min | **1.45 ms** | 1.45 ms | 1.47 ms | 1.50 ms | 1.69 ms | 2.09 ms | 300 |
| `D5.1` | 4 | min | **26.0 µs** | 26.0 µs | 26.4 µs | 26.7 µs | 28.3 µs | 47.6 µs | 300 |
| `D5.2` | 109 | min | **140.2 µs** | 140.2 µs | 142.2 µs | 143.0 µs | 148.2 µs | 156.4 µs | 300 |
| `D6.1` | 20 | min | **221.44 ms** | 221.44 ms | 223.33 ms | 225.12 ms | 229.87 ms | 241.60 ms | 15 |
| `D6.2` | 17 | min | **443.9 µs** | 443.9 µs | 488.9 µs | 518.4 µs | 674.9 µs | 1.45 ms | 300 |
| `D6.3` | 3 | min | **1.26 ms** | 1.26 ms | 1.77 ms | 1.78 ms | 2.29 ms | 2.89 ms | 300 |
| `D7` | 1,535 | min | **3.50 ms** | 3.50 ms | 3.56 ms | 3.67 ms | 4.35 ms | 5.02 ms | 300 |
| `D8.1` | 1,120 | min | **2.55 ms** | 2.55 ms | 2.61 ms | 2.63 ms | 2.73 ms | 3.33 ms | 300 |
| `D8.2` | 1 | min | **88.2 µs** | 88.2 µs | 89.3 µs | 90.0 µs | 94.5 µs | 112.3 µs | 300 |
| `D8.3` | 138 | min | **1.73 ms** | 1.73 ms | 1.80 ms | 1.86 ms | 2.17 ms | 2.57 ms | 300 |
| `D8.4` | 85 | min | **443.3 µs** | 443.3 µs | 457.4 µs | 459.1 µs | 471.8 µs | 543.2 µs | 300 |
| `D8.5` | 2,575 | min | **4.79 ms** | 4.79 ms | 4.99 ms | 5.15 ms | 6.32 ms | 7.13 ms | 300 |
| `D8.6` | 1 | min | **85.70 ms** | 85.70 ms | 87.40 ms | 88.36 ms | 99.78 ms | 106.10 ms | 60 |
| `D8.7` | 32 | min | **441.8 µs** | 441.8 µs | 522.3 µs | 516.5 µs | 560.9 µs | 674.8 µs | 300 |
| `D9.1` | 20 | min | **280.0 µs** | 280.0 µs | 283.1 µs | 285.2 µs | 299.5 µs | 318.5 µs | 300 |
| `D9.2` | 37 | min | **188.0 µs** | 188.0 µs | 189.4 µs | 190.3 µs | 195.4 µs | 201.2 µs | 300 |
| `D10` | 20 | min | **912.4 µs** | 912.4 µs | 965.6 µs | 955.7 µs | 1.00 ms | 1.33 ms | 300 |
| `D11` | 180 | min | **176.3 µs** | 176.3 µs | 177.9 µs | 178.3 µs | 181.1 µs | 186.5 µs | 300 |
| `D12.1` | 3 | min | **129.04 ms** | 129.04 ms | 130.76 ms | 130.72 ms | 131.79 ms | 132.59 ms | 15 |
| `D12.2` | 1 | min | **148.5 µs** | 148.5 µs | 151.4 µs | 152.2 µs | 156.8 µs | 225.6 µs | 300 |
| `D13` | 1,028 | min | **1.44 ms** | 1.44 ms | 1.47 ms | 1.49 ms | 1.53 ms | 3.40 ms | 300 |
| `D14` | 20 | min | **501.18 ms** | 501.18 ms | 514.24 ms | 514.64 ms | 526.78 ms | 534.93 ms | 12 |
| `D15.1` | 104 | min | **437.97 ms** | 437.97 ms | 446.83 ms | 449.04 ms | 455.39 ms | 470.99 ms | 13 |
| `D15.2` | 2 | min | **168.23 ms** | 168.23 ms | 168.89 ms | 168.88 ms | 169.58 ms | 169.66 ms | 15 |
| `D16.1` | 1 | min | **14.2 µs** | 14.2 µs | 14.7 µs | 14.8 µs | 15.0 µs | 16.8 µs | 300 |
| `D16.2` | 3 | min | **64.5 µs** | 64.5 µs | 65.0 µs | 66.2 µs | 68.8 µs | 89.0 µs | 300 |
| `D17` | 50 | min | **366.21 ms** | 366.21 ms | 369.67 ms | 369.64 ms | 371.99 ms | 378.78 ms | 15 |
| `D18.1` | 32 | min | **2.25 ms** | 2.25 ms | 2.40 ms | 2.41 ms | 2.46 ms | 4.13 ms | 300 |
| `D18.2` | 25 | min | **9.39 ms** | 9.39 ms | 10.13 ms | 10.42 ms | 12.72 ms | 16.25 ms | 300 |
| `recon_bm25_synonym` | 5 | min | **126.99 ms** | 126.99 ms | 133.17 ms | 134.41 ms | 142.66 ms | 146.64 ms | 15 |
| `recon_vector_2lane` | 5 | min | **149.83 ms** | 149.83 ms | 159.60 ms | 160.41 ms | 169.77 ms | 180.15 ms | 15 |
| `recon_hybrid_fused` | 5 | min | **159.26 ms** | 159.26 ms | 168.83 ms | 169.06 ms | 179.40 ms | 189.06 ms | 15 |
| `point_taxon_by_id` | 1 | min | **1.8 µs** | 1.8 µs | 1.9 µs | 1.9 µs | 2.0 µs | 2.3 µs | 600 |
| `lineage_walk` | 1 | min | **54.6 µs** | 54.6 µs | 55.0 µs | 55.3 µs | 57.5 µs | 62.0 µs | 300 |

**At the dispatch floor** — these cells are within 3x the 1.0 µs noise floor, so most of what they report is the cost of issuing a query, not of answering it:

- `point_taxon_by_id` — 1.8 µs, 1.8x the floor

## 6. Control cells — the machine-drift meter

Noise floor (`RETURN 1`, dispatch + materialisation with no graph work behind it): **1.0 µs** median, 0.9 µs min. Protocol item 8 requires each control's median at **2x that or more**; the ratio is in the last column.

| control | statistic | value | median | max/median | x floor | ≥2x floor |
|---|---|---|---|---|---|---|
| `ctrl_unwind_200k` | min | **11.85 ms** | 12.28 ms | 1.6x | 12,275x | yes |
| `ctrl_unwind_20k` | min | **966.4 µs** | 990.1 µs | 1.5x | 990x | yes |
| `ctrl_unwind_case_20k` | min | **1.64 ms** | 1.68 ms | 1.1x | 1,676x | yes |
| `ctrl_sha256_16mib` | min | **5.46 ms** | 5.50 ms | 1.0x | 5,502x | yes |

Control contract: **holds**.

## 7. MCP overhead — the same query over stdio vs in-process

Server boot + `initialize` handshake: **4.10 s**, paid once per agent session. It includes loading the `.kgl`, so it is roughly section 3's warm load plus the process start.

| query | over MCP | in-process | overhead | ratio | statistic |
|---|---|---|---|---|---|
| `mcp_floor` | **20.8 µs** | 0.9 µs | 19.9 µs | 22.70x | min / min |
| `D2` | **97.7 µs** | 88.2 µs | below this cell's own spread (±21.2 µs) | 1.11x | min / min |
| `D15.1` | **439.27 ms** | 438.34 ms | below this cell's own spread (±17.11 ms) | 1.00x | min / min |

`mcp_floor` is `RETURN 1` on both sides: its overhead column **is** the agent surface's fixed cost — JSON-RPC encode, a pipe round trip, the server's result rendering — with no graph work behind it. The other two rows are that plus the query. Note the MCP side also *renders* its answer as text and inlines at most 15 rows, so the two sides return different amounts of material for the same engine work; that rendering is part of what the surface costs and is deliberately not subtracted.

# MicrobiomeKG performance capture — 2026-09-04 (source-to-graph-2)

Produced by `bench/bench.py`; see `bench/README.md` for what each cell means and how to reproduce it. Every sample of every cell is in the `.json` beside this file.

## Capture metadata

| | |
|---|---|
| captured | 2026-09-04 10:50:50+0200 |
| source set | **source-to-graph-2** |
| machine | Mac16,10, Apple M4, 16.0 GB |
| OS / Python | macOS-26.6.2-arm64-arm-64bit-Mach-O / 3.14.3 |
| kglite | 0.16.23 (`cp310-abi3-macosx_11_0_arm64` — released wheel) |
| repo HEAD | `2267c5f feat(build): a census beside the saved graph, and the acceptance suite reads it` (5 uncommitted paths) |
| load average | 28.26 at start, 20.30 at end (1 min) |
| harness wall time | 6.2 min |
| graph timed | `/Volumes/EksternalHome/Koding/Python/MicrobiomeKG/graph/microbiomekg.kgl` (49.4 MB, written 2026-09-04 10:28:24) |
| graph size | 934,206 nodes, 1,324,684 edges |
| edge sources in that graph | bugsigdb, card, chembl, gutmdisorder, hmdb, maier2018, masi, njc19, reactome, zimmermann2019 |

Taken under whatever load the machine had (protocol item 9); the load average above is that record. Every timing below is from the released PyPI wheel — no debug extension was built for any number here.

> Source-to-graph cost gate (refactor/source-to-graph): every prep returns frames into one store and the load is from_blueprint(frames=) on kglite 0.16.23; no CSV directory. Build with --with-vectors to compare like-for-like with the 2026-09-03 release-train captures. Load average recorded; the control cells price the machine. Second run, for agreement.

## 1. Build — `scripts/build.py` end to end

Wall time **6.2 min** (exit 0), writing 1,394,681 table rows across 57 tables and a 213.9 MB `.kgl`.

Sources the build itself reports loading: **bugsigdb, card, gutmdisorder, chembl, hmdb, maier2018, zimmermann2019, masi, mimedb, njc19, reactome**.

Statistic: **single run**. A build is a once-per-event cost that reads 7.5 GB of raw input; it is reported as the one wall time it took, not as a distribution, and the segment times below are that same run carved at the phase markers `scripts/build.py` flushes.

| segment | seconds | share | peak RSS (tree) | peak RSS (build proc) |
|---|---|---|---|---|
| `startup` | 0.3 | 0.1% | 68 MB | 68 MB |
| `prep_bugsigdb` | 9.1 | 2.4% | 3,034 MB | 3,034 MB |
| `prep_card` | 7.5 | 2.0% | 3,159 MB | 3,159 MB |
| `prep_gutmdisorder` | 9.4 | 2.5% | 3,280 MB | 3,280 MB |
| `prep_chembl` | 7.4 | 2.0% | 3,392 MB | 3,392 MB |
| `prep_hmdb` | 81.3 | 21.9% | 3,311 MB | 3,311 MB |
| `prep_kegg` | 0.0 | 0.0% | — | — |
| `prep_maier2018` | 8.2 | 2.2% | 3,121 MB | 3,121 MB |
| `prep_zimmermann2019` | 64.5 | 17.4% | 5,800 MB | 5,800 MB |
| `prep_masi` | 11.1 | 3.0% | 4,517 MB | 4,517 MB |
| `prep_mimedb` | 7.6 | 2.0% | 3,672 MB | 3,672 MB |
| `prep_njc19` | 7.4 | 2.0% | 3,598 MB | 3,598 MB |
| `prep_reactome` | 12.0 | 3.2% | 2,645 MB | 2,645 MB |
| `prep_taxonomy` | 16.4 | 4.4% | 4,865 MB | 4,865 MB |
| `blueprint` | 6.9 | 1.8% | 4,976 MB | 4,976 MB |
| `from_blueprint` | 6.3 | 1.7% | 6,641 MB | 6,641 MB |
| `bm25_indexes` | 0.3 | 0.1% | 5,656 MB | 5,656 MB |
| `vector_indexes` | 111.8 | 30.1% | 5,775 MB | 5,775 MB |
| `report` | 3.0 | 0.8% | 4,604 MB | 4,604 MB |
| `save` | 1.0 | 0.3% | 5,351 MB | 5,351 MB |

Peak RSS: **6,641 MB** for the build process itself (the one that loads the graph and builds the indexes), **6,641 MB** for the whole process tree at its widest moment. Sampled from `ps` every 200 ms — the prep scripts are child processes, and `getrusage(RUSAGE_CHILDREN)` cannot tell them apart from the parent — it is read anyway as the cross-check (7,012 MB from `getrusage(RUSAGE_CHILDREN)`); a large disagreement would mean the sampler missed a spike between two ticks.

`scripts/build.py` prints its `saved …` line **after** `graph.save()` returns, so the save's own time sits inside the `report` segment above it and the `save` row is only the tail between that line and process exit. Section 3 measures `save()` directly and is the number to quote.

### CSV rows written (top 15 tables)

| table | rows |
|---|---|
| `taxon` | 864,132 |
| `taxon_signature` | 114,726 |
| `taxon_condition` | 112,966 |
| `drug_taxon_no_effect` | 42,233 |
| `metabolite_pathway` | 36,130 |
| `pathway_pathway` | 23,717 |
| `pathway` | 23,604 |
| `taxon_drug_not_metabolised` | 17,479 |
| `signature_bodysite` | 15,376 |
| `signature` | 14,846 |
| `signature_condition` | 13,959 |
| `resistance_gene_drug_class` | 13,691 |
| `cited_taxa` | 11,071 |
| `metabolite` | 9,056 |
| `taxon_substance_abundance` | 7,579 |

## 6. Control cells — the machine-drift meter

Noise floor (`RETURN 1`, dispatch + materialisation with no graph work behind it): **1.0 µs** median, 1.0 µs min. Protocol item 8 requires each control's median at **2x that or more**; the ratio is in the last column.

| control | statistic | value | median | max/median | x floor | ≥2x floor |
|---|---|---|---|---|---|---|
| `ctrl_unwind_200k` | min | **11.29 ms** | 11.39 ms | 1.0x | 10,946x | yes |
| `ctrl_unwind_20k` | min | **983.7 µs** | 998.0 µs | 1.0x | 959x | yes |
| `ctrl_unwind_case_20k` | min | **1.66 ms** | 1.68 ms | 1.0x | 1,611x | yes |
| `ctrl_sha256_16mib` | min | **5.53 ms** | 5.53 ms | 1.0x | 5,314x | yes |

Control contract: **holds**.

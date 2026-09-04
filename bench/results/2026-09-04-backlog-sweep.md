# MicrobiomeKG performance capture — 2026-09-04 (backlog-sweep)

Produced by `bench/bench.py`; see `bench/README.md` for what each cell means and how to reproduce it. Every sample of every cell is in the `.json` beside this file.

## Capture metadata

| | |
|---|---|
| captured | 2026-09-04 14:08:27+0200 |
| source set | **backlog-sweep** |
| machine | Mac16,10, Apple M4, 16.0 GB |
| OS / Python | macOS-26.6.2-arm64-arm-64bit-Mach-O / 3.14.3 |
| kglite | 0.16.23 (`cp310-abi3-macosx_11_0_arm64` — released wheel) |
| repo HEAD | `0c1432c docs: the CARD model count and the ChEMBL PubMed-URL count, as measured` (0 uncommitted paths) |
| load average | 9.24 at start, 29.12 at end (1 min) |
| harness wall time | 6.4 min |
| graph timed | `/Volumes/EksternalHome/Koding/Python/MicrobiomeKG/graph/microbiomekg.kgl` (49.4 MB, written 2026-09-04 10:28:24) |
| graph size | 934,206 nodes, 1,324,684 edges |
| edge sources in that graph | bugsigdb, card, chembl, gutmdisorder, hmdb, maier2018, masi, njc19, reactome, zimmermann2019 |

Taken under whatever load the machine had (protocol item 9); the load average above is that record. Every timing below is from the released PyPI wheel — no debug extension was built for any number here.

> Backlog-sweep cost gate (fix/backlog-sweep P1-P4): mondo.obo declared and required, MalformedInput replacing SystemExit in the workbook preps, the legacy csv key gone. Nothing touched the embedder or HNSW. --with-vectors for like-for-like with the 2026-09-03/04 captures; load average recorded, control cells price the machine. The vector-lane retake verdict is read only from a capture started under load < 3.0 (dev-docs/plans/backlog-sweep.md P5).

## 1. Build — `scripts/build.py` end to end

Wall time **6.3 min** (exit 0), writing 1,394,681 table rows across 57 tables and a 214.0 MB `.kgl`.

Sources the build itself reports loading: **bugsigdb, card, gutmdisorder, chembl, hmdb, maier2018, zimmermann2019, masi, mimedb, njc19, reactome**.

Statistic: **single run**. A build is a once-per-event cost that reads 7.5 GB of raw input; it is reported as the one wall time it took, not as a distribution, and the segment times below are that same run carved at the phase markers `scripts/build.py` flushes.

| segment | seconds | share | peak RSS (tree) | peak RSS (build proc) |
|---|---|---|---|---|
| `startup` | 0.2 | 0.0% | 10 MB | 10 MB |
| `prep_bugsigdb` | 9.2 | 2.4% | 3,038 MB | 3,038 MB |
| `prep_card` | 7.6 | 2.0% | 3,164 MB | 3,164 MB |
| `prep_gutmdisorder` | 9.5 | 2.5% | 3,279 MB | 3,279 MB |
| `prep_chembl` | 7.5 | 2.0% | 3,374 MB | 3,374 MB |
| `prep_hmdb` | 82.6 | 21.8% | 3,304 MB | 3,304 MB |
| `prep_kegg` | 0.0 | 0.0% | — | — |
| `prep_maier2018` | 8.2 | 2.2% | 3,154 MB | 3,154 MB |
| `prep_zimmermann2019` | 65.9 | 17.4% | 4,721 MB | 4,721 MB |
| `prep_masi` | 9.6 | 2.5% | 3,737 MB | 3,737 MB |
| `prep_mimedb` | 7.9 | 2.1% | 3,775 MB | 3,775 MB |
| `prep_njc19` | 7.3 | 1.9% | 3,711 MB | 3,711 MB |
| `prep_reactome` | 11.9 | 3.1% | 2,581 MB | 2,581 MB |
| `prep_taxonomy` | 16.6 | 4.4% | 4,974 MB | 4,974 MB |
| `blueprint` | 6.7 | 1.8% | 5,047 MB | 5,047 MB |
| `from_blueprint` | 6.4 | 1.7% | 6,227 MB | 6,227 MB |
| `bm25_indexes` | 0.3 | 0.1% | 5,821 MB | 5,821 MB |
| `vector_indexes` | 116.1 | 30.7% | 5,812 MB | 5,812 MB |
| `report` | 3.7 | 1.0% | 2,856 MB | 2,856 MB |
| `save` | 1.2 | 0.3% | 4,274 MB | 4,274 MB |

Peak RSS: **6,227 MB** for the build process itself (the one that loads the graph and builds the indexes), **6,227 MB** for the whole process tree at its widest moment. Sampled from `ps` every 200 ms — the prep scripts are child processes, and `getrusage(RUSAGE_CHILDREN)` cannot tell them apart from the parent — it is read anyway as the cross-check (6,623 MB from `getrusage(RUSAGE_CHILDREN)`); a large disagreement would mean the sampler missed a spike between two ticks.

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

Noise floor (`RETURN 1`, dispatch + materialisation with no graph work behind it): **1.0 µs** median, 0.9 µs min. Protocol item 8 requires each control's median at **2x that or more**; the ratio is in the last column.

| control | statistic | value | median | max/median | x floor | ≥2x floor |
|---|---|---|---|---|---|---|
| `ctrl_unwind_200k` | min | **10.94 ms** | 11.01 ms | 1.1x | 10,573x | yes |
| `ctrl_unwind_20k` | min | **993.5 µs** | 1.00 ms | 1.0x | 963x | yes |
| `ctrl_unwind_case_20k` | min | **1.67 ms** | 1.68 ms | 1.0x | 1,612x | yes |
| `ctrl_sha256_16mib` | min | **5.53 ms** | 5.53 ms | 1.0x | 5,315x | yes |

Control contract: **holds**.

# MicrobiomeKG performance capture — 2026-09-03 (release-train-2)

Produced by `bench/bench.py`; see `bench/README.md` for what each cell means and how to reproduce it. Every sample of every cell is in the `.json` beside this file.

## Capture metadata

| | |
|---|---|
| captured | 2026-09-03 22:04:21+0200 |
| source set | **release-train-2** |
| machine | Mac16,10, Apple M4, 16.0 GB |
| OS / Python | macOS-26.6.2-arm64-arm-64bit-Mach-O / 3.14.3 |
| kglite | 0.16.22 (`cp310-abi3-macosx_11_0_arm64` — released wheel) |
| repo HEAD | `a5fe6d8 docs: queries by task — one Cypher statement per endpoint group, gated twice` (4 uncommitted paths) |
| load average | 20.15 at start, 19.30 at end (1 min) |
| harness wall time | 6.1 min |
| graph timed | `/Volumes/EksternalHome/Koding/Python/MicrobiomeKG/graph/microbiomekg.kgl` (49.3 MB, written 2026-09-03 21:35:09) |
| graph size | 934,206 nodes, 1,324,684 edges |
| edge sources in that graph | bugsigdb, card, chembl, gutmdisorder, hmdb, maier2018, masi, njc19, reactome, zimmermann2019 |

Taken under whatever load the machine had (protocol item 9); the load average above is that record. Every timing below is from the released PyPI wheel — no debug extension was built for any number here.

> Release-train cost gate (feat/release-train, after the package relocation: preps run as -m microbiomekg.preps.<name>, blueprint no longer rewritten by the build). Taken under a heavy unrelated background load (1-minute load average ~11 on 10 cores at start, from processes outside this repo); the control cells price it. Build with --with-vectors to compare like-for-like with the 2026-09-03 ten-sources capture; this graph has eleven sources (MASI added). Second run, for agreement.

## 1. Build — `scripts/build.py` end to end

Wall time **6.0 min** (exit 0), writing 1,395,866 CSV rows across 57 tables and a 215.2 MB `.kgl`.

Sources the build itself reports loading: **bugsigdb, card, gutmdisorder, hmdb, chembl, mimedb, reactome, maier2018, njc19, zimmermann2019, masi**.

Statistic: **single run**. A build is a once-per-event cost that reads 7.5 GB of raw input; it is reported as the one wall time it took, not as a distribution, and the segment times below are that same run carved at the phase markers `scripts/build.py` flushes.

| segment | seconds | share | peak RSS (tree) | peak RSS (build proc) |
|---|---|---|---|---|
| `startup` | 0.1 | 0.0% | 2 MB | 2 MB |
| `prep_bugsigdb.py` | 9.7 | 2.7% | 3,047 MB | 30 MB |
| `prep_card.py` | 7.7 | 2.1% | 2,926 MB | 30 MB |
| `prep_gutmdisorder.py` | 10.4 | 2.9% | 3,116 MB | 30 MB |
| `prep_hmdb.py` | 80.6 | 22.3% | 2,761 MB | 30 MB |
| `prep_chembl.py` | 8.3 | 2.3% | 2,570 MB | 15 MB |
| `prep_kegg.py` | 0.1 | 0.0% | 37 MB | 15 MB |
| `prep_mimedb.py` | 8.3 | 2.3% | 2,903 MB | 15 MB |
| `prep_reactome.py` | 12.3 | 3.4% | 161 MB | 15 MB |
| `prep_maier2018.py` | 8.3 | 2.3% | 2,834 MB | 15 MB |
| `prep_njc19.py` | 8.3 | 2.3% | 2,780 MB | 15 MB |
| `prep_zimmermann2019.py` | 66.2 | 18.3% | 4,549 MB | 15 MB |
| `prep_masi.py` | 10.5 | 2.9% | 3,115 MB | 15 MB |
| `prep_taxonomy.py` | 16.0 | 4.4% | 3,454 MB | 15 MB |
| `blueprint` | 0.0 | 0.0% | — | — |
| `ontology` | 0.0 | 0.0% | — | — |
| `from_blueprint` | 3.3 | 0.9% | 1,554 MB | 1,554 MB |
| `bm25_indexes` | 0.4 | 0.1% | 1,596 MB | 1,596 MB |
| `vector_indexes` | 107.7 | 29.8% | 3,685 MB | 3,685 MB |
| `report` | 2.9 | 0.8% | 4,984 MB | 4,984 MB |
| `save` | 0.1 | 0.0% | 3,902 MB | 3,902 MB |

Peak RSS: **4,984 MB** for the build process itself (the one that loads the graph and builds the indexes), **4,984 MB** for the whole process tree at its widest moment. Sampled from `ps` every 200 ms — the prep scripts are child processes, and `getrusage(RUSAGE_CHILDREN)` cannot tell them apart from the parent — it is read anyway as the cross-check (5,307 MB from `getrusage(RUSAGE_CHILDREN)`); a large disagreement would mean the sampler missed a spike between two ticks.

`scripts/build.py` prints its `saved …` line **after** `graph.save()` returns, so the save's own time sits inside the `report` segment above it and the `save` row is only the tail between that line and process exit. Section 3 measures `save()` directly and is the number to quote.

### CSV rows written (top 15 tables)

| table | rows |
|---|---|
| `taxon.csv` | 864,132 |
| `taxon_signature.csv` | 114,726 |
| `taxon_condition.csv` | 113,015 |
| `drug_taxon_no_effect.csv` | 42,233 |
| `metabolite_pathway.csv` | 36,130 |
| `pathway_pathway.csv` | 23,717 |
| `pathway.csv` | 23,604 |
| `taxon_drug_not_metabolised.csv` | 17,479 |
| `signature.csv` | 15,820 |
| `signature_bodysite.csv` | 15,376 |
| `signature_condition.csv` | 13,959 |
| `resistance_gene_drug_class.csv` | 13,691 |
| `cited_taxa.csv` | 11,071 |
| `metabolite.csv` | 9,056 |
| `taxon_substance_abundance.csv` | 7,579 |

## 6. Control cells — the machine-drift meter

Noise floor (`RETURN 1`, dispatch + materialisation with no graph work behind it): **1.0 µs** median, 1.0 µs min. Protocol item 8 requires each control's median at **2x that or more**; the ratio is in the last column.

| control | statistic | value | median | max/median | x floor | ≥2x floor |
|---|---|---|---|---|---|---|
| `ctrl_unwind_200k` | min | **11.60 ms** | 11.96 ms | 1.1x | 11,492x | yes |
| `ctrl_unwind_20k` | min | **986.1 µs** | 1.00 ms | 1.5x | 962x | yes |
| `ctrl_unwind_case_20k` | min | **1.65 ms** | 1.67 ms | 1.0x | 1,608x | yes |
| `ctrl_sha256_16mib` | min | **5.53 ms** | 5.53 ms | 1.0x | 5,313x | yes |

Control contract: **holds**.

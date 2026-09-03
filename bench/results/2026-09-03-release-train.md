# MicrobiomeKG performance capture — 2026-09-03 (release-train)

Produced by `bench/bench.py`; see `bench/README.md` for what each cell means and how to reproduce it. Every sample of every cell is in the `.json` beside this file.

## Capture metadata

| | |
|---|---|
| captured | 2026-09-03 21:58:13+0200 |
| source set | **release-train** |
| machine | Mac16,10, Apple M4, 16.0 GB |
| OS / Python | macOS-26.6.2-arm64-arm-64bit-Mach-O / 3.14.3 |
| kglite | 0.16.22 (`cp310-abi3-macosx_11_0_arm64` — released wheel) |
| repo HEAD | `a5fe6d8 docs: queries by task — one Cypher statement per endpoint group, gated twice` (2 uncommitted paths) |
| load average | 11.68 at start, 20.15 at end (1 min) |
| harness wall time | 6.1 min |
| graph timed | `/Volumes/EksternalHome/Koding/Python/MicrobiomeKG/graph/microbiomekg.kgl` (49.3 MB, written 2026-09-03 21:35:09) |
| graph size | 934,206 nodes, 1,324,684 edges |
| edge sources in that graph | bugsigdb, card, chembl, gutmdisorder, hmdb, maier2018, masi, njc19, reactome, zimmermann2019 |

Taken under whatever load the machine had (protocol item 9); the load average above is that record. Every timing below is from the released PyPI wheel — no debug extension was built for any number here.

> Release-train cost gate (feat/release-train, after the package relocation: preps run as -m microbiomekg.preps.<name>, blueprint no longer rewritten by the build). Taken under a heavy unrelated background load (1-minute load average ~11 on 10 cores at start, from processes outside this repo); the control cells price it. Build with --with-vectors to compare like-for-like with the 2026-09-03 ten-sources capture; this graph has eleven sources (MASI added).

## 1. Build — `scripts/build.py` end to end

Wall time **6.1 min** (exit 0), writing 1,395,866 CSV rows across 57 tables and a 215.1 MB `.kgl`.

Sources the build itself reports loading: **bugsigdb, card, gutmdisorder, hmdb, chembl, mimedb, reactome, maier2018, njc19, zimmermann2019, masi**.

Statistic: **single run**. A build is a once-per-event cost that reads 7.5 GB of raw input; it is reported as the one wall time it took, not as a distribution, and the segment times below are that same run carved at the phase markers `scripts/build.py` flushes.

| segment | seconds | share | peak RSS (tree) | peak RSS (build proc) |
|---|---|---|---|---|
| `startup` | 0.1 | 0.0% | 6 MB | 6 MB |
| `prep_bugsigdb.py` | 10.6 | 2.9% | 2,850 MB | 30 MB |
| `prep_card.py` | 8.0 | 2.2% | 2,913 MB | 30 MB |
| `prep_gutmdisorder.py` | 10.7 | 2.9% | 3,158 MB | 16 MB |
| `prep_hmdb.py` | 81.4 | 22.3% | 2,779 MB | 16 MB |
| `prep_chembl.py` | 9.4 | 2.6% | 2,619 MB | 15 MB |
| `prep_kegg.py` | 0.1 | 0.0% | — | — |
| `prep_mimedb.py` | 8.3 | 2.3% | 2,909 MB | 15 MB |
| `prep_reactome.py` | 12.5 | 3.4% | 161 MB | 15 MB |
| `prep_maier2018.py` | 8.3 | 2.3% | 2,834 MB | 15 MB |
| `prep_njc19.py` | 8.0 | 2.2% | 2,739 MB | 15 MB |
| `prep_zimmermann2019.py` | 65.5 | 18.0% | 4,240 MB | 15 MB |
| `prep_masi.py` | 10.4 | 2.8% | 3,126 MB | 15 MB |
| `prep_taxonomy.py` | 15.9 | 4.3% | 3,453 MB | 15 MB |
| `blueprint` | 0.0 | 0.0% | — | — |
| `ontology` | 0.0 | 0.0% | — | — |
| `from_blueprint` | 3.1 | 0.9% | 1,576 MB | 1,576 MB |
| `bm25_indexes` | 0.3 | 0.1% | 1,618 MB | 1,618 MB |
| `vector_indexes` | 109.5 | 30.0% | 3,654 MB | 3,654 MB |
| `report` | 2.9 | 0.8% | 4,542 MB | 4,542 MB |
| `save` | 0.2 | 0.1% | 3,704 MB | 3,704 MB |

Peak RSS: **4,542 MB** for the build process itself (the one that loads the graph and builds the indexes), **4,542 MB** for the whole process tree at its widest moment. Sampled from `ps` every 200 ms — the prep scripts are child processes, and `getrusage(RUSAGE_CHILDREN)` cannot tell them apart from the parent — it is read anyway as the cross-check (4,849 MB from `getrusage(RUSAGE_CHILDREN)`); a large disagreement would mean the sampler missed a spike between two ticks.

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
| `ctrl_unwind_200k` | min | **11.63 ms** | 11.94 ms | 1.1x | 11,471x | yes |
| `ctrl_unwind_20k` | min | **990.8 µs** | 997.8 µs | 1.3x | 958x | yes |
| `ctrl_unwind_case_20k` | min | **1.66 ms** | 1.68 ms | 1.1x | 1,613x | yes |
| `ctrl_sha256_16mib` | min | **5.53 ms** | 5.53 ms | 1.0x | 5,313x | yes |

Control contract: **holds**.

# Benchmarks — what the graph reproduces, and against what

Every number on this page is executed against the built graph by
`tests/test_skill_claims.py` (the sidecar is `docs/claims/benchmarks.md`), so a
row that stops being true is a failing test, not a stale table. The comparator
figures are what the other side has published and are marked as such; they are
not re-measured here. Measured `2026-09-03` on the eleven-source default build.

The five rows answer `docs/design/capability-gaps.md` §G's benchmark items
G1–G5: no download, one Cypher statement each, and a stop rule written before
the number was — a benchmark whose only possible outcome is "we win" is not one.

## G1 — Association-layer shape

The comparator publishes the whole shape of its microbe–disease layer, and
that is the fair comparison — not node counts, which say how much taxonomy was
ingested rather than how much was claimed.

| | published by the comparator | this graph |
|---|---:|---:|
| microbe–disease associations | 63,316 | 105,880 reports over **56,306** distinct (taxon, disease) pairs |
| microbes in the layer | 2,981 | **7,754** |
| diseases in the layer | 243 | **813** |

```cypher
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
WITH t, d, count(r) AS reports
RETURN count(*) AS pairs, sum(reports) AS edges,
       count(DISTINCT t) AS taxa, count(DISTINCT d) AS diseases
```

**Reading, with the stop rule applied.** The rule was: if any of ours is not
larger, say so and withdraw the multiple. Microbes and diseases are 2.6× and
3.3× theirs. Distinct pairs are **not** larger — 56,306 against 63,316 — and
whether their figure counts pairs or reports is unpublished, so no multiple is
claimed for it. What this graph has more of is reports per pair: direction is
per study here, never aggregated, so forty reports on one pair stay forty.

The entity counts behind the layer, for the reader who wants the node numbers
anyway: 864,132 `Taxon`, 826 `Disease`, 9,056 `Metabolite`, 6,408 `Drug`,
23,604 `Pathway`, 1,518 `ProteinTarget`, 2,528 `Paper`.

## G2 — Reconciliation confidence

The comparator scores entity mapping on a three-point scale — exact NCBI id
match, fuzzy name match, genus-level-only match — and estimates that "~95%"
of its associations have high-confidence mappings. That is *mapping*
confidence, not evidence strength. This graph keeps the same fact as a
countable ledger on every BugSigDB membership edge, and keeps what would not
resolve as a node instead of dropping it.

| `resolution_status` | edges |
|---|---:|
| exact | 114,161 |
| merged (an old id, followed to the current one) | 413 |
| promoted (a strain, promoted to its species) | 152 |
| deleted (an id NCBI has retired) | 16 |

```cypher
MATCH ()-[r:REPORTED_BY]->()
RETURN r.resolution_status AS status, count(*) AS n ORDER BY n DESC
```

Over 114,742 membership edges, 99.5% resolved to the exact id the source gave,
and `resolution_normalized` is false on every one, because BugSigDB resolves
by id and no name was normalised to get there. The names that would not
resolve are 224 `UnresolvedTaxon` tombstones, each carrying the candidates it
refused to choose between — the population the comparator describes as
"flagged but included" and this graph keeps as nodes.

## G3 — Drug-screen headlines

Two published screens, each with a headline number in its abstract. The graph
recomputes both from the loaded edges, and where it falls short it names the
cost rather than rounding.

| screen | published | this graph | gap |
|---|---:|---:|---|
| Maier 2018: human-targeted drugs inhibiting any gut strain | 24% | **203 of 835 = 24.3%** | none |
| Zimmermann 2019: drugs metabolised by any strain | 176 of 271 | **172 of 271** | 4 drugs, metabolised only by a strain the loader refused to resolve |

```cypher
MATCH (d:Drug)-[r:INHIBITS_GROWTH_OF]->(:Taxon) WHERE r.drug_class = 'human-targeted drugs'
WITH count(DISTINCT d) AS hit
MATCH ()-[r2:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->()
WHERE r2.drug_class = 'human-targeted drugs'
RETURN hit, count(DISTINCT r2.prestwick_id) AS screened
```

The four missing drugs are metabolised only by *Bifidobacterium ruminatum*,
one of 2 strain names NCBI holds two candidates for and whose row offers nothing
to choose with. The loader refuses to guess; the four hits are what the refusal
costs, and the drugs themselves are in the graph with their measured non-hits.

## G4 — BugSigDB loader fidelity

110,547 of the association edges come from one source, so the cheapest
decisive check is that the source was transcribed faithfully. The measure is
exact agreement between what the graph holds and what the dump it was built
from contains.

| | the `2026-09-02` `full_dump` | this graph |
|---|---:|---:|
| signatures | 14,846 | **14,846** |
| studies | 2,126 | **2,126** |

```cypher
MATCH (s:Signature)-[:PART_OF_STUDY]->(st:Study)
RETURN count(DISTINCT s) AS signatures, count(DISTINCT st) AS studies
```

**Stop rule applied:** a disagreement the dump date does not explain would be
filed as a bug and this row would say "disagrees". It agrees exactly.

## G5 — Cross-source direction agreement

Three sources report (taxon, disease) directions: BugSigDB, gutMDisorder and
MASI. Where more than one of them reports the same pair, do they agree? The
baseline is D17's single-source picture: 56,306 pairs, 8,257 carrying both
directions, 47,262 resting on a single study (83.9%).

| multi-source pairs | 871 |
|---|---:|
| every source internally unanimous, and they agree | **335** |
| every source internally unanimous, and they disagree | **120** |
| at least one source disagrees with itself | **416** |

```cypher
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
WITH t, d, r.primary_source AS src, collect(DISTINCT r.direction) AS dirs
WITH t, d, count(src) AS n_src,
     sum(CASE WHEN size(dirs) = 1 THEN 1 ELSE 0 END) AS unanimous,
     collect(DISTINCT dirs[0]) AS firsts
WHERE n_src > 1
RETURN count(*) AS multi,
       sum(CASE WHEN unanimous = n_src AND size(firsts) = 1 THEN 1 ELSE 0 END) AS agree,
       sum(CASE WHEN unanimous = n_src AND size(firsts) > 1 THEN 1 ELSE 0 END) AS disagree,
       sum(CASE WHEN unanimous < n_src THEN 1 ELSE 0 END) AS within
```

Of the 871 pairs seen by more than one source, 424 are BugSigDB × gutMDisorder,
244 are all three, 119 gutMDisorder × MASI and 84 BugSigDB × MASI. This is the
least flattering number the graph can publish about itself and the one no
comparator publishes at all: the query reports the disagreement and nothing
here resolves it.

## G7 — The breadth proxy against a published meta-analysis

D14 asks "is this taxon a generic dysbiosis marker?" and answers it by
*signature breadth* — how many BugSigDB signatures report the taxon — because
the healthy-cohort prevalence that would answer it directly is not in the
graph. Duvallet et al. 2017 answered the same question from 28 case-control
datasets across ten diseases: a genus significant in the same direction in at
least two diseases is part of the "non-specific" response. Their supplementary
file S3 names that set (`tests/fixtures/duvallet2017_genera.tsv`, cut by
`tests/fixtures/make_duvallet2017_reference.py`), and the benchmark asks how
many of D14's top-ranked genera are in it.

| | |
|---|---:|
| genera in Duvallet's non-specific set (24 health, 20 disease, 7 both) | 51 |
| D14's top ten genera by signature breadth, in that set | **9** |
| D14's top twenty, in that set | **14** |

```cypher
MATCH (t:Taxon)-[:REPORTED_BY]->(s:Signature)
WHERE t.placeholder = false AND t.rank = 'genus'
WITH t.title AS genus, count(s) AS n
ORDER BY n DESC LIMIT 10
RETURN sum(CASE WHEN genus IN [<the 51 genera>] THEN 1 ELSE 0 END) AS overlap
```

The ranking is restricted to `rank = 'genus'` because the reference is a genus
list: D14's documented top six interleaves two families (*Lachnospiraceae*,
*Oscillospiraceae*), which are neither hits nor misses here. The one miss in
the top ten is *Clostridium*: the reference uses RDP's cluster names
(`Clostridium_XlVb`, `Clostridium_IV`, …) and has no plain *Clostridium*, so
it is counted as a miss rather than mapped. The stop rule was written before
the number: `overlap@10` of five or more validates the proxy; fewer moves
GMrepo's healthy baselines to the top of the source backlog. Nine validates
it — the breadth of one curation reproduces a cross-study meta-analysis — and
the healthy-prevalence half of D14 stays a separate, still-open item.

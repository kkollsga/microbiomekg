# Evaluation — does the graph serve the user stories?

Written 2026-09-03 against a clean `scripts/build.py` run made for this
evaluation (**932,372 nodes, 1,311,540 edges, 17 node types, 28 relationship
types**, ten sources, `--scope microbial`, KEGG off) and **re-measured the same
day after MASI landed** (**934,206 nodes, 1,324,684 edges, 18 node types, 33
relationship types**, eleven sources). Where a number moved, both are given and
the second is the current one. Every number below came from a query run in one
of those sessions, or from `.venv/bin/python -m pytest -q` (**810 passed in
46 s** at writing; **1,166 passed** after MASI and the agent-surface work).
Nothing is carried over from a report this evaluation did not verify.

The audience for the verdict is a working microbiome bioinformatician. The
person who commissioned it is not one, so the summary is written for them.

---

## Executive summary

**Verdict: the graph does what it says it does, and the criticism it was built
against is answered on its strongest point and unanswered on its weakest. It is
worth having — but it is a *dataset* worth having, and it is currently dressed
as an agent product, which is the part the critic objected to and the part that
is still true.**

Three findings, in order of how much they should change your view:

1. **The evidence model is real, not a claim.** Every one of the twenty Part D
   acceptance queries runs, and every golden reproduces. A taxon–disease pair
   resolves to forty separate reports across twenty-one studies with study
   design, assay, both group sizes and a PMID on each, and the one dissenting
   study is still there. The critic's central objection — *"it doesn't tell you
   whether the link is experimentally demonstrated"* — is answered with a query,
   not with a paragraph. It is also answered **honestly**: 73.1% of association
   edges are observational, 4.2% are human RCTs, and the graph says so rather
   than hiding it behind a confidence score.

2. **The most valuable thing here is not the associations. It is the 61,127
   measured negatives.** Two published drug screens contribute 42,233 "this drug
   was tested against this bacterium and did nothing" and 17,479 "this bacterium
   was given this drug and did not touch it", plus 894 curated refutations of
   metabolite exchange and MASI's 521 curated non-effects — the two screens are
   98% of the population. Every other edge in this graph, and in every graph it is
   modelled on, exists because a result was worth publishing. This is the only
   population in it that escapes that selection, and no comparable resource
   ships it.

3. **The agent surface has a defect that makes it lie about the graph's newest
   capability.** The `metabolites_pathways` skill — injected verbatim into the
   `cypher_query` tool description an agent reads — still describes the graph as
   it stood before NJC19 landed. Its routing line says *"SKIP for cross-feeding
   / consumption (there is no CONSUMES edge in this graph at all)"*. There are
   4,784. It says *Akkermansia muciniphila* has zero metabolites; the graph has
   four for it. It says butyrate has six producers; the graph has 109. An agent
   that reads only the tool descriptions — the exact thing this project built
   the skill pack for — would tell a user that the single query the project
   fetched a whole source to close cannot be answered. All 810 tests pass with
   this in place, because the skill tests check that the *Cypher* runs, never
   that the *prose* is true.

**Nothing in Part D failed to run.** That was the one thing this evaluation was
told to look hardest for, and it is a clean result: 33 query fragments across
the 20 entries, zero errors, zero empty answers where an answer was claimed.

**Where it does not answer the criticism.** The bioinformatician said the thing
solves a problem an experienced bioinformatician does not have, and is built for
agents rather than people. The first half is *partly* wrong now — the negatives,
the confounder columns and the cross-source reconciliation are things an expert
does not get anywhere else in one place — but the second half stands. There is
no human entry point: no browser, no CLI query tool, no export. The only way to
ask this graph a question is to write Python or to be an LLM holding an MCP
connection. That is a choice, and it is the choice the critic named.

**What it would take to change the verdict from "worth having" to "worth
adopting":** fix the stale skill (hours), give it a non-agent front door
(days), and land GMrepo's healthy baselines (the one missing source that turns
half the ranked outputs from suggestive into interpretable).

---

## 1. Did Part D actually run?

Yes. All twenty entries, run verbatim through the Python API against the fresh
build. Where an entry carries several queries, each was run separately.

| # | Status in Part D | Ran? | Rows | Golden reproduced? |
|---|---|---|---:|---|
| D1 signature overlap | answerable-now | yes | 25 | yes — `overlap ≤ signature_size` on every row |
| D2 taxon × disease evidence | answerable-now | yes | 40 | **exact**: 40 edges / 21 studies / 39 increased / 1 decreased |
| D3 cross-disease breadth | answerable-now | yes | 25 | **exact**: 3,821 of 7,753 taxa (49.3%) |
| D4a stronger tiers | answerable-now | yes | 30 | **exact**: in-vivo 17,858 · meta 4,297 · RCT 4,247 · in-vitro 1,613 |
| D4b intervention leg | answerable-now | yes | 1,380 | **exact**: 1,380 edges / 220 interventions / 395 taxa |
| D5a *A. muciniphila* products | partial | yes | 4 | **exact** (the entry's own correction (a) holds) |
| D5b butyrate producers | partial | yes | 109 | **exact** |
| D6a MES ranking | answerable-now | yes | 20 | **exact**: 96 metabolites carry both halves; acetate 441 P / 72 C |
| D6b degradation | answerable-now | yes | 17 | 387 edges over 17 macromolecules |
| D6c refutations | answerable-now | yes | 3 | **exact**: import- 720 / export- 87 / degrade- 87 |
| D7 AMR carriage (*E. coli*) | answerable-now | yes | 1,535 | **exact**: 646 determinants, 31 classes, 7 mechanisms |
| D8 leg 1 (ChEMBL) | answerable-now | yes | 138 | 95 drugs → 28 bacterial taxa |
| D8 leg 2 (intervention→drug) | answerable-now | yes | 85 | **exact**: 85 edges / 15 drugs / 57 taxa |
| D8 leg 3 (growth screen) | answerable-now | yes | 1,120¹ | **exact**: 5,592 hits + 42,233 non-hits; 203/835 = 24.3% |
| D8 leg 4 (metabolism screen) | answerable-now | yes | 2,575 | **exact**: 2,575 hits + 17,479 non-hits; 172 of 271 drugs |
| D8 metformin three-outcome | answerable-now | yes | 1 | **exact**: 0 inhibited, 38 tested-no-effect |
| D8 sulfasalazine four-outcome | answerable-now | yes | 1 | **exact**: 52 metabolised_by, 14 tested_untouched |
| D8 gene layer | answerable-now | yes | 32 | **exact**: 32 `METABOLISES` edges carry locus tags |
| D9a/D9b 16S share | answerable-now | yes | 20 / 37 | **exact**: 58,595 of 105,097 = 55.8% (55.3% of 105,880 after MASI, whose 783 associations record no sequencing type) |
| D10 probiotic candidates | partial | yes | 20 | **exact**: 26 candidates, 4 with AMR, 18 with a metabolite |
| D11 confounder columns | answerable-now | yes | 180 | **exact**: 14,846 sigs / 2,304 / 1,958 / 6,485; T2D 180 / 58 / 42 |
| D12a/D12b nomenclature | partial | yes | 3 / 1 | **exact**: 1598 at rank filter, score 14.16; 69 edges, all `exact` |
| D13 pathway walk | partial | yes | 1,028 | **stale prose, see below** |
| D14 dysbiosis breadth | partial | yes | 20 | **exact**: Bacteroides 1,150 · Streptococcus 1,123 · Prevotella 1,063 · Lachnospiraceae 1,024 · Lactobacillus 938 · Oscillospiraceae 875 |
| D15a audit | answerable-now | yes | 111 | **exact**: `ASSOCIATED_WITH` 15,985 / 105,097 = 15.2%, warn — 16,768 / 105,880 = 15.8% after MASI, then 17,546 / 112,966 = 15.5% once the union range made it one rule over all three condition types |
| D15b per-field / per-source census | answerable-now | yes | 14 / 2 | **exact**: `{by: 'property'}` names `group_0_size` 14,837 and `group_1_size` 14,732 as the gap, six fields complete; per source, bugsigdb 103,461 · gutmdisorder 1,636, all 1,636 missing group sizes |
| D16a/D16b shortest path | answerable-now | yes | 1 / 3 | **exact**: 1 hop direct, 3-hop evidence walk returns the signatures |
| D17 disagreement | answerable-now | yes | 50 | **exact**: 8,238 conflicts, 47,232 single-cohort of 56,124 pairs (84.2%) |
| D18a/D18b metformin | partial | yes | 32 / 25 | **exact**: 32 rows, `['no-effect']` on every one |
| D19, D20 | descoped | n/a | — | correctly absent |

¹ the `drug_class = 'human-targeted drugs'` slice of 5,592; the entry states no
golden for the filtered form.

### Two Part D goldens the graph contradicts

Neither is a broken query. Both are prose that the tests already know is wrong,
which is the worst place for a stale number to live — a reader trusts the
document and the suite stays green.

- **D8, digoxin.** Part D says *"21 other taxa **do** metabolise digoxin here"*.
  Measured: **15 taxa across 21 screened isolates**. The test
  (`test_d8_a_measured_negative_is_bounded_by_its_assay_and_digoxin_proves_it`)
  asserts the pair `(15, 21)` and its own docstring says "fifteen". The
  document reports the isolate count as a taxon count — which is precisely the
  error the same page warns about two paragraphs earlier
  (*"`count(DISTINCT r.screen_column)` is the strain count; `count(r)` is
  not"*).
- **D13, the pathway walk.** Part D quotes *"4,806 rows over 95 organisms and
  635 pathways … *E. coli* alone reaches 387 rows"*. Those are the **HMDB-only**
  figures. The whole walk is **130,214 rows over 628 taxa and 1,125 pathways**,
  and *E. coli* reaches **1,028**. `METABOLITE_GOLDEN` carries both sets
  correctly; the prose kept the old one when NJC19 grew the `PRODUCES` table
  27×.

Both are reported to the coordinator rather than fixed here.

---

## 2. Testing the criticism directly

### 2.1 "It doesn't tell you whether the link is experimentally demonstrated"

**What the graph does.** Every association edge carries a fourteen-property
contract, of which `evidence_level` is derived from the source's own design,
sequencing and host columns and is never defaulted. Asked for one pair, it
returns the reports grouped by how they were measured:

```cypher
MATCH (t:Taxon {id:851})-[r:ASSOCIATED_WITH]->(d:Disease {id:'MONDO:0005575'})
RETURN r.evidence_level AS level, r.study_design AS design, count(r) AS reports,
       count(DISTINCT r.study_id) AS studies,
       min(r.group_0_size) AS min_n0, max(r.group_1_size) AS max_n1,
       collect(DISTINCT r.direction) AS directions
ORDER BY reports DESC
```

| level | design | reports | studies | min n0 | max n1 | directions |
|---|---|---:|---:|---:|---:|---|
| observational-shotgun | case-control | 17 | 7 | 24 | 111 | increased, decreased |
| observational-shotgun | cross-sectional, not case-control | 6 | 2 | 54 | 691 | increased |
| observational-16S | case-control | 6 | 5 | 45 | 153 | increased |
| observational-16S | cross-sectional, not case-control | 4 | 3 | 64 | 558 | increased |
| meta-analysis | case-control,meta-analysis | 3 | 2 | 308 | 354 | increased |
| meta-analysis | meta-analysis | 2 | 1 | — | — | increased |
| meta-analysis | meta-analysis,case-control | 2 | 1 | 392 | 386 | increased |

That is *Fusobacterium nucleatum* × colorectal cancer, and it is the A1
acceptance sentence satisfied literally: supporting studies grouped by evidence
level, with design and sample sizes. The dissenting study
(`bsdb:41270896/1/2`, `decreased`) survives as its own row.

**Does it answer the objection? Yes.** Not "documents it" — answers it. The
critic asked for a field that separates demonstrated from asserted, and the
field exists, is populated on 100% of edges, is drawn from source columns rather
than a curator's guess, and is filterable in one `WHERE`.

**The counts, which are the honest part of the answer.** Over the three
association relationships (112,183 edges):

| evidence class | edges | share |
|---|---:|---:|
| observational (all five assay classes) | 81,955 | 73.1% |
| in-vivo-model (animal) | 19,285 | 17.2% |
| interventional-rct (human) | 4,743 | 4.2% |
| meta-analysis | 4,478 | 4.0% |
| in-vitro | 1,705 | 1.5% |
| unknown | 17 | 0.02% |

Within `ASSOCIATED_WITH`'s disease edges alone, `observational-16S` is
**58,595 of 105,880 = 55.3%** — a genus-resolution assay carrying the majority
of the graph's disease claims, and the graph says so on every edge rather than
in a footnote.

Across **all 272,897 evidence-bearing edges** (adding the exchange, screen,
AMR, mechanism, pathway and MASI layers) the picture inverts, because the
screens are enormous and every screen cell is a laboratory measurement:

| evidence_level | edges | share |
|---|---:|---:|
| in-vitro | 116,936 | 42.8% |
| observational-16S | 61,793 | 22.6% |
| computational-predicted | 31,948 | 11.7% |
| in-vivo-model | 21,042 | 7.7% |
| observational-shotgun | 18,126 | 6.6% |
| unknown | 9,178 | 3.4% |
| interventional-rct | 7,360 | 2.7% |
| meta-analysis | 4,478 | 1.6% |
| observational-amplicon / -unspecified / -targeted | 2,036 | 0.7% |

Both tables are true and they answer different questions, which is why the
graph stores the level per edge instead of a headline. `computational-predicted`
is almost entirely Reactome's `IEA` orthology projection (31,773 of 31,948) and
one `WHERE` removes it.

**Single-cohort support, the number that should govern how anyone reads the
rest (D17):**

```cypher
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
WITH t, d, collect(DISTINCT r.direction) AS dirs, count(DISTINCT r.study_id) AS ns
RETURN count(*) AS pairs,
       sum(CASE WHEN size(dirs)>1 THEN 1 ELSE 0 END) AS conflict,
       sum(CASE WHEN ns=1 THEN 1 ELSE 0 END) AS single_cohort
```

→ **56,124 pairs · 8,238 carry both directions (14.7%) · 47,232 rest on one
study (84.2%)**. Five sixths of this graph's taxon–disease claims have been seen
once. That is a property of the literature, not of the loader, and the graph
reports it instead of averaging it away.

**What the audit reports per relationship, and why one headline number is not
comparable.** `CALL ontology_audit()` returns 111 rules; the twenty-two
`required_properties` rows are the completeness check:

| relationship | severity | violations | total | pct |
|---|---|---:|---:|---:|
| `ABUNDANCE_CHANGED_BY` | warn | 1,380 | 1,380 | 100.0% |
| `CONFERS_RESISTANCE_TO` | warn | 8,052 | 13,691 | 58.8% |
| `CARRIES_RESISTANCE_GENE` | warn | 3,717 | 6,415 | 57.9% |
| `VIA_MECHANISM` | warn | 3,717 | 6,513 | 57.1% |
| `ASSOCIATED_WITH` | warn | 17,546 | 112,966 | 15.5% |
| `PRODUCES` / `CONSUMES` / `DEGRADES` / `NO_EXCHANGE_WITH` | warn | 0 | 9,483 | 0.0% |
| `IN_PATHWAY` | warn | 0 | 36,130 | 0.0% |
| `INHIBITS_GROWTH_OF` / `DOES_NOT_INHIBIT_GROWTH_OF` | **error** | 0 | 47,825 | 0.0% |
| `METABOLISES` / `DOES_NOT_METABOLISE` | **error** | 0 | 20,054 | 0.0% |
| MASI's four `*_SUBSTANCE` relationships | **error** | 0 | 11,456 | 0.0% |
| `REPORTED_BY` | **error** | 0 | 114,742 | 0.0% |
| `HAS_MECHANISM` / `OF_ORGANISM` / `IS_DRUG` | **error** | 0 | 8,492 | 0.0% |

**These percentages must not be read as a quality ranking, and the three
CARD rows are the proof.** Their ~58% is one field: 3,717 of 6,415 carriage
edges have no `publications` and no `pmid`, because CARD's `PMID.tsv` cites
2,734 of its 6,451 models and the rest of the file is not a citation index.
`ABUNDANCE_CHANGED_BY`'s 100% is three columns gutMDisorder never had — it
records no `study_design` at all and its association rows carry no link to a
sample arm, so no per-association group sizes exist. `ASSOCIATED_WITH`'s 15.5%
is a source that *has* those columns leaving 11.7% of its sample sizes blank —
and that row covers all three condition types since the union range made it one
relationship, where it used to be the disease third of the relation quoted as
though it were the whole of it (16,768 / 105,880 = 15.8%, beside two rules at
6.2% and 20.5% that nothing reported).
Each contract is the set of fields *that source could in principle supply*, so
the fractions measure different things by construction. Comparing them requires
the per-field census, which is now the engine's own —
`CALL ontology_audit({by: 'property'})`, printed on every build — rather than a
Cypher aggregation somebody had to know to write. It settles the three CARD
rows in one row each: `pmid` on 8,052 of 13,691 `CONFERS_RESISTANCE_TO` edges,
every other declared property complete. And on `ASSOCIATED_WITH` it says the
15.5% is **`group_0_size` (14,837) and `group_1_size` (14,732)**, with six of
the fourteen fields complete on all 112,966 edges. Read it as a census — an
edge missing both group sizes is in both rows, so the rows sum past the
aggregate. The per-relationship denominators — every one of them non-zero —
are what make the audit non-vacuous.

One deliberate hole, stated by the model and confirmed here:
`evidence_level` is **never null** (a missing design yields the string
`'unknown'`), so no required-property check can see the 800 edges whose level
means nothing. The 15.5% is a floor.

### 2.2 "It's designed to be used by AI agents, not humans"

**What the graph does.** It ships an MCP server with a seven-skill pack that is
injected into the tool descriptions, plus `docs/` for a human reader.

**Does it answer the objection? No — it documents it.** There is no human
entry point at all. `scripts/serve.py` starts an MCP server over stdio;
`scripts/build.py` builds; there is no query CLI, no notebook, no browser view,
no tabular export, no `.tsv` dump of the association table. A bioinformatician
who wants the evidence-annotated taxon–disease table has to either write kglite
Python or run an LLM. The one artefact that is human-shaped —
the `taxon_condition` table on the build result, 112,966 rows with all fourteen contract fields —
is a build intermediate that nothing in the README points at as a product.

This is worth stating plainly because it is the difference between the two
things this repo could be. As a *dataset* — versioned CSVs plus a documented
evidence contract plus the ledgers — it is defensible against the practitioner
criticism the research chapter itself collected (§4.24: "here is a versioned,
filterable, citable dataset" lands; "designed for AI agents" does not). As an
*agent product* it is exactly the thing the quoted thread rejects. Today the
repo is built as the second and would be received better as the first. The
underlying data is the same; only the packaging is at issue.

### 2.3 "They're solving a problem I don't have"

**Partly answered, and the part that is answered is not the part the project
leads with.**

What an experienced bioinformatician genuinely does not have elsewhere:

- **The measured negatives.** 42,233 `DOES_NOT_INHIBIT_GROWTH_OF` + 17,479
  `DOES_NOT_METABOLISE` + 894 `NO_EXCHANGE_WITH` + MASI's 521 curated
  non-effects = **61,127 edges recording that somebody looked and found
  nothing**, each as its own relationship so no query counts a refutation as an
  observation by omission. Asked about metformin, the graph returns `0
  inhibited, 38 tested_no_effect` — before this layer, that question returned
  nothing, and nothing was indistinguishable from "tested and clean". **The two
  screens are 98% of it**, and MASI's contribution is the measurement of why:
  it curates the same literature and 388 of its 404 "this microbe does not
  metabolise this drug" statements are about *Unclassified gut microbiota*,
  which is not an organism.
- **Confounder control as schema.** 2,304 signatures carry `matched_on`, 1,958
  `confounders`, 6,485 an antibiotics-exclusion window. For type 2 diabetes,
  180 signatures, 58 with confounders, 42 matched, 109 with an exclusion
  window. The research survey found no other source in the field that records
  this at all, and 26 differentially abundant T2D ASVs became zero after
  matching on host variables.
- **A reconciliation trail that is auditable rather than assumed.** 114,742
  `REPORTED_BY` edges carry the resolution status: 114,161 `exact`, 413
  `merged`, 152 `promoted`, 16 `deleted`. 124 `UnresolvedTaxon` tombstones keep
  the names nothing resolved — 56 gutMDisorder, 45 HMDB, 13 NJC19, 3 ambiguous
  HMDB names, 2 NJC19 ambiguities, 2 Zimmermann strains the loader refused to
  guess at. Nothing is dropped, and "the graph has no edge for X" is a question
  the ledgers answer.

What an experienced bioinformatician already has, and does not need: the
associations themselves. BugSigDB has an R package (`bugsigdbr`) that exports
GMT files; CARD has RGI; ChEMBL has an API. The graph's contribution over those
is the *join* and the *uniform evidence field*, and whether that is worth a
dependency is a judgement about how many of those sources any one person
actually needs at once.

**The honest reading:** the objection was correct about the announced product
it was aimed at and is now half-wrong about this one. The half that survives is
that nothing here replaces domain expertise or the source databases, which the
project's own A3 contract already concedes.

---

## 3. The MCP surface: what an agent actually gets

Driven over stdio exactly as `tests/test_mcp_acceptance.py` does, against the
fresh build.

**Wiring — all correct.**

- Handshake `instructions` (1,515 chars) arrive and carry the three evidence
  rules with their numbers.
- `tools/list` exposes seven tools. **All seven repo skills are injected into
  `cypher_query`** (`amr`, `drugs`, `evidence_audit`, `metabolites_pathways`,
  `reconciliation`, `signature_enrichment`, `taxon_disease_evidence`), plus
  kglite's own `cypher_query` skill — 60,832 characters of description.
- **Gating works.** kglite's bundled `code_graph_analysis`, `code_graph_views`
  and `read_code_source` skills are all absent, because they are gated on
  `Function`/`Class` node types this graph does not have. That is the check that
  proves the repo's own `applies_when` gates are live rather than decorative.
- **Read-only holds.** `MATCH (t:Taxon {id: 851}) SET t.title = 'x'` is refused
  with a typed error naming the flag that would enable writes.
- `graph_overview()` prepends the sticky field reminder and returns the full
  ontology with per-class descriptions that are genuinely load-bearing (the
  `Pathway` class description says "a pathway is never evidence that a gut taxon
  runs it" — an agent reading only the schema gets the caveat).

**Three realistic agent questions, end to end.**

*"Which bacteria are enriched in colorectal cancer and how good is the
evidence?"* — Works, and the skills change the answer. An agent following
`taxon_disease_evidence` resolves the label first (nine colorectal terms,
`MONDO:0005575` vs `MONDO:0024331` kept distinct, exactly as C14 requires),
then applies the placeholder and study-count guards. The difference is visible:

| naive `count(r)` ranking | guarded ranking (`count(DISTINCT study_id)`, placeholder excluded) |
|---|---|
| Fusobacterium 68 · Parvimonas 53 · Peptostreptococcus 48 · Prevotella 44 · Clostridium 42 | Fusobacterium 42 studies · Parvimonas 29 · Peptostreptococcus 29 · Streptococcus 27 · Porphyromonas 26 |

and the guarded form additionally reports `directions = [increased, decreased]`
on all of the top ten, which the naive one hides. Without the placeholder
filter the same relationship surfaces `Escherichia/Shigella sp.` (303 edges),
`Candidatus Saccharimonadota` (103) and `uncultured bacterium` (71) as if they
were organisms. The skill's guards are load-bearing, not decorative.

*"Does metformin explain the T2D microbiome signature?"* — Works, and gives the
best answer in the graph. `CHEMBL:CHEMBL1431` reaches 32 T2D-associated taxa
through the growth screen with `metformin_growth_effect = ['no-effect']` on
every one; the independent abundance leg returns 24 edges over 21 taxa,
including *Akkermansia muciniphila* increased in a human RCT (PMID 27999002) and
*Akkermansia* increased in a mouse (PMID 23804561) correctly tiered
`in-vivo-model`. An agent asking whether *Intestinibacter* — the confounder
Forslund calls the most consistent — was screened gets **twelve
name matches — seven of them the genus itself — and zero growth measurements on
any of them**, which is the right
answer, delivered as a number rather than an empty result. This is the question
this graph answers better than any single source, and the surface delivers it.

*"What does this graph know about *Akkermansia muciniphila*?"* — Works
through the API, and **the skill pack misdirects the agent**. One query returns
the whole footprint:

| relationship | edges |
|---|---:|
| DOES_NOT_INHIBIT_GROWTH_OF | 1,104 |
| DOES_NOT_METABOLISE | 256 |
| REPORTED_BY | 242 |
| ASSOCIATED_WITH | 219 |
| INHIBITS_GROWTH_OF | 92 |
| METABOLISES | 15 |
| ASSOCIATED_WITH to a Phenotype / ABUNDANCE_CHANGED_BY / ASSOCIATED_WITH to an Exposure | 13 / 12 / 12 |
| PRODUCES | 4 |
| CONSUMES | 3 |
| DEGRADES | 1 |

`PRODUCES` returns sulfate, propionic acid, ethanol and acetic acid, all NJC19,
all `in-vitro`. `CONSUMES` returns N-acetylgalactosamine, N-acetyl-D-glucosamine
and D-glucose — the mucin-degradation story, at species level, with
`genus_level_evidence = false`. Both are exactly what a microbiome person would
want.

**But the agent is told neither exists.** The `metabolites_pathways` skill's
routing description, injected verbatim into the tool an agent reads, says:

> *"Read the coverage section BEFORE answering: this layer is 578 production
> edges … SKIP for cross-feeding / consumption (**there is no CONSUMES edge in
> this graph at all**)"*

and its body says *"**Akkermansia muciniphila* (239935) has zero metabolites
here"*, *"butyrate returns **six** producers"*, and *"**MiMeDB is the source
that closes this** … and it is **not loaded**"*. Measured on this build:
**3,418 `PRODUCES`**, **4,784 `CONSUMES`**, **387 `DEGRADES`**, **894
`NO_EXCHANGE_WITH`**; *A. muciniphila* has four products and three consumptions;
butyrate has **109** producers; MiMeDB **is** loaded and its finding is that it
contributes zero production edges, so an agent following the skill would send a
user to fetch a source already proven not to carry the data.

This is a correctness defect in the product's primary interface, not a doc nit.
It is invisible to the suite because `tests/test_mcp_skills.py` asserts that
every Cypher block *parses, executes and returns at least one row* — all of
which the stale skill's blocks still do — and never that the prose matches the
graph. 810 tests pass with a skill telling agents the graph cannot do the thing
a whole source was fetched to make it do.

One smaller instance of the same class: `overview_prefix` in
`microbiomekg/mcp/microbiomekg_mcp.yaml` says `primary_source` is *"which of the **six**
sources wrote this edge"*. There are ten, and an agent that trusts it will
under-enumerate when reasoning about coverage.

**Would an agent reading only tool descriptions ask the right question?** For
taxon–disease, drugs, AMR, enrichment, reconciliation and the audit — yes,
demonstrably: the guards are specific, numeric, and phrased as consequences
("if it returns one row, the parallel edges collapsed at load … say so rather
than answering"). For metabolites and cross-feeding — no; it would decline a
question the graph answers.

---

## 4. Limits, stated with numbers

### 4.1 What is missing

| Wanted for | Source | Status | Consequence |
|---|---|---|---|
| D5/D13 enzyme + reaction | MiMeDB v2.0 reaction table | not bulk-downloadable; the two published dumps are MySQL tables with **zero** cross-references between them | production claims carry no enzyme and no pathway of their own |
| D8/D18 drug↔taxon aggregate | MASI interaction tables | documented `unrecoverable`, **and that was wrong — see the caveat below** | the two primary screens closed both directions first, and measure where MASI curates |
| D14 healthy baselines | GMrepo / `bugphyzz` | not fetched | "is this taxon just generic dysbiosis?" is answered by signature *breadth* only, a proxy for the r = −0.84 prevalence relationship — **validated 2026-09-04**: nine of D14's top ten genera are in Duvallet 2017's published non-specific set (`docs/benchmarks.md` G7) |
| D12 nomenclature | LPSN | not fetched | NCBI's name is reported as if uncontested; *Lacticaseibacillus rhamnosus* is taxonomically suspended at LPSN and the graph cannot say so |
| D13 gene layer | gutSMASH | not fetched | taxon→pathway is genome-inferred in every available case |
| associations | Disbiome | host does not complete a TCP connection; never archived | one fewer independent curation to cross-check against |

**Caveat on MASI, and it matters — now settled.** `docs/sources.md` §14 and
Part D's D8 both stated the interaction tables were *"not recoverable"*. They
were recoverable: `www.aiddlab.com` has an **expired TLS certificate, not a
dead host**, and all eight files answer HTTP 200 behind it, confirmed
2026-09-03. Every automated fetch had been failing at the TLS handshake, and
the Wayback Machine — which could not handshake either — had archived only the
one file a person had saved by hand, so two symptoms of one cause were read as
two independent confirmations. The operator downloaded the eight files through
a browser rather than have the fetcher disable certificate verification, and
`docs/sources.md` §14 now carries the retraction and the file list. The
"unrecoverable" verdict in the committed documents was wrong and has been
corrected.

### 4.2 What is thin

| Layer | Size | Against |
|---|---:|---|
| `PRODUCES` | **3,418** edges, 830 organisms, 226 metabolites | the announcement's 231,556 production links — **68×** smaller |
| — of which HMDB | 578 edges / 272 organisms / 154 metabolites, from **224** microbial-origin records (0.10% of HMDB's 217,920) | — |
| — of which NJC19 | 2,840 edges / 638 organisms / 99 metabolites | one 2020 curation, CC0 |
| `CONSUMES` | 4,784 over 714 taxa, 205 metabolites | 96 metabolites carry both a producer and a consumer, so MES is non-zero on 96 rows and zero on the rest |
| Growth screen | **38 taxa** (40 isolates) | a gut community of hundreds of species |
| Metabolism screen | **66 taxa** (76 strains) | same |
| CARD carriage | 6,415 edges, **539 taxa** | 6,451 models, 2,734 with a PMID |
| Papers | **2,486** | the announcement's 10,000 |
| Taxa carrying any claim | **8,717** of 864,110 `Taxon` nodes (1.0%) | the other 99% is lineage scaffolding, required to keep `HAS_PARENT` walkable |

The replication picture in the production layer is honest and small: max
records per (taxon, metabolite) pair is **3**, on **43** pairs — and both causes
are correct behaviour (HMDB and NJC19 independently curating the same
production, and several NJC19 species strings promoting onto one NCBI node),
not double-counting.

### 4.3 Licence encumbrance

| licence | evidence-bearing edges | can it be redistributed? |
|---|---:|---|
| CC-BY-4.0 (BugSigDB, CARD ontology) | 110,589 | yes, with attribution |
| Maier2018-unstated | 47,825 | **no separate data licence exists** |
| CC0-1.0 (NJC19, Reactome) | 45,035 | yes, unconditionally |
| CARD-noncommercial | 26,577 | academic/non-profit only, "as is and unmodified" |
| Zimmermann2019-unstated | 20,054 | **no separate data licence exists** |
| CC-BY-SA-3.0 (ChEMBL) | 6,984 | yes, but **copyleft — forces share-alike on any derived graph** |
| unknown (gutMDisorder) | 3,016 | unstated by the site |
| HMDB-noncommercial | 578 | non-commercial only, no redistribution grant |

- **KEGG** is behind `--with-kegg` and contributes **zero** edges to a default
  build, verified: no `KEGG:` pathway node exists in this graph.
- **CARD's answer lives in the encumbered half.** Only **42 of 13,691**
  `CONFERS_RESISTANCE_TO` edges are `CC-BY-4.0` — `aro.obo` names every term but
  states only 37 models' drug classes. A redistributable AMR cut is 0.3% of the
  layer.
- **The two screens carry an invented-nothing licence token.** `*-unstated`
  rather than a guessed permissive string, one token per article so a reader
  excluding one keeps the other. That is right, and it means **67,879 edges —
  26% of the evidence-bearing graph — have no stated redistribution
  permission**.
- A fully unrestricted cut exists and is measurable: **68,752 CC0 edges**
  (NJC19 + Reactome).

### 4.4 Where an answer could mislead

Each of these is real, each has a countable filter, and each is on the edge
rather than in a document — but a caller who does not apply it gets a
confidently wrong answer.

1. **`DOES_NOT_METABOLISE` means "not in this assay".** The flagship case
   proves it: *Eggerthella lenta* × digoxin is scored a **non-hit** — 4.011%
   consumed against a 20% threshold, FDR p = 0.552, 12 h, n = 4 — because
   digoxin reduction needs the *cgr* operon under arginine-poor conditions.
   Reading that edge as a refutation of the textbook result would be a wrong
   answer generated from a correct measurement. 15 other taxa do metabolise
   digoxin here.
2. **`DOES_NOT_INHIBIT_GROWTH_OF` means "not at 20 µM in monoculture".** 42,233
   such edges. A drug that shifts a community through pH, cross-feeding or the
   host is invisible to the assay.
3. **CARD's taxid is the reference *sequence's* organism.** 6,415 carriage
   edges, every one `sequence_derived = true`; **132 are keyed on taxid 2
   (Bacteria)**, 264 are above species rank, and 18 point at a plasmid, a
   transposon or a synthetic construct. `taxon_specificity` splits them
   (`species-or-below` 6,133 / `above-species` 264 / `not-an-organism` 18).
   Reading a carriage edge as a resistance phenotype is the error, and even a
   perfect sequence hit does not say the gene is expressed.
4. **Strain collapses to species.** Maier's 40 isolates become 38 taxa,
   Zimmermann's 76 become 66; each collapse is parallel edges. `count(r)` is not
   a strain count — *Bacteroides fragilis* metabolises 116 drugs here because
   seven isolates are one node.
5. **A Reactome pathway hit is about the metabolite, not the taxon.** The
   three-hop walk resolves 130,214 rows, and every pathway belongs to one of
   Reactome's 16 model organisms. The `RETURN` carries the literal string
   `'capability, not production'` for that reason. 87.9% of `IN_PATHWAY` is
   `IEA` orthology projection (31,773 of 36,130) rather than a read paper.
6. **16S is genus resolution.** 55.8% of association edges. A species-level
   claim resting on them has to say so; the graph gives the field, not the
   discipline.
7. **A shortest path is navigation, not evidence.** D16 returns 1 hop where a
   direct edge exists and 2 hops between two taxa through a shared metabolite
   (*A. muciniphila* → D-glucose → *F. nucleatum*) — which is a real path and
   almost certainly a meaningless one, since D-glucose has 299 consumers.
8. **The cross-feeding pairs are not gut-scoped.** Butyrate's producer/consumer
   join returns *Brachyspira hyodysenteriae* → butyrate → *Thermodesulfatator
   indicus*, a swine pathogen feeding a deep-sea thermophile. NJC19 curates
   microbial physiology, not a gut community; nothing in the layer restricts it
   to co-resident organisms and no query in Part D adds that filter.

---

## 5. Compared to the announced product

The MicroMap announcement's own figures against this build. "Ours" is measured;
"theirs" is as announced and unverified.

| | announced | this graph | reading |
|---|---:|---:|---|
| taxa | 1,100,000 | 864,110 nodes / **8,717 with any claim** | theirs counts the taxonomy; so does ours. The honest number is 8,717 |
| diseases | 1,464 nodes; **243 in the association layer** | **826** nodes (MONDO 410, EFO 394, MASI 15, DOID 5, ORPHANET 2); **813 in the association layer** | node-to-node ours is smaller, because non-disease terms were refused a `Disease` type rather than absorbed; layer-to-layer — the shape they publish on their homepage — ours is 3.3× larger |
| microbe–disease associations | 63,316 over 2,981 microbes | **105,880** reports over **56,306** distinct (taxon, disease) pairs, 7,754 taxa | fewer distinct pairs, 2.6× the microbes, and more reports per pair: direction is per study here and never aggregated (`docs/model.md` §3). Whether 63,316 counts pairs or reports is not published |
| metabolites | 6,534 | **9,056** (HMDB 7,773 · MiMeDB 1,237 · NJC19 46) | larger — but only 226 have a producer edge (§3) |
| pathways | 1,710 | **23,604** | larger, and worth less: 16 model organisms, no gut commensal |
| drugs | 6,220 | **6,408** | comparable |
| production links | 231,556 | **3,418** | **68× smaller, and this is the real gap** |
| AMR links | 276,169 | **26,619** (13,691 + 6,513 + 6,415) | 10× smaller. Theirs is sourced from CARD Prevalence, which is in-silico and "not included in CARD's primary curation"; ours is the curated half, and its own predicted layer is **104 of 13,691 edges**, removable with one `WHERE` |
| papers | 10,000 | **2,486** | smaller |

**Where we are smaller and why.** Production links is the one that should
sting: 3,418 against 231,556 is not a rounding difference, and the reason is
that no downloadable source carries per-taxon production at that scale. MiMeDB
would have, and its published dumps do not contain the join. A 231,556-edge
production layer is almost certainly BLAST-propagated or reaction-inferred, and
the honest comparison is not 3,418 vs 231,556 but *3,418 measured* vs *231,556
of unknown provenance* — which is a claim this evaluation cannot check, and
which is exactly the asymmetry the whole evidence model exists to expose. The
AMR gap is the same shape and is checkable: 276,169 is Prevalence's size, and
CARD says in its own documentation that Prevalence is in-silico.

**Where the shape is better, with the query that proves it.** The announcement
lists five query types. All five run here; one of them returns something the
announced schema structurally cannot.

- **A5.1 associations with provenance** → D2, above. Forty rows, not one.
- **A5.2 metabolites of a taxon and taxa of a metabolite** → D5. Thin: 3,418
  edges.
- **A5.3 shortest path** → D16. Works; the graph says in its own tool
  description that it is a navigation aid.
- **A5.4 biomarkers and probiotic candidates** → D1 + D10. 26 IBD candidates at
  `n_studies ≥ 2` (from 118 depleted taxa — the replication clause drops 92),
  4 carrying an AMR determinant, 18 with a metabolite.
- **A5.5 cross-feeding** → D6, and this is where the comparison is about
  measured volume and provenance, not existence:

  ```cypher
  MATCH (m:Metabolite)
  OPTIONAL MATCH (p:Taxon)-[:PRODUCES]->(m) WHERE p.placeholder = false
  OPTIONAL MATCH (c:Taxon)-[:CONSUMES]->(m) WHERE c.placeholder = false
  WITH m, count(DISTINCT p) AS P, count(DISTINCT c) AS C
  RETURN m.title, P, C, 2.0*P*C/(P+C) AS mes ORDER BY mes DESC
  ```

  | metabolite | producers | consumers | MES |
  |---|---:|---:|---:|
  | CO2 | 303 | 104 | 154.9 |
  | Acetic acid | 441 | 72 | 123.8 |
  | Hydrogen | 176 | 95 | 123.4 |
  | L-Lactic acid | 281 | 69 | 110.8 |
  | formate | 145 | 61 | 85.9 |
  | Butyric acid | 109 | 26 | 42.0 |

  MES is **identically zero without consumption edges**. Their published schema
  has `UTILIZES` and `PROCESSES` and their API documents a cross-feeding
  endpoint (`docs/design/capability-gaps.md` §F), so the relationship exists
  on both sides and this table is not a binary win. What it shows and theirs
  cannot be checked for is *measured* consumption: 4,784 `CONSUMES` edges,
  each carrying `primary_source` and `source_record_id`, against a
  consumption layer whose size and provenance are unpublished. Without a key
  the comparison stops there.

The structural win is **`Signature` as a node**. D1's overlap query is
answerable because the taxon *set* survives; a flattened
`(Taxon)-[:ASSOCIATED_WITH]->(Disease)` model destroys it and makes enrichment
impossible. Measured: 14,846 signature nodes, 114,742 membership edges, and
`overlap ≤ signature_size` holds on every returned row.

---

<!-- PERFORMANCE TABLE: spliced by coordinator -->

---

## 6. Verdict

### Per workflow

| | workflow | verdict | why |
|---|---|---|---|
| **W1** | Enrichment of a differential-abundance result against curated signatures | **yes** | `Signature` is a node with 114,742 membership edges and full assay metadata; D1 runs, `overlap ≤ signature_size` holds, and the statistic legitimately belongs outside the graph. |
| **W2** | Biomarker discovery validated across cohorts | **partial** | the cross-disease specificity leg is exact (3,821 of 7,753 taxa in >1 condition) and the confounder columns are queryable, but the abundance matrices are and should be out of scope, and healthy-baseline prevalence is absent. |
| **W3** | Probiotic / live-biotherapeutic candidate selection | **partial** | three legs of four: replicated depletion, AMR carriage and metabolites work (26 IBD candidates, 4 with a determinant, 18 with a metabolite), and the interventional leg exists at 1,380 edges — but the observational→animal→human-RCT chain the workflow is defined by is not recorded end to end by any source here, so the output is candidates, never conclusions. |
| **W4** | Mechanism hypothesis via metabolite production | **partial** | 3,418 production edges over 830 organisms with a real evidence tier is six times what it was, and it is still two orders of magnitude short of a mechanism catalogue; no enzyme, no gene, and the pathway hit is about the metabolite. |
| **W5** | Cross-feeding network inference | **partial** | the curated class is genuinely answered — 4,784 `CONSUMES`, 96 metabolites with a non-zero MES — but it is one 2020 curation, it is not gut-scoped (butyrate producers pair with deep-sea thermophiles), the computed class is correctly descoped, and **the agent surface currently tells callers the relationship does not exist**. |
| **W6** | AMR gene surveillance in metagenomes | **partial** | the workflow starts from reads and this graph does not take reads; the RGI hit category cannot come from any download. What it does answer — "what does CARD assert about this taxon, by which mechanism, at what call confidence, under which licence" — it answers completely (1,535 rows for *E. coli*), with the reference-sequence caveat on every edge. |
| **W7** | Drug–microbiome interaction lookup | **yes** | both directions closed by the two primary screens, four distinct claim types kept apart, both papers' headline numbers reproduced from the loaded edges (24.3%; 172 of 271), and 59,712 measured negatives that no aggregator carries. |

Two `yes`, five `partial`, no `no`. Every `partial` names the leg that works and
the leg that does not, and each is a measured number rather than a label — which
is itself the most unusual property of this project.

### Is it worth building?

**Yes, with one correction and one reframing.**

The case *for*: the evidence model is not a slogan. It survives the build, the
audit, the save/load round trip and the MCP protocol, and 810 tests hold it
there. Three things in it exist nowhere else in one place — 61,127 measured
negatives, confounder control as a queryable field, and a reconciliation trail
where every unresolved name is a tombstone rather than a silent drop. The
project's discipline about *not* inventing data is the strongest signal in it:
MASI's 62.5% overlap with the two screens is measured on every edge rather
than absorbed into them; MiMeDB
contributes zero production edges and that is recorded as a finding; HMDB's
disease layer is refused because 72% of it carries one name; two Zimmermann
strain names are left unresolved rather than guessed, at a priced cost of four
drugs. A resource that reports what it could not do is worth more than one that
reports a bigger number.

The case *against*, stated as strongly as it deserves:

- **The core association layer is one source.** 110,547 of 112,966
  taxon–condition edges are BugSigDB, which has an R package, a GMT exporter and
  its own enrichment tool. For W1 and W2 — the two workflows the graph is best
  at — a bioinformatician can already do the job with `bugsigdbr` and no graph
  at all. The graph's value over that is the join to CARD, the screens and
  NJC19, and that join is used by exactly one query family (D10's candidate
  chain, D18's confounder check).
- **84.2% of pairs rest on one study, and 14.7% disagree with themselves.** The
  graph handles this correctly by refusing to resolve it — but a resource whose
  honest reading is "five sixths of this has been seen once" is a hypothesis
  index, not a reference, and it should be described as one.
- **The packaging fights the audience.** The critic's "designed for AI agents,
  not humans" is unrebutted and the research chapter this project commissioned
  collected direct evidence that the target audience rejects that framing. The
  data would land better as a versioned, citable dataset with an MCP server
  beside it than as an MCP server with a build script.
- **And the interface has a live defect.** A skill in the shipped pack tells
  agents the graph cannot answer cross-feeding, which is the one query the
  project fetched a source specifically to close. That it passed 810 tests is
  the finding: the gates check that skills *execute*, never that they are
  *true*, which is the same class of error as an audit rule with a zero
  denominator.

None of that makes it not worth building. It makes the honest description
narrower than the ambition: **a rigorously provenanced, ten-source join over
BugSigDB, with two published screens and a curated exchange layer attached, and
a measurement of its own incompleteness that no comparable resource ships.**
That is a real thing, and it is smaller than "a microbiome knowledge graph".

---

## 7. What we would build next, in order

1. **Fix `microbiomekg/mcp/microbiomekg.skills/metabolites_pathways.md`, and add the gate
   that would have caught it.** The skill actively misinforms an agent about
   4,784 `CONSUMES` edges, 3,418 `PRODUCES` edges and the 109-producer butyrate
   answer. First because it is hours of work on the product's primary interface;
   and the gate matters more than the fix — a test that reads the numeric claims
   out of each skill body and asserts them against the built graph turns this
   whole class of drift red instead of green. `overview_prefix`'s "six sources"
   is the same bug and the same fix.
2. **Ship a human front door.** A `scripts/query.py` that takes a taxon or a
   disease and prints the evidence table, plus a documented, licence-tagged CSV
   export of the association layer. This is the difference between the artefact
   the critic rejected and the artefact the same thread said it wanted, and it
   costs days. It also converts the licence work already done — per-edge
   `source_licence` on 272,897 edges — from an invariant into a feature: the
   CC0 cut is one `WHERE` and 68,752 edges.
3. **GMrepo (or `bugphyzz`) for healthy-cohort prevalence.** It is the one
   missing source that changes an *answer* rather than adding a layer: D14's
   "generic dysbiosis or disease-specific?" is currently signature breadth, a
   proxy, and the published relationship it approximates (r = −0.84 between a
   genus's healthy prevalence and how often it is reported increased) is what
   makes the ranked outputs of W1, W2 and W3 interpretable rather than
   suggestive. **2026-09-04:** the breadth proxy was scored against Duvallet
   2017's meta-analysis and reproduced it (nine of the top ten,
   `docs/benchmarks.md` G7), so the proxy is validated and GMrepo stays at
   this priority — the prevalence denominator is still the thing it would add.
4. **~~Settle the MASI question and act on it.~~ Settled 2026-09-03.**
   `aiddlab.com` was behind an expired certificate rather than gone, all eight
   files answer 200, and the operator fetched them through a browser rather
   than have the fetcher disable certificate verification. The two committed
   documents that stated "unrecoverable" have been corrected, and
   `docs/sources.md` §14 carries both the retraction and the mechanism of the
   error: a negative reached by two failures with one shared cause is one
   observation, not two. **And it is loaded** — 13,122 edges, 1,350 `Substance`
   nodes, probiotic annotation on 540 taxa — with the result that matters for
   this list: **62.5% of its interaction edges restate a pair Maier 2018 or
   Zimmermann 2019 already measured**, so the aggregator's value was never the
   11,771 pairs. It was the 4,295 edges nothing else here carries, the 278
   substances that are not drugs, and the probiotic column D10 is named for
   (26 IBD candidates → 32; 7 of them now flagged). Every D8 golden is
   unchanged, by design.
5. **Scope the exchange layer, or say it is unscoped.** D6 is the project's
   best structural argument and its top answers pair swine pathogens with
   deep-sea thermophiles, because NJC19 curates microbial physiology and nothing
   restricts the join to co-resident organisms. A `body_site`/habitat filter, or
   an explicit statement on the edge that these are *potential* exchanges
   between organisms that may never meet, is what stops the strongest query in
   the graph producing its most impressive-looking wrong answer.

Deliberately not on this list: LPSN, gutSMASH, and MiMeDB v2.0. Each closes a
named `partial`, none of them changes what a working bioinformatician could do
with this graph next week.

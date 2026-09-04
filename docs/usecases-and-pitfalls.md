# Use cases and pitfalls — the user contract

This file is the contract the graph is tested against. Every use case below
must be answerable by a Cypher query on the built graph, and every pitfall
must have a test that fails when the loader gets it wrong. The ontology and
build scripts are not final until this document has been reviewed and the
tests written from it pass on the final graph.

Structure:

- **Part A — Observed user needs.** What the target user actually said they
  need, quoted from the MicroMap announcement thread (r/genomics, 2026-09).
- **Part B — How researchers use this kind of data.** Findings from the
  research agents (sources in `docs/research/`), turned into concrete queries.
- **Part C — Pitfalls.** Data traps with real examples and the test that
  guards each one.
- **Part D — Acceptance queries.** The final list of Cypher queries with
  expected shapes, run against the final graph.

## Part A — Observed user needs

Source: the MicroMap announcement (a Neo4j-backed microbiome graph of 1.1M
taxa, 1,464 diseases, 6,534 metabolites, 1,710 pathways, 6,220 drugs, 276k
AMR links, 10k papers) and one experienced bioinformatician's reply.

### A1. Evidence type is the thing that matters

> "I'll give you points for actually attempting to maintain the provenance
> of the supposed links rather than just saying that there is one, although
> it doesn't tell you whether the link is experimentally demonstrated as far
> as I can tell, which is the important thing."

Contract:

- Every association edge (taxon–disease, taxon–metabolite, taxon–drug,
  gene–drug) carries an `evidence_level` that distinguishes at least:
  observational abundance difference (16S), observational (shotgun),
  interventional/clinical, in-vivo model, in-vitro/experimental, and
  computational/predicted. The value is derived from the source's own
  fields, never defaulted.
- Every association edge carries its provenance: source database, source
  record id, PMID or DOI, and the direction and effect the source reports.
- An edge with unknown evidence is allowed to exist but must be *countable*:
  `CALL ontology_audit()` reports the fraction of association edges missing
  each evidence field, and queries can exclude them with one WHERE clause.
- Acceptance: for a given taxon–disease pair, a query lists the supporting
  studies grouped by evidence level, with study design and sample sizes.

### A2. Provenance means "which paper, which study, what direction"

From the announcement's own feature list. Contract: a taxon–disease
association resolves to the *study* (design, cohort, body site, sequencing
method, sample sizes per group) and the *paper* (PMID/DOI), and the
direction is stored per study, never aggregated into a single sign.

### A3. Existing tooling already serves the expert

> "They're solving a problem that I (experienced bioinformatician) don't
> have ... it's designed to be used by AI agents, not humans."

Contract: the graph is not a replacement for the source databases or for
domain expertise. Its value is (a) reconciliation across sources with an
auditable trail, and (b) a query surface an agent or a script can use
without re-implementing each source's format. Part B must therefore ground
every use case in something researchers demonstrably do today, not in what
a graph could hypothetically enable.

### A4. Same organism, different name

From the announcement: "the same organism can appear under different names,
different taxonomic ranks, or outdated nomenclature across these sources."
Contract: NCBI tax_id is the canonical key; synonyms, merged ids, renamed
genera (the 2020 Lactobacillus split, Clostridioides, Cutibacterium, ...)
and strain-to-species promotion are resolved through one auditable
reconciliation path, and every unresolved name is recorded, never dropped.
Details and tests in Part C.

### A5. The announced query set

The announcement lists five query types; each becomes an acceptance query
in Part D:

1. Taxon–disease associations with provenance.
2. Metabolites produced by a taxon, and taxa producing a metabolite.
3. Shortest path between any two entities.
4. Biomarker signatures and probiotic candidates for a condition.
5. Cross-feeding networks between taxa.

Use case 5 depends on taxon–metabolite production *and consumption* edges;
HMDB alone does not carry consumption. Part B must say which source does,
or the use case is descoped explicitly.

## Part B — How researchers use this kind of data

Synthesised from `docs/research/researcher-workflows.md` (§2 workflows, §3
evidence grading, §4 criticisms), `docs/research/existing-graphs-and-schemas.md`
§5 (recommendations) and `docs/research/source-formats.md` (what the next
loaders actually consume). Part A said what the *user* asked for; this part says
what the *literature* shows researchers actually do with this data, and — for
each of those seven workflows — whether this graph answers it today.

Where Part A and the research disagree, the research wins and the disagreement
is named. Two such places exist and are marked **[A-override]** below.

**The source state this section is written against.** Loaded now: NCBI Taxonomy
(`new_taxdump` 2026-09-02), BugSigDB (`full_dump` 2026-09-02), MONDO
(2026-09-01, as the disease-id hub), gutMDisorder v1 (2020, recovered from
Wayback), CARD, HMDB 5.0, Reactome, ChEMBL 37, MiMeDB, NJC19 and the two
published drug screens, Maier 2018 and Zimmermann 2019, and **MASI** — eleven
sources over the taxonomy. **KEGG** has a loader and stays off by default on its
licence. `docs/sources.md` is the per-source record.

**The gap-filling sources have now been fetched and profiled, and the outcome is
four for five — the two substitutes arrived first and answered better than the
source they substituted for, which then arrived after all.**
**NJC19** is exactly what it was fetched for and closed W5/D6.
**MiMeDB**'s published bulk downloads carry **no microbe–metabolite association
at all, in v1.0 or in v2.0** — two MySQL tables with zero cross-references
between them (`data/raw/mimedb/v2/PROVENANCE.md`) — so it cannot close W4/D5 and
contributes `Metabolite` nodes only; what moved D5 was NJC19's export half, which
was fetched for D6. v2.0 was fetched on 2026-09-03 specifically to test whether
the newer release published the pairs. It does not: it publishes a *count* of
them. **MASI**'s interaction tables were **written off as unrecoverable and were
not**: `www.aiddlab.com` answers HTTP 200 on all eight download files from
behind an **expired TLS certificate**, which is what every automated fetch was
failing on, and they arrived by hand through a browser on 2026-09-03 rather
than by turning certificate verification off (`docs/sources.md` §14). W7's
drug↔taxon layer had already been closed by the two published screens MASI
aggregates, loaded directly and one per direction: **Maier 2018** (1,197
drugs × 40 gut isolates; 5,592 measured inhibitions, 42,233 measured non-hits)
and **Zimmermann 2019** (271 drugs × 76 strains; 2,575 measured depletions,
17,479 measured non-hits) — **and that order turned out to matter.** MASI is an
aggregator: 66.4% of its 12,512 interaction records cite one of those two
papers, and **7,161 of the 11,456 edges it produces (62.5%) restate a (taxon,
compound) pair one of those screens already *measures*.** Because the primary
sources landed first, the graph could measure that overlap instead of
accumulating it — MASI's substances are their own `Substance` node type, its
four interaction relationships are its own, and
`duplicates_primary_source` names the restatement on every edge. What it adds
that nothing else here has is a **curated literature layer over 542 taxa and
1,350 substances** including 278 that are not drugs at all, plus the probiotic
annotation D10 is named for. Every "no" below now names what actually happened
rather than what was expected.

### W1. Enrichment of a differential-abundance result against curated signatures

**Input.** A thresholded differential-abundance result from the researcher's own
cohort — typically genus-level from 16S, species-level from MetaPhlAn — with a
direction and a q-value per taxon. **Question:** *"My 34 genera that go up in
cases — has anyone seen this before, and in what condition?"*, i.e. which
published signatures are enriched in my hit list, and is my result specific to
my disease or generic dysbiosis? **Needed fields:** signature membership as NCBI
tax_ids at a stated rank; direction per signature; condition; body site; host
species; `Sequencing type` and `16S variable region` (a genus-level 16S
signature and a species-level shotgun signature cannot be intersected without
cutting to a common rank); group sizes, to down-weight tiny studies; PMID.
**Source:** BugSigDB is the only source shaped as *signatures* (sets) rather
than pairwise edges; `bugsigdbr::writeGMT()` exports them in the GMT shape
gene-set tools expect and `BugSigDBEnrich` runs the enrichment. Geistlinger et
al., Nat Biotechnol 42:790 (2024), PMC11098749; CBEA, Nguyen Q et al.,
PMC9154102.

**Can this graph answer it? YES — and this is the one the model was reshaped
for.** `Signature` is a first-class node with one `REPORTED_BY` edge per taxon,
so the *set* survives; a purely flattened `(Taxon)-[:ASSOCIATED_WITH]->(Disease)`
model would have destroyed it and made enrichment impossible. The research
document names this as the single structural note in its whole survey that is
about the shape of the graph rather than the choice of sources
(§5, "One structural note that is not a gap"). `Signature` carries
`sequencing_type`, `variable_region`, `host_species`, `group_0_size`,
`group_1_size` and `pmid`; `IN_CONDITION` and `AT_BODY_SITE` carry the condition
and site. The enrichment statistic itself runs outside the graph — the graph's
job is to serve the sets and their metadata, which it does (D1).

### W2. Biomarker discovery validated across cohorts

**Input.** Several public case-control cohorts for one disease — in practice
**curatedMetagenomicData** (>22,000 uniformly processed samples, 94 studies) —
plus the researcher's own. **Question:** *"Which taxa separate cases from
controls in a way that survives training on cohort A and testing on cohort B,
and is the separation specific to this disease?"* **Needed fields:** the
abundance matrices themselves (not in any KG). *From an association graph*: for
each candidate biomarker, which other diseases it is reported in, at what
direction, in how many independent studies, at what sample sizes — the
disease-specificity check; plus the confounder fields (`Antibiotics exclusion`,
`Matched on`, `Confounders controlled for`). **Source:** curatedMetagenomicData
for matrices; SIAMCAT (Wirbel et al., Genome Biol 22:93, 2021, PMC8008609) for
the ML and confounder checks; xMarkerFinder (PMID 38745111) as the protocol;
BugSigDB/GMrepo for cross-disease specificity. SIAMCAT's headline is itself a
design requirement: over 10,803 fecal metagenomes, naively transferred models
"lost accuracy and disease specificity".

**Can this graph answer it? PARTIAL.** The cross-disease specificity leg is
answerable now (D3): `count(DISTINCT r.study_id)` per (taxon, condition), across
conditions, with sizes and direction. (a) **The confounder fields are loaded**
as of 2026-09-03: `matched_on` (2,304 signatures), `confounders` (1,958) and
`antibiotics_exclusion` (6,485) are extracted and declared, so the fields the
research calls "the strongest argument for BugSigDB as the spine" are queryable
per signature (D11, which also records what the original diagnosis of this gap
got wrong). (b) Healthy-baseline prevalence is still absent; GMrepo or
`bugphyzz` fills it (D14).

### W3. Probiotic / live-biotherapeutic candidate selection

**Input.** A disease and the taxa reported depleted in it. **Question:** *"Which
depleted taxon is a credible intervention candidate — is the depletion
replicated, is there animal or human interventional evidence, is the organism
safe (no transferable AMR), and is there a plausible mechanism?"* **Needed
fields:** direction + replication count + evidence tier on the taxon–disease
edge; **intervention records** as a relation type (gutMDisorder is the only
surveyed source that curates *"interventions change the composition of gut
microbiota"* as a relation); per-genome AMR calls with model type and hit
category (CARD/RGI); taxon–metabolite production with an evidence tier.
**Source and the canonical worked chain:** *Akkermansia muciniphila* —
observational negative correlation with obesity/T2D → mouse work → a
randomised, double-blind, placebo-controlled pilot in 32 overweight
insulin-resistant humans (Depommier et al., Nat Med 25:1096, 2019, PMID
31263284). No single database records more than one rung of that chain.
gutMDisorder v2.0, NAR 51:D717 (2023); CARD, Alcock et al., NAR 48:D517 (2020).

**Can this graph answer it? PARTIAL — three legs of four.** Replicated
depletion with an evidence tier is answerable now (D10's first leg). The AMR leg
**is loaded**: CARD contributes 6,415 `CARRIES_RESISTANCE_GENE` edges, and 4 of
the 26 replicated IBD depletion candidates carry a determinant (D7, D10). The
metabolite leg **is loaded, and it is no longer HMDB-wide**: 3,418 `PRODUCES`
edges over 830 organisms — HMDB's 578 from 224 microbial-origin metabolites
keyed on free-text organism names (§"HMDB" in `source-formats.md`), plus
**NJC19's 2,840 export events over 638 species**. **18** of those 26 candidates
now carry a metabolite, against 7 before. Note which source did it: `pending:
MiMeDB` is what this sentence used to say, and MiMeDB contributed **zero**
production edges (D5). The
interventional-evidence leg **is loaded** —
gutMDisorder contributes 1,380
`(Taxon)-[:ABUNDANCE_CHANGED_BY]->(Intervention)` edges over 220 interventions,
558 of them human-interventional and 822 animal (D4). Note the graph can already *distinguish* the rungs —
`evidence_level` separates `in-vivo-model` from `interventional-rct` — it just
has only BugSigDB's slice of them.

### W4. Mechanism hypothesis via metabolite production (SCFA, bile acids, TMAO)

**Input.** A taxon whose abundance changed, optionally with a metabolomics
readout. **Question:** *"Which of my changed taxa can make butyrate / secondary
bile acids / TMA, and does that match the metabolite I measured?"* **Needed
fields:** taxon → metabolite with (a) relation direction (produces / consumes /
degrades), (b) evidence tier, (c) the pathway or gene carrying it, (d) the rank
at which the claim holds — strain-specific in most real cases, (e) a citation.
**Source:** the three exemplars in the research doc show the tiers are not
interchangeable — Vital et al.'s 3,055-entry butyrate gene catalogue over 3,184
genomes, whose own caveat is that pathway detection "does not automatically
imply functionality", with Peptococcaceae carrying the pathway but *oxidising*
butyrate; Rath et al.'s *cutC* in 100% of 50 fecal samples with no expression or
production measured (Microbiome 5:54, 2017, PMC5433236); and the *bai* operon,
characterised to purified enzymes yet with carriers differing in whether they
actually convert cholate to deoxycholate (Reed et al., PMC7221253). The
load-bearing number: gutSMASH, on 1,135 individuals with matched plasma and
faecal metabolomics, found metabolite levels "almost completely uncorrelated"
with the metagenomic abundance of the corresponding genes (r ≈ −0.04 to 0.24).

**Can this graph answer it? PARTIAL — six times wider than it was, and not
because of the source named for it.** The taxon–metabolite edge is **3,418
`PRODUCES` edges over 830 organisms and 226 metabolites**, `in-vitro` 3,383 /
`computational-predicted` 35 (D5). HMDB's half is unchanged and still small:
**224 records, 0.10% of the file**, keyed on uncontrolled, misspelled,
mixed-rank organism strings with no taxid, of which 158 are
`quantified`/`detected`, and 67 of which name no organism at all. The other
2,840 edges are **NJC19's export half** — species-level, literature-curated.

**`pending: MiMeDB` did not resolve the way this section assumed, and the
question is now closed rather than open.** The published bulk downloads are two
MySQL tables with **no association between them** — zero `MMDBm` ids in the
metabolites dump, zero `MMDBc` ids in the microbes dump, and no Microbial
Sources or Metabolic Reactions columns at all. That was measured on v1.0, and
**v2.0 was then fetched and measured the same way, with the same result**
(`data/raw/mimedb/v2/PROVENANCE.md`). The 23.1M BLAST-propagated pathways this
paragraph warned about are in neither download, so there is no predicted layer
here to segregate. What MiMeDB contributes is compound identity for NJC19's
free-text names.

**What v2.0 added is a count of the pairs it withholds.** Its `microbe_relations`
column is an integer per metabolite — MiMeDB's own tally of related microbes,
830,984 summed over the file — with no microbe id anywhere to say which. So the
pairs demonstrably exist in their database and are published nowhere: they are
reachable only from the site's per-metabolite web pages, and this project does
not scrape. **No bulk source publishes per-taxon production pairs at scale.**
That is a different statement from "the right file has not been fetched yet",
and it is the one the evidence supports. The gutSMASH result is *why* genome-inferred production is a
distinct and low tier rather than a synonym for production — and it is why
NJC19's `in-vitro` (an experimentally verified transport event) and a future
genome-inferred layer must not share a value.

### W5. Cross-feeding network inference

**Input.** A community composition from metagenomics. **Question:** *"Who feeds
whom? Which metabolite exchanges are present in a healthy community and lost in
disease?"* **Needed fields — the critical one is a `CONSUMES` edge.** Marcelino
et al. define the **Metabolite Exchange Score MES = 2·P·C / (P+C)** — the
harmonic mean of potential Producers and Consumers — and **MES = 0 when a
metabolite is only produced or only consumed**. Without consumption edges the
score is identically zero and the use case is dead. **Source:** the published
workflow does *not* use a curated association database — it reconstructs
genome-scale models (CarveMe, AGORA2) and reads production/consumption off
exchange reactions, simulated with MICOM (whose `interactions` output is a
directed `focal / partner / metabolite / flux / class ∈ {provided, received,
co-consumed}` table) or SMETANA. Marcelino et al., Nat Commun 14:6546 (2023),
PMC10589287: 955 species across 1,661 gut metagenomes, exchanges significantly
affected in 10 of 11 diseases. The curated alternative is **NJC19** (Lim et al.,
Sci Data 7:204, 2020, PMC7320173): 8,224 directed import/export/degrade events
plus 912 negative associations across 838 species, curated from 769 sources,
CC0.

**Can this graph answer it? YES for the curated class — NJC19 landed
2026-09-03.** **4,784 `CONSUMES` edges over 714 taxa and 205 metabolites**, plus
387 `DEGRADES` and 894 `NO_EXCHANGE_WITH`, and **96 metabolites carry both a
producer and a consumer**, so MES is non-zero for the first time (D6). The
computed class (MICOM/SMETANA) stays out of scope and separate (D20). **[A-override]** Part A5 says HMDB
"alone does not carry consumption" and asks Part B to name a source "or the use
case is descoped explicitly". The answer is NJC19, so it is *not* descoped — but
Part A understates the problem: **no source in the entire seven-source profiled
set carries consumption**, not just HMDB, and MiMeDB's origin assignment keys on
compounds appearing as a *product*, so it does not fill the gap either. NJC19's
literature-curated qualitative edges and MICOM/SMETANA's computed quantitative
edges are two evidence classes and must be separate edge types, never merged
(D6).

### W6. AMR gene surveillance in metagenomes

**Input.** Metagenomic reads, contigs or MAGs. **Question:** *"What resistance
genes are in this sample, to which drug classes, by which mechanism — and how
confident is each call?"* **Needed fields:** ARO id and its relations; the
**detection model type** (a variant model means the *mutation* confers
resistance, not the gene's presence); the **RGI hit category** (Perfect /
Strict / Strict-nudged / Loose); `confers_resistance_to_drug_class` vs
`confers_resistance_to_antibiotic`; and the curated-vs-prevalence provenance
flag. **Source:** CARD, whose inclusion bar is worth copying verbatim — an AMR
determinant must be "described in a peer-reviewed scientific publication, with
its DNA sequence available in GenBank, including clear experimental evidence of
elevated minimum inhibitory concentration (MIC) over controls" — while CARD
Prevalence is in silico only and "not included in CARD's primary curation".
Alcock et al., NAR 48:D517 (2020); CARD 2023, NAR 51:D690, PMC9825576.

**Can this graph answer it? YES — CARD landed 2026-09-03** (6,451
`ResistanceGene`s, 6,415 carriage edges, 539 taxa; D7). Four conditions applied
and all four were met, all from `source-formats.md`: key models on `Model ID`
(6,463 unique;
`ARO Accession` is duplicated on 5 rows of `aro_index.tsv`), prefer the CC BY 4.0
`aro.obo` half over the non-redistributable `card-data/` half and carry the
licence per edge, never use `card-ontology/ncbi_taxonomy.obo` as a source of
taxon labels (it renames `NCBITaxon:2` to CARD's editorial string), and say
plainly what the taxon edge means — the taxid on a model is the *reference
sequence's* organism, not the organism the gene is claimed for (132 models are
keyed on taxid 2, "Bacteria" — and 264 carriage edges are above species rank in
total). A "276k AMR links" figure sourced from Prevalence is predicted, not
curated; the predicted layer here is 104 of 13,691 drug-class edges and one
`WHERE` drops it (D7). The one field this workflow asked for that no download
can supply is the RGI hit category: Perfect / Strict / Loose is produced by
*running* RGI against a sample.

### W7. Drug–microbiome interaction lookup

**Input.** A drug (or a patient's medication list), or a taxon. **Question, two
directions:** (a) *drug → bug* — "does this non-antibiotic drug inhibit gut
commensals, and is the shift I see a drug effect rather than a disease effect?";
(b) *bug → drug* — "which gut bacteria metabolise this drug, by which gene?"
**Needed fields:** drug identifier (ChEMBL/ATC/DrugBank); taxon at **strain**
resolution — both landmark screens are strain-level; the assay and its readout;
the direction (**inhibits / metabolises / no effect** — the negatives matter);
and the gene where identified. **Source:** Maier et al. screened >1,000 marketed
drugs against 40 gut strains and found "24% of the drugs with human targets …
inhibited the growth of at least one strain in vitro" (Nature 555:623, 2018,
PMID 29555994); Zimmermann et al. measured 76 gut bacteria against 271 oral
drugs, of which 176 (65%) were metabolised by at least one strain (Nature
570:462, 2019, PMID 31158845). Curated aggregator: **MASI** (Zeng et al., NAR
49:D776, 2021, PMC7779062), the only drug resource with a directed, typed edge —
bacteria→substance 4,001 pairs, substance→bacteria 7,770 pairs, genus-level.

**Can this graph answer it? YES — both directions are closed, and neither was
closed by MASI.**

MASI is not dead, and this entry said it was. `www.aiddlab.com` answers HTTP
200 on all eight of its download files from behind an **expired TLS
certificate**: every automated fetch died at the handshake, and the Wayback
Machine — which cannot handshake with it either — holds only the one file
somebody had saved by hand, so two failures with one cause read as
confirmation. The tables carrying the 4,001 + 7,770 typed pairs were fetched
through a browser on 2026-09-03, with certificate verification left on;
`docs/sources.md` §14 carries the retraction, the file list and what is loaded
from them. What closed both directions of this query is still the two primary
screens below, which measure where MASI curates.

**Direction (a), drug → bug, is answered by the landmark screen MASI
aggregates, loaded directly.** Maier et al.'s supplementary tables carry the
whole 1,197-drug × 40-isolate matrix, so the graph holds **5,592
`INHIBITS_GROWTH_OF` and 42,233 `DOES_NOT_INHIBIT_GROWTH_OF` edges** over 38
taxa and 1,197 drugs, and reproduces the paper's own headline from the loaded
edges: **203 of 835 human-targeted drugs (24.3%) inhibit at least one strain**.
This is *better* than MASI would have been for this leg — MASI resolves "down to
genus level" while the screen is strain-resolved, and MASI curates positives
while the screen measured every cell. Two earlier legs remain and answer
different questions: ChEMBL supplies 95 drugs acting on a protein of 28
bacterial taxa, and gutMDisorder's interventions joined to ChEMBL by name supply
85 `ABUNDANCE_CHANGED_BY` edges over 15 drugs and 57 taxa.

**The negatives are the part of "needed fields" nothing else here supplies, and
both screens carry them.** W7's field list asks for "the direction (**inhibits /
metabolises / no effect** — the negatives matter)", and before these two sources
landed the graph had no drug negative of any kind. A screen measures the whole
matrix, so "this drug was tested against this bacterium and did nothing at
20 µM" and "this strain was given this drug and did not touch it" are
*measurements*, not absences of curation — **42,233 and 17,479 of them**, the
larger half of each source. Each is its own relationship rather than a flag, so
no `MATCH (d)-[:INHIBITS_GROWTH_OF]->(t)` and no
`MATCH (t)-[:METABOLISES]->(d)` counts a refutation as an observation by
omission. The 55 cells Maier's screen wrote `NA` for become **neither**
relationship: a pair nobody measured is not a non-hit. Zimmermann's screen has
no such cell — all 20,596 carry a number — and the loader still refuses to file
a missing one as a non-hit, because that is the error that would look harmless.

**Four of Zimmermann's eighty measured columns are not organisms**, and they are
worth naming here because the mistake is invisible: `Control pH 4` through
`Control pH 7` sit *between* strain columns with the same five sub-columns each,
and under the hit rule they produce 38 apparent hits between them. Loading them
would have written 1,084 cells of abiotic chemistry as microbial metabolism, and
would have reported 80 screened strains against the paper's 76.

**Direction (b), bug → drug, is closed by the same move: the other landmark
screen, loaded directly.** Zimmermann et al. measured 271 orally administered
drugs against 76 human gut strains by LC-MS, every cell of the matrix, and the
graph holds **2,575 `METABOLISES` and 17,479 `DOES_NOT_METABOLISE` edges** over
66 taxa and 271 drugs, reproducing the paper's own headline from the loaded
edges: **176 of 271 drugs (65%) are metabolised by at least one strain**
(`docs/sources.md` §16). The two directions are **different edge types running
opposite ways** — `Drug → Taxon` for inhibition, `Taxon → Drug` for metabolism —
which is the requirement Part D's D8 recorded before either source was fetched,
because collapsing them conflates antimicrobial killing with drug metabolism.

**"And the gene where identified" is answered without a `Gene` node.** The
metabolism screen's second half identifies 30 bacterial gene products for 20 of
the drugs, and they ride on the edge as `gene_locus_tags`, `gene_products` and
`gene_protein_ids` for the 37 (organism, drug) pairs they cover. They are not a
node type because they come from a *different experiment* — a gain-of-function
library expressed in *E. coli*, not the 76 strains — and **5 of the 37 pairs
disagree with the whole-cell screen**, which is why those five sit on
`DOES_NOT_METABOLISE` edges rather than being quietly dropped. `docs/model.md`
records what would change the recommendation.

**The rank caveat survives, softened, on both screens.** Both are strain-level
and this graph keys `Taxon` on the species, so Maier's 40 isolates promote to 38
taxa and Zimmermann's 76 to 66 — the two *B. fragilis* and two *E. coli*
isolates of the first, the seven *B. fragilis* and three *B. thetaiotaomicron*
of the second, and two Zimmermann strains that reach no taxon at all because
NCBI holds two candidates for each name and the sheet has nothing to choose
with. Nothing else is lost: each collapse is **parallel edges**, and `nt_code` /
`screen_column`, `strain` and `reported_name` carry the isolate on every edge,
so "which strain?" is answerable from the edge even though the strain is not a
node.

### Evidence grading adopted

Two proposals had to be reconciled: the research document's **nine-value**
`evidence_level` (§3.3, itself marked `[inference]` — a synthesis, not a
published vocabulary) and the schema survey's **seven-value** ladder (§5(b),
project-controlled, chosen for exportability). They disagree on more than
length: the nine values mix *what was measured* with *how many times it was
measured*, while the seven describe only the measurement.

**The reconciliation rule: `evidence_level` describes one observation, never a
body of evidence.** An edge is one signature's report of one taxon. It cannot
know how many other studies agree with it, and a stored answer would be frozen
at build time and wrong after the next source refresh. So the four values in the
nine-value list that are properties of a *set* — `curated_single_study`,
`curated_replicated`, `temporal_or_genetic`, `established` — are **not adopted
as values**. Replication is `count(DISTINCT r.study_id)` at query time (D3, D5,
D17), which is strictly more informative and which D15 can audit; the temporal
axis survives verbatim in `study_design` (`prospective cohort`, `time series /
longitudinal observational`) where a query can filter on it; and `established`,
which ClinGen defines as requiring replication *over time*, is a verdict about a
taxon–disease pair and is therefore a query result, not an edge property.

**The final `evidence_level` vocabulary — twelve values.** Ten are emitted
today by `microbiomekg.ontology.evidence_level()`; two are reserved for sources
being loaded next. Spelling is hyphenated with `16S` capitalised, because that
is what the built edges already carry; `source-formats.md`'s underscore
spellings (`observational_16s`, `in_vivo_model`, `in_vitro`,
`computational_predicted`, `interventional_clinical`) are the same values in a
different spelling and each pending loader maps to the hyphenated form on write.
A near-miss spelling is a silent filter miss, so D15 counts distinct values.

| Value | One-line definition | Source field(s) that justify assigning it |
|---|---|---|
| `computational-predicted` | No measurement of *this* edge: a genome/MAG pathway call, sequence similarity, homology propagation or a KG inference. | HMDB `status ∈ {predicted, expected}` (88.8% of HMDB); CARD's 36 meta-models with no reference sequence; MiMeDB's BLAST-propagated pathway layer; Reactome `IEA`. |
| `text-mined` | Asserted by an NLP or co-occurrence pipeline; no curator read the paper. | No current source emits it. Reserved so that a SemMedDB-class source can never land as anything else — SemRep's strict precision is 0.55. |
| `unknown` | The source records no design, host or assay from which a level can be derived. Never defaulted to observational. | BugSigDB rows whose `Study design` is absent (17 edges today); KEGG links; Reactome `TAS`; HMDB disease associations, which are metabolomic and take `unknown` rather than a plausible-looking `observational-*`. |
| `observational-unspecified` | A human observational differential-abundance result whose assay is not recorded. | `Study design` ∈ the observational set **and** `Sequencing type` absent or outside the known set. |
| `observational-targeted` | Observational, measured by a targeted assay rather than a community survey. | `Sequencing type = PCR`; gutMDisorder `Sequencing Technology` ∈ {qPCR, PCR, RT-qPCR, DGGE}. |
| `observational-amplicon` | Observational, non-16S amplicon. | `Sequencing type ∈ {ITS / ITS2, 18S}`. |
| `observational-16S` | Observational, 16S amplicon — the graph's modal value and, per Edgar, genus-resolution at best. | `Sequencing type = 16S`. |
| `observational-shotgun` | Observational, whole-metagenome shotgun; the only observational rung that supports a species-level claim. | `Sequencing type = WMS`; gutMDisorder "quantitative metagenomics by shotgun sequencing". |
| `meta-analysis` | A synthesis over several cohorts, curated as one record. | `Study design = meta-analysis`. |
| `in-vitro` | Measured in culture: monoculture or defined co-culture growth, a metabolite assay, an MIC over controls, or a gene→product step shown by knockout or heterologous expression. | `Study design = laboratory experiment` with no live host named; CARD's curated resistance models; ChEMBL mechanism rows whose only references are PubMed; HMDB microbial-origin edges whose metabolite is `detected`/`quantified`; NJC19's experimentally-verified events; **every edge of the Maier 2018 growth screen, which is the largest population of this level in the graph — and the only one where the level is carried by a *non-*result as often as by a result**. |
| `in-vivo-model` | Demonstrated in a non-human host — any design run in an animal, gnotobiotic colonisation, or HMA-rodent transfer. A discounted tier, never causal support. | `Host species` ∉ {human, absent}, **whatever the design** — a mouse RCT is not human interventional evidence; the whole gutMDisorder mouse workbook. |
| `interventional-rct` | A randomised controlled trial in humans, or an approved clinical use. | `Study design = randomized controlled trial` with a human host; gutMDisorder human rows whose `Research Type` names an intervention; ChEMBL `max_phase = 4` **and** a DailyMed/FDA/EMA reference. |

**Two companions, kept separate and never folded into the level** (§5(b), and
STRING's architectural lesson — the combined score is an aggregate but the
channels are never destroyed):

- **`knowledge_level`** — Biolink's seven values verbatim:
  `knowledge_assertion`, `logical_entailment`, `prediction`,
  `statistical_association`, `text_co_occurrence`, `observation`,
  `not_provided`. Written from a per-source table, never defaulted; BugSigDB is
  `statistical_association` (the assertion is "these two groups differed", not a
  causal claim). `not_provided` is a real, countable value.
- **`agent_type`** — Biolink's eight verbatim: `manual_agent`,
  `automated_agent`, `data_analysis_pipeline`, `computational_model`,
  `text_mining_agent`, `image_processing_agent`,
  `manual_validation_of_automated_agent`, `not_provided`. BugSigDB is
  `manual_agent`: a named curator read a published figure, with a curation date
  and a review state on the row.

**Two things deliberately not stored.** `contradiction` (ClinGen's
`disputed`/`refuted`, DisGeNET's EI) is *not* an edge property: with one source
there is no adjudicating authority, and a stored verdict would be a majority
vote over parallel edges, which guard G4 forbids. Disagreement is a query result
(D17). And nothing is stored as a **score** — §5(b) is explicit that a derived
confidence may be computed in a query from these components but must not be
stored as the evidence field.

### Guards adopted from the criticism

The ten consolidated guards of §4.26, each reduced to a statement a test can
fail on. The empirical warrant for the whole set, quoted once: Tierney et al.
(PLoS Biology 20(3):e3001556, 2022, PMC8890741) fitted **6,035,110 models**
across 6 phenotypes and 15 cohorts and found that of 581 previously-reported
microbe–disease associations, **"1 out of 3 taxa demonstrated substantial
inconsistency in association sign"**, with **">90% of published findings for
type 1 diabetes (T1D) and type 2 diabetes (T2D)"** nonrobust. The sign flips
about one time in three; every guard below follows from that.

- **G1 — Identity includes direction, body site and host.** An association is
  keyed on `(signature_id, tax_id, condition_id)`; parallel edges are the
  evidence, not a defect. Testable: the three `bsdb:23459324` signatures with
  identical PMID, condition, taxon and direction remain **three**
  `ASSOCIATED_WITH` edges; a `(taxon, condition)` pair carrying both
  `increased` and `decreased` remains two edges. *(C12, C13.)*
- **G2 — No bare names, no surrogate ids, nothing dropped.** Every taxon is an
  NCBI tax_id chased transitively through `merged.dmp`; a deleted id becomes an
  `UnresolvedTaxon` tombstone with `status="deleted"` and **no** `tax_id`.
  Testable: input rows = edges + `unresolved_taxa` records + explicitly
  reported filter counts, and taxid 3120442 exists as a tombstone still wired
  to its 16 signatures. *(C6, C18.)*
- **G3 — Per-edge provenance and per-edge licence.** Every association edge
  carries `primary_source`, `source_record_id`, `source_licence` and
  `source_relation`, and every source's version string and retrieval date is
  recorded in `docs/sources.md`. Testable: `ontology_audit()` reports zero
  violations for those four fields; a mixed-licence graph can be redistributed
  in parts because the licence is on the edge, not on the graph.
- **G4 — Single-cohort is flagged; disagreement is exposed, never resolved.** A
  taxon–disease pair supported by exactly one distinct `study_id` is reported as
  `single_cohort` and excluded by default from ranked outputs; a pair carrying
  both directions is returned as two rows with their study ids and evidence
  levels, never reduced to a sign and never resolved by majority. Testable: D17
  on *Fusobacterium nucleatum* × colorectal cancer returns the 39 `increased`
  edges **and** the one `decreased` edge, not a verdict; T1D and T2D edges are a
  standing fixture. *(Tierney, above.)*
- **G5 — Rank ceiling enforced by assay.** A species-level claim is served as
  species-level only when the evidence is shotgun, full-length 16S or an isolate
  genome; `reported_rank` stays the source's claim and NCBI's own rank is kept
  separately in `original_rank`. Warrant: identical V4 sequences belong to
  different species with **63% probability**, and best-method species accuracy
  at V4 is 19.8% (Edgar, PeerJ 6:e4652, 2018). Testable: no D-query ranks
  species identity off `observational-16S` edges without saying so in its
  result.
- **G6 — Causal claims default false; animal evidence is a discounted tier.** No
  query returns "X causes Y" from `observational-*` or `in-vivo-model` evidence,
  and `in-vivo-model` sorts below `interventional-rct` in every ranked output.
  Warrant: 95% of published HMA-rodent studies (36/38) reported phenotype
  transfer, a rate Walter et al. call implausible (Cell 180:221, 2020). Testable:
  D4's ordering, and the absence of any `causes` predicate in the ontology.
- **G7 — Confounder control is schema, not metadata.** `matched_on`,
  `confounders` and `antibiotics_exclusion` are queryable per signature, so
  "which studies for disease Y controlled for medication" is one query.
  Testable: D11 returns a non-empty breakdown. **This guard holds as of
  2026-09-03** — `antibiotics_exclusion` is extracted and all three columns are
  declared, which `tests/test_acceptance.py` asserts separately from their
  values (D11 records what the original diagnosis got wrong). Warrant:
  26 differentially abundant ASVs in T2D → **0** after matching on host
  variables (Vujkovic-Cvijin et al., Nature 587:448, 2020).
- **G8 — Curated and machine-extracted are segregated at the schema level.**
  `knowledge_level` × `agent_type` is written from a per-source table and never
  defaulted; a source whose evidence model nobody has read gets `not_provided`,
  which one `WHERE` clause counts. Testable: every value is drawn from Biolink's
  pinned enums, and no `text-mined` edge shares an `evidence_level` with a
  curated one.
- **G9 — Placeholder and implausible taxa are flagged, not dropped and not
  string-matched.** `Taxon.placeholder` is true for `uncultured bacterium`
  (77133), `Bacteroides sp.` (29523) and `Candidatus` names; ranked D-queries
  exclude them by that boolean, never by a name substring. Testable: C9's four
  fixtures resolve verbatim and carry the flag. **Half-open:** the
  habitat-plausibility check §4.16 asks for — the check that would have caught
  hot-spring organisms curated faithfully out of a contaminated placenta paper —
  is not implemented, and is recorded as absent rather than assumed.
- **G10 — Expansion factor published; no scoring without hygiene.** The build
  reports edges per source record, predicted edges stay behind
  `knowledge_level = 'prediction'` so excluding them is one `WHERE` clause, and
  nothing here is scored for link prediction without a source-disjoint split and
  a degree-matched baseline. Testable: D15 reports the per-source
  edge-to-record ratio. Warrant: GMMAD ships 220,690 *predicted* associations
  alongside 3,836 curated ones — 57× — and a KG's link predictions correlate
  with node degree at R² = 0.77.

**[A-override] on A1's evidence vocabulary.** Part A1 asks for a level that
distinguishes "observational abundance difference (16S), observational
(shotgun), interventional/clinical, in-vivo model, in-vitro/experimental, and
computational/predicted" — six classes. The adopted vocabulary is twelve,
because BugSigDB's own design column forces `meta-analysis` and three further
observational assay classes to be distinguishable, and because `unknown` and
`text-mined` must be *values* rather than nulls for A1's third bullet
(countability) to hold. A1's six are a subset of the twelve; nothing it asked
for was dropped.

## Part C — Pitfalls

Every id, name class, delimiter and count below was read out of the real
sources on 2026-09-02 — NCBI `new_taxdump` (2026-09-02 build) and the
BugSigDB `full_dump.csv` export stamped `2026-09-02_20:58_UTC`, 14,846 data
rows. Nothing here is from memory. The fixtures under `tests/fixtures/` are
cut from those same two files, so each example below is reproducible against
the fixture without a network call.

Fixture inventory:

- `tests/fixtures/taxdump_mini/` — 220 nodes (65 taxa of interest + 155
  lineage scaffolding to `root`), 533 name rows, 6 `merged.dmp` rows, 3
  `delnodes.dmp` rows. Every line is copied verbatim from the real dump.
- `tests/fixtures/bugsigdb_mini.csv` — 34 real rows + 9 hand-built
  adversarial rows, in the real 51-column export format including the
  leading licence banner line.
- `tests/fixtures/mondo_mini.obo` — 11 MONDO stanzas copied verbatim from the
  2026-09-01 release: the six terms the BugSigDB fixture cites, an obsolete
  one, and terms carrying `MONDO:equivalentTo` xrefs to EFO and DOID.

Test modules: `tests/test_reconcile.py` (the taxonomy pitfalls, C1–C9),
`tests/test_ontology.py` (C11, C17, and the ontology-artifact drift guard
C21), `tests/test_build.py` (the end-to-end build, C10, C12–C19) and
`tests/test_loader_contracts.py` (C13's and C16's kglite-engine behaviours,
which run whether or not this repo's code exists).

Test-name convention below: `file::test_name`.

### C1. Name classes — a name is not a key

`names.dmp` has one row per (tax_id, name, name class). The classes that a
resolver may look through are `scientific name`, `synonym`,
`equivalent name`, `genbank synonym` and `includes`. `authority` is **not**
one of them: it holds the citation-decorated form
(`Clostridioides difficile (Hall and O'Toole 1935) Lawson et al. 2016`) and
matching on it would attach papers to strings no author writes.

Real: tax 562 alone carries 16 name rows across six classes, including the
`includes` rows `Achromobacter sp. ATCC 35328` and `bacterium 10a` — names
that are *not* E. coli in any paper, but which NCBI files under 562.

Guard: `tests/test_reconcile.py::test_scientific_name_resolves_exact`,
`::test_includes_class_is_searched`, `::test_lookup_is_case_insensitive`,
`::test_authority_class_is_not_a_lookup_class` (which uses
`Lactobacillus plantari`, a `(sic)` misspelling that exists *only* inside an
`authority` string for 1590 — matching that class would resolve it).

### C2. Homonyms across kingdoms — `first-wins` invents facts

Three genus names in the fixture resolve to more than one taxon, verified in
`names.dmp`:

| name | tax_ids | what they are |
|---|---|---|
| `Bacillus` | **1386**, **55087** | bacterial genus (`Bacillus <firmicutes>`) / stick-insect genus (`Bacillus <walking sticks>`) |
| `Proteus` | **583**, **210425** | enterobacterial genus / the olm, a salamander (`Proteus <salamanders>`) |
| `Morganella` | **581**, **90690**, **108061** | enterobacteria / basidiomycete fungi / scale insects |

NCBI disambiguates in the `unique name` column, which most exports throw
away. `Morganella` is a three-way collision, so even a "if exactly two, take
the bacterial one" heuristic fails.

The resolver must return `status="ambiguous"` with all candidates in
`candidates` and **no** `tax_id`. A first-wins index keyed on lowercase name
would silently file every `Bacillus` signature under a stick insect or a
bacterium depending on file order in `names.dmp`.

Guard: `tests/test_reconcile.py::test_homonym_genus_is_ambiguous`
(parametrised over the three names and their exact candidate tuples).

### C3. Homonyms *within* bacteria — the kingdom heuristic is not enough

C2 invites the fix "prefer the bacterial candidate". It does not work.
`Bacteroides corrodens` is a `synonym` of **both**:

- **539** — `Eikenella corrodens` (Betaproteobacteria), unique name
  `Bacteroides corrodens <b-proteobacteria>`
- **827** — `Campylobacter ureolyticus` (Campylobacterota), unique name
  `Bacteroides corrodens <e-proteobacteria>`

Both are oral/gut bacteria that appear in microbiome papers. Likewise
`Bacillus brevis` is a synonym of **1393** (`Brevibacillus brevis`) and of
**2815668** (`Phalces brevis`, a stick insect).

Guard: `tests/test_reconcile.py::test_intra_bacterial_homonym_is_ambiguous`.

### C4. Renamed taxa — and the ones NCBI kept only in authority form

The rename cases from the announcement, with the tax_id each resolves to and
the *exact* name class the old binomial is filed under:

| name used in papers | tax_id | how NCBI stores the old name |
|---|---|---|
| Clostridium difficile → Clostridioides difficile | **1496** | **authority-decorated `synonym` only** |
| Propionibacterium acnes → Cutibacterium acnes | **1747** | bare `synonym` |
| Ruminococcus gnavus → Mediterraneibacter gnavus | **33038** | bare `synonym` |
| Lactobacillus reuteri → Limosilactobacillus reuteri | **1598** | **authority-decorated `synonym` only** |
| Lactobacillus plantarum → Lactiplantibacillus plantarum | **1590** | **authority-decorated `synonym` only** |
| Lactobacillus rhamnosus → Lacticaseibacillus rhamnosus | **47715** | bare `synonym` |
| Eubacterium rectale → Agathobacter rectalis | **39491** | **authority-decorated `synonym` only** |

This is the sharpest trap in the whole catalog and it is invisible until you
grep the dump. NCBI is **inconsistent**: for 1747, 33038 and 47715 it keeps
both `Propionibacterium acnes` and
`Propionibacterium acnes (Gilchrist 1900) Douglas and Gunter 1946 (Approved Lists 1980)`.
For 1496, 1598, 1590 and 39491 it keeps **only** the decorated form —
`grep -P "\t\|\tClostridium difficile\t\|" names.dmp` returns nothing. A
resolver that indexes name classes literally therefore returns
`unresolved` for *Clostridium difficile*, the single most-cited renamed
organism in the clinical microbiome literature, while happily resolving
*Propionibacterium acnes*. The failure is silent and looks like a data gap.

The fix is a second, normalised index that strips a **recognised authority
tail** (a parenthesised authority, an `Author Year` / `Author et al. Year`
tail, `emend.`, `(Approved Lists 1980)`, `(sic)`), consulted **only when the
exact index misses**. Exact-first is not optional — see C5.

Guard: `tests/test_reconcile.py::test_legacy_binomial_resolves_via_authority_stripping`
(parametrised over all seven rows above, asserting tax_id **and** that the
four decorated-only cases come back `status="synonym"`, not `"unresolved"`).

### C5. Authority stripping must not outrank exact matches

A greedy normaliser — "cut everything from the first capitalised token after
the epithet" — maps `Escherichia coli K-12` to `escherichia coli`, so the
normalised index maps `escherichia coli` to **{562, 83333}** and a
normalised-first resolver reports `Escherichia coli` as **ambiguous**. This
was reproduced on the fixture while writing these tests.

Contract: consult the exact index first and return its answer if non-empty;
consult the normalised index only on a miss. Then `Escherichia coli` → 562
`exact`, `Escherichia coli K-12` → 83333 `exact` (then promoted, C7), and
`Clostridium difficile` → 1496 `synonym`.

Guard: `tests/test_reconcile.py::test_exact_match_beats_normalised_match`.

### C6. Merged and deleted ids in older exports

`merged.dmp` maps a retired id to its survivor; `delnodes.dmp` lists ids that
were withdrawn with no successor. Both appear in exports made before the
change. Real rows in the fixture:

- `1440055 | 1496 |` and `1581190 | 1496 |` — two retired *Clostridioides
  difficile* ids.
- `1129128 | 1598 |`, `299639 | 47715 |`, `83834 | 1590 |`,
  `105824 | 853 |`.
- Deleted, verified absent from both `nodes.dmp` and `merged.dmp`:
  **1009**, **1029**, **1036**.

A merged id must resolve to the survivor with `status="merged"` and
`original_tax_id` preserved — dropping the original loses the ability to
explain why an old paper's id is not in the graph. A deleted id must come
back `status="deleted"` with **no** `tax_id`: inventing one is worse than
admitting the loss. An id in none of the three files (fixture uses
**999999999**) is `unresolved`.

Guard: `tests/test_reconcile.py::test_merged_id_resolves_to_survivor`,
`::test_deleted_id_has_no_tax_id`, `::test_unknown_id_is_unresolved`,
`tests/test_build.py::test_merged_old_id_absent_new_id_present` and
`::test_merged_row_lands_on_the_survivor`.

### C7. Strains and subspecies must promote, keeping the original

- **83333** `Escherichia coli K-12`, rank `strain`, parent **562** rank
  `species`.
- **1682** `Bifidobacterium longum subsp. infantis`, rank `subspecies`,
  parent **216816** `Bifidobacterium longum`, rank `species`.

With `rank_ceiling="species"` both promote to the parent with
`status="promoted"`, `tax_id` = the species, `original_tax_id` = the strain
or subspecies id and `original_rank` = `"strain"` / `"subspecies"`. Losing
`original_tax_id` makes the promotion unauditable; not promoting leaves the
graph with a `:Taxon` that no species-level query finds.

A taxon already at or above the ceiling is **not** promoted: `Bacillus`
(1386, `genus`) and `Lachnospiraceae` (186803, `family`) come back `exact`.

Guard: `tests/test_reconcile.py::test_strain_promotes_to_species`,
`::test_subspecies_promotes_to_species`, `::test_strain_name_promotes_too`,
`::test_rank_at_or_above_ceiling_is_not_promoted`,
`::test_rank_ceiling_genus_promotes_a_species`,
`tests/test_build.py::test_below_species_rows_land_on_the_species_node`.

### C8. Rank-less nodes break naive lineage walking

The fixture's 219 nodes carry 25 distinct rank strings. Walking "up until you
hit a rank" or "the parent is always the next standard rank" fails on:

- **1** `root`, rank `no rank`, whose parent is **itself** (`1 | 1 | no rank`).
  A promotion loop with no self-parent guard hangs here — and the 120 s
  pytest ceiling is what turns that into a *failed* test rather than a
  wedged suite.
- **131567** `cellular organisms`, rank `cellular root` — a rank string most
  rank tables do not contain.
- 23 nodes at rank `clade` (e.g. **1783257** in the *Akkermansia muciniphila*
  lineage) and 6 more at `no rank`, sitting *between* standard ranks.
- **48479** (`environmental samples`, `no rank`) is the parent of **77133**
  `uncultured bacterium`, and **2646097** (`no rank`) the parent of **29523**
  `Bacteroides sp.` — so "parent of a species is a genus" is false in the
  fixture, not just in theory.

The promotion loop must be driven by an explicit *below-ceiling* rank set and
must terminate on a self-parent, never by assuming a rank ladder.

Guard: `tests/test_reconcile.py::test_promotion_terminates_at_self_parent_root`,
`::test_rankless_and_clade_nodes_do_not_break_resolution`,
`::test_species_whose_parent_is_rankless_still_resolves`,
`tests/test_build.py::test_taxon_lineage_is_walkable_to_root`.

### C9. Placeholder and bracketed names are real nodes, not junk

All four of these are `scientific name` rows in the real dump and all four
are in the fixture:

- **77133** `uncultured bacterium` — 13 BugSigDB rows cite it. It is a real
  tax_id and a real signature member, but it is not an organism anyone can
  act on. It must resolve (to 77133) and be *flagged*, not dropped.
- **29523** `Bacteroides sp.` — a genus-level placeholder filed at rank
  `species`. Its `sp.` suffix means "some species of"; treating it as a
  species sibling of *Bacteroides fragilis* double-counts the genus.
- **1512** `[Clostridium] symbiosum` — the brackets are NCBI's marker for
  "the name is misapplied; this is not really *Clostridium*", and they are
  **part of the scientific name string**. Whether the plain binomial also
  resolves is a *per-taxon curation fact*, not a rule: for 1512 NCBI happens
  to also file `Clostridium symbiosum` as a `synonym`, so it resolves without
  any unbracketing step — but nothing guarantees that for the next bracketed
  taxon. Never write an unbracketing normaliser; look the name up and let
  `names.dmp` answer.
- **2500537** `Candidatus Cibiobacter qucibialis` — `Candidatus` is a status
  prefix, not a genus. Stripping it yields `Cibiobacter qucibialis`, which is
  not in `names.dmp`.

Contract: resolve them exactly as written, and carry a flag so
`Part D` queries can exclude them; never silently normalise the brackets or
the `Candidatus` prefix away, and never drop the row.

Guard: `tests/test_reconcile.py::test_placeholder_names_resolve_verbatim`,
`::test_unbracketed_name_resolves_through_the_synonym_row`,
`::test_stripping_the_candidatus_prefix_does_not_match`.

### C10. BugSigDB: the taxon column is a *lineage path*, not a taxon list

The export's own encoding, read off the real file:

- The file starts with a **licence banner line** before the header. Reading
  it with `pd.read_csv(path)` gives a one-column frame; `skiprows=1` is
  required.
- `NCBI Taxonomy IDs` holds **`;`-separated taxa**, and each taxon is a
  **`|`-separated lineage path whose last element is the taxon**. Example
  from `bsdb:22728514/4/1`:
  `3379134|1224|1236|2887326|468|469;1783272|201174|1760|85009|31957|1912216|33011;…`
  → the taxa are **469**, **33011**, … — not 3379134, 1224, 1236.
- Splitting on `|` as well as `;` yields **9,458** distinct ids across the
  full dump where the correct answer is **8,152** — 1,306 phantom taxa, every
  one of them an *ancestor* that the study never reported, each acquiring
  edges it did not earn.
- The parallel `MetaPhlAn taxon names` column uses a **different outer
  delimiter**: `,` between taxa, `|` between ranks (`k__…|p__…|s__…`). The
  two columns zip positionally (verified: **0** length mismatches over the
  14,225 rows that have both), but only if each is split on its own
  delimiter.
- Missing is the literal string `"NA"`, never an empty cell — so
  `pd.read_csv(..., keep_default_na=False)` plus an explicit `"NA"` check,
  otherwise `"NA"` becomes `NaN` and a float column (C16).

Guard: `tests/test_build.py::test_only_leaf_taxa_are_cited`,
`::test_ancestors_acquire_no_association_edges`. Note the ancestors are
legitimately *present* as `:Taxon` nodes — `HAS_PARENT` has to be walkable —
so the assertion is that they carry no `REPORTED_BY` and no
`ASSOCIATED_WITH` edge, not that they are absent.

### C11. BugSigDB: `Study design` is multi-valued *and* contains commas

`Study design` is comma-joined, and one of its atomic values contains a
comma: `cross-sectional observational, not case-control`. So
`bsdb:...` rows literally read
`laboratory experiment,cross-sectional observational, not case-control`.

Naively splitting on `,` over the full dump produces the phantom design
values `cross-sectional observational` and `not case-control`, giving 9
tokens where the real vocabulary is 7 designs plus `NA`. The seven atomic
values, all present in the fixture, are:

`case-control`, `cross-sectional observational, not case-control`,
`laboratory experiment`, `prospective cohort`,
`time series / longitudinal observational`,
`randomized controlled trial`, `meta-analysis`.

The split must be against that known vocabulary (longest-match first), not
on the delimiter. `EVIDENCE_LEVELS` must have a key for each of the seven.

Guard: `tests/test_ontology.py::test_evidence_levels_cover_every_fixture_design`,
`::test_evidence_levels_cover_the_whole_bugsigdb_vocabulary`,
`::test_naive_comma_split_is_not_the_design_vocabulary`,
`::test_the_multi_design_fixture_row_splits_into_two_known_designs`,
`::test_evidence_levels_values_are_the_declared_levels`.

### C12. BugSigDB: direction is relative to Group 1, and disagreement is data

`Abundance in Group 1` ∈ {`increased`, `decreased`, `NA`} (7,741 / 6,683 /
422 in the full dump). It is the abundance in **Group 1** relative to Group
0, and `Group 0 name` / `Group 1 name` are free text — `bsdb:39/2/1` has
Group 0 `after excercise` and Group 1 `youth Neck before`, i.e. Group 1 is
*not* reliably the case arm. So `increased` maps to "increased in Group 1",
and the group names must ride along on the edge; it may not be flattened to
"increased in disease".

Across the full dump **8,818** (taxon, condition) pairs carry *both*
`increased` and `decreased` from different studies — for example
(**410072**, `Obesity`). Collapsing them into one signed edge destroys a
real, reportable disagreement, which is exactly the A1/A2 contract.

Guard: `tests/test_build.py::test_direction_is_stored_per_association`,
`::test_conflicting_directions_survive_as_separate_edges`.

### C13. Cross-source dedupe: two studies are two edges

`bsdb:23459324/3/2`, `bsdb:23459324/4/1` and `bsdb:23459324/6/1` are three
signatures from **the same study, same PMID (23459324), same condition
(Obesity, MONDO:0011122), same taxon (1598 *Limosilactobacillus reuteri*),
same direction (increased)** — but different experiments with different
sample sizes (64/108, 64/32, 79/140). They are three pieces of evidence, not
one.

Contract: a `Signature` node per source row, and taxon–condition association
edges hung off the signature. A `MERGE`-style collapse on (taxon, condition)
would turn 3 into 1 and make "list the supporting studies" (A1) unanswerable.
The count that proves it: the fixture's 43 rows resolve to **53** distinct
taxa but **71** taxon-report edges.

Guard: `tests/test_build.py::test_same_pair_from_three_signatures_is_three_edges`,
`::test_conflicting_directions_survive_as_separate_edges`,
`::test_golden_edge_counts`.

**And the loader used to undo it silently at scale.** Reproduced against
kglite 0.16.21 while writing these tests: the blueprint's junction-CSV loader
streamed in chunks and **deduplicated parallel edges from the second chunk
onwards**. With `KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE=3` and a junction CSV
holding ten identical `A1 -> B1` pairs, the built graph had **three** edges.
The default chunk is 100,000 rows and `taxon_condition` is 112,966 rows of
deliberately parallel edges, so a default build dropped 7.7% of them —
precisely the evidence multiplicity this whole document exists to protect,
removed with no warning and no error, which is why the build raised the chunk
size above the row count.

That test pinned the *bug* rather than xfailing it, and kglite 0.16.22 turned
it red: the chunk regime is now decided once per CSV, so the chunk size bounds
peak RAM without changing the graph. It is asserted as a fix now — `guard`
below — and this repo's floor is `kglite>=0.16.22`.

Guard: `tests/test_loader_contracts.py::test_junction_loader_keeps_parallel_edges`,
`::test_junction_loader_keeps_parallel_edges_across_a_chunk_boundary` (ten rows
through a three-row chunk still load ten edges) and
`::test_junction_loader_keeps_edge_properties_across_a_chunk_boundary` (the
survivors keep their own `pmid` rather than the last chunk's).

### C14. Disease identity: the column named `EFO ID` is not EFO, and not disease

Real prefixes in that one column, counted over the fixture's 20 distinct
terms: `EFO` (9), `MONDO` (5), `CHEBI` (2), `EXO` (1), `GSSO` (1), `HP` (1),
`NCBITAXON` (1). Over the full dump it also carries `GO:` and `ENVO:`. So:

- **Not one ontology.** `MONDO:0005575` (Colorectal cancer) and
  `EFO:0002755` (Diet) live in the same column.
- **Not all diseases.** `CHEBI:33281` (`Antimicrobial agent`) is a chemical,
  `EXO:0000114` (`Socioeconomic status`) an exposure, `HP:0002745` (`Oral
  leukoplakia`) a phenotype, `GSSO:000707` a social attribute, and
  `NCBITAXON:568703` (`Lactobacillus rhamnosus GG`, on `bsdb:23339708/4/2`)
  is **an organism** — a probiotic used as the exposure. Typing all of them
  `:Disease` puts a *Lactobacillus* strain in the disease list.
- **Both `Condition` and `EFO ID` are comma-multi-valued**, and they do not
  always agree: over the full dump **42 rows** have different comma counts in
  the two columns, so a positional zip is provably wrong for those rows. Worse,
  the id string `MONDO:0024647,MONDO:0008171` appears with condition
  `Nephrolithiasis,Urolithiasis` on one row and `Urolithiasis,Nephrolithiasis`
  on another — the same id order under two label orders, so the zip is not
  merely incomplete, it is *contradictory*.
- **Same id, two labels**: `MONDO:0002009` appears as both
  `Major depressive disorder` and `Unipolar depression`. The id is the key;
  the label is one observed spelling among several.
- **Two ids, near-same condition**: the fixture has `MONDO:0005575`
  (Colorectal cancer, `bsdb:25104642/3/2`) and `MONDO:0024331` (Colorectal
  carcinoma, `bsdb:25432777/2/2`). These are *not* the same term and must not
  be merged by string similarity — but a Part D query for colorectal disease
  has to find both, which is what the ontology's `is_a` forest is for.

Contract: node type is chosen by the id's **prefix**, never by the column
name; the key is the MONDO CURIE where MONDO declares an equivalence and the
source CURIE otherwise; the free-text `Condition` is stored as an observed
label, not as the key; and the label↔id pairing is positional only when the two
columns agree on comma count, otherwise resolved against MONDO's own labels or
reported.

**Resolved (`microbiomekg/conditions.py`).** All 42 mismatched rows turn out to
be one shape — a *single* id whose condition label contains a comma
(`Helminthiasis, animal`, `Osteoarthritis, knee`), i.e. C11's trap in a second
column. 18 are reassembled by matching MONDO's label, 24 by the single-id
identity, 0 lost. `MONDO`/`EFO`/`DOID`/`ORPHANET` become `Disease`, `HP`
becomes `Phenotype`, `CHEBI`/`ENVO`/`EXO`/`GSSO` become `Exposure`, and the
other 13 vocabularies (116 terms, 1,027 mentions) get no node type and go to
the `unresolved_conditions` table on the build result. See `docs/model.md` §1.

Guard: `tests/test_conditions.py` (the whole module),
`tests/test_build.py::test_condition_terms_keep_their_source_vocabulary`,
`::test_non_disease_terms_are_not_disease_nodes`,
`::test_the_phenotype_and_exposure_terms_are_their_own_types`,
`::test_two_colorectal_terms_stay_distinct`,
`::test_multi_condition_row_links_to_both_terms`,
`::test_a_live_mondo_id_keys_its_own_disease_node`,
`::test_terms_with_no_mondo_equivalence_keep_their_own_curie`,
`::test_a_comma_inside_a_condition_label_does_not_mispair`,
`::test_every_condition_mention_is_accounted_for`.

### C15. Paper identity: PMID is not always there, and DOI is not normalised

- **58 rows** in the full dump have `PMID = NA`; the fixture keeps 5, from
  **5 distinct studies** (`Study 11`, `Study 39`, `Study 513`, `Study 562`,
  and the adversarial `Study ADV7`). Keying `:Paper` on PMID alone maps all
  five to one node called `NA` — five different papers merged into one, with
  every edge misattributed. Over the full dump that is **12 distinct studies**
  collapsing into one node.
- **43 rows** have no PMID but *do* have a DOI (`bsdb:513/1/1` →
  `https://doi.org/10.3390/applmicrobiol1020014`).
- `bsdb:11/1/1` has **neither** PMID nor DOI nor URL. Its only identity is
  BugSigDB's own `Study` id, which is therefore the required fallback key.
- **DOIs are not normalised in the source**: bare (`10.3748/wjg.15.2887`),
  full URL (`https://doi.org/10.1186/s13099-022-00527-8`), and DataCite
  (`10.5281/zenodo.7544549`) forms all appear. The same paper reached from
  two sources under two DOI spellings becomes two `:Paper` nodes.

Contract: paper key = PMID if present, else normalised DOI (lowercased, URL
prefix stripped), else `study:<BugSigDB Study id>`. The fixture's 43 rows
yield **39** distinct papers under that rule and **34** under "PMID only,
NA collapses". As built, `:Paper` is keyed on PMID alone: 33 nodes, and the six
PMID-less studies correctly get no paper at all.

Guard: `tests/test_build.py::test_papers_without_pmid_do_not_collapse`,
`::test_doi_forms_are_normalised`.

### C16. Integer id pitfalls in kglite

Measured against kglite 0.16.21, not assumed:

- A pandas column that gains a `NaN` becomes `float64`. Passed as
  `unique_id_field`, kglite coerces whole-number floats back to int (the
  "Float IDs" note in `KGLite/docs/python/guides/blueprints.md`) — **but the
  NaN row itself is skipped**, with `nodes_skipped: 1` and `has_errors: True`
  in the returned dict and a `UserWarning` on stderr. Both are trivially
  ignorable. Nothing raises. This is C18 wearing a different hat: the
  loader's return dict must be read, not discarded.
- On a **property**, the float survives: a `Group 1 sample size` column with
  one `NA` stores `15.0`, and — the part that bites later — **fixes the
  property's schema type to `Float64` for the whole graph**. A subsequent
  load of the same property from a clean `Int64` column fails with
  `Type mismatch for property 'n1': existing schema has 'Float64', but data
  has 'Int64'`. The first CSV loaded wins, forever. Cast sample sizes to a
  nullable `Int64` before the first `add_nodes`.
- kglite stores an integer id as a **compact 32-bit key**, falling back to a
  full 64-bit key when any value is outside `0..2**32-1`. NCBI tax_ids are
  comfortably inside that (the fixture's largest is 2,815,668; NCBI's current
  maximum is ~3.8M), so `tax_id` stays on the fast path — but only while it
  is an *int*. A tax_id that reaches kglite as the **string** `"562"` lands
  in a different key space, and `WHERE t.tax_id = 562` then matches nothing
  while `= "562"` matches — a silent empty result, not an error. Parse the
  last element of every lineage path with `int()` at the edge of the loader.

Guard: `tests/test_build.py::test_tax_ids_are_integers_not_strings`,
`::test_sample_sizes_are_integers_not_floats`,
`::test_missing_sample_size_is_absent_not_the_string_NA`, and — against the
engine directly — `tests/test_loader_contracts.py::test_integer_ids_survive_a_nan_in_the_column`,
`::test_a_nan_pins_a_property_to_float_for_the_whole_graph`,
`::test_a_string_tax_id_does_not_match_an_integer_comparison`.

### C17. Evidence completeness must be countable, not invisible

The A1 contract is that an edge with unknown evidence exists but is
*countable*. Over the fixture's **72** `ASSOCIATED_WITH` edges (55 to a
`Disease`, 3 to a `Phenotype`, 14 to an `Exposure` — one relationship over the
union), the per-field gap census is:

| evidence property | edges lacking it |
|---|---|
| `pmid` | 6 |
| `statistical_test` | 6 |
| `group_1_size` | 5 |
| `sequencing_type` | 5 |
| `study_design` | 3 |
| `group_0_size` | 2 |
| `direction` | 1 |
| `source_relation` | 1 (absent exactly where `direction` is) |
| `evidence_level`, `knowledge_level`, `agent_type`, `primary_source`, `source_record_id`, `source_licence` | 0 (always derived/written) |
| **edges missing at least one** | **16** (22.2%) |

Three things about the instrument, the first two verified against kglite
0.16.21 and the third the 0.16.22 answer to them:

- `CALL ontology_audit()` counts **edges** missing at least one required
  property — so its `violations` column is the union (16), never the sum of
  the column above. Its columns are `rule, severity, violations, exempted,
  total, pct`, plus `domain_class` and `property`, which are Null unless asked
  for.
- `CALL edge_property_violation()` emits **one row per violating edge**. Its
  `property` names the *first* missing property in declaration order — so a
  gap report built from that column alone silently under-counts every field
  but the first — and its `properties` column is the whole failing set, which
  is what to `UNWIND` for a per-field tally.
- **`CALL ontology_audit({by: 'property'})` is the table above, from the
  engine.** One row per *declared* property — the complete ones included, so
  "nothing fails `evidence_level`" is a row rather than an absence. It is a
  **census**: an edge missing `pmid` and `statistical_test` appears in both
  rows, so the rows sum to more than the 16 and never back to it.
  `scripts/build.py` prints it on every build, and D15 is where it is read.

`ontology_audit()` reports **one** `ASSOCIATED_WITH.required_properties` row,
not three: the relation is one relationship over a union range, so the 16 is
the whole of it rather than a sum across three names (C14, docs/model.md §8).

Setting `enforcement: "error"` on the association's `required_properties`
would fail the build on upstream data reality; per KGLite's ontology guide
those stay `warn`. Rules over fields *this repo* writes (`REPORTED_BY`'s
`reported_name` / `resolution_status` / `source`) are legitimately `error` —
a violation there is our bug, not BugSigDB's.

One hole the table hides: `evidence_level` is never absent because the
derivation returns the string `"unknown"` when the design is missing. A
required-property check cannot see it, so "how many edges have an unknown
evidence level" is a `WHERE r.evidence_level = 'unknown'` query, not an audit
row. That is a deliberate choice (never silently "observational"), but it
means the audit's 22.2% is a floor, not the whole gap.

Guard: `tests/test_ontology.py::test_every_evidence_property_is_required_on_associations`,
`::test_evidence_rules_are_not_enforcement_error`,
`tests/test_build.py::test_ontology_audit_counts_the_missing_evidence_edges`,
`::test_edge_property_violation_names_the_evidence_free_row`,
`::test_per_field_evidence_gap_census`,
`::test_audit_denominators_are_not_zero`.

### C18. Silent drops — every input row must be accounted for

The failure mode that hides all the others: a row that resolves to nothing
and leaves no trace. Every row must land in exactly one of three places —
an edge, a record in `unresolved_taxa`, or an explicit, reported filter
count. The three sinks must sum to the input row count.

Concrete leaks in this data:

- `bsdb:19533811/2/NA` (a real row) has `NCBI Taxonomy IDs = NA`,
  `MetaPhlAn taxon names = NA` and `Abundance in Group 1 = NA` — an *empty
  signature*. It contributes zero taxon edges. **621** rows of the full dump
  are like it. That is a legitimate filter, but it must be counted, not
  absorbed.
- The three adversarial rows that must appear in `unresolved_taxa` with
  the stated status: `bsdb:adv-deleted/1/1` (tax 1009, `deleted`),
  `bsdb:adv-ambig/1/1` (`Bacteroides corrodens`, `ambiguous`, candidates
  539 and 827), `bsdb:adv-unknown/1/1` (tax 999999999, `unresolved`).
- kglite's own quiet drops: `add_nodes` / `add_connections` return
  `nodes_skipped` / `has_errors` and emit `UserWarning`s (target node not
  found, null FK, type mismatch) rather than raising. A blueprint build that
  does not read them reports success while dropping edges.
- **The leak these guards actually caught (2026-09-02).** The first
  implementation read only `NCBI Taxonomy IDs` and never fell back to
  `MetaPhlAn taxon names`, so the two name-only adversarial rows lost their
  taxa with no counter anywhere: 72 mentions reported instead of 74, 2
  unresolved records instead of 3, 72 association edges instead of 73. In the
  *current* BugSigDB export the two columns are always `NA` together (621
  rows, both), so nothing in the real data would have exposed it — but it
  means `resolve(name=...)`, the half of the interface that exists for the C4
  rename problem, was dead code, and the next source (HMDB, CARD, KEGG) gives
  names, not tax_ids. Fixed the same day; the adversarial rows are what
  keep it fixed.

`TaxonomyIndex.resolve` never raises — which is right, and is exactly why a
`Resolution` whose status is not `exact`/`synonym`/`merged`/`promoted` must
be written to the unresolved sink by the caller.

Guard: `tests/test_build.py::test_every_taxon_mention_is_accounted_for`,
`::test_adversarial_rows_are_in_the_unresolved_report`,
`::test_ambiguous_record_lists_its_candidates`,
`::test_unresolved_taxa_are_still_joined_to_their_signature`,
`::test_empty_signature_row_exists_but_reports_nothing`,
`::test_name_only_rows_are_resolved_not_ignored`,
`::test_every_input_row_became_a_signature`.

### C19. Golden counts, so "it built" is not the assertion

A build test that asserts `count > 0` passes on a graph that lost 90% of its
rows. The fixture is small enough to state exactly what it must produce.
Every number was derived **twice, independently** — once from
`bugsigdb_mini.csv` + `taxdump_mini/` in the test module's own terms, once by
reading the pipeline's output — and the two agree.

| node type | golden | | relationship | golden |
|---|---|---|---|---|
| `Signature` | **43** | | `HAS_PARENT` | **142** |
| `Study` | **39** | | `REPORTED_BY` | **74** |
| `Paper` | **33** | | `ASSOCIATED_WITH` | **72** |
| `Disease` | **15** | | — of them to a `Disease` | **55** |
| `Phenotype` | **1** | | — to a `Phenotype` | **3** |
| `Exposure` | **4** | | — to an `Exposure` | **14** |
| `BodySite` | **9** | | `IN_CONDITION` | **43** |
| `Taxon` | **143** | | `AT_BODY_SITE` | **45** |
| `UnresolvedTaxon` | **3** | | | |
| | | | `PART_OF_STUDY` | **43** |
| | | | `PUBLISHED_AS` | **34** |

and the derived quantities:

| quantity | golden |
|---|---|
| input rows | **43** (34 real + 9 adversarial) |
| taxon mentions in | **74** |
| taxa some signature named | **53** |
| lineage ancestors carried for `HAS_PARENT` | **90** (143 − 53) |
| unresolved records | **3** |
| condition terms with no node type (ledgered) | **1** |
| typed condition terms with no MONDO equivalence | **14** |
| `ASSOCIATED_WITH` edges, over all three condition types | **72** |
| association edges missing ≥1 evidence field | **16** |

Three of these numbers are where the guards actually bit during this
session's first run against the implementation: `UnresolvedTaxon` was **2**,
`REPORTED_BY` **72** and `ASSOCIATED_WITH` **72**, because the loader read
only the `NCBI Taxonomy IDs` column and ignored the taxon *names* — see C18.

`Taxon` is 143 rather than 53 because the lineage has to stay walkable: the
90 extra nodes are ancestors, and they must carry **no** `REPORTED_BY` and
**no** `ASSOCIATED_WITH` edge (C10). `Paper` is 33 rather than 39 because
six studies have no PMID and correctly get no `:Paper` at all (C15) — and
because the 43rd row reuses an existing PMID, so `PUBLISHED_AS` is 34 against
33 papers. The 20 distinct condition terms split 15 / 1 / 4 across the three
condition types with one ledgered (C14), and the association edges are 72
rather than 73 because the one association to `NCBITAXON:568703` has no
condition node to point at.

Guard: `tests/test_build.py::test_golden_node_counts`,
`::test_golden_edge_counts`, `::test_only_leaf_taxa_are_cited`,
`::test_shortest_path_taxon_to_disease`,
`::test_shortest_path_between_two_co_reported_taxa`,
`::test_taxon_lineage_is_walkable_to_root`.

### C20. The ontology artifact drifts from the ontology module

`blueprint.json` gates the build on a *file*, `ontology.json`; the document
is *edited* in `microbiomekg/ontology.py`. They drifted within a day of both
existing: the checked-in file required `group0_sample_size`,
`group1_sample_size` and `source_id` while the module (and the prep scripts)
had moved to `group_0_size`, `group_1_size` and `signature_id`.

A drifted artifact is worse than no artifact. The gate does not fail loudly —
it audits property names nothing writes, so it reports a violation on
*every* edge for a field that does not exist, while the fields that really
are missing go uncounted. The audit stays green-ish, the number moves, and
nothing says why.

Contract: `ontology.json` is generated (`python -m microbiomekg.ontology`)
and never hand-edited, and a test compares it to the module.

Guard: `tests/test_ontology.py::test_the_checked_in_ontology_json_matches_the_module`.

### C21. Interface gaps this catalog exposes

Recorded here because they are contract changes, not test bugs. **All six are
closed**; the resolution is noted under each.

1. **`Resolution` has no way to say "resolved, but not an organism".** C9's
   placeholder taxa — `uncultured bacterium` (77133), `Bacteroides sp.`
   (29523), `Candidatus Cibiobacter qucibialis` (2500537) — resolve
   *exactly*, yet are not actionable. Nothing in the field set distinguishes
   them from *Escherichia coli*, so Part D queries must re-derive it from the
   name string, which is the string-matching this document argues against.
   **Recommendation: add a boolean (`placeholder`), do not overload
   `status`** — the taxon *is* resolved, and collapsing the two would lose
   the difference between "77133 is a real id" and "the name matched
   nothing". **Done:** `Resolution.placeholder`, set from
   `is_placeholder_name()` on the scientific name of the taxon the resolution
   landed on, and carried onto the `Taxon` node so the exclusion is
   `WHERE NOT t.placeholder`. 1,936 of the 8,078 cited taxa are flagged.
2. **No status for "resolved only after normalisation".** C4's four
   decorated-only cases come back `status="synonym"`, which is true but does
   not record that an authority tail had to be stripped. `note` carries it
   today, and
   `tests/test_reconcile.py::test_decorated_only_synonym_records_the_normalisation`
   pins that, so the audit trail exists — but it is prose, not a field, and
   nothing can aggregate it. **Done:** `Resolution.normalized`, and
   `resolution_normalized` on the `REPORTED_BY` edge.
3. **`rank_ceiling` says nothing about the rank vocabulary.** The 219-node
   fixture alone carries 25 distinct rank strings including `clade`,
   `no rank` and `cellular root`. The *below-ceiling* set has to be
   enumerated explicitly, and belongs in `docs/model.md`: "above species" is
   not a total order over NCBI's rank strings. **Done:**
   `BELOW_SPECIES_RANKS`, 15 rank strings enumerated from the real `nodes.dmp`
   (290,597 of 2,993,228 nodes sit below a species), with `AMBIGUOUS_RANKS`
   naming the two the lineage has to place. Enumerating it found a live bug the
   ladder hid: 83334 `Escherichia coli O157:H7` is `no rank` under a *species*,
   and "below the ceiling" had to become "at or below" for it — and for 190,786
   siblings — to promote at all.
4. **`reported_rank` on the edge is the source's claim, not NCBI's.** Both
   below-species adversarial rows use MetaPhlAn's `t__` prefix, so both land
   as `reported_rank = "strain"` even though 1682 is a `subspecies` in
   `nodes.dmp`. That is defensible — it is what the source said — but it
   means the NCBI rank of a promoted taxon survives only inside the prose of
   `resolution_note` (`"promoted from 1682 (subspecies) to 216816
   (species)"`). A separate `original_rank` column on the edge would make it
   queryable. **Done:** `REPORTED_BY` carries `reported_rank` (the source's
   claim) and `original_rank` (NCBI's) as two properties. They disagree on 170
   of the 114,742 real mentions — 151 where MetaPhlAn says `species` and NCBI
   says `subspecies`.
5. **`ONTOLOGY` does not name its association relationships.**
   `tests/test_ontology.py` has to *infer* which relationships carry the
   evidence contract (it takes those requiring both a direction and a study
   design) so it can hold them to `warn` while letting this repo's own
   `REPORTED_BY` sit at `error`. An explicit `ASSOCIATION_RELATIONSHIPS`
   tuple would turn a heuristic into a declaration. **Done:**
   `microbiomekg.ontology.ASSOCIATION_RELATIONSHIPS`, which the tests now
   assert against instead of inferring from.
6. **`CALL edge_property_violation()` under-reports.** One row per violating
   edge, naming only the first missing property — see C17. Anything that
   needed a per-field gap census had to use Cypher instead, and a reader who
   assumed otherwise reported a confidently wrong breakdown. **Done, by
   kglite 0.16.22, in both of the two shapes this wanted.** The procedure
   yields a `properties` column carrying the whole failing set (`property` is
   now defined as the first of it, so the row identity is unchanged), and
   `CALL ontology_audit({by: 'property'})` fans a `required_properties` rule
   into one row per *declared* property — including the ones nothing fails, so
   a complete field is visible as complete rather than as an absence. D15 uses
   both and `scripts/build.py` prints the census on every build. The one
   caveat is in the name: it is a **census**, so an edge missing two fields is
   counted twice and the rows do not sum back to the rule's violations.

## Part D — Acceptance queries

The final list. Ordering is the research document's §5 (Q1–Q15), which is
ordered by how commonly the question appears as the stated purpose of a source
database or the entry point of a published workflow; **D1–D15 correspond
one-to-one with Q1–Q15**. D16–D18 are the Part A5 query types and the guard
queries that §5 implies but does not number; D19–D20 are the two things this
graph deliberately does not do. Nothing announced in A5 is lost: A5.1 = D2,
A5.2 = D5, A5.3 = D16, A5.4 = D1 + D10, A5.5 = D6.

**How to read the Cypher.** Node keys are addressed as `{id: …}` (the
blueprint `pk` value) and node titles as `.title`. Queries against loaded data
use `docs/model.md`'s names as they stand in `blueprint.json` today — including
the three post-model.md changes the loader has since made: `Disease` is keyed on
its MONDO CURIE where MONDO declares an equivalence, non-disease conditions have
moved to `Phenotype` / `Exposure` — reached by the *same* `ASSOCIATED_WITH` and
`IN_CONDITION` relationships, over a union range, so a disease-only query says
`->(:Disease)` — and the evidence contract's `source` /
`signature_id` are now `primary_source` / `source_record_id` alongside
`knowledge_level`, `agent_type`, `source_licence` and `source_relation`.
Queries marked `pending: <source>` are written against the node and edge names
proposed in `docs/research/source-formats.md`'s extraction tables; where that
document has no table yet (MiMeDB, NJC19, MASI) the names are proposed here and
are the loader's contract.

Measurements quoted as "measured" were taken on 2026-09-03 from a clean
`scripts/build.py` run over **eleven** sources — BugSigDB (`full_dump`
2026-09-02), gutMDisorder v1, CARD 4.0.2, HMDB 5.0, Reactome (2026-09-02),
ChEMBL 37, MiMeDB v2.0 (dumped 2025-10-08), NJC19 (Sci Data 7:204, 2020), the
two published drug screens, Maier 2018 (Nature 555:623) and Zimmermann 2019
(Nature 570:462), and MASI v1.0 (NAR 49:D776, 2021) — against NCBI
`new_taxdump` 2026-09-02 at `--scope microbial`. **934,206 nodes, 1,324,684
edges.** KEGG is licence-gated and **not** in any number here: a default build
carries none of it. Where a later source moved a number the earlier value is kept beside it: a
golden that moves when a source lands is the expected outcome, and the pair is
what says by how much. `tests/test_acceptance.py` runs every `answerable-now`
and `partial` query below and asserts these numbers.

---

### D1 — "Which published signatures does my hit list overlap, for which condition, at which body site, and in which direction?"

*Status:* **`answerable-now`**. *Fields:* signature membership as NCBI tax_ids ·
`Signature.direction` · `IN_CONDITION` · `AT_BODY_SITE` · `Signature.host_species`
· `sequencing_type` · `variable_region` · `group_0_size` / `group_1_size` · `pmid`.

```cypher
UNWIND [821, 851, 1263, 40520, 239935, 33038] AS tid
MATCH (t:Taxon {id: tid})-[:REPORTED_BY]->(s:Signature)
WHERE s.direction = 'increased'
MATCH (s)-[:IN_CONDITION]->(d:Disease)
OPTIONAL MATCH (s)-[:AT_BODY_SITE]->(b:BodySite)
WITH s, d, b, count(DISTINCT t) AS overlap
WHERE overlap >= 2
RETURN d.title AS condition, b.title AS body_site, s.id AS signature,
       overlap, s.n_taxa AS signature_size,
       s.sequencing_type AS assay, s.variable_region AS region,
       s.host_species AS host, s.group_0_size AS n0, s.group_1_size AS n1,
       s.pmid AS pmid, s.evidence_level AS level
ORDER BY overlap DESC, signature_size ASC LIMIT 25
```

*Shape:* one row per overlapping signature, with the overlap count, the
signature's own size (the enrichment denominator) and enough metadata to
down-weight it. **This is the query the model was reshaped for: it is answerable
precisely because `Signature` is a node.** A flattened
`(Taxon)-[:ASSOCIATED_WITH]->(Disease)` model destroys the set and makes
enrichment impossible — the research document's only structural finding about
the shape of the graph rather than the choice of sources. The enrichment
*statistic* (ORA / PADOG / CBEA) runs outside the graph; the graph serves the
sets. *Golden check:* every returned signature's `signature_size` equals its
`REPORTED_BY` degree, and `overlap <= signature_size`.

### D2 — "What is reported for taxon X in disease Y, and how strong is each report?"

*Status:* **`answerable-now`**. This is A5.1 and Part A's A1 acceptance
sentence. *Fields:* the full ten-field evidence contract plus its four
provenance companions.

```cypher
MATCH (t:Taxon {id: 851})-[r:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0005575'})
RETURN r.direction AS direction, r.evidence_level AS level,
       r.study_design AS design, r.sequencing_type AS assay,
       r.group_0_size AS n_control, r.group_1_size AS n_case,
       r.statistical_test AS test, r.significance_threshold AS alpha,
       r.mht_correction AS mht, r.pmid AS pmid,
       r.study_id AS study, r.source_record_id AS signature,
       r.knowledge_level AS knowledge_level, r.agent_type AS agent_type,
       r.primary_source AS source, r.source_licence AS licence
ORDER BY level, study
```

*Shape:* one row per signature — never one aggregated row per pair. *Golden
check (measured, and **unchanged by gutMDisorder**, which curates no
*F. nucleatum* result for colorectal cancer at all):* **taxon 851
(*Fusobacterium nucleatum*) × `MONDO:0005575`
(colorectal cancer) returns 40 rows across 21 distinct `study_id`s — 39
`increased` from 20 of them, and one `decreased` from `bsdb:41270896`.** The
increased-direction requirement of "more than one study" is met twenty times
over; the single dissenting edge is not removed, and D17 is where it is
reported. If this returns one row, C13's parallel-edge collapse has recurred —
the chunk-boundary dedupe kglite 0.16.22 fixed, which this build no longer
overrides.

### D3 — "Which taxa are reported in more than one disease, and in which direction?"

*Status:* **`answerable-now`** for the single-source form. *Fields:* D2's,
aggregated per taxon across conditions, over a normalised disease key.

```cypher
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
WHERE t.placeholder = false
WITH t, count(DISTINCT d.id) AS n_conditions,
     count(DISTINCT r.study_id) AS n_studies,
     collect(DISTINCT d.title) AS conditions,
     collect(DISTINCT r.direction) AS directions
WHERE n_conditions > 1
RETURN t.title AS taxon, t.rank AS rank, n_conditions, n_studies,
       conditions AS reported_in, directions
ORDER BY n_conditions DESC LIMIT 25
```

*Golden check (measured):* **3,821 of 7,753 taxa carrying an
`ASSOCIATED_WITH` edge appear in more than one condition — 49.3%** (BugSigDB
alone: 3,799 of 7,718, 49.2%), within two points of Duvallet et al.'s published
51% of genus-level associations being associated with more than one disease.
The fraction barely moved because gutMDisorder's 622 cited taxa are mostly ones
BugSigDB already names — **556 of them, 89%** — which is the join working, not
a coincidence. A build that returns a materially lower
fraction is under-loaded. *Caveat that is part of the answer, not a defect:*
Crohn's and ulcerative colitis separate at 95.1% specificity on an eight-genus
signature, so the query must never roll conditions up silently — `Disease.mondo_id`
and the MONDO `IS_A` forest (`pending: MONDO`) are how a caller asks for
"colorectal disease" deliberately, which is also the only way D2's
`MONDO:0005575` and `MONDO:0024331` are found together (C14).

### D4 — "Which associations are supported by more than observational abundance — animal model, intervention, or human RCT?"

*Status:* **`answerable-now`** (was `partial`; the intervention leg landed with
gutMDisorder on 2026-09-03). *Fields:* `evidence_level` · `host_species` ·
`study_design`, and for the second leg the `ABUNDANCE_CHANGED_BY` edge.

```cypher
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
WHERE r.evidence_level IN ['interventional-rct', 'meta-analysis',
                           'in-vitro', 'in-vivo-model']
WITH d, t, r.evidence_level AS level, r.direction AS direction,
     r.host_species AS host, count(DISTINCT r.study_id) AS studies
RETURN d.title AS disease, t.title AS taxon, level, direction, host, studies
ORDER BY CASE level WHEN 'interventional-rct' THEN 0
                    WHEN 'meta-analysis'      THEN 1
                    WHEN 'in-vitro'           THEN 2
                    ELSE 3 END,
         studies DESC
LIMIT 30
```

*Golden check (measured):* the four tiers are non-empty — `in-vivo-model`
17,858 edges, `observational-shotgun` 16,463, `meta-analysis` 4,297,
`interventional-rct` 4,247, `in-vitro` 1,613 of 105,097. **G6 is enforced by the
`ORDER BY`:** `in-vivo-model` sorts last, below every human tier, because 95% of
published HMA-rodent studies report phenotype transfer and that rate is not
evidence.

*The second leg, which is what needed the second source:*

```cypher
MATCH (t:Taxon)-[r:ABUNDANCE_CHANGED_BY]->(i:Intervention)
RETURN i.title AS intervention, i.drugbank_id AS drugbank, t.title AS taxon,
       r.direction AS direction, r.evidence_level AS level,
       r.host_species AS host, r.p_value AS p, r.pmid AS pmid
ORDER BY level, intervention
```

*Golden check (measured):* **1,380 edges over 220 interventions and 395 taxa**,
all from gutMDisorder, split `in-vivo-model` 822 / `interventional-rct` 558 —
because its whole mouse workbook lands as `in-vivo-model` regardless of design
(G6), and 168 of its 190 mouse studies are interventions. It is deliberately
**not** an `ASSOCIATED_WITH`: "this drug changed this taxon" and "this taxon is
associated with this disease" are different claims with different directions,
and collapsing them is MDAD's documented weakness. Only 220 of gutMDisorder's
930 mouse association rows have a DOID at all, so most mouse edges are this
relation rather than a disease association — 389 of its 3,193 rows reach
neither and sit in `unresolved_associations` with that reason.

### D5 — "Which metabolites does taxon X produce, and is that measured or predicted?" (and the reverse: which taxa produce metabolite M?)

*Status:* **`partial`** (was `pending-source: MiMeDB`), and **not because
MiMeDB landed.** No MiMeDB bulk download carries a microbe–metabolite
association — v1.0 and v2.0 alike — so the source fetched to close this query
contributes **zero** edges to it; what moved it is **NJC19's export half**,
fetched for D6.
This is A5.2. *Fields:* production direction · evidence tier · pathway/gene ·
rank at which the claim holds · citation · replication count.

```cypher
// Two sources in one table: HMDB's 578 ontology annotations and NJC19's 2,840
// curated export events. `primary_source` is what tells them apart.
MATCH (t:Taxon {id: 239935})-[p:PRODUCES]->(m:Metabolite)
RETURN m.title AS metabolite, m.chebi_id AS chebi, m.status AS hmdb_status,
       p.evidence_level AS level, p.knowledge_level AS knowledge_level,
       p.reported_name AS organism_as_named, p.genus_level_evidence AS genus_only,
       p.publications AS refs, p.primary_source AS source
ORDER BY level, metabolite
```

`m.status` is HMDB's own quantification status and `p.enzyme` does not exist:
**neither source carries an enzyme**, which is what D13 is `partial` about.

```cypher
// the reverse (A5.2's second half): who makes butyrate?
// CHEBI:30772 is butyric *acid*, which is what HMDB's record carries. See the
// key note below: CHEBI:17968 is the conjugate base and matches nothing here.
MATCH (t:Taxon)-[p:PRODUCES]->(m:Metabolite {id: 'CHEBI:30772'})
WHERE t.placeholder = false
RETURN t.title AS producer, t.rank AS rank, p.evidence_level AS level,
       count(DISTINCT p.source_record_id) AS n_records
ORDER BY level, n_records DESC
```

*Golden check (measured 2026-09-03, ten sources):* **3,418 `PRODUCES` edges
over 830 organisms and 226 metabolites**, `in-vitro` 3,383 /
`computational-predicted` 35 — split **HMDB 578 / 272 organisms / 154
metabolites** and **NJC19 2,840 / 638 / 99**. `computational-predicted` is
HMDB's and only HMDB's: NJC19's inclusion criterion is an experimentally
verified event, so a predicted NJC19 edge would be a value nothing in that
source could justify. The reverse query returns **109 butyrate producers, all
`in-vitro`** (was six, all HMDB's), and it returns them on **one node** only
because NJC19's `Butyrate` reaches HMDB's `Butyric acid` through the conjugate
route — had it not, 103 producers would sit on a `NJC19:Butyrate` node nobody
queries.

**Two statements in this entry the data has now overturned, both recorded rather
than quietly edited.**

*(a) "Akkermansia muciniphila has no answer."* This entry said the taxon its own
forward query names had **zero** rows, "this query's `pending-source` status as a
number rather than a label". It has **four** now — acetic acid, ethanol,
propionic acid, sulfate — and every one is NJC19's. HMDB still attributes
nothing to it. The label was right about the gap and wrong about which source
would close it.

*(b) "The replication count is 1 for every pair."* It reaches **3**, on 43
pairs, and both causes are correct behaviour rather than double-counting: HMDB
and NJC19 independently curate the same production (29 pairs — the first
cross-source corroboration this relationship has ever had), and several NJC19
species strings promote onto one NCBI species (*Thermoanaerobacter
thermohydrosulfuricus*, *T. indiensis* and *T. ethanolicus* are three curated
rows under one node, with all three strings kept in `reported_name`). What
*would* be double-counting — a pair carrying more records than distinct (source,
organism string, compound string) triples — is asserted absent.

**The key in the reverse query is a contract statement the data made
untenable.** It addressed butyrate as `CHEBI:17968`, the conjugate base; HMDB's
butyric acid record carries `chebi_id` **30772**, the acid, and ChEBI holds
those as two terms. `Metabolite` is keyed on HMDB's own `chebi_id`, so the
acid/base distinction survives as two identities and the query as first written
returned **nothing at all** — which looks exactly like "no source has this".

**And the taxon the forward query names has no answer.** *Akkermansia
muciniphila* (239935) is in the graph and HMDB attributes **no** metabolite to
it: zero rows, on the source that is supposed to answer half of D5. That is
this query's `pending-source` status as a number rather than a label.

*Shape:* one row per (taxon, metabolite, source record). *Expected size:*
HMDB's microbial branch is **224 metabolites, 0.10% of the file**, keyed on
free-text, misspelled, mixed-rank organism names with **no taxid** — 169
"genus"-level terms that include phyla, a class, six families, two Gram stains
and a U+FB01 ligature typo; the misspellings (`Citrobacter frundii`,
`Akkermansia muciniphilia`) land in `UnresolvedTaxon`, which is the correct
outcome, not a loss. NJC19's export half is species-level and five times larger,
and its own losses are 15 renamed organisms and 6 host cell types, all
countable.

*What is still missing, and why the status is `partial` rather than
`answerable-now`.* Neither source carries the **pathway or gene** the claim runs
through — that is D13's leg, and it is `partial` for the same reason.

**The blocker is no longer a pending fetch.** This entry used to name MiMeDB's
v2.0 reaction table — Precursor, Product, Enzyme, Enzyme's source organism,
Reaction type, References — as the thing that would supply it. **v2.0 has since
been fetched, on 2026-09-03, and does not contain it.** Both of its bulk files
are one MySQL table with no join to the other, exactly as v1.0's were, measured
the same way and recorded in `data/raw/mimedb/v2/PROVENANCE.md`. What v2.0 added
is a `microbe_relations` **count** — 830,984 pairs tallied, none named — so the
association provably exists upstream and is published in no file. The remaining
routes are the site's per-metabolite and per-microbe web exports, which are
interactive pages behind a Cloudflare challenge, and this project does not
scrape.

So the honest statement of D5's gap is: **no bulk source publishes per-taxon
production pairs at scale, and NJC19's export half is what this graph has.**
That is not a smaller gap than before — it is the same gap with the candidate
that was supposed to fill it eliminated. The status stays `partial` and does not
improve. If a curated reaction layer ever does arrive, its 23.1M
BLAST-propagated pathways are `computational-predicted` and must stay in a
separate layer from the 25,276 curated reactions.

*Required qualifier:* the answer carries a replication count. Its expected value
was **1** and is now up to **3** — see (b) above; the reasons are cross-source
corroboration and species promotion, not double-counting. *Why the tier is not
optional:* gutSMASH measured metabolite levels to be "almost completely
uncorrelated" with the abundance of the corresponding genes across 1,135
individuals.

### D6 — "Which taxa consume metabolite M?" — the cross-feeding query

*Status:* **`answerable-now`** (was `pending-source: NJC19`; the source landed
2026-09-03). This is Part A's use case 5, and it was **not** descoped — Part A
understated the gap (no source in the profiled seven carries consumption, not
just HMDB, and MiMeDB keys origin on compounds appearing as a *product*, so it
would not have filled it even had its association table been downloadable).
*Fields:* a `CONSUMES` edge with an evidence tier and a rank.

```cypher
MATCH (m:Metabolite)
OPTIONAL MATCH (p:Taxon)-[:PRODUCES]->(m) WHERE p.placeholder = false
OPTIONAL MATCH (c:Taxon)-[:CONSUMES]->(m) WHERE c.placeholder = false
WITH m, count(DISTINCT p) AS producers, count(DISTINCT c) AS consumers
RETURN m.title AS metabolite, producers, consumers,
       CASE WHEN producers + consumers = 0 THEN 0.0
            ELSE 2.0 * producers * consumers / (producers + consumers)
       END AS mes
ORDER BY mes DESC LIMIT 20
```

```cypher
// the degradation half, which is a different claim and a different edge type
MATCH (t:Taxon)-[d:DEGRADES]->(m:Metabolite)
RETURN m.title AS macromolecule, count(DISTINCT t) AS degraders
ORDER BY degraders DESC
```

```cypher
// and the refutations, which are countable rather than absent
MATCH (t:Taxon)-[n:NO_EXCHANGE_WITH]->(m:Metabolite)
RETURN n.source_relation AS refuted, count(n) AS n ORDER BY n DESC
```

**Metabolite Exchange Score: MES = 2·P·C / (P + C)** — the harmonic mean of the
number of potential producers P and consumers C, and **MES = 0 when a metabolite
is only produced or only consumed** (Marcelino et al., Nat Commun 14:6546,
2023). That identity was the whole argument, and it is why the before/after is a
binary rather than a ratio: every row of this query returned 0.0 until NJC19
landed.

*Golden check (measured 2026-09-03):* **4,784 `CONSUMES` edges over 714 taxa and
205 metabolites**, plus **387 `DEGRADES`** over 212 taxa and 17 macromolecules
and **894 `NO_EXCHANGE_WITH`**. **96 metabolites carry both a producer and a
consumer**, so 96 rows have a non-zero MES. The stated golden — "acetate, the
most frequently exported product (44.3% of NJC19's species), must have both a
non-zero producer and a non-zero consumer count" — holds: **441 producers, 72
consumers**, MES 123.8, second only to CO2. The top of the ranking is what a gut
cross-feeding network is supposed to look like: CO2, acetate, hydrogen, lactate,
formate, ammonia, ethanol, succinate, butyrate, propionate.

**The golden held only because of a join, and the join is the fragile part.**
HMDB records `Acetic acid` (CHEBI:15366) and `Butyric acid` (CHEBI:30772); NJC19
says `Acetate` and `Butyrate`, and carries **no ChEBI, HMDB, KEGG or PubChem id
for any of its 283 compounds**. Without the `-ate` ↔ `-ic acid` conjugate step
the consumers land on freshly minted nodes, the producers stay on HMDB's, and
MES is 0 for both halves of every short-chain fatty acid — the same trap D5's
"key note" recorded for CHEBI:17968 vs CHEBI:30772, arriving from the other
side. `metabolite_join` on every edge records which spelling matched, so a
conjugate match is countable rather than assumed.

**And where the graph genuinely holds a conjugate pair as two nodes, it still
does.** `Formate` reaches CHEBI:15740 because a node is spelled exactly that,
while HMDB's 10 formate producers sit on `Formic acid` (CHEBI:30751), so each
node carries a partial picture. The source's own spelling is tried before any
derivation on purpose: ChEBI holds the acid and the base as two terms, this
graph keys `Metabolite` on ChEBI, and silently merging them would be an identity
claim the project has not made. A consumer computing MES over a conjugate pair
has to say which term they mean, exactly as D5's reverse query does.

*The loader contract as it actually landed*, against what this entry proposed:
`(Taxon)-[:PRODUCES|CONSUMES]->(Metabolite)` was proposed with `source_relation
∈ {export, import, degrade}`; degradation became its own relationship
`DEGRADES`, because a blueprint junction entry names one relationship per CSV
per target type (docs/model.md §8) and because extracellular breakdown of a
polymer is a different claim about a community from uptake of a small molecule.
`source_relation` carries the source's own word on every edge regardless, so the
proposed filter still works. `primary_source = "njc19"`, `source_licence =
"CC0-1.0"`, `knowledge_level = "knowledge_assertion"`, `agent_type =
"manual_agent"`, `evidence_level = "in-vitro"` all landed as proposed. The **912
negatives as their own edge type** landed as `NO_EXCHANGE_WITH` as proposed —
**894 of the 912**, with `source_relation` naming the refuted activity
(`import-negative` 720, `degrade-negative` 87, `export-negative` 87); the other
18 sit on rows whose organism is one of NJC19's six host cell types or a taxon
NCBI has renamed, and each is a ledger row in `unresolved_exchange` rather
than a loss.

**One field this entry did not ask for and the data forced.** 2,426 of NJC19's
9,136 rows (26.6%) stand on nothing but `(G)`-marked references — a species-filed
row whose entire literature basis was read at genus level, per the sheet's own
legend. Loading those verbatim presents a genus-level observation as a
species-level fact, which is what guard **G5** exists to stop, so
`genus_level_evidence` is a boolean on every NJC19 edge and one `WHERE` clause
separates the 2,432 genus-backed edges from the 6,473 that are not.

### D7 — "Which AMR genes does taxon X carry, to which drug class, by which mechanism, and at what call confidence?"

*Status:* **`answerable-now`** (was `pending-source: CARD`; the source landed
2026-09-03). *Fields:* ARO id · detection model type · drug class · resistance
mechanism · what the taxon edge actually claims. **The one field in the original
list that is not here is the RGI hit category, and it cannot be:** Perfect /
Strict / Loose is produced by *running* RGI against a sample, so it is a
per-sample output and no CARD download carries it. It is not written as an empty
placeholder; `taxon_specificity` carries the call-confidence information CARD
*does* have, on every carriage edge.

```cypher
MATCH (t:Taxon {id: 562})-[c:CARRIES_RESISTANCE_GENE]->(g:ResistanceGene)
OPTIONAL MATCH (g)-[:CONFERS_RESISTANCE_TO]->(dc:DrugClass)
OPTIONAL MATCH (g)-[:VIA_MECHANISM]->(m:ResistanceMechanism)
RETURN g.title AS determinant, g.id AS aro, m.title AS mechanism,
       dc.title AS drug_class, c.model_type AS model_type,
       c.sequence_derived AS from_reference_sequence,
       c.taxon_specificity AS taxon_specificity,
       c.evidence_level AS level, c.knowledge_level AS knowledge,
       c.primary_source AS source, c.source_licence AS licence
ORDER BY drug_class, determinant
```

**Three names differ from the extraction table this query was first written
against, and each difference is a fact about the data rather than a
preference.** `AROTerm` is `ResistanceGene` and `CARRIES_DETERMINANT` is
`CARRIES_RESISTANCE_GENE`, because the node is one CARD *model* and
`model_type` is the thing W6 asks for. The resistance mechanism is a
`ResistanceMechanism` node behind `VIA_MECHANISM` rather than a string
property, because a model may carry two of them — `MexR` is `antibiotic efflux`
**and** `antibiotic target alteration` — which one property cannot hold.

*Golden check (measured over CARD 4.0.2, `_timestamp` 2026-08-11):* **6,451
`ResistanceGene`s, 50 `DrugClass`es and 8 `ResistanceMechanism`s**, joined by
**6,415 `CARRIES_RESISTANCE_GENE`, 13,691 `CONFERS_RESISTANCE_TO` and 6,513
`VIA_MECHANISM`** edges, with **539 taxa** carrying a determinant. The query
above returns **1,535 rows for *E. coli*: 646 determinants, 31 drug classes,
7 mechanisms**, every row `sequence_derived = true` and every row carrying its
licence and model type. `protein variant model` is among them, which is W6's
"detection model type" requirement populated rather than declared.

*Four conditions the loader had to satisfy, all from the source profile, all
met:* models are keyed on `Model ID` (6,463 unique — `ARO Accession` is
duplicated on 5 rows of `aro_index.tsv`, and keying on it silently drops half
of each pair); `card.json` is the model authority, not `aro_index.tsv` (they
disagree on 84 models, and the disagreements are a ledger rather than a silent
resolution); the licence rides **per edge** (`CC-BY-4.0` for `aro.obo`,
`CARD-noncommercial` for `card-data/`); and `card-ontology/ncbi_taxonomy.obo`
is never a source of taxon labels — it renames `NCBITaxon:2` to CARD's own
editorial string, and taxid 2 in this graph is `Bacteria`.

*The claim the edge makes, stated on the edge, and each caveat now a count:*
`sequence_derived = true` means the taxid is the **reference sequence's**
organism — "this sequence was cloned from this organism", not "this organism is
resistant". **132 carriage edges are keyed on taxid 2 (Bacteria) alone, 264 are
above species rank in total, and 18 point at something that is not an organism**
(plasmids, a transposon, a synthetic construct); all are kept, flagged by
`taxon_specificity`, and excludable with one clause. Gene presence is not
phenotype: even a Perfect RGI hit "does not indicate if the AMR gene is
expressed or if it results in elevated MIC", while AMRFinderPlus and ResFinder
score 54–58% balanced accuracy against measured resistance. **The predicted
layer is 104 of the 13,691 `CONFERS_RESISTANCE_TO` edges** — the 36 meta-models
with no reference sequence — carrying `evidence_level =
'computational-predicted'`, so a "276k AMR links" figure sourced from CARD
Prevalence would be excluded by one `WHERE`. *And the licence finding, which is
not a rounding error:* only **42 of 13,691** drug-class edges are `CC-BY-4.0`,
because `aro.obo` names every term but states only 37 models' drug classes — so
D7's answer lives in the non-redistributable half of the download.

### D8 — "Does drug D inhibit gut bacteria, or get metabolised by them, and which strains?"

*Status:* **`answerable-now`** — both halves of the question the query is named
for, each from the published screen that measured it, each as its own pair of
edge types. *Fields:* drug id · taxon · assay and readout · direction,
**including no-effect** · the route the claim travelled.

**Leg 3 — the drug inhibits the bacterium, measured (Maier 2018).** The leg D8
was written for.

```cypher
MATCH (d:Drug)-[r:INHIBITS_GROWTH_OF]->(t:Taxon)
WHERE r.drug_class = 'human-targeted drugs'
RETURN d.title AS drug, t.title AS organism, r.nt_code AS isolate,
       r.strain AS strain, r.adjusted_p_value AS adjusted_p,
       r.screen_concentration_um AS screened_at_um,
       r.ic25_um AS ic25_um, r.ic25_qualifier AS ic25_qualifier,
       r.validation_outcome AS validation,
       r.evidence_level AS level, r.drug_join AS join_route,
       r.source_licence AS licence
ORDER BY organism, drug
```

*Golden check (measured over the published screen):* **5,592
`INHIBITS_GROWTH_OF` edges over 399 drugs and 38 taxa** — 287 of the 399
approved — and **42,233 `DOES_NOT_INHIBIT_GROWTH_OF` edges**, one per measured
non-hit. All 1,197 library entries reach the graph, as 1,197 distinct `Drug`
nodes. The paper's own headline reproduces from the loaded edges: **203 of 835
human-targeted drugs = 24.3%** inhibit at least one strain, against the
abstract's "24% of the drugs with human targets".

**The negative is a first-class query, and it is the reason this leg is worth
having:**

```cypher
// "Has anyone tested this drug against this bug, and what happened?"
// Three outcomes, and the third is not silence.
MATCH (d:Drug {pref_name: 'METFORMIN'})
OPTIONAL MATCH (d)-[hit:INHIBITS_GROWTH_OF]->(t:Taxon)
OPTIONAL MATCH (d)-[miss:DOES_NOT_INHIBIT_GROWTH_OF]->(u:Taxon)
RETURN count(DISTINCT t) AS inhibited,
       count(DISTINCT u) AS tested_no_effect,
       'anything else was never tested' AS caveat
```

*Golden check:* metformin returns **0 inhibited, 38 tested-no-effect**. Before
this source the same question returned nothing, and nothing was
indistinguishable from "tested and clean".

**Leg 1 — the drug acts on a bacterial protein (ChEMBL).** Unchanged: **95
drugs reach 28 bacterial taxa through 1,493 `OF_ORGANISM` edges over 94 target
organisms; 65 of the 95 are approved.** A different claim from leg 3 — for 28
mostly-pathogen taxa this is an antibacterial's target, not a gut-commensal
effect — and it is a two-hop path through `ProteinTarget`, never a `Drug`–`Taxon`
shortcut. `tests/test_acceptance.py` asserts that **every** direct
`Drug`–`Taxon` edge in the graph is one of Maier's two types, which is the
restatement of the guard that used to assert there were none.

```cypher
MATCH (d:Drug)-[m:HAS_MECHANISM]->(p:ProteinTarget)-[:OF_ORGANISM]->(t:Taxon)
WHERE t.lineage_domain = 'Bacteria'
RETURN d.title AS drug, d.approved AS approved, p.title AS target,
       p.uniprot AS uniprot, t.title AS organism, m.action_type AS action,
       m.evidence_level AS level, m.source_licence AS licence
ORDER BY organism, drug
```

**Leg 2 — the drug changed a taxon's abundance in a host (gutMDisorder, joined
to ChEMBL by name).** Unchanged: **85 edges over 15 drugs and 57 taxa**, the
join being an exact casefolded whole-label name match, 15 of 222 interventions.

```cypher
MATCH (t:Taxon)-[r:ABUNDANCE_CHANGED_BY]->(i:Intervention)-[:IS_DRUG]->(d:Drug)
RETURN d.title AS drug, i.title AS intervention, t.title AS taxon,
       r.direction AS direction, r.evidence_level AS level,
       r.host_species AS host, r.pmid AS pmid
ORDER BY drug, taxon
```

**Four legs, four different claims, and they are not interchangeable.** Leg 1
says a drug binds a protein this organism has; leg 2 says a drug changed this
taxon's abundance in a patient or a mouse; leg 3 says a drug did or did not stop
this isolate growing in a tube; leg 4 says this isolate did or did not chemically
destroy the drug. An abundance shift with no growth inhibition is an argument
for an indirect mechanism, and a drug that is metabolised but does not inhibit
is an argument about bioavailability rather than about the microbiome's
composition. The graph can now state all four for the same taxon.

**Leg 4 — the bacterium metabolises the drug, measured (Zimmermann 2019).**
The clause D8 was written with and could not answer until now.

```cypher
MATCH (t:Taxon)-[r:METABOLISES]->(d:Drug)
RETURN t.title AS organism, r.strain AS strain, d.title AS drug,
       r.percent_consumed AS percent_consumed,
       r.drug_threshold_percent AS threshold_for_this_drug,
       r.fdr_p_value AS fdr_p, r.incubation_hours AS hours, r.replicates AS n,
       r.gene_locus_tags AS genes, r.therapeutic_indication AS indication,
       r.evidence_level AS level, r.drug_join AS join_route,
       r.source_licence AS licence
ORDER BY organism, drug
```

*Golden check (measured over the published screen):* **2,575 `METABOLISES`
edges over 172 drugs and 66 taxa** — 147 of the 172 approved — and **17,479
`DOES_NOT_METABOLISE` edges**, one per measured non-hit. All 271 screened
compounds reach the graph, 248 of them by joining a `Drug` node that already
existed and 23 minted. The screen's own headline reproduces from the loaded
edges with one documented subtraction: **176 of 271 drugs are metabolised by at
least one of the 76 strains, and the graph says 172**, because the four missing
ones — `ALPRENOLOL`, `DIPHENYLPYRALINE`, `IRSOGLADINE MALEATE` and `MEMANTINE`
— are metabolised **only** by *Bifidobacterium ruminatum*, one of the two strain
names this loader deliberately refuses to guess at (below). Four drugs is the
priced cost of that refusal, and it is a number rather than a shrug.

**The direction is the model.** These edges run `Taxon → Drug`; Maier's run
`Drug → Taxon`. The agent is on the tail of both, which is what keeps
`MATCH (d:Drug)-[r]->(t:Taxon)` meaning *the growth screen and nothing else* —
`tests/test_acceptance.py` asserts that, and it is only true because this source
points the other way. Collapsing the two into one relationship with a flag is
what Part D forbade in advance, because it conflates antimicrobial killing with
drug metabolism.

**The two screens overlap, and the overlap is the interesting part:** **195 of
the drugs and 26 of the taxa are in both**, so for those pairs the graph can say
whether a drug both fails to kill an organism *and* is destroyed by it — 28
drugs inhibit at least one taxon and are metabolised by at least one.

```cypher
// "What does the gut do to this drug, and what does it do to the gut?"
// Four outcomes, and two of them are measured negatives.
MATCH (d:Drug {pref_name: 'SULFASALAZINE'})
OPTIONAL MATCH (t:Taxon)-[:METABOLISES]->(d)
OPTIONAL MATCH (u:Taxon)-[:DOES_NOT_METABOLISE]->(d)
OPTIONAL MATCH (d)-[:INHIBITS_GROWTH_OF]->(v:Taxon)
OPTIONAL MATCH (d)-[:DOES_NOT_INHIBIT_GROWTH_OF]->(w:Taxon)
RETURN count(DISTINCT t) AS metabolised_by, count(DISTINCT u) AS tested_untouched,
       count(DISTINCT v) AS inhibits, count(DISTINCT w) AS tested_no_inhibition,
       'anything else was never tested, in either screen' AS caveat
```

*Golden check:* sulfasalazine returns **52 metabolised_by and 14
tested_untouched**. Before this source the first two columns were empty for
every drug in the graph, and empty was indistinguishable from "tested, nothing
happened".

**A measured negative is bounded by its assay, and here is the case that proves
it.** *Eggerthella lenta* reducing digoxin is the textbook drug-metabolism
result, and **this screen measured that pair and scored it a non-hit** — 4.0%
consumed against the drug's 20% threshold, FDR p = 0.55, so the graph holds
`(Eggerthella lenta)-[:DOES_NOT_METABOLISE]->(DIGOXIN)`. That is not a
refutation of the literature: digoxin reduction needs the *cgr* operon expressed
under arginine-poor conditions, and this screen ran one medium at 12 h. **Read
every `DOES_NOT_METABOLISE` edge as "not in this assay", never as "not at
all"** — `incubation_hours` and `replicates` are on the edge so the bound is
readable, and **15 other taxa across 21 screened isolates** *do* metabolise
digoxin here, which is itself the finding the classic single-organism story does
not carry. The 21 is the isolate count — `count(DISTINCT r.screen_column)` —
and reading it as a taxon count is the error this entry warns about two
paragraphs below.

**"And the gene where identified" is answered without a `Gene` node.** The
paper's second half names 30 bacterial gene products for 20 of the drugs, and
they ride on the edge: **32 `METABOLISES` edges carry `gene_locus_tags`,
`gene_products` and `gene_protein_ids`** — and **5 `DOES_NOT_METABOLISE` edges
carry them too**, because the genes were found in a gain-of-function library
expressed in *E. coli* and on those five pairs that experiment and the
whole-cell screen disagree. Keeping the disagreement visible is the point; the
recommendation against a node type, and what would change it, is in
`docs/model.md`.

```cypher
MATCH (t:Taxon)-[r:METABOLISES]->(d:Drug)
WHERE r.gene_locus_tags <> ''
RETURN d.title AS drug, t.title AS organism, r.strain AS strain,
       r.gene_locus_tags AS genes, r.gene_products AS products,
       r.gene_protein_ids AS refseq
ORDER BY drug, organism
```

**Two strain names are deliberately unresolved, and the tombstones say what was
rejected.** `Bacteroides WH2` and `Bifidobacterium ruminatum` each have **two**
NCBI candidates — `Bacteroides sp. WH2` (311784) against *B. cellulosilyticus*
WH2 (1268240); *B. ruminantium* (78346) against *B. ruminale*, a synonym of
*B. thermophilum* (33905) — and the reference column offers `WH2` and `fecal
isolate`, which choose nothing. They are `UnresolvedTaxon` nodes carrying both
candidate ids rather than a guess, at 271 measurements each. Five *other* names
are corrected, and every correction is confirmed by something that is not the
spelling: three by the row's own DSM number, one because there is exactly one
name in all of `names.dmp` at edit distance 1, one because the binomial is a
verbatim prefix of the string. The rule, not the list, is the contribution.

*Rank caveat, softened rather than resolved, on both screens:* both are
strain-level and this graph keys `Taxon` on the species, so Maier's 40 isolates
become 38 taxa (the non-toxigenic and enterotoxigenic *B. fragilis* collapse, as
do *E. coli* IAI1 and ED1a) and Zimmermann's 76 become 66 (seven *B. fragilis*
and three *B. thetaiotaomicron* among them). Each collapse is **parallel
edges**, and `nt_code` / `screen_column`, `strain` and `reported_name` are on
every edge, so "which strain?" is answerable from the edge even though the
strain is not a node. **The consequence is a per-taxon count that exceeds any
per-strain count**: *Bacteroides fragilis* metabolises 116 drugs in the graph
and no single one of its seven isolates metabolised more than 89, because those
seven are one node. `count(DISTINCT r.screen_column)` is the strain count; `count(r)` is not.

*Licence caveat, and these are the two strictest in the graph:* both screens are
journal supplementary tables of subscription articles with no separate data
licence, so their edges carry `source_licence = 'Maier2018-unstated'` and
`'Zimmermann2019-unstated'` rather than an invented permissive token. Two
tokens, not one, because two articles are two permissions and a reader excluding
one has no reason to lose the other; because G3 puts the licence on the edge,
either cut is one `WHERE` clause and neither contaminates anything else.

> **What the MASI download turned out to be, and what replaced it
> (2026-09-03).** The file this entry was written against,
> `MASI_v1.0_download_substanceInfo.{txt,xlsx}`, is the **substance
> dictionary**, not the interaction tables: 1,350 rows, 18 columns, and **no
> organism column, no interaction column, no effect, no direction and no
> PMID**. The interaction tables were then recorded as **not recoverable**,
> which was wrong: `aiddlab.com` serves them from behind an **expired TLS
> certificate**, so every fetch failed at the handshake and the Wayback Machine
> never captured them for the same reason. They were downloaded by hand through
> a browser on 2026-09-03 — see `docs/sources.md` §14 for the retraction and
> for what is loaded from them now.
>
> **And what is loaded is deliberately not on this query's relationships.**
> MASI is an aggregator: **5,419 of its 12,512 interaction records cite Maier
> 2018 and 2,884 cite Zimmermann 2019**, and **7,161 of the 11,456 edges it
> produces (62.5%) restate a (taxon, compound) pair one of those two screens
> already *measures*.** So its substances are `Substance` nodes, its four
> relationships are its own (`METABOLISES_SUBSTANCE`,
> `DOES_NOT_METABOLISE_SUBSTANCE`, `ABUNDANCE_CHANGED_BY_SUBSTANCE`,
> `ABUNDANCE_UNCHANGED_BY_SUBSTANCE`), and the identity between a MASI
> substance and a `Drug` is one declared `SAME_COMPOUND_AS` edge. **Every
> golden on this page is therefore unmoved by MASI's arrival**, which is the
> point: had its metabolism records landed on `METABOLISES`, the query above
> would count a curated restatement and a measured screen cell as two
> observations with nothing in the query text to say so. What MASI adds is
> reached deliberately, in one hop, and
> `WHERE r.duplicates_primary_source IS NULL` is the 4,295 edges no screen
> here measured.
> Profile: `data/raw/masi/PROVENANCE.md`. **The aggregator was overtaken by
> the two primary sources it aggregates**, one per direction, and both are
> better artifacts than MASI would have been: strain-resolved where MASI is
> genus-resolved, and carrying the 42,233 and 17,479 measured non-hits a curated
> positives-only resource never would.

### D9 — "Show me every association for taxon X where the evidence is 16S-only, so I can down-weight it."

*Status:* **`answerable-now`**. *Fields:* `evidence_level` · `sequencing_type` ·
`Signature.variable_region` · `Signature.sequencing_platform` · the rank the
taxon was reported at.

```cypher
MATCH (t:Taxon {id: 851})-[r:ASSOCIATED_WITH]->(d:Disease)
WITH d, r, CASE WHEN r.evidence_level = 'observational-16S' THEN 1 ELSE 0 END AS is16s
RETURN d.title AS disease, count(r) AS edges, sum(is16s) AS edges_16S,
       collect(DISTINCT r.evidence_level) AS levels,
       collect(DISTINCT r.sequencing_type) AS assays
ORDER BY edges DESC LIMIT 20

// the variable region and platform live on the Signature, not the edge:
MATCH (t:Taxon {id: 851})-[:REPORTED_BY]->(s:Signature)-[:IN_CONDITION]->(d:Disease)
WHERE s.sequencing_type = '16S'
RETURN d.title AS disease, s.variable_region AS region,
       s.sequencing_platform AS platform, count(s) AS signatures
ORDER BY signatures DESC
```

*Golden check (measured):* `observational-16S` is 58,595 of 105,097 association
edges — **55.8%** (BugSigDB alone: 57,391 of 103,461, 55.5%; gutMDisorder is
1,204 of its 1,636, an even more 16S-heavy corpus), matching the model's measured signature
distribution and BugSigDB's own 92.5%-of-*studies* 16S figure once weighted by
signature size. *Why this query ranks so high:* it is the direct
operationalisation of Part A's complaint, and it is the query G5 depends on —
identical V4 sequences belong to different species with 63% probability, so a
species-level claim resting only on `observational-16S` edges must say so.

### D10 — "For disease Y, which depleted taxa are plausible probiotic candidates?"

*Status:* **`partial`** — the depletion, AMR and metabolite legs work and
**the query now has the column it is named for**, but the probiotic annotation
is as wide as MASI's microbe dictionary and no wider (540 taxa of 864,132).
This is A5.4's second half. *Fields:* D2 ∪ D5 ∪ D7, joined on taxon, plus
`Taxon.probiotic`.

```cypher
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0005265'})
WHERE r.direction = 'decreased' AND t.placeholder = false
WITH t, count(DISTINCT r.study_id) AS n_studies,
     collect(DISTINCT r.evidence_level) AS levels
WHERE n_studies >= 2
OPTIONAL MATCH (t)-[:CARRIES_RESISTANCE_GENE]->(a:ResistanceGene)
OPTIONAL MATCH (t)-[p:PRODUCES]->(m:Metabolite)          // HMDB + NJC19; MiMeDB none
RETURN t.title AS candidate, t.rank AS rank, n_studies, levels,
       count(DISTINCT a) AS amr_determinants,
       collect(DISTINCT m.title) AS metabolites,
       // MASI. `true` = used as a probiotic; `false` = MASI curates the
       // organism and does not say so; **null = MASI has no row for it**, which
       // is not the same claim and must not be read as one.
       t.probiotic AS used_as_probiotic,
       t.probiotic_use_species AS probiotic_in,
       t.probiotic_research_stage AS probiotic_stage
ORDER BY n_studies DESC LIMIT 20
```

*Shape:* one row per candidate with its replication count, the strongest tier
reached, its AMR burden, its claimed metabolites and — since MASI — whether
anyone actually uses it as a probiotic. *Golden check (measured for
inflammatory bowel disease, `MONDO:0005265`):* **32 candidates at
`n_studies >= 2`; 5 carry an AMR determinant, 20 have at least one metabolite,
and 7 are organisms MASI records as being used as probiotics.** The first three
columns read `0`, `[]` and nothing at all for every row before CARD, HMDB and
MASI landed, and the fact that all four are populated is the reason the status
is `partial` rather than `pending-source`: the remaining gap is coverage — MASI
names 46 probiotics in total — not a missing relationship.

**The probiotic column is the one the query is named for, and it moved the
answer rather than decorating it.** The seven are *Akkermansia muciniphila*,
*Bifidobacterium adolescentis*, *B. bifidum*, *B. longum*,
*B. pseudocatenulatum*, *Butyricicoccus pullicaecorum* and *Faecalibacterium
prausnitzii*, each with the population it is used in and the stage that use has
reached (`Research`, `Clinical trial`, `Marketed`) — including the
*A. muciniphila* case this entry's own last paragraph walks through. **The flag
is three-state and the third state is load-bearing:** a candidate MASI has no
row for is `null`, never `false`, so this query never reads "MASI does not cover
this organism" as "this organism is not a probiotic".

*The `n_studies >= 2` clause is G4, not a nicety:* 84.2% of (taxon, condition)
pairs in the current build rest on a single study, and the sign of a
single-study association flips about one time in three — here the clause drops
**87 of 119** depleted taxa, leaving the 32. *The chain this query is a proxy
for* — observational correlation → mouse → a randomised, double-blind,
placebo-controlled human pilot, as in the *Akkermansia muciniphila* case — is
not recorded end-to-end by any single database, so the query returns
candidates, never conclusions. MASI's `probiotic_research_stage` is the closest
this graph gets to naming where on that chain an organism has reached, and it
is one curator's summary, not a trial record.

### D11 — "Which studies for disease Y controlled for medication or antibiotics?"

*Status:* **`answerable-now`** (was `partial` — the one place the graph failed
a guard it declared; closed 2026-09-03). The research calls this "the strongest
argument for BugSigDB as the spine": no other source in the survey records
confounder control. *Fields:* `Antibiotics exclusion` · `Confounders controlled
for` · `Matched on`.

```cypher
MATCH (s:Signature)-[:IN_CONDITION]->(d:Disease {id: 'MONDO:0005148'})
RETURN s.id AS signature, s.pmid AS pmid, s.study_design AS design,
       s.matched_on AS matched_on,
       s.confounders AS confounders_controlled,
       s.antibiotics_exclusion AS antibiotics_exclusion,
       s.group_0_size AS n0, s.group_1_size AS n1
ORDER BY pmid
```

*What was missing, and what was wrong about the diagnosis.* `Antibiotics
exclusion` (BugSigDB column 24) was genuinely never extracted — that half was
right, and it is the widest of the three columns: **6,485 of 14,846
signatures** carry an exclusion window. The other half was not: `matched_on`
and `confounders` were *not* returning null. The blueprint declared neither,
but kglite's loader carries every CSV column a node spec does not `skip`, so
both reached the graph anyway — 2,304 and 1,958 signatures respectively,
measured. That is a weaker guarantee than it looks (an undeclared column has no
declared type and no `property_types` check), so the fix was still three column
names: extract the third, and *declare* all three, which
`tests/test_acceptance.py` now asserts separately from their values. **G7 is
enforceable as of that fix**; D18's competing-explanation check still waits on
MASI for its drug→taxon half. *Golden check (measured 2026-09-03):* 14,846
signatures carry 2,304 `matched_on`, 1,958 `confounders` and 6,485
`antibiotics_exclusion`; for type 2 diabetes (`MONDO:0005148`) the query returns
180 signatures, 58 with confounders and 42 matched on. *Why it matters more
than its rank suggests:* 26 differentially abundant ASVs in T2D became **0**
after matching on host variables, and significance vanished entirely for
depression, autism, lung disease, thyroid disease, migraine and SIBO. An
unfiltered graph serves every one of those edges.

### D12 — "This paper says *Lactobacillus reuteri*. What is the current name and tax_id, and does a query for *Limosilactobacillus reuteri* find it?"

*Status:* **`partial`** — the NCBI half is answerable now, the nomenclatural
half has no source. This is Part A's A4 as a query, and it is harder than A4
assumes. *Fields:* `merged.dmp` ids · `names.dmp` synonym classes · rank · and
LPSN's correct-name/synonym status, which NCBI does not carry.

```cypher
// the easy half: an obsolete binomial through the synonym index.
// The rank filter is not cosmetic — see the golden check below.
MATCH (t:Taxon)
WHERE text_bm25(t, 'synonyms_text', 'Lactobacillus reuteri') > 0
  AND t.rank = 'species'
RETURN t.id AS tax_id, t.title AS current_name, t.rank AS rank,
       t.synonyms AS synonyms,
       text_bm25(t, 'synonyms_text', 'Lactobacillus reuteri') AS score
ORDER BY score DESC LIMIT 3

// and the audit trail: how did each spelling actually resolve?
MATCH (t:Taxon {id: 1598})-[r:REPORTED_BY]->(s:Signature)
RETURN r.reported_name AS as_printed, r.reported_tax_id AS as_given,
       r.resolution_status AS status,
       r.resolution_normalized AS needed_authority_stripping,
       r.resolution_note AS note, count(s) AS signatures
ORDER BY as_printed
```

*Golden check (measured), and both halves came out other than this document
first claimed:*

**The lookup finds 1598 only if it says which rank it wants.** Unfiltered, the
top three BM25 hits for `Lactobacillus reuteri` are *strains* — 491077, 299033
and 1273150 — because a strain's synonym string repeats the binomial in a
shorter document and BM25 scores that higher. Filtered to `rank = 'species'`
the answer is **1598 (*Limosilactobacillus reuteri*, score 14.16)**, whose
synonym list carries `Lactobacillus reuteri Kandler et al. 1982` and **not** the
bare binomial — which is C4 confirmed in the built graph: NCBI keeps that name
only in authority-decorated form, so a resolver indexing name classes literally
returns `unresolved` for it and for *Clostridium difficile*, and the failure
looks like a data gap. 726 taxa score above zero on that query; the rank filter
is what makes it an answer.

**The audit trail has nothing to strip.** Every one of taxon 1598's 69
`REPORTED_BY` edges reads `as_printed = 'Limosilactobacillus reuteri'`,
`status = 'exact'`, `needed_authority_stripping = false` — BugSigDB prints the
*current* name. Across the whole graph the resolution statuses are `exact`
114,161 / `merged` 413 / `promoted` 152 / `deleted` 16, and
`resolution_normalized` is **true on no edge at all**. Authority stripping is a
resolver path this corpus never exercises (`tests/test_reconcile.py` is where it
is tested), and the honest reading of the audit trail here is that the graph
records how each spelling resolved, not that any of them needed rescuing.

> **The Lacticaseibacillus rhamnosus note — why this query is `partial`.** NCBI
> taxid **47715** has scientific name ***Lacticaseibacillus rhamnosus***, and
> "Lactobacillus rhamnosus" resolves to the same taxid as a bare `synonym`, so
> the query above answers cleanly. But LPSN records the *Lacticaseibacillus*
> name as **taxonomically suspended** — "(and therefore not recommended for
> medical use for now) until no later than 2025 in favour of *Lactobacillus
> rhamnosus*" — and the stated end-date has passed while the page still reads
> suspended. *L. casei* and *L. paracasei* moved to *Lacticaseibacillus* and
> stayed; **only *rhamnosus* was suspended**, and it is arguably the single most
> commercially important probiotic species (LGG). The same shape recurs with
> *Prevotella copri* / *Segatella copri*. A single "current name" field cannot
> express that two authorities disagree about the same taxid, and this graph has
> one. Closing it needs **LPSN** (CC BY-SA 4.0, with an API) as a source, which
> is not in the fetch list; until then the graph reports NCBI's name and the
> disagreement is invisible. Recorded here rather than worked around: an
> unbracketing or un-renaming normaliser would be exactly the string-matching
> C9 forbids.

### D13 — "Which pathway or gene carries the production claim for taxon X → metabolite M?"

*Status:* **`partial`** (was `pending-source: KEGG / Reactome`) — the pathway
half resolves and is **misleading if unqualified**; the *gene* half has no
source at all. *Fields:* pathway id · gene · organism rank · whether the
assignment is genome-inferred.

```cypher
MATCH (t:Taxon {id: 562})-[p:PRODUCES]->(m:Metabolite)-[i:IN_PATHWAY]->(pw:Pathway)
RETURN m.title AS metabolite, pw.id AS pathway, pw.title AS pathway_name,
       pw.pathway_source AS pathway_source, pw.species AS pathway_species,
       i.evidence_code AS pathway_evidence, i.knowledge_level AS pathway_knowledge,
       p.evidence_level AS production_level,
       p.knowledge_level AS production_knowledge,
       'capability, not production' AS reading
ORDER BY pathway_source, pathway
```

*Golden check (re-measured 2026-09-03 over the whole `PRODUCES` layer — KEGG is
licence-gated and a default build has none of it):* the three-hop path resolves
for **130,214 rows over 628 taxa and 1,125 pathways**, out of **23,604
`Pathway` nodes** and a **23,717-edge `PART_OF_PATHWAY` DAG in which 388
children have more than one parent** (a loader modelling it as a tree loses
those silently). *E. coli* alone reaches **1,028** rows. **The figures this
entry carried until now — 4,806 rows over 95 organisms and 635 pathways, with
*E. coli* at 387 — are the HMDB-only slice**, and they stayed here after NJC19
grew `PRODUCES` 6x; `p.primary_source = 'hmdb'` still reproduces them exactly.
The `IN_PATHWAY` edges split **`IEA` 31,773 / `TAS` 4,357** — 87.9% of
`ChEBI2Reactome.txt` is an orthology projection from human rather than a read
paper, carried as `knowledge_level = logical_entailment` against
`knowledge_assertion`, and it is the cleanest knowledge-level signal in the
whole increment. Without it on the edge, D13's answer would read as curated
throughout. D5's example, *Akkermansia muciniphila*, reached **zero rows** here
while HMDB was the only source of production; on NJC19's four products it now
reaches **195**, every one of them a statement about the metabolite rather than
about the organism.

*The qualifier is part of the answer.* Reactome's 23,604 pathways span **16 model
organisms and not one gut commensal**, and the built graph reproduces exactly
that: every species a `PRODUCES → IN_PATHWAY` walk reaches is one of the 16, led
by *Homo sapiens* (16,424 rows). So a Reactome hit says the *metabolite*
participates in a human — or bovine, or zebrafish — pathway, never that the
taxon runs it. **There are three exceptions the plan did not name:** of the 830
organisms this graph credits with producing something, three are also species
Reactome models — *Mycobacterium tuberculosis*, *Plasmodium falciparum* and
*Saccharomyces cerevisiae*, carried for infection and model-organism pathways —
and a tuberculosis bacillus, a malaria parasite and a laboratory yeast are not
gut commensals, so "not one gut commensal" survives intact.

*Why the gene half is `pending` rather than absent by choice.* KEGG carries
microbial maps but **no taxid at all** (its organism route was retired upstream)
and ships under a licence that keeps the whole slice behind `--with-kegg`. So
the taxon→pathway assignment is genome-inferred in every case available here,
and gutSMASH *measured* gene abundance to be "almost completely uncorrelated"
with metabolite level in 1,135 individuals; PICRUSt2's overlap with true
metagenome results collapses from 654 to 66 KO terms. The row is labelled
`capability, not production` for that reason, and gutSMASH's MGC types (which
encode substrate and product in the type name) are the source that would make
the claim direct — not fetched.

### D14 — "Which of my changed taxa are just generic dysbiosis markers rather than disease-specific?"

*Status:* **`partial`** — the signature-breadth half works, the healthy-prevalence
half needs a source not in the fetch list. *Fields:* prevalence in healthy
samples · fraction of signatures reporting increase vs decrease per taxon.

```cypher
MATCH (t:Taxon)-[:REPORTED_BY]->(s:Signature)
WHERE t.placeholder = false
WITH t, count(s) AS n_signatures,
     sum(CASE WHEN s.direction = 'increased' THEN 1 ELSE 0 END) AS n_increased
MATCH (t)-[r:ASSOCIATED_WITH]->(d:Disease)
WITH t, n_signatures, n_increased, count(DISTINCT d.id) AS n_conditions
RETURN t.title AS taxon, t.rank AS rank, n_signatures, n_conditions,
       1.0 * n_increased / n_signatures AS frac_increased,
       n_signatures > 100 AS non_specific
ORDER BY n_signatures DESC LIMIT 20
```

*Golden check (measured):* the top rows must contain the four genera BugSigDB
itself names as "each reported as differentially abundant in more than 100
signatures" — and they do: **Bacteroides 1,150 · Streptococcus 1,123 ·
Prevotella 1,063 · Lactobacillus 938** taxon-report edges, with
*Lachnospiraceae* (1,024) and *Oscillospiraceae* (875) interleaved at family
rank. A build that does not reproduce those four is under-loaded. *What is
missing:* the healthy-prevalence half — BugSigDB's own r = −0.84 between a
genus's healthy prevalence and the fraction of signatures reporting it increased
in disease — needs **GMrepo** (9,623 healthy controls) or `bugphyzz`. *Standing
negative fixture:* the Firmicutes:Bacteroidetes ratio must never surface as an
obesity signal; ten studies found no significant phylum-level association,
including F:B. Any pipeline that returns it has a bug.

### D15 — "How many association edges have no evidence level, which sources do they come from, and which are single-cohort?"

*Status:* **`answerable-now`**. This is Part A's A1 third bullet and the query
that keeps the other nineteen honest.

```cypher
CALL ontology_audit() YIELD rule, severity, violations, exempted, total, pct
RETURN rule, severity, violations, total, pct ORDER BY pct DESC
```

```cypher
// the per-field census the audit's single percentage rolls up — the engine's
// own, one row per DECLARED property including the ones nothing fails
CALL ontology_audit({by: 'property'})
YIELD rule, property, violations, total, pct
WHERE rule = 'ASSOCIATED_WITH.required_properties' AND property IS NOT NULL
RETURN property, violations, total, pct ORDER BY pct DESC
```

*Golden check (measured):* of 112,966 edges, **`group_0_size` 14,837 (13.1%)
and `group_1_size` 14,732 (13.0%)** are the gap; `study_design` 2,436 (2.2%),
`statistical_test` 2,305 (2.0%), `sequencing_type` 1,910 (1.7%), `pmid` 1,061
(0.9%), `direction` and `source_relation` 894 (0.8%) each, and the remaining
six of the fourteen — `evidence_level`, `knowledge_level`, `agent_type`,
`primary_source`, `source_record_id`, `source_licence` — are **complete**,
which the census says out loud rather than leaving to be inferred from an
absence. The same query over `CONFERS_RESISTANCE_TO` is the sharper reading:
its 58.8% is **one field**, `pmid` on 8,052 of 13,691 edges, and every other
declared property is complete.

**Read it as a census, not a partition.** An edge missing both group sizes is
counted under both, so these rows sum to *more* than the rule's 17,546
violations. The `domain_class` breakdown is the partitioning one.

The row-level drill-down carries the same information per edge, and the
`properties` column is the whole failing set rather than the first of it:

```cypher
CALL edge_property_violation() YIELD relationship, properties, exempt
WHERE relationship = 'ASSOCIATED_WITH' AND NOT exempt
UNWIND properties AS field
RETURN field, count(*) AS edges ORDER BY edges DESC
```

Neither reports the **source** each gap comes from, which is the other half of
this query's question and still a Cypher aggregation:

```cypher
MATCH (:Taxon)-[r:ASSOCIATED_WITH]->(:Disease)
RETURN r.primary_source AS source, count(r) AS edges,
       sum(CASE WHEN r.direction        IS NULL THEN 1 ELSE 0 END) AS no_direction,
       sum(CASE WHEN r.pmid             IS NULL THEN 1 ELSE 0 END) AS no_pmid,
       sum(CASE WHEN r.group_0_size     IS NULL THEN 1 ELSE 0 END) AS no_group0,
       sum(CASE WHEN r.group_1_size     IS NULL THEN 1 ELSE 0 END) AS no_group1,
       sum(CASE WHEN r.statistical_test IS NULL THEN 1 ELSE 0 END) AS no_test,
       sum(CASE WHEN r.evidence_level  = 'unknown'      THEN 1 ELSE 0 END) AS level_unknown,
       sum(CASE WHEN r.knowledge_level = 'not_provided' THEN 1 ELSE 0 END) AS kl_not_provided
ORDER BY edges DESC
```

*Golden check (measured, and this is the project's headline number):*
`ontology_audit()` must return an `ASSOCIATED_WITH.required_properties` row at
`severity = warn` with a **non-zero denominator** and a violation fraction of
**17,546 of 112,966 edges = 15.5%**. That is **one** rule over every
association — disease, phenotype and exposure alike — since the junction edge's
target became a union; it was three rules of which only the disease one
(16,768 of 105,880 = 15.8%) was ever quoted as "the" number, beside 293 of
4,717 and 485 of 2,369 that nothing reported. The relation's completeness and
the disease slice's completeness are different questions and this row now
answers the first; `-[r:ASSOCIATED_WITH]->(:Disease)` still answers the second.

Earlier readings, kept because the movement is the point: 14,349 of 103,461 =
13.87% on BugSigDB alone, 15,985 of 105,097 = 15.20% once gutMDisorder landed,
16,768 of 105,880 = 15.8% once MASI did. **Each rise is the audit working, not
a regression:** all 1,636 gutMDisorder edges are violations, because that
source records no `study_design` and its association rows carry no link to a
sample arm, so no per-association group sizes exist either. For the same reason
`ABUNDANCE_CHANGED_BY.required_properties` reads **1,380 of 1,380 = 100%** — a
rule whose whole population is one source with three missing columns. A single
percentage over sources with different column sets is not the interesting
number; the per-source census below is, which is why that query is here. A zero
denominator means the rule is auditing property names nothing writes (C20); a
0.00% fraction means BugSigDB's literal `"NA"` reached the graph as a value
(C17) and the gate is vacuous. *And the number is a floor, not the whole gap:*
`evidence_level` is never absent — the derivation returns the string
`"unknown"` — so 800 further edges carry a level that means nothing and no
required-property check can see them. That is deliberate (never silently
"observational") and it is why `level_unknown` is a column here.
*G10's expansion factor* belongs in this report too, and `scripts/build.py`
prints it for **every relationship the fragments declare** rather than for the
three association names it once listed: edges per source record where the edge
carries one, edges per input row where it does not, and a line of its own for a
declared relationship that loaded **no** edges — which is the shape the
`IS_DRUG` defect had, zero edges and a rule auditing 0 of 0, for a whole
release.

### D16 — "Shortest path between any two entities" (A5.3)

*Status:* **`answerable-now`**, with a caveat that is part of the answer.

```cypher
MATCH p = shortestPath((t:Taxon {id: 853})-[*..4]-(d:Disease {id: 'MONDO:0005011'}))
RETURN length(p) AS hops,
       [n IN nodes(p) | labels(n)[0]] AS types,
       [n IN nodes(p) | n.title]      AS names
```

```cypher
// the evidence path, asked for explicitly rather than inferred from the shortcut
MATCH p = (t:Taxon {id: 853})-[:REPORTED_BY]->(s:Signature)-[:IN_CONDITION]->(d:Disease {id: 'MONDO:0005011'})
RETURN s.id AS signature, s.evidence_level AS level, s.study_design AS design,
       s.group_0_size AS n0, s.group_1_size AS n1, s.pmid AS pmid LIMIT 5
```

*Golden check:* returns **1 hop** where a direct `ASSOCIATED_WITH` exists — the
flattened edge doing its job — and the three-hop
`Taxon → Signature → Disease` walk returns the evidence that shortcut stands
for. *Caveat, from G10:* over a graph of ~1.31M edges a shortest path routes
through hubs — `Bacillota` alone carries 855 taxon-report edges — and a KG's
link scores correlate with node degree at R² = 0.77. A shortest path here is a
navigation aid, never evidence, and no D-query treats path existence as support.

### D17 — "Where do studies disagree, and which pairs rest on a single cohort?"

*Status:* **`answerable-now`**. This is guard G4 as a query — the one the
Tierney result makes mandatory.

```cypher
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
WITH t, d, collect(DISTINCT r.direction) AS directions,
     count(DISTINCT r.study_id) AS n_studies, count(r) AS n_edges
RETURN t.title AS taxon, d.title AS disease, directions, n_studies, n_edges,
       size(directions) > 1 AS direction_conflict,
       n_studies = 1        AS single_cohort
ORDER BY n_edges DESC LIMIT 50
```

*Golden check (measured):* **8,257 of 56,306 (taxon, disease) pairs carry both
`increased` and `decreased`, and 47,262 of 56,306 — 83.9% — rest on a single
study** (BugSigDB alone: 8,114 and 46,809 of 55,445, 84.4%; before MASI, 8,238
and 47,232 of 56,124). So `single_cohort` is the default exclusion for every ranked D-query,
not a rare flag. The named fixture is D2's: *Fusobacterium nucleatum* ×
colorectal cancer returns `directions = ['increased','decreased']`, `n_edges =
40`, `n_studies = 21`. **The query reports the disagreement; it never resolves
it, and no majority rule is applied anywhere in the graph.** T1D and T2D pairs
are a standing fixture because they are the measured worst case: >90% of
published findings for both were nonrobust to model specification.

### D18 — "Is this T2D association a drug effect?" — the metformin confounding check

*Status:* **`partial`**, and it stays `partial` for a reason that changed
shape rather than went away. Three routes now offer a competing explanation:
gutMDisorder's abundance shift in a host (17 T2D taxa), Maier's measured
growth **negative** in a tube (32 T2D taxa, zero hits at 20 µM — a constraint on
the *mechanism*, not a second correlation), and MASI's curated literature layer,
which is the largest at **365 metformin edges over 185 taxa, 48 of them
associated with T2D**. *Fields:* D2's, joined to a drug→taxon layer, plus D11's
confounder columns.

```cypher
// metformin is CHEMBL:CHEMBL1431. Two drug->taxon routes, and they answer
// different questions: gutMDisorder says the abundance moved in a host,
// Maier says the growth did or did not move in a tube.
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0005148'})
MATCH (drug:Drug {id: 'CHEMBL:CHEMBL1431'})
      -[g:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->(t)
OPTIONAL MATCH (t)-[a:ABUNDANCE_CHANGED_BY]->(:Intervention)-[:IS_DRUG]->(drug)
WITH t, collect(DISTINCT r.direction) AS direction_in_t2d,
     count(DISTINCT r.study_id) AS t2d_studies,
     collect(DISTINCT g.effect) AS metformin_growth_effect,
     collect(DISTINCT g.nt_code) AS isolates_screened,
     collect(DISTINCT g.source_relation) AS screen_call,
     collect(DISTINCT a.direction) AS metformin_abundance_effect
RETURN t.title AS taxon, direction_in_t2d, t2d_studies,
       metformin_growth_effect, isolates_screened, screen_call,
       metformin_abundance_effect,
       'competing explanation' AS reading
ORDER BY t2d_studies DESC
```

*Golden check (measured):* the query returns **32 rows**, and
`metformin_growth_effect` is `['no-effect']` on every one of them — 34 isolate
measurements over 32 taxa. Metformin's whole growth profile is **40
measurements, 38 taxa, zero hits**. The gutMDisorder leg is unchanged and still
reaches **21 taxa over 24 `ABUNDANCE_CHANGED_BY` edges, 17 of which carry a T2D
association**; both legs are kept because neither refutes the other, and an
abundance shift with no growth inhibition is itself the finding — it argues for
an indirect mechanism rather than direct killing.

**D18 is a template, not one drug, and the screen is what makes that usable.**

```cypher
// "Which drugs could explain any of the taxa I found changed in T2D?"
MATCH (t:Taxon)-[:ASSOCIATED_WITH]->(:Disease {id: 'MONDO:0005148'})
MATCH (d:Drug)-[g:INHIBITS_GROWTH_OF]->(t)
RETURN d.title AS drug, g.drug_class AS class,
       count(DISTINCT t) AS t2d_taxa_inhibited
ORDER BY t2d_taxa_inhibited DESC LIMIT 25
```

*Golden check (measured):* **380 drugs inhibit at least one of the 32 T2D taxa,
186 of them human-targeted rather than antibacterial.** That is the shape of the
question Forslund et al. generalised to — of 41 drug categories, 19 associated
singly with the microbiome and only **6** survived multi-drug correction, and
taxonomic associations fell 154 → 47 — and it was unaskable here before a
drug↔taxon layer existed.

**The third route, and the reason to read it carefully.** MASI's metformin
records reach the `Substance` node metformin also has, one `SAME_COMPOUND_AS`
hop from `CHEMBL:CHEMBL1431`:

```cypher
MATCH (t:Taxon)-[m]->(s:Substance)-[:SAME_COMPOUND_AS]->
      (:Drug {id: 'CHEMBL:CHEMBL1431'})
RETURN t.title AS taxon, type(m) AS claim, m.direction AS direction,
       m.evidence_level AS level, m.publications AS paper,
       m.duplicates_primary_source AS also_measured_by
```

*Golden check (measured):* **365 edges over 185 taxa**, of which **347 are pairs
no screen in this graph measured** (`duplicates_primary_source IS NULL`); 48 of
the taxa carry a T2D association, against Maier's 32 and gutMDisorder's 17.

*What the partial does not cover, and the gap changed kind rather than closed.*
From Forslund et al. (Nature 528:262, 2015, PMID 26633628; 784 metagenomes
across three countries): an ***Escherichia*** increase and an
***Intestinibacter*** decrease are metformin effects rather than T2D signals,
the latter consistent across all three cohorts; a ***Lactobacillus*** increase
attributed to unstratified T2D was "eliminated or reversed" when controlling for
metformin. gutMDisorder curated a metformin edge for only *Bifidobacterium* of
the four, and *Intestinibacter* was not one of Maier's 40 isolates — which is
what this entry called the reason for `partial`.

**MASI reaches all three of the ones gutMDisorder misses**, including
*Intestinibacter*, with a curated abundance **decrease** in vivo in humans. And
the citation on that edge is `PMID:26633628` — **Forslund et al. itself**. That
is the finding this query is checking a T2D association *against*, curated by a
third party and loaded back in; a curated restatement of the paper is not
independent evidence for or against it, so the status does not move. What did
move is the reach (32 T2D taxa → 48) and the shape of the gap: it is no longer
"no edge exists for *Intestinibacter*" but "the edge that exists is the claim,
not a test of it" — which `primary_source = 'masi'`, `evidence_level = 'unknown'`
and `publications` all say on the edge itself, and which
`tests/test_acceptance.py` asserts by name so it cannot be read as a measurement
by accident.

*And the thing the growth screen cannot say at all:* it is a monoculture assay
at one concentration. A drug that changes a community without killing anything —
by shifting pH, by cross-feeding, by an effect on the host — is invisible to it,
and 42,233 non-hits are non-hits *at 20 µM in pure culture*, not evidence of no
effect in a gut. That is exactly why the two legs are both kept rather than one
being read as the answer. Verbatim, and unchanged by any of this: "metformin
treatment status could be reliably recovered from microbial composition using
SVMs, **metformin-untreated T2D status itself could not**".

### D19 — "Train a cross-cohort classifier on these taxa" — `descoped`

*Status:* **`descoped`.** *Reason:* the graph holds no sample-level abundance
matrices and will not. W2's modelling leg belongs to curatedMetagenomicData
(>22,000 samples, 94 studies) plus SIAMCAT or xMarkerFinder; this graph's role
is the *disease-specificity and replication metadata* those tools need (D3, D10,
D17), not the matrices. Recorded explicitly so nobody plans a query for it. The
number that says why it matters anyway: naively transferred models showed a
"more than twofold increase in false positives on average" and elevated
cross-disease false positives "by a factor of 2.8", with one ankylosing
spondylitis model calling >90% of other-disease cases positive.

### D20 — "Compute per-sample cross-feeding fluxes" — `descoped`

*Status:* **`descoped`.** *Reason:* MICOM's and SMETANA's directed exchange
tables are produced by genome-scale metabolic model simulation per sample
(CarveMe/AGORA2 reconstruction, then pFBA at community scale) — computation over
an input community, not a database to load. D6's NJC19 layer is the curated,
qualitative, literature-backed class and is in scope; the computed, quantitative,
sample-contextual class is a different evidence class and **the two must never
be merged into one edge type**. If a computed layer is ever ingested it lands as
`knowledge_level = 'prediction'`, `agent_type = 'computational_model'`,
`evidence_level = 'computational-predicted'`, in its own relationship type — the
authors of the method are themselves explicit that these are *potential*
interactions "naturally unable to predict all organism-specific traits".

---

### Coverage

| Status | Count | Queries |
|---|---:|---|
| `answerable-now` | **12** | D1, D2, D3, D4, D6, D7, D8, D9, D11, D15, D16, D17 |
| `partial` | **6** | D5, D10, D12, D13, D14, D18 |
| `pending-source` | **0** | — |
| `descoped` | **2** | D19, D20 |
| **total** | **20** | |

**D8 moved, and it is the first count to move in three increments.** It had been
`partial` since ChEMBL landed, for three different reasons in turn — first that
no `Drug`–`Taxon` edge existed at all, then that only the inhibition half did.
Both halves are now measured screens with their measured negatives kept, so the
query answers the question it is named for.

- **D8** is `answerable-now`: **5,592 `INHIBITS_GROWTH_OF` + 42,233
  `DOES_NOT_INHIBIT_GROWTH_OF`** over 1,197 drugs and 38 taxa, and **2,575
  `METABOLISES` + 17,479 `DOES_NOT_METABOLISE`** over 271 drugs and 66 taxa, as
  four relationship types across two directions. Both screens reproduce their
  own paper's headline from the loaded edges (24.3% of human-targeted drugs
  inhibit at least one strain; 172 of 271 drugs are metabolised by at least one
  taxon, against a published 176 whose four-drug gap is priced and named). The
  gene layer W7 asks for rides on the edge, and there is still no `Gene` node.
- **D18** is still `partial`, and the reason changed shape rather than went
  away. The competing explanation now reaches 48 T2D taxa across three routes —
  gutMDisorder's 17, Maier's 32 with a measured metformin negative, and MASI's
  365 curated metformin edges over 185 taxa. MASI does reach *Intestinibacter*,
  the confounder Maier's 40 isolates missed, with an abundance decrease — but
  the citation on that edge is `PMID:26633628`, **Forslund et al. itself**, so
  what the graph gained is the finding under test rather than a test of it. A
  curated restatement of the paper does not promote the status; it is why the
  edge says `primary_source = 'masi'` and `evidence_level = 'unknown'`.
- **D10** is still `partial` and gained the column it is named for. MASI's
  microbe dictionary puts `probiotic`, `probiotic_use_species` and
  `probiotic_research_stage` on 540 `Taxon` nodes, and **7 of D10's 32 IBD
  candidates carry it** — *Akkermansia muciniphila* and *Faecalibacterium
  prausnitzii* among them. The gap is coverage: MASI names 46 probiotics in
  total, and the flag is null rather than false on every taxon it does not
  cover.

Which source would close which remaining query: **nothing on offer** closes
D5's enzyme/pathway leg (or D13's) — MiMeDB v2.0 was fetched on 2026-09-03 to do
exactly that and carries no reaction table and no pair list, only a count of the
pairs it withholds, so that candidate is eliminated rather than pending;
**gutSMASH** → D13's gene leg; **GMrepo**/`bugphyzz` → D14's healthy-prevalence
half; **LPSN** → D12's nomenclatural half. MASI is off this
list because it arrived: its tables were recovered on 2026-09-03 once the
"unrecoverable" verdict turned out to be an expired certificate
(`docs/sources.md` §14), and both primary sources it aggregates were already
loaded. Nothing on this list would close D18 —
what that query wants is a screen that ran *Intestinibacter*, and no published
one did.

Eleven sources have landed and moved twelve queries. **gutMDisorder** closed D4's
intervention leg; **CARD** closed D7 outright and D10's AMR leg; **HMDB +
Reactome** moved D13 from `pending-source` to `partial` and gave D5 its first
578 edges; **ChEMBL**, joined to gutMDisorder's interventions by `IS_DRUG`,
moved D8 and D18 off `pending-source`; **NJC19** closed D6, took D5 from 578
edges to 3,418, and more than doubled D10's metabolite leg (7 candidates → 18);
**MiMeDB** wrote 1,237 `Metabolite` nodes and no edges, which is a finding
rather than a contribution — it is what gives NJC19's cross-reference-free
compounds an identity to point at, and its v2.0 refresh added 302 nodes and,
again, zero edges; **Maier 2018** closed D8's inhibition leg and turned D18's
metformin question from a 17-taxon correlation into a 32-taxon measured
negative; **Zimmermann 2019** closed D8 outright, adding the direction no other
source in this graph carries — the bacterium changing the drug — and the first
`Taxon`–`Drug` edge; **MASI** moved D10 (26 candidates → 32, and the probiotic
column the query is named for) and widened D18's reach to 48 taxa, while
**moving no golden on D8 at all** — by design, because 62.5% of its edges
restate a pair one of the two screens already measured and none of them is
allowed onto a screen's relationship. Of the original five `partial` queries,
**two needed no new source at all** — D11 is closed (three column names declared, one more
extracted) and D14's non-specificity half already worked. Every `partial` above
names the leg that works and the leg that does not, and each is a measured
number rather than a label.

**Two numbers are worth reading twice: 42,233 and 17,479.** Together with
NJC19's 894 `NO_EXCHANGE_WITH` and MASI's 521 curated non-effects they are the
**61,127 edges** in this graph of the form "somebody looked at this pair and
found nothing", for any relationship — and the two screens are 98% of it. Every other edge here exists because a
result was worth publishing, which is the selection bias the whole evidence
model is built to make visible — and a screen is the one design that escapes it.
Each screen carries its own control on the claim: the 55 cells Maier wrote `NA`
for are neither relationship, because a pair nobody measured is not a negative,
and the four `Control pH` columns Zimmermann interleaved among its strains are
neither either, because abiotic degradation is not metabolism. Both are ledger
rows in the `unresolved_maier2018` table on the build result and
the `unresolved_zimmermann2019` table on the build result rather than rounding errors.

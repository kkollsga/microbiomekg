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
(`new_taxdump` 2026-09-02), BugSigDB (`full_dump` 2026-09-02), **MONDO
(2026-09-01, as the disease-id hub)** and **gutMDisorder v1 (2020, recovered
from Wayback — loaded 2026-09-03)**. Fetched and profiled, not yet loaded:
HMDB 5.0, CARD, Reactome, KEGG, ChEMBL 37
(`docs/research/source-formats.md`). Being fetched to close the
three named gaps: **MiMeDB** (per-taxon metabolite production), **NJC19**
(consumption / cross-feeding), **MASI** (drug↔taxon). Every "no" below names
which of those fills it.

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

**Can this graph answer it? PARTIAL — the depletion leg only.** Replicated
depletion with an evidence tier is answerable now (D10's first leg). The AMR leg
is `pending: CARD`; the metabolite leg is `pending: MiMeDB` (HMDB alone yields
224 microbial-origin metabolites keyed on free-text organism names, §"HMDB" in
`source-formats.md`); the interventional-evidence leg **is loaded** —
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

**Can this graph answer it? NO.** There is no taxon–metabolite edge today.
**`pending: HMDB` gives 224 edges** — 0.10% of the file, keyed on uncontrolled,
misspelled, mixed-rank organism strings with no taxid, of which 158 are
`quantified`/`detected`. **`pending: MiMeDB`** is what makes the question
answerable at scale (Microbial Sources + Metabolic Reactions carrying Precursor,
Product, Enzyme, Enzyme's source organism, Reaction type, References; v2.0:
29,295 metabolites, 3,725 microbes, 25,276 curated reactions). Its 23.1M
BLAST-propagated pathways are a different evidence class and land as
`computational-predicted`, never merged with the curated reactions. The gutSMASH
result is *why* genome-inferred production is a distinct and low tier rather
than a synonym for production.

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

**Can this graph answer it? NO — and this is Part A's use case 5.**
**`pending: NJC19`** for the curated class. **[A-override]** Part A5 says HMDB
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

**Can this graph answer it? NO — `pending: CARD`.** Four conditions apply when
it lands, all from `source-formats.md`: key models on `Model ID` (6,463 unique;
`ARO Accession` is duplicated on 5 rows of `aro_index.tsv`), prefer the CC BY 4.0
`aro.obo` half over the non-redistributable `card-data/` half and carry the
licence per edge, never use `card-ontology/ncbi_taxonomy.obo` as a source of
taxon labels (it renames `NCBITaxon:2` to CARD's editorial string), and say
plainly what the taxon edge means — the taxid on a model is the *reference
sequence's* organism, not the organism the gene is claimed for (132 models are
keyed on taxid 2, "Bacteria"). A "276k AMR links" figure sourced from Prevalence
is predicted, not curated (D7).

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

**Can this graph answer it? NO — `pending: MASI`.** ChEMBL, which *is* fetched,
supplies the `Drug` and `ProteinTarget` nodes and its targets' taxids, but no
drug↔gut-taxon edge exists in it at all. This gap is load-bearing twice over:
it blocks W7 directly, and it is the *defence* against W2's confounding trap —
without a drug→taxon layer the graph cannot offer "metformin" as a competing
explanation for a T2D edge, which is exactly the error Forslund et al.
documented (D18).

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
| `in-vitro` | Measured in culture: monoculture or defined co-culture growth, a metabolite assay, an MIC over controls, or a gene→product step shown by knockout or heterologous expression. | `Study design = laboratory experiment` with no live host named; CARD's curated resistance models; ChEMBL mechanism rows whose only references are PubMed; HMDB microbial-origin edges whose metabolite is `detected`/`quantified`; NJC19 and MASI experimentally-verified events. |
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
  Testable: input rows = edges + `unresolved_taxa.csv` records + explicitly
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

**And the loader will silently undo it at scale.** Reproduced against kglite
0.16.21 while writing these tests: the blueprint's junction-CSV loader streams
in chunks and **deduplicates parallel edges from the second chunk onwards**.
With `KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE=3` and a junction CSV holding ten
identical `A1 -> B1` pairs, the built graph has **three** edges. The default
chunk is 100,000 rows and the full-dump `taxon_disease.csv` is ~118k rows of
deliberately parallel edges, so a default build drops every repeat of a pair
it saw in the first chunk — precisely the evidence multiplicity this whole
document exists to protect, removed with no warning and no error. The build
command must raise the chunk size above the row count.

Guard: `tests/test_loader_contracts.py::test_junction_loader_keeps_parallel_edges`
and `::test_junction_loader_drops_parallel_edges_beyond_one_chunk` — the
second pins the *bug*, deliberately not as an xfail, so a kglite release that
repairs it turns the test red and the chunk-size override can be removed.

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
`data/csv/unresolved_conditions.csv`. See `docs/model.md` §1.

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
*countable*. Over the fixture's **72** association edges (55 `ASSOCIATED_WITH`,
3 `ASSOCIATED_WITH_PHENOTYPE`, 14 `ASSOCIATED_WITH_EXPOSURE`), the per-field
gap census is:

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

Two things about the instrument, both verified against kglite 0.16.21:

- `CALL ontology_audit()` counts **edges** missing at least one required
  property — so its `violations` column is the union (16), never the sum of
  the column above. Its columns are `rule, severity, violations, exempted,
  total, pct`.
- `CALL edge_property_violation()` emits **one row per violating edge**,
  naming only the *first* missing property in declaration order — not one row
  per missing field. It tells you *which* edges are incomplete; the per-field
  table above needs a Cypher query
  (`MATCH ()-[r:ASSOCIATED_WITH]->() WHERE r.<prop> IS NULL`). A gap report
  built from the procedure alone silently under-counts every field but the
  first.

Since the union runs over three relationships (C14), `ontology_audit()` reports
three `*.required_properties` rows and the 16 is their sum.

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
an edge, a record in `unresolved_taxa.csv`, or an explicit, reported filter
count. The three sinks must sum to the input row count.

Concrete leaks in this data:

- `bsdb:19533811/2/NA` (a real row) has `NCBI Taxonomy IDs = NA`,
  `MetaPhlAn taxon names = NA` and `Abundance in Group 1 = NA` — an *empty
  signature*. It contributes zero taxon edges. **621** rows of the full dump
  are like it. That is a legitimate filter, but it must be counted, not
  absorbed.
- The three adversarial rows that must appear in `unresolved_taxa.csv` with
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
| `Paper` | **33** | | `ASSOCIATED_WITH` | **55** |
| `Disease` | **15** | | `ASSOCIATED_WITH_PHENOTYPE` | **3** |
| `Phenotype` | **1** | | `ASSOCIATED_WITH_EXPOSURE` | **14** |
| `Exposure` | **4** | | `IN_CONDITION` | **34** |
| `BodySite` | **9** | | `IN_PHENOTYPE` | **3** |
| `Taxon` | **143** | | `IN_EXPOSURE` | **6** |
| `UnresolvedTaxon` | **3** | | `AT_BODY_SITE` | **45** |
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
| association edges (all three relationships) | **72** |
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

Recorded here because they are contract changes, not test bugs. **Items 1–5 are
closed**; the resolution is noted under each, and item 6 stands.

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
   needs a per-field gap census must use Cypher instead, and a reader who
   assumes otherwise will report a confidently wrong breakdown.

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
moved to `Phenotype` / `Exposure` with their own `ASSOCIATED_WITH_PHENOTYPE` /
`ASSOCIATED_WITH_EXPOSURE` edges, and the evidence contract's `source` /
`signature_id` are now `primary_source` / `source_record_id` alongside
`knowledge_level`, `agent_type`, `source_licence` and `source_relation`.
Queries marked `pending: <source>` are written against the node and edge names
proposed in `docs/research/source-formats.md`'s extraction tables; where that
document has no table yet (MiMeDB, NJC19, MASI) the names are proposed here and
are the loader's contract.

Measurements quoted as "measured" were taken from `data/csv/` on 2026-09-03,
against the full BugSigDB dump of 2026-09-02 **and gutMDisorder v1**. Where the
second source moved a number, the one-source value is kept beside it: a golden
that moves when a source lands is the expected outcome, and the pair is what
says by how much. `tests/test_acceptance.py` runs every `answerable-now` query
below and asserts these numbers.

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
reported. If this returns one row, C13's parallel-edge collapse has recurred and
`KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE` was not set above the row count.

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
neither and sit in `unresolved_associations.csv` with that reason.

### D5 — "Which metabolites does taxon X produce, and is that measured or predicted?" (and the reverse: which taxa produce metabolite M?)

*Status:* **`pending-source`** — HMDB gives 224 edges, MiMeDB gives the rest.
This is A5.2. *Fields:* production direction · evidence tier · pathway/gene ·
rank at which the claim holds · citation · replication count.

```cypher
-- pending: HMDB (224 microbial-origin edges), MiMeDB (per-taxon, with enzyme)
MATCH (t:Taxon {id: 239935})-[p:PRODUCES]->(m:Metabolite)
RETURN m.title AS metabolite, m.chebi_id AS chebi, m.hmdb_status AS hmdb_status,
       p.evidence_level AS level, p.knowledge_level AS knowledge_level,
       p.reported_name AS organism_as_named, p.enzyme AS enzyme,
       p.publications AS refs, p.primary_source AS source
ORDER BY level, metabolite

-- the reverse (A5.2's second half): who makes butyrate?
MATCH (t:Taxon)-[p:PRODUCES]->(m:Metabolite {id: 'CHEBI:17968'})
WHERE t.placeholder = false
RETURN t.title AS producer, t.rank AS rank, p.evidence_level AS level,
       count(DISTINCT p.source_record_id) AS n_records
ORDER BY level, n_records DESC
```

*Shape:* one row per (taxon, metabolite, source record). *Expected size, stated
so nobody plans on a bigger number:* HMDB's microbial branch is **224
metabolites, 0.10% of the file**, keyed on free-text, misspelled, mixed-rank
organism names with **no taxid** — 169 "genus"-level terms that include phyla, a
class, six families, two Gram stains and a U+FB01 ligature typo; the misspellings
(`Citrobacter frundii`, `Akkermansia muciniphilia`) are expected to land in
`UnresolvedTaxon`, which is the correct outcome, not a loss. MiMeDB v2.0 (29,295
metabolites, 3,725 microbes, 25,276 curated reactions) is what makes this
answerable at scale; its 23.1M BLAST-propagated pathways are
`computational-predicted` and must stay in a separate layer. *Required
qualifier:* the answer carries a replication count and the expected value is
**1** — even robustly predicted metabolites are predicted by markedly different
sets of taxa across datasets. *Why the tier is not optional:* gutSMASH measured
metabolite levels to be "almost completely uncorrelated" with the abundance of
the corresponding genes across 1,135 individuals.

### D6 — "Which taxa consume metabolite M?" — the cross-feeding query

*Status:* **`pending-source`: NJC19**. This is Part A's use case 5, and it is
**not** descoped — but Part A understates the gap: no source in the profiled
seven carries consumption, not just HMDB, and MiMeDB keys origin on compounds
appearing as a *product*, so it does not fill it either. *Fields:* a `CONSUMES`
edge with an evidence tier and a rank.

```cypher
-- pending: NJC19 (8,224 directed import/export/degrade events, 838 species, CC0)
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

**Metabolite Exchange Score: MES = 2·P·C / (P + C)** — the harmonic mean of the
number of potential producers P and consumers C, and **MES = 0 when a metabolite
is only produced or only consumed** (Marcelino et al., Nat Commun 14:6546,
2023). That identity is the whole argument: without a `CONSUMES` edge every row
of this query returns 0.0 and the use case is dead. *Proposed loader contract
for NJC19:* `(Taxon)-[:PRODUCES|CONSUMES]->(Metabolite)` with
`source_relation ∈ {export, import, degrade}`, `primary_source = "njc19"`,
`source_licence = "CC0-1.0"`, `knowledge_level = "knowledge_assertion"`,
`agent_type = "manual_agent"`, `evidence_level = "in-vitro"` (NJC19's curation
basis is experimentally verified transport or degradation), and the **912
negative associations as their own edge type**
`(Taxon)-[:NO_EXCHANGE_WITH]->(Metabolite)` — explicit negatives are rare enough
in this field to be worth their own shape. *Golden check when it lands:*
acetate, the most frequently exported product (44.3% of NJC19's species), must
have both a non-zero producer and a non-zero consumer count.

### D7 — "Which AMR genes does taxon X carry, to which drug class, by which mechanism, and at what call confidence?"

*Status:* **`pending-source`: CARD**. *Fields:* ARO id · detection model type ·
RGI hit category · drug class · resistance mechanism · curated-vs-prevalence
provenance flag.

```cypher
-- pending: CARD
MATCH (t:Taxon {id: 562})-[c:CARRIES_DETERMINANT]->(a:AROTerm)
OPTIONAL MATCH (a)-[:CONFERS_RESISTANCE_TO]->(dc:DrugClass)
RETURN a.title AS determinant, a.id AS aro,
       a.resistance_mechanism AS mechanism, dc.title AS drug_class,
       c.model_type AS model_type, c.hit_category AS rgi_hit,
       c.sequence_derived AS from_reference_sequence,
       c.evidence_level AS level, c.primary_source AS source,
       c.source_licence AS licence
ORDER BY drug_class, determinant
```

*Four conditions the loader must satisfy, all from the source profile:* key
models on `Model ID` (6,463 unique — `ARO Accession` is duplicated on 5 rows of
`aro_index.tsv`, and keying on it silently drops half of each pair); take
`card.json` as the model authority, not `aro_index.tsv` (they disagree on 84
models); carry the licence per edge (`CC-BY-4.0` for `aro.obo`,
`card-data-noncommercial` for `card-data/`); and never use
`card-ontology/ncbi_taxonomy.obo` as a source of taxon labels — it renames
`NCBITaxon:2` to CARD's own editorial string. *The claim the edge makes, stated
on the edge:* `sequence_derived = true` means the taxid is the **reference
sequence's** organism, which is "this sequence was cloned from this organism",
not "this organism is resistant" — 132 models are keyed on taxid 2 (Bacteria).
And gene presence is not phenotype: even a Perfect RGI hit "does not indicate if
the AMR gene is expressed or if it results in elevated MIC", while AMRFinderPlus
and ResFinder score 54–58% balanced accuracy against measured resistance. A
"276k AMR links" figure sourced from CARD Prevalence is `computational-predicted`
and must be excludable with one `WHERE`.

### D8 — "Does drug D inhibit gut bacteria, or get metabolised by them, and which strains?"

*Status:* **`pending-source`: MASI**. ChEMBL, which *is* fetched, supplies the
`Drug` and `ProteinTarget` nodes and 125 target taxids, but **no drug↔gut-taxon
edge exists in it at all**. *Fields:* drug id · taxon at strain resolution ·
assay and readout · direction (inhibits / metabolises / no effect — the
negatives matter) · gene.

```cypher
-- pending: MASI (bacteria->substance 4,001 pairs; substance->bacteria 7,770)
MATCH (t:Taxon)-[a:ALTERS_SUBSTANCE|ALTERS_TAXON]-(d:Drug {id: 'CHEMBL:CHEMBL1431'})
RETURN t.title AS taxon, t.rank AS rank,
       type(a) AS edge_direction,
       a.alteration_effect AS effect, a.exposure_dose AS dose,
       a.exposure_duration AS duration, a.pmid AS pmid,
       a.evidence_level AS level, a.primary_source AS source
ORDER BY edge_direction, taxon
```

*Shape:* two edge types, never one — `ALTERS_TAXON` (the drug changes the
bacterium: Maier's 24% of human-targeted drugs inhibiting at least one of 40
strains) and `ALTERS_SUBSTANCE` (the bacterium changes the drug: Zimmermann's
176 of 271 oral drugs metabolised by at least one of 76 strains). Collapsing
them into one `ASSOCIATED_WITH` conflates antimicrobial killing with drug
metabolism, which is MDAD's documented weakness. *Rank caveat:* MASI resolves
"down to genus level" while both landmark screens are strain-level, so the
strain half is only available from the Maier/Zimmermann supplementary matrices
directly. *Liveness caveat recorded in the research:* MASI's site has an expired
TLS certificate and declares no separate database licence.

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

-- the variable region and platform live on the Signature, not the edge:
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

*Status:* **`partial`** — the depletion leg works, the AMR and metabolite legs
do not. This is A5.4's second half. *Fields:* D2 ∪ D5 ∪ D7, joined on taxon.

```cypher
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0005265'})
WHERE r.direction = 'decreased' AND t.placeholder = false
WITH t, count(DISTINCT r.study_id) AS n_studies,
     collect(DISTINCT r.evidence_level) AS levels
WHERE n_studies >= 2
OPTIONAL MATCH (t)-[:CARRIES_DETERMINANT]->(a:AROTerm)   -- pending: CARD
OPTIONAL MATCH (t)-[p:PRODUCES]->(m:Metabolite)          -- pending: MiMeDB
RETURN t.title AS candidate, t.rank AS rank, n_studies, levels,
       count(DISTINCT a) AS amr_determinants,
       collect(DISTINCT m.title) AS metabolites
ORDER BY n_studies DESC LIMIT 20
```

*Shape:* one row per candidate with its replication count, the strongest tier
reached, its AMR burden and its claimed metabolites. Today the last two columns
return `0` and `[]` for every row — that is the honest answer, not a bug, and
D15 reports it. *The `n_studies >= 2` clause is G4, not a nicety:* 84.4% of
(taxon, condition) pairs in the current build rest on a single study, and the
sign of a single-study association flips about one time in three. *The chain
this query is a proxy for* — observational correlation → mouse → a randomised,
double-blind, placebo-controlled human pilot, as in the *Akkermansia muciniphila*
case — is not recorded end-to-end by any single database, so the query returns
candidates, never conclusions.

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
-- the easy half: an obsolete binomial through the synonym index
MATCH (t:Taxon)
WHERE text_bm25(t, 'synonyms', 'Lactobacillus reuteri') > 0
RETURN t.id AS tax_id, t.title AS current_name, t.rank AS rank,
       t.synonyms AS synonyms,
       text_bm25(t, 'synonyms', 'Lactobacillus reuteri') AS score
ORDER BY score DESC LIMIT 3

-- and the audit trail: how did each spelling actually resolve?
MATCH (t:Taxon {id: 47715})-[r:REPORTED_BY]->(s:Signature)
RETURN r.reported_name AS as_printed, r.reported_tax_id AS as_given,
       r.resolution_status AS status,
       r.resolution_normalized AS needed_authority_stripping,
       r.resolution_note AS note, count(s) AS signatures
ORDER BY as_printed
```

*Golden check:* `Lactobacillus reuteri` → **1598** with
`status = "synonym"` and `needed_authority_stripping = true`, because NCBI keeps
that binomial **only** in authority-decorated form (C4) — a resolver that indexes
name classes literally returns `unresolved` for it and for *Clostridium
difficile*, and the failure looks like a data gap.

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

*Status:* **`pending-source`: KEGG / Reactome — and misleading if unqualified.**
*Fields:* pathway id · gene · organism rank · whether the assignment is
genome-inferred.

```cypher
-- pending: HMDB/MiMeDB for PRODUCES, KEGG + Reactome for PARTICIPATES_IN
MATCH (t:Taxon {id: 239935})-[p:PRODUCES]->(m:Metabolite)-[:PARTICIPATES_IN]->(pw:Pathway)
RETURN m.title AS metabolite, pw.id AS pathway, pw.title AS pathway_name,
       pw.source AS pathway_source, pw.species AS pathway_species,
       p.evidence_level AS production_level,
       p.knowledge_level AS production_knowledge,
       'capability, not production' AS reading
ORDER BY pathway_source, pathway
```

*The qualifier is part of the answer.* Reactome's 23,603 pathways span **16
model organisms and not one gut commensal**, so a Reactome hit says the
*metabolite* participates in a human pathway, never that the taxon runs it.
KEGG carries microbial maps but **no taxid at all** (its organism route was
retired upstream) and ships under a restrictive licence that keeps the whole
slice behind a build flag. So the taxon→pathway assignment is genome-inferred in
every case available here, and gutSMASH *measured* gene abundance to be "almost
completely uncorrelated" with metabolite level in 1,135 individuals; PICRUSt2's
overlap with true metagenome results collapses from 654 to 66 KO terms. The row
is labelled `capability, not production` for that reason, and gutSMASH's MGC
types (which encode substrate and product in the type name) are the source that
would make the claim direct — not fetched.

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
-- the per-field census the audit's single percentage rolls up (C17: the
-- edge_property_violation procedure names only the FIRST missing property,
-- so a breakdown built from it under-counts every field but one)
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
**15,985 of 105,097 edges = 15.20%** on the 2026-09-03 two-source build
(BugSigDB alone: 14,349 of 103,461 = 13.87%). **The rise is the audit working,
not a regression:** all 1,636 gutMDisorder edges are violations, because that
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
`"unknown"` — so 17 further edges carry a level that means nothing and no
required-property check can see them. That is deliberate (never silently
"observational") and it is why `level_unknown` is a column here.
*G10's expansion factor* belongs in this report too: edges per source record,
per source, published rather than assumed.

### D16 — "Shortest path between any two entities" (A5.3)

*Status:* **`answerable-now`**, with a caveat that is part of the answer.

```cypher
MATCH p = shortestPath((t:Taxon {id: 853})-[*..4]-(d:Disease {id: 'MONDO:0005011'}))
RETURN length(p) AS hops,
       [n IN nodes(p) | labels(n)[0]] AS types,
       [n IN nodes(p) | n.title]      AS names

-- the evidence path, asked for explicitly rather than inferred from the shortcut
MATCH p = (t:Taxon {id: 853})-[:REPORTED_BY]->(s:Signature)-[:IN_CONDITION]->(d:Disease {id: 'MONDO:0005011'})
RETURN s.id AS signature, s.evidence_level AS level, s.study_design AS design,
       s.group_0_size AS n0, s.group_1_size AS n1, s.pmid AS pmid LIMIT 5
```

*Golden check:* returns **1 hop** where a direct `ASSOCIATED_WITH` exists — the
flattened edge doing its job — and the three-hop
`Taxon → Signature → Disease` walk returns the evidence that shortcut stands
for. *Caveat, from G10:* over a graph of ~1.14M edges a shortest path routes
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

*Golden check (measured):* **8,238 of 56,124 (taxon, condition) pairs carry both
`increased` and `decreased`, and 47,232 of 56,124 — 84.2% — rest on a single
study** (BugSigDB alone: 8,114 and 46,809 of 55,445, 84.4%). So `single_cohort` is the default exclusion for every ranked D-query,
not a rare flag. The named fixture is D2's: *Fusobacterium nucleatum* ×
colorectal cancer returns `directions = ['increased','decreased']`, `n_edges =
40`, `n_studies = 21`. **The query reports the disagreement; it never resolves
it, and no majority rule is applied anywhere in the graph.** T1D and T2D pairs
are a standing fixture because they are the measured worst case: >90% of
published findings for both were nonrobust to model specification.

### D18 — "Is this T2D association a drug effect?" — the metformin confounding check

*Status:* **`pending-source`: MASI**. *Fields:* D2's, joined to a drug→taxon
layer, plus D11's confounder columns once they are loaded.

```cypher
-- pending: MASI (drug->taxon); metformin is CHEMBL:CHEMBL1431
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0005148'})
MATCH (drug:Drug {id: 'CHEMBL:CHEMBL1431'})-[a:ALTERS_TAXON]->(t)
WITH t, r.direction AS direction_in_t2d, r.evidence_level AS t2d_level,
     a.alteration_effect AS metformin_effect, a.pmid AS metformin_pmid,
     count(DISTINCT r.study_id) AS t2d_studies
RETURN t.title AS taxon, direction_in_t2d, t2d_studies, t2d_level,
       metformin_effect, metformin_pmid,
       'competing explanation' AS reading
ORDER BY t2d_studies DESC
```

*Fixtures, from Forslund et al. (Nature 528:262, 2015, PMID 26633628; 784
metagenomes across three countries):* an ***Escherichia*** increase and an
***Intestinibacter*** decrease are **metformin effects, not T2D signals** — the
latter consistent across all three cohorts; a ***Lactobacillus*** increase
attributed to unstratified T2D was "eliminated or reversed" when controlling for
metformin; and increased butyrate/propionate production potential — a "beneficial
SCFA producer" signal — was the drug, not the disease, which bears directly on
D5 and D10. Verbatim: "metformin treatment status could be reliably recovered
from microbial composition using SVMs, **metformin-untreated T2D status itself
could not**". *Why the status is `pending` and not `descoped`:* without the
drug→taxon layer the graph physically cannot offer metformin as a competing
explanation, which is the second independent argument for closing Gap 3.
Generalised: of 41 drug categories, 19 associated singly with the microbiome and
only **6** survived multi-drug correction; taxonomic associations fell 154 → 47.

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
| `answerable-now` | **9** | D1, D2, D3, D4, D9, D11, D15, D16, D17 |
| `partial` | **3** | D10, D12, D14 |
| `pending-source` | **6** | D5, D6, D7, D8, D13, D18 |
| `descoped` | **2** | D19, D20 |
| **total** | **20** | |

Which source closes which pending query: **MiMeDB** → D5 (and D10's, D13's
metabolite legs); **NJC19** → D6; **CARD** → D7 (and D10's AMR leg); **MASI** →
D8, D18; **KEGG/Reactome** → D13's pathway leg. **gutMDisorder has landed**
and closed D4's intervention leg. Of the original five `partial` queries, **two
needed no new source at all** — D11 is closed (three column names declared, one
more extracted), and D14's non-specificity half already works. The remaining
two (D10, D12) each split cleanly into an answerable leg and a named pending
one.

# How microbiome researchers actually use integrated taxon–disease / metabolite / pathway / drug / AMR data

Research input for **Part B** of `docs/usecases-and-pitfalls.md`. Every claim is
tied to a citable source — a paper, a database's own documentation, a tool's
docs, or a published protocol. Where something is a synthesis rather than a
stated fact it is marked **[inference]**. Where a fact could not be verified it
says **not found** rather than guessing.

Part A (A3) forbids speculative "a graph could enable…" reasoning, so nothing
below is included unless someone is demonstrably doing it today.

Contents:

1. [The database publications and their stated use cases](#1-the-database-publications-and-their-stated-use-cases)
2. [Analysis workflows that consume this data](#2-analysis-workflows-that-consume-this-data)
3. [Evidence grading](#3-evidence-grading)
4. [Criticisms of microbiome association databases and KGs](#4-criticisms-of-microbiome-association-databases-and-kgs)
5. [Candidate acceptance queries](#5-candidate-acceptance-queries)

Two access caveats that bound what is below. **Reddit and Biostars were
unreachable** during this research (connection refused / HTTP 403), so the thin
forum material in §4.24 is an access failure, not community silence. And several
source sites refuse programmatic fetching or are down entirely — `bugsigdb.org`,
`hmdb.ca`, `mimedb.org` and `vmh.life` return HTTP 403, while
`disbiome.ugent.be`, MDAD's host, MACADAM and AGORA2's QC site were unreachable
on 2026-09-02. Facts drawn from papers, mirrors or export repos rather than the
live site are flagged where it matters.

---

## 1. The database publications and their stated use cases

### 1.1 The one-paragraph summary

Six things fell out of the survey that change the schema, and they are worth
stating before the per-database detail:

- **The signature, not the pairwise edge, is BugSigDB's unit.** A study contrast
  produces *two* signatures (up-set and down-set) and the enrichment workflow
  operates on the set. Flattening to 34 independent taxon→disease edges destroys
  the primary use case.
- **The direction reference group differs across every source.** BugSigDB is
  "Abundance in Group 1" (exposed group); Peryton is "relative to group 2";
  GMrepo uses a signed LDA against the health arm; Disbiome is patient-vs-control.
  A unified `INCREASED_IN` edge must carry the **comparator**, not just a sign.
- **Over half of Peryton's edges are disease-vs-disease, not disease-vs-health**
  (4,200 of 7,977, 52.65%). Ingesting them as "taxon associated with disease X"
  without the contrast is wrong.
- **Effect sizes essentially do not exist** in the curated taxon–disease
  resources. BugSigDB, Peryton and Disbiome store none. Only GMrepo carries a
  continuous LDA score, and only GMrepo v3 and MicroPhenoDB publish a
  cross-study confidence measure.
- **Consumption edges exist, but not in any source on the current list.** They
  come from NJC19 (curated, CC0) or from genome-scale model exchange reactions
  (AGORA2/APOLLO + MICOM/SMETANA, computed).
- **Licensing is not uniform and several sources are NC.** BugSigDB (ODC-BY 1.0),
  MicroPhenoDB (CC BY 4.0), NJC19 (CC0) and CARD's *ontology* (CC BY 4.0) are
  the permissive ones. gutMDisorder, GMrepo, Peryton, MiMeDB, HMDB and gutMGene
  are CC BY-NC. CARD's sequences, models and prevalence data are McMaster
  proprietary and explicitly prohibit commercial-organisation use.

### 1.2 BugSigDB

Geistlinger L, et al. *BugSigDB captures patterns of differential abundance
across a broad range of host-associated microbial signatures.* Nat Biotechnol
42:790–802 (2024). PMC11098749 ·
https://pmc.ncbi.nlm.nih.gov/articles/PMC11098749/ ·
https://www.nature.com/articles/s41587-023-01872-y

**Stated use cases.** Systematic comparison of a new study's signature against
published results; identifying conditions with *consistent* differential
abundance across independent studies; **bug set enrichment analysis** using
gene-set methods; microbe co-occurrence / mutual-exclusivity analysis. Four
worked examples in Results:

1. *Replication analysis* — 1,194 fecal signatures from 311 studies scored for
   cross-study consistency. HIV infection and antibiotic treatment were the most
   reproducible (semantic similarity 0.68 and 0.64, p < 0.05); antibiotic
   signatures consistently lose *Bifidobacterium* and *Blautia*.
2. *Colorectal cancer enrichment* — ten CRC datasets (N = 662 cases / 653
   controls) tested against the whole corpus; ORA found 19 enriched signatures at
   FDR < 0.05, **11 of them from oral body sites**, read as support for
   oral-to-gut introgression.
3. *Cross-body-site clustering* — 27 metasignatures; aerobic (oral, nasal)
   separated from anaerobic (vaginal, GI) sites.
4. *Co-occurrence vs healthy prevalence* — r = −0.84 (p = 3 × 10⁻⁶) between a
   genus's prevalence in 9,623 healthy controls and the proportion of signatures
   reporting it elevated in disease.

**Curated evidence fields — the 51-column schema.** `bugsigdbr::importBugSigDB()`
returns a flat frame with study/experiment metadata denormalised onto each row
(verbatim, from the Bioconductor vignette and
http://waldronlab.io/BugSigDBStats/articles/BugSigDBStats.html):

```
BSDB ID, Study, Study design, PMID, DOI, URL, Authors list, Title, Journal,
Year, Keywords, Experiment, Location of subjects, Host species, Body site,
UBERON ID, Condition, EFO ID, Group 0 name, Group 1 name, Group 1 definition,
Group 0 sample size, Group 1 sample size, Antibiotics exclusion,
Sequencing type, 16S variable region, Sequencing platform, Data transformation,
Statistical test, Significance threshold, MHT correction, LDA Score above,
Matched on, Confounders controlled for, Pielou, Shannon, Chao1, Simpson,
Inverse Simpson, Richness, Signature page name, Source, Curated date, Curator,
Revision editor, Description, Abundance in Group 1, MetaPhlAn taxon names,
NCBI Taxonomy IDs, State, Reviewer
```

A Bioc-3.16 mirror of the same vignette lists **48** columns — the set is
versioned and has grown, so pin the release you ingest.

Three-level entity model: **Study → Experiment (one contrast) → Signature (one
taxon list with one direction)**. `BSDB ID` encodes all three (`bsdb:83/1/2`).

**Direction encoding.** Column `Abundance in Group 1` ∈ {`increased`,
`decreased`}, relative to `Group 1` (the exposed/case group), with `Group 0` the
reference; `Group 0 name`, `Group 1 name`, `Group 1 definition` name them. One
contrast yields two sibling signatures. In the exported GMT the direction is a
name suffix: `bsdb:83/1/1_Obesity:before-surgery_vs_after-surgery_UP` /
`…_DOWN`.

**No per-taxon p-value, q-value, or effect size is stored.** Significance is
experiment-level only (`Significance threshold`, `MHT correction`, `LDA Score
above`); a taxon is in the signature iff the source paper called it significant
under that threshold. **[inference]** — from the complete 51-column list
containing no such field. This is a hard modelling constraint.

**Study design vocabulary** (live counts, retrieved 2026-09-02): `case-control`
825, `cross-sectional observational, not case-control` 543, `laboratory
experiment` 223, `prospective cohort` 169, `time series / longitudinal
observational` 157; the paper's 2022 snapshot adds `randomized controlled trial`
(4.4%) and `meta-analysis` (0.9%).

**Measurement technology is split across three columns**: `Sequencing type`
(`16S` 7,085 · `WMS` 1,578 · `PCR` 85 · `ITS/ITS2` 76 · `18S` 5), `16S variable
region` (encoded as **digit strings** — `34`, `4`, `12`, `123`, `45` — not
"V3-V4"), and `Sequencing platform` (`Illumina` 7,448 · `Roche454` 346 · `Ion
Torrent` 328 · `RT-qPCR` 143). **qPCR lives on the platform axis, not the
sequencing-type axis; culture-based is not a value — not found.**

Alpha diversity is first-class: six named columns (`Pielou`, `Shannon`, `Chao1`,
`Simpson`, `Inverse Simpson`, `Richness`), each holding `increased` /
`decreased` / `unchanged` / `not reported`.

**Scale.** Paper: >2,500 signatures, 628 studies, ~1,222 experiments, ~1,400
taxa. **Live snapshot 2026-09-02: 2,115 studies, 9,108 experiments, 14,845
signatures** — roughly 6× the published count. Size the graph off the live dump.
Group 1 sample size: median 21, mean 62.8, max 10,413.

**License / download.** **Open Data Commons Attribution 1.0** (the most
permissive taxon–disease source). Bulk CSV, `.gmt`, hourly/weekly snapshots at
https://github.com/waldronlab/BugSigDBExports, semi-annual Zenodo releases, the
`bugsigdbr` R package, and a web API. `bugsigdb.org` returns HTTP 403 to
programmatic fetches — use the exports repo.

**Authors' own caveats.** ">90% of the studies … are based on 16S amplicon
sequencing", limiting enrichment to genus level; "Some genera are functionally
heterogeneous, such as streptococci, which groups deadly pathogens with common
commensals"; "~45% of signatures containing fewer than five taxa … too small
individually to be effectively compared"; *Lactobacillus* and *Veillonella* "are
more likely false positives or at least are not well suited as candidate
biomarkers"; and "the majority of the curated information is too complex for
currently available text mining algorithms."

### 1.3 Disbiome

Janssens Y, et al. *Disbiome database: linking the microbiome to disease.* BMC
Microbiol 18:50 (2018). PMC5987391 ·
https://pmc.ncbi.nlm.nih.gov/articles/PMC5987391/

**Stated use case.** Researchers can "rapidly and easily find bacterial species
possibly correlated to specific diseases", to accelerate work on probiotics,
prebiotics and microbiota transplantation. **No worked case study.**

**Schema.** Relational with **Experiment as the central entity** — "the
microbiome difference between a patient and control" — linked to *Organism,
Disease, Sample, Detection Method, Host, Control, Response, Publication,
Location, Reference Classification Database*. Diseases → **MedDRA** (Preferred
Term or Lowest Level Term); organisms → **NCBI and SILVA**, with a field
recording which. Over **25 detection methods** (qPCR, NGS, DGGE, RFLP, DNA
microarray) and **50 sample types**.

**Direction.** Two-tier. Every experiment carries a qualitative outcome —
**`elevated` or `reduced`**. Quantitative outcome is optional: "When absolute
data is not available, the microbial differences are only presented by the
qualitative outcome." The response unit is *detection-method-dependent*, so
quantities are **not comparable across methods**. No p-value field is described.

**Study design.** No case-control/cohort field. Instead a **16-question
reporting-quality questionnaire** (4 reporting, 5 analysis, 7 design parameters —
including control-group definition, matched controls, blinding, sample/control
size). Detection method distinguishes technology but does **not** separate 16S
from shotgun — both are "next-generation sequencing".

**Scale.** Paper: >190 diseases, >800 organisms, from ~500 qualifying
publications screened out of ~20,000 (2009–2018 window). Widely-cited later
figure: 5,573 associations / 1,098 microbes / 240 diseases. Current live counts
**not found** — `disbiome.ugent.be` was unreachable (ECONNREFUSED) at check time.

**License.** Verbatim, typo included: "**Lisence: none. Restrictions for
non-academic users: none.**" JSON export.

**Caveats.** PubMed-only, 2009–2018; manual entry with quarterly updates; **no
animal studies**.

### 1.4 gutMDisorder (2020 / 2022)

Cheng L, et al. NAR 48:D554 (2020) ·
Qi X, et al. *gutMDisorder v2.0.* NAR 51:D717 (2023) ·
https://academic.oup.com/nar/article/51/D1/D717/6754909

**Stated use cases** — three documented, and the distinguishing one is
**intervention-conditioned** querying, which no other source supports:

1. Disease-stage comparison — "the abundance of Bacteroidetes was significantly
   decreased in patients with active CD, as compared with the inactive CD group".
2. Drug/intervention response — aldafermin patients showed "variations in the
   *Veillonella* genus".
3. Age-stratified intervention effect in mice.

The database documents two relation types: *"gut microbiota associated with
disorder"* and *"interventions change the composition of gut microbiota"*.

**Fields.** Microbe (NCBI Taxonomy); **host species Human or Mouse** (two
separately-counted datasets); phenotype as a *paired comparison string* (e.g.
`Acne Vulgaris/Health`); intervention typed as chemical/drug, diet/food/nutrition
or other; alteration; **source type literature vs raw sequencing dataset** (v2's
main addition); sample size; sex, age, BMI; sequencing platform; PMID. v2 also
serves abundance profiles at seven ranks (kingdom→species).

**Direction — four-valued, and deliberately not limited to significant changes.**
Verbatim: "Microbial alterations are not limited to statistically significant
increase and decrease, but also include the **presence and absence** of microbes
without statistical significance." So the vocabulary is
**increase | decrease | presence | absence**. For the raw-data half, direction is
computed by **LEfSe with LDA > 2** — a computed sign, not a curated one.

> **Modelling consequence:** a gutMDisorder edge does *not* guarantee statistical
> significance. Keep `alteration` as a 4-way enum; do not collapse
> presence/absence into increase/decrease.

**Technology.** 16S rRNA, shotgun quantitative metagenomics, qPCR, RT-qPCR;
v2's pipeline splits 16S → QIIME 2 and shotgun → MetaPhlAn3. No epidemiological
study-design vocabulary — **not found**.

**Scale (v2.0, Oct 2022).** Human literature 4,164 associations / 774 microbes /
346 phenotypes / 316 interventions from 548 publications; human raw-data 8,410 /
1,009 / 113 / 19 from 105 datasets (14,581 samples); mouse literature 2,251;
mouse raw-data 1,720. **≈16,545 associations total.**

**License: CC BY-NC.** Note the NC clause.

### 1.5 GMrepo

Wu S, et al. NAR 48:D545 (2020) · Dai D, et al. *GMrepo v2.* NAR 50:D777 (2022) ·
v3, NAR 54:D734 (2026) · https://gmrepo.humangut.info

**Structurally different from the rest: GMrepo is not a curated association
store.** It is a re-processed sample repository with curated host metadata, from
which associations are **derived by running LEfSe**. The taxon–disease edges are
computed, not read out of papers.

**Stated use cases.** Complex metadata queries ("locating fecal samples from
healthy individuals aged 18–25 with healthy BMIs"); per-project marker
identification; **cross-dataset marker comparison** (seven CRC projects —
*Fusobacterium nucleatum*, *Parvimonas micra*, *Gemella morbillorum* consistent,
rheumatoid arthritis inconsistent); and a **marker-centric cross-disease view**
(*F. nucleatum* across eight phenotype comparisons) to separate disease-specific
from generic markers. That last one is the disease-specificity question, served
directly.

**Fields.** Phenotype → **NCBI MeSH IDs**, organised as health-vs-disease pairs.
Curated per-run metadata: age, sex, country, BMI, antibiotic history, phenotype,
platform, sequence type, read count (v3 adds diet). **Two QC flags**: QC1 fails
runs with "<20 000 reads" or <50% retained after trimming; QC2 rejects any sample
where "a single taxon accounts for >99.99%". Abundances normalised to 100% per
rank.

**Direction — a signed LDA score**, not a word. LDA < −2 → health-enriched;
LDA > +2 → disease-enriched; magnitude = strength. Users can "exclude markers
showing inconsistent trends (e.g. significantly decreased in disease in one
project but significantly increased in others)".

**v3 adds a Marker Consistency Index (MCI)** — "the proportion of comparisons in
which a taxon was enriched in healthy samples", 0–100%, with **MCI > 75% =
consistently health-enriched, MCI < 25% = disease-enriched**. This is the only
ready-made cross-study confidence score published by any of these resources.

**Technology has hard downstream consequences**: 16S → QIIME2/DADA2 against
Greengenes, **genus-level markers only** (the UI's "Species" button is
"unclickable" for 16S); shotgun → MetaPhlAn2/4, species + genus.

**Scale.** v2: 353 projects, 71,642 runs (45,111 16S + 26,531 shotgun), 133
phenotypes, 592 marker taxa (350 species + 242 genera) across 47 phenotype pairs
from 83 projects. v3: 890 projects, 118,965 runs, 302 phenotypes, 1,299 marker
taxa across 167 phenotype pairs.

**License: CC BY-NC 3.0.** REST API with R/Perl/Python clients.

**Caveats.** "~30% of gut metagenomic samples did not have any of the three basic
information [age, gender, BMI], even after several rounds of manual curation."
Marker inconsistency is the *stated motivation* for the cross-dataset page.
Only 83 of 353 (v2) / 275 of 890 (v3) projects met marker-analysis criteria.
v3 adds: geographic imbalance, extraction-kit/platform batch effects, and
reliance on LEfSe alone — "different algorithms yield method-specific marker
sets".

### 1.6 Peryton

Skoufos G, et al. *Peryton: a manual collection of experimentally supported
microbe-disease associations.* NAR 49:D1328 (2021). PMC7779029 ·
https://pmc.ncbi.nlm.nih.gov/articles/PMC7779029/

**Stated use cases.** Form and refine hypotheses; "cross-validate their
experimental findings". **No worked case study** — the paper presents the
resource plus network/chord/hierarchy browsing.

**Fields, verbatim.** "bacterial abundance, the groups under study (including
group sizes, mean age and sex ratios), experimental design, study cohorts, sample
type, the applied high- or low-throughput techniques, **Next-Generation
Sequencing (NGS) sample accession numbers** and article metadata". Disease →
**MeSH**; microorganism → **NCBI Taxonomy**. The NGS accession field is a
provenance link back to raw data that the other curated sources lack.

**Direction.** The paper states only that "Bacterial abundance … **relative to
group 2** is indicated" — i.e. the **opposite reference convention from
BugSigDB's group-1-relative encoding**. The literal vocabulary
(increased/decreased) is **not found** in the retrievable text. Inclusion
requires statistical significance in the source paper, but no stored p-value or
effect size — **not found**.

**Study design.** 43 distinct experimental methods and 73 sample types as
browsing facets (enumerations not published). The design axis is the
**"relationship among groups"** facet, and it is binary in practice: **disease vs
healthy controls 3,777 entries (47.35%); different disease states 4,200 entries
(52.65%)**.

> **Modelling consequence:** more than half of Peryton's edges are
> disease-vs-disease. An edge ingested without its comparator is a different fact
> from the one Peryton curated.

**Scale (v1.0, 2020/2021).** 7,977 associations · 43 diseases · 1,396
microorganisms · 314 curated articles · 8 taxonomic ranks. Species-level: 1,718
(21.54%). Cohort >50: 4,611 (57.80%). No later version found.

**License: CC BY-NC.** TSV download.

### 1.7 MiMeDB

Wishart DS, et al. *MiMeDB: the Human Microbial Metabolome Database.* NAR
51:D611 (2023). PMC9825614 · MiMeDB 2.0, NAR 54:D623 (2026). PMC12807671

**Stated use cases.** Query/explore/interpret multi-omics against the microbiome;
"identification of microbial metabolites or microbially derived metabolites found
in stool samples, urine, or even in blood". **No worked case study** — the
figures are feature demos.

**Schema — the two categories that matter, verbatim.** *"The **'Microbial
Sources'** category contains data fields for each microbe's Superkingdom,
Kingdom, Phylum, Genus/Species, Genome map, and Host(s)."* and *"The
**'Metabolic Reactions'** category contains data fields for the metabolite's
Reaction identifier, the **Precursor molecule**, the **Product molecule**, the
Enzyme, the **Enzyme's source organism**, the **Reaction type**, and the relevant
References."*

Citations are present on Metabolic Reactions, Health Effects, Biospecimens and
Exposure Sources — **but are not listed among the Microbial Sources columns.**

**Production vs consumption: production-oriented.** MiMeDB 2.0's origin
assignment keys on "reactions in which each compound appears as a **product**".
A degradation/consumption edge type is **not found**. **[inference]** consumption
is only recoverable by treating `Precursor molecule` + `Enzyme's source organism`
as a derived edge.

**Evidence grading: none as a filterable field.** Nearest is a biospecimen-level
`Detection status` ∈ {detected and quantified, detected only} and a prose
curation policy applied at ingest ("only peer-reviewed sources… Exclusion
criteria included non-peer-reviewed reports, animal-only studies without
demonstrated human analogs, and in vitro findings lacking validation").
**[inference]** grading was consumed at curation time and discarded — you cannot
filter MiMeDB edges by evidence strength.

MiMeDB *does* classify metabolite **origin** on an evidence basis, which is a
usable second axis: **microbial-only** ("chemicals that can only be produced by
microbial enzymes or microbially-mediated reactions"), **host–microbe
co-metabolites** (requiring "at least one microbial-specific reaction … and at
least one human-specific reaction"), **human-only** ("no evidence of microbial
enzymes or microbial reactions").

**Scale.** v1.0: 24,254 metabolites (1,808 microbial-only, 14,210 host–microbe
co-metabolites), 1,904 microbes, 22,054 reactions. **v2.0 (2026): 29,295
metabolites, 3,725 microbes, 25,276 reactions, 23,106,015 pathways.** The
microbe→metabolite **edge count is not published** in either paper.

**License: CC BY-NC 4.0.** CSV/XML; v2.0 adds a per-microbe "download all related
metabolites as CSV" button — the most direct route to an edge list. `mimedb.org`
returns 403 to automated fetching.

**Caveats.** Predicted content is to be kept "in a separate data layer"; the
23.1 M pathways are **homology-propagated via BLAST against UniProt** —
**[inference]** orders of magnitude larger than the 25,276 curated reactions and
not the same evidence class. "The size and frequency of these publications now
exceed our capacity to manually keep MiMeDB as current as we would like."
**No AMR-gene entity exists.**

### 1.8 HMDB's "microbial origin" annotation

Wishart DS, et al. *HMDB 5.0.* NAR 50:D622 (2022). PMC8728138

**Direct answer: HMDB's microbial annotation is a categorical origin flag on the
metabolite, not a per-taxon link.**

The XML carries origin under `metabolite → ontology → origins` as a fixed value
list, rendered as **booleans with no organism slot**: `Food`, `Endogenous`,
**`Microbial`**, `Drug`, `Drug or Steroid Metabolite`, `Drug Metabolite`,
`Plant`, `Toxin/Pollutant`, `Cosmetic`. HMDB 4.0 confirms the ontology fields as
"(i) status (detected, expected), (ii) **origin (exogenous/endogenous/
microbial)**, (iii) biofunction, (iv) application, (v) cellular location".

HMDB 5.0 does claim more: "Much more detailed disposition data about the origin
(food, microbial, endogenous), **originating species**, biofluid and body site of
many metabolites … is now provided through **ChemFOnt**." This could **not be
verified** — hmdb.ca returns 403 and ChemFOnt's browser renders client-side.
**[inference]** ChemFOnt's own framing is food-centric and it imports *from*
MiMeDB, so species-level source terms are likely best developed for food.

> **Ingestion trap.** HMDB's `taxonomy` element is **ClassyFire chemical
> taxonomy, not organism taxonomy.** Do not map it to a `Taxon` node.

**Production vs consumption: neither.** The origin flag is not a directed edge at
all.

**License: CC BY-NC 4.0.** Practical caveat: the full XML "becomes clipped around
4GB, causing parsing failures" — stream-parse.

**Author caveat that matters for us, verbatim:** "the focus for this year's
update … precluded further expansion or updates with several other popular HMDB
data collections (such as **metabolite-disease, metabolite-gene or
metabolite-SNP associations**)." HMDB's disease layer was not updated in 5.0.

### 1.9 VMH / AGORA2 / APOLLO — the metabolic reconstructions

Noronha A, et al. *The Virtual Metabolic Human database.* NAR 47:D614 (2019) ·
Heinken A, et al. *Genome-scale metabolic reconstruction of 7,302 human
microorganisms for personalized medicine.* Nat Biotechnol 41:1320 (2023).
PMC10497413 · APOLLO: PMC10592896 (Cell Systems, PMID 39947184)

**This is the answer to Part A's use case 5, and the answer is "yes, but you
compute it".**

**Both directions are present, and direction is the sign of flux through an
exchange reaction.** Verbatim from AGORA2's Methods: *"For each retrieved
positive or negative data point, the capability of the respective model to **take
up or produce** the corresponding metabolite was calculated using FBA on
unlimited medium by either **minimizing or maximizing** the corresponding
exchange reaction, respectively."*

**The precomputed artifact is named but not published as a file.** From APOLLO:
*"The theoretical metabolite uptake and secretion potential on unlimited medium
… were computed through the **computeUptakeSecretion** function … the function
computes the minimal and maximal fluxes for each exchange reaction in a model
through **flux variability analysis**."* Result: **517 metabolites consumable,
434 secretable (360 overlapping), 1,248 producible internally.** Sibling
functions include `plotMetaboliteProducersConsumers` and
`summarizeFeaturesOnTaxonLevels` (which aggregates to species/genus/family/
order/class/phylum — solving rank aggregation).

But APOLLO's Data Availability names no supplementary uptake/secretion matrix.
**[inference] you will run `computeUptakeSecretion` yourself over downloaded
AGORA2/APOLLO models — a MATLAB + COBRA compute step, not a download.**

**AGORA2 scale and validation.** 7,302 strains / 1,738 species / 25 phyla; 98
drugs, 15 drug-metabolising enzymes, 1,440 drug-related reactions, 363 drug
metabolites. Validated against three independent experimental datasets —
**NJC19** (455 species / 5,319 strains, uptake+secretion), **Madin** (185
species, positive uptake only), **BacDive** (676 strains) — with accuracies
**0.82 / 0.84 / 0.81**; drug transformations 0.81.

**AGORA2's worked case study** is directly relevant: 616-subject Japanese cohort
(365 CRC, 251 controls), personalised models predicting drug-metabolising
potential — "only 53% of the microbiomes presented the capacity to metabolize
digoxin". Cross-feeding appears explicitly: "in two-step reactions, such as
levodopa degradation to m-tyramine, the drug conversion potential for the second
step was limited by the species abundance carrying out the first step."

**Authors' caveats, verbatim.** "Our knowledge about gut microorganisms remains
limited and, thus, any in silico reconstruction will be inherently incomplete."
False positives may reflect "nonfunctional genes or regulatory mechanisms"; and
a direct consumption warning — "for certain metabolites, for example, methionine
… in vivo association statistics were consistently inverse to the corresponding
in silico association statistics. These latter results may correspond to **net
uptake** of the metabolites by the microbial community."

**License.** AGORA2 article CC BY 4.0; **APOLLO is CC BY-NC-ND 4.0** (note the
NoDerivatives clause). `vmh.life` and its `_api` return 403 to automated fetching.
The AGORA2 QC site `metaboreport.live` is **dead**.

**APOLLO caveats.** 247,092 reconstructions from MAGs; average 997.92 reactions
(lower coverage than AGORA2); only 52.85% refined with experimental data;
**64.11% of strains unclassified at species level**.

### 1.10 NJC19 / NJS16 — the curated cross-feeding resource we are missing

Lim R, et al. *Large-scale metabolic interaction network of the mouse and human
gut microbiota.* Sci Data 7:204 (2020). PMC7320173 · data at Dryad
doi:10.5061/dryad.dr7sqv9v8 · predecessor NJS16: Sung J, et al. Nat Commun
8:15393 (2017). PMC5467172

**This is a directed, literature-curated transport network — the shape our graph
wants — and it is CC0.**

NJS16's schema, verbatim: *"a community member and a chemical compound are then
connected by a **(directed)** link if the organism can **import and/or export**
the metabolite, or **degrade** the macromolecule."*

Curation basis, verbatim: *"Metabolic information primarily used in this study
was **experimental evidence** of metabolite transport or macromolecule
degradation reported in literature… a careful read of hundreds of these sources
was done to discern which annotations were **experimentally verified**"*,
including "literature sources that report the messenger RNA or protein expression
for metabolic-byproduct-producing enzymes, or for metabolite-specific
transporters."

**Scale (NJC19).** 838 microbial species (766 bacteria, 53 archaea, 19
eukaryotes) + 6 host cell types; **8,224 small-molecule transport and
macromolecule degradation events**; **912 negative associations**; curated from
**769 research articles, reviews and textbooks**. Species-level. SCFAs are
first-class — acetate is the most frequently exported product (44.3% of species).

**License: CC0-1.0** (verified via the Dryad API) — the only fully unrestricted
resource in the whole survey.

### 1.11 MASI, MDAD — drug–microbe resources

**MASI.** Zeng X, et al. *MASI: microbiota—active substance interactions
database.* NAR 49:D776 (2021). PMC7779062. **The only drug resource with a
directed, typed edge out of the box.** Verbatim: *"The bacteria and active
substance interactions are further divided into the subclasses of **bacteria
alteration of active substances** and **active substance alteration of
bacteria**."* — **bacteria → substance: 4,001 unique pairs; substance → bacteria:
7,770 unique pairs.** Fields: bacterium, substance, alteration-effect description,
experimental conditions ("chemical exposure dose and duration"), host effects,
PubMed ID. Rank: "taxonomic information down to genus level". Evidence grading is
a single binary inclusion criterion: *"Only the experimentally determined
interactions, modulations, or regulations were included in MASI."* Scale: 1,051
pharmaceutical + 103 dietary + 119 herbal + 46 probiotic + 142 environmental
substances × 806 species; 56 diseases; 784 microbiota–disease associations.
Caveat: "about 83% of bacteria species in MASI have <10 known interactive
substances." Liveness **degraded** — expired TLS certificate. No separate
database license.

**MDAD.** Sun Y-Z, et al. *MDAD: A Special Resource for Microbe-Drug
Associations.* Front Cell Infect Microbiol 8:424 (2018). PMC6292923. Worked case
study, verbatim: *"cefotaxime can kill Acinetobacter baumannii by targeting
beta-lactamase. In MDAD, we can find many other drugs that target beta-lactamase,
including aztreonam, cloxacillin, imipenem and so on."* — **[inference]** that is
a target-mediated repositioning walk, and it requires a **microbial protein/RNA
target node** between drug and microbe, not a direct edge.

Fields: *"drug name, microbe name and the PubMed ID reference"*, plus DrugBank
link, **strain**, and **target** (UniProt-linked). **Two evidence classes,
verbatim:** *"The **experimentally supported** associations were demonstrated by
lab experiments reported in publications. The **clinically supported**
microbe-drug associations were FDA-approved or confirmed to be effective in
clinical trials."*

**Direction is ambiguous and this is MDAD's biggest weakness.** The paper names
two conceptually opposite categories ("microbes as drug targets and
pharmacomicrobiomic interactions") but **does not type edges per record**.
**[inference]** a naive `(:Microbe)-[:ASSOCIATED_WITH]->(:Drug)` will conflate
antimicrobial killing with drug metabolism; the presence/absence of a UniProt
target is the best available discriminator.

Scale: 5,055 entries / 1,388 drugs / 180 microbes / 824 strains / 993 references.
**Liveness: almost certainly dead** — connection refused, and the Wayback Machine
has never captured the URL. A GitHub zip (no license file) is the only obtainable
copy.

Related and better-structured: **aBiofilm** (Rajput et al., NAR 2018), which MDAD
drew from, carries **agent type, organism/strain, concentration, percentage
inhibition, biofilm stage targeted, mechanism of action, assay media** — the best
per-edge evidence schema in this cluster. **[inference]** worth modelling
directly rather than through MDAD's flattened re-import.

### 1.12 AMDB — a disambiguation, because the brief's premise was partly wrong

The AMDB in NAR 2022 is **Yang, Park, Jung & Chun**, *"AMDB: a database of
animal gut microbial communities with manually curated metadata"*, NAR 50:D729.
PMC8728277.

> **It contains no drugs, no diseases, no metabolites, no pathways and no AMR
> genes.** It is 16S-derived taxonomic abundance plus host metadata: SRA
> accession, host taxonomy, diet type, sampling site, alpha diversity. ASV-level
> against EzBioCloud at ≥97% identity, bacteria only. 2,530 samples / 34 projects
> / 467 animal species / 10,478 taxa. **No directed interaction edges exist.**
> **[inference]** this is a host-context abundance substrate for taxon nodes, not
> an interaction source — it does not belong on the source list for this graph.

Do not confuse with: **AMDB = Animal Metabolite Database** (amdb.online, animal
tissue metabolite concentrations, CC BY 4.0, unrelated); **AMDD** (Antimicrobial
Drug Database, site dead); **AMPDB** (Anti-Microbial Peptide Database); **ARDB**
(Antibiotic Resistance Genes Database). **No antimicrobial-peptide or
antimicrobial-drug database named "AMDB" exists.**

### 1.13 CARD (and RGI)

Alcock BP, et al. *CARD 2023.* NAR 51:D690 (2023). PMC9825576 · CARD 2020, NAR
48:D517 · https://card.mcmaster.ca

**Stated use cases.** Annotate genomes/metagenomes; prevalence statistics
("blaNDM-1 is found in 47 pathogens"); mobile-element association; reference sets
for metagenomic read alignment; pathogen-of-origin prediction; surveillance. The
worked case study is the construction of CARD-R itself: RefSeq assemblies →
plasmid/chromosome/island split → RGI **retaining only Perfect and Strict hits** →
322,710 unique nucleotide ARG allele sequences.

**Four ontologies:** ARO (resistance), MO (detection models), RO (relations),
**NCBITaxon** "for tracking the source organisms and taxonomic distribution".

**ARO relations, verbatim:** `is_a`, `part_of`, `has_part`, `participates_in`,
**`confers_resistance_to_drug_class`**, **`confers_resistance_to_antibiotic`**,
`targeted_by`, `targeted_by_antibiotic`, `regulates`, `derives_from`,
`evolutionary_variant_of`, `is_small_molecule_inhibitor`. Naming drift: CARD 2017
used `confers_resistance_to_drug` / `targeted_by_drug`. `part_of` is **narrow** —
"restricted to association of sub-units with their large multi-unit protein
complexes", not generic containment.

**Nine detection models; RGI supports five** — protein homolog (PHM), protein
variant (PVM), protein overexpression (POM), rRNA gene variant (RVM),
nonfunctional insertion (NFI). Verbatim: "RGI does not currently support the PKM,
PDM, GCM or EPS model." The **bit-score cut-off is hand-curated per model**.

**RGI hit categories, verbatim.** Perfect — "detects AMR proteins with an exact
(100%) match to a CARD reference sequence". Strict — "more flexible, allowing for
variation from the CARD reference sequence as long as the sequence falls within
the curated BLAST bit score cut-offs". Loose — "works outside of the detection
model cut-offs … will also catalog homologous sequences and spurious partial
hits". `--include_nudge` reclassifies ≥95%-identity Loose hits as Strict, flagged
in a `Nudged` column.

**The curated/predicted split, which is the single most reusable evidence design
in the whole survey.** CARD canonical requires *"Sequences available in GenBank
with clear experimental evidence of elevated MIC in a peer-reviewed journal"*.
CARD Prevalence / Resistomes & Variants is *"in silico prediction of AMR alleles"*
and **"they are not experimentally characterized genes"** — which is why RGI
refuses them for `rgi main`. Prevalence is computed as: "if 50 WGS assemblies
were analyzed and blaNDM-1 was predicted by RGI in 40, the calculated prevalence
would be 80%" — **sequence-detection prevalence, not phenotype prevalence.**

**The caveat that must be carried into the graph, verbatim from the CARD FAQ:**

> *"a **PERFECT hit does not indicate if the AMR gene is expressed or if it
> results in elevated MIC** in the pathogen of interest. Activity of AMR genes
> can be pathogen and strain specific."*

Even the strongest tier does not license an inference to phenotype. Also:
**β-lactamases are an explicit exception to the elevated-MIC curation standard**
— per-gene-family evidence heterogeneity you must model.

**Scale.** v3.2.4: 6,627 ARO terms, 5,010 reference sequences, 1,933 curated
variant mutations, 5,057 detection models, 458 AMR gene families, 64 drug
classes, 10 resistance mechanisms, 367 antimicrobials. Live 2026-09-02: 9,051
terms / 6,453 sequences / 6,489 models; ontology v4.0.2 (Aug 2026). CARD-R: 414
pathogens / 279,120 alleles, but **prevalence data is dated Nov 2023 while the
ontology is Aug 2026, and homepage/download/prevalence counts mutually disagree
(413 vs 414 pathogens; 276,270 vs 279,120 alleles). Pin an explicit version plus
prevalence date.**

**License — CARD is NOT fully open.** Verbatim: *"Use or reproduction of
Materials on the site, in whole or in part, by any **commercial organization
whether or not for non-commercial (including research) or commercial purposes is
prohibited**, except with written permission of McMaster University."* Carve-out:
*"Ontologies at the Comprehensive Antibiotic Resistance Database are freely
available under the Creative Commons CC-BY license version 4.0."*
**[inference] ARO structure is redistributable; reference sequences, detection
models, bit-score cut-offs, curated SNP lists and Prevalence data are not.**
ARO is separately queryable via EBI OLS4 (verified working).

### 1.14 MACADAM

Le Boulch M, et al. *MACADAM: MetAboliC pAthways DAtabase for Microbial taxonomic
groups.* Database (Oxford) 2019:baz049. PMC6487390

> **Liveness: appears decommissioned.** Both `macadam.toulouse.inra.fr` and the
> post-rename `.inrae.fr` **fail DNS resolution** (2026-09-02). Data is pinned to
> RefSeq 92 (Jan 2019) against a stated 6-month cadence. **Treat as archival.**

**Worked case study, directly relevant to us:** the L-lysine fermentation to
acetate and butanoate pathway (MetaCyc **P163-PWY**), "a pathway of interest in
understanding the interactions between host and gut microbiota" — present in 992
organisms, median PS 0.4, median PFS 0.7.

**Method.** Pathway Tools v20.5 (PathoLogic) against **MetaCyc**, over RefSeq 92
complete genomes plus MicroCyc PGDBs = 13,509 PGDBs. **MinPath is not used.**
Verbatim: "each PGDB is associated with an organism, i.e. with a species or a
strain taxID and PGDBs do not exist at upper taxonomic ranks." **[inference]** a
genus-level statement is therefore a derived aggregate (median score + member
count), not a stored fact.

**Two numeric scores, no named classes.** **PS** (pathway score): "A value of 1
indicates that all the enzymes required for the pathway are present in the
genome … A value of 0 indicates that none of the enzymes are present." Mean
bacterial PS 0.82 ± 0.24. **PFS** = enzyme redundancy, 0–77.

> **PS is not monotonic confidence.** Verbatim: "MACADAM contains eight pathways
> in 1519 organisms with a PS equal to 0. The pathway is still present because of
> the **functional inference applied by MetaCyc experts, information that they
> cross-reference with phenotypic evidence described in the literature**."
> **[inference]** a KG treating PS as a single confidence float conflates
> curator-asserted-with-zero-genomic-support against half-complete-genomic-
> evidence.

Produces-vs-consumes typing on metabolites is **not an exposed field — not
found**. No explicit "these are predictions, not measurements" statement —
weaker than gutSMASH's.

### 1.15 gutSMASH

Pascal Andreu V, et al. *gutSMASH predicts specialized primary metabolic pathways
from the human gut microbiota.* Nat Biotechnol 41:1416 (2023). PMC10423304 ·
web server NAR 49:W263 (2021). PMC8262752 · gutSMASH 2.0, J Mol Biol (2026)

**Worked case studies — and one is a warning to build the schema around.**

1. 4,240 genomes → 19,890 MGCs; "marked differences in pathway distribution among
   phyla… These data **explain taxonomic differences in short-chain fatty acid
   production** and suggest a characteristic metabolic niche for each taxon."
2. BiG-SCAPE clustering → 12,259 putative novel clusters in 932 families.
3. **The negative result.** In 1,135 LifeLines DEEP metagenomes with matched
   plasma and faecal metabolomics: *"the level of microbiome-derived metabolites
   in plasma and feces is **almost completely uncorrelated** with the metagenomic
   abundance of corresponding metabolic genes"* — r ≈ −0.04 to 0.24 across 14
   metabolites.

**Output.** MGCs (metabolic gene clusters) detected by rules over Pfam domain
combinations plus custom subfamily pHMMs. Per-MGC: coordinates, contig, **MGC
type** (the rule that fired), **MGC class**, genes colour-coded core/transport/
regulatory, KnownClusterBlast similarity %. Input is a single genome →
**strain-level; no aggregation**. **Every gene cluster type carries a PubMed ID**
in the Glossary — **[inference]** maps cleanly to
`MGC -[instance_of]-> MGCType -[supported_by]-> Publication`.

**Both directions, encoded in the type names.** Production: `Acetate to
butyrate`, `Glutamate to butyrate`, `Threonine to propionate`, `Succinate to
propionate`, `Acrylate to propionate`, `Arginine to putrescine`, `P-cresol
synthesis`, `Bilirubin to urobilinogen`, `r-butyrobetaine to TMA`. Consumption /
degradation: `Carnitine caiTABCDE`, `Lysine degradation`, `Gallic acid
metabolism`, `Uric acid to Xanthine`, **`Taurine to H2S`**, `Sulfoquinovose to
sulphonate`, `Histidine to glutamate`, `Glycine cleavage`, `AAA reductive
branch`. **[inference]** the substrate and product are recoverable from the type
name + class — a controlled vocabulary of ~56 strings to curate once by hand;
they are not structured output fields.

Classes, verbatim: **Aliphatic amine / npAA / Aromatic / SCFA** ("fatty acids
with 5 carbon atoms maximum") **/ SCFA-other / Other / E-MGC** (energy-capturing)
**/ Putative** ("gene clusters of unknown function"), plus hybrid.

**No per-hit confidence score** — detection is binary rule matching. The only
grading axis is **`known` vs `putative`**.

**License: AGPL-3.0+** (network-triggering copyleft if you serve derived
computation). **No precomputed catalogue over UHGG exists — not found**; no
Zenodo deposition of the 19,890-MGC set. **[inference] you will run gutSMASH
yourself over your chosen genome catalogue.**

**Authors' caveat, and it is a measurement rather than a disclaimer:**

> *"**gene abundances in metagenomes are not (on their own) a useful predictor of
> metabolic outputs. This finding has important implications for analyses that
> make metabolic inferences from gene abundances.**"*

### 1.16 Secondary resources worth knowing

- **MicroPhenoDB** (PMC8377004) — 5,677 associations / 1,781 microbes / 542
  phenotypes; **phenotype ontology is EFO**, so it joins directly to BugSigDB.
  Direction recorded as **+1 increased / −1 decreased**. Ships a confidence score
  in [−1,1] weighting evidence source — **IDSA guideline 1.0, NCIT 0.5,
  literature 0.25** — the only resource weighting curated-guideline evidence above
  literature. Also carries a microbe → core-gene layer. **CC BY 4.0.**
- **Amadis** (PMC8317061) — 20,167 associations, the largest raw count, but its
  direction vocabulary is **causal, not abundance-directional**: "Microbiota
  promote disease progression" / "Microbiota inhibit disease progression".
  **[inference] different edge semantics — do not merge into an up/down axis.**
- **HMDAD** (Ma et al., Brief Bioinform 2017) — 483 associations, 39 diseases,
  data frozen at July 2014. Direction `Eij ∈ {1, −1}`, publication count as
  weight. Superseded on every axis; its remaining value is as the benchmark set
  most microbe–disease link-prediction papers evaluate on.
- **gutMGene** (PMC11701569) — three edge types (microbe–metabolite, metabolite–
  host gene, microbe–host gene) with an evidence vocabulary worth borrowing:
  *"**Causal** associations stem from controlled experiments that manipulate a
  specific variable … Conversely, **correlational** associations are derived from
  statistical correlation analyses."* But note 4,860 literature-based vs
  **2,476,040 reconstruction-based** associations, and the causal/correlational
  grading applies **only to the 4,860**.
- **BacDive** (NAR 2025) — 97,334 strains, and it separates measured from
  predicted properly: genome-based predictions live in a separate section, marked
  with an AI icon and a confidence value, and only >90%-confidence predictions
  are integrated. **CC BY 4.0**, REST API. But SCFA coverage is sparse — a spot
  check of *Clostridium butyricum* DSM 10702 lists only "butyricin 7423" under
  Metabolite production, with **acetate and butyrate absent**.

---

## 2. Analysis workflows that consume this data

### W1. Enrichment of a differential-abundance result against curated signatures

**Input.** The researcher has run a differential-abundance test on their own
cohort (16S or shotgun) and holds a thresholded list of taxa — typically
genus-level from 16S, species-level from MetaPhlAn — with direction and a
p/q value per taxon.

**Question.** *"My 34 genera that go up in cases — has anyone seen this before,
and in what condition?"* Concretely: which published signatures are enriched in
my hit list, and is my result specific to my disease or a generic dysbiosis
pattern?

**Output.** A ranked list of BugSigDB signatures (each = one published
experiment's up- or down-set) with an enrichment p-value, letting the researcher
say "my up-set recapitulates the CRC signature of Wu et al." or "my up-set is
just the generic post-antibiotic loss pattern".

**Needed fields.** Signature membership as NCBI tax_ids at a stated rank;
direction per signature; condition (EFO); body site (UBERON); host species;
`Sequencing type` and `16S variable region` — because a genus-level 16S signature
and a species-level shotgun signature cannot be intersected without cutting to a
common rank; group sizes, to down-weight tiny studies; PMID.

**Source(s).** BugSigDB is the only source in the current list shaped as
*signatures* (sets) rather than pairwise edges. `bugsigdbr` exports them via
`writeGMT()` with `tax.id.type = c("ncbi","metaphlan","taxname")` and `tax.level`
— exactly the GMT shape gene-set tools expect. `BugSigDBEnrich`
(https://github.com/waldronlab/BugSigDBEnrich, Shiny app at
https://shiny.sph.cuny.edu/BugSigDBEnrich/) runs the enrichment. Geistlinger et
al. call it **bug set enrichment analysis** and benchmark ORA, PADOG and CBEA.
Taxonomy-aware alternative: **CBEA** (competitive balances for taxonomic
enrichment analysis, PMC9154102), which handles compositionality via an isometric
log-ratio transform.

**Citation.** Geistlinger et al., Nat Biotechnol 42:790 (2024), PMC11098749 ·
`bugsigdbr` vignette,
https://master.bioconductor.org/packages/devel/bioc/vignettes/bugsigdbr/inst/doc/bugsigdbr.html
· Nguyen Q et al., CBEA, PMC9154102.

> **Schema consequence — the biggest one in Part B.** A pairwise
> `(taxon)-[ASSOCIATED_WITH]->(disease)` model loses the *set*. Enrichment needs
> the **signature as a first-class node** grouping the taxa of one experiment with
> one direction, not 34 independent edges.

### W2. Biomarker discovery validated across cohorts

**Input.** Several public case-control cohorts for one disease — typically from
**curatedMetagenomicData** (>22,000 uniformly processed samples, 94 studies, 42
countries; MetaPhlAn3 taxonomy + HUMAnN3 function; manual curation by 17
curators) — plus the researcher's own cohort.

**Question.** *"Which taxa separate cases from controls in a way that survives
being trained on cohort A and tested on cohort B — and is the separation specific
to this disease or shared with others?"*

**Output.** A model with cross-study AUROC, a short list of features that
generalise, and an explicit disease-specificity assessment.

**Needed fields.** Per-cohort abundance matrices with sample-level metadata (the
KG does not hold these). *From an association graph* the workflow needs: which
other diseases each candidate biomarker is reported for, at what direction, in
how many independent studies, with sample sizes — the disease-specificity check.
Confounder fields matter: BugSigDB's `Antibiotics exclusion`, `Matched on`,
`Confounders controlled for`.

**Source(s).** curatedMetagenomicData for the matrices; **SIAMCAT** for the ML
plus confounder checks; **xMarkerFinder** as a published four-stage protocol
(differential signature identification → model construction → model validation →
biomarker interpretation); BugSigDB / Disbiome / GMrepo for cross-disease
specificity. **GMrepo v2/v3 is built for exactly this**: 592 marker taxa across
47 phenotype pairs (v2) / 1,299 across 167 (v3), with "a marker-centric view to
allow users to check if a marker has different trends in different diseases", and
v3's **MCI** as a ready-made consistency score.

SIAMCAT's headline finding is itself a design requirement: in a meta-analysis of
10,803 fecal metagenomes, "when ML models were naively transferred across
studies, they lost accuracy and disease specificity".

**Citation.** Pasolli E et al., curatedMetagenomicData, Nat Methods 14:1023
(2017), https://bioconductor.org/packages/curatedMetagenomicData · Wirbel J et
al., SIAMCAT, Genome Biol 22:93 (2021), PMC8008609 · Zheng H et al.,
xMarkerFinder, Nat Protoc (2024), PMID 38745111 · Dai D et al., GMrepo v2, NAR
50:D777 (2022).

### W3. Probiotic / live-biotherapeutic candidate selection

**Input.** A disease, and a set of taxa reported depleted in it.

**Question.** *"Which depleted taxon is a credible intervention candidate — is
the depletion replicated, is there animal or human interventional evidence, is
the organism cultivable and safe (no transferable AMR, no virulence factors), and
does it have a plausible mechanism?"*

**Output.** A shortlist with, per candidate: count of independent studies
reporting depletion, the strongest evidence tier reached (observational → mouse →
human RCT), AMR/virulence flags from its genome, and the metabolite it is claimed
to produce.

**Needed fields.** Direction + replication count + evidence tier on the
taxon–disease edge; **intervention records** — gutMDisorder explicitly curates
the relation *"interventions change the composition of gut microbiota"* and is
the only source in the survey that does; per-genome AMR gene calls with model
type and hit category (CARD/RGI); taxon–metabolite production with evidence tier.

**Source(s) and the canonical worked chain.** *Akkermansia muciniphila*:
observed negative correlation with obesity / untreated T2D / hypertension → mouse
work → a randomised, double-blind, placebo-controlled pilot in 32 overweight
insulin-resistant humans (40 enrolled), 10¹⁰ bacteria/day for 3 months, primary
endpoints safety/tolerability/metabolic parameters, with pasteurised *A.
muciniphila* improving insulin sensitivity and body composition. That whole chain
is what "experimentally demonstrated" looks like for a probiotic claim, and no
single database records more than one rung of it.

**Citation.** Depommier C et al., Nat Med 25:1096 (2019), PMID 31263284 ·
Qi X et al., gutMDisorder v2.0, NAR 51:D717 (2023) · Alcock BP et al., CARD, NAR
48:D517 (2020).

### W4. Mechanism hypothesis via metabolite production (SCFA, bile acids, TMAO)

**Input.** A taxon (or set of taxa) whose abundance changed, plus optionally a
metabolomics readout from the same samples.

**Question.** *"Is there a metabolite that explains this? Which of my changed
taxa can make butyrate / secondary bile acids / TMA, and does that match the
metabolite I measured going down?"*

**Output.** Per taxon, the metabolites it is reported to produce, **with the kind
of evidence** — gene present in the genome, enzyme characterised, metabolite
measured in monoculture, or measured in vivo.

**Needed fields.** taxon → metabolite with (a) relation direction (produces /
consumes / degrades / transforms), (b) evidence tier, (c) the pathway or gene
carrying it, (d) the rank at which the claim holds (strain-specific in most real
cases), (e) a citation.

**Three worked exemplars showing the tiers are not interchangeable.**

- **Butyrate — gene-centric prediction.** Vital, Howe & Tiedje screened 3,184
  genomes and built a 3,055-entry gene catalogue over four pathways ("(i) the
  acetyl-CoA, (ii) glutarate, (iii) 4-aminobutyrate, and (iv) lysine pathways"),
  with `but` / `buk` as terminal biomarkers. Their own caveat, verbatim:
  *"Although targeting complete pathways is a more robust way to predict function
  than single-gene analysis, their detection in genomes does not automatically
  imply functionality, since that must be done by specific biochemical testing."*
  Concrete failure case: Peptococcaceae and Syntrophomonadaceae carry the pathway
  but are "known rather to **oxidize** butyrate for growth" — **the same genes
  running in reverse; a pathway hit can mean the organism consumes the
  metabolite.**
- **TMA — gene present, production unproven.** Rath et al. found *cutC* in 100%
  of 50 fecal samples but *cntA* in only 26%, with producers under 1% of the
  community. Verbatim self-limitation: *"we only targeted the TMA-producing
  potential by quantifying respective gene abundances, and no investigations on
  gene expression/TMA production were performed."* Plus an annotation-transfer
  problem: functionality had been shown only "for *Acinetobacter baumannii* and
  *Escherichia coli*", while stool sequences averaged 86% ± 7% nucleotide identity
  to references.
- **Secondary bile acids — enzyme-level demonstration, and strain-dependent.**
  The *bai* operon 7α-dehydroxylation route is characterised down to purified
  enzymes in *Clostridium scindens* ATCC 35704. But Reed et al. showed organisms
  **carrying the *bai* operon differ in whether they actually convert cholate to
  deoxycholate** — the gene-presence-vs-production gap made experimentally
  explicit within one pathway.

**Citation.** Vital M, Howe AC, Tiedje JM, mBio 5(2):e00889-14 (2014), PMC3994512
· Vital M, Karch A, Pieper DH, mSystems 2:e00130-17 (2017), PMC5715108 · Rath S
et al., Microbiome 5:54 (2017), PMC5433236 · Ridlon JM et al., Gut Microbes
7:22 (2016), PMC4856454 · Reed AD et al., J Bacteriol 202 (2020), PMC7221253 ·
Craciun S & Balskus EP, PNAS 109:21307 (2012), PMC3535645 · Devlin AS & Fischbach
MA, Nat Chem Biol 11:685 (2015), PMC4543561.

### W5. Cross-feeding network inference

**Input.** A community composition (taxon list with abundances) from
metagenomics.

**Question.** *"Who feeds whom? Which metabolite exchanges are present in a
healthy community and lost in disease?"*

**Output.** A metabolite-mediated network with **producers and consumers** per
metabolite, and a per-metabolite score.

**Needed fields — the critical one is a `CONSUMES` edge.** Marcelino et al.
define the **Metabolite Exchange Score MES = 2·P·C / (P+C)** — the harmonic mean
of the number of potential Producers and Consumers — and **MES = 0 if a
metabolite is only produced or only consumed**. Without consumption edges the
score is identically zero and the use case is dead.

**Source(s) — and note the workflow does not use a curated association
database.** It reconstructs genome-scale metabolic models (**CarveMe v1.5** in
Marcelino et al.; **AGORA2** in the VMH lineage) and reads production/consumption
off the **exchange reactions**, simulated at community scale with **MICOM v0.26**
under pFBA. MICOM's `micom.interaction.interactions` emits directed per-sample
edges with columns `focal`, `partner`, `metabolite`, `flux`, `class` ∈
{**provided, received, co-consumed**}, `sample_id`. The alternative is **SMETANA**
detailed mode, whose output columns are literally
`['community','medium','receiver','donor','compound','scs','mus','mps','smetana']`
— a directed donor→receiver→compound table with a certainty score.

Scale and result in Marcelino et al.: 955 species (949 bacterial, 6 archaeal)
across 1,661 gut metagenomes (871 healthy, 790 diseased); exchanges significantly
affected in **10 of 11 diseases**; in Crohn's, *"The diversity of potential H2S
consumers was more affected in CD patients (56% less diverse on average)…than the
diversity of H2S producers (32% less diverse)."*

The authors are explicit these are *potential*, model-derived interactions:
*"limited by the use of automated genome-scale metabolic reconstructions, which
represent phenotypes close to manually-curated models but are naturally unable to
predict all organism-specific traits or secondary metabolism."*

**The curated alternative** is **NJC19** (§1.10): 8,224 directed import / export /
degrade events plus 912 negative associations across 838 species, curated from
769 sources, **CC0**. **[inference]** these are two different evidence classes —
NJC19 is literature-curated and qualitative; MICOM/SMETANA output is computed,
quantitative and sample-contextual. They should be separate edge classes, not
merged.

**Citation.** Marcelino VR et al., *Disease-specific loss of microbial
cross-feeding interactions in the human gut*, Nat Commun 14:6546 (2023),
PMC10589287 · Diener C, Gibbons SM, Resendis-Antonio O, MICOM, mSystems
5:e00606-19 (2020), https://journals.asm.org/doi/10.1128/msystems.00606-19 ·
Zelezniak A et al., SMETANA, PNAS (2015), https://github.com/cdanielmachado/smetana
· Lim R et al., NJC19, Sci Data 7:204 (2020), PMC7320173 · Sung J et al., NJS16,
Nat Commun 8:15393 (2017), PMC5467172.

### W6. AMR gene surveillance in metagenomes

**Input.** Metagenomic reads, assembled contigs, or MAGs.

**Question.** *"What resistance genes are in this sample, to which drug classes,
by which mechanism — and how confident is each call?"*

**Output.** A resistome table: ARO term, gene family, drug class, mechanism, hit
quality, and increasingly the likely host organism.

**Needed fields.** ARO id and its relations; the **detection model type** — a
variant model means the *mutation* confers resistance, not the gene's presence;
the **RGI hit category** (Perfect / Strict / Strict-nudged / Loose);
`confers_resistance_to_drug_class` vs `confers_resistance_to_antibiotic`; and the
curated-vs-prevalence provenance flag.

**The evidence bar CARD sets, which is worth copying verbatim.** "to be included
in CARD an AMR determinant must be described in a peer-reviewed scientific
publication, with its DNA sequence available in GenBank, including clear
experimental evidence of elevated minimum inhibitory concentration (MIC) over
controls." And the counterpart: CARD Prevalence / Resistomes & Variants is in
silico only and "not included in CARD's primary curation nor used as reference
sequences".

> A 276k-edge AMR layer sourced from prevalence data is **predicted**, not
> curated — and even a Perfect hit "does not indicate if the AMR gene is expressed
> or if it results in elevated MIC".

**Citation.** Alcock BP et al., CARD 2020, NAR 48:D517,
https://academic.oup.com/nar/article/48/D1/D517/5608993 · CARD 2023, NAR 51:D690,
PMC9825576.

### W7. Drug–microbiome interaction lookup

**Input.** A drug (or a patient's medication list), or a taxon.

**Question — two directions.**
(a) *Drug → bug:* "Does this non-antibiotic drug inhibit gut commensals, and is
the microbiome shift I see in my cohort a drug effect rather than a disease
effect?"
(b) *Bug → drug:* "Which gut bacteria metabolise this drug, and by which gene?"

**Output.** (a) per drug × strain growth-inhibition calls; (b) per drug the
metabolising strains and the responsible enzyme.

**Needed fields.** Drug identifier (ChEMBL / ATC / DrugBank); taxon at **strain**
resolution — both landmark screens are strain-level; the assay and its readout;
the direction (inhibition vs metabolism vs no effect — **the negatives matter
here**); and the gene where identified.

**Source(s).** Maier et al. "screened more than 1,000 marketed drugs against 40
representative gut bacterial strains, and found that **24% of the drugs with
human targets**, including members of all therapeutic classes, inhibited the
growth of at least one strain in vitro"; antipsychotics were overrepresented;
they explicitly present it as "a resource for future research on drug-microbiome
interactions". Zimmermann et al. measured 76 gut bacteria against 271 oral drugs;
**176 (65%) were metabolised by at least one strain**, and they mapped the
responsible microbial genes. Curated aggregators: **MASI** (typed bidirectional
edges, §1.11), **MDAD** (untyped, likely dead), **aBiofilm** (best per-edge
assay schema).

**Citation.** Maier L et al., Nature 555:623–628 (2018), PMID 29555994,
doi:10.1038/nature25979 · Zimmermann M et al., Nature 570:462–467 (2019), PMID
31158845, https://www.nature.com/articles/s41586-019-1291-3 · Zeng X et al.,
MASI, NAR 49:D776 (2021), PMC7779062 · Sun Y-Z et al., MDAD (2018), PMC6292923.

---

## 3. Evidence grading

### 3.1 How existing curated resources grade evidence

**DisGeNET.** The GDA score is "a weighted sum of evidence components, where each
component can contribute up to a maximum value", with published component
ceilings: **Curated ≤ 0.70, Literature ≤ 0.40, Inferred ≤ 0.25, Clinical Trials
≤ 0.10, Models ≤ 0.10**; range 0 to ~1.55. Source classes for gene–disease
associations: **CURATED, ANIMAL_MODELS, INFERRED, LITERATURE**. The **Evidence
Index (EI)**, verbatim: *"An EI equal to one indicates that all the publications
support the GDA or the VDA, while an EI smaller than one indicates that there are
publications that assert that there is no association"* — **a contradiction
meter, not a strength meter**. The **Evidence Level (EL)** is *passed through*
from ClinGen and Genomics England PanelApp, not invented. Enumerated EL string
values: **not found**.
https://support.disgenet.com/support/solutions/articles/202000100283- ·
Piñero et al., NAR 48:D845 (2020).

> **Design point.** The score is dominated by *source class*, not publication
> count. Text-mined literature is structurally capped below curation.

**ClinGen Gene–Disease Validity** (Strande et al., AJHG 100:895, 2017) — **the
most directly transferable scheme, because it separates genetic from experimental
evidence and caps them independently.** SOP v11: **Genetic Evidence max 12
points, Experimental Evidence max 6 points.** Classifications: Definitive (12,
plus replication over time) / Strong (10–11) / Moderate (7–9) / Limited (1–6) /
Disputed / Refuted / No Known Disease Relationship (0). Experimental
sub-categories each default 1, max 2: *Function*, *Functional Alteration*,
*Models and Rescue*.

> **All experimental evidence in the world can contribute at most 6 of 18
> points. Animal models alone can never reach Definitive.** This is a published
> statement that model-organism demonstration is *weaker* than human evidence for
> this edge type — the inverse of what the microbiome field usually assumes.

Verbatim: Definitive = "repeatedly demonstrated in both the research and clinical
diagnostic settings" over time; Disputed = "Only a few cases with non-specific,
genetically heterogeneous phenotypes and missense variants; no convincing
experimental data available"; Refuted = "Evidence refuting the initial reported
evidence … significantly outweighs any evidence supporting the role."

Three transferable ideas: two independent axes with independent caps;
**contradiction as a separate class, not a low score**; and "replication over
time" as an explicit named requirement for the top tier.

**GO evidence codes + ECO.** GO's grouping:
*Experimental* — EXP, IDA, IPI, IMP, IGI, IEP;
*High-throughput* — HTP, HDA, HMP, HGI, HEP (a separate, lower-trust tier of the
*same* methods);
*Phylogenetic* — IBA, IBD, IKR, IRD;
*Computational* — ISS, ISO, ISA, ISM, IGC, RCA;
*Author* — TAS, NAS; *Curator* — IC, ND; *Electronic* — **IEA**.
Verbatim: *"'Electronic' (IEA) annotation are not manually reviewed."* Structural
lessons: the code names the **method**, not a number; high-throughput variants get
their own codes; the operationally decisive split is **manually reviewed vs
not**, which cuts across experimental/computational.
https://geneontology.org/docs/guide-go-evidence-codes/

**ECO** (Giglio et al., NAR 47:D1186, 2019) — two roots, `evidence` and
`assertion method`; 1,515 terms; 27 GO codes map to 33 ECO classes. **ECO's own
caveat: terms indicate the *type* of evidence only — not quality or confidence.**
So ECO is reusable as `evidence_type` but cannot supply an ordinal
`evidence_level`. **[inference]** the clean design is `evidence_type` = ECO CURIE
(descriptive, unbounded) **plus** `evidence_level` = a small ordinal vocabulary.

**IntAct MIscore.** Three equally-weighted components: publication count (Sp),
**diversity of detection methods** (Sm), diversity of interaction types (St).
Per-method numeric weights keyed to PSI-MI terms — biophysical 1.00, biochemical
1.00, protein complementation 0.66, imaging 0.33, genetic interference 0.10,
unknown 0.05. Thresholds: >0.6 high, 0.45–0.6 medium. **Transferable: method
*diversity*, not just count — two papers using the same assay is worth less than
two using different assays.** PMC4316181.

**STRING — the single most important architectural lesson here.** Seven evidence
channels (neighborhood, fusion, co-occurrence, co-expression, **experiments**,
databases, **text mining**), each exposed as its own 0–1 sub-score (`nscore`,
`fscore`, `pscore`, `ascore`, `escore`, `dscore`, `tscore`), "and can be enabled
or disabled separately as desired". The combined score is an aggregate, but **the
channels are never destroyed.**

> The expert's complaint in Part A — "it doesn't tell you whether the link is
> experimentally demonstrated" — is precisely the failure mode of an
> aggregate-only score. STRING's answer is: keep the channel and let the consumer
> filter on it.

**CTD.** A `curated` / `inferred` partition, with transitive inference stated
verbatim: "if chemical C1 has a curated relationship to phenotype P1 and,
independently, chemical C1 also has a curated association with disease D1, then
phenotype P1 is said to have an inferred relationship with disease D1". The
inference statistic is **WXYA**, a weighted network-topology score that rewards
inferences supported by more connecting genes and **penalises inferences running
through highly-connected hubs**, to stop scale-free hubs inflating scores.
`DirectEvidence` values are `marker/mechanism` and `therapeutic`; verbatim
primary-source definitions **not found** (ctdbase.org returns 302).
King BL et al., PLoS ONE 7:e46524 (2012).

**Open Targets.** Evidence *datatypes*: `genetic_association`, `somatic_mutation`,
`known_drug`, `affected_pathway`, `literature`, `animal_model`, `rna_expression`.
Scores computed at three levels (source, type, overall) by a **harmonic sum** —
evidence sorted descending, each divided by rank², normalised by ~1.644 — so the
2nd piece of evidence is worth 1/4 of the 1st and the scale **saturates**: ten
weak papers never beat one strong one. Datasource weights down-weight exactly the
three you'd expect: Europe PMC (text-mining), Expression Atlas, IMPC (mouse) =
**0.2**; Cancer Biomarkers, OTAR = 0.5; all others 1.0. **Explicit caveat,
verbatim: association scores "should not be interpreted as a confidence score".**
https://platform-docs.opentargets.org/associations

**GRADE.** Verbatim: High = "We are very confident that the true effect lies
close to that of the estimate of the effect"; Moderate / Low / Very Low as
progressively weaker confidence statements. Starting points: *"randomized trials
without important limitations provide high quality evidence"*; *"observational
studies without special strengths or important limitations provide low quality
evidence."* Five rate-down domains (risk of bias, imprecision, inconsistency,
indirectness, publication bias); three rate-up factors. **Transferable: GRADE
grades a *body of evidence for one outcome*, and grades design first, then
adjusts** — which maps onto "assign a base level from study design, then
downgrade for inconsistency across cohorts". https://gdt.gradepro.org/app/handbook/handbook.html

**Microbiome-specific classes.**

- **HMDB status** — the cleanest directly-reusable ordinal ladder of *measurement
  strength* found anywhere: **Detected and Quantified** / **Detected but not
  Quantified** ("solid experimental evidence and literature data supporting the
  metabolite's existence and/or quantification") / **Expected but not Quantified**
  ("expected to exist based on biochemistry, enzymology or known constituents") /
  **Predicted but not Quantified**. The HMDB 5.0 paper documents the first three;
  the four-value form is the database field vocabulary. Verbatim definition of the
  "Predicted" tier: **not found**.
- **MiMeDB** — `Detected and Quantified` / `Detected Only` / predicted, with
  predicted compounds to be kept "in a separate data layer" rather than flagged
  with a field — a stronger stance than a level column.
- **MDAD** — two classes, verbatim: **"experimentally supported"** ("demonstrated
  by lab experiments reported in publications") and **"clinically supported"**
  ("FDA-approved or confirmed to be effective in clinical trials").
- **CARD** — the curated (`elevated MIC over controls`) vs Prevalence
  (`in silico prediction … not experimentally characterized genes`) split, plus
  the orthogonal Perfect/Strict/Loose hit confidence and the model-type axis.
- **gutMGene** — **"causal"** ("controlled experiments that manipulate a specific
  variable") vs **"correlational"** ("statistical correlation analyses").
- **BugSigDB grades nothing at all.** It has no evidence-level or confidence
  field; it exposes the study metadata that lets a consumer grade for themselves.
  That is itself a defensible design position — and its 92.5% 16S / 7.5% shotgun
  split tells you what the population actually is.
- **Bradford Hill as a numbered rubric for microbiome–disease claims:
  not found.** The field reformulated the problem as *modified Koch's postulates*
  instead (§3.2a).

### 3.2 What "experimentally demonstrated" means

#### (a) For a taxon–disease link

The ladder, weakest to strongest, with each rung's stated weakness. **The
literature does not support the naive ordering that puts Mendelian randomization
above animal work.**

1. **Cross-sectional / case-control differential abundance, single cohort, 16S.**
   The default: 44.7% case-control + 27.2% cross-sectional of BugSigDB's studies,
   92.5% of them 16S. Surana & Kasper state the failure mode verbatim — MWAS
   produce *"long lists of implicated microbes without clearly elucidating their
   causal role"* and *"correlations have not always held up in subsequent
   studies"*. *Weakness: reverse causation, confounding by diet/medication/transit
   time, no replication.*
2. **Replicated across independent cohorts, or meta-analysis.** BugSigDB exists
   because "systematic comparisons among published results … remain difficult";
   meta-analysis is only **0.9%** of its curated studies. *Weakness: replication
   removes cohort-specific noise but not shared confounding.* **[inference]**
3. **Longitudinal / prospective — taxon precedes onset.** BugSigDB treats
   *Prospective cohort* (10.5%) and *Time-series/longitudinal* (8.1%) as distinct
   design classes; this is Hill's temporality criterion in practice. *Weakness:
   precedence excludes reverse causation but not confounding; a subclinical
   prodrome can shift the microbiome before diagnosis.* **[inference]**
4. **Mendelian randomization — rank this LOW and label it contested.** The
   instrument source is MiBioGen (Kurilshikov et al., Nat Genet 53:156, 2021):
   18,340 individuals, 24 cohorts, and verbatim — *"Microbial composition showed
   high variability across cohorts: only 9 of 410 genera were detected in more
   than 95% of samples."* Only **31 loci** reached genome-wide significance and
   **only one — LCT — reached study-wide significance**. The published critique
   (Hatcher et al., medRxiv 2025, doi:10.1101/2025.06.03.25328787; 66 studies,
   ~48,082 MR estimates) concludes verbatim: ***"all studies were judged to be of
   poor quality, due to the inappropriate application of MR – specifically,
   instrument selection, exposure and outcome definition, choice of analytical
   methodology, assessment of reverse causation and replication – and lack of
   transparent reporting."*** *Weakness: with one study-wide-significant locus
   available, nearly every published microbiome MR relaxes the instrument
   threshold — exactly the failure Hatcher names.*
5. **Gnotobiotic colonisation / FMT transfer of phenotype — itself contested.**
   Walter et al. (Cell 180:221, 2020), verbatim: *"In a systematic review, we
   found that **95% of published studies (36/38) on HMA rodents reported a
   transfer of pathological phenotypes** to recipient animals… We posit that this
   exceedingly high rate of inter-species transferable pathologies is implausible
   and overstates the role of the gut microbiome in human disease."* *Weakness: a
   95% positive rate is prima facie publication bias; the result establishes
   sufficiency in a mouse, not causation in a human.*
6. **Causal microbe identified by triangulation + add-back (modified Koch's
   postulates).** Surana & Kasper, verbatim: *"we bioinformatically pinpointed a
   limited number of taxa associated with our phenotype and substantiated these
   correlations by add-back experiments to fulfill Koch's postulates"*, and *"We
   propose that Koch's postulates be expanded to apply to identification of
   beneficial organisms."* Formalised by Neville, Forster & Lawley as *"a variant
   of Koch's postulates, aimed at providing a framework to establish causation in
   microbiome studies"* (the enumerated postulates are paywalled — **not found**).
   Fischbach's selection criteria are themselves a usable filter: phenotypes
   *"large in magnitude, easy to measure, and unambiguously driven by the
   microbiota"*. *Weakness: still an animal system; sufficiency, not necessity.*
7. **Human intervention trial (probiotic RCT, defined consortium, FMT RCT).**
   BugSigDB records RCT as its own class (4.4%). Under GRADE, randomised trials
   start at **High** certainty and observational studies at **Low** — two full
   levels apart before any adjustment. *Weakness: an FMT or multi-strain RCT shows
   that **an intervention** works, not that **the named taxon** is the causal
   agent; taxon attribution needs rung 6 on top.*

#### (b) For a taxon–metabolite production link

**The headline empirical fact, and the best single citation in this whole
document** — gutSMASH, on 1,135 individuals with matched plasma and faecal
metabolomics:

> *"the level of microbiome-derived metabolites in plasma and feces is **almost
> completely uncorrelated** with the metagenomic abundance of corresponding
> metabolic genes, indicating a crucial role for pathway-specific gene regulation
> and metabolite flux."* (r ≈ −0.04 to 0.24 across 14 metabolites)

That is the justification for making genome-inferred production a **distinct and
low** evidence level rather than a synonym for production.

1. **Pathway predicted from a genome/MAG by an automated tool.** gutSMASH (19,890
   MGCs across 4,240 genomes), MACADAM (PS/PFS over MetaCyc), AGORA2
   reconstructions, PICRUSt2 for 16S. *This rung is capability, not production.*
2. **Marker gene detected, where the marker is validated elsewhere.** Vital et
   al.'s butyrate catalogue; Rath et al.'s *cutC*/*cntA*. *Weakness: annotation
   transfer at 86% identity, regulation, and reversibility — Peptococcaceae carry
   the butyrate pathway but oxidise butyrate.*
3. **Gene expressed (metatranscriptomics / proteomics).** Vital et al. 2017, 2,387
   samples. *Weakness: transcript ≠ protein ≠ flux; gutSMASH attributes the
   decoupling specifically to "gene regulation and metabolite flux", so expression
   closes only part of the gap.*
4. **Metabolite measured in monoculture of that strain.** The standard Vital et
   al. call "specific biochemical testing". Reed et al. make the rung-2-vs-rung-4
   gap explicit: organisms carrying the *bai* operon differ in whether they
   actually convert cholate to deoxycholate.
5. **Gene→metabolite step established by heterologous expression / knockout /
   enzymology.** Craciun & Balskus verified the choline TMA-lyase cluster
   "through genetic knockout and heterologous expression" plus EPR — which is what
   made *cutC* a marker gene that Rath et al. later merely counted. Devlin &
   Fischbach: *"We show, for the first time, that iso-bile acids are produced by
   Ruminococcus gnavus"* — the same edge previously existed only as an
   unattributed community-level fact. **Note this rung is orthogonal to rung 4,
   not above it**: rung 5 proves the gene does the chemistry, rung 4 proves this
   organism makes the compound. The strongest single-strain evidence is 4 + 5.
6. **Measured in defined co-culture or with the taxon manipulated in a
   community.** *Weakness: cross-feeding means a metabolite measured in co-culture
   may be produced by the partner.*
7. **Measured in a gnotobiotic animal mono-colonised with that taxon.** Koeth et
   al.: germ-free mice showed "no detectable plasma d3-(methyl)TMA or
   d3-(methyl)TMAO" until conventionalised.
8. **Measured in humans by isotope tracing and/or microbiota suppression.** Same
   paper's human arm: 250 mg heavy-isotope L-carnitine with a steak → "Post-
   prandial increases in d3-TMAO and d3-L-carnitine in plasma were readily
   detected"; then a week of poorly-absorbed broad-spectrum antibiotics → "virtually
   no detectable formation of either native or d3-labeled TMAO … consistent with
   an obligatory role for gut microbiota." *Even this establishes **microbiota**-
   dependence, not **taxon** attribution — that still needs rungs 4–5.*

### 3.3 A proposed `evidence_level` vocabulary

**[inference] — this is a synthesis, not a published vocabulary.** Nine ordinal
values, plus two contradiction values on a separate field.

Three companion fields, all borrowed, all required:

- `evidence_type` — an **ECO** CURIE. ECO gives type, not confidence, by its own
  statement, so it complements rather than replaces the level.
- `evidence_channels` — keep the per-channel breakdown, never only an aggregate.
  **STRING's design, and the direct answer to Part A's A1.**
- `contradiction` — separate from level (ClinGen's Disputed/Refuted;
  DisGeNET's EI).

| Value | Meaning | Borrowed from |
|---|---|---|
| `predicted` | Computationally inferred only — genome/MAG pathway call, sequence similarity, KG transitive inference. No measurement of *this* edge. | GO **IEA**/ISS; DisGeNET **INFERRED**; CTD **inferred**; HMDB **Predicted**; MiMeDB's separate data layer; CARD **Prevalence** |
| `text_mined` | Asserted by an NLP/co-occurrence pipeline; no curator read the paper. | DisGeNET **LITERATURE** (capped 0.40 vs curated 0.70); STRING **textmining**; Open Targets Europe PMC weight **0.2** |
| `curated_single_study` | One human observational study, curator-verified. | BugSigDB case-control/cross-sectional (72% of corpus); ClinGen **Limited**; GRADE observational start = **Low** |
| `curated_replicated` | Concordant in ≥2 independent cohorts, or a meta-analysis. | ClinGen replication logic + **Moderate**; IntAct method-**diversity**; GRADE **inconsistency**; GMrepo **MCI** |
| `temporal_or_genetic` | Prospective/longitudinal precedence, **or** a host-genetic instrument (MR). Explicitly **not** above `curated_replicated` for MR-only evidence. | BugSigDB **Prospective cohort**/**Time-series**; Hill temporality; downweighted per Hatcher 2025 and MiBioGen |
| `in_vitro_demonstrated` | Measured in monoculture / defined co-culture, or gene→product shown by heterologous expression, knockout or enzyme assay. **For taxon–metabolite, the first rung that means "produces".** | GO **IDA/IMP/IPI**; ClinGen **Function** + **Functional Alteration**; HMDB **Detected and Quantified**; MDAD **experimentally supported**; MASI |
| `in_vivo_animal_demonstrated` | Gnotobiotic mono-colonisation, defined-consortium colonisation, or FMT transfer into germ-free animals. | ClinGen **Models and Rescue** (capped); DisGeNET **ANIMAL_MODELS** (≤0.10); Open Targets **animal_model** (0.2); Surana & Kasper add-back; Koeth germ-free arm. **Carries Walter's 95%-transfer warning** |
| `human_intervention_demonstrated` | RCT (probiotic, consortium, FMT) or human isotope-tracing / microbiota-suppression experiment. | GRADE randomised start = **High**; Open Targets **known_drug**; MDAD **clinically supported**; Koeth human arm |
| `established` | Repeatedly demonstrated across independent groups **and over time**, including ≥1 human-intervention rung, or an in-vivo + in-vitro pair for the named taxon. | ClinGen **Definitive** — note it requires replication *over time*, not just points |

| Contradiction value | Meaning | Borrowed from |
|---|---|---|
| `disputed` | Credible published evidence both for and against (DisGeNET-style EI < 1). | ClinGen **Disputed**; DisGeNET **EI** |
| `refuted` | Refuting evidence significantly outweighs supporting evidence. | ClinGen **Refuted** |

**Four design rules the sources argue for, which matter more than the value
list:**

1. **Never collapse to a single number.** Open Targets says so itself: association
   scores "should not be interpreted as a confidence score". Store level, channel
   breakdown and ECO type.
2. **Source class dominates evidence volume.** DisGeNET caps text-mining below
   curation; Open Targets' harmonic sum makes the 2nd paper worth ¼ of the 1st.
   Ten 16S case-control papers must not out-rank one gnotobiotic add-back.
3. **Split the axes the way ClinGen does.** For taxon–disease: an
   `observational_level` and an `experimental_level`, each capped. For
   taxon–metabolite: `capability_evidence` (genome/expression) vs
   `production_evidence` (measured metabolite) — because gutSMASH *measured* them
   as "almost completely uncorrelated".
4. **Record the method, not just the level.** BugSigDB grades nothing but records
   sequencing type, 16S region, statistical test, correction and threshold — and
   that is enough for a consumer to grade. IntAct attaches a numeric weight per
   PSI-MI method term. Storing `method` (16S / WMS / qPCR / culture / MS) alongside
   `evidence_level` lets us re-grade later without re-curating.

---

## 4. Criticisms of microbiome association databases and KGs

### 4.1 The empirical warrant for the whole chapter

**Tierney BT, Tan Y, Yang Z, Shui B, Walker MJ, Kent BM, Kostic AD, Patel CJ.**
*Systematically assessing microbiome-disease associations identifies drivers of
inconsistency in metagenomic research.* PLoS Biology 20(3):e3001556 (2022).
PMC8890741 · https://doi.org/10.1371/journal.pbio.3001556

A specification-curve analysis fitting **6,035,110 models** across 6 phenotypes,
15 public cohorts, 2,343 individuals. Verbatim:

> "When querying a subset of **581 microbe-disease associations that have been
> previously reported in the literature, 1 out of 3 taxa demonstrated substantial
> inconsistency in association sign**. Notably, **>90% of published findings for
> type 1 diabetes (T1D) and type 2 diabetes (T2D) were particularly nonrobust**
> in this regard."

- T1D: **0 of 34** features reached FDR significance. T2D: **5 of 96 (5.2%)**.
- **27.9%** of features disagreed with the published direction in ≥50% of models.
- "different models yielded contradictory associations for the same taxon-disease
  pairing, some showing positive correlations and others negative."
- Authors' recommendation: "fitting and reporting a single model … will not be
  conducive to efficiently and consistently delivering clinically actionable
  biology."

> **This converts "an edge from one paper is weak evidence" from an editorial
> position into a measured claim: the sign flips about one time in three.**

**Guard.** Require **≥2 independent studies agreeing in direction** before an edge
leaves a provisional tier; store `n_studies_agreeing_direction` and
`n_studies_disagreeing`; expose a "single-study, direction-unconfirmed" tier that
queries exclude by default. Make T1D/T2D edges a standing fixture in the test
suite — they are the measured worst case.

### 4.2 The published critique of exactly this kind of resource

**Badal VD, Wright D, Katsis Y, Kim H-C, Swafford AD, Knight R, Hsu C-N.**
*Challenges in the construction of knowledge bases for human microbiome-disease
associations.* Microbiome 7:129 (2019). PMC6728997 ·
https://doi.org/10.1186/s40168-019-0742-2

From the Knight lab, about precisely this problem. Verbatim:

- Manual curation "is **not sustainable or scalable** given the rapid pace of
  publication in this field" — Disbiome, "the largest and most comprehensive
  effort to date", covered only **~500 abstracts**.
- "Prominent microbiome resources such as Bergey's Manual, Open Tree of Life
  Taxonomy, SILVA, RDP, Greengenes, and NCBI **differ in structure, organization,
  maintenance, and scope**", and "bacterial names evolve and undergo
  reclassification."
- Coverage: HMDAD's **292 microbes** against ~19,717 known microbes as of 2017.
- **The modelling criticism that bears directly on our schema:** existing KBs
  "**model microbe-disease associations as qualitative directional (reduced vs.
  elevated) relationships only. This limits their usability in situations where
  disease progression may be associated with microbial blooms.**"

They recommend common controlled vocabularies and annotated benchmark corpora.

### 4.3 Text-mined edges are wrong far more often than their presence suggests

**SemRep** — Kilicoglu H, Rosemblat G, Fiszman M, Shin D. *Broad-coverage
biomedical relation extraction with SemRep.* BMC Bioinformatics 21:188 (2020).
PMC7222583. **Strict: precision 0.55, recall 0.34, F1 0.42** (relaxed: 0.69 /
0.42 / 0.52 — the figure usually quoted downstream). On the CDR benchmark,
precision 0.90 but recall 0.24–0.35. Error attribution: "most errors occurred in
the relational analysis steps (51.5%)", with **NER/normalisation (MetaMap) the
largest single source at 26.9%** — a third of the damage is *entity resolution*,
which is our §4.6 problem.

> **Roughly 45% of strictly-evaluated SemRep relations are wrong.** Use 0.55, not
> 0.69.

**SemMedDB contradictions** — Sosa DN & Altman RB, Brief Bioinform 23(4):bbac268
(2022), PMC9294417: "SemMedDB was observed to contain **nearly 500 000** such
inconsistencies" (`X causes Y` alongside `X NOT_causes Y`); the filtered
apparent-contradiction rate is 2.6%. On dropped context: "Much of this context,
such as anatomical location(s) of drug action, is critical" — species, body site,
dose and "computational predictions versus experimental observations" are
routinely discarded at extraction.

**GNBR** (Percha & Altman, Bioinformatics 34:2614, 2018, PMC6061699), which DRKG
consumes, **publishes no precision figure at all**; validation was thematic
enrichment plus manual inspection of 10 dependency paths per cluster, and only
13.6–33.3% of paths got theme assignments. **Treat "no published precision" as
*precision unknown*, not as *precision fine*.**

**Guard.** Store negation/polarity as a first-class edge property, and run a
build-time contradiction sweep that **fails the build** above a threshold rather
than silently retaining both edges.

### 4.4 Degree bias — a KG's link predictions are mostly reading node popularity

Bonner S, Kirik U, Engkvist O, Tang J, Barrett IP, Brief Bioinform 23(5):bbac279
(2022) · https://academic.oup.com/bib/article/23/5/bbac279/6649936 ·
https://github.com/AstraZeneca/biomedical-kg-topological-imbalance

- **R² between gene node degree and TransE's predicted score: 0.77 (melanoma),
  0.79 (Parkinson's), 0.74 (Fuchs dystrophy), 0.77 (fallopian tube cancer)** —
  and the pattern holds for **all 137 diseases in Hetionet**, R² ≈ 0.6–0.85.
  Across models on breast cancer: TransH 0.83, RotatE 0.81, DistMult 0.73,
  ComplEx 0.45. Across datasets: DRKG 0.76, OpenBioLink 0.54.
- Verbatim: "the total volume of connections an entity has within the graph
  **seemingly matters more than any biological information encoded within**."
- **Stratified ranking collapse** (DaG holdout, 10 splits): low-degree genes
  (deg < 200) MRR **0.006**, Hits@10 0.012; high-degree (deg > 1000) MRR
  **0.053**, Hits@10 0.118 — a ~9× gap.
- **Two causal manipulations, not correlations.** *Rewiring:* randomising UBC's
  edges "has almost no negative impact on the rank. Indeed the rank actually
  **increases**". UBC — degree ~10⁴, with exactly **one** edge to a Disease and
  **one** to a Compound — "is ranked in the top 100 for every disease in the
  Hetionet dataset"; in OpenBioLink, where UBC is only 6th by degree, the same
  ranks become 232–3329. *Edge addition:* adding "random, biologically
  meaningless edges" moved gene TRG from least-likely to "one of the most likely"
  for two diseases.
- "the model is **more confident in a highly-connected gene than a true positive
  it has seen during training**."

Null-model corroboration: Aiyappa R, et al., *Implicit degree bias in the link
prediction task*, arXiv:2405.14985 — "the common edge sampling procedure … has an
implicit bias toward high-degree nodes … to the extent that a **'null' link
prediction method based solely on node degree can yield nearly optimal
performance**." *Counterweight, reported honestly:* Brière et al. (2026) found
"no evidence that predictions are driven by degree alone" — but that was
specifically about degree *alone* under permutation, and it is a null result
against two causal manipulations.

**Hetionet's authors already built the control, and it is worth copying
wholesale** (Himmelstein et al., eLife 6:e26726, 2017): **degree-weighted path
count (DWPC)** — "each path is weighted by taking the product of the node degrees
along the path raised to a negative exponent" — and **permuted hetnets** via XSwap
that "preserve node degree while eliminat[ing] edge specificity", "useful for
computing the baseline performance of meaningless edges while preserving node
degree". Every headline metric is reported as **Δ AUROC above the
degree-preserving null**.

Their own stated limitation is a direction problem in disguise: "the
Compound–binds–Gene relationship type **conflates antagonist with agonist
effects**", so "we expect some high scoring predictions to **exacerbate rather
than treat** the disease."

**Guard.** Ship a degree-preserving permuted copy of the graph with every release
and report metrics as Δ against it.

### 4.5 Leakage, and duplicate edges in shipped biomedical KGs

**Inverse-relation leakage** is why FB15k-237 and WN18RR exist: Dettmers T,
Minervini P, Stenetorp P, Riedel S, AAAI 2018, arXiv:1707.01476 — "**WN18 and
FB15k suffer from test leakage through inverse relations**"; leakage measured at
**94% (WN18) and 81% (FB15k)** of test triples; a rule that merely inverts
training triples scores WN18 MRR .963 / FB15k MRR .660.

**PrimeKG ships every edge twice with an identical label** —
https://github.com/mims-harvard/PrimeKG/issues/14 (closed 2023-09-13): "the
resulting dataframe has **8,100,498** edges/triples instead of the reported
4,050,249 … every triple appears twice in source/target swapped form … **the
labels are identical**." Plus 370 exact duplicates in `drug_protein`. A random
split puts an edge in train and its twin in test.

Other verified PrimeKG / DRKG / Hetionet defects, each issue URL checked:

| Issue | State | Substance |
|---|---|---|
| [PrimeKG #19](https://github.com/mims-harvard/PrimeKG/issues/19) | **open** | **88 duplicate nodes with conflicting names** — `ND5` vs `MT-ND5`; `gallbladder` vs `gall bladder` |
| [PrimeKG #22](https://github.com/mims-harvard/PrimeKG/issues/22) | **open** | Paper says ">200k" drug–effect edges; user counts **64,784**. No maintainer reply |
| [PrimeKG #5](https://github.com/mims-harvard/PrimeKG/issues/5) | closed | Disease ontology edges **bidirectional** — "Short bowel disorder" is both parent and child of itself |
| [PrimeKG #26](https://github.com/mims-harvard/PrimeKG/issues/26) | **open** | No flag distinguishing auto-added reverse edges from genuine ones |
| [DRKG #32](https://github.com/gnn4dr/DRKG/issues/32) | **open** | Rows with **empty gene identifiers** (`Gene::` then tab) |
| [DRKG #31](https://github.com/gnn4dr/DRKG/issues/31) | **open** | "GNBR contains over 2 million edges, whereas the README … specifies that only 335,369 edges were derived from GNBR" |
| [Hetionet #52](https://github.com/hetio/hetionet/issues/52) | **open** since 2023 | Does `Disease–upregulates–Gene` imply `Disease–associates–Gene`? Unresolved — a multi-relation leakage vector |

**Guard — three cheap build-time assertions.**
`count(distinct frozenset{h,t} × r) == count(triples)`; reject any CURIE with an
empty local part; assert the ontology `parent_of` relation is a **DAG**. And split
by **entity pair**, not by triple — once (microbe, disease) is in test under *any*
relation, exclude it from train under *every* relation.

### 4.6 The "same PMID counted twice" problem is documented, not hypothetical

BugSigDB's own tracker records it seven times, in the best-curated resource in the
field:

| Issue | State | Substance |
|---|---|---|
| [#106](https://github.com/waldronlab/BugSigDB/issues/106) | closed | Study_149 and Study_345 "are duplicates of the same PMID … **is there a way to search for duplicate studies, ie those with the same PMID?**" |
| [#48](https://github.com/waldronlab/BugSigDB/issues/48) | closed | Study_187 / Study_154 curated independently by different curators |
| [#35](https://github.com/waldronlab/BugSigDB/issues/35) | closed | PMID 27625705 created twice |
| [#178](https://github.com/waldronlab/BugSigDB/issues/178) | closed | **Leading zeros defeat the uniqueness check** — Study_580 and Study_731 are the same paper |
| [#205](https://github.com/waldronlab/BugSigDB/issues/205) | closed | Curators didn't understand the uniqueness error and re-created existing studies |
| [#330](https://github.com/waldronlab/BugSigDB/issues/330) | closed | Duplicate signatures where "deletion affects both" |
| [#143](https://github.com/waldronlab/BugSigDB/issues/143) | **open** | Cross-study record collision |

**Guard.** Normalise PMIDs to integers — **strip leading zeros; this is a real,
shipped bug in the best resource in the field** — and enforce a unique index on
`(normalised_PMID, condition, body_site, comparison_group)` at ingest.

**Measured redundancy across sources.** MicroPhenoDB collected **7,449 redundant →
5,677 non-redundant** associations — **~24% redundancy** when merging HMDAD +
Disbiome + NCIT + IDSA (PMC8377004).

**HMDAD ships ~7% duplicate rows.** The source paper reports 483 associations;
two independent later groups (MSignVGAE, PMC11328394; RNMFMDA, PMC7652725) both
report **450 after de-duplication** — **[inference]** the distributed file
therefore carries ~33 duplicate rows. Density: 292 × 39 = 11,388 cells, 450
positives = **3.95%**, ~96% unlabeled — set the AUROC 0.91–0.97 link-prediction
literature against that.

**A provenance-tiering hazard worth naming.** GMMAD (BMC Genomics 24:482, 2023,
PMC10464125) holds 3,836 curated disease–microbe associations alongside **220,690
*predicted* disease–metabolite associations** — the predicted layer is **57×** the
curated one. Ingesting it without honouring that boundary floods the graph with
model output labelled as knowledge.

### 4.7 Version metadata is missing from every major biomedical KG

Bonner et al., Brief Bioinform 23(6):bbac404 (2022), §6.3, on Hetionet / DRKG /
BioKG / PharmKG / OpenBioLink / CKG — verbatim:

> "**None of the detailed KGs have any form of maintenance or update schedule in
> place.** This means they will become increasingly out of date as the underlying
> data resources continue to evolve."
> "**Many of the resources do not detail from which version or year of a certain
> dataset the information has been collected.**"
> "So much of the data represented in a biological KG is uncertain … **Yet this
> uncertainty is rarely represented in the graph itself, perhaps leading to a
> false sense of trust** being created by the presence of certain relationships."
> "The lack of true negative samples in many graphs also means that the negative
> sampling strategy employed can bias the results."

Their Table 15 shows **"Version Info: ✗" for all six.**

**Cross-KG integration is measurably broken.** Hu S, Cheng H, et al., *Beyond
Identifier Matching*, medRxiv 2026, doi:10.64898/2026.05.26.26354182 — genes align
at 94–99%, but **disease overlap is 0.7% from PrimeKG to Hetionet vs 78.7% from
Hetionet's perspective** (wildly asymmetric). ClinicalBERT consolidation collapsed
22,205 disease nodes to 17,080 with three named failure modes: **peer
over-merging, parent–child collapse, lexical false positives**. Conclusion:
"identifier matching alone is a **weak baseline** for biomedical KG integration".
⚠️ preprint, abstract-level verification only.

**Guard.** Every source node and edge carries the source's **version string and
retrieval date**, and the graph refuses to build if any source lacks one.

### 4.8 Negatives, and the cost of an honest evaluation split

- **OpenBioLink** (Breit A et al., Bioinformatics 36:4097, 2020) is the one
  benchmark carrying **explicit true negatives** — "this relation was explicitly
  detailed **not** to exist."
- **The measured cost of an honest split** — Celebi R et al., BMC Bioinformatics
  20:726 (2019), PMC6921491: random CV gives AUC 0.93 / AUPR 0.92 / **F1 0.85**;
  drug-wise disjoint CV gives AUPR 0.81 / **F1 0.71**; pairwise disjoint gives
  AUPR 0.76 / **F1 0.63**. **F1 falls 26% purely from making the split honest.**
- Microbe-domain equivalent (RNMFMDA, PMC7652725): random negatives "may contain
  positive MDAs, thereby severely affecting the prediction accuracy".

**Guard.** Curate an explicit **negative edge type** from "no significant
difference" reports (NJC19 already ships 912 of them for transport); use
PU-learning elsewhere; report every metric under both random and entity-disjoint
splits.

### 4.9 Reported KGE numbers are dominated by training setup, not architecture

- Bonner et al., AILSCI 2022, arXiv:2105.10488: a 100-trial hyperparameter search
  improved Hits@1 by **+218%** (DistMult/Hetionet); seed-only variation leaves
  DistMult AMR at 0.201 ± **0.303** — the standard deviation exceeds the mean.
- Gema AP et al., Bioinform Adv 4:vbae097 (2024), PMC11538020: re-training ComplEx
  on BioKG gave **Hits@10 0.793 vs 0.012** — a ~66× swing from training
  methodology on identical data. "knowing model architecture alone … is probably
  insufficient to replicate results."

### 4.10 What the source databases say about each other

**Peryton on the incumbents** (PMC7779029): Disbiome and gutMDisorder "focus on
associations in contrast with healthy phenotypes" whereas Peryton also holds
disease-grade, metastatic-vs-non-metastatic and symptomatic-vs-asymptomatic
contrasts; "gutMDisorder **only permits querying** … by species name,
disorder/intervention and microorganism name"; Disbiome's "free-text search engine
is **not designed to be field-aware, frequently returning irrelevant entries**."
**No double-curation or inter-curator agreement procedure is described — not
found.**

**Disbiome on itself** (PMC5987391): "A NGS method is able to detect certain
bacteria where other techniques fail, resulting in **different relative
proportions**"; "different NGS platforms can produce different microbial
profiles"; "it is important to use the **same platform(s)** to make comparisons
possible." And on causality: "it remains to be elucidated whether the observed
microbiota differences … are a **symptom** of the disease or have a more
**causal** effect."

⚠️ **Cite a date with any Disbiome count, or cite neither.** Two snapshots
circulate — 9,102 experiments / 1,470 microbes / 322 diseases, and 8,731
associations / 1,622 microbes / 374 diseases — with different units and different
dates.

**BugSigDB's own method bias, quantified:** 92.5% 16S vs 7.5% shotgun (which is
why "enrichment analyses were performed at the genus level"), and **>50% of
studies are from China and the US** (201 and 157 of 628). Quality control is
social, not statistical — "tagging contributions as verified after review by a
trusted editor." **No inter-curator agreement statistic is published — not
found.**

### 4.11 Confirmed absent — and the absence is itself a finding

- **No published head-to-head comparison or audit of microbe–disease databases.**
  Dozens of papers *use* HMDAD and Disbiome side by side reporting separate AUCs,
  but none compares their contents, quantifies overlap, or audits curation errors.
- **No paper whose purpose is to criticise HMDAD**, despite ~35 papers
  benchmarking on it — none caveats its size, age, or duplicates.
- No published critique, erratum or third-party audit of **SPOKE** or
  **CROssBAR**; no external audit of **Hetionet** beyond Bonner's degree work.
- No **BugSigDB** inter-curator agreement statistic; **GNBR** publishes no
  precision figure.

### 4.12 Reproducibility of taxon–disease signatures across cohorts

**Half of "disease-associated" genera are not disease-specific.** Duvallet C,
Gibbons SM, Gurry T, Irizarry RA, Alm EJ. *Meta-analysis of gut microbiome
studies identifies disease-specific and shared responses.* Nat Commun 8:1784
(2017). PMID 29209090, PMC5716994. 28 case-control studies, 10 diseases (the
MicrobiomeHD collection). Verbatim:

> "**on average, 51% of a data set's genus-level associations were genera that
> were associated with more than one disease**" … "many associations found in
> case–control studies are likely not disease-specific but rather part of a
> **non-specific, shared response to health and disease**."

24 health-associated and 20 disease-associated genera out of **152** significant
in ≥1 dataset — and **seven genera that were both health- and disease-associated**
(direction contradiction, stated explicitly). Sample sizes within this single
meta-analysis run from ≈4 controls / 19 cases to 428 controls / 185 cases.

**BugSigDB's own non-specificity numbers.** Signatures contain **six microbes on
average**. Only two conditions replicate well — HIV (semantic similarity 0.68,
P = 0.002) and antibiotic treatment (0.64, P = 0.0005). Semantic similarity was
needed because **literal Jaccard overlap gives "sparse results"** — **[inference]**
exact taxon-set overlap between independent same-condition signatures is close to
empty. Four genera — ***Streptococcus, Prevotella, Bacteroides, Lactobacillus*** —
are "each reported as differentially abundant in **more than 100 signatures**",
while **1,009 of 1,370 unique microbes (73.6%)** appear in fewer than five. And
the false-positive mechanism, quantified: **r = −0.84, P = 3 × 10⁻⁶** between a
genus's healthy prevalence and the fraction of signatures reporting it *increased*
in disease.

**Cross-study transfer collapses, with numbers.** Wirbel J, Zych K, Essex M, et
al., SIAMCAT, Genome Biol 22:93 (2021), PMC8008609. 130 classification tasks, 50
studies, **10,803 samples**; 58% of datasets classifiable at AUROC ≥ 0.75
*within* study. On transfer: "low cross-study portability … apparent also from a
**more than twofold increase in false positives on average**", and loss of
disease specificity — "(false-positive) predictions for other diseases were
elevated for most models (**by a factor of 2.8 on average**)", with the
ankylosing-spondylitis model predicting "**more than 90% of cases from other
diseases to be AS positive**". A UC model looks *better* when Danish samples are
included (AUROC 0.84 vs 0.76) — the gain is country, not disease.

**The obesity signature did not replicate.** Sze MA & Schloss PD, mBio
7(4):e01018-16 (2016), PMC4999546. Ten studies: **no significant association for
any phylum-level metric, including the Firmicutes:Bacteroidetes ratio.** Where
signal existed it was trivial — obese averaged **2.07% lower** Shannon diversity;
RR of low diversity 1.27 (95% CI 1.09–1.48). Cross-study classification accuracy
**33.01–64.77% (median 56.68%)**, i.e. several at or below chance. The power
number is the one to remember:

> "To detect a 1, 5, 10, or 15% difference in Shannon diversity, the median
> required sampling effort per group was approximately **3,400, 140, 35, or 16
> individuals**" — and **only one of ten studies had power > 0.80** for a 5%
> difference.

**Same taxon, opposite directions — a documented case with the variance
decomposition.** Romano S, Savva GM, Bedarf JR, Charles IG, Hildebrand F, Narbad
A, npj Parkinsons Dis 7:27 (2021), PMC7946946. "Over 100 differently abundant
taxa … have been reported … findings are often **inconsistent**". For
*Prevotellaceae*: "Some studies detected these taxa to be highly depleted …
whereas others found no differences … or found these taxa **enriched**."
Lactobacillaceae were "enriched in PD in the Western cohorts but **never in
Chinese studies**". The explanation:

> **disease status explained <1% of variance; study of origin explained 28–53%.**

**The contrast case sets the ceiling.** CRC is the field's success story — Wirbel
et al., Nat Med 25:679 (2019), PMC7984229: 8 studies, n=768, **29 core species**
at FDR < 1e-5, within-study AUROC 0.69–0.92, transfer drop only 0.07 ± 0.12,
disease specificity held (FPR 0.09–0.13 on other diseases). Thomas et al., Nat
Med 25 (2019), PMID 30936548: 969 metagenomes, cross-cohort **average AUC 0.84**.
Yet even here, "individual studies showed marked discrepancies in the species
identified as significant". **[inference]** ~0.80–0.84 cross-cohort AUROC is the
current ceiling for the best-behaved disease — tier edge confidence against that,
not against within-study performance.

**"Healthy microbiome" is not a definable reference state.** Lloyd-Price J,
Abu-Ali G, Huttenhower C, Genome Med 8:51 (2016), PMC4848870: "Characterizing a
'healthy' microbiome as an ideal set of specific microbes is therefore **no longer
a practical definition**"; shared taxa "vary in abundance by **more than an order
of magnitude** among healthy individuals"; only **a third** of metagenome genes
are found in a majority of healthy people. Shanahan F, Ghosh TS, O'Toole PW,
Gastroenterology 160:483 (2021), PMID 33253682: "Whether a healthy microbiome can
be defined is an important and seemingly simple question, but with a complex
answer in continual need of refinement." *(abstract only — paywalled.)*

**Guards.** Store `n_distinct_cohorts` and direction agreement per pair (§4.1).
Compute a per-taxon **condition breadth** and flag anything crossing the
>100-signature line as `non_specific`, excluded from disease-differentiating
queries by default. Never model a `HEALTHY_MICROBIOME` reference state — key every
"health-associated" claim to a named cohort so it inherits that study's control
definition. And keep the F:B ratio as a **known-negative fixture**: any pipeline
that surfaces it as an obesity signal has a bug.

### 4.13 Compositionality, differential-abundance method choice, and technical batch

**Compositional data invalidates the standard toolkit.** Gloor GB, Macklaim JM,
Pawlowsky-Glahn V, Egozcue JJ, Front Microbiol 8:2224 (2017), PMC5695134. "the
total read count observed in a HTS run is a **fixed-size, random sample** of the
relative abundance"; compositional data "have a **negative correlation bias**…
exhibit **spurious correlation** upon subsetting or aggregation"; and tools in
common use "exhibit unacceptably high false positive identification rates… **the
false positive rates can be up to 20× higher than expected**." What this
invalidates: Pearson/Spearman on proportions, count normalisation, rarefying, and
Bray–Curtis / JSD / UniFrac as usually applied.

The hardest numbers are in the SparCC paper — Friedman J & Alm EJ, PLoS Comput
Biol 8(9):e1002687 (2012):

> "in some real data sets many of the correlations among taxa can be artifactual,
> and **true correlations may even appear with opposite sign**" … "the standard
> approach yields **3 spurious species-species interactions for each true
> interaction and misses 60% of the true interactions**."

Weiss S, Van Treuren W, Lozupone C, et al., **ISME J** 10(7):1669 (2016),
PMC4918442 (note: ISME J, not Microbiome) — 8 correlation tools: "Different tools
consistently produce **very different numbers and types of significant edges** for
the same data"; compositional damage is severe below **n_eff = 13**, and at **70%
sparsity** performance is "little better (or even worse) than random guessing."
Kurtz ZD, et al. (SPIEC-EASI), PLoS Comput Biol 11(5):e1004226 (2015):
"correlations can arise between OTUs that are **indirectly connected**";
reproducibility on American Gut across disjoint subsets — SPIEC-EASI ≈ 50 edge
disagreements vs CCREPE ≈ **250**.

**Differential-abundance tools disagree by ~50×.** Nearing JT, Douglas GM, Hayes
MG, et al., Nat Commun 13:342 (2022), PMC8763921. **14 methods × 38 datasets,
9,405 samples.** Mean % of ASVs called significant (unfiltered):

| Method | mean % significant | SD |
|---|---:|---:|
| limma voom (TMMwsp) | **40.5%** | 41% |
| Wilcoxon (CLR) | 30.7% | 42.3% |
| LEfSe | 12.6% | 12.3% |
| edgeR | 12.4% | 11.4% |
| ALDEx2 | **1.4%** | 3.4% |
| ANCOM-II | **0.8%** | 1.8% |

- Range across all 14: **0.8% – 40.5%** — a ~50× spread on identical data.
- Uniquely-called (found by no other tool): **edgeR 12.1%, LEfSe 11.1%**.
- Consensus (>12 of 14 tools agreeing): **38.5%** filtered vs **17.3%** unfiltered.
- Shuffled-label false discovery, filtered: **edgeR 10.3%**, LEfSe 4.4%, others
  0–2.2%.
- Verdict: "**many biological interpretations based on microbiome data analysis
  are likely not robust to DA tool choice**"; "we can clearly recommend that
  users **avoid using edgeR** … **as well as LEfSe**."

> This is uncomfortable, and worth stating plainly: **LEfSe is the single most
> common method in the published microbiome literature, and it is one of the two
> the authors advise against.** GMrepo's entire marker layer is LEfSe-derived, and
> so is gutMDisorder's raw-data half. Those edges are not wrong, but they are
> single-method edges from a method with an elevated shuffled-label false
> discovery rate.

**Rarefying is a live, unresolved disagreement — report both sides.** *Against:*
McMurdie PJ & Holmes S, PLoS Comput Biol 10(4):e1003531 (2014) — "rarefying
biological count data is **statistically inadmissible**". *For:* Schloss PD,
mSphere 9(1):e00355-23 (2024), PMC10826360 — identifies **11 compromising design
choices** in those simulations, notably that it tested *single subsampling* rather
than true rarefaction: "**Far from being 'inadmissible', rarefaction is a valuable
tool**"; and mSphere 9(2):e00354-23, PMC10900887 — "**rarefaction was the only
normalization approach to control the Type I error**" when sequencing depth is
confounded with treatment group, where other methods approached ~100% false
detection. *Conditional middle:* Weiss S, et al., Microbiome 5:27 (2017),
PMC5335496 — rarefying wins for presence/absence metrics and at ~10× library-size
differences; DESeq2 raises FDR below 20 samples/group; ANCOM "the only method
tested that has a good control of false discovery rate" above 20/group.
**[inference]** the camps largely address different estimands (per-taxon DA vs
diversity metrics), which is why both can be right.

**Technical protocol beats biology.** Costea PI, Zeller G, Sunagawa S, et al.,
Nat Biotechnol 35:1069 (2017), PMID 28967887, across 21 extraction protocols:
"**We found that DNA extraction had the largest effect on the outcome of
metagenomic analysis.**" ⚠️ **No variance-explained percentage appears in this
paper — do not attribute one to it.** Sinha R, Abu-Ali G, Vogtmann E, et al.
(MBQC), Nat Biotechnol 35:1077 (2017), PMC5839636 — 15 labs, 9 pipelines, 22
specimens, >16,000 profiles: "Variability depended most on biospecimen type and
origin, followed by **DNA extraction, sample handling environment, and
bioinformatics**"; "**up to 5-fold variation** between communities profiled in
different laboratories." ⚠️ **No R² / variance-decomposition table — again, do not
attribute one.**

**Guards.** `transform` ∈ {raw, proportion, rarefied, clr, absolute} mandatory per
edge; refuse to compare across transforms. Separate `ASSOCIATED_WITH` (marginal)
from `CONDITIONALLY_DEPENDENT_ON` (graphical model) as distinct edge types. Store
`da_method` and `n_methods_supporting`; default queries return only
≥2-method-replicated edges. Blacklist Pearson/Spearman-on-proportions edges or tag
them with a ~0.75 spurious prior, and blacklist the *Bacteroides*↔*Prevotella*
anticorrelation specifically (§4.14). Store `extraction_protocol` and
`sequencing_center`; a cross-study aggregation that mixes protocols must flag that
it did.

### 4.14 Relative vs absolute abundance — the direction of a change is not recoverable

Vandeputte D, Kathagen G, D'hoe K, Vieira-Silva S, Valles-Colomer M, Sabino J,
Wang J, Tito RY, De Commer L, Darzi Y, Vermeire S, Falony G, Raes J.
*Quantitative microbiome profiling links gut community variation to microbial
load.* Nature 551:507 (2017). PMID 29143816. Verbatim:

> "Comparative analyses of relative microbiome data **cannot provide information
> about the extent or directionality of changes**."
> "up to **tenfold differences in the microbial loads** of healthy individuals."
> "**the taxonomic trade-off between *Bacteroides* and *Prevotella* is an artefact
> of relative microbiome analyses**."
> "we identify **microbial load as a key driver of observed microbiota alterations
> in a cohort of patients with Crohn's disease**."
> "**microbiome research must exchange ratios for counts.**"

Badal et al. (§4.2) make the same point from the KB side: qualitative up/down
"limits their usability in situations where disease progression may be associated
with microbial blooms."

**Guard.** `abundance_basis` ∈ {relative, absolute} on every edge; label the edge
`relative_abundance_change`, never `abundance_change`; no directional claim from
relative data without a load measurement. Every source in §1 stores relative
abundance, so in practice **every association edge in this graph is a
relative-abundance edge** and should say so.

### 4.15 Medication confounding — the metformin story

Forslund K, Hildebrand F, Nielsen T, Falony G, Le Chatelier E, Sunagawa S, et al.
*Disentangling type 2 diabetes and metformin treatment signatures in the human
gut microbiota.* Nature 528:262 (2015). PMID 26633628, PMC4681099. 784
metagenomes, three countries, stratified by metformin status.

> "In most of these reports, **treatment regimens were not controlled for** and
> conclusions could thus be confounded by the impact of various drugs on the
> microbiome."
> "While metformin treatment status could be reliably recovered from microbial
> composition using SVMs, **metformin-untreated T2D status itself could not**."
> "the previously reported high accuracy of gut microbial signatures for
> identifying treatment-unstratified T2D patients **decreased dramatically** when
> considering a large set of metformin-naïve patients only."

Which "T2D findings" were actually the drug:

- ***Escherichia* increase** → metformin effect.
- ***Intestinibacter* decrease** → metformin effect, consistent across all three
  cohorts.
- ***Lactobacillus* increase** → attributed to T2D unstratified, but "this trend
  was **eliminated or reversed** when controlling for metformin".
- **Increased butyrate/propionate production potential** → metformin, not disease.
  **A "beneficial SCFA producer" signal in an unstratified cohort can be a drug
  effect** — which bears directly on W4 and on probiotic candidate selection (W3).

**Generalised across drug classes.** Vich Vila A, Collij V, Sanna S, et al., Nat
Commun 11:362 (2020), PMC6969170: 1,883 samples, **59.8% on ≥1 drug**; 41 drug
categories, 19 associated singly → **6** after multi-drug correction; taxonomic
associations **154 → 47**, pathway associations **411 → 271**. PPIs were the only
drug associated in all three cohorts — and PPI users were up for the ARGs *tetA*,
*tetB*, *Mel* in all three, **which bears directly on an AMR layer**.

**Host variables generally — the strongest confounding result in the field.**
Vujkovic-Cvijin I, Sklar J, Jiang L, Natarajan L, Knight R, Belkaid Y. *Host
variables confound gut microbiota studies of human disease.* **Nature** 587:448
(2020), PMC7677204 (note: *Nature*, not Nat Commun). 11 matching variables
including **alcohol frequency** and **bowel movement quality**; 5,878 core AGP
subjects; 19 diseases.

> "**matching cases and controls for confounding variables reduces observed
> differences in the microbiota and the incidence of spurious associations.**"

**Significance was lost entirely** for clinical depression, autism spectrum
disorder, lung disease, thyroid disease, migraine and SIBO. Retained: IBD, skin
conditions, acid reflux, cancer. **T2D worked example: 26 differentially abundant
ASVs → 0 after matching.** And an audit of six prior T2D microbiome studies found
**only 1 of 6 reported alcohol frequency**.

Falony G, Joossens M, Vieira-Silva S, et al., Science 352:560 (2016): 69
covariates, 92% replication; "**Stool consistency showed the largest effect size,
whereas medication explained largest total variance**"; "proposed disease marker
genera associated to host covariates, **urging inclusion of the latter in study
design**." ⚠️ **The widely-quoted "7.7% variance explained" could not be verified
(Science returned 403 on all routes) — do not cite it.** Zhernakova A, Kurilshikov
A, Bonder MJ, et al., Science 352:565 (2016), PMC5240844: 126 factors "collectively
explain **18.7%** of the variation."

**Drug → bug, measured directly.** Maier L, et al., Nature 555:623 (2018) —
"**24% of the drugs with human targets** … inhibited the growth of at least one
strain in vitro" against 40 strains. ⚠️ The commonly-quoted "1,197 drugs" is **not
in the abstract**; the abstract says "more than 1,000 marketed drugs".

**Guards.** `drug_adjusted` boolean + `drugs_controlled[]` + `matched_on[]` per
edge. Auto-emit a `CONFOUNDED_BY` edge when a disease association and a drug
association share a taxon and cohort. Make *Escherichia*/*Intestinibacter*/T2D a
fixture in the regression suite. Add a `DRUG –INHIBITS→ TAXON` layer from Maier
2018 as a competing-explanation check — this is a second, independent argument for
closing Gap 3.

### 4.16 Contamination — the pitfall that invalidated a body site

This is the strongest cautionary tale available, and it is not in the brief.

**Salter SJ, Cox MJ, Turek EM, Calus ST, Cookson WO, Moffatt MF, Turner P,
Parkhill J, Loman NJ, Walker AW.** *Reagent and laboratory contamination can
critically impact sequence-based microbiome analyses.* BMC Biol 12:87 (2014).
PMID 25387460, PMC4228153. Contaminating DNA is "**ubiquitous** in commonly used
DNA extraction kits and other laboratory reagents", "varies greatly in composition
**between different kits and kit batches**", and "critically impacts results
obtained from samples containing a low microbial biomass" — affecting **both 16S
and shotgun**. "**Concurrent sequencing of negative control samples is strongly
advised.**" The paper ships an explicit contaminant-genus list.

**The placenta case, in three acts.**

1. Aagaard K, Ma J, Antony KM, Ganu R, Petrosino J, Versalovic J. *The placenta
   harbors a unique microbiome.* Sci Transl Med 6:237ra65 (2014). PMID 24848255,
   PMC4929217. 320 samples, **1,488 citations**, and **no retraction, correction,
   or expression of concern**. It is still, formally, in the literature.
2. de Goffau MC, Lager S, Sovio U, Gaccioli F, Cook E, Peacock SJ, Parkhill J,
   Charnock-Jones DS, Smith GCS. *Human placenta has no microbiome but can contain
   potential pathogens.* Nature 572:329 (2019). PMID 31367035, PMC6697540:
   "**there was no evidence for the presence of bacteria in the large majority of
   placental samples**… Almost all signals were related either to the acquisition
   of bacteria during labour and delivery, or to **contamination of laboratory
   reagents**… **the human placenta does not have a microbiome**." Sole exception:
   *S. agalactiae* in ~5% pre-labour.
3. Systematic re-analysis, De Jesus Federico II C, et al., Am J Reprod Immunol
   (2026), doi:10.1111/aji.70246, PMID 42104576 — seven studies re-analysed:
   "**no consistent microbiome signature** distinguishing the term from preterm
   placentas… Bacterial DNA in placental tissues was primarily attributed to
   contamination from the urogenital tract or laboratory processes."

Recommendations framework: Eisenhofer R, Minich JJ, Marotz C, Cooper A, Knight R,
Weyrich LS, *Trends Microbiol* 27(2):105 (2019), PMID 30497919 — the **RIDE**
checklist.

**[inference] Any KG that ingested 2014–2018 literature uncritically contains a
full body-site's worth of contaminant edges, sourced from a paper that was never
retracted and is therefore invisible to a retraction check.**

**And curation fidelity is not data quality.** BugSigDB issue
[#156](https://github.com/waldronlab/BugSigDB/issues/156) ("Quality control", 72
comments): a journal reviewer found an entry that **faithfully reproduced its
source paper** — whose organisms were obvious contaminants. Verbatim: "the
organisms cited in the study read like a list of contaminants not found in
mammals. Groups like Aquificae and Thermaceae are normally found in **hot
springs**… **A study like this should really be flagged as unusual in the
system.**" PI Levi Waldron's proposed remedies are directly implementable: a list
of taxa that do not live in human hosts, and a study-level tag vocabulary —
"**Retracted paper / Contamination issues suspected / Batch effect issues
suspected / Uncontrolled confounding suspected / Results are suspect.**"

**Guards.** `negative_control_sequenced` and `decontam_method` as required fields
on low-biomass studies. Ship a **habitat-plausibility check** and Waldron's five
study-quality tags **in v1** — no extraction-accuracy metric catches a faithfully
extracted bad paper. Quarantine disputed body sites (placenta, blood, healthy
tissue) behind an explicit flag rather than merging them into the main graph.

### 4.17 Taxonomic resolution limits of 16S — an information-theoretic ceiling

**Edgar RC.** *Accuracy of taxonomy prediction for 16S rRNA and fungal ITS
sequences.* PeerJ 6:e4652 (2018). https://peerj.com/articles/4652/ — the single
most load-bearing citation in this chapter:

> "identical V4 sequences belong to different species with ≫10% probability, e.g.,
> **63% probability** according to BLAST16S… correctly predicting ~90% of species
> names for V4 metagenomic sequences is **surely not achievable in practice by any
> algorithm using any current or future reference database**."

| Rank | V4 | V3–V5 | Full-length |
|---|---:|---:|---:|
| Genus, best method (SINTAX50) | **50.3%** | 59.3% | 67.7% |
| Species, best method (SINTAX80) | **19.8%** | 23.2% | 30.3% |
| Species, QIIME v1 | 6.6% | 7.6% | 9.8% |
| Species, mothur KNN | 0.0% | 0.0% | 0.0% |

Over-classification rate is **100%** for several common methods — they *always*
assign a novel sequence to a known taxon, never "unknown". At 95% V4 identity the
"twilight zone" makes genus / family / order / class roughly equiprobable as the
lowest common rank.

**Johnson JS, Spakowicz DJ, Hong B-Y, et al.**, Nat Commun 10:5029 (2019),
PMC6834636: variable-region sequencing "**cannot achieve the taxonomic resolution
afforded by sequencing the entire (~1500 bp) gene**"; "**The V4 region performed
worst, with 56% of in-silico amplicons failing to confidently match their sequence
of origin**"; and critically — "**it is not valid to assume that ever finer
clustering of these sub-regions will result in the improved taxonomic resolution
necessary to reflect species**." *ASVs do not rescue you.* Intragenomic 16S copy
variation was found in 349/381 isolates.

**Edgar RC**, Bioinformatics 34(14):2371 (2018): "Optimal identity thresholds were
**~99% for full-length sequences and ~100% for the V4 hypervariable region**" —
the ubiquitous 97% OTU threshold is simply wrong.

> **Stated plainly: a "species-level" edge derived from a V4 16S study is at best
> a ~20%-accurate species call and a ~50%-accurate genus call. It is not a species
> edge.**

Corroborated from inside the sources: BugSigDB enriches "at the genus level"
because 92.5% of its corpus is 16S; GMrepo makes the species view **physically
unclickable** for 16S projects; HMDAD is genus-level by design.

**Guard.** `assay.variable_region` and `clustering_threshold` mandatory; hard-assert
`edge.rank != 'species' OR evidence.method ∈ {full_length_16S, shotgun,
isolate_genome, WGS}`. A 97%-OTU node is sub-genus at best and should not carry a
species label at all. Record the **unclassified fraction** too — a taxon absent
from the graph is far more often *unmappable* than *absent from the sample*
(Kraken2 maintainers themselves cannot state an expected classification rate for
gut samples: [DerrickWood/kraken2#236](https://github.com/DerrickWood/kraken2/issues/236),
"**I'm not actually sure.** We worked on brain and corneal samples, not gut ones").

### 4.18 Reference taxonomies disagree — with each other and with themselves

- **GTDB vs NCBI, the headline.** Parks DH, Chuvochina M, Waite DW, Rinke C,
  Skarshewski A, Chaumeil P-A, Hugenholtz P, Nat Biotechnol 36:996 (2018), PMID
  30148503: "**58% of the 94,759 genomes** comprising the Genome Taxonomy Database
  had changes to their existing taxonomy." Majority-case disagreement, not an edge
  case. GTDB also treats *Shigella* spp. as synonyms of *E. coli*; NCBI does not.
- **GTDB moves fast.** Species clusters went **45,555 → 136,646** bacterial between
  R202 and R10-RS226, and ">95% of bacterial and archaeal species remain to be
  genomically elucidated" (Parks et al., NAR 2022, PMC8728215; GTDB R10, NAR,
  doi:10.1093/nar/gkaf1040). **Absence of a taxon node is not evidence of absence.**
- **Label overlap between databases is 30–50%.** Robeson MS 2nd, O'Rourke DR,
  Kaehler BD, Ziemski M, Dillon MR, Foster JT, Bokulich NA (RESCRIPt), PLoS Comput
  Biol 17(11):e1009581 (2021): "**~30–50% … of species labels were shared by SILVA,
  GTDB, and NCBI-RefSeq**"; Greengenes yields sequences "unannotated at the genus
  (**54%**) and species (**90%**) levels."
- **Same data, different differential-abundance results.** Campos P, Merlin BL,
  Wrege RM, et al., Poultry Science 101:101971 (2022), PMC9241040 — the *same ASVs
  at 15.8% abundance* classified as *Faecalibacterium* / *Gemmiger* /
  *Subdoligranulum* depending on database, and **LEfSe found 12 vs 9 enriched
  genera** depending on database. Also notes "**the Greengenes database was last
  updated in August 2013**."
- **Same data, four labels.** ⚠️ *preprint* — Ceccarani C & Severgnini M, bioRxiv
  2023.04.12.535864: only **16.1%** of relative abundance was identically
  classified by all four databases; **24.4%** belonged to one group labelled four
  different ways. Beta-diversity conclusions survived; **the labels did not — and
  a KG stores labels.**
- **The tool maintainers confirm it.** QIIME 2 forum, *Taxonomic discrepancy with
  Greengenes, Silva and NCBI* (Dec 2024), Nicholas Bokulich: "**the discrepancy is
  known and expected**, and if you start looking deeper you will find that many
  other discrepancies exist"; NCBI BLAST defaults use `core_nt`, which "contains
  many uncurated sequences that are misannotated."
- **A silent failure mode worth a regression test.**
  [dada2 issue #2205](https://github.com/benjjneb/dada2/issues/2205) (open, Jun
  2026) — classifying against full GTDB SSU r232 returns "Bacteria, NA, NA…" for
  nearly everything **including *Streptococcus mutans***; trimming species off the
  reference fixes it; independently reproduced; DADA2's author: "So I'm not sure
  what is going on here." **No error is raised — just NAs.**

**Guard.** Store `(namespace, id, version)` — never a bare name or bare ID. Forbid
cross-namespace joins without an explicit versioned mapping. On every taxonomy
upgrade run a diff job reporting nodes whose parent/rank/name changed, rather than
silently re-materialising. Tag `reference_stale=true` for Greengenes 13_8. And
alert on a **sudden rise in unassigned ranks** — that is what the dada2 bug looks
like from the outside.

### 4.19 NCBI Taxonomy mechanics a loader must handle

**The disclaimer is real and verbatim**, from the Taxonomy Browser
(https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=2):

> "**The NCBI taxonomy database is not an authoritative source for nomenclature or
> classification** - please consult the relevant scientific literature for the most
> reliable information."

Meanwhile Schoch CL, Ciufo S, Domrachev M, et al., *NCBI Taxonomy: a comprehensive
update on curation, resources and tools*, Database 2020:baaa062, PMC7408187, notes
it is "the standard nomenclature and classification repository for the INSDC."
**It is the de facto integration point precisely while disclaiming authority** —
which is exactly why Part A's A4 makes NCBI tax_id the canonical key *and* requires
an auditable reconciliation path.

- **`merged.dmp` / `delnodes.dmp`.** `merged.dmp` maps `old_tax_id → new_tax_id`.
  **`delnodes.dmp` is the real trap** — Schoch: it "lists TaxNodes that have been
  deleted… **as well as TaxNodes that were once public but are no longer linked to
  any public sequence entries**." An id cached from a 2015 paper can vanish with
  **no forwarding address**, and the two files are disjoint, so a resolver reading
  only `merged.dmp` silently drops those rows.
- **Name classes** (Schoch Table 1): `current name` may differ from `primary name`;
  **`in-part` names "can be duplicate across TaxNodes"** — one string legitimately
  resolves to *several* tax_ids; `common name` coverage is "not comprehensively
  added."
- **Homonyms, with counts — exactly the failure a microbiome KG hits.** Genus
  ***Morganella*** covers "species of **enterobacteria, mushrooms and scale
  insects** covered by three codes of nomenclature; **a total of 89 unique names
  across 194 TaxNodes**"; ***Drosophila*** 23 names / 47 TaxNodes; ***Candida***
  **211 names / 430 TaxNodes**. Total exposure **323 names / 671 TaxNodes**.
- **Not found:** any documented case of a tax_id being *reused* for a different
  organism. Schoch asserts TaxIds are stable and unique.
- **A real downstream break from lineage-string parsing.**
  [bugsigdbr issue #63](https://github.com/waldronlab/bugsigdbr/issues/63) — NCBI
  emitted lineages with **two `k__` ranks** (`k__Bacteria|k__Bacillati|p__Bacillota|…`)
  and the parser silently returned **78 values instead of 98**. No error — just a
  length mismatch.

**Guard.** Resolve node identity only against `name_class = "scientific name"`;
every other class becomes an alias edge with its class recorded, and the resolver
returns the *full* candidate set rather than first-match. Filter by NCBI division
before matching. Regression test: `Morganella`, `Candida`, `Drosophila` each return
exactly one expected bacterial node or an explicit ambiguity error. Resolve stored
tax_ids through `merged.dmp` **transitively**, and raise a **hard error — not a
silent drop** — on anything in `delnodes.dmp`. **Never parse taxonomy from
rank-prefix strings; walk the real hierarchy.**

### 4.20 The Lactobacillus split, and taxonomy churn generally

Zheng J, Wittouck S, Salvetti E, Franz CMAP, Harris HMB, Mattarelli P, O'Toole PW,
Pot B, Vandamme P, Walter J, Watanabe K, Wuyts S, Felis GE, Gänzle MG, Lebeer S.
*A taxonomic note on the genus Lactobacillus: Description of 23 novel genera,
emended description of the genus Lactobacillus Beijerinck 1901, and union of
Lactobacillaceae and Leuconostocaceae.* Int J Syst Evol Microbiol 70(4):2782–2858
(2020). PMID 32293557, doi:10.1099/ijsem.0.004107.

**The arithmetic, made explicit — 23 ≠ 25.** 23 novel genera + the emended
*Lactobacillus* + the pre-existing *Paralactobacillus* (Leisner et al. 2000) =
**25 genera**. LPSN records the 2020 emendation as "Emendation accompanied by the
**removal of 213 species** from the genus." **[inference]** on the arithmetic —
the IJSEM page returns 403; "25" is verified from ISAPP (co-authored by Lebeer, an
author of the paper) plus the LPSN genus inventory. Note *Paralactobacillus* is
**not** one of the 23.

**The 23 novel genera** (LPSN, filtered on "Zheng et al. 2020"): *Acetilactobacillus,
Agrilactobacillus, Amylolactobacillus, Apilactobacillus, Bombilactobacillus,
Companilactobacillus, Dellaglioa, Fructilactobacillus, Furfurilactobacillus,
Holzapfelia, **Lacticaseibacillus**, **Lactiplantibacillus**, Lapidilactobacillus,
Latilactobacillus, Lentilactobacillus, **Levilactobacillus**, **Ligilactobacillus**,
**Limosilactobacillus**, Liquorilactobacillus, Loigolactobacillus,
Paucilactobacillus, Schleiferilactobacillus, Secundilactobacillus.*

⚠️ **One of the 23 replacement names itself needed replacing within three years.**
*Holzapfelia* Zheng et al. 2020 is now "validly published under the ICNP,
**illegitimate name**", a later homonym of *Holzapfelia* Cossmann 1901; the correct
name is ***Holzapfeliella*** Deshmukh & Oren 2023 (IJSEM 73:005688).

**Species pairs, each verified on its own LPSN page:**

| Old | LPSN correct name (2026-09) |
|---|---|
| *L. casei* | ***Lacticaseibacillus casei*** |
| *L. paracasei* | ***Lacticaseibacillus paracasei*** |
| *L. plantarum* | ***Lactiplantibacillus plantarum*** |
| *L. reuteri* | ***Limosilactobacillus reuteri*** |
| *L. fermentum* | ***Limosilactobacillus fermentum*** |
| *L. salivarius* | ***Ligilactobacillus salivarius*** |
| *L. brevis* | ***Levilactobacillus brevis*** |
| *L. rhamnosus* | ⚠️ **still *Lactobacillus rhamnosus*** — see below |

Remaining in *Lactobacillus*: *L. delbrueckii* (the genus type, so it could not
move), *L. acidophilus, L. gasseri, L. crispatus, L. johnsonii, L. helveticus,
L. jensenii, L. iners, L. amylovorus*. LPSN lists 50 correct-name species.

> ⚠️ **The rename that got un-renamed.** LPSN, `/species/lacticaseibacillus-rhamnosus`:
> "This name is **taxonomically suspended** (and therefore not recommended for
> medical use for now) until no later than 2025 in favour of *Lactobacillus
> rhamnosus* (Hansen 1968) Collins et al. 1989." Meanwhile **NCBI taxid 47715 has
> scientific name *Lacticaseibacillus rhamnosus***, and "Lactobacillus rhamnosus"
> resolves to the same taxid. *L. casei* and *L. paracasei* moved and stayed; **only
> *rhamnosus* was suspended** — arguably the single most commercially important
> probiotic species (LGG). Mechanism: the List of Recommended Names / CoMicProN,
> Göker M et al., IJSEM 75(10):006943 (2025), PMID 41129200, PMC12548757. **Not
> found:** why *rhamnosus* specifically; the stated end-date has passed while the
> page still reads suspended.

**The fallout for data reuse, in one sentence.** Qiao N, Wittouck S, Mattarelli P,
Zheng J, Lebeer S, Felis GE, Gänzle MG, JDS Communications 3(3):222 (2022),
PMC9623751: "The NCBI taxonomy database has been updated with the new taxonomy but
**the former names of the records containing 16S sequences are maintained**, which
thus still follow the old taxonomy."

And ISAPP's own reassurance is a trap: "All new genera proposed for this group
begin with the letter 'L'. Thus, the '*L.*' genus abbreviation may still be used."
— **which means "*L.*" is now ambiguous across 21+ genera.** Any pipeline parsing
abbreviated binomials from abstracts is now silently wrong.

Note BugSigDB independently flags ***Lactobacillus*** as one of two genera "more
likely false positives or at least … not well suited as candidate biomarkers"
(§1.2). This genus is simultaneously the worst-affected by renaming *and* among the
least trustworthy as a signal.

**The other renames — verified, with the unsettled ones flagged.**

| Old | New | Citation | Status |
|---|---|---|---|
| *Clostridium difficile* | ***Clostridioides difficile*** | Lawson PA, Citron DM, Tyrrell KL, Finegold SM, Anaerobe 40:95 (2016), PMID 27370902 | ✅ clean. Watch: *Peptoclostridium difficile* is a third string in circulation and is **not validly published** |
| *Propionibacterium acnes* | ***Cutibacterium acnes*** | Scholz CFP, Kilian M, IJSEM 66:4422 (2016), PMID 27488827 | ✅ clean |
| *Eubacterium rectale* | ***Agathobacter rectalis*** | Rosero JA, et al., IJSEM 66:768 (2016), PMID 26619944 | ✅ but publicly contested — Sheridan/Flint letter + reply, IJSEM 66:2107 (2016), PMID 26920933 |
| *Bacteroides vulgatus / dorei* | ***Phocaeicola vulgatus / dorei*** | García-López M, et al., Front Microbiol 10:2083 (2019) | ✅ — but *P. vulgatus* was **suspended and then un-suspended** |
| *Prevotella copri* | *Segatella copri* | **Hitch TCA, Bisdorf K, Afrizal A, et al., Syst Appl Microbiol 45:126354 (2022)** | ⚠️ **NOT settled** — see below |
| *Faecalibacterium prausnitzii* | split; *F. duncaniae*, *F. hattorii*, *F. gallinarum* | Sakamoto M, et al., IJSEM 72:005379 (2022) | ✅ — **but see the strain trap.** (*F. longum* is **Zou Y et al., Sci Rep 11:11340 (2021)**, not Sakamoto) |
| *Ruminococcus gnavus* | ***Mediterraneibacter gnavus*** | Togo AH, et al., Antonie Van Leeuwenhoek 111:2107 (2018) | ✅ LPSN **and** NCBI (taxid 33038) now agree |
| *Lactococcus lactis* subsp. *cremoris* | ***Lactococcus cremoris*** | Li TT, Tian WL, Gu CT, IJSEM (2021) | ⚠️ LPSN's reference string reads "2019; 71:0" — internally inconsistent; verify before printing |
| *Fusobacterium nucleatum* subspecies → species | *F. animalis*, *F. polymorphum*, *F. vincentii* | Kook J-K, et al., Curr Microbiol 74:1137 (2017) | ⚠️ **LPSN records all three as validly published SYNONYMS, not correct names**, while the CRC literature routinely uses *F. animalis* as a species |

> ⚠️ ***Segatella copri* is an authority disagreement, not a rename.** LPSN
> (2026-09): the correct name is still ***Prevotella copri***; *Segatella copri* is
> "synonym (and not recommended for medical use)". NCBI: scientific name
> ***Segatella copri***, **taxid 165179** — the *same taxid* either way. LPSN's own
> hedge: "*Segatella* is the correct name **instead if this genus is regarded as a
> separate genus**" — a taxonomic opinion, not a nomenclatural fact. **A KG must be
> able to represent "the authorities disagree", not pick one.**

> ⚠️ **The *Faecalibacterium* strain trap — serious for a microbiome KG.** The type
> strain of ***F. duncaniae* is A2-165** (DSM 17677 / JCM 31915) — the single
> most-used "*F. prausnitzii*" strain in the anti-inflammatory literature.
> *F. prausnitzii* sensu stricto is a **different** organism (ATCC 27768). **A
> decade of "*F. prausnitzii* A2-165" findings are, under current nomenclature,
> findings about *F. duncaniae*.**

**Phylum renames.** Oren A & Garrity GM, *Valid publication of the names of
forty-two phyla of prokaryotes*, IJSEM 71(10):005056 (2021), PMID 34694987:
Firmicutes → **Bacillota**, Bacteroidetes → **Bacteroidota**, Proteobacteria →
**Pseudomonadota**, Actinobacteria → **Actinomycetota**. LPSN records the old
strings as **not validly published**. Compounding: *Bacillota* also carries the
synonyms "Bacillaeota", "Eurybacteria", "Halanaerobiota", "Clostridiota" — **five
or more strings for one phylum** — and *Actinobacteria* has
*Actinobacteriota*/*Actinobacteraeota* variants that are **not** the valid name, so
a naive `-ota` suffix rule gives wrong answers. Publicly contested: Sharma A,
Kolter R, et al., mBio (2022), doi:10.1128/mbio.02323-22.

> **The F:B ratio now has two spellings on each side.** Any table computing it must
> normalise phylum labels first and **fail loudly** if both spellings of the same
> phylum are present.

**How much literature still uses stale names — a direct measurement.** No published
study quantifies this (**not found**), so it was measured: Europe PMC phrase counts
restricted to `PUB_YEAR:2025 OR PUB_YEAR:2026`, run 2026-09-02:

| Old name | hits | New name | hits | old share |
|---|---:|---|---:|---:|
| "Firmicutes" | 19,501 | "Bacillota" | 4,055 | **83%** |
| "Ruminococcus gnavus" | 1,415 | "Mediterraneibacter gnavus" | 80 | **95%** |
| "Prevotella copri" | 1,134 | "Segatella copri" | 173 | **87%** |
| "Lactobacillus plantarum" | 4,430 | "Lactiplantibacillus plantarum" | 3,845 | 54% |
| "Bacteroides vulgatus" | 896 | "Phocaeicola vulgatus" | 864 | 51% |
| "Clostridium difficile" | 3,808 | "Clostridioides difficile" | 5,384 | 41% |

⚠️ Caveats: phrase occurrences over title/abstract/full text, so "*Bacillota*
(formerly *Firmicutes*)" counts in both columns — the "old share" is an **upper
bound** on exclusive old-name use, and Europe PMC full-text coverage is uneven.
Directionally it is hard to explain away: **ten years after the *C. difficile*
rename, the old name is still in 41% of recent records.**

**LPSN is the nomenclatural authority NCBI disclaims being.** Parte AC, Sardà
Carbasse J, Meier-Kolthoff JP, Reimer LC, Göker M, **IJSEM** 70:5607 (2020) (note:
IJSEM, not NAR); Meier-Kolthoff JP et al., NAR 50:D801 (2022); Freese et al., NAR
54:D884 (2025), PMC12807606. ">59,000 taxon names, more than 34,000 … validly
published under the ICNP"; the List of Recommended Names carries ">14K names … 10K
of which are recommended." **CC BY-SA 4.0**, with API and downloads.

What LPSN has that NCBI does not: `correct name` vs `synonym` status; homotypic vs
heterotypic synonymy; **nomenclatural status separate from taxonomic status**;
effective vs valid publication with Validation List number; basonym and full author
citation; **LoRN tagging and taxonomic suspension with end dates**; type
designations. ⚠️ **A three-year trap in date fields**: *M. gnavus* is
effective-published **2018**, the genus is cited **2019**, and the species
combination is cited **2023** (Validation List 213) — one organism, three
defensible "authority years".

**Guards.** Key taxon nodes on a **stable numeric id** (NCBI taxid, resolved
transitively through `merged.dmp`), and carry *every* name — LPSN correct name,
LPSN synonyms, NCBI scientific name, NCBI equivalent names — as attributes with
`source` and `as_of`. Build the synonym table from **LPSN's own fields**, not hand
typing; store `lpsn_snapshot_date`; re-diff on a schedule and alert when a name
flips `correct name → synonym`. Add a **suspension-history** column
(`suspended_from`, `suspended_until`, `unsuspended`) — a name that has flipped once
will flip again. Store **effective year, valid year and validation-list number
separately**. Model **strain** as a first-class node with culture-collection
accessions (ATCC/DSM/JCM), so a species split re-parents strains without
invalidating evidence edges — this is what catches "*F. prausnitzii* A2-165" ≡
"*F. duncaniae* A2-165". Reject abbreviated binomials (`^[A-Z]\.\s`) at ingest
unless the genus is recoverable. **Emit a build warning for every taxon where
`lpsn_correct_name != ncbi_scientific_name`** — today that set includes at least
*rhamnosus*, *copri*, and the three *Fusobacterium* names. And follow McMurry JA,
Juty N, Blomberg N, et al., PLoS Biol 15(6):e2001414 (2017), PMC5490878: record
obsolete/merged/secondary ids as explicit `replaced_by` edges rather than silently
rewriting the node.

### 4.21 Reporting standards exist because these fields are routinely missing

**STORMS** — Mirzayi C, Renson A, Genomic Standards Consortium, MAQC Society, et
al., *Reporting guidelines for human microbiome research: the STORMS checklist*,
Nat Med 27:1885 (2021), PMC9105086: "This review revealed **substantial reporting
heterogeneity**, particularly for epidemiology, such as **study design, confounding
factors, and sources of bias** … as well as microbiome-specific issues, including
statistical analysis of compositional relative abundance data and handling 'batch'
effects."

The 17-item checklist maps almost one-to-one onto a KG schema — 1.3 body site;
3.5 antibiotic/treatment; 3.6 final analytic sample sizes *with reasons for
exclusion*; 3.8 matching variables; 4.4 DNA extraction method ("a major source of
technical differences across studies"); 4.6 primers and 16S variable region;
4.7/4.8 positive and negative controls; 4.13 batch effects; 7.9 "all software,
packages, **databases**, and libraries … **including version numbers**"; 10.2
"Clearly state **magnitude and direction** of differential abundance."

**MIxS/MIMARKS** — Yilmaz P, Kottmann R, Field D, et al., Nat Biotechnol 29:415
(2011), PMC3367316: "**<10% of the 1.2 million 16S rRNA gene sequences (SILVA
release 100) were associated with even basic information** such as latitude and
longitude, collection date or PCR primers."

**How much public metadata is actually missing.** Abdill RJ, Adamowicz EM, Blekhman
R, *Public human microbiome data are dominated by highly developed countries*, PLoS
Biol 20(2):e3001536 (2022) — 444,829 human microbiome samples, 2,592 studies:
"**Most samples are missing even basic information such as sex (77% missing) and
age (79% missing), and the most prevalent tag indicating host health status,
'host_disease,' is only available for 7.8% of samples**"; 14% have no determinable
country. Klie A, Tsui BY, Mollah S, et al., Database (2021), PMC8083811 — 2.9M SRA
samples, 43.9M attribute–value pairs: of 11 selected attributes "**only
'SCIENTIFIC_NAME' … covers more than 25% of samples**".

**Geography bias**, same Abdill paper: **40.2% of samples from the United States
alone**, "almost five times more than any other country"; **71.2% from Europe +
Northern America**; central and southern Asia is 25.8% of world population but
**1.8% of samples**. (BugSigDB's own figure: >50% of studies are China + US.)

**Guard.** Make `body_site`, `host_species`, `assay.strategy`,
`assay.variable_region`, `taxonomy_db` + `version`, `n_cases`, `n_controls`,
`matched_on[]` and `direction` **required, non-nullable** on every association edge,
with a validation query that rejects rather than defaults. **Never treat an absent
field as a value** — carry `source ∈ {curated, inferred, absent}` per field. Store
`country` and expose a coverage query reporting, for any edge, the geography
distribution of its supporting studies.

### 4.22 Conflation traps — body site, host species, disease granularity, control definition

**Body site — the same taxon means opposite things.** *Fusobacterium nucleatum* was
"an invasive anaerobe **previously linked to periodontitis and appendicitis, but
not to cancer**" before Castellarin M, Warren RL, Freeman JD, et al., Genome Res
22:299 (2012), PMC3266037 (qPCR in 99 subjects, **p = 2.5 × 10⁻⁶**); companion
Kostic AD, et al., Genome Res 22:292 (2012). The reservoir is proven — Komiya Y, et
al., Gut (2019), PMC5945502 found "**identical strains of *Fusobacterium
nucleatum***" in both CRC tissue and oral samples. *Lactobacillus*-dominance is not
a universal health marker even within one body site: Ravel J, Gajer P, Abdo Z, et
al., PNAS 108(Suppl 1):4680 (2011), PMC3063603 — five vaginal community state
types, four *Lactobacillus*-dominated but by **different species**, with ethnic
differences at χ² = 36.8, P < 0.0001.

*Recall BugSigDB's CRC case study: 11 of the 19 enriched signatures were from
**oral** body sites (§1.2). Body site is not a filter you add later.*

**Host species — the 4% number.** Xiao L, Feng Q, Liang S, et al., Nat Biotechnol
33:1103 (2015), PMID 26414350: "**only 4.0% of the mouse gut microbial genes were
shared** (95% identity, 90% coverage) with those of the human gut microbiome" —
against ">95% of its KEGG orthologous groups" matching. *Functional similarity is
high; gene-level identity is near-nil.* Nguyen TLA, Vieira-Silva S, Liston A, Raes
J, Dis Model Mech 8:1 (2015), PMC4283646: small-intestine:colon length ratio **2.5
in mice vs 7 in humans**; surface ratio **18 vs 400**; and on humanised mice, "the
host-microbe relationships in these humanized models **do not necessarily reflect
the real relationships seen in humans**, because the gut microbiota is transplanted
into a host with which it has not co-evolved."

**Disease granularity — CD and UC separate at the microbiome level.** Pascal V,
Pozuelo M, Borruel N, et al., Gut 66:813 (2017), PMC5531220: an eight-genus
signature achieves "**specificity of 95.1% for the detection of CD versus UC**";
"Although UC and CD share many epidemiologic, immunologic, therapeutic and clinical
features, our results showed that they are **two distinct subtypes of IBD at the
microbiome level**." Validated across 2,045 samples in four countries.

Cross-ontology mapping is measurably inconsistent: Cui L, Zeng N, Kim M, et al.
(COHeRE), AMIA Annu Symp Proc (2015), PMC4765676 — **138,987 concept pairs** with
inconsistent relationships across UMLS source vocabularies; of 40 manually
reviewed, **95.8% of the inconsistencies were real**. Mondo — Vasilevsky NA,
Matentzoglu NA, Toro S, et al., **Genetics 2026**, PMID 41052288, PMC13050200 (the
2022 reference is the preprint): "challenges arise due to the vast number of
diseases, differing methods of classification, and **conflicting terminological
coding systems**"; it provides "fully provenanced and attributed links back to the
sources."

**"Control" does not mean healthy.** The reference IBD cohort defines its own
controls thus — Lloyd-Price J, Arze C, Ananthakrishnan AN, et al. (IBDMDB), Nature
569:655 (2019), PMC6650278: "Subjects not diagnosed with IBD based on endoscopic
and histopathologic findings were classified as '**non-IBD**' controls, including
the aforementioned healthy individuals presenting for routine screening, **and
those with more benign or non-specific symptoms**." **Not found:** a dedicated
study comparing household vs population vs non-IBD-gastro controls and showing
effects flip — but Vujkovic-Cvijin (§4.15) establishes the consequence.

**Sample size and effect-size metric.** Kelly BJ, Gross R, Bittinger K, et al.,
Bioinformatics 31:2461 (2015), PMC4514928 — PERMANOVA power via ω². Note
Vujkovic-Cvijin's observation that "beta diversity metrics (i.e. R² effect sizes
and F statistics) exhibited **substantially stronger correlations with sample
sizes** than AUROCs" — **the commonly reported effect size is itself sample-size
dependent.**

**Duplicate populations across sources.** Hussein H, Berrang-Ford L, Al-Zubaidi H,
et al., BMC Public Health 22:1827 (2022), PMID 36167529 — double-counting arises
from including "the same individuals multiple times in a single analysis"; there is
"a clear need for methodological and guideline development". **Not found:** any
quantification of how often it inflates results.

**Guards.**

| Trap | Guard |
|---|---|
| Body site | `UBERON ID` is a **mandatory qualifier on the edge**, not a property of the taxon. Uniqueness on `(taxon, body_site, host_species, phenotype)` so `F. nucleatum @ oral` and `@ colon_tumor` co-exist and no query merges them |
| Host species | `host_species` (NCBI taxid) mandatory and non-nullable; a validation query returning any Taxon–Disease path whose evidence **mixes** host species; an explicit `cross_species_extrapolation` flag before such a path is traversable |
| Disease granularity | Store the term **at the granularity the study reported**, plus a separate `rolls_up_to` edge; **never write CD evidence onto an IBD node**. MONDO as primary id, every xref as its own edge with `mapping_source` and `mapping_confidence` |
| Control definition | `control_definition` as a controlled vocabulary; two studies whose controls differ in kind are not poolable without a flag |
| Sample size | `n_cases`, `n_controls`, `effect_size` **and** `effect_size_metric` (ω² / R² / AUROC / log2FC) — reject edges where the metric is unnamed, since R² and AUROC are not comparable and R² is confounded with n |
| Duplicate populations | Deduplicate on **cohort/accession identity, not PMID** — store `cohort_id` (BioProject/SRA/EGA) as the unit of evidence and count *distinct cohorts*, never distinct PMIDs |
| Direction reversal | Store `direction` **with** an explicit `comparison_group` descriptor (`case_vs_healthy_population` / `case_vs_non_IBD_clinic` / `case_vs_household_control` / `case_vs_other_disease`); forbid merging two edges sharing `(taxon, disease, body_site, host_species)` but differing in `comparison_group`. **Not found:** a paper documenting sign reversal *specifically* from reference-group choice — but Tierney (§4.1) establishes the general rate at ~1 in 3 |

### 4.23 Causality, AMR phenotype, and inferred function

**Causality — the strongest available critical line.** Walter J, Armet AM, Finlay
BB, Shanahan F, *Establishing or Exaggerating Causality for the Gut Microbiome:
Lessons from Human Microbiota-Associated Rodents*, Cell 180(2):221 (2020), PMID
31978342: "whether such changes are causal, consequential, or bystanders to disease
is, for the most part, **unresolved**… In a systematic review, we found that **95%
of published studies (36/38) on HMA rodents reported a transfer of pathological
phenotypes** to recipient animals… **We posit that this exceedingly high rate of
inter-species transferable pathologies is implausible and overstates the role of
the gut microbiome in human disease.**"

**Guard.** Mandatory `evidence_type` enum — `observational_human |
interventional_human | HMA_rodent | conventional_animal | in_vitro |
computational` — plus a `causal_claim` boolean **defaulting to false**. No query
returns "X causes Y" from observational or HMA-rodent evidence. The 36/38 figure is
the justification for treating HMA-rodent evidence as a *discounted* tier, not as
causal support — which is exactly why §3.3 places `in_vivo_animal_demonstrated`
below `human_intervention_demonstrated`.

**AMR — presence ≠ phenotype, and the tools disagree wildly.**

- *Tool disagreement* (⚠️ **preprint**): Inda-Díaz JS et al., bioRxiv 2026,
  doi:10.64898/2026.05.11.724158 — ten ARG pipelines, >270M genes, 13 habitats:
  "**up to a 45-fold difference in the number of reported ARGs, with a mean Jaccard
  index of only 16% between pipelines**… no single approach should be treated as
  authoritative… **taken uncritically, the same data can support conflicting
  biological and ecological interpretations.**"
- *Database disagreement* (peer-reviewed): Eladawy M, et al., J Antimicrob
  Chemother (2025), PMC12596052 — same isolates, three databases: total concordance
  **91% (ResFinder), 85.7% (CARD), 80.5% (AMRFinder)**. Papp M & Solymosi N,
  Antibiotics (2022), PMC8944830 — six databases: "several different nomenclature
  forms of the same ARGs"; **13, 9 and 3 duplicate sequences** in NDARO, ResFinder
  and MEGAres respectively.
- *Genotype ≠ phenotype, with hard numbers*: Madden DE, Baird T, Bell SC, McCarthy
  KL, Price EP, Sarovich DS, *Keeping up with the pathogens*, Genome Medicine 16
  (2024), PMC11157771 — balanced accuracy across 10 antibiotics: ARDaP
  **85%/81%**, vs **abritAMR 56%/54%, AMRFinderPlus 58%/54%, ResFinder 60%/53%**.
  *The standard tools are barely above coin-flip.* Alfaray RI, et al., Antibiotics
  (2023), PMC10376887: "**presence of ARG may not directly correlate with the
  sensitive/resistance phenotype**."

This corroborates CARD's own FAQ warning (§1.13) that "a PERFECT hit does not
indicate if the AMR gene is expressed or if it results in elevated MIC".

**Guard.** Never store a bare `Taxon –has_ARG→ Antibiotic`. Model it as
`Genome –ARG_detected {tool, tool_version, database, database_version,
identity_threshold, coverage_threshold}→ ARG`, with `ARG –confers_resistance_to→
Antibiotic` as a **separate, phenotype-backed** edge carrying `AST_method` and
`MIC`. A 45-fold / Jaccard-16% spread means a single-database resistome is a
database artifact as much as a biological finding.

**Inferred function is not function.**

- Matchado MS, Rühlemann M, Reitmeier S, et al., *On the limits of 16S rRNA
  gene-based metagenome prediction and functional profiling*, Microbial Genomics
  10(2):001203 (2024), PMC10926695: "**16S rRNA gene-based functional inference
  tools generally do not have the necessary sensitivity to delineate health-related
  functional changes in the microbiome and should thus be used with care**";
  overlapping KO terms with true metagenome results collapsed from **654** (CRC) to
  **66** (PICRUSt2, T2D cohort). And a methodological bombshell: "**Spearman
  correlation values are not affected by label permutation and are thus not suited
  to robustly assess the performance** of functional inference tools" — the field's
  standard validation metric is vacuous. Corroborated by Sun S, Jones RB, Fodor AA,
  Microbiome 8:46 (2020), PMID 32241293: "**simple correlation coefficient is a
  highly unreliable measure** for the performance of metagenome prediction tools".
- **Microbe–metabolite links are largely cohort-specific — and this is the finding
  that most directly threatens W4 and Q5.** Muller E, Algavi YM, Borenstein E, *A
  meta-analysis study of the robustness and universality of gut
  microbiome-metabolome associations*, Microbiome (2021), PMC8507343. 1,733 samples,
  10 studies: **97** robustly well-predicted metabolites; "other metabolites
  exhibited large variation in predictability across datasets, suggesting a
  **cohort- or study-specific relationship**"; and critically, even robustly
  predicted metabolites were "**predicted by markedly different sets of taxa across
  datasets**."

> **The metabolite-level prediction replicates while the taxon→metabolite edge does
> not — and the taxon→metabolite edge is exactly what a KG stores.**

**Guard.** Tag every functional/metabolite edge with `inference_basis ∈
{measured_metagenome, measured_metabolome, 16S_inferred, GEM_predicted}` and
**exclude `16S_inferred` from health/disease queries by default**. Store
taxon→metabolite edges with `n_cohorts_replicated`, because Muller 2021 shows that
number is usually 1.

### 4.24 Practitioner and community criticism

⚠️ **Access caveat, stated honestly.** **Reddit was entirely unreachable** (both
`www.reddit.com` and `old.reddit.com` refused connections; WebSearch disallows the
domain) and **Biostars returned HTTP 403**. So: **zero Reddit and zero Biostars
findings — not reachable, not absent.** Do not present the absence as community
silence.

**Named senior critics.** Jonathan Eisen (UC Davis) runs an "Overselling the
Microbiome Award" — ~19 posts over 5+ years
(https://phylogenomics.blogspot.com/search/label/overselling%20the%20microbiome).
On a release linking infant microbiome to cognitive development: "**They do not
show ANY role of bacteria in how brains develop.** … They do not show in any way
what is or is not an 'optimal' microbiome. Ridiculous. Dangerous. Deceptive. Scary.
Snake oil."

**A practitioner primer that names our exact problems.** Abhishaike Mahajan, *A
primer on why microbiome research is hard* (Jun 2024),
https://www.owlposting.com/p/a-primer-on-why-microbiome-research — HN: 91 points,
26 comments. "most DNA sequences derived from a metagenomic sequencing run will, in
all likelihood, be **unable to be perfectly matched to any catalogued species**";
different labs with different databases reach contradictory conclusions on
*identical samples*; ~10% of gut sequences unmappable; fungi and viruses largely
ignored; and as of 2024 the only clear clinical success is FMT for *C. difficile*.
HN discussion *Human microbiome myths and misconceptions* (Oct 2023) ran to **217
points / 90 comments** on the same themes.

**AI-slop skepticism — the reputational context this ships into.** *I flagged two
research papers for fake authors and both were accepted as orals*
(https://news.ycombinator.com/item?id=49116721) — 276 points, 162 comments: "Both
papers were accepted for oral presentations **with the condition that they simply
fix the hallucinated references**"; and "If all these papers were not gatekept by
journals, it would be trivially easy to **validate at least the existence of cited
papers**." *AI slop is killing online communities* (834 points, 734 comments) names
the real cost: "**the stuff you don't spot is the stuff you don't spot**." *AI Slop
vs. OSS Security* (193 points) frames the generation/verification asymmetry as
economics: "even a 5% hit rate on a hundred submissions is better than the effort of
manually verifying five findings."

**"Designed for AI agents" — practitioners reject the framing.** *You need to
rewrite your CLI for AI agents* (https://news.ycombinator.com/item?id=47252459), 163
points, 67 comments: "If AI agents are so underdeveloped and useless that they can't
parse out CLI flags, then the answer is **not** to rewrite the CLI"; "**This feels
completely speculative:** there's no measure of whether this approach is actually
effective". And the substantive objection, from someone running agents in
production: "**The failures are almost never, 'the output wasn't structured
enough.' They're context window overflows, permission issues.**"

> This is direct evidence for Part A's A3. The audience that would evaluate this
> graph is hostile to "built for AI agents" as a value proposition and receptive to
> "here is a versioned, filterable, citable dataset". If an MCP server ships, the
> most-upvoted MCP critique (*The "S" in MCP Stands for Security*, 730 points, 183
> comments) asks for exactly one thing: "**Version the tool descriptions** so that
> they can be pinned and do not change."

**Not found**, despite proper searching: any thread specifically about an
LLM-assembled *biological* database or knowledge graph. Abundant material on
AI-generated papers, bug reports and web content; nothing on AI-built bio-databases.

⚠️ **One correction worth carrying, because a hostile reader will use it.** The
uBiome collapse (FBI raid Apr 2019, bankruptcy Sep 2019, SEC charges Mar 2021 over a
$60M fraud) was **an insurance-billing and securities fraud, not invalid microbiome
science** — the highest-engagement HN thread on it (261 points, 173 comments)
contains no criticism of the science, and commenters distinguish it from Theranos
precisely because the sequencing worked. Miscasting it is exactly the error that
would discredit this chapter.

### 4.25 There is almost no published microbiome KG to critique

Europe PMC returns **one** paper for the exact phrase "microbiome knowledge graph"
— Pudavar AE et al., Arch Microbiol (2025), doi:10.1007/s00203-025-04413-0, PMID
40794276 — which says of itself: "**Limited studies describe the construction and
application of KGs capturing these associations for domain experts.**" A broader
sweep of `"knowledge graph" AND microbiome` found no paper building or critiquing a
microbiome-specific KG. Nearest prior art is **MetagenomicKG** (Ma C, Liu S, Won S,
Koslicki D, Bioinformatics 42(7) (2026), PMID 42334937, PMC13330922), whose stated
motivation is our pitfall: "the **inconsistent nomenclature or identifiers** of
these databases present challenges for effective integration."

**The one review that criticises microbiome knowledge bases directly** —
Santangelo BE, Apgar M, Burkhart Colorado AS, Martin CG, Sterrett J, Wall E,
Joachimiak MP, Hunter LE, Lozupone CA, *Integrating biological knowledge for
mechanistic inference in the host-associated microbiome*, Front Microbiol
15:1351678 (2024), PMID 38638909, PMC11024261:

> "**Without mappings to a semantic standard, it is impossible to combine a resource
> with others as the concepts represented are not identical.**"
> "Microbes in gutMGene, gutMDisorder, Disbiome, Amadis, and GIMICA are mapped to
> NCBI Taxonomy, however those in **MDAD and NJS16 are not**."
> "chemical names that are manually curated … **cannot be mapped to an identifier
> in a primary knowledge source**."
> "the same taxa having **different names depending on the date of publication**."

It also notes that most of these databases lack any mapping to MONDO / MeSH / DO for
their *disease* terms — which is Q3's gap, independently confirmed.

**Your upstream sources will die.** Kern F, Fehlmann T, Keller A, *On the lifetime
of bioinformatics web services*, NAR 48:12523 (2020), PMID 33270886, PMC7736811 —
2,396 tools over 133 days: availability ~90% for 2019–2020 tools but "**~50% for
tools published in 2010**"; **20.6% never** worked during the window.

**First-hand, on the day of writing (2026-09-02), two independent attempts each:**
`cuilab.cn` (HMDAD's host) returns **certificate expired**; `disbiome.ugent.be`
returns **ECONNREFUSED**. Also dead or degraded from §1: MDAD's host (never archived
by the Wayback Machine), MACADAM (DNS failure on both the `.inra.fr` and `.inrae.fr`
forms), AGORA2's QC site `metaboreport.live`, and MASI's expired TLS certificate.
Permanent decommissioning cannot be distinguished from a transient outage here — but
**the two most-cited microbe–disease association databases were both unreachable on
the day this was written.**

**Guard.** Vendor and version-pin every upstream snapshot with a checksum and a
fetch date; **never resolve an upstream URL at query time.**

### 4.26 The ten guards, consolidated

1. **Edge key = `(taxon_id, body_site, host_species, disease_id, direction,
   comparison_group)`.** Direction and body site are part of identity, not
   collapsible attributes; contradictions become queryable rather than silently
   resolved. §4.12, §4.22.
2. **Never a bare name or a sequential surrogate id.** Stable numeric ids resolved
   transitively through `merged.dmp`; deleted ids return tombstones, never a 404 a
   later insert can occupy. §4.19, §4.20.
3. **Every edge carries `source_db` + `source_db_version` + `taxonomy_db` +
   `taxonomy_db_version`.** Snapshots vendored and checksummed; nothing upstream
   resolved at query time. §4.7, §4.25 — both major microbe–disease database hosts
   were unreachable the day this was written.
4. **Rank ceiling enforced by assay.** `rank != 'species'` unless the evidence is
   full-length 16S / shotgun / isolate genome. Edgar's 63% figure makes this a hard
   constraint, not a heuristic. §4.17.
5. **`evidence_type` enum + `causal_claim` defaulting false**, with HMA-rodent as
   its own discounted tier (Walter's 36/38). §4.23, §3.3.
6. **`n_distinct_cohorts` and `n_da_methods` on every association**, with defaults
   that hide single-cohort, single-method edges. Lead citation: Tierney et al. 2022
   — a measured ~1-in-3 sign-flip rate, >90% for T1D/T2D. Supporting: Duvallet 51%,
   Nearing 0.8–40.5%, Wirbel 2.8×. §4.1, §4.12, §4.13.
7. **Confounder fields as required schema, not optional metadata**:
   `drugs_controlled[]`, `matched_on[]`, `unmeasured_confounders[]`. The metformin
   story and the T2D 26→0 result are the regression fixtures. §4.15.
8. **Human-curated vs machine-extracted segregated at the schema level**, every
   machine-derived assertion carrying PMID/DOI **plus the exact quoted span**, and a
   published precision figure from a human-audited random sample with the sample
   size stated. SemRep's own strict precision is 0.55. §4.3, §4.24.
9. **A habitat-plausibility check and Waldron's five study-quality tags in v1** —
   faithful extraction from a contaminated paper produces a confidently wrong edge
   that no extraction metric catches. §4.16.
10. **Evaluation hygiene if link prediction is ever scored**: dedupe
    inverse/symmetric edges before splitting, hold out a source-disjoint test set,
    and report a degree-matched baseline alongside the headline metric. §4.4, §4.5,
    §4.8.

### 4.27 Where the evidence is thin — label it thin

- **No Reddit or Biostars data** (unreachable, not absent).
- **No community discussion of LLM-assembled biological databases** (searched;
  absent from reachable venues).
- **No documented case of sign reversal specifically from reference-group choice**,
  though Tierney establishes the general rate.
- **No quantification of duplicate-population inflation.**
- **No variance-explained figure for Costea 2017, the MBQC, or Falony's
  much-quoted 7.7%** — all three are routinely cited with numbers that could not be
  verified in the sources. Do not repeat them.
- **No published head-to-head audit of microbe–disease databases**, and **no
  BugSigDB inter-curator agreement statistic** (§4.11).

## 5. Candidate acceptance queries

Ordered by how commonly the question appears as the **stated purpose** of a
source database or the **entry point** of a published workflow. Each is tagged
with the evidence fields it needs, and whether the current source list —
**NCBI, BugSigDB, Disbiome, HMDB, CARD, Reactome, KEGG, ChEMBL** — can answer it.

---

**Q1. "I have a list of taxa that changed in my cohort. Which published
signatures does it overlap, for which condition, at which body site, and in which
direction?"**
*Why first:* this is the reason `bugsigdbr` exports GMT and the reason
`BugSigDBEnrich` exists; it is BugSigDB's own headline analysis (W1).
*Fields:* signature membership (NCBI tax_id) · `Abundance in Group 1` ·
`Condition`/`EFO ID` · `Body site`/`UBERON ID` · `Host species` ·
`Sequencing type` · group sizes · PMID.
*Coverage:* **YES (BugSigDB)** — but only if the **Signature is a node**, not 34
pairwise edges. This is a schema requirement, not a data gap.

**Q2. "What is reported for taxon X in disease Y, and how strong is each
report?"**
*Fields:* direction per study · study design · sequencing type · n per group ·
statistical test + threshold + MHT correction · PMID.
*Coverage:* **YES (BugSigDB + Disbiome).** BugSigDB carries all of it; Disbiome
adds qualitative outcome + detection method but no design field.

**Q3. "Which taxa are reported in more than one disease, and in which
direction?"** (the disease-specificity / non-specific-dysbiosis check)
*Why third:* it is GMrepo's marker-centric view, SIAMCAT's cross-disease
comparison, and BugSigDB's r = −0.84 analysis — three independent sources built
this question a feature.
*Fields:* Q2's, aggregated per taxon across conditions, **plus normalised disease
terms** so IBD / Crohn's / UC are not three unrelated nodes — but *never* rolled
up silently, since CD and UC separate at **95.1% specificity** on an eight-genus
signature (§4.22).
*Calibration:* Duvallet's 51%, and BugSigDB's four >100-signature genera
(*Streptococcus, Prevotella, Bacteroides, Lactobacillus*), are the expected
answers. A graph that does not reproduce them is under-loaded.
*Coverage:* **PARTIAL.** BugSigDB (EFO) and Disbiome (MedDRA) use different
disease ontologies; the join needs an EFO↔MeSH↔MedDRA mapping the source list
does not provide.

**Q4. "Which taxon–disease associations are supported by more than observational
abundance — animal model, intervention, or human RCT?"**
*This is Part A's A1, stated as a query.*
*Fields:* `evidence_level` with an interventional tier · `Host species` ·
`Study design`.
*Coverage:* **PARTIAL.** BugSigDB records `Study design` (RCT 4.4%) and
`Host species` but has **no evidence-level field at all**; the tier must be
*derived* from design + host. **Missing: gutMDisorder** (the only source curating
interventions as a relation type) and **Peryton** ("experimentally supported" by
name).

**Q5. "Which metabolites does taxon X produce, and is that measured or
predicted?"**
*Fields:* taxon→metabolite direction · evidence tier · pathway/gene · rank ·
citation.
*Coverage:* **NO at the required resolution.** HMDB's `Microbial` origin is a
**boolean flag on the metabolite with no organism slot** (§1.8) — it cannot
answer "which taxon". **Missing: MiMeDB** (Microbial Sources + Metabolic
Reactions with Precursor/Product/Enzyme source organism). **GAP #1.**
*And the answer must carry a replication count.* Muller et al. 2021 found that
even robustly predicted metabolites were "**predicted by markedly different sets
of taxa across datasets**" (§4.23) — the metabolite-level prediction replicates
while the taxon→metabolite edge usually does not. Store
`n_cohorts_replicated`; expect 1.

**Q6. "Which taxa consume metabolite M?"** (cross-feeding — Part A use case 5)
*Fields:* a `CONSUMES` edge with evidence tier and rank.
*Coverage:* **NO. No source on the list carries consumption.** MES = 2PC/(P+C) is
identically zero without it. **Missing: NJC19** (8,224 directed import/export/
degrade events, CC0) for curated edges, and **AGORA2/APOLLO
`computeUptakeSecretion`** (517 consumable / 434 secretable metabolites) or
**MICOM**/`SMETANA` for computed ones. **GAP #2.**

**Q7. "Which AMR genes does taxon X carry, to which drug class, by which
mechanism, and at what call confidence?"**
*Fields:* ARO id · **detection model type** · **RGI hit category** ·
`confers_resistance_to_drug_class` / `_antibiotic` · resistance mechanism ·
**curated-vs-prevalence provenance flag**.
*Coverage:* **YES (CARD)** — with four conditions: carry the model type, carry
the hit category, keep Prevalence-derived edges separated from curated ones, and
**never collapse the chain to `Taxon –has_ARG→ Antibiotic`**. A "276k AMR links"
figure sourced from Prevalence is predicted, not curated; and gene presence is
not phenotype — CARD's own FAQ says "a PERFECT hit does not indicate if the AMR
gene is expressed or if it results in elevated MIC", while AMRFinderPlus and
ResFinder score **54–58% balanced accuracy** against measured resistance
(§4.23). Licensing: CARD's ontology is CC BY 4.0, its sequences/models/prevalence
are not, and commercial-organisation use of the latter is prohibited.

**Q8. "Does drug D inhibit gut bacteria, or get metabolised by them, and which
strains?"**
*Fields:* drug id (ChEMBL/ATC/DrugBank) · **strain-level** taxon · assay +
readout · direction (**inhibits / metabolises / no effect** — negatives matter) ·
gene.
*Coverage:* **PARTIAL.** ChEMBL supplies the drug node and nothing else — no
taxon edge. **Missing: MASI** (typed bidirectional: 4,001 bacteria→substance +
7,770 substance→bacteria) or the Maier/Zimmermann supplementary matrices.
**GAP #3.**

**Q9. "Show me every association for taxon X where the evidence is 16S-only, so I
can down-weight it."**
*Why this high:* it is the direct operationalisation of the expert's complaint,
and 92.5% of BugSigDB is 16S.
*Fields:* `Sequencing type` · `16S variable region` · `Sequencing platform` ·
the **rank at which the taxon was reported**.
*Coverage:* **YES (BugSigDB), partial elsewhere.** Disbiome lumps 16S and shotgun
under "next-generation sequencing"; CARD and HMDB have no such axis.

**Q10. "For disease Y, which depleted taxa are plausible probiotic candidates —
replicated depletion, no transferable AMR, a known beneficial metabolite?"**
*Fields:* Q2 ∪ Q5 ∪ Q7, joined on taxon.
*Coverage:* **PARTIAL — fails on the Q5 leg.** The AMR and depletion legs work;
the metabolite leg has no per-taxon evidence tier without MiMeDB.

**Q11. "Which studies for disease Y controlled for medication or antibiotics?"**
(the metformin trap — Forslund et al. showed a published T2D signature was
confounded by antidiabetic medication, Nature 528:262, 2015, PMID 26633628:
*"we show, using 784 available human gut metagenomes, how antidiabetic medication
confounds these results"*)
*Fields:* `Antibiotics exclusion` · `Confounders controlled for` · `Matched on`.
*Why this matters more than its rank suggests:* Vujkovic-Cvijin et al. (Nature
587:448, 2020) found **26 differentially abundant ASVs in T2D → 0 after matching
on host variables**, and that significance vanished entirely for depression,
autism, lung disease, thyroid disease, migraine and SIBO. An unfiltered graph
will happily serve every one of those edges.
*Coverage:* **YES (BugSigDB), uniquely.** No other source on the list records
confounder control. This is the strongest argument for BugSigDB as the spine.

**Q12. "This paper says *Lactobacillus reuteri*. What is the current name and
tax_id, and does a query for *Limosilactobacillus reuteri* find it?"**
*Fields:* NCBI `merged.dmp` merged ids · `names.dmp` synonym classes (scientific
name / synonym / equivalent name) · rank · **and the LPSN correct-name/synonym
status**, which NCBI does not carry.
*Coverage:* **YES for the easy case (NCBI), NO for the hard one.** Loading merged
ids and synonym classes resolves *L. reuteri*. But the graph must also represent
**authority disagreement**: LPSN keeps ***Lactobacillus rhamnosus*** (the name is
*taxonomically suspended* against *Lacticaseibacillus*) while NCBI taxid 47715
reads *Lacticaseibacillus rhamnosus*; and LPSN keeps ***Prevotella copri*** while
NCBI reads *Segatella copri* — same taxid either way (§4.20). A single "current
name" field cannot express that. This is Part A's A4 as a query, and it is harder
than A4 assumes.

**Q13. "Which pathway or gene carries the production claim for taxon X →
metabolite M?"**
*Fields:* pathway id · gene · organism rank · whether the assignment is
genome-inferred.
*Coverage:* **PARTIAL and misleading if unqualified.** Reactome is human-centric;
KEGG has microbial pathways but the taxon→pathway assignment is genome-inferred,
and gutSMASH *measured* gene abundance to be "almost completely uncorrelated"
with metabolite level in 1,135 individuals. 16S-based inference is worse still —
Matchado et al. 2024 report PICRUSt2's overlap with true metagenome results
collapsing from **654 to 66 KO terms** (§4.23). **Missing: gutSMASH MGC types**
(which encode substrate and product in the type name) and **MACADAM** (PS/PFS
scores) — though MACADAM appears decommissioned (DNS failure on both domain
forms) and MiMeDB's 23.1 M BLAST-propagated pathways are not the same evidence
class as its 25,276 curated reactions.

**Q14. "Which of my changed taxa are just generic dysbiosis markers rather than
disease-specific?"**
*Fields:* prevalence in healthy samples · fraction of signatures reporting
increase vs decrease per taxon.
*Coverage:* **PARTIAL.** BugSigDB supplies the second half; the healthy-prevalence
half comes from GMrepo (9,623 healthy controls in the published analysis) or
`bugphyzz`, neither on the list.

**Q15. "How many association edges in the graph have no evidence level, which
sources do they come from, and which are single-cohort or implausible?"**
*Fields:* an audit over `evidence_level` nullity grouped by source database; plus
`n_distinct_cohorts == 1`, `n_da_methods == 1`, and a **habitat-plausibility
flag** (BugSigDB's own curators asked for one after a faithfully-curated entry
turned out to list hot-spring organisms in a mammalian sample, §4.16).
*Coverage:* **internal** — this is Part A's A1 third bullet
(`CALL ontology_audit()`), and it is the query that keeps the other fourteen
honest. Note that curation fidelity is not data quality: no extraction metric
catches a correctly-extracted bad paper.

---

### Summary of gaps in the current source list

**Gap 1 — no per-taxon metabolite production with an evidence tier.**
HMDB's microbial annotation is a **boolean origin flag on the metabolite with no
organism slot**; it cannot answer "which taxon makes this". Fills Q5, Q10, Q13.
*Candidate:* **MiMeDB** (CC BY-NC; Microbial Sources + Metabolic Reactions
carrying Precursor, Product, Enzyme, Enzyme's source organism, Reaction type and
References). Secondary: **BacDive** (CC BY 4.0, cleanly separates measured from
>90%-confidence genome predictions, but sparse on SCFAs).

**Gap 2 — no consumption edges, so cross-feeding (Part A use case 5) is
unanswerable.** MES = 2PC/(P+C) is zero without consumers. Fills Q6.
*Candidate:* **NJC19** (CC0, 838 species, 8,224 directed import/export/degrade
events plus 912 explicit negatives, curated from 769 sources) for the curated
class; **AGORA2/APOLLO exchange reactions via `computeUptakeSecretion`**, or
**MICOM**/`SMETANA`, for the computed class. These are two different evidence
classes and should not be merged.

**Gap 3 — no drug↔taxon edge.** ChEMBL gives the drug node and nothing that
connects it to a taxon. Fills Q8, and it is also the *defence* against Q11's
confounding trap: without a drug→taxon layer the graph cannot offer "metformin"
as a competing explanation for a T2D edge, which is precisely the error Forslund
et al. documented. *Candidate:* **MASI** (typed bidirectional edges, 806 species,
though its site has an expired certificate) or the Maier 2018 / Zimmermann 2019
supplementary matrices directly, which are strain-level and carry negatives.

**Runner-up gaps**, smaller but real: no interventional taxon–disease evidence
(**gutMDisorder** curates interventions as a relation type; **Peryton** is
"experimentally supported" by name) for Q4; no healthy-baseline prevalence for
the generic-dysbiosis check (**GMrepo**, or `bugphyzz` for per-taxon traits like
"butyrate producing") for Q14; no cross-ontology disease mapping between
BugSigDB's EFO and Disbiome's MedDRA for Q3 — **MONDO** is the natural primary;
and no nomenclatural authority for Q12's hard case, which needs **LPSN**
(CC BY-SA 4.0, with an API) alongside NCBI.

### One structural note that is not a gap

Q1 — the most common question in the survey — fails today not for want of a
source but for want of a **node type**. BugSigDB's unit is the *signature*: a set
of taxa from one experiment with one direction, exported as GMT precisely so
gene-set machinery can consume it. Flattened into pairwise taxon→disease edges,
the set is gone and enrichment is impossible. Everything else in this document is
about which sources to add; this one is about the shape of the graph itself.

**Runner-up gaps**, worth noting but smaller: no interventional taxon–disease
evidence (gutMDisorder / Peryton, Q4); no healthy-baseline prevalence for the
generic-dysbiosis check (GMrepo, Q14); and no cross-ontology disease mapping
between BugSigDB's EFO and Disbiome's MedDRA (Q3).

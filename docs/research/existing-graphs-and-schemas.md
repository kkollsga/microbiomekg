# Existing microbiome knowledge graphs and their schemas

Research agent output, 2026-09-02. Read-only web research; nothing was posted,
registered or submitted anywhere.

**Scope.** This file covers *the graphs and schemas that already exist* — what
they model, how they key entities, how they carry evidence, and where they
break. A sibling agent covers researcher workflows and evidence grading; this
file deliberately does not duplicate that.

**How this feeds `usecases-and-pitfalls.md`.** Part A of the contract makes
three demands that decide most of what follows:

- **A1** — every association edge carries a derived, non-defaulted
  `evidence_level`, and missing evidence must be *countable*.
- **A2** — provenance resolves to a *study* (design, cohort, body site, method,
  group sizes) and a *paper*, with direction stored **per study**.
- **A4** — NCBI tax_id is the canonical key; unresolved names are recorded,
  never dropped.

Every graph below is scored against those three. The short version: **exactly
one existing resource (BugSigDB) satisfies A2 at the study level**, exactly one
schema (Biolink) gives A1 a vocabulary that survives export, and **no existing
microbiome graph satisfies A4 with an auditable trail** — the two that come
closest (KG-Microbe, MetagenomicKG) both leak dangling taxon references, which
their own issue trackers document.

---

## 1. Graphs and databases surveyed

### 1.1 KG-Microbe (Joachimiak lab, LBNL / Knowledge-Graph-Hub)

The most schema-disciplined microbial KG in existence, and the most useful
single template for this project. Modular: a `Core` graph of organismal traits
plus derived graphs that layer biomedical and functional content on top.

| Aspect | Value |
|---|---|
| Subgraphs | `KG-Microbe-Core` (traits, environments, growth), `-Biomedical` (disease + human function), `-Function` (UniProt annotations), `-Biomedical-Function` (merge) |
| Node categories | Organism/strain, chemical, environment, phenotype/trait, enzyme, reaction, pathway, disease, gene, medium, assay |
| Node CURIE prefixes | `NCBITaxon`, `strain:` (minted), `CHEBI`, `KEGG`, `PubChem`, `CAS-RN`, `EC`, `GO`, `Rhea`, `UPA`, `ENVO`, `PATO`, `UBERON`, `FOODON`, `PO`, `MONDO`, `HP`, `HGNC`, `OMIM`, plus minted trait prefixes (`oxygen:`, `temperature:`, `salinity:`, `cell_shape:`, `motility:`, `trophic_type:`, `isolation_source:`, `medium:`, `assay:`, `gram_stain:`, …) |
| Taxon key | `NCBITaxon:<id>` CURIE. Names that cannot be mapped get **minted nodes for unclassified organisms**, wired in with rank and taxonomic-relationship edges — the name is preserved rather than dropped |
| Predicates | Biolink: `has_phenotype`, `produces`, `consumes`, `derives_from`, `participates_in`, `enables`, `capable_of`, `contributes_to`, `occurs_in`, `binds`, `part_of`, `subclass_of`, `related_to`, `associated_with_increased_likelihood_of`, `associated_with_decreased_likelihood_of` |
| Sources | BacDive, MediaDive, Madin et al., BactoTraits, Rhea, UniProt, Disbiome, Wallen et al. (Parkinson's), CTD, plus NCBITaxon/GO/ChEBI/EC/MONDO/HPO/ENVO/UPA ontologies, LPSN, GOLD, METPO |
| Evidence / provenance | **Weak.** Trait–strain provenance survives "in the graph metadata" (strain designations, source ids as node labels). The 2025 preprint documents **no edge-level provenance methodology** for the merged graphs |
| Same-name problem | Strain→taxon parent edges; minted stubs for unresolvable parents (issues #815, #895, #917); LPSN↔NCBITaxon exact-synonym lookup (#589, #590) |
| Serialisation | KGX TSV (nodes.tsv / edges.tsv), merged with the KGX tool |
| Licence | BSD-3-Clause (code). No data licence declared in the 2025 preprint — the merged product inherits KEGG's and others' terms |
| Maintained | **Yes, very actively** — 2,100+ commits, issues filed and closed through 2026 |

**Directly relevant limitations, stated by the authors:** UniProt annotations
are largely *not experimentally validated*; reaction directionality is
*inferred* (eQuilibrator) rather than observed; Disbiome contributes only
"coarse taxonomic resolution" disease associations; and EC / Rhea / GO
redundantly represent the same enzymatic activity, creating inconsistency.

**What its issue tracker reveals** (this is the most valuable part of the whole
survey — see §4):

- **#909** — 706,765 shipped edges use `METPO:2000511`, a term upstream
  obsoleted with no declared replacement.
- **#932** — LPSN references 4,233 deposit CURIEs it never writes a node for.
- **#904** — CultureMech's export points ~13,845 edges at prefixes kg-microbe
  does not declare (`FOODON`, `komodo.medium`, `TOGO`, `MEDIADB`, …).
- **#918 / #933** — merged-graph invariants do not report edge targets with no
  node row; KGX silently *invents* nodes for undeclared endpoints.
- **#892** — 524 strain nodes (2,660 in an older build) carry **two
  taxonomically incompatible NCBITaxon parents**.
- **#638** — BacDive strain DSM 9790 assigned to the wrong species taxid,
  contradicting an existing correct assignment.
- **#919** — 93 NCBITaxon nodes had a BacDive *description sentence* as their
  `rdfs:label`.
- **#899** — deposit nodes minted from in-house designations asserted **false
  `close_match` equivalences**.
- **#683** — "shipped merged KG carries stale + orphaned content".
- **#402** — a BacDive taxon node with id `nan`.

### 1.2 MicrobiomeKG (Translator; Frontiers in Systems Biology 2025)

Built by extracting knowledge assertions from the **supplementary tables** of
microbiome papers. The nearest thing in existence to the "evidence type is the
thing that matters" contract in A1, because it keeps the statistics.

| Aspect | Value |
|---|---|
| Size | v2.1.0: 27,772 nodes, 112,118 edges from 104 supplementary tables across 40 publications (71,602 edges statistically significant) |
| Node categories | Biolink classes: `Disease`, `SmallMolecule`, `OrganismTaxon`, `PhenotypicFeature`, `ChemicalEntity`, `Gene` (28 Biolink classes total) |
| Identifiers | CURIEs, normalised through **BABEL** (Translator's Node Normalizer) |
| Predicates | 8 Biolink predicates; dominant are `biolink:associated_with`, `biolink:correlated_with`, `biolink:affects`; 244 distinct subject-category × predicate × object-category combinations |
| Evidence on edges | p-value, FDR-correction status, **sample size**, effect strength, **statistical test type**, source-table mapping, supplementary-file caption, contextual notes. p ≤ 0.1 cutoff (0.075 in the earlier preprint) |
| Provenance | Publication per assertion; extraction driven by a human-curated config file per supplementary table |
| Serving | TRAPI API via **Plover** (in-memory Biolink KG server) with predicate-hierarchy reasoning and subclass chaining |
| Licence | CC BY-ND 4.0 on the preprint; data availability is via API, no clean bulk-download licence statement |
| Maintained | Active as a Translator component |

**Stated limitation:** coverage. 40 papers against Disbiome's 1,179. It is a
*method* demonstration, not a corpus — but the method (declarative
table→triple config, statistics preserved on the edge) is the one worth
copying.

### 1.3 MetagenomicKG (Bioinformatics 2024/2026)

| Aspect | Value |
|---|---|
| Size | ~1.25M nodes, 56M edges |
| Node types (14) | Microbe, Phenotypic Feature, Disease, KEGG Orthology, Compound, Reaction, Drug, Glycan, Enzyme, Drug Group, AMR, Network, Pathway, Module |
| Taxon key | **Dual**: GTDB for bacteria/archaea, NCBI Taxonomy for viruses/fungi. Genomes without RefSeq/GenBank ids are assigned to the nearest GTDB match at ≥99.5% ANI |
| Node ids | **Minted** — "unified node ID combining type with sequential numbering" (i.e. not the source CURIE) |
| Predicates | Biolink; dominant `genetically_associated_with`, `associated_with`, `subclass_of`, `superclass_of` |
| Sources | GTDB, NCBI Taxonomy, KEGG, BV-BRC, RTX-KG2, MicroPhenoDB, AMRFinderPlus |
| Evidence / provenance | `knowledge_source` attribute per edge + source link. No study-level detail, no statistics |
| Licence | **CC BY-NC-ND 4.0** — non-commercial, no derivatives. Fatal for redistribution |
| Maintained | Published 2024, journal version 2026 |

**Notable good decision:** it **excludes RTX-KG2 edges whose only support is
SemMedDB**, on the grounds that NLP-derived assertions are error-prone. That is
an evidence-level filter applied at build time, and it is worth copying as a
*policy*, not as a deletion — record the exclusion rather than the edge.

**Notable bad decision:** minting sequential internal node ids destroys the
ability to join back to the source vocabulary without a side table, and mixing
GTDB and NCBI taxonomies in one `Microbe` node type means the same organism can
legitimately appear twice.

### 1.4 MicroPhenoDB (Genomics Proteomics Bioinformatics 2020)

| Aspect | Value |
|---|---|
| Content | 5,677 non-redundant microbe–disease associations (1,781 microbes × 542 phenotypes, >22 body sites); 696,934 core-gene→microbe relationships (27,277 genes, 685 microbes) |
| Microbe key | **NCBI Taxonomy id**, with NCIT official names alongside |
| Disease key | **EFO** (Experimental Factor Ontology) |
| Record fields | Accession (`MBP00000900`), **association score −1…+1**, data source (IDSA guideline / NCIT / literature / HMDAD / Disbiome), supporting PMIDs, body site, **direction of abundance change** |
| Score model | `Raw_score = (W_IDSA + W_NCIT + W_Literature) × log(N/n_j)` — a source-weighted, inverse-frequency score. Sign encodes direction (positive = disease correlates with increased abundance) |
| Evidence type | **Not recorded.** The score conflates source reliability, source count and publication count into one number |
| Licence | Open access article; data licence not stated |
| Maintained | Authors promised 6-monthly updates in 2021; no evidence of updates since |

**The score is the anti-pattern.** It is exactly the thing A1 objects to: a
single number that cannot be decomposed back into "was this experimentally
demonstrated?". If MicroPhenoDB is ingested, ingest the *components* (source,
PMIDs, direction) and treat the score as a derived property, never as the
evidence field.

### 1.5 Disbiome (BMC Microbiology 2018)

| Aspect | Value |
|---|---|
| Content | ~1,200 publications, 372 diseases, 1,622 organisms (figures vary by snapshot) |
| Microbe key | NCBI **and** SILVA taxonomy links |
| Disease key | **MedDRA** — a regulatory pharmacovigilance vocabulary, not a disease ontology. Needs mapping to MONDO |
| Record model | An **experiment** row links: Publication ID, Organism ID, Sample ID, Disease ID, Host ID, Control ID, **Method ID**, Location ID |
| Evidence | Detection method recorded; each study scored for **reporting quality** via a standardised questionnaire |
| Direction | Per-experiment abundance change |
| Access | REST-ish JSON endpoints at `disbiome.ugent.be` |
| Maintained | Sporadic; the site is up, curation activity is low |

**Structurally, Disbiome is the closest existing model to A2** — an experiment
node that ties publication, method, disease, control and organism together.
Its weakness is MedDRA (mapping loss to MONDO) and coarse taxonomic
resolution, which KG-Microbe's authors flag explicitly.

### 1.6 BugSigDB (Nature Biotechnology 2023, Waldron lab)

Not a knowledge graph — a curated **signature** database — but it is the only
resource surveyed that satisfies A2 outright, and it should be the spine of any
taxon–disease evidence layer.

| Aspect | Value |
|---|---|
| Content | >2,500 curated signatures from >600 studies (initial release; larger now), 3 host species |
| Taxon key | **NCBI Taxonomy ids**, phylum→strain. Also exports MetaPhlAn lineage strings and plain names |
| Condition key | **EFO** id (`EFO ID` column) |
| Body site key | **UBERON** id (`UBERON ID` column) |
| Export columns (~51) | Study design, PMID, DOI, authors, journal, year, subject location, host species, body site + UBERON ID, condition + EFO ID, **Group 0 / Group 1 names and sample sizes**, statistical test, significance threshold, MHT correction, sequencing type, 16S variable region, sequencing platform, data transformation, LDA score threshold, **abundance direction in Group 1**, NCBI Taxonomy IDs, diversity metrics (Shannon, Chao1, Simpson, Pielou) |
| Access | Bulk download, hourly GitHub snapshots, semi-annual Zenodo releases, `bugsigdbr` Bioconductor client |
| Licence | **Open Data Commons Attribution (ODC-BY) 1.0** per the site's `Project:About`; the paper text says CC BY-NC 4.0 — **the discrepancy must be resolved before commercial redistribution** |
| Maintained | Yes — community curation, ongoing releases |

Every field A2 asks for is a literal BugSigDB column. This is the resource to
build the study model around.

### 1.7 gutMGene v1/v2 (NAR 2022, 2025)

| Aspect | Value |
|---|---|
| Content | Gut microbe → host gene, microbe → metabolite, metabolite → host gene, human + mouse |
| Microbe key | NCBI Taxonomy id |
| Metabolite key | Cross-referenced to **PubChem, HMDB, ChEBI, KEGG, FooDB, MetaboLights** |
| Gene key | NCBI Gene symbol + id |
| Evidence field | **`Evidence` column classifies each association as *causal* or *correlational***: causal = controlled experiments manipulating the microbe or metabolite; correlational = statistical correlation analysis (e.g. Pearson). `Evidence Number` = supporting publication count |
| Other fields | Substrate, sample type, species, experimental method, measurement technique, alteration description (brief + detailed) |
| Licence | Article CC BY-NC; data "freely available" |
| Maintained | v2.0 in 2025 |

**gutMGene is the one source that ships a causal/correlational distinction as a
first-class field.** That field is the single most valuable ingest in the whole
survey for A1, and it must not be flattened into a generic "association".

### 1.8 GMMAD / GMMAD2

| Aspect | Value |
|---|---|
| Content | 3,836 disease–microbe + 879,263 microbe–metabolite associations; **220,690 disease–metabolite associations are predicted, not observed** |
| Fields | Disease name, microbe name, metabolite name, alteration pattern (increase/decrease), experimental method (e.g. 16S), **alteration strength score**, **confidence score**, metabolite chemistry |
| Identifiers | Names, primarily — weakly keyed |
| Maintained | v2.0, last update 2024-07 |

**Hazard:** the predicted edges outnumber the curated disease–microbe edges
57:1 and are stored alongside them. Any ingest must carry the
predicted-vs-observed distinction on the edge or the graph is 98% inference by
volume.

### 1.9 MMiKG (Briefings in Bioinformatics 2023)

Microbiota–gut–brain axis path-mining platform, visualised in GraphXR and
Neo4j, free and open, no login. Literature-derived. Node/edge schema is not
formally published as a model — it is a Neo4j property graph assembled from
literature plus existing resources, with the merge inferring "prospective
connections". Useful as a use-case reference (path mining across the axis), not
as a schema template: **inferred edges are not distinguished from curated ones
in the published description**.

### 1.10 SPOKE (UCSF, Bioinformatics 2023)

| Aspect | Value |
|---|---|
| Size | ~27M nodes / 21 types, 53M edges / 55 types, 41 source databases |
| Microbe handling | An **`Organism`** node type — "all taxonomic levels from NCBI Taxonomy", plus bacterial strains from BV-BRC. Bacterial pathways from KEGG/MetaCyc, `EC` and `Reaction` nodes. There is **no dedicated microbiome node type**; microbes are ordinary organisms |
| Identifiers | NCBI Taxonomy (Organism), Uberon (Anatomy), Reactome/KEGG/WikiPathways (Pathway), EC numbers |
| Edge properties | Retained per source: p-value, Benjamini-Hochberg FDR, log2FC, binding affinity (Kd > Ki > IC50 precedence), STRING confidence ≥0.4, **human-review status and evidence type on selected edges (including organism–disease)** |
| Build | Rebuilt **weekly** by scripted download + integrity check → parent node/edge tables |
| Licence | Paper CC BY; **the graph is deliberately not available as a bulk download**, to avoid redistributing content under 41 incompatible licences. API + neighborhood explorer only |
| Maintained | Yes |

**Two decisions worth copying:** (a) edges keep the source's own statistics
rather than a harmonised score; (b) the build is a scheduled, integrity-checked
refresh, not a one-off. **One decision to note:** the no-bulk-download stance is
an honest response to licence mixing, and it is the fate of any graph that
ingests KEGG.

### 1.11 PrimeKG (Harvard / Zitnik lab, Scientific Data 2023)

| Aspect | Value |
|---|---|
| Node types (10) | anatomy (UBERON), gene/protein (**Entrez**), disease (**MONDO**), effect/phenotype (**HPO** + SIDER side effects collapsed in), drug (**DrugBank**), pathway (**Reactome**), biological process / molecular function / cellular component (**GO**), exposure |
| Microbes | **None.** No taxon node type, no microbial content of any kind |
| Edges | ~4M relationships, 30 edge types; **reverse edges added, then de-duplicated, self-loops removed** |
| Evidence | Source attribution per edge; no evidence typing, no publications on edges |
| Notable | Built a **disease-grouping** layer on top of MONDO because raw MONDO classes ("Autism, susceptibility to, 1/2/x-linked") do not correspond 1:1 to clinical manifestations |
| Licence | MIT (code), CC0 (Harvard Dataverse dataset) |
| Maintained | Snapshot; successors (PrimeKG++, PrimeKG-CL) are separate projects |

**Relevance is negative and instructive.** The flagship disease-centric
biomedical KG has no place for a microbe, which is precisely the gap this
project fills. Its MONDO-grouping problem is a real warning: **MONDO ids are
not clinical concepts**, and a taxon–disease edge keyed on a raw MONDO leaf may
be far more specific than the study that produced it.

### 1.12 Hetionet v1.0 (Himmelstein, eLife 2017)

| Aspect | Value |
|---|---|
| Metanodes (11) | Anatomy (402), Biological Process (11,381), Cellular Component (1,391), Compound (1,552), Disease (137), Gene (20,945), Molecular Function (2,884), Pathway (1,822), Pharmacologic Class (345), Side Effect (5,734), Symptom (438) |
| Microbes | **None** |
| Metaedges | 24; directionality declared at the metaedge level |
| Identifiers | DrugBank (Compound), Disease Ontology / DOID (Disease), Entrez (Gene), Uberon (Anatomy), MeSH (Symptom), UMLS (Side Effect) |
| Edge properties | JSON/Neo4j formats carry URLs, **source and licence per edge**, confidence scores |
| Licence | Repository content CC0; the *composite* is effectively CC BY-NC-SA 4.0 because 4 of 31 sources are non-commercial-only |
| Maintained | **No** — v1.0, 2017, unchanged |

**The one thing to copy from Hetionet: per-edge licence.** It is the only graph
surveyed that records the licence of the source *on the edge itself*, which is
what makes a mixed-licence graph redistributable in parts. Its per-metaedge
directionality declaration is the second.

### 1.13 CKG — Clinical Knowledge Graph (Mann lab)

~16M nodes, ~220M relationships; Neo4j; proteomics-centric (genomics,
transcriptomics, proteomics, metabolomics). Node files are `ID` + attribute
columns; relationship files are edge lists. **No microbial/taxon node type.**
Code MIT, dataset CC BY 4.0. Relevant only as a loader-architecture reference
(clean node/edge TSV contract, documented "adding new resources" path).

### 1.14 BioKG (Walsh et al., CIKM 2020)

Benchmark KG for relational learning, from 13 sources: UniProt, DrugBank, KEGG,
SIDER, HPA, Cellosaurus, Reactome, CTD, IntAct, MedGen, MeSH, InterPro, SMPDB.
Entity types are drug / protein / disease / pathway / genetic-disorder class —
**no taxon or microbe entity type**. Licence is explicitly *mixed* and
enumerated per source in the README (CC BY 4.0, CC BY-NC 4.0, CC BY-NC-SA,
CC BY-SA 3.0, CC0, Apache 2.0, custom) — and the build **requires DrugBank
credentials**, so the graph cannot be redistributed as data at all. Relevance:
a worked example of the licence-mixing trap, and of the "no evidence layer,
because the consumer is an embedding model" design that A1 explicitly rejects.

### 1.15 MicroMap / Graphomics (the product this project responds to)

Read from the public site only.

| Aspect | Value (as publicly stated) |
|---|---|
| Positioning | "verified data plane for biological AI" — curated KG + validated pipelines + provenance tracking, **MCP-native** |
| MicroMap counts | 1.7M+ entities: 1.1M+ taxa, 1,400+ diseases, 6,500+ metabolites, 6,200+ drugs, 2,028 proteins, 1,710 pathways; **63,316 microbe–disease associations**; 276k AMR links; 10k papers |
| Components | **MapForge** (builds the graph — "ingests sources, links entities, **scores confidence on every connection**"), **Workbench** (50+ pipeline steps, multi-tenant RBAC), **Nexus** (agent that reasons over the graph) |
| Access | 60+ API endpoints; MCP; managed / self-hosted / licensed |
| Provenance claim | "Every answer writes back to the graph — with its provenance"; `/docs/provenance` publishes an assertion contract (read 2026-09-03) |
| Schema | **Published in part** (2026-09-03): `/docs/api/schemas` lists 15 node labels and 21 relationship types, `/docs/api/rest-endpoints` ~63 endpoints. **Not published:** the property-level schema, the identifier convention, and any evidence model — the sharper form of the same finding |
| Licence / pricing | Not public; contact required |
| Build claim | Homepage: "built MicroMap … from raw sources in days, no manual curation pipeline". Their ingest-engine page documents an `approve` stage with a reviewer and timestamp before an entity link enters the graph. The two disagree; **this document quotes the documented pipeline**, and the homepage line is the outlier |

**Two observations that matter for positioning.** First, the public surface
advertises a *confidence score per connection* — the MicroPhenoDB anti-pattern
at product scale — and never mentions evidence *type*, which is exactly the
reviewer's complaint quoted in A1. Second, 63,316 microbe–disease associations
against 1.1M taxa implies the association layer is thin relative to the
taxonomy dump; the 1.1M taxa number is approximately the size of NCBI Taxonomy
itself, i.e. the taxonomy is ingested wholesale rather than restricted to taxa
that participate in an assertion.

---

## 2. Schema conventions worth adopting

### 2.1 Biolink Model — the parts that pay for themselves

Biolink is a LinkML-defined universal schema for biomedical KGs (Translator's
lingua franca). **Adopting it wholesale is not recommended** — the class
hierarchy is large, the association classes are numerous, and the reification
requirement (edges as `Association` instances) fights a property-graph loader.
But four slot families are cheap, flat, and make a later Biolink/KGX export a
mechanical transform rather than a re-model.

**(a) Knowledge-source retrieval provenance.** Biolink models the *chain* of
resources an assertion passed through:

| Slot | Meaning |
|---|---|
| `biolink:primary_knowledge_source` | "the furthest upstream resource in the chain that the data creator can identify". **Exactly one** per association |
| `biolink:aggregator_knowledge_source` | a resource that retrieved and possibly transformed the knowledge from another resource. Multivalued |
| `biolink:supporting_data_source` | a resource providing data that was *computed on* to generate new knowledge |
| `biolink:knowledge_source` | abstract parent; avoid — it does not state the role |

Values are `infores:` CURIEs (`infores:disbiome`, `infores:bugsigdb`). The
guidance is explicit: *minimally distinguish primary from aggregator.*

**(b) `knowledge_level`** — the 7 permissible values, verbatim:

| Value | Definition |
|---|---|
| `knowledge_assertion` | "A statement of purported fact that is put forth by an agent as true, based on assessment of direct evidence." |
| `logical_entailment` | "A statement reporting a conclusion that follows logically from premises representing established facts or knowledge assertions." |
| `prediction` | "A statement of a possible fact based on probabilistic forms of reasoning over more indirect forms of evidence, that lead to more speculative conclusions." |
| `statistical_association` | "A statement that reports concepts representing variables in a dataset to be statistically associated with each other in a particular cohort." |
| `text_co_occurrence` | "A statement reporting that mentions of two concepts in some corpus of text occur together at a statistically significant frequency." |
| `observation` | "A statement reporting (and possibly quantifying) a phenomenon that was observed to occur - absent any analysis or interpretation." |
| `not_provided` | "The knowledge level is not provided, typically because it cannot be determined from available information." |

This single enum answers most of A1 by itself: a BugSigDB differential-abundance
signature is `statistical_association`; a gutMGene *causal* record is
`knowledge_assertion`; a GMMAD predicted disease–metabolite link is
`prediction`; a SemMedDB-only edge is `text_co_occurrence`. **`not_provided` is
the countable bucket A1 demands** — it is a real value, not a null.

**(c) `agent_type`** — the 8 permissible values, verbatim: `manual_agent`,
`automated_agent`, `data_analysis_pipeline`, `computational_model`,
`text_mining_agent`, `image_processing_agent`,
`manual_validation_of_automated_agent`, `not_provided`. For this graph,
`data_analysis_pipeline` covers 16S/shotgun differential-abundance output
("report the direct results of the analysis … do not interpret/infer broader
conclusions"), `manual_agent` covers curated causal claims, and
`computational_model` covers GMMAD-style predictions.

`knowledge_level` × `agent_type` is Biolink's designed replacement for exactly
the single-confidence-score pattern MicroPhenoDB and MicroMap use.

**(d) Statistics and qualifiers.** `biolink:p_value` (float, on `Association`)
and `biolink:adjusted_p_value` (inherits from it) exist as first-class slots.
Direction is modelled with qualifier slots —
`object_direction_qualifier` (`increased` / `decreased`),
`subject_direction_qualifier`, `*_aspect_qualifier`,
`anatomical_context_qualifier` — which is how "Bacteroides is *increased* in
CRC, in *stool*" is said without minting a predicate per direction.
`biolink:publications` is multivalued and holds PMID/DOI CURIEs.
`biolink:has_evidence` (maps to `RO:0002558`) is multivalued with range
`InformationContentEntity` — in practice ECO CURIEs go here.

### 2.2 ECO — the Evidence and Conclusion Ontology

~600 terms under two roots: **`evidence`** (`ECO:0000000`) and **`assertion
method`**. `experimental evidence` is `ECO:0000006`; `experimental evidence used
in manual assertion` is `ECO:0000269` (the cross-product form). The assertion
branch has exactly two terms — *automatic assertion* and *manual assertion* —
and every evidence term has a child for each.

ECO is the right vocabulary for `has_evidence`, but it is **not** the right
vocabulary for A1's `evidence_level` ladder. ECO has no term for "16S
differential abundance in a case-control cohort" versus "shotgun differential
abundance" versus "germ-free mouse colonisation". The correct arrangement is
two fields: a **project-controlled `evidence_level`** carrying the ladder A1
specifies, and an **ECO CURIE** alongside it for interoperability. Do not try to
express the ladder in ECO; you will end up with everything mapped to
`ECO:0000006` and no information.

### 2.3 Flattening Biolink onto property-graph edges

Biolink is RDF/LinkML-shaped; a Neo4j-style edge is flat. The mapping is
mechanical if — and only if — you avoid three things:

1. **Do not merge multivalued slots into a delimited string** without deciding
   the delimiter up front. `publications` and `has_evidence` are multivalued;
   pick one representation (list property if the store supports it, otherwise
   a `|`-joined string with a documented separator) and never mix.
2. **Do not encode direction into the relationship type.** Biolink's qualifier
   pattern exists because `associated_with_increased_likelihood_of` /
   `..._decreased_...` doubles the predicate vocabulary and makes "any
   association between X and Y" a two-branch query. KG-Microbe uses the doubled
   predicates; MicrobiomeKG uses qualifiers. Follow MicrobiomeKG.
3. **Do not let `primary_knowledge_source` become a list.** Biolink says
   exactly one. If two sources both claim to be primary, that is *two edges*,
   not one edge with two sources — and keeping them separate is what makes A2's
   "direction stored per study, never aggregated" enforceable.

---

## 3. Identifier conventions per entity

### 3.1 Taxa

**Canonical: `NCBITaxon:<id>` (prefixed CURIE, not a bare integer).**

- A bare `562` is ambiguous the moment a second numeric namespace enters the
  graph, and it silently type-collides with any other integer id. Every
  Biolink-shaped graph surveyed (KG-Microbe, MicrobiomeKG, MetagenomicKG,
  SPOKE) uses the CURIE form. BugSigDB ships bare ids in a column named
  `NCBI Taxonomy IDs` — prefix them at load.
- **Store `merged.dmp` and `delnodes.dmp` resolution as data, not as a
  one-time transform.** NCBI's own guarantee is: taxids are never reused, but
  they *are* merged (synonymised) and deleted. `merged.dmp` maps secondary →
  primary; `delnodes.dmp` lists deletions. There is an explicit documented hole:
  a taxid can disappear from NCBI pages **without appearing in either file**.
  So the loader needs a third state — *unresolvable* — and A4 requires it be
  recorded rather than dropped.
- Cross-refs to store as properties: `gtdb_id` (GTDB is a *different*
  taxonomy, not a synonym — MetagenomicKG mixes them in one node type and
  should not be copied here), `silva_id` (Disbiome ships these),
  `lpsn_id`, `bacdive_id`, `metaphlan_lineage` (BugSigDB), and the **source's
  verbatim name string**.
- **The verbatim name is not optional.** The 2020 Lactobacillaceae
  reorganisation moved 300+ species out of *Lactobacillus* into 23 new genera;
  *Clostridium difficile* → *Clostridioides*; *Propionibacterium acnes* →
  *Cutibacterium*. A paper published in 2018 says "Lactobacillus reuteri"; the
  current taxid resolves to *Limosilactobacillus reuteri*. Both strings must
  survive, because a user searching the literature searches the old one.
- Rank must be a property (`taxon_rank`), because strain→species promotion is
  a lossy operation that A4 requires be auditable.

### 3.2 Diseases

**Canonical: `MONDO:<id>`.** Cross-refs as properties: `efo_id`, `doid_id`,
`meddra_id`, `ncit_id`, `mesh_id`, `umls_cui`, `hp_id` (when the source gave a
phenotype rather than a disease).

- MONDO is the merge hub by construction — it is "a semi-automatically
  constructed ontology that merges in multiple disease resources", with
  **curated 1:1 equivalence axioms validated by OWL reasoning**, not loose
  `hasDbXref` strings. Mappings ship in **SSSOM** format plus SKOS and
  `oboInOwl:hasDbXref`. Mappings exist to OMIM, Orphanet, EFO, DOID, NCIT.
- **What the sources actually ship, and the mapping burden it creates:**
  - **BugSigDB → EFO.** Direct, clean, one column. EFO→MONDO is a
    well-populated MONDO mapping set.
  - **Disbiome → MedDRA.** MedDRA is a *pharmacovigilance* vocabulary and is
    **licence-restricted** (MSSO subscription). MONDO's MedDRA coverage is
    thinner than its EFO/DOID coverage. Expect a residue and record it.
  - **MicroPhenoDB → EFO.** Same path as BugSigDB.
  - **Hetionet → DOID**, **PrimeKG → MONDO**, **MetagenomicKG →** whatever
    RTX-KG2/MicroPhenoDB gave it.
- **Use `skos:exactMatch` only.** Mondo's own guidance and the practice of
  downstream consumers is to take exact matches and reject close matches, "to
  reduce noise and prevent problems in the ontology merging".
- **Heed PrimeKG's finding:** MONDO leaves are not clinical concepts. Store the
  study's own disease string next to the MONDO id, and expect to need a
  grouping layer for query ergonomics ("colorectal cancer" spanning many
  MONDO leaves).

### 3.3 Metabolites

**Canonical: `CHEBI:<id>` where one exists; otherwise `HMDB:<accession>`.**

- ChEBI is an OBO ontology with a real class hierarchy (so `subclass_of`
  queries work — "any short-chain fatty acid"), is CC BY, and is the prefix
  KG-Microbe and Biolink both prefer. HMDB is the better *coverage* for human
  metabolites but is a flat catalogue and is **CC BY-NC in practice**
  ("re-distribution for commercial purposes requires explicit permission").
- **HMDB's XML carries the cross-refs you need**, per record:
  `chebi_id`, `kegg_id`, `pubchem_compound_id`, `drugbank_id`, `foodb_id`,
  plus UniProt/PDB protein links. ~220k entries, 130+ fields. So HMDB is the
  right *bridge* file even when it is not the canonical key.
- Cross-refs to store: `hmdb_id`, `kegg_compound_id` (`C#####`),
  `pubchem_cid`, `inchikey`, `cas_rn`, `foodb_id`.
- **Store the InChIKey.** It is the only identifier in this list that is
  computable from structure, so it is the fallback join when two sources share
  no id — and the only one that detects a mis-mapping rather than propagating
  it.
- **KEGG compound ids are a licence liability** (§3.9). Store them as
  cross-reference properties; do not make them a key and do not redistribute
  KEGG-derived *content*.

### 3.4 Pathways

**Canonical: `REACT:R-HSA-<id>` for host pathways; `KEGG:map<id>` /
`KEGG:ko<id>` for microbial/orthology pathways — kept as separate namespaces,
never merged.**

- Reactome ids are species-stamped (`R-HSA-` human, `R-MMU-` mouse) and
  Reactome is **CC0**, so it is safe to redistribute. PrimeKG, Hetionet and
  SPOKE all use it.
- KEGG's `map#####` (reference), `hsa#####` (human), `ko#####` (orthology) and
  `M#####` (module) are the only practical vocabulary for *microbial* pathway
  content — MetagenomicKG's whole functional layer is KEGG — but see §3.9.
- MetaCyc/BioCyc appear in SPOKE; licence-restricted, avoid.
- Do **not** attempt Reactome↔KEGG pathway equivalence. They partition biology
  differently and there is no maintained exact-match set; a merged pathway node
  is a silent wrong answer.

### 3.5 Drugs / chemicals used as drugs

**Canonical: `CHEBI:<id>` for the chemical entity; `DRUGBANK:<id>` as the
cross-ref most sources speak; `CHEMBL:<id>` for bioactivity provenance;
`RXCUI:<id>` for clinical/prescribing identity.**

- The problem is real and well documented: paracetamol is simultaneously
  `UMLS:C0000970`, `DRUGBANK:DB00316`, `CHEBI:46195`, `CHEMBL112`.
- **DrugBank is not redistributable.** BioKG's build literally requires
  DrugBank credentials, which is why BioKG ships as a build script rather than
  as data. Hetionet and PrimeKG both key drugs on DrugBank and both inherit its
  non-commercial terms. **Do not make DrugBank the canonical key** for a graph
  intended to be redistributed; store it as a property.
- RxNorm (RXCUI) is public-domain NLM and is the right identifier for "the
  thing a clinician prescribes", which is a different concept from "the
  molecule". Keep both; do not collapse.
- Cross-refs to store: `drugbank_id`, `chembl_id`, `rxcui`, `unii`,
  `pubchem_cid`, `atc_code`.
- **Canonicalisation method to copy:** Monarch/RTX-KG2's approach — build a
  graph of id-equivalence assertions, run **clique detection**, then elect one
  representative CURIE per clique. RTX-KG2 ships this as two artefacts, a
  pre-canonicalised graph (duplicates preserved as distinct nodes) and a
  canonicalised one. Shipping both is what makes a false merge detectable
  after the fact.

### 3.6 Genes and proteins

**Canonical: `UniProtKB:<accession>` for proteins; `NCBIGene:<id>` for genes.**

- For *microbial* genes, UniProtKB is the only identifier with cross-species
  coverage; KG-Microbe's functional layer is built on it (32,662 microbes).
  Note its authors' warning that many UniProt functional annotations are
  computational, not experimental — so a UniProt-derived edge is
  `agent_type=automated_agent`, not `manual_agent`.
- For *host* genes, gutMGene ships NCBI Gene symbols + ids; PrimeKG uses
  Entrez; RTX-KG2's documented preference order is Ensembl > NCBI Gene > HGNC.
  Store `hgnc_id`, `ensembl_gene_id`, `gene_symbol` as properties.
- **A bare gene symbol is never a key** — symbols are ambiguous across species
  and change over time.

### 3.7 AMR

**Canonical: `ARO:<id>`** (Antibiotic Resistance Ontology, e.g. `ARO:3000159`).

- CARD is organised as four ontologies — ARO (resistance concepts), Model
  Ontology, Relations Ontology, and **NCBITaxon for source organisms and
  taxonomic distribution** — so the taxon join is native and needs no mapping.
- **Licence: CC BY 4.0**, one of the few cleanly redistributable sources in
  this domain.
- Cross-refs: `card_url`, `ncbi_amr_gene_symbol` (AMRFinderPlus, which is what
  MetagenomicKG used), `card_model_id`.

### 3.8 Body site, host, study

- Body site: **`UBERON:<id>`** — BugSigDB ships it as a column, SPOKE and
  PrimeKG both use it.
- Host species: **`NCBITaxon:9606`** etc. — same namespace as microbial taxa,
  which is correct and is what BugSigDB does (`Host species`).
- Publication: **`PMID:<id>`** primary, `DOI:<doi>` fallback. Both as CURIEs.
- Study/experiment: a **minted** id is unavoidable (no external authority
  exists), but it must be *derived deterministically* from source + source
  record id so a rebuild reproduces it. MetagenomicKG's sequential minting is
  the counter-example — it does not survive a rebuild.

### 3.9 Licence map (this determines what can ship)

| Source | Licence | Redistributable? |
|---|---|---|
| NCBI Taxonomy, RxNorm, MeSH, NCBI Gene | US public domain / NLM terms | Yes |
| Reactome | CC0 | Yes |
| ChEBI, GO, UBERON, MONDO, ECO, HPO, ENVO | CC BY 4.0 | Yes, with attribution |
| CARD / ARO | CC BY 4.0 | Yes |
| UniProt | CC BY 4.0 | Yes |
| BugSigDB | ODC-BY 1.0 per site; CC BY-NC 4.0 per paper | **Resolve the discrepancy first** |
| Disbiome | not clearly stated | Ask / treat as unclear |
| HMDB | CC BY-NC in effect; commercial use needs explicit permission | Non-commercial only |
| gutMGene / GMMAD | CC BY-NC (article) | Non-commercial only |
| MetagenomicKG | **CC BY-NC-ND 4.0** | No derivatives — cannot be reshaped |
| DrugBank | CC BY-NC 4.0 + credentialled download | No |
| **KEGG** | Academic-use-only API; **subscription for organisational/commercial use**; unclear whether subscribers may disseminate large-scale derived data; on termination, subscribers must **delete derivative data including ML models** | **No** |
| MedDRA | MSSO subscription | No |
| SPOKE | CC BY paper; graph deliberately not bulk-downloadable | N/A |
| Hetionet | CC0 for original content; composite effectively CC BY-NC-SA | Partial |

**KEGG is the single biggest structural constraint on this graph.** Any
microbial-function layer that mirrors KEGG content is undistributable, and the
deletion-on-termination clause reaches derived models. Store KEGG ids as
cross-reference *pointers* and source function from Rhea/EC/GO/UniProt (all
open) instead. This is what KG-Microbe does and it is not an accident.

---

## 4. Known failure modes

Each of these is drawn from a source's own tracker, limitations section, or a
published review — not from speculation.

**F1 — Dangling edge endpoints, silently materialised.** KGX **invents nodes**
for edge endpoints that have no node row, so a broken reference becomes a
label-less node instead of an error (kg-microbe #918, #933). LPSN references
4,233 CURIEs it never writes nodes for (#932); CultureMech points ~13,845 edges
at prefixes the graph does not declare (#904). *Guard:* a merged-graph
invariant that every edge endpoint has a node row **and** a declared prefix,
run as a build gate, not a report.

**F2 — Obsoleted upstream terms shipped as live ids.** 706,765 kg-microbe edges
use `METPO:2000511`, obsoleted upstream with no declared replacement (#909), and
a companion issue notes the vendored deprecation set "can go stale … and
nothing running in CI would notice" (#927). *Guard:* pin ontology versions,
diff obsoletions on every refresh, and fail the build on an obsolete id in a
shipped artefact.

**F3 — Taxid drift, in three distinct forms.** (a) *Merged* taxids —
`merged.dmp` maps secondaries to primaries; a graph built before a merge and a
query written after it disagree. (b) *Deleted* taxids — `delnodes.dmp`, plus
NCBI's documented hole where a taxid vanishes from the web pages **without**
appearing in either file. (c) *Renamed* taxa — the 2020 Lactobacillaceae split
(300+ species, 23 new genera), *Clostridioides*, *Cutibacterium*. Downstream:
`shenwei356/taxid-changelog` exists specifically because this drift is
continuous. *Guard:* resolve through `merged.dmp` at load, record the
pre-resolution id and the verbatim source name on the edge, and count
unresolvable names as a first-class audit metric (A4).

**F4 — Incompatible parents from independent sources.** 524 kg-microbe strain
nodes (2,660 in an older build) carry **two taxonomically incompatible
NCBITaxon parents** (#892); the multi-parent guard existed per-transform but
nothing checked the merged graph (#896). BacDive assigned DSM 9790 to the wrong
species, contradicting an existing correct assignment (#638). *Guard:* the
invariant belongs **where sources meet** (the merge), not in each transform.

**F5 — Free text leaking into identity fields.** 93 NCBITaxon nodes carried a
BacDive *description sentence* as their `rdfs:label` (#919); a taxon node with
id `nan` (#402); underscores in NCBITaxon scientific names (#428). *Guard:*
shape assertions on every identity field at ingest — a label is not a sentence,
an id matches its prefix's pattern.

**F6 — False equivalence assertions from name matching.** kg-microbe minted
`close_match` edges between deposit nodes on the basis of in-house designations
that turned out not to be equivalent (#899), and separately found that a
"contested-deposit" report *overstated* the conflict (#908). Translator's
experience is the same at scale: "false merges introduce factually incorrect
edges that propagate throughout downstream queries and ML models." *Guard:*
never assert equivalence from name string match alone; keep the
pre-canonicalised form (RTX-KG2's two-artefact pattern) so a merge is
reversible.

**F7 — Provenance loss at merge, and semantic loss at predicate
normalisation.** RTX-KG2 maps **1,228 source relationship types onto 77 Biolink
predicates**, with acknowledged "semantic loss of precision" (several distinct
antagonist relations collapse to one `decreases_activity_of`). Its authors also
name the structural problem: "knowledge sources that are important connectors …
do not provide structured provenance information." *Guard:* keep the source's
own verbatim relation string on the edge alongside the normalised predicate.
RTX-KG2 does this (`relation`, `relation_label` next to `predicate`); copy it.

**F8 — Edge inflation from many-to-many expansion.** PrimeKG's build adds
reverse edges then de-duplicates then removes self-loops — the pipeline exists
because the expansion produces duplicates by construction. GMMAD ships **220,690
predicted** disease–metabolite associations against 3,836 curated disease–microbe
ones. MicroPhenoDB's 696,934 gene–microbe rows come from 27,277 genes × 685
microbes — a cross-product, not 696,934 observations. MicroMap's 276k AMR links
against 1.1M taxa has the same shape. *Guard:* count edges **per source record**,
not per source; a source contributing more edges than it has records is
expanding, and the expansion factor belongs in the audit output.

**F9 — "Association" edges that mix correlation and causation.** The review
literature is explicit that microbe–disease associations "can be divided into
causation vs. correlation/inverse causation (e.g. reduced immunity resulting in
bacterial growth) or negation of a previously reported relation", and that
computational models over these databases "still cannot determine how the
microbial abundances influence disease status". MicrobiomeKG's three dominant
predicates are `associated_with`, `correlated_with`, `affects` — the first is
undifferentiated. gutMGene v2 is the counter-example: an explicit `Evidence`
column separating causal from correlational. *Guard:* the `evidence_level`
ladder from A1, populated from source fields, never defaulted.

**F10 — Single confidence scores that cannot be decomposed.** MicroPhenoDB's
`(W_IDSA + W_NCIT + W_Literature) × log(N/n_j)` folds source reliability, source
count and publication count into one signed number. GMMAD ships "alteration
strength score" and "confidence score". MicroMap advertises "scores confidence
on every connection". None of these can answer "is this experimentally
demonstrated?" — which is the reviewer's actual question in A1. *Guard:* store
the components; derive the score in the query if anyone wants one.

**F11 — Stale content shipped alongside fresh.** kg-microbe #683: "shipped
merged KG carries stale + orphaned content"; #828: January merged TSVs sitting
next to the current tarball. *Guard:* a build stamp per artefact and a gate that
refuses to publish a merge containing rows from a prior build.

**F12 — Two taxonomies in one node type.** MetagenomicKG uses GTDB for
bacteria/archaea and NCBI for viruses/fungi, in one `Microbe` type, with
GTDB-Tk ≥99.5% ANI assignment for unplaced genomes. The same organism can
therefore appear twice with no edge between the two nodes. *Guard:* one
canonical taxonomy; the other as a cross-reference property.

**F13 — Licence contamination.** BioKG requires DrugBank credentials to build
and therefore cannot ship as data. SPOKE is deliberately not bulk-downloadable
"to preserve integrity of the original databases and prevent redistribution of
content under multiple licences". Hetionet's CC0 contribution sits inside a
CC BY-NC-SA composite. *Guard:* Hetionet's per-edge licence property (§1.12) —
it is the only mechanism surveyed that makes a mixed-licence graph
partially redistributable.

**F14 — Text-mined edges treated as equal to curated ones.** MetagenomicKG
explicitly excludes RTX-KG2 edges supported only by SemMedDB, "prone to errors".
MMiKG merges literature-derived and inferred edges without a published
distinction. *Guard:* `knowledge_level=text_co_occurrence` +
`agent_type=text_mining_agent` makes this one WHERE clause instead of a policy
decision baked into the build.

---

## 5. Recommendations

### (a) Canonical identifier per entity type

| Entity type | Canonical key | Form | Cross-refs stored as properties | Rationale / source |
|---|---|---|---|---|
| Taxon | **NCBITaxon** | `NCBITaxon:562` (prefixed CURIE, never bare `562`) | `gtdb_id`, `silva_id`, `lpsn_id`, `bacdive_id`, `metaphlan_lineage`, `source_taxon_name` (verbatim), `taxon_rank`, `ncbitaxon_id_as_given` (pre-`merged.dmp`) | A4 mandates it; every Biolink-shaped graph surveyed uses the CURIE form; BugSigDB ships bare ids that must be prefixed at load |
| Disease | **MONDO** | `MONDO:0005575` | `efo_id`, `doid_id`, `meddra_id`, `ncit_id`, `mesh_id`, `umls_cui`, `source_disease_name` (verbatim) | MONDO carries curated 1:1 equivalence axioms validated by OWL reasoning, not loose xrefs, and ships them in SSSOM; BugSigDB and MicroPhenoDB give EFO, Disbiome gives MedDRA — both map through MONDO |
| Phenotype (non-disease) | **HP** | `HP:0002014` | `efo_id`, `source_phenotype_name` | Separate node type from disease; PrimeKG's collapse of HPO phenotypes and SIDER side effects into one `effect/phenotype` type is a merge that cannot be undone |
| Metabolite / chemical | **CHEBI**, falling back to **HMDB** | `CHEBI:30089` / `HMDB:HMDB0000042` | `hmdb_id`, `kegg_compound_id`, `pubchem_cid`, `inchikey`, `cas_rn`, `foodb_id`, `drugbank_id` | ChEBI is CC BY with a real subclass hierarchy (so "any SCFA" is one query); HMDB has better human coverage but is flat and CC BY-NC — and its XML already carries `chebi_id`/`kegg_id`/`pubchem_compound_id`/`drugbank_id`/`foodb_id`, making it the bridge file |
| Pathway (host) | **REACT** | `REACT:R-HSA-71291` | `kegg_pathway_id`, `wikipathways_id` | Reactome is CC0 and species-stamped |
| Pathway (microbial) | **KEGG**, as a *separate namespace* | `KEGG:map00650`, `KEGG:ko00650` | `metacyc_id`, `unipathway_id`, `ec_numbers` | Only practical microbial-pathway vocabulary, but never merged with Reactome — they partition biology differently and no maintained exact-match set exists |
| Drug (molecule) | **CHEBI** | `CHEBI:46195` | `drugbank_id`, `chembl_id`, `rxcui`, `unii`, `atc_code`, `pubchem_cid` | DrugBank must not be the key: it is CC BY-NC and credentialled (BioKG ships as a build script because of it), and Hetionet/PrimeKG inherit its terms by keying on it |
| Drug (clinical product) | **RXCUI** | `RXCUI:161` | `ndc`, `atc_code` | Public-domain NLM; "what is prescribed" is a different concept from "the molecule" — keep both, do not collapse |
| Protein | **UniProtKB** | `UniProtKB:P0A7B8` | `pdb_ids`, `interpro_ids` | Only cross-species-covering protein id; KG-Microbe's whole functional layer is built on it |
| Host gene | **NCBIGene** | `NCBIGene:7124` | `ensembl_gene_id`, `hgnc_id`, `gene_symbol` | gutMGene ships NCBI Gene ids and symbols; a bare symbol is never a key |
| AMR determinant | **ARO** | `ARO:3000159` | `card_model_id`, `ncbi_amr_gene_symbol` | CARD is CC BY 4.0 and already keys source organisms on NCBITaxon, so the taxon join is native |
| Body site | **UBERON** | `UBERON:0001988` | `source_body_site_name` | BugSigDB ships it as a column; SPOKE and PrimeKG both use it |
| Publication | **PMID**, falling back to **DOI** | `PMID:29866037` / `DOI:10.1186/s12866-018-1197-5` | — | CURIE form so it round-trips into `biolink:publications` unchanged |
| Study / experiment | **minted, deterministic** | `STUDY:<source>-<source_record_id>` | `source_record_id` | No external authority exists. Derive it from source + source key so a rebuild reproduces it — MetagenomicKG's sequential minting does not survive a rebuild |

**One rule underneath all of these:** the canonical key is prefixed, the
cross-refs are properties, and **the source's verbatim string is always kept**.
Verbatim names are what make F3 (taxid drift) and F6 (false equivalence)
auditable after the fact rather than invisible.

### (b) Minimal evidence / provenance property set per association edge

Fifteen properties. Every one maps to a Biolink slot or is explicitly named as
project-local, so a KGX/Biolink export later is a rename, not a re-model.
Nothing here requires adopting Biolink's class hierarchy or edge reification.

| Property (proposed name) | Type | Biolink slot it exports to | Required? | Purpose |
|---|---|---|---|---|
| `primary_source` | string, `infores`-style token (`bugsigdb`, `disbiome`, `gutmgene`) | `biolink:primary_knowledge_source` | **Yes** — exactly one | The furthest-upstream resource that can be identified. If two sources both claim primary, that is two edges, not one edge with two values |
| `aggregator_source` | list[string] | `biolink:aggregator_knowledge_source` | No | Intermediates the assertion passed through, including this graph itself |
| `source_record_id` | string | (no Biolink slot — keep as edge property / `xref`) | **Yes** | The source's own primary key. Without it an edge cannot be round-tripped, re-verified, or diffed across a source refresh |
| `publications` | list[CURIE] (`PMID:…`, `DOI:…`) | `biolink:publications` | **Yes** (may be empty, never absent) | A2. Empty-but-present is what makes "how many edges have no paper?" one query |
| `knowledge_level` | enum — **Biolink's 7 values verbatim**: `knowledge_assertion`, `logical_entailment`, `prediction`, `statistical_association`, `text_co_occurrence`, `observation`, `not_provided` | `biolink:knowledge_level` | **Yes** | The interoperable half of A1. Never defaulted — `not_provided` is a real, countable value, not a null |
| `agent_type` | enum — **Biolink's 8 values verbatim**: `manual_agent`, `automated_agent`, `data_analysis_pipeline`, `computational_model`, `text_mining_agent`, `image_processing_agent`, `manual_validation_of_automated_agent`, `not_provided` | `biolink:agent_type` | **Yes** | Separates "a curator asserted this" from "a pipeline emitted this". Together with `knowledge_level` this replaces the single-confidence-score pattern |
| `evidence_level` | enum — **project-controlled**: `observational_16s`, `observational_shotgun`, `interventional_clinical`, `in_vivo_model`, `in_vitro`, `computational_predicted`, `unknown` | exports as an ECO CURIE in `biolink:has_evidence` + a qualifier | **Yes** | A1's ladder. ECO cannot express it (no term distinguishes 16S from shotgun differential abundance), so it is project-local by necessity — and `unknown` is countable, not null |
| `evidence_code` | list[CURIE] (`ECO:0000269`, `ECO:0000006`) | `biolink:has_evidence` (→ `RO:0002558`) | No | ECO interoperability layer alongside `evidence_level` |
| `direction` | enum `increased` / `decreased` / `no_change` / `not_applicable` | `biolink:object_direction_qualifier` | **Yes** for abundance edges | A2: direction is per-study and must never be aggregated. Store it as a qualifier, **not** by doubling the relationship type (KG-Microbe's `associated_with_increased_likelihood_of` pattern makes "any association" a two-branch query) |
| `p_value` | float | `biolink:p_value` | No | Real Biolink slot on `Association` |
| `p_value_adjusted` | float | `biolink:adjusted_p_value` | No | Inherits from `p_value` in Biolink |
| `effect_size` | float + `effect_size_type` string | (edge attribute) | No | MicrobiomeKG and SPOKE both keep the source's own statistic rather than harmonising |
| `study_id` | CURIE (`STUDY:<source>-<id>`) | edge → `Study` node | **Yes** for abundance edges | A2's spine: design, cohort, body site, method and per-group sample sizes hang off the study node, not off the edge. BugSigDB's export gives every one of these fields directly |
| `source_relation` | string, verbatim | (edge attribute) | **Yes** | RTX-KG2's `relation` / `relation_label` next to `predicate`. Predicate normalisation is lossy by construction (1,228 → 77 in RTX-KG2); this is the only thing that makes the loss recoverable |
| `source_licence` | string (SPDX-ish token) | (edge attribute) | **Yes** | Hetionet's per-edge licence. It is what lets a mixed-licence graph be redistributed in parts instead of not at all, and KEGG makes that non-optional here |

Notes on shape:

- **Multivalued properties** (`publications`, `aggregator_source`,
  `evidence_code`) — pick one representation up front (native list, or
  `|`-joined with a documented separator) and never mix. This is the cheapest
  source of silent join failures.
- **The `ontology_audit()` contract in A1 reduces to counting**
  `knowledge_level = 'not_provided'`, `evidence_level = 'unknown'`,
  `publications = []`, and `study_id IS NULL` per edge type. Because each has a
  real value rather than a null-or-missing property, every one of those is a
  single `WHERE` clause — which is precisely what A1 asked for.
- **Nothing in this set is a score.** A derived confidence can be computed in a
  query from these components; it must not be stored as the evidence field
  (F10).

### (c) Three design decisions to copy

1. **Keep the source's own statistics and its verbatim relation on the edge;
   never harmonise them into one number.**
   *Motivating source:* SPOKE retains per-source p-values, BH-FDR, log2FC,
   binding affinity with a documented Kd > Ki > IC50 precedence, and human-review
   status on organism–disease edges. MicrobiomeKG keeps p-value, FDR status,
   sample size, effect strength and **statistical test type** per assertion.
   RTX-KG2 keeps `relation` / `relation_label` next to the normalised
   `predicate` — its authors quantify the loss it protects against (1,228 source
   relation types → 77 Biolink predicates, "semantic loss of precision").
   *Counter-example this avoids:* MicroPhenoDB's
   `(W_IDSA + W_NCIT + W_Literature) × log(N/n_j)`, and MicroMap's advertised
   "scores confidence on every connection" — neither can answer A1's actual
   question.

2. **Carry the causal/correlational distinction as a first-class, source-derived
   field, and encode it in Biolink's `knowledge_level` × `agent_type` pair.**
   *Motivating source:* gutMGene v2's `Evidence` column, which classifies each
   association as *causal* (controlled experiments manipulating the microbe or
   metabolite) or *correlational* (statistical correlation analysis), plus an
   `Evidence Number` publication count. Biolink then gives it a portable
   vocabulary: `knowledge_assertion` + `manual_agent` for the causal records,
   `statistical_association` + `data_analysis_pipeline` for differential-abundance
   output, `prediction` + `computational_model` for GMMAD's 220,690 predicted
   edges, `text_co_occurrence` + `text_mining_agent` for anything SemMedDB-like.
   *Counter-example this avoids:* MicrobiomeKG's dominant
   `biolink:associated_with`, MMiKG's undifferentiated merge of literature and
   inferred edges, and the review-literature finding that these databases mix
   causation, correlation, inverse causation and negation under one label.

3. **Make the study — not the edge — the unit of provenance, and model it on
   BugSigDB's export schema.**
   *Motivating source:* BugSigDB ships, per signature, study design, PMID/DOI,
   host species, body site + **UBERON ID**, condition + **EFO ID**, Group 0 and
   Group 1 names **and sample sizes**, statistical test, significance threshold,
   MHT correction, sequencing type, 16S variable region, sequencing platform,
   data transformation, and abundance direction in Group 1 — with taxa
   standardised to NCBI Taxonomy. Disbiome independently arrived at the same
   shape: an *experiment* row joining Publication / Organism / Sample / Disease /
   Host / Control / **Method** / Location ids, with a standardised reporting-quality
   questionnaire per study. That is A2, already normalised, in two independent
   resources.
   *Counter-example this avoids:* MetagenomicKG's edge-level
   `knowledge_source` string, which cannot answer "which cohort, what design,
   how many subjects".

### (d) Three design decisions to avoid

1. **Do not merge nodes on name equality, and do not ship only the merged
   graph.**
   *Motivating source:* kg-microbe #899 — deposit nodes minted from in-house
   designations asserted **false `close_match` equivalences**; #892 — 524 strain
   nodes (2,660 in an earlier build) carry two taxonomically incompatible
   NCBITaxon parents, because the multi-parent guard was per-transform and
   nothing checked the merge (#896); #638 — a BacDive strain assigned to the
   wrong species, contradicting a correct existing assignment. Translator's
   summary of the class: "false merges introduce factually incorrect edges that
   propagate throughout downstream queries and ML models."
   *Do instead:* RTX-KG2's two-artefact pattern — a pre-canonicalised graph
   where equivalent-but-differently-identified concepts remain distinct nodes,
   and a canonicalised one — so every merge is inspectable and reversible; and
   put the identity invariant **at the merge**, where sources actually meet.

2. **Do not let identifiers go unvalidated at ingest — not their prefix, not
   their shape, not their liveness, not their existence as nodes.**
   *Motivating source:* the kg-microbe tracker is a catalogue of this single
   failure. #918/#933 — KGX **invents** nodes for edge endpoints with no node
   row, so a dangling reference becomes a silent label-less node; #932 — LPSN
   references 4,233 CURIEs it never writes nodes for; #904 — ~13,845 edges point
   at prefixes the graph does not declare; #909 — 706,765 shipped edges use an
   obsoleted term with no declared replacement, while #927 notes the vendored
   deprecation set "can go stale … and nothing running in CI would notice";
   #919 — 93 NCBITaxon nodes carried a description *sentence* as their label;
   #402 — a taxon node with id `nan`. Add NCBI's own documented hole: a taxid can
   vanish without appearing in `merged.dmp` **or** `delnodes.dmp`.
   *Do instead:* a build gate (not a report) asserting that every edge endpoint
   has a node row and a declared prefix, that every id matches its prefix's
   pattern, that no shipped id is obsolete in the pinned ontology version, and
   that every taxid resolved through `merged.dmp` — with the pre-resolution id
   and verbatim name retained, and unresolvables counted rather than dropped
   (A4).

3. **Do not expand many-to-many relationships into edges, and do not store
   predicted edges in the same shape as observed ones.**
   *Motivating source:* GMMAD ships **220,690 predicted** disease–metabolite
   associations against 3,836 curated disease–microbe ones — 98% of that layer
   is inference by volume, stored alongside the curation. MicroPhenoDB's 696,934
   gene–microbe rows are 27,277 genes × 685 microbes, a cross-product rather
   than 696,934 observations. PrimeKG's pipeline adds reverse edges, then
   de-duplicates, then removes self-loops, because the expansion generates
   duplicates by construction. MicroMap's own public numbers — 1.1M taxa (≈ all
   of NCBI Taxonomy) against 63,316 microbe–disease associations, plus 276k AMR
   links — show a taxonomy ingested wholesale rather than restricted to taxa
   that participate in an assertion.
   *Do instead:* count edges **per source record** and publish the expansion
   factor in the audit output; materialise a taxon node only when it
   participates in an assertion or is on the ancestry path of one; and keep
   predicted edges behind `knowledge_level = 'prediction'` so excluding them is
   one `WHERE` clause. MetagenomicKG's decision to **exclude** RTX-KG2 edges
   supported only by SemMedDB is the right instinct applied the wrong way —
   record the evidence level and let the query filter, rather than deciding at
   build time and losing the record.

---

## Sources

Graphs and databases: [KG-Microbe repo](https://github.com/Knowledge-Graph-Hub/kg-microbe) ·
[KG-Microbe 2025 preprint](https://www.biorxiv.org/content/10.1101/2025.02.24.639989v1.full) ·
[KG-Microbe issue tracker](https://github.com/Knowledge-Graph-Hub/kg-microbe/issues) ·
[MicrobiomeKG (Frontiers Syst Biol 2025)](https://www.frontiersin.org/journals/systems-biology/articles/10.3389/fsysb.2025.1544432/full) ·
[MicrobiomeKG (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11507793/) ·
[MetagenomicKG](https://pmc.ncbi.nlm.nih.gov/articles/PMC10980061/) ·
[MicroPhenoDB](https://academic.oup.com/gpb/article/18/6/760/7229829) ·
[Disbiome](https://pmc.ncbi.nlm.nih.gov/articles/PMC5987391/) ·
[BugSigDB (Nat Biotechnol 2023)](https://www.nature.com/articles/s41587-023-01872-y) ·
[bugsigdbr vignette](https://bioconductor.org/packages/release/bioc/vignettes/bugsigdbr/inst/doc/bugsigdbr.html) ·
[BugSigDB Project:About](https://bugsigdb.org/Project:About) ·
[gutMGene v2.0 (NAR 2025)](https://academic.oup.com/nar/article/53/D1/D783/7850954) ·
[GMMAD](https://bmcgenomics.biomedcentral.com/articles/10.1186/s12864-023-09599-5) ·
[MMiKG](https://academic.oup.com/bib/article/24/6/bbad340/7287430) ·
[SPOKE (Bioinformatics 2023)](https://academic.oup.com/bioinformatics/article/39/2/btad080/7033465) ·
[SPOKE nodes and edges](https://spoke.rbvi.ucsf.edu/docs/index.html) ·
[PrimeKG (Sci Data 2023)](https://www.nature.com/articles/s41597-023-01960-3) ·
[Hetionet](https://github.com/hetio/hetionet) ·
[Hetionet (eLife 2017)](https://elifesciences.org/articles/26726) ·
[CKG docs](https://ckg.readthedocs.io/) ·
[BioKG](https://github.com/dsi-bdi/biokg) ·
[Graphomics / MicroMap](https://graphomics.com)

Schema and vocabulary: [Biolink knowledge-source retrieval](https://biolink.github.io/biolink-model/knowledge-source-retrieval/) ·
[KnowledgeLevelEnum](https://biolink.github.io/biolink-model/KnowledgeLevelEnum/) ·
[AgentTypeEnum](https://biolink.github.io/biolink-model/AgentTypeEnum/) ·
[biolink:p_value](https://biolink.github.io/biolink-model/p_value/) ·
[biolink:has_evidence](https://biolink.github.io/biolink-model/has_evidence/) ·
[Biolink qualifier examples](https://biolink.github.io/biolink-model/association-examples-with-qualifiers/) ·
[Biolink Model paper](https://ascpt.onlinelibrary.wiley.com/doi/10.1111/cts.13302) ·
[ECO (NAR 2022)](https://academic.oup.com/nar/article/50/D1/D1515/6431816) ·
[Mondo](https://mondo.monarchinitiative.org/) ·
[Mondo (Genetics 2026)](https://academic.oup.com/genetics/article/232/4/iyaf215/8276117)

Identifiers, licences and failure modes: [RTX-KG2](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9520835/) ·
[NCBI Taxonomy FAQ (merged/deleted taxids)](https://www.ncbi.nlm.nih.gov/books/NBK54428/) ·
[taxid-changelog](https://github.com/shenwei356/taxid-changelog) ·
[HMDB sources](https://hmdb.ca/sources) ·
[CARD 2023 (NAR)](https://academic.oup.com/nar/article/51/D1/D690/6764414) ·
[ARO repo](https://github.com/arpcard/aro) ·
[KEGG licence](https://www.kegg.jp/kegg/rest/) ·
[Challenges in constructing microbiome knowledge bases (Microbiome 2019)](https://microbiomejournal.biomedcentral.com/articles/10.1186/s40168-019-0742-2) ·
[Improving Biomedical KG Quality (arXiv 2508.21774)](https://arxiv.org/abs/2508.21774)

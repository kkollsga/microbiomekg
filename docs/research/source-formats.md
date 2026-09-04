# Source formats — what the next loaders actually consume

Profiled 2026-09-03 against the bytes in `data/raw/` (the fetch of 2026-09-02).
Everything below is measured, not read off a website: counts, fill rates and
pitfalls come from a full pass over each file. Nothing here was inferred from
documentation.

Scope: the seven sources **not yet loaded** — gutMDisorder, HMDB, CARD,
Reactome, KEGG, ChEMBL, MONDO. NCBI Taxonomy and BugSigDB are already in
increment 1 (`docs/model.md`) and appear here only as join targets.

Vocabulary for `evidence_level` / `knowledge_level` / `agent_type` is
`docs/research/existing-graphs-and-schemas.md` §5(b). `knowledge_level` and
`agent_type` use Biolink's enumerations verbatim; `evidence_level` is the
project-controlled ladder.

Intermediate outputs for loader authors live in the session scratchpad
(`.../scratchpad/profile/`): `hmdb_profile.json`, `hmdb_pass2.json`,
`hmdb_ontology_paths.txt` (every distinct ontology path with a metabolite
count), `hmdb_microbial_sample.csv` (200-row sample) and
`hmdb_microbial_all.csv` (all 224), `hmdb_chebi_ids.txt`, `hmdb_kegg_ids.txt`.

---

## Cross-source summary

| Source | Records the loader consumes | Taxon id? | Evidence fields | Redistributable |
|---|---:|---|---|---|
| gutMDisorder | 3,193 associations (2,263 human + 930 mouse) | **NCBI taxid**, 96.3 % / 97.0 % | PMID, DOID, research type, intervention, p-value, statistical method, direction, sequencing tech + platform, per-group sample size | licence unstated |
| HMDB | 217,920 metabolites | **none** — free-text organism names | metabolite `status`, 1.03 M PubMed-backed references, disease refs, biospecimen | non-commercial, no redistribution |
| CARD | 6,451 AMR models | **NCBI taxid**, 99.4 % | 6,254 PMID refs, SNP curation source (WHO-R / CRyPTIC-R / Curated-R) | data no; `aro.obo` CC BY 4.0 |
| Reactome | 23,603 pathways; 113,779 ChEBI→pathway; 269,113 gene→pathway | species **name** only, 16 model organisms | `TAS` vs `IEA` evidence code | CC0 |
| KEGG | 587 maps, 19,626 compounds, 19,647 links | **none** (organism list retired) | none | **no** |
| ChEMBL | 7,561 mechanisms, 4,225 approved molecules, 1,518 targets | target `tax_id`, 98.4 % | 13,600 typed refs (PubMed/DailyMed/FDA/…), `action_type`, `direct_interaction` | CC BY-SA 3.0 |
| MONDO | 36,015 MONDO terms | n/a (disease hub) | `source="MONDO:equivalentTo"` on xrefs | CC BY 4.0 |

**The one structural fact that shapes the whole increment:** only two of the
seven sources carry an NCBI taxid, and they are gutMDisorder and CARD. HMDB
names organisms in free text; Reactome and KEGG carry no bacterial taxa at all
(Reactome's 16 species are model organisms; KEGG's taxon route was retired
upstream). Any taxon–metabolite or taxon–pathway edge in this increment comes
from HMDB name matching or from nothing.

---

## 1. gutMDisorder

### Files and shape

`data/raw/gutmdisorder/human.xlsx` (1,643,490 B) and `mouse.xlsx` (728,405 B),
2020 v1 release recovered from Wayback. Three sheets each, `openpyxl` via
pandas:

| Workbook | Literature | Sample | Association |
|---|---:|---:|---:|
| human | 325 × 14 | 724 × 14 | 2,263 × 9 |
| mouse | 190 × 14 | 563 × 11 | 930 × 9 |

### How the three sheets join

**One key, three spellings.** `Literature.Index` (int) ← `Sample.Index` ←
`Association.index` (note the lowercase `i` on Association, in both workbooks).
`Index` is the *study/experiment* key: one Literature row per index, 1–8 Sample
rows per index, 1–N Association rows per index.

`Sample Number` is a **within-index ordinal** (1–8), not a join key: it numbers
the arms of one study (case group, control group, …). `Experiment ID` is an SRA
/ BioProject accession (`SRP103884`, `PRJNA411831`), sometimes a bare integer,
comma-multivalued, 33 % / 15 % filled — a cross-reference, never a key.

**Consequence for the evidence model, and it is the important one:** an
Association row has **no reference to a Sample row**. Group sizes cannot be
attached per association the way BugSigDB's `Group 0/1 sample size` can. The
honest load is: `Sample` rows become an arm-list hanging off the `Study`
node, and the association edge carries the *study's* sample sizes as a
list/sum, flagged as study-level rather than per-arm. Do not silently pick
`Sample Number == 1`.

### Column inventory and fill

**Literature** (evidence + disease endpoint): `Index` 100 %, `PMID` 100 %
(numeric, no malformed values; 18 human / 16 mouse PMIDs appear on more than
one index — the same paper curated as several experiments), `Journal` 100 %,
`Title` 100 %, `Authors` 100 % / 99.5 %, **`Research Type`** 100 %,
`Intervention` 26.8 % / 88.4 %, `Intervention Type` 26.8 % / 88.4 %,
`Intervention ID` 5.5 % / 12.1 % (**DrugBank** ids, `DB00065`,
comma-multivalued), `Disorder Name` 80.3 % / 34.2 %, **`DOID`** 65.5 % / 26.8 %,
`Conclusion` 100 % (free text), `Experiment ID` 32.9 % / 14.7 %.

`Research Type` has exactly three values: `Gut microbiota associated with
disorder` (238 human / 22 mouse), `Interventions change the composition of gut
microbiota` (86 / 168), `Gut microbiota for adjuvant therapy` (1 / 0). This is
the observational-vs-interventional discriminator and it is 100 % filled.
`Intervention Type` ∈ {`Drug`, `Food`, `Others`}.

**Sample** (cohort description): `Sample Size` 99.2 % / 95.6 %, `Sample Source`
99.4 % / 100 % (`stool` 646/496, then biopsies, caecal content, saliva),
`Sex (male, female)` 75.3 % / 83.8 % — **a single cell holding two numbers
comma-separated** (`"5,8"` = 5 male, 8 female), `Age` 85.8 % / 83.1 % (free
text: `52.25 years old`, `6 weeks old`), `BMI` 33.3 % (human only),
`Nation/Race` 99 %, `Condition` 95.3 % / 100 % (free text, 411/446 distinct —
`healthy`, `Healthy controls`, `Healthy Controls`, `healthy persons` all
separate strings), **`Sequencing Technology`** 99.6 % / 100 %,
`Sequencing Platform` 60.8 % / 91.5 %.

`Sequencing Technology` values, comma-multivalued: `16S rRNA sequences` (552 /
480), `16S rRNA sequences,qPCR`, `16S rDNA sequences`, `qPCR`, `RT-qPCR`,
`denaturing gradient gel electrophoresis`, `quantitative metagenomics by
shotgun sequencing` (7 human rows, and 2 more with the atoms in the other
order), `PCR`. The human sheet also carries two junk columns, `Unnamed: 12`
(empty) and `Unnamed: 13` (four rows of `"  "`).

**Association** (the edge): `index` 100 %, `Gut Microbiota` 100 % (name),
`Gut Microbiata ID` 100 % (gutMDisorder's own `gm0587` key — note the
misspelling "Microbiata", present in both column names),
**`Gut Microbiata NCBI ID`** 96.3 % / 97.0 %, `Classification` 100 % (rank),
`P Value` 70.2 % / 65.9 % (float), `Statistical Method` 99.1 % / 100 % (98 / 56
free-text values), `Description` 100 % (the sentence from the paper),
`Alteration` 100 % — exactly two values, `increase` / `decrease`.

### Taxon identification

`Gut Microbiata NCBI ID` is a bare integer NCBI taxid (read as float64 by
pandas because of the nulls). `Classification` gives the rank as a string:
genus 1097/347, family 446/227, species 320/117, phylum 235/194, class 86/14,
order 66/22, `no rank` 13/9.

Checked against `merged.dmp` / `delnodes.dmp` / `nodes.dmp`:

| | distinct taxids | live | merged | deleted | unknown |
|---|---:|---:|---:|---:|---:|
| human | 524 | 511 | **11** | **2** | 0 |
| mouse | 254 | 249 | **5** | 0 | 0 |

Merged examples: 1532→33035, 209879→**39948** (`Dialister`, which appears in
row 1 of the human sheet under the *old* id), 541000→216572, 424536→990719.
Deleted: 186813, 990724 — these have no replacement and must land as
`UnresolvedTaxon`, not be dropped.

`Classification` disagrees with the NCBI rank of the id it names on **63 human
and 27 mouse** rows (e.g. labelled `genus`, id is a species: 24 human rows;
labelled `order`, id is a family: 16). Trust `nodes.dmp`, keep
`Classification` verbatim as `reported_rank`.

### Evidence / provenance fields available verbatim

`PMID`, `DOID`, `Research Type`, `Intervention`, `Intervention Type`,
`Intervention ID` (DrugBank), `Alteration`, `P Value`, `Statistical Method`,
`Sequencing Technology`, `Sequencing Platform`, `Sample Size`, `Sample Source`,
`Condition`, `Nation/Race`, `Age`, `Sex`, `BMI`, `Conclusion`, `Description`,
`Experiment ID`. No FDR/adjusted p-value, no effect size, no confidence score.

### Pitfalls

1. **The mouse workbook's `Index` columns are floats with binary noise, and
   `int()` silently mis-joins.** `Sample.Index` and `Association.index` in
   `mouse.xlsx` hold values like `63.0000000000001` and `33.9999999999999`
   while `Literature.Index` is a clean int64. An equality join drops **45 of
   930** association rows and **47 of 563** sample rows; `astype(int)` recovers
   all but one and maps `33.9999999999999` → **33**, attaching that
   association to the *wrong paper*. Use `round().astype(int)`. `human.xlsx` is
   clean, so a loader tested only on human will not see this.
2. **The join key is spelled `index` on Association and `Index` elsewhere**, in
   both workbooks. A shared helper that hard-codes one casing loads one sheet.
3. **Duplicate and self-contradicting association rows.** Human: 22 fully
   identical rows, 76 duplicate `(index, gmID, Alteration)` triples, and 15
   `(index, taxon)` pairs carrying **both** `increase` and `decrease`. Mouse:
   1 / 6 / 5. These are real curation duplicates, not parallel observations
   from different arms — there is no arm key to distinguish them by. Deduplicate
   on the full row; keep genuine direction conflicts as parallel edges and let
   them be countable.
4. **`Gut Microbiata ID` is not 1:1 with the taxid**: 4 human / 2 mouse taxids
   are reached from two different `gm` ids (the same organism curated twice
   under two names). `gm` → taxid is a function; taxid → `gm` is not.
5. `DOID` is comma-multivalued in exactly one human cell
   (`DOID:8878,DOID:8577`), matching a `Disorder Name` of
   `"Crohn's disease,ulcerative colitis"`. Split on comma; that also makes
   `DOID:8878` the only unmapped-to-MONDO DOID worth investigating (see §7).
6. **Disease coverage is much thinner than the row counts suggest**: only
   1,477 of 2,263 human and **220 of 930** mouse association rows belong to a
   literature row that has a DOID at all (mouse is an intervention corpus —
   `Interventions change the composition of gut microbiota` is 168 of 190
   studies). Most mouse edges are Taxon–Intervention, not Taxon–Disease.
7. `Sex (male, female)` is two integers in one cell; `Age` and `Condition` are
   free text with no controlled vocabulary. No literal `NA`/`N/A`/`-` spellings
   exist — missing is genuinely empty (4 whitespace-only cells in the human
   `Unnamed: 13` column are the only exception).
8. `Experiment ID` mixes SRA accessions, BioProject accessions, comma-joined
   pairs and bare integers (`11169`, `698323440`).

### Extraction table

| Source field | Graph target |
|---|---|
| `Literature.PMID` | `Paper` pk `pmid`; edge `publications = ["PMID:<n>"]` |
| `Literature.DOID` (split `,`) | `Disease`; canonical key MONDO via §7, `doid_id` property, `source_disease_name` = `Disorder Name` |
| `Literature.Index` | `Study` pk `STUDY:gutmdisorder-<human\|mouse>-<index>` |
| `Literature.Research Type` | `Study.research_type`; drives `evidence_level` |
| `Literature.Intervention` / `Intervention Type` / `Intervention ID` | `Drug` node when `Intervention Type = Drug` and a DrugBank id exists (`drugbank_id` property); else `Study.intervention` verbatim |
| `Literature.Conclusion`, `Journal`, `Title`, `Authors` | `Study` properties / `Paper` properties |
| `Sample.*` | `StudyArm` sub-node under `Study` (`sample_number`, `sample_size`, `sample_source`, `condition`, `age`, `sex_male`, `sex_female`, `bmi`, `nation_race`, `sequencing_technology`, `sequencing_platform`) |
| `Association.Gut Microbiata NCBI ID` | `Taxon` via `reconcile.py` (`merged.dmp` chase, rank ceiling) |
| `Association.Gut Microbiota` / `Classification` / `Gut Microbiata ID` | edge `reported_name`, `reported_rank`, `source_record_id` |
| `Association.Alteration` | edge `direction` (`increase`→`increased`, `decrease`→`decreased`) |
| `Association.P Value` | edge `p_value` |
| `Association.Statistical Method` | edge `statistical_test` |
| `Association.Description` | edge `source_relation` (verbatim sentence) |
| host | edge `host_species` = `NCBITaxon:9606` / `NCBITaxon:10090` from the workbook |

Edges: `(Taxon)-[:ASSOCIATED_WITH]->(Disease)` where a DOID exists;
`(Taxon)-[:ABUNDANCE_CHANGED_BY]->(Drug|Intervention)` for the intervention
studies. Both carry the same contract.

### Evidence vocabulary this source justifies

- `primary_source = "gutmdisorder"`, `source_licence = "unstated"`.
- `knowledge_level = "statistical_association"` for every row — each is a
  differential-abundance result with a p-value and a named test.
- `agent_type = "manual_agent"` — human curators reading papers.
- `evidence_level`: `in_vivo_model` for the whole mouse workbook regardless of
  design (model.md rule 2 already says a mouse RCT is not human evidence);
  for the human workbook, `interventional_clinical` when
  `Research Type` names an intervention, else `observational_16s` /
  `observational_shotgun` split on `Sequencing Technology`
  (`quantitative metagenomics by shotgun sequencing` → shotgun; `qPCR`/`PCR`/
  `RT-qPCR`/`DGGE` alone → `observational_targeted`), else
  `observational_unspecified`.

---

## 2. HMDB 5.0

### File and shape

`data/raw/hmdb/hmdb_metabolites.xml`, 6,486,862,079 B, single XML document,
namespace `http://www.hmdb.ca`, root `<hmdb>`, one `<metabolite>` per record.
**217,920 metabolites.** Streamed with `iterparse` + `el.clear()` +
`root.clear()`; a full pass costs ~2.5 minutes and bounded memory. Never
`ET.parse` it.

### Identifier fill rates (n = 217,920)

| Field | Filled | % | Distinct |
|---|---:|---:|---:|
| `accession` | 217,920 | 100.00 | 217,920 (no duplicates) |
| `name` | 217,920 | 100.00 | — |
| `inchikey` | 217,899 | 99.99 | — |
| `chemical_formula` | 217,899 | 99.99 | — |
| `pubchem_compound_id` | 104,230 | **47.83** | 103,682 |
| `foodb_id` | 74,427 | 34.15 | 73,846 |
| `chemspider_id` | 31,269 | 14.35 | — |
| `cas_registry_number` | 15,672 | 7.19 | — |
| **`chebi_id`** | 13,701 | **6.29** | 13,562 |
| `knapsack_id` | 7,994 | 3.67 | — |
| **`kegg_id`** | 6,814 | **3.13** | 5,900 |
| `drugbank_id` | 3,258 | 1.50 | 3,241 |
| `biocyc_id` | 2,652 | 1.22 | — |
| `vmh_id` | 1,561 | 0.72 | — |
| `metlin_id` | 1,581 | 0.73 | — |
| `bigg_id` | 696 | 0.32 | — |

`secondary_accessions` adds 80,986 retired HMDB ids across the file — these are
the redirect table and must be loaded, or a citation of `HMDB00001` will not
find `HMDB0000001`.

**`status`** — the single most load-bearing field HMDB has, 100 % filled:
`expected` 98,256 (45.1 %), `predicted` 95,355 (43.8 %), `detected` 20,924
(9.6 %), `quantified` 3,385 (1.6 %). **Only 24,309 records (11.2 %) have ever
been observed in a human sample.** Everything else is a prediction or an
expectation, and that is what `knowledge_level` must carry.

### How microbial origin is encoded

The `<ontology>` block is a forest of four `<root>` terms — `Disposition`
(572 distinct terms), `Process` (666), `Physiological effect` (528), `Role`
(242) — each a recursive `<descendants>/<descendant>` tree of
`{term, definition, parent_id, level, type, synonyms, descendants}`. There are
no ids on the terms, only names and an internal `parent_id`.

Origin lives at **`Disposition → Source`**, whose six children are:

| Term | Metabolites |
|---|---:|
| `Food` | 146,742 |
| `Endogenous` | 145,377 |
| `Biological` | 144,377 |
| `Synthetic` | 193 |
| `Environmental` | 162 |
| `Exogenous` | 6 |

There is **no `Microbial` term and no `Drug` term under `Source`**. Microbial
origin is one level deeper, at `Disposition/Source/Biological/**Microbe**`:

- **224 metabolites** carry `Disposition/Source/Biological/Microbe`. That is
  0.10 % of the file. (`Biological/Fungi` adds 55 more, and
  `Biological/Saccharomyces cerevisiae` sits directly under `Biological`, not
  under `Microbe` — three sibling encodings of the same idea.)
- Of those 224: `quantified` 158, `detected` 28, `expected` 38 — i.e. the
  microbial branch is the *best*-curated slice of HMDB, the inverse of the file
  as a whole. 207 have a ChEBI id, 176 have a KEGG id, and **152 have `Feces`
  in `biospecimen_locations`**.
- Organisms are named as **free text at two further levels**: 169 distinct
  genus-level terms and 218 distinct species-level terms under them
  (`Microbe/Escherichia/Escherichia coli` — 61 and 60 metabolites
  respectively). **No taxid anywhere.**
- The "genus" level is not a rank. It contains genera (`Bacteroides`,
  `Akkermansia`, `Prevotella`), phyla (`Firmicutes`, `Proteobacteria`,
  `Bacteroidetes`, `Cyanobacteria`), a class (`Gammaproteobacteria`), families
  (`Lachnospiraceae`, `Ruminococcaceae`, `Christensenellaceae`,
  `Rhodobacteraceae`, `Actinomycetaceae`, `Rhizobiaceae`), an order
  (`Actinomycetales`), Gram stains (`Gram-negative bacteria`,
  `Gram-positive bacteria`), a community (`Human gut microbiota`, 2
  metabolites), a plural (`Bifidobacteria`), and a **U+FB01 ligature typo**
  (`Biﬁdobacterium`, distinct from `Bifidobacterium`).
- Species-level terms carry misspellings that will not match `names.dmp`:
  `Citrobacter frundii`, `Clostridium botulinium`, `Akkermansia muciniphilia`,
  `Citrobacter intermediuns`, `Clostridia propionicum`, `Bacillus Coagulans`
  (capitalised epithet), `Bifidobacterium Bifidum`, `Bacteroides spp.`,
  `Algibacter sp. AQP096`, `Streptococcus group B`.

`Disposition → Biological location` is a *human anatomy* tree (Subcellular
149,675 / Biofluid and excreta 136,762 / Tissue and substructures 97,722 /
Organ and components 87,007), **not** an organism tree. `Biofluid and
excreta/Feces` appears on 1,135 metabolites there. `Disposition → Route of
exposure` is Enteral (144,704, essentially all `Ingestion`) vs Parenteral (396).

**Verdict for the loader: HMDB gives a taxon–metabolite edge for 224
metabolites, keyed on an uncontrolled organism string.** That is the whole
microbial yield. It must go through `reconcile.py` by *name*, with the ligature
and misspelling cases expected to land in `UnresolvedTaxon`.

### Diseases, pathways, biospecimens

`<diseases>/<disease>` — **22,600 metabolites** carry ≥1 disease; 27,670
disease rows; **657 distinct disease names**; `omim_id` on 24,755 rows
(89.5 %); 149,037 `<reference>` rows of which **124,943 (83.8 %) carry a
`pubmed_id`**. 391 distinct OMIM ids.

`biological_properties/pathways/pathway` — 54,282 metabolites (24.9 %) carry
≥1 pathway; **815,803 pathway rows**; `name` 100 %, `smpdb_id` 814,686
(99.86 %), **`kegg_map_id` 2,131 (0.26 %)**. 49,604 distinct SMPDB ids but only
**54 distinct KEGG map ids**. The SMPDB set is dominated by auto-generated
per-disease and per-drug "action pathways" (`Azathioprine Action Pathway`,
`Adenosine Deaminase Deficiency`) — 49,628 distinct names for 217,920
metabolites is not a pathway vocabulary, it is a per-compound artefact.

`biological_properties/biospecimen_locations/biospecimen` — a closed
18-value list: Blood 40,678, **Feces 6,791**, Urine 4,692, Saliva 1,239,
CSF 445, Breast Milk 121, Sweat 91, Breath 60, Cellular Cytoplasm 49,
Amniotic Fluid 18, Bile 18, Prostate Tissue 12, Semen 4, then singletons
(Pericardial Effusion, Aqueous Humour, Ascites Fluid, Lymph, Tears).
**Feces is present and is the second-largest class.**

Also available and worth knowing about: `protein_associations` (22,862
metabolites, 863,759 rows, **100 % carry a `uniprot_id`**) — a
Metabolite→Protein edge set that joins straight to ChEMBL's target accessions;
`general_references` (1,197,555 rows, 1,031,122 with a `pubmed_id`);
`normal_concentrations` (51,243 rows) and `abnormal_concentrations` (40,635),
both with `biospecimen`, `subject_condition`, `subject_age`, `subject_sex` and
their own references — 6,534 normal + 8,810 abnormal rows are **Feces**
measurements, which is a quantitative gut-metabolite layer this project has not
budgeted for.

### Pitfalls

1. **`3-methylglutaconic aciduria type II, X-linked` is attached to 20,020 of
   the 27,670 disease rows — 72 % of HMDB's entire disease layer.** The next
   name down is `Colorectal cancer` at 831. This is a curation accident, not
   biology; loading `diseases` naively produces one disease node with 20,020
   metabolite edges that will dominate every path query in the graph. Cap or
   drop it explicitly and say so in the audit.
2. **Microbial origin is 224 records, not thousands.** Any plan sized on
   "HMDB has microbial metabolites" needs this number in front of it before
   the loader is written. A `grep`-style match on `microb|bacter|fung` across
   the whole ontology returns 519 metabolites, but 233 of those are
   `Role/Industrial application/Household products/Antimicrobial agent` —
   *drugs that kill microbes*, the exact opposite of microbial origin. Match on
   the path prefix `/Disposition/Source/Biological/Microbe`, never on a term
   substring.
3. **ChEBI and KEGG ids are present on 6.3 % and 3.1 % of records.** HMDB is
   described in the schema survey as "the bridge file"; it bridges for 13,562
   ChEBI ids and 5,900 KEGG ids, and for nothing else. `inchikey` (99.99 %) is
   the only near-universal join HMDB offers.
4. Ids are clean apart from a single lowercase `kegg_id` of `c0338`
   (should be `C0338`), and 27 of the 5,900 KEGG ids no longer exist in KEGG's
   current compound list (§5).
5. `<parent_id>` inside the ontology is an internal HMDB cvterm number that is
   **not** unique to the metabolite and does not appear anywhere else in the
   file — it is useless as a term key. Terms have to be keyed by their path.
6. The four ontology roots overlap semantically: `Role/Biological role/Drug
   metabolite` (948) and `Role/Industrial application/Drug` (1,489) are how
   "this is a drug" is encoded, not `Disposition/Source`.
7. Empty elements are present as `<definition/>`, `<parent_id/>` — `.text` is
   `None`, not `''`. And the XML is namespaced: every `find()` needs
   `{http://www.hmdb.ca}`.

### Extraction table

| Source field | Graph target |
|---|---|
| `accession` | `Metabolite` pk `HMDB:<accession>` (canonical key is ChEBI where present per §5(a), HMDB otherwise) |
| `name`, `chemical_formula`, `average_molecular_weight`, `state` | `Metabolite` properties |
| `inchikey`, `chebi_id`, `kegg_id`, `pubchem_compound_id`, `drugbank_id`, `foodb_id`, `cas_registry_number` | `Metabolite` cross-ref properties (`chebi_id` prefixed `CHEBI:` on write — HMDB stores it bare) |
| `secondary_accessions/accession` | `Metabolite.secondary_accessions` (list) — the redirect table |
| `status` | `Metabolite.hmdb_status`; drives `knowledge_level` on every HMDB edge |
| `ontology` path `/Disposition/Source/Biological/Microbe/<genus>[/<species>]` | `(Taxon\|UnresolvedTaxon)-[:PRODUCES]->(Metabolite)`, edge `reported_name` = the term verbatim, `source_relation = "Disposition/Source/Biological/Microbe"` |
| `ontology` path `/Disposition/Source/{Food,Endogenous,Synthetic,Environmental,Exogenous}` | `Metabolite.origin` (list) |
| `biological_properties/biospecimen_locations/biospecimen` | `(Metabolite)-[:FOUND_IN]->(BodySite)`; `Feces` → `UBERON:0001988` |
| `diseases/disease/{name,omim_id}` + `references/reference/pubmed_id` | `(Metabolite)-[:ASSOCIATED_WITH]->(Disease)`, `Disease.omim_id`, edge `publications` |
| `biological_properties/pathways/pathway/{name,smpdb_id,kegg_map_id}` | `(Metabolite)-[:PARTICIPATES_IN]->(Pathway)`; `Pathway` pk `SMP:<id>` / `KEGG:<map>` |
| `protein_associations/protein/uniprot_id` | `(Metabolite)-[:INTERACTS_WITH]->(ProteinTarget)` keyed `UniProtKB:<acc>` |
| `general_references/reference/pubmed_id` | `Paper` nodes; `(Metabolite)-[:CITED_BY]->(Paper)` |

### Evidence vocabulary

- `primary_source = "hmdb"`, `source_licence = "hmdb-noncommercial"` — and see
  `docs/sources.md`: HMDB content should be behind the same build flag as KEGG
  if the graph is ever to leave this machine.
- `agent_type = "manual_agent"` for `status ∈ {detected, quantified}` and for
  every `diseases` row (they carry curated PubMed refs);
  `computational_model` for `status ∈ {predicted, expected}`.
- `knowledge_level`: `knowledge_assertion` where `status` is `quantified` or
  `detected`; **`prediction`** where it is `predicted` or `expected`. 88.8 % of
  HMDB falls in the second bucket and the audit should say so out loud.
- `evidence_level`: `in_vitro` for the microbial-origin edges whose metabolite
  is `quantified`/`detected` (158 of 224), `computational_predicted` otherwise.
  Disease edges: `observational_shotgun` is wrong — HMDB disease associations
  are metabolomic, so they take `unknown` unless a per-reference read is added
  later. `unknown` is countable; do not default them to observational.

---

## 3. CARD

### Files

`data/raw/card/card-data/` (© McMaster, **not redistributable**) and
`data/raw/card/card-ontology/` (**CC BY 4.0**). Two licences in one download —
see `docs/sources.md`. `card.json` reports `_version: 4.0.2`,
`_timestamp: 2026-08-11T13:01:48+00:00`.

| File | Rows | Role |
|---|---:|---|
| `card.json` | 6,451 models | the model store; **the only file with taxids** |
| `aro_index.tsv` | 6,463 × 12 | ARO ↔ model ↔ gene ↔ categories, flat |
| `aro_categories.tsv` | 685 × 3 | the 685 category terms themselves |
| `aro_categories_index.tsv` | 6,411 × 5 | accession → categories (no ARO column) |
| `PMID.tsv` | 4,408 × 6 | citations per ARO term |
| `snps.txt` | 3,735 × 8 | resistance mutations, with a curation-source column |
| `card-ontology/aro.obo` | 9,051 terms | the ARO graph, CC BY 4.0 |
| `card-ontology/ncbi_taxonomy.obo` | 1,899 terms | CARD's taxonomy slice |

### How a model links

**ARO accession.** `card.json` stores it **bare** (`"ARO_accession": "3002999"`);
`aro_index.tsv`, `aro_categories.tsv` and `PMID.tsv` store it **prefixed**
(`ARO:3002999`); `aro.obo` uses the prefixed form as the term id. Normalise on
read. 6,451 distinct accessions in `card.json`, 6,458 in `aro_index.tsv`.

**Gene name.** `ARO_name` / `Model Name` / `CARD Short Name`. `Model Name` and
`ARO Name` differ in case for a handful of rows
(`Escherichia coli UhpA…` vs `…uhpA…`).

**Source organism taxid** — this is the field the task asks about and it is
**not in any TSV**. It lives at

```
card.json → <model_id> → model_sequences.sequence.<seq_id>.NCBI_taxonomy
          → { NCBI_taxonomy_id, NCBI_taxonomy_name, NCBI_taxonomy_cvterm_id }
```

Coverage: 6,415 of 6,451 models (**99.44 %**) have exactly one sequence, and
every one of those sequences carries an `NCBI_taxonomy_id`. 36 models
(`efflux pump system meta-model`, `gene cluster meta-model`) have no
`model_sequences` at all and therefore no taxon. **No model has more than one
distinct taxon** — the field is single-valued in practice.

**743 distinct taxids**, all resolvable: 726 live, **17 merged**, 0 deleted,
0 unknown. Merged examples 68570→1971, 1144672→70347, 1214076→2203204.
Ranks: species 466, **strain 185**, `no rank` 35, genus 18, subspecies 14 —
so the `rank_ceiling = species` promotion in `reconcile.py` will fire on
roughly a quarter of them. Top taxids are clinical pathogens:
287 *P. aeruginosa* (1,081 models), 470 *A. baumannii* (737), 573
*K. pneumoniae* (704), 562 *E. coli* (562), 550 *E. cloacae* (170), and
**2 = Bacteria itself on 132 models**.

**Drug classes and resistance mechanisms** are ARO categories, available two
ways: `card.json → ARO_category → <cvterm> → {category_aro_accession,
category_aro_name, category_aro_class_name}` where `class_name` ∈
{`Drug Class` (13,691 assignments, 50 distinct), `AMR Gene Family` (6,657,
529 distinct), `Resistance Mechanism` (6,513, 8 distinct)}; or the
`;`-joined strings in `aro_index.tsv`. The eight mechanisms are:
antibiotic inactivation 5,246, antibiotic target alteration 626, antibiotic
efflux 344, antibiotic target protection 172, antibiotic target replacement 81,
reduced permeability to antibiotic 30, resistance by absence 13, resistance by
host-dependent nutrient acquisition 1.

**Publications.** `PMID.tsv`: 4,408 ARO terms, `PMID` filled on 4,386 (99.5 %),
`;`-multivalued on 961 rows, 6,254 total references, **3,543 distinct PMIDs**.
`DOI` on 7 rows, `ISBN` on 39. Only **2,747 of the 4,408** ARO accessions in
`PMID.tsv` appear in `aro_index.tsv` — the rest cite drug-class and gene-family
terms, not models. `aro.obo` carries a second, larger citation set: **3,459
distinct PMIDs** inside `def:` dbxref brackets.

`snps.txt` carries a genuine evidence gradient in its `source` column:
`Curated-R` 1,701, `WHO-R` 996, `CRyPTIC-R` 921, `ReSeqTB-High` 79,
`ReSeqTB-Moderate` 3, `ReSeqTB-Minimal` 35 — plus a `citation` PMID per row.

`aro.obo`: 9,051 terms, **0 obsolete**, 31 typedefs. Edge-bearing relationships:
`confers_resistance_to_antibiotic` 4,558, `confers_resistance_to_drug_class`
865, `derives_from` 337, `targeted_by_antibiotic` 252, `part_of` 240,
`is_small_molecule_inhibitor_of` 215, `regulates` 86, plus efflux-component
relations. Xrefs out of ARO: PubChem 703, **CHEBI 529**, **ChEMBL 523**,
CAS 393, PDB 47 — that is the join from an antibiotic ARO term to the
`Metabolite`/`Drug` node set.

### Pitfalls

1. **`aro_index.tsv` and `card.json` disagree about which models exist**, in
   the same tarball: 48 model ids are in the index and absent from
   `card.json` (e.g. 2067 `CMY-131`), and 36 are in `card.json` and absent from
   the index (2176–2186, 2551, 2704…). Pick `card.json` as the model authority
   — it is the file with the taxids — and treat index-only rows as a
   reportable inconsistency, not as extra models.
2. **`ARO Accession` is duplicated on 5 rows of `aro_index.tsv`** — the same
   ARO term with two model ids (`ARO:3000506` mexR/MexR; `ARO:3002118`
   CMY-106; `ARO:3003170` CMY-131; `ARO:3003893`; `ARO:3003900`). Keying nodes
   on ARO accession from this file silently drops half of each pair. Key models
   on `Model ID` (unique, 6,463) and the term on ARO.
3. **`card-ontology/ncbi_taxonomy.obo` renames NCBI terms.** `NCBITaxon:2` is
   named `"Bacteria, Viruses, Fungi, and other genome sequence associated with
   antimicrobial resistance"` — CARD's editorial label, not the NCBI scientific
   name. Never use this file as a source of taxon labels; use it only, if at
   all, as the list of taxids CARD cares about (1,899 terms, against the 743
   actually used by models).
4. **The taxon on a model is the taxon of the *reference sequence*, not the
   organism the gene is claimed for.** Model 2 (`CblA-1`) has
   `ARO_description` "found in *Bacteroides uniformis*" and
   `NCBI_taxonomy_name` `"mixed culture bacterium AX_gF3SD01_15"`
   (taxid 663108). 132 models are keyed on taxid 2 (Bacteria) alone. A
   `(Taxon)-[:CARRIES]->(AROTerm)` edge built from this field asserts "this
   sequence was cloned from this organism", which is a weaker claim than
   "this organism is resistant" — say which one the edge means.
5. `Drug Class` in `aro_index.tsv` is `;`-multivalued on **4,096 of 6,463
   rows** (53 distinct atoms); `AMR Gene Family` on 184 rows; `Resistance
   Mechanism` on 58. `nuniq` on the raw column reports 150 "drug classes" that
   are really 53 atoms in combination.
6. `PMID.tsv` splitting yields **21 empty atoms** (trailing/leading `;`), and
   the `DOI`/`ISBN` columns contain values that themselves begin with a
   semicolon (`;10.1007/BF03298293`, `;978-92-4-008241-0`). Strip after split.
7. Two PubMed references in the whole CARD/ChEMBL set are a URL rather than
   an id (both ChEMBL's; see §6 pitfall 4) — the same class of defect appears
   here as `PMID` cells that are empty strings after split.

### Extraction table

| Source field | Graph target |
|---|---|
| `card.json` key / `model_id` | `AMRModel` pk `CARD:<model_id>`, `model_type`, `model_name` |
| `ARO_accession` (prefix to `ARO:`) | `AROTerm` pk; `name` = `ARO_name`, `description` = `ARO_description`, `card_short_name` |
| `model_sequences.sequence.*.NCBI_taxonomy.NCBI_taxonomy_id` | `(Taxon)-[:CARRIES_DETERMINANT]->(AROTerm)`, edge `reported_name` = `NCBI_taxonomy_name`, `sequence_derived = true` |
| `model_sequences.sequence.*.protein_sequence.accession` / `dna_sequence.accession` | `AMRModel.protein_accession` / `.dna_accession` (GenBank) |
| `ARO_category` where `class_name = "Drug Class"` | `(AROTerm)-[:CONFERS_RESISTANCE_TO]->(DrugClass)` pk `ARO:<category_accession>` |
| `ARO_category` where `class_name = "Resistance Mechanism"` | `AROTerm.resistance_mechanism` (8 values) |
| `ARO_category` where `class_name = "AMR Gene Family"` | `(AROTerm)-[:IN_GENE_FAMILY]->(AROTerm)` |
| `aro.obo` `is_a` / `confers_resistance_to_*` / `part_of` | `AROTerm` hierarchy + resistance edges (**this is the CC BY 4.0 half — prefer it**) |
| `aro.obo` `xref: CHEBI:*` / `ChEMBL:*` | `(AROTerm)-[:SAME_AS]->(Metabolite\|Drug)` — the join to §2 and §6 |
| `PMID.tsv` `PMID` (split `;`) | `Paper`; edge `publications` |
| `snps.txt` `Mutations`, `source`, `citation` | `AMRModel.mutations` + edge `evidence_source` |

### Evidence vocabulary

- `primary_source = "card"`; `source_licence = "CC-BY-4.0"` for anything taken
  from `card-ontology/`, `"card-data-noncommercial"` for anything from
  `card-data/`. Keep them distinct per edge — that is exactly the case
  Hetionet's per-edge licence field exists for.
- `agent_type = "manual_agent"` (CARD is expert-curated); the `snps.txt` rows
  sourced `CRyPTIC-R` are `data_analysis_pipeline`.
- `knowledge_level = "knowledge_assertion"` for a model with a PMID;
  `not_provided` for the 1,661 model-bearing ARO terms with no `PMID.tsv` row.
- `evidence_level = "in_vitro"` for a curated resistance model (they rest on
  MIC/phenotype experiments), `computational_predicted` for the 36 meta-models
  with no reference sequence.

---

## 4. Reactome

Five headerless TSVs, CC0. `ReactomePathways.txt` 23,603 rows
(`id`, `name`, `species`); `ReactomePathwaysRelation.txt` 23,717 rows
(`parent`, `child`); `ChEBI2Reactome.txt` 113,779 and
`ChEBI2Reactome_All_Levels.txt` 307,049 rows; `NCBI2Reactome.txt` 269,113 rows.
The three mapping files share one 6-column layout:
`source_id · pathway_id · url · pathway_name · evidence_code · species`.

**Pathways.** 23,603 ids, no duplicates, all matching `R-[A-Z]{3}-\d+`. The
three-letter infix is the species: HSA 2,883, MMU 1,845, GGA 1,841, RNO 1,833,
BTA 1,822, SSC 1,805, CFA 1,784, DRE 1,696, XTR 1,621, DME 1,591, CEL 1,409,
DDI 1,085, plus SCE, SPO, MTU, PFA. **16 species, and they are model
organisms — there is not a single gut commensal.** The bacterial content is
*Mycobacterium tuberculosis* and *Plasmodium falciparum*, i.e. pathogens
Reactome models for infection pathways. 204 pathway names carry a trailing
space.

**Hierarchy.** 8,450 parents, 23,188 children, 415 roots. Every id on both
sides is present in `ReactomePathways.txt`. **388 children have more than one
parent** — it is a DAG, not a tree; a loader assuming one parent loses edges.
No parent/child pair crosses species.

**ChEBI → pathway.** 3,260 distinct ChEBI ids (bare integers, no `CHEBI:`
prefix — prefix on write) over 14,935 pathways (20,473 in the All_Levels file,
which adds every ancestor pathway and triples the row count for the same 3,260
compounds). Species distribution follows the pathway set: Homo sapiens 15,732
rows, then the other 15 organisms at 6–10 k each. No duplicate rows.

**Overlap with HMDB's ChEBI set:** HMDB has 13,562 distinct ChEBI ids;
Reactome has 3,260; **1,114 are in both** (1,101 restricting Reactome to
*Homo sapiens*). So a `Metabolite`→`Pathway` bridge via ChEBI reaches
1,114 HMDB metabolites — 0.5 % of HMDB, but 34 % of everything Reactome has a
compound for.

**NCBI2Reactome** is **NCBI *Gene*** ids, not taxonomy: 73,767 distinct
numeric ids over 17,588 pathways. Confirmed by shape (id `1` = A1BG,
`R-HSA-114608` Platelet degranulation, *Homo sapiens*) and by scale — there is
no world in which 73,767 taxa map into 16 species' pathways. It is `NCBIGene`
per §5(a). Reactome does not ship a taxonomy mapping at all; species is a
plain-English string in the last column.

**Evidence codes.** Both mapping files carry `TAS` (traceable author
statement — a curator read a paper) or `IEA` (inferred from electronic
annotation — orthology projection from human):

| File | IEA | TAS | IEA share |
|---|---:|---:|---:|
| `ChEBI2Reactome.txt` | 99,768 | 14,011 | 87.7 % |
| `ChEBI2Reactome_All_Levels.txt` | 269,836 | 37,213 | 87.9 % |
| `NCBI2Reactome.txt` | 224,898 | 44,215 | 83.6 % |

This is the cleanest `knowledge_level` signal in the whole increment and it is
100 % filled.

### Pitfalls

1. **`R-SCE-9865878` ("Complex III assembly", *S. cerevisiae*) appears in both
   mapping files but is missing from `ReactomePathways.txt`.** A loader that
   requires the pathway node to pre-exist drops those rows; one that creates on
   demand mints a `Pathway` with no name or species unless it reads columns 4
   and 6 of the mapping row. Prefer the latter — the mapping files carry the
   name and species inline.
2. **22 `NCBI2Reactome` source ids are not gene ids at all** but nucleotide
   accessions: `MN908947.3` (the SARS-CoV-2 reference genome), `NC_001547`,
   `J02428.1`, `K02485`, `KJ852773`, `KT992094`, `M12294.2`, `MG736819`. A
   `int()` cast throws; a regex filter silently drops them. Route them to a
   `source_id_raw` property and report the count.
3. **`ChEBI2Reactome_All_Levels.txt` is not a superset with extra compounds —
   it is the same 3,260 compounds propagated up the hierarchy.** Loading both
   files creates 307,049 edges where 113,779 carry the information; use the
   lower-level file for edges and the hierarchy for ancestry queries.
4. Trailing whitespace in pathway names (204 in `ReactomePathways.txt`, and
   inside the mapping files' name column, e.g. `"Platelet degranulation "`) —
   strip before comparing names across files.
5. Reactome's species column and Reactome's id infix must agree; they do here,
   but the loader should assert it rather than reading species from one of them
   arbitrarily.

### Extraction table

| Source field | Graph target |
|---|---|
| `ReactomePathways.txt` col 1 | `Pathway` pk `REACT:<id>` |
| col 2 (stripped) | `Pathway.name` |
| col 3 | `Pathway.species` (verbatim string; no taxid available) |
| `ReactomePathwaysRelation.txt` | `(Pathway)-[:HAS_SUBPATHWAY]->(Pathway)` — DAG, 388 multi-parent children |
| `ChEBI2Reactome.txt` col 1 → `CHEBI:<n>` | `(Metabolite)-[:PARTICIPATES_IN]->(Pathway)` — join to HMDB's `chebi_id` |
| col 5 | edge `evidence_code` (`ECO:0000304` for TAS, `ECO:0000501` for IEA) and `knowledge_level` |
| col 6 | edge `species` |
| `NCBI2Reactome.txt` col 1 → `NCBIGene:<n>` | `(HostGene)-[:PARTICIPATES_IN]->(Pathway)` |

### Evidence vocabulary

- `primary_source = "reactome"`, `source_licence = "CC0-1.0"`.
- `knowledge_level = "knowledge_assertion"` for `TAS`,
  **`logical_entailment`** for `IEA` (orthology inference is exactly that).
- `agent_type = "manual_agent"` for `TAS`, `automated_agent` for `IEA`.
- `evidence_level`: not an abundance association, so the ladder does not apply
  — set `computational_predicted` for `IEA` and `unknown` for `TAS`, or omit
  the field on non-association edge types and say which types the audit covers.

---

## 5. KEGG

Six headerless 2-column TSVs from `rest.kegg.jp`. **Restrictive licence — the
whole KEGG slice stays behind a build flag** (`docs/sources.md`).

| File | Rows | Content |
|---|---:|---|
| `list_pathway.tsv` | 587 | `map01100` ↹ `Metabolic pathways` |
| `list_pathway_hsa.tsv` | 372 | `hsa01100` ↹ `Metabolic pathways - Homo sapiens (human)` |
| `list_compound.tsv` | 19,626 | `C00003` ↹ `NAD+; NAD; Nicotinamide adenine dinucleotide; …` |
| `link_compound_pathway.tsv` | 19,647 | `path:map00010` ↹ `cpd:C00022` |
| `conv_compound_pubchem.tsv` | 19,494 | `pubchem:3303` ↹ `cpd:C00001` |
| `list_genome.tsv` | 11,945 | `T01001` ↹ `hsa; Homo sapiens (human)` |

**Compound ↔ pathway.** All 19,647 link rows use the `map` (reference) prefix,
never `hsa`. They cover **464 of the 587 maps** (123 maps have no compound —
they are signalling/disease maps) and **6,688 of the 19,626 compounds
(34.1 %)**. Every linked compound and pathway exists in the corresponding list
file. Both sides carry a namespace prefix (`path:`, `cpd:`) that must be
stripped.

**Join to HMDB.** HMDB carries 5,900 distinct `kegg_id` values, of which
**5,873 (99.5 %) are present in `list_compound.tsv`**. So the compound bridge
is essentially total in the HMDB→KEGG direction and covers 30 % of KEGG's
compound space. The 27 misses are compounds KEGG has withdrawn since HMDB 5.0
(2021): `C00626`, `C01383`, `C01808`, `C02406`, `C03543`, `C05132`, … These
must be reported, not dropped silently — they are the measurable cost of
HMDB's age. HMDB's `kegg_id` prefixes: 5,889 `C` (compound), **8 `D`** (drug),
**2 `G`** (glycan), 1 lowercase `c` — the `D`/`G` ids will not join against a
compound list at all.

**No taxon join exists.** `/list/organism` was retired upstream (HTTP 400, see
`docs/sources.md` §7) and `list_genome.tsv` returns only
`T-number ↹ org_code; organism name`, with the taxonomic lineage column gone.
There is no taxid in any of the six files. 11,945 T-numbers, 11,945 distinct
organism codes, no duplicates, every row parses on the first `;`. Attaching a
KEGG pathway to a `Taxon` requires either name matching against `names.dmp`
(the names carry strain qualifiers — `Sorangium cellulosum So ce56` — and are
therefore lossy) or 11,945 per-genome `/get/genome:Txxxxx` requests. **Do not
build taxon–pathway edges from KEGG in this increment.** KEGG's contribution is
the compound vocabulary and the compound→map links.

### Pitfalls

1. **`conv/compound/pubchem` returns PubChem *Substance* ids (SIDs), not
   Compound ids (CIDs).** `C00001` (water) maps to `pubchem:3303`; water's
   PubChem **CID** is 962. Writing these into a `pubchem_cid` property makes
   every KEGG compound point at the wrong PubChem record, and it will look
   plausible because 3303 is a valid PubChem identifier. Store as
   `pubchem_sid`, or resolve SID→CID separately. HMDB's own
   `pubchem_compound_id` **is** a CID — the two must not share a property name.
2. `list_compound.tsv` column 2 is a `"; "`-joined synonym list on 8,777 of
   19,626 rows. The first atom is the display name; the rest are synonyms.
   Loading the whole cell as `name` produces names like
   `"NAD+; NAD; Nicotinamide adenine dinucleotide; DPN; …"`.
3. Both link columns are namespace-prefixed (`path:map00010`, `cpd:C00022`),
   and `conv` prefixes both sides too (`pubchem:3303`). Strip consistently, or
   the KEGG compound key will not match HMDB's bare `C00022`.
4. 132 of the 19,626 compounds have no PubChem mapping at all.
5. The `hsa` pathway list duplicates the `map` list with the species appended
   to the name (`Metabolic pathways - Homo sapiens (human)`). Loading both
   yields two `Pathway` nodes for one biological pathway. Use `map` ids as the
   pk and treat `hsa` as an organism-specific alias.

### Extraction table

| Source field | Graph target |
|---|---|
| `list_pathway.tsv` col 1 | `Pathway` pk `KEGG:<mapNNNNN>`, `source = "kegg"` |
| `list_pathway.tsv` col 2 | `Pathway.name` |
| `list_compound.tsv` col 1 | `Metabolite.kegg_compound_id` = `KEGG:<Cxxxxx>` (join key, not pk) |
| `list_compound.tsv` col 2, first `; ` atom | `Metabolite.kegg_name`; remainder → `kegg_synonyms` (list) |
| `link_compound_pathway.tsv` | `(Metabolite)-[:PARTICIPATES_IN]->(Pathway)` |
| `conv_compound_pubchem.tsv` | `Metabolite.pubchem_sid` — **never** `pubchem_cid` |
| `list_genome.tsv` | not loaded this increment (no taxid) |

### Evidence vocabulary

- `primary_source = "kegg"`, `source_licence = "kegg-restricted"`, and the
  whole slice gated on the build flag.
- `knowledge_level = "knowledge_assertion"` — KEGG maps are manually drawn.
- `agent_type = "manual_agent"`.
- `evidence_level = "unknown"` — KEGG ships no per-link evidence, and
  fabricating one would be exactly the F10 failure the schema survey warns
  about.

---

## 6. ChEMBL 37

Three JSONL files plus a TSV. CC BY-SA 3.0 (copyleft — a derived graph
incorporating this must itself be CC BY-SA).

### `mechanism.jsonl` — 7,561 rows, the Drug→ProteinTarget edge list

Field fill: `mec_id`, `record_id`, `molecule_chembl_id`,
`parent_molecule_chembl_id`, `mechanism_of_action`, `max_phase`,
`direct_interaction`, `disease_efficacy`, `molecular_mechanism` all 100 %;
`mechanism_refs` 99.4 %; **`action_type` and `target_chembl_id` 92.4 %**;
`mechanism_comment` 28.3 %; `selectivity_comment` 6.2 %;
`binding_site_comment` 4.8 %; `site_id` 3.3 %; `variant_sequence` 0.9 %.

5,954 distinct molecules, 1,518 distinct targets (plus 577 rows with a null
target — vaccines, antiseptics, and drugs whose target is unknown; those rows
also have a null `action_type`).

`action_type`: INHIBITOR 3,586, ANTAGONIST 980, AGONIST 949, BINDING AGENT 284,
BLOCKER 179, MODULATOR 111, POSITIVE ALLOSTERIC MODULATOR 82, … 35 values in
all. `direct_interaction = 1` on 7,557 of 7,561; `disease_efficacy = 1` on
7,559; `molecular_mechanism = 1` on 7,559 — these three flags are effectively
constant and carry no discriminating information.

`max_phase` **on the mechanism row**: `4` 3,814, `2` 2,029, `3` 1,130, `1` 500,
`-1` 88.

### `mechanism_refs` — the evidence

13,600 reference objects, `{ref_id, ref_type, ref_url}`; **42 rows (0.6 %) have
no refs at all**. `ref_type` distribution:

| ref_type | n | | ref_type | n |
|---|---:|---|---|---:|
| PubMed | 8,289 | | ISBN | 302 |
| Other | 1,286 | | ClinicalTrials | 153 |
| DailyMed | 1,171 | | DOI | 112 |
| FDA | 1,031 | | PMC | 41 |
| Wikipedia | 702 | | Expert | 40 |
| EMA | 369 | | KEGG, BNF, IUPHAR, PMDA, HMA, PubChem, Patent, UniProt, InterPro | ≤ 39 each |

5,677 distinct PubMed ids. This is a **typed, multi-valued** provenance field —
exactly the `publications` list §5(b) asks for, and richer: a `DailyMed`/`FDA`
reference is regulatory label evidence, which is a different knowledge claim
from a PubMed paper.

### `molecule_max_phase4.jsonl` — 4,225 approved molecules

`molecule_chembl_id`, `pref_name`, `molecule_type`, `max_phase` (**the string
`"4.0"` on every row**), `therapeutic_flag`, `withdrawn_flag`, `oral`,
`parenteral`, `topical` all 100 %; `first_approval` 89.4 % (year int);
`molecule_properties` 84.1 % (alogp, full_mwt, psa, qed_weighted, ro5 …);
`molecule_structures` 80.9 % (canonical SMILES **plus a full molfile**);
`atc_classifications` 57.0 % (list of ATC codes, e.g. `["C02CA01"]`).

### `target.jsonl` — 1,518 targets

`target_chembl_id`, `pref_name`, `target_type`, `species_group_flag` 100 %;
**`organism` 98.5 %**; **`tax_id` 98.4 %** (1,493 rows — the sources doc does
not mention this field, and it is the ChEMBL taxon join);
`target_components` 91.4 %; `cross_references` 2.5 %.

`target_type`: SINGLE PROTEIN 1,075, PROTEIN FAMILY 111, PROTEIN COMPLEX 102,
NUCLEIC-ACID 64, SMALL MOLECULE 37, PROTEIN COMPLEX GROUP 28, OLIGOSACCHARIDE
22, MACROMOLECULE 16, METAL 10, LIPID 10, and 8 more. **Only 1,075 targets are
a single protein**; the rest are families, complexes, or not proteins at all.

UniProt accessions come from `target_components[].accession`: 2,729 component
accessions, 2,283 distinct, on **1,385 of 1,518 targets** (91.2 %). 131 targets
have zero components (the metals, subcellular compartments, cell lines).
`chembl_uniprot_mapping.txt` is the FTP twin: 17,257 rows, 12,371 distinct
UniProt accessions, 13,209 distinct ChEMBL targets, typed by the same
`target_type` strings — it covers the whole of ChEMBL, not just our 1,518.

`tax_id`: **125 distinct, every one live in `nodes.dmp`** — 0 merged, 0
deleted, 0 unknown. This is the cleanest taxid set of any source here. 1,211
targets are *Homo sapiens*; 282 are not, and **865 mechanism rows point at a
non-human target**: `Bacteria` (19 targets), *Staphylococcus aureus* (18),
HIV-1 (10), *M. tuberculosis* (8), *S. pneumoniae* (8), *P. aeruginosa* (7),
*N. meningitidis* (6), *E. coli* (4). That is the antibacterial slice, and it
is the only part of ChEMBL that touches a microbe.

### How the Drug→ProteinTarget edge is built

```
Drug(CHEMBL<mol>) -[:HAS_MECHANISM {action_type, mechanism_of_action,
                                    publications, source_record_id=mec_id}]->
ProteinTarget(CHEMBL<target>)
```
with `ProteinTarget.uniprot` = the accessions of its `target_components`, and
`ProteinTarget.tax_id` giving the organism. Where the target is
`SINGLE PROTEIN`, project a second edge to `UniProtKB:<accession>` so the
metabolite–protein edges from HMDB (§2, 863,759 rows, 100 % UniProt) join here.

### Pitfalls

1. **The `Drug` node set does not cover the edge set.** `molecule_max_phase4`
   holds 4,225 approved molecules; `mechanism.jsonl` names **5,954** distinct
   molecules, of which only **3,025 are in the molecule file**. Loading
   mechanisms against `max_phase = 4` drops 49 % of the mechanism rows, and
   loading all of them mints 2,929 `Drug` nodes with no `pref_name`, no ATC and
   no approval year. Decide explicitly: either filter mechanisms to
   `max_phase == 4` (3,814 rows) or fetch the missing molecules. Do not do
   half of each.
2. **`max_phase` has two types in two files**: integer `4` on mechanism rows,
   the string `"4.0"` on molecule rows. `==` across them fails silently.
3. **577 mechanism rows (7.6 %) have a null `target_chembl_id` and a null
   `action_type`.** They are real curated mechanisms (`mechanism_of_action` is
   100 % filled) with no protein endpoint — load them as
   `Drug.mechanism_of_action` text, not as a dangling edge.
4. **Two `ref_type: PubMed` entries carry a URL in `ref_id`** (`mec_id`
   9195 and 9450, both `https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4804253/`
   of 8,289 PubMed references). Validate `ref_id` against `\d+` before
   writing `PMID:<id>`; the rest are clean. The loader ledgers each as
   `malformed_reference`.
5. **`parent_molecule_chembl_id` differs from `molecule_chembl_id` on 1,626
   rows** (salt vs free base). Edges keyed on `molecule_chembl_id` will
   duplicate the same drug under several salt forms — 38 `(molecule, target,
   action_type)` triples already repeat, up to 5×. Key `Drug` on the *parent*
   and keep the salt id on the edge. The loader keeps it as
   `reported_molecule_chembl_id`; `source_record_id` is the mechanism record's
   own `mec_id`, the provenance-of-record field every source fills the same
   way.
6. `molecule_structures.molfile` is a multi-kilobyte embedded MOL block on
   3,417 records — it is 60 % of the 12.8 MB file and nothing in the model uses
   it. Drop it at parse time.
7. `target_components[].target_component_xrefs` mixes PDBe, GoProcess,
   GoFunction, GoComponent, InterPro and more in one list keyed by
   `xref_src_db` — filter, don't iterate blindly.

### Extraction table

| Source field | Graph target |
|---|---|
| `molecule.parent_molecule_chembl_id` (via mechanism) / `molecule_chembl_id` | `Drug` pk `CHEMBL:<id>` |
| `molecule.pref_name`, `molecule_type`, `first_approval`, `withdrawn_flag`, `oral`/`parenteral`/`topical`, `atc_classifications` | `Drug` properties |
| `molecule.molecule_structures.canonical_smiles` | `Drug.smiles` (drop `molfile`) |
| `target.target_chembl_id` | `ProteinTarget` pk `CHEMBL:<id>`; `pref_name`, `target_type`, `organism` |
| `target.tax_id` | `(ProteinTarget)-[:IN_ORGANISM]->(Taxon)` — 125 taxids, all live |
| `target.target_components[].accession` | `ProteinTarget.uniprot` (list) + `UniProtKB:` node for `SINGLE PROTEIN` |
| `mechanism.action_type` | edge `action_type` |
| `mechanism.mechanism_of_action` | edge `source_relation` (verbatim) |
| `mechanism.mec_id` | edge `source_record_id` |
| `mechanism.mechanism_refs[]` where `ref_type = PubMed` | edge `publications` = `["PMID:…"]`; `DOI` → `DOI:…` |
| `mechanism.mechanism_refs[]` where `ref_type ∈ {DailyMed, FDA, EMA, PMDA, HMA, BNF}` | edge `regulatory_refs` (list of URLs) — a different evidence class from a paper |
| `mechanism.max_phase` | edge `clinical_phase` |

### Evidence vocabulary

- `primary_source = "chembl"`, `source_licence = "CC-BY-SA-3.0"`, and the
  attribution string (`ChEMBL 37`, Mendez et al. 2019) recorded once at graph
  level.
- `knowledge_level = "knowledge_assertion"` — every mechanism row is a curator
  assertion backed by a reference.
- `agent_type = "manual_agent"`.
- `evidence_level`: `interventional_clinical` where `max_phase = 4` **and** at
  least one `DailyMed`/`FDA`/`EMA` reference exists (an approved label);
  `in_vitro` where the only references are PubMed and the target is a single
  protein; `unknown` for the 42 ref-less rows. Never `computational_predicted`
  — nothing in this subset is predicted.

---

## 7. MONDO

`data/raw/mondo/mondo.obo`, release `2026-09-01`, CC BY 4.0.

**63,278 `[Term]` blocks**, of which **36,015 are `MONDO:`-prefixed**. The
remaining 27,263 are imported terms from BFO, UBERON (5,360), HP (4,859),
GO (4,142), NCBITaxon (2,227), CHEBI (1,269), CL (1,222), ENVO, ECTO, PATO,
CHR and a `http…` bucket of 5,788 anonymous class ids. **A loader that counts
`[Term]` blocks or keys nodes on `id:` without filtering the prefix creates
27,263 non-disease nodes.**

**Obsolete terms: 4,618**, of which **2,488 carry `replaced_by:`** and 665
carry `consider:` (a weaker suggestion, not a redirect). The remaining ~1,465
obsolete terms have neither and are dead ends.

**Xrefs.** 122,000+ `xref:` lines on MONDO terms, each optionally annotated
`{source="…"}`. Source values: **`MONDO:equivalentTo` 93,943**, `MONDO:GARD`
15,930, `MONDO:relatedTo` 2,434, `MONDO:NANDO` 2,345,
`MONDO:obsoleteEquivalent` 1,893, `MONDO:equivalentObsolete` 927,
`MONDO:otherHierarchy` 542, plus ORCID-attributed and unannotated ones.
**Only `MONDO:equivalentTo` is a 1:1 equivalence**; `relatedTo`,
`otherHierarchy` and the two `obsolete*` variants are not and must not be used
as a merge key.

Equivalence counts by target vocabulary (`source="MONDO:equivalentTo"` only):

| Prefix | equivalentTo | all xrefs |
|---|---:|---:|
| MEDGEN | 21,661 | 21,661 |
| UMLS | 12,217 | 21,661 |
| **DOID** | **11,258** | 12,091 |
| SCTID | 7,234 | 9,158 |
| Orphanet | 6,896 | 10,491 |
| OMIM | 6,498 | 10,176 |
| MESH | 5,699 | 8,211 |
| NCIT | 5,035 | 7,440 |
| **EFO** | **2,387** | 2,400 |
| ICD10CM | 619 | 2,142 |
| MedDRA | 3 | 1,488 |

**No EFO, DOID, MeSH, UMLS, NCIT, ICD10CM or Orphanet id maps to more than one
MONDO term under `equivalentTo`** — the equivalence relation is a clean
function in the direction this project needs. And **no `equivalentTo` xref from
EFO or DOID points at an obsolete MONDO term**, so the obsolete set does not
have to be chased for these two vocabularies.

### Does it actually join our two sources?

**BugSigDB** (`data/raw/bugsigdb/full_dump_v1.3.1.csv`, column `EFO ID`):
7,425 non-empty cells, **127 multi-valued**, **587 distinct CURIEs** across 15
prefixes — EFO 427, MONDO 71, HP 28, CHEBI 24, GO 15, NCBITAXON 9, then XCO,
OBI, PATO, EXO, DOID, ORPHANET, IDOMAL, BTO, MP. Resolution:

| Outcome | distinct CURIEs |
|---|---:|
| already MONDO | 71 |
| MONDO via `equivalentTo` | 180 (179 EFO + 1 DOID) |
| only a non-`equivalentTo` xref | 3 |
| no MONDO at all | **333** |

**51.5 % of BugSigDB's 7,425 rows (3,822) resolve to a MONDO id.** The 333
unresolved are not a MONDO gap — they are **not diseases**: `EFO:0004866`
Autoantibody measurement, `EFO:0010105` CD4-positive T-lymphocyte count,
`EFO:0004611` LDL cholesterol measurement, `EFO:0001799` Ethnic group,
`EFO:0005271` Sleep duration, `EFO:0003939` Energy intake, plus every
`CHEBI:`, `GO:`, `NCBITAXON:` and `PATO:` value in the column. `docs/model.md`
already keys `Disease` on the raw CURIE with an `ontology` property for this
reason; MONDO turns that into a real canonical key **for the disease half
only**, and the rest belong on `Phenotype` / `Measurement` / `Exposure` node
types (§5(a) is explicit that phenotype must not be collapsed into disease).

**gutMDisorder** (`DOID` column, both workbooks): **91 distinct DOIDs**.
64 map via `equivalentTo`, 22 have a MONDO xref under a weaker source, and
**5 do not map at all**: `DOID:8878` (the one inside the comma-multivalued
cell), `DOID:9357`, `DOID:9770`, `DOID:9552`, and `DOID:00400085` — the last
of which is **malformed**: DOID ids are 1–7 digits and `00400085` is 8 with a
leading double zero.

### Pitfalls

1. **Filter on the `MONDO:` id prefix.** 43 % of the `[Term]` blocks in this
   file are imported foreign terms.
2. **Only `source="MONDO:equivalentTo"` is a merge key.** Using every `xref:`
   line adds 28,000+ non-equivalent mappings; using `MONDO:relatedTo` or
   `MONDO:obsoleteEquivalent` to key a disease node merges distinct concepts.
   The counts differ enormously per vocabulary — UMLS is 12,217 equivalent of
   21,661 total, MedDRA is **3 of 1,488**.
3. **Prefix casing differs between sources and MONDO.** BugSigDB writes
   `ORPHANET:101953` and `NCBITAXON:10566`; MONDO writes `Orphanet:` and
   `NCBITaxon:`. An exact-string lookup misses them; an upper-cased lookup
   recovers `ORPHANET:101953` (as a non-equivalent xref). Normalise case on
   both sides and keep the source's verbatim string, per §5(a).
4. **Obsolete MONDO terms with no `replaced_by`** — roughly 1,465 of the 4,618.
   `consider:` (665) is a suggestion, not a redirect, and must not be followed
   automatically.
5. `xref:` lines appear on obsolete MONDO terms too (1,893 marked
   `MONDO:obsoleteEquivalent`, 927 `MONDO:equivalentObsolete` — two different
   annotations meaning different things). Neither is a live equivalence.
6. `mondo.sssom.tsv` — the machine-readable mapping set the schema survey
   recommends — **is not published on this release** (HTTP 404,
   `docs/sources.md` §11). The OBO xrefs are the only mapping source we have,
   and they lack SSSOM's `predicate_id` / `mapping_justification` columns; the
   `source=` annotation is the substitute.

### Extraction table

| Source field | Graph target |
|---|---|
| `id: MONDO:*` (not obsolete) | `Disease` pk `MONDO:<id>` |
| `name:` | `Disease.label` |
| `is_a:` (MONDO→MONDO only) | `(Disease)-[:IS_A]->(Disease)` |
| `xref:` with `source="MONDO:equivalentTo"`, prefix EFO | `Disease.efo_id` (list) — the BugSigDB join |
| … prefix DOID | `Disease.doid_id` (list) — the gutMDisorder join |
| … prefix MESH / UMLS / NCIT / OMIM / Orphanet | `Disease.mesh_id` / `umls_cui` / `ncit_id` / `omim_id` / `orphanet_id` |
| `is_obsolete: true` + `replaced_by:` | redirect table applied at load; never a node |
| `def:` | `Disease.definition` |

### Evidence vocabulary

MONDO contributes no association edges, so no `evidence_level`. Where an
`IS_A` or a cross-reference edge is materialised:
`primary_source = "mondo"`, `source_licence = "CC-BY-4.0"`,
`knowledge_level = "knowledge_assertion"`, `agent_type = "manual_agent"`
(MONDO's equivalences are OWL-reasoned and curator-reviewed; the
`logical_entailment` value would also be defensible for the inferred half, but
the OBO release does not distinguish them, so do not guess).

---

## What this profile changes about the plan

1. **Taxon–metabolite edges are 224, not thousands.** HMDB's microbial branch
   is 0.10 % of the file and carries no taxids. Use case A5.2 ("metabolites
   produced by a taxon") is answerable but small, and A5.5 (cross-feeding)
   remains descoped — nothing here carries consumption.
2. **Two sources give a real taxon join; three give none.** gutMDisorder
   (96–97 %) and CARD (99.4 %) carry NCBI taxids and both need `merged.dmp`
   (16 and 17 stale ids respectively) and `delnodes.dmp` (2). ChEMBL's targets
   carry a clean 125-taxid set. Reactome, KEGG and HMDB carry none.
3. **MONDO earns its place but only covers the disease half.** 51.5 % of
   BugSigDB rows and 70 % of gutMDisorder's DOIDs resolve; the misses are
   overwhelmingly measurements and phenotypes, which need their own node type
   rather than a lower MONDO coverage target.

## The three biggest pitfalls per source

| Source | 1 | 2 | 3 |
|---|---|---|---|
| gutMDisorder | mouse `Index` floats: `int()` mis-joins one row to the wrong paper, `==` drops 45 | Association has no link to a Sample arm — group sizes are study-level only | 22 identical + 76 near-identical duplicate association rows, and 15 direction contradictions |
| HMDB | one disease name on 20,020 of 27,670 disease rows | microbial origin is 224 records with free-text, misspelled, mixed-rank organism names and no taxid | 88.8 % of records are `predicted`/`expected`, never observed |
| CARD | `aro_index.tsv` and `card.json` disagree on 84 models | the taxid is the *reference sequence's* organism (132 models say "Bacteria") | `ncbi_taxonomy.obo` renames NCBI terms; `ARO_accession` is bare in JSON, prefixed in TSV |
| Reactome | 16 model-organism species — no gut taxa at all | `NCBI2Reactome` is NCBI **Gene**, and 22 of its ids are nucleotide accessions | `_All_Levels` is the same 3,260 compounds re-projected, not more data |
| KEGG | `conv/compound/pubchem` gives SIDs, not CIDs | no taxid anywhere — the organism list is retired upstream | compound names are `"; "`-joined synonym lists; only 34 % of compounds have a pathway |
| ChEMBL | mechanism names 5,954 molecules, the molecule file has 3,025 of them | `max_phase` is int in one file, `"4.0"` string in the other | 1,626 rows key on a salt rather than the parent molecule |
| MONDO | 43 % of `[Term]` blocks are imported non-MONDO terms | only `source="MONDO:equivalentTo"` is a merge key (MedDRA: 3 of 1,488) | prefix casing differs (`ORPHANET:` vs `Orphanet:`); `mondo.sssom.tsv` is not published |

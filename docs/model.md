# The graph model

MicroMap's shape (taxa, diseases, metabolites, pathways, drugs, resistance,
papers) with one thing added that it does not have: **an association edge
cannot exist without saying how it was demonstrated**, and the ontology
reports what fraction of them fail that.

Everything below is built and measured, on a clean `scripts/build.py` run of
2026-09-03 carrying **six** sources: NCBI taxonomy + BugSigDB (increment 1),
gutMDisorder (increment 2), then CARD, HMDB, Reactome and ChEMBL. KEGG is
licence-gated and off by default, so no number here includes it. A source is
added as files — `scripts/prep_<source>.py`, `blueprints/<source>.json`,
`microbiomekg/ontology/<source>.py` — never by editing a shared one (§8).

---

## 1. Node types

| Type | pk | title | Source of the key | Increment |
|---|---|---|---|---|
| `Taxon` | `tax_id` (int) | `scientific_name` | NCBI `nodes.dmp` | 1 |
| `UnresolvedTaxon` | `unresolved:<source>:<raw>` | `raw_name` | our own | 1 |
| `Disease` | MONDO CURIE where MONDO declares an equivalence, else the source CURIE | `label` | BugSigDB "EFO ID" | 1 |
| `Phenotype` | HP CURIE | `label` | BugSigDB "EFO ID" | 1 |
| `Exposure` | CHEBI / ENVO / EXO / GSSO CURIE | `label` | BugSigDB "EFO ID" | 1 |
| `BodySite` | `UBERON:0001155` else `site:<slug>` | `label` | BugSigDB "UBERON ID" | 1 |
| `Study` | `bsdb:<n>` | `title` | BugSigDB BSDB ID prefix | 1 |
| `Signature` | `bsdb:<study>/<exp>/<sig>` | `description` | BugSigDB BSDB ID | 1 |
| `Paper` | `pmid` (int) | `title` | PubMed | 1 |
| `Intervention` | `INTERVENTION:<slug>` | `label` | gutMDisorder `Intervention` (+ `drugbank_id`) | 2 |
| `Metabolite` | ChEBI CURIE where HMDB carries a `chebi_id`, else `HMDB:<accession>` | `name` | HMDB `hmdb_metabolites.xml`; KEGG/PubChem/InChIKey as properties | 2 |
| `Pathway` | `REACT:R-HSA-…` / `KEGG:map…` | `name` | Reactome, and KEGG behind `--with-kegg`; `pathway_source` property | 2 |
| `Drug` | `CHEMBL:<parent molecule id>` | `pref_name` | ChEMBL `max_phase = 4` **and** every molecule a mechanism names | 3 |
| `ProteinTarget` | `CHEMBL:<target id>` | `pref_name` | ChEMBL; `uniprot`, `tax_id` properties | 3 |
| `ResistanceGene` | `ARO:3002999` | `name` | CARD `card.json` model, named from `aro.obo` | 3 |
| `DrugClass` | `ARO:0000032` | `label` | CARD ARO category `Drug Class` | 3 |
| `ResistanceMechanism` | `ARO:0001004` | `label` | CARD ARO category `Resistance Mechanism` | 3 |

Decisions worth the ink:

**The column named "EFO ID" is neither EFO nor, in 7% of its mentions, a
condition this model has a type for.** It carries **21** vocabularies over the
full dump — MONDO 7,390 mentions, EFO 5,447, HP 678, GO 348, CHEBI 324, OBA
257, IDOMAL 130, NCBITAXON 127, and thirteen more. Three decisions follow, all
made in `microbiomekg/conditions.py` so no prep script re-decides them.

**Node type comes from the CURIE's prefix, never from the column's name.**
`MONDO`/`EFO`/`DOID`/`ORPHANET` become `Disease`, `HP` becomes `Phenotype`,
`CHEBI`/`ENVO`/`EXO`/`GSSO` become `Exposure`. Everything else — `GO`
processes, `OBA` measurements, `CL` cell types, `OBI` protocols,
`NCIT:C102763` (a *surgical procedure*), `XCO`, `PO`, `BTO`, `MP`, `IDOMAL`,
`PR` and `NCBITAXON` — gets **no node type at all**. `NCBITAXON:568703` is
*Lacticaseibacillus rhamnosus* GG, a probiotic used as the exposure; typing it
`:Disease` puts a bacterial strain in the disease list, and inventing an
`Anything` type for the other twelve would be the same error with more steps.
Those 116 terms and 1,027 mentions go to `data/csv/unresolved_conditions.csv`
with their raw strings and the reason — recorded, never dropped. `Phenotype` is
kept apart from `Disease` on the schema survey's own counter-example: PrimeKG
folded HPO phenotypes and drug side effects into one type and cannot undo it.

**The key is the MONDO CURIE where MONDO says the two terms are the same.**
MONDO ships curated 1:1 equivalence axioms as `xref:` lines qualified
`source="MONDO:equivalentTo"`, and that qualifier is the *only* thing read.
Measured on the 2026-09-01 release: **372 of 875 typed terms join the hub**
(371 live MONDO ids plus their own identity), and **503 keep their own CURIE
with `mondo_id` null**. Both halves stay queryable — `source_id` and
`source_vocabulary` are on every node, so `WHERE d.source_vocabulary = 'EFO'`
survives the rename, and `source_condition` keeps the verbatim string BugSigDB
wrote.

Two measured facts worth stating plainly, because both are counter-intuitive:

- **None of BugSigDB's 394 EFO ids has a MONDO equivalence.** MONDO's 2,400
  `EFO:` equivalence xrefs and BugSigDB's 394 EFO ids are disjoint sets. The
  hub therefore joins nothing on this source's second-largest vocabulary; it
  will join gutMDisorder's DOIDs (12,091 equivalences) when that source lands.
  The EFO ids stay `Disease` nodes with their own CURIE — and some of them
  (`EFO:0000246` Age, `EFO:0004340` Body mass index) plainly are not diseases.
  Routing those correctly needs a term-level EFO import, which this increment
  does not have; guessing from the label would be the merge-on-name failure the
  survey catalogues.
- **A `source="EFO:…"` attribute is not an equivalence, and reading it as one
  is measurably wrong.** `xref: NCIT:C84442 {source="EFO:0000195",
  source="MONDO:equivalentTo"}` says *MONDO ≡ NCIT:C84442, as asserted by EFO's
  record* — not MONDO ≡ EFO:0000195. Taking it as an equivalence yields exactly
  four EFO joins on the real dump and **all four are wrong**: `EFO:0000195`
  *Metabolic syndrome* would become `MONDO:0000816` *abdominal
  obesity-metabolic syndrome*, and `EFO:0000180` *HIV-1 infection* would become
  `MONDO:0004951` *susceptibility to HIV infection*. The cheap-looking join
  more than doubles hub coverage and poisons it.
- **Two MONDO ids BugSigDB cites are obsolete** in the current release
  (`MONDO:0016667`, `MONDO:0100318`), and an obsolete term's `name:` literally
  begins with the word "obsolete". They are treated as not-live: own CURIE as
  key, `mondo_id` null.

**Condition ↔ id pairing: the C11 comma trap, in a second column.** Both
`Condition` and `EFO ID` are comma-joined, and — exactly like `Study design` —
some *condition labels contain a comma*: `Helminthiasis, animal`,
`Osteoarthritis, knee`, `Hypertension, pregnancy-induced`. **All 42 rows of the
full dump whose two columns disagree on comma count are that shape.** Worse,
`MONDO:0024647,MONDO:0008171` appears with `Nephrolithiasis,Urolithiasis` on
one row and the reverse label order on another, so a positional zip is not
merely incomplete, it is contradictory. Three rules, in order:

1. **Equal comma counts → pair positionally** (14,603 rows). Nothing is in
   doubt.
2. **Otherwise, match by label**: look each id's name up in MONDO and consume
   the contiguous run of fragments whose `", "`-join equals it. That
   reassembles `Helminthiasis` + `animal` — **18 of the 42**.
3. **Otherwise, if the row has exactly one id**, the whole `Condition` cell
   verbatim is that id's label — **24 of the 42**. With one id there is no
   pairing decision to get wrong, so this is an identity, not a guess. (It is
   what carries `Hepatitis, Alcoholic` onto `MONDO:0001505`, whose MONDO name
   is *alcoholic hepatitis* and which no label match reassembles.)

Anything still unpaired goes to the ledger with its raw string. On the full
dump that is one row: a condition label with no id at all.

**Accounting.** 14,987 condition mentions in; 12,843 `IN_CONDITION` + 678
`IN_PHENOTYPE` + 438 `IN_EXPOSURE` + 1,028 ledger rows out. The three sinks sum
to the input, which is C18's rule applied to the condition column.

**`Paper` is separate from `Study`.** Every later source (CARD, ChEMBL,
Disbiome) cites PMIDs too, so `Paper` is the join point that makes "what else
does this paper support?" a one-hop query. `Study` is BugSigDB's curation unit;
`Paper` is the literature. Verified: the study-level fields (PMID, title,
journal, year, DOI) are perfectly constant within all 2,126 BugSigDB studies,
so hoisting them to a node loses nothing.

**A few PMIDs are not PMIDs.** A handful of rows put a DOI or a PMC id in the
PMID column. Those get no `Paper` node and no `pmid` on the edge, and the raw
string is kept as `Study.pmid_raw` so the loss is visible.

**`Metabolite` is a selected slice, and the rule is a property on the node.**
HMDB has 217,920 records and **88.8% of them are `predicted` or `expected`** —
never observed in any sample. Loading all of them would put a chemistry
database in a microbiome graph, so a record is kept when it satisfies at least
one of three rules: it carries the ontology path
`Disposition/Source/Biological/Microbe` (**224 records**, the only ones that can
produce a `PRODUCES` edge — and **67 of those name no organism beneath it**, so
157 records over 957 organism terms are what the 578 edges come from); `Feces`
is in its `biospecimen_locations` (6,791 —
the gut slice, and HMDB's second-largest biospecimen class); or its `chebi_id`
is one Reactome's `ChEBI2Reactome.txt` maps, which is the only way an HMDB
record can reach a pathway. Which rule kept it is `Metabolite.selection_rule`,
joined with `|` when several did, so `WHERE m.selection_rule = 'feces'` counts
the rule rather than trusting this paragraph. `status` rides on the node for
the same reason: it is what makes "measured or predicted" a filter.

**The key is ChEBI where HMDB has one.** ChEBI is the identity the rest of the
increment joins on — Reactome's compound file is ChEBI ids and nothing else —
so a metabolite that has one is keyed on it. The consequence is that HMDB's
13,701 `chebi_id` values over 13,562 distinct ids merge a handful of record
pairs onto one node, which is correct (they are one compound) but drops the
second record's scalar properties; each merge is a row in
`data/csv/unresolved_production.csv` naming both accessions.

**HMDB's disease layer is not loaded at all.** 20,020 of its 27,670 disease
rows — 72% — carry the single name `3-methylglutaconic aciduria type II,
X-linked`, where the next name down has 831. That is a curation accident, and
loading it produces one `Disease` node with 20,020 metabolite edges that
dominates every path query in the graph. The rows are counted and reported by
the prep. The other ~7,650 are probably fine; they are not loaded because the
layer cannot be loaded in part without inventing a rule for which curation
accidents count.

### `Signature` is a node — recommended, and why

The choice was between a flattened `(Taxon)-[:ASSOCIATED_WITH {…20 fields}]->(Disease)`
edge and a `Signature` node with one edge per taxon. **The model uses both, with
a rule that stops it being duplication:**

> Anything the ontology must *audit* lives on the edge. Everything else lives on
> the `Signature` node.

- `Signature` (14,846 nodes) carries the full curation record: group names and
  definitions, variable region, sequencing platform, data transformation, MHT
  correction, LDA cutoff, **`matched_on`, `confounders`,
  `antibiotics_exclusion`**, alpha diversity, curator, curation date, figure of
  origin, state. Those three confounder columns are guard G7 —
  *confounder control is schema, not metadata* — and D11 is the query that
  reads them: 26 differentially abundant ASVs in type 2 diabetes became **0**
  after matching on host variables, and no other source in the survey records
  the fact at all.
- The three association relationships (112,183 edges: 105,097 `ASSOCIATED_WITH`
  + 4,717 `ASSOCIATED_WITH_PHENOTYPE` + 2,369 `ASSOCIATED_WITH_EXPOSURE`) carry
  the **fourteen-field evidence contract** and nothing else, because
  `required_properties` is the only completeness check kglite can enforce, and
  it works on **edge** properties only. Putting the evidence on the `Signature`
  node would make the whole premise of this project unauditable.

> **A column the blueprint does not declare still reaches the graph** — the
> loader carries every CSV column it is not told to `skip`. So "the property
> answers a query" is not evidence that anything guarantees it: an undeclared
> column has no declared type, is invisible to the ontology's `property_types`
> check, and rests on the loader staying generous. Every property a query in
> Part D reads is therefore declared, and `tests/test_acceptance.py` asserts
> the declaration rather than the value's presence.

What the `Signature` node buys, concretely:

- "How many independent studies support this taxon in this disease?" is
  `count(DISTINCT r.study_id)` either way, but "which experimental arms, at what
  group sizes, from which figure?" needs the node.
- The evidence for 115k taxon mentions is written **once per signature** rather
  than being a per-mention string blob.
- The 1.3% of signatures with no condition still exist as nodes with their taxa
  attached; a purely flattened model would have nothing to hang them on.

What the flattened edge buys: `shortestPath` and evidence filtering are one hop,
not three, and the ontology can audit them.

`sub_nodes` were considered for `Signature` under `Study` and rejected:
`Signature` is referenced by `Taxon` and `Disease` from outside its parent, so
it is a first-class node, not owned detail. `sub_nodes` fits the
`Signature`→per-taxon-statistic table if a later source provides effect sizes
per taxon (BugSigDB does not).

---

## 2. Edge types and the evidence contract

| Edge | Domain → Range | Carries |
|---|---|---|
| `HAS_PARENT` | `Taxon` → `Taxon` | — (parent pointer, `ancestry`) |
| `ASSOCIATED_WITH` | `Taxon` → `Disease` | **the evidence contract** |
| `ASSOCIATED_WITH_PHENOTYPE` | `Taxon` → `Phenotype` | **the same contract** |
| `ASSOCIATED_WITH_EXPOSURE` | `Taxon` → `Exposure` | **the same contract** |
| `REPORTED_BY` | `ReportedTaxon` → `Signature` | reconciliation provenance |
| `PART_OF_STUDY` | `Signature` → `Study` | — |
| `IN_CONDITION` | `Signature` → `Disease` | — |
| `IN_PHENOTYPE` | `Signature` → `Phenotype` | — |
| `IN_EXPOSURE` | `Signature` → `Exposure` | — |
| `AT_BODY_SITE` | `Signature` → `BodySite` | — |
| `ABUNDANCE_CHANGED_BY` | `Taxon` → `Intervention` | **the same contract** |
| `CONFERS_RESISTANCE_TO` | `ResistanceGene` → `DrugClass` | **CARD's eight-property contract** |
| `VIA_MECHANISM` | `ResistanceGene` → `ResistanceMechanism` | **the same eight** |
| `CARRIES_RESISTANCE_GENE` | `Taxon` → `ResistanceGene` | **the same eight**, plus what the taxid means |
| `PRODUCES` | `Taxon` → `Metabolite` | **HMDB's nine-property production contract** |
| `IN_PATHWAY` | `Metabolite` → `Pathway` | **a seven-property pathway contract**, plus `evidence_code` |
| `PART_OF_PATHWAY` | `Pathway` → `Pathway` | — (sub-pathway pointer, `ancestry`, a **DAG**) |
| `PUBLISHED_AS` | `Study` → `Paper` | — |

**Three association relationships are one relation, split by the engine.** The
model wants a single `ASSOCIATED_WITH` over a union range, and the ontology can
express that (an abstract `Condition` class with three subclasses, the way
`ReportedTaxon` already works on the domain side). The **blueprint** cannot:
`junction_edges` is a map keyed by relationship name inside one node spec, and
each entry names exactly one `target` node type — so one relationship cannot be
loaded from three CSVs pointing at three types. The names are therefore listed
in `microbiomekg.ontology.ASSOCIATION_RELATIONSHIPS`, "any association" is
`-[:ASSOCIATED_WITH|ASSOCIATED_WITH_PHENOTYPE|ASSOCIATED_WITH_EXPOSURE]->`, and
the split is recorded in §8 as an engine limitation rather than a preference.
The same constraint splits `IN_CONDITION`.

### The evidence contract on `ASSOCIATED_WITH`

Fourteen properties, declared `required_properties` on all three association
relationships. One edge per `(signature, taxon, condition)` — parallel edges
are the point, not an error: they *are* the independent observations.

The first eight are **how it was demonstrated**; the last six are **who says
so, and under what terms** — the schema survey's §5(b) minimal provenance set.

| Property | Type | From | Missing (measured) |
|---|---|---|---|
| `direction` | string `increased`/`decreased` | Abundance in Group 1 | 0.8% |
| `study_design` | string | Study design | 0.02% |
| `evidence_level` | string, **derived** (below) | design + sequencing + host | 0% |
| `sequencing_type` | string `16S`/`WMS`/`ITS / ITS2`/`18S`/`PCR` | Sequencing type | 1.0% |
| `statistical_test` | string | Statistical test | 1.3% |
| `group_0_size` | int | Group 0 sample size | 11.7% |
| `group_1_size` | int | Group 1 sample size | 11.6% |
| `pmid` | int | PMID | 0.9% |
| `knowledge_level` | Biolink enum, `statistical_association` | derived from the source | 0% |
| `agent_type` | Biolink enum, `manual_agent` | derived from the source | 0% |
| `primary_source` | string `bugsigdb` | ours | 0% |
| `source_record_id` | string, the BSDB ID | BSDB ID | 0% |
| `source_licence` | string `CC-BY-4.0` | the export's own banner line | 0% |
| `source_relation` | string, the source's own wording | Abundance in Group 1 | 0.8% |

Also carried, deliberately outside the audited contract because they are
context rather than evidence: `signature_id` (the join key onto the
`Signature` node), `study_id`, `host_species`, `body_site`,
`significance_threshold`, `mht_correction`.

**Measured headline over both sources: 15.20% of taxon–disease edges (15,985
of 105,097) are missing at least one contract field**, plus 293 of 4,717
phenotype edges (6.21%), 485 of 2,369 exposure edges (20.46%) and **1,380 of
1,380 intervention edges (100%)**. Those are what `ontology_audit()` returns and
what the build prints, and they are the numbers the project exists to make
visible.

**The number moved when the second source landed, and that is the audit
working.** BugSigDB alone measured 14,349 of 103,461 = 13.87%. Every one of
gutMDisorder's 1,636 taxon–disease edges is missing three fields, so all 1,636
are violations: the source records **no study design** at all (`Research Type`
is a curation category — "gut microbiota associated with disorder" — not a
design, and writing it into the design column would improve this number by
misdescribing the data), and its association rows carry **no link to a sample
arm**, so there are no per-association `group_0_size`/`group_1_size` either;
the study's arm sizes are carried instead as `study_sample_size` /
`study_arm_sizes` with `sample_size_scope = "study-level (not
per-association)"`, and one mouse study has three arms, which no pair of group
sizes could have described. `ABUNDANCE_CHANGED_BY` is 100% for the same reason:
its whole population is that source. What gutMDisorder *does* carry on every
edge is a citation, a direction, a p-value, a named test and its assay — the
per-field census (§7 Q5, D15) is where that is legible, and a single percentage
over sources with different column sets is not.

**Why the Biolink pair, and why these two values.** `evidence_level` below is
project-controlled by necessity — ECO has no term that separates 16S from
shotgun differential abundance — but *how much of a claim an edge is* has a
portable vocabulary, and Biolink's `knowledge_level` × `agent_type` is it. The
two enums are pinned verbatim in `microbiomekg.ontology` (a near-miss spelling
exports silently and nothing downstream recognises it). A curated BugSigDB
signature is **`statistical_association` + `manual_agent`**: the assertion is
"these two groups' abundances differed significantly", which is a statistical
association and not a knowledge assertion about causation; and the agent is a
person — a named curator, with a curation date and a review state on the row,
transcribing a published figure. It is deliberately *not*
`data_analysis_pipeline`, which would be right for a resource that re-ran the
statistics itself. Both values come from a per-source table, so the next source
cannot inherit this one's answer, and a source nobody has read the evidence
model of gets `not_provided` — a real, countable value, never a plausible
default.

**`source_relation` is what makes normalisation reversible.** `direction` is
our two-valued normalisation; `source_relation` is BugSigDB's own wording of
the same fact (`abundance in group 1 increased`). RTX-KG2 quantifies what this
protects against: 1,228 source relation types collapsing into 77 Biolink
predicates. It is absent exactly where `direction` is absent, so the gap stays
countable rather than being papered over with a "not reported" string.

**`primary_source` and `source_record_id` are renames, not additions.** They
carry what `source` and `signature_id` used to, under the names a Biolink/KGX
export uses. Keeping both spellings would put two byte-identical strings on
110,547 edges, which is duplication rather than provenance.

`required_properties` reports one row per *edge*, not per field, so the audit
gives one honest completeness fraction and the per-field breakdown is a Cypher
query (§7, Q5). That is a deliberate reading of the tool, not a workaround.

### `evidence_level`

**The vocabulary is twelve values, and this table is the authority.** It is the
reconciliation `docs/usecases-and-pitfalls.md` Part B argues to — the research
document's nine-value list against the schema survey's seven — under one rule:
**`evidence_level` describes one observation, never a body of evidence.** An
edge is one signature's report of one taxon; it cannot know how many other
studies agree, and a stored answer would be frozen at build time and wrong
after the next refresh. So `curated_single_study`, `curated_replicated`,
`temporal_or_genetic` and `established` are *not* values here: replication is
`count(DISTINCT r.study_id)` at query time (D3, D17), the temporal axis
survives verbatim in `study_design`, and "established" is a verdict about a
pair, which is a query result. Part B carries the argument; this table carries
the vocabulary, and the two are cross-referenced rather than restated.

Ten values are emitted today by `microbiomekg.ontology.evidence_level()`; two
are reserved for sources being loaded next. **Spelling is hyphenated with `16S`
capitalised**, because that is what the built edges carry — a near-miss
spelling is a silent filter miss, so a source whose profile writes
`observational_16s` maps to the hyphenated form on write, and D15 counts
distinct values. The tuple is pinned as
`microbiomekg.ontology.EVIDENCE_LEVEL_VALUES`.

| Value | One-line definition | What justifies assigning it |
|---|---|---|
| `computational-predicted` | No measurement of *this* edge: a genome/MAG pathway call, sequence similarity, homology propagation or a KG inference. | HMDB `status ∈ {predicted, expected}`; CARD's meta-models; MiMeDB's BLAST-propagated layer; Reactome `IEA`. |
| `text-mined` | Asserted by an NLP or co-occurrence pipeline; no curator read the paper. | No current source emits it. Reserved so a SemMedDB-class source can never land as anything else. |
| `unknown` | The source records no design, host or assay a level can be derived from. **Never defaulted to observational.** | BugSigDB rows with no `Study design` (8 signatures, 17 edges); KEGG links; HMDB disease associations. |
| `observational-unspecified` | A human observational differential-abundance result whose assay is not recorded. | An observational design with `Sequencing type` absent or outside the known set. |
| `observational-targeted` | Observational, measured by a targeted assay rather than a community survey. | `Sequencing type = PCR`; gutMDisorder qPCR / RT-qPCR / PCR / DGGE. |
| `observational-amplicon` | Observational, non-16S amplicon. | `Sequencing type ∈ {ITS / ITS2, 18S}`. |
| `observational-16S` | Observational, 16S amplicon — the modal value, and genus-resolution at best. | `Sequencing type = 16S`; gutMDisorder `16S rRNA/rDNA sequences`. |
| `observational-shotgun` | Observational, whole-metagenome shotgun; the only observational rung that supports a species-level claim. | `Sequencing type = WMS`; gutMDisorder "quantitative metagenomics by shotgun sequencing". |
| `meta-analysis` | A synthesis over several cohorts, curated as one record. | `Study design = meta-analysis`. |
| `in-vitro` | Measured in culture: growth, a metabolite assay, an MIC over controls, or a gene→product step shown by knockout or expression. | `Study design = laboratory experiment` with no live host named; CARD's curated models; NJC19 / MASI verified events. |
| `in-vivo-model` | Demonstrated in a non-human host — any design run in an animal. A discounted tier, never causal support. | `Host species` ∉ {human, absent}, **whatever the design**; the whole gutMDisorder mouse workbook. |
| `interventional-rct` | A randomised controlled trial in humans, or an approved clinical use. | `Study design = randomized controlled trial` with a human host; gutMDisorder human rows whose `Research Type` names an intervention. |

**Two companions, kept separate and never folded into the level.**
`knowledge_level` and `agent_type` are Biolink's enums verbatim, pinned in
`microbiomekg.ontology` and written from a per-source table
(`SOURCE_EVIDENCE`), never defaulted — a source whose evidence model nobody has
read gets `not_provided`, which is a real, countable value. And **nothing is
stored as a score**: a derived confidence may be computed in a query from these
components, never persisted as the evidence field.

Derived in `microbiomekg.ontology.evidence_level(study_design, sequencing_type,
host_species)` for the sources whose columns fit that shape; a source with a
different evidence model brings its own derivation in
`microbiomekg/ontology/<source>.py` and maps onto the same twelve values. The
design→level table is `EVIDENCE_LEVELS`. First match wins:

1. `laboratory experiment` → `in-vitro` when no live host is named, else
   `in-vivo-model`;
2. any non-human host → `in-vivo-model`, whatever the design — *a mouse RCT is
   not human interventional evidence*;
3. `randomized controlled trial` → `interventional-rct`; `meta-analysis` →
   `meta-analysis`;
4. an observational design refined by what it sequenced →
   `observational-shotgun` / `observational-16S` / `observational-amplicon` /
   `observational-targeted` / `observational-unspecified`;
5. otherwise `unknown` — never silently "observational".

Measured over all 14,846 signatures: `observational-16S` 55.6%,
`in-vivo-model` 20.2%, `observational-shotgun` 12.2%, `interventional-rct`
5.1%, `meta-analysis` 2.3%, `observational-unspecified` 1.9%, `in-vitro` 1.2%,
`observational-amplicon` 0.7%, `observational-targeted` 0.7%, `unknown` 0.1%.

> **Gotcha, load-bearing.** BugSigDB joins multiple designs with commas, and one
> of its designs — `cross-sectional observational, not case-control` — *contains
> a comma*. A naive `split(",")` shreds 4,170 of 14,846 rows into two bogus
> atoms. `split_study_designs()` does longest-key-first substring matching
> instead; verified to reconstruct all 14,846 cells exactly.

### `REPORTED_BY` — the provenance edge

`(Taxon | UnresolvedTaxon) -[:REPORTED_BY]-> (Signature)`, 114,742 edges,
carrying `reported_name`, `reported_rank`, `original_rank`, `reported_tax_id`,
`resolution_status`, `resolution_normalized`, `resolution_note`, `direction`,
`source`. Its
`required_properties` are declared at `enforcement: error` because *we* write
them unconditionally — a violation there is a bug in this repo, not upstream
data, so it should fail the build.

Its domain is the abstract class `ReportedTaxon`, which is the one place an
abstract class earns its keep here: one declaration covers edges from two
concrete types, and `ontology_audit({by: 'domain_class'})` then splits the
result by resolved-vs-unresolved for free. (That the *range* side cannot do the
same for the association edges is the blueprint limitation above, not an
ontology one.)

**`reported_rank` and `original_rank` are two different claims and are stored
as two properties.** `reported_rank` is what the *source* said: MetaPhlAn's
prefix vocabulary, which has no `subspecies` and files one under `t__` =
strain. `original_rank` is **NCBI's** rank for the id as given, straight out of
`nodes.dmp`. Folding one into the other — which this repo did until now, with
NCBI's value overwriting MetaPhlAn's — loses a real disagreement: on the full
dump 170 mentions carry a MetaPhlAn rank that NCBI contradicts, 151 of them
`species` where NCBI says `subspecies`. A rank query should trust
`original_rank`; a question about what the source claimed needs
`reported_rank`.

**`resolution_normalized`** says the name matched only through the
authority-stripped fallback index (C4). It is a boolean rather than prose in
`resolution_note` so it can be counted. It is `false` on all 114,742 BugSigDB
edges, because BugSigDB resolves by id, and `false` for CARD too, which
carries an NCBI taxid on every model. It will vary the moment a source
arrives that names organisms in prose.

### CARD — three node types, two licences, and a weaker claim than it looks

`ResistanceGene` is keyed on the ARO accession and backed by one `card.json`
model. **`card.json` is the model authority, not `aro_index.tsv`**: they
disagree about 84 models in the same tarball (48 index-only, 36 JSON-only), the
JSON is the only file with taxids, and its accessions are unique across all
6,451 models while the index duplicates five of them. The 84 go to
`data/csv/card_model_disagreements.csv` rather than being resolved silently.
Names and `is_a` parents come from `card-ontology/aro.obo`, which covers every
model term and every category and is the redistributable half; `gene_family`
stays a property because nothing joins to it, while `DrugClass` is a node
because it is the other end of D7's question.

**The licence is per edge.** `card-data/` is © McMaster and non-commercial,
`aro.obo` is CC BY 4.0, and the difference is real rather than bureaucratic:
`aro.obo` names all 6,451 model terms, so every node fact is `CC-BY-4.0`, but
6,414 of 6,451 models get their drug class only from `card.json`'s
`ARO_category` — so **D7's answer lives in the non-redistributable half whatever
Part D's "prefer the CC BY 4.0 half" advises**. Saying that per edge is what
lets the graph ship in parts; `WHERE r.source_licence = 'CC-BY-4.0'` is the
shippable subgraph.

**`CARRIES_RESISTANCE_GENE` does not say the organism is resistant.** Its taxid
is the *reference sequence's* organism, and three properties say so on every
edge: `sequence_derived` (always true), `taxon_scope`
(`reference-sequence-organism`) and `taxon_specificity`, which is
`species-or-below`, `above-species` (132 models carry taxid 2, Bacteria) or
`not-an-organism` (17 taxids are plasmids, a transposon, `synthetic construct`
or a metagenome — and NCBI ranks a plasmid `species`, so only the lineage can
tell). CARD's own `NCBI_taxonomy_name` is never used as a label: on all 132
taxid-2 models it is the curation string *"Bacteria, Viruses, Fungi, and other
genome sequence associated with antimicrobial resistance"* — the same renaming
`ncbi_taxonomy.obo` is warned about, leaking into `card.json` itself. It
survives on the edge as `reported_name`, because that is what the source said.

**The contract on these three edges is eight properties, not the shared
fourteen.** `direction`, `sequencing_type`, `statistical_test` and the two group
sizes describe a differential-abundance observation; a resistance model is not
one, and declaring them would report a permanent 100% violation — a gate that
cannot go green measures as little as one that cannot go red. What is declared
is `evidence_level`, `pmid` and the six provenance fields, so the audit's number
means something: it is the share of edges whose determinant has no citation
(3,717 of 6,451 model terms have no `PMID.tsv` row). `evidence_level` is
`in-vitro` for a curated model — CARD admits a determinant only with "clear
experimental evidence of elevated minimum inhibitory concentration (MIC) over
controls" — and `computational-predicted` for the 36 meta-models that have no
reference sequence, which is what makes D7's predicted layer excludable with one
`WHERE`.

**Two things the extraction table asked for that the data cannot give.** There
is no `hit_category`: RGI's Perfect/Strict/Loose is produced by *running* RGI
against a sample and appears in no CARD download, so D7's `c.hit_category` is
unanswerable from this source and is not written as an empty column pretending
otherwise. And `publications` is a `" | "`-joined string rather than a list,
because a CSV column cannot carry a list property (§8 item 1); `pmid` holds the
first of them so the contract's integer column is filled, and it is *a*
citation for the determinant, not a claim to be the principal one.

---

### HMDB — `PRODUCES`, and the organism strings that carry it

**`PRODUCES` runs from a `Taxon` to a `Metabolite` and there are 224 records
behind the whole relationship.** HMDB names the organism as free text at two
levels under `Disposition/Source/Biological/Microbe` with **no taxid anywhere**,
so every edge is a name resolved through `microbiomekg.reconcile` and the
source's string survives as `reported_name`. Origin is matched as a **path
prefix**, never as a term substring: `grep microb|bacter|fung` over the ontology
returns 519 metabolites and 233 of them are
`Role/Industrial application/Household products/Antimicrobial agent` — drugs
that kill microbes, the opposite of the relation being loaded.

**HMDB's "genus" level is not a rank, and one of its strings resolves to
something false.** It holds genera, phyla, a class, six families, an order, two
Gram stains, a community (`Human gut microbiota`) and a U+FB01 ligature typo. A
term resolving broader than a **family** gets no edge — `PRODUCTION_RANK_CEILING`
— and the reason is not vagueness: NCBI files the exact string `Firmicutes` as a
**synonym of 1783272 `Bacillati`, a kingdom** (the 2024 nomenclature change),
while the phylum a reader means, 1239 `Bacillota`, carries `firmicutes` only as
a blast name, which `NAME_CLASSES` excludes. A verbatim load does not write a
coarse edge there, it writes a wrong one. G5's split is kept: `reported_rank` is
HMDB's own level (`genus-level term` / `species-level term`, and the point is
that neither *is* a rank) and `original_rank` is NCBI's, so the mixing is one
`WHERE` clause away. Everything refused lands in
`data/csv/unresolved_production.csv` **with the id and rank it did reach**, so
the ceiling is reversible rather than a drop.

**A species term suppresses its own genus only when the species resolved.**
A metabolite listing `Microbe/Escherichia` and
`Microbe/Escherichia/Escherichia coli` makes one claim at two levels of detail;
emitting both doubles its evidence. But a plain "keep the leaf" rule loses the
claim entirely wherever the one species under a genus is one of HMDB's
misspellings (`Akkermansia muciniphilia`, `Citrobacter frundii`), so the genus
is kept when its species failed. Two terms of one metabolite that reach the
*same* taxon are likewise one annotation spelled twice — the ligature typo sits
beside its correctly spelled sibling and `str.casefold` folds U+FB01 to `fi`, so
both resolve to 1678 — and the loser is filed with its reason.

**The contract is nine properties, not the shared fourteen**, for CARD's
reason: `direction`, `sequencing_type` and the two group sizes describe a
differential-abundance observation and a production claim is not one. What is
declared is `evidence_level`, `hmdb_status`, `reported_name` and the six
provenance fields — every one written by this loader rather than read from
upstream, so the rule sits at zero and *can* move. `knowledge_level` is
`knowledge_assertion` on all 224 and `agent_type` is `manual_agent`: the
annotation is a person's entry in a hand-built tree whatever the compound's
detection status. What the status changes is `evidence_level` — `in-vitro` where
the metabolite is `detected`/`quantified`, `computational-predicted` otherwise.
Those answer different questions and Part B keeps them in different columns;
folding them would make `prediction` mean "nobody has run the assay yet".
`publications` is a `|`-joined PMID list capped at 25 with `n_publications`
beside it, and HMDB mints **no `Paper` node**: its references are free-text
citation strings, so a minted node would have no title, which is what
`paper.csv` is keyed and BM25-indexed on.

### Reactome and KEGG — a DAG, an evidence code, and a build flag

**`IN_PATHWAY` joins on ChEBI and nothing else.** Reactome's compound file is
3,260 ChEBI ids; HMDB carries 13,562; 1,114 are in both, and that intersection
is the bridge. A ChEBI id no HMDB record carries reaches no edge — the mapping
files carry no compound name, so a minted `Metabolite` would be a bare CURIE —
and lands in `data/csv/unresolved_pathway_links.csv` instead.

**`evidence_code` is the cleanest `knowledge_level` signal in the increment and
it is 100% filled.** `TAS` (a curator read a paper) →
`knowledge_assertion`/`manual_agent`/`ECO:0000304` with `evidence_level`
**`unknown`**, because Part B's ladder describes an abundance observation and a
pathway membership is not one. `IEA` (orthology projection from human) →
`logical_entailment`/`automated_agent`/`ECO:0000501` and
`computational-predicted`. **87.7% of `ChEBI2Reactome.txt` is `IEA`**, and
without that on the edge nothing distinguishes a curated membership from a
propagated one.

**`PART_OF_PATHWAY` is a DAG.** 388 of 23,188 children have more than one
parent, so no `cardinality` cap is declared; `ancestry`, not `transitive`, for
the same reason `HAS_PARENT` is. `ChEBI2Reactome_All_Levels.txt` is not loaded —
it is the same 3,260 compounds propagated up this hierarchy, 307,049 rows
carrying the information of 113,779. `NCBI2Reactome.txt` is not loaded either:
those are NCBI **Gene** ids, and reading 73,767 of them as taxids would wire
that many imaginary organisms into a 16-species pathway set.

**What a pathway hit does not say.** Reactome's 23,603 pathways span 16 species
and every one is a model organism — not a single gut commensal. So
`(Taxon)-[:PRODUCES]->(Metabolite)-[:IN_PATHWAY]->(Pathway)` says the
*metabolite* takes part in a human pathway, never that the taxon runs it. D13
labels its rows `capability, not production` for that reason.

**KEGG is behind `scripts/build.py --with-kegg`, off by default.** KEGG is not a
public database, so a graph carrying it cannot be published; every KEGG row
carries `source_licence = 'KEGG-restricted'` and `evidence_level = 'unknown'`
(KEGG ships no per-link evidence field, and inventing one would make it
indistinguishable from Reactome's real code in a query).
`microbiomekg/ontology/kegg.py` declares **no class and no relationship** —
KEGG writes rows into Reactome's `Pathway` and `IN_PATHWAY` — which is what
makes the gate cheap: composing its fragment into a build that did not run the
prep costs nothing, no node type loaded empty and no audit rule at `0 / 0`. The
metabolite selection rule deliberately never consults KEGG, so the flag's blast
radius is exactly the licence boundary: `KEGG:map…` nodes and their edges, and
nothing else. `conv/compound/pubchem` is not loaded at all — it returns PubChem
**Substance** ids where HMDB's `pubchem_compound_id` is a **Compound** id, and
`C00001` (water) → `pubchem:3303` would look entirely plausible next to water's
real CID of 962. There are no taxon–pathway edges from KEGG and there cannot be:
`/list/organism` was retired upstream and the roster that replaced it lost the
lineage column.

---

### ChEMBL — one drug, whatever salt it was curated as

**6,030 `Drug` nodes, 1,518 `ProteinTarget` nodes, 6,984 `HAS_MECHANISM`
edges, 1,493 `OF_ORGANISM` edges, 15 `IS_DRUG` edges.** Three JSONL files, CC
BY-SA 3.0 — the only copyleft source in the graph, which is why
`source_licence` and `chembl_release` (`ChEMBL 37`) ride on every ChEMBL node
and edge rather than living only in `docs/sources.md`: a per-edge licence is
what lets the rest of the graph be redistributed on its own terms.

**`Drug` is keyed on the *parent* molecule.** 1,626 mechanism rows name a salt
rather than the free base, and 1,105 of the 4,225 approved molecules *are* a
salt of another one in the same file. Keyed on `molecule_chembl_id`, metformin
and metformin hydrochloride are two nodes with half the mechanisms each and
nothing says so. The parent comes from `mechanism.parent_molecule_chembl_id`,
which is 100% filled — the molecule file carries no `molecule_hierarchy` field
at all, so a molecule no mechanism names has no parent evidence anywhere in the
fetched subset and keeps its own id. The salt id the row actually carried stays
on the edge as `reported_molecule_chembl_id`, and the collapsed ids stay on the
node as `salt_ids`, so the normalisation is reversible. `Drug.salt_form` marks
a node whose *properties* had to be read from a salt record because the parent
has none: **0 on ChEMBL 37**, and implemented anyway because it stops being 0
the day a release ships a salt whose parent is not approved.

**Both halves of the molecule set load, and `approved` says which is which.**
`mechanism.jsonl` names 5,954 molecules and the max_phase-4 file holds 3,025 of
them. Filtering the mechanisms to the molecules file drops 49% of them
silently; loading them against nothing mints nameless drugs indistinguishable
from approved ones. `source-formats.md` §6 asks for an explicit decision rather
than half of each, and this is it: 3,120 nodes with a `pref_name`, an ATC code
and an approval year, and 2,910 with `approved = false`, no name and their
mechanisms intact.

**`ProteinTarget.tax_id` is the only field in ChEMBL that touches a microbe.**
It is on 98.4% of targets, resolves through `microbiomekg.reconcile` like every
other source's organism, and yields 1,493 `OF_ORGANISM` edges over 94 taxa
(125 source taxids, promoted to the species ceiling; **every one live in
`nodes.dmp`** — the cleanest taxid set of any source here). 865 mechanism edges
land on a non-human target, and 95 drugs — 65 of them approved — reach a
protein of one of 28 bacteria. **That is the half of D8 that exists**: "which
drugs act on a
bacterial protein" is answerable now; "which gut bacteria does this drug
inhibit" still needs MASI, because ChEMBL carries no drug↔taxon edge at all.
D8 and D18 therefore stay `pending-source: MASI`, and
`tests/test_acceptance.py` asserts that no `Drug`–`Taxon` edge exists, so the
gap cannot close by accident.

A target whose taxid the loaded taxonomy does not carry is a **ledger row, not
an edge**: the junction loader vivifies a stub node for a missing endpoint
(§8), so writing one through would grow `Taxon` nodes whose only name is their
own id.

**`HAS_MECHANISM` carries seven required properties, not the fourteen-field
contract.** Eight of those fourteen describe a differential-abundance
observation — direction, group sizes, sequencing type, statistical test — and a
drug–protein mechanism has none of them. Requiring them would report ~100%
violations meaning "this is not an abundance study" rather than "this evidence
is missing", and an audit row that always reads 100% is one nobody looks at
again. What is required is the §5(b) provenance set plus `evidence_level`, all
written by our prep unconditionally — so the rule is declared at **`error`**,
where a violation is a regression here rather than a gap upstream. The upstream
gaps stay countable elsewhere: 577 mechanisms with no target and 25 targets
with no `tax_id` are ledger rows in `unresolved_chembl.csv`, and the 42
reference-less rows land in `evidence_level = 'unknown'`.

**Three evidence levels, from a source with no study design.** `max_phase = 4`
**and** a regulatory reference (DailyMed/FDA/EMA/PMDA/HMA/BNF) is
`interventional-rct` — an approved label is a regulator's finding that the
mechanism supports an approved indication. References that are *all* literature
(PubMed/PMC/DOI) are `in-vitro`. Everything else is `unknown`. Measured:
`in-vitro` 3,153, `interventional-rct` 2,059, `unknown` 1,772. Never
`computational-predicted` — nothing in this subset is predicted. "All", not
"any": one Wikipedia entry in the reference set means the mechanism is not
carried by papers alone, which moves 1,070 edges from `in-vitro` to `unknown`
and is the conservative direction.

**`IS_DRUG` is a name match, because the id route does not exist.** The
intended join was the DrugBank id gutMDisorder puts on 35 of its 222
`Intervention` nodes — but the fetched molecule JSONL carries **no**
cross-references at all (the REST pull's `only=` kept 13 of 34 fields), so
there is no DrugBank, ChEBI or PubChem id on the ChEMBL side to join to. The
link is therefore an **exact, casefolded, whole-label** match against ChEMBL's
`pref_name` (a salt's name resolves onto its parent's node), and it is thin on
purpose: **15 of 222**. Every miss is a row in `unresolved_chembl.csv` naming
the drugs it would have reached — `Acetylsalicylic acid` is ASPIRIN to ChEMBL,
and `Clarithromycin,Metronidazole` is one cell naming two molecules — because
accepting either would invent an intervention gutMDisorder never curated.

> **The link needed a prep-order hook, and that is now what orders the build.**
> `intervention.csv` is gutMDisorder's, and `scripts/build.py` used to run the
> prep scripts in **name** order, which puts `prep_chembl.py` first — so a
> single-pass build found no table, loaded `IS_DRUG` with **zero** edges, and
> reported `IS_DRUG.required_properties` as 0 of 0: a rule that cannot fail.
> Each prep now declares `DEPENDS_ON` (`prep_chembl` names `gutmdisorder`,
> `prep_taxonomy` names every source that writes `cited_taxa.csv`) and
> `build.py` topologically sorts them. A consumer that re-derived another
> source's node ids from its raw input would dangle silently instead, and a
> dangling junction endpoint is vivified rather than refused.

Two statements in `docs/research/source-formats.md`'s ChEMBL extraction table
did not survive contact and are corrected here rather than there:
`(ProteinTarget)-[:IN_ORGANISM]->(Taxon)` is spelled `OF_ORGANISM` in the
built graph, and the evidence values it names (`interventional_clinical`,
`in_vitro`, `computational_predicted`) are the underscore spellings Part B
maps onto the hyphenated vocabulary on write. Its claim that **one** PubMed
reference carries a URL is two — and both sit on mechanisms with no target, so
no edge is affected either way.

## 3. Taxon reconciliation

Implemented in `microbiomekg/reconcile.py` (`TaxonomyIndex`, `Resolution`), not
in the prep scripts, so every source routes through one policy.

**NCBI `tax_id` is the canonical key.** Nothing else. Names are lookup keys.

1. **An explicit id beats a name.** BugSigDB *does* carry NCBI ids (column
   `NCBI Taxonomy IDs`), so it resolves by id and the name is only a label.
   **CARD carries one too** — `model_sequences.sequence.*.NCBI_taxonomy`,
   on 6,415 of its 6,451 models — so it also resolves by id, and its own
   `NCBI_taxonomy_name` is never looked up (on 132 models it is a curation
   string, not a taxon name). Disbiome will resolve by name.
2. **`merged.dmp` remap**, chased transitively. Measured: **413 of 115,634
   BugSigDB taxon mentions point at an id NCBI has since merged.** Without the
   remap those become 413 dangling or duplicate taxa.
3. **Rank promotion, against an enumerated rank set — not a rank ladder.**
   `rank_ceiling` defaults to `species`, and "more specific than species" is
   answered by `BELOW_SPECIES_RANKS`, a set **enumerated from the real
   `nodes.dmp`** rather than inferred from an ordering: of 2,993,228 nodes,
   290,597 sit strictly below a species and they carry exactly 15 rank
   strings — `no rank` 190,787, `strain` 49,211, `subspecies` 35,704,
   `varietas` 10,933, `isolate` 1,322, `forma specialis` 859, `forma` 779,
   `serotype` 573, `clade` 207, `serogroup` 164, `genotype` 22, `biotype` 18,
   `morph` 11, `pathogroup` 6, `subvariety` 1. A hand-kept ladder is a claim
   about a file; this is a reading of it. (`RANK_LADDER` survives as the
   fallback for a non-`species` ceiling, and is documented as the weaker
   claim.) Promotion keeps the original id in `reported_tax_id` and the walk in
   `resolution_note`. Measured: 163 promotions.

   **Two of those 15 ranks are ambiguous and the lineage has to place them.**
   `no rank` and `clade` also occur *above* species (75,020 and 729 nodes), so
   the rank string alone cannot decide; `below_ceiling()` returns `None` there
   and the nearest *unambiguous* ancestor decides. The test is **at or below**
   the ceiling, not below it: 83334 `Escherichia coli O157:H7` is `no rank`
   with parent 562, a species — the ancestor that places it sits *at* the
   ceiling. Reading that as "not below" leaves every serovar, pathovar and
   O-antigen standing as its own species-level node. The other direction is
   the older trap: `Enterobacteriaceae incertae sedis` (`no rank`, parent a
   family) must **not** be "promoted" to its family, or a real intermediate
   node vanishes.
3b. **`original_rank` is NCBI's rank, always.** `Resolution.original_rank` is
   read from `nodes.dmp` for the id as given, and it is never overwritten by a
   source's own rank claim. See §2 for the two-property split on the edge.
4. **Name lookup** is case-insensitive over the name classes
   `scientific name`, `synonym`, `equivalent name`, `genbank synonym`,
   `includes`. `authority` and `in-part` are excluded — the first is a citation
   string, the second is explicitly *not* a name for the taxon it is filed
   under. `common name` is excluded by the same rule, which is why `E. coli`
   does not resolve.
4b. **Authority stripping, as a fallback only.** NCBI keeps some legacy
   binomials *only* in decorated form, and one of them is the most-cited
   renamed organism in the field:

   ```
   1496 | Clostridioides difficile                                        | scientific name
   1496 | Clostridium difficile (Hall and O'Toole 1935) Prevot 1938 …     | synonym
   ```

   There is no bare `Clostridium difficile` row anywhere in `names.dmp`, so a
   literal lookup of the name every paper prints returns nothing. Same for
   *Lactobacillus plantarum*, *Lactobacillus reuteri* and *Eubacterium rectale*.
   `strip_authority()` builds a second index keyed on the bare name, consulted
   **only after the exact index misses**, so `Escherichia coli K-12` still
   resolves to its own taxon rather than collapsing onto *E. coli*. The rule
   cuts at the first `(` or four-digit year and leaves a string with neither
   untouched — which is what keeps it from manufacturing hits for
   `Clostridium symbiosum` (bracket marker) or `Cibiobacter qucibialis`
   (`Candidatus` marker). A normalised match sets `Resolution.normalized` and
   records the decorated spelling it matched in `note` — the boolean so it can
   be *counted*, the prose so it can be read.
5. **Ambiguity is never guessed.** A name matching more than one taxon returns
   `status="ambiguous"`, `tax_id=None`, and the full candidate tuple. The dump
   has 1,992 ambiguous name keys (`bacteria`, `paracoccus`,
   `bacteroides corrodens`, …). Picking the first would be a silent wrong
   answer; returning candidates lets the caller disambiguate with context this
   module does not have.
6. **Nothing is dropped.** Anything with `tax_id is None` — `ambiguous`,
   `deleted`, `unresolved` — becomes an `UnresolvedTaxon` node with the raw
   string, the status, the candidates and the note, wired to its signatures by
   the same `REPORTED_BY` edge a resolved taxon uses, and written to
   `data/csv/unresolved_taxa.csv`. Measured: 1 such node — NCBI **deleted**
   `3120442` (*Staphylococcales*), still cited by 16 BugSigDB signatures. That
   one node is the whole argument for the policy: a silent drop would have
   removed 16 real observations and left no trace.

7. **"Resolved" and "actionable" are two different questions, so they are two
   fields.** `Resolution.placeholder` is true when the taxon the resolution
   landed on carries an NCBI placeholder name: `uncultured`, `unclassified`,
   `unidentified`, `environmental sample`, a ` sp.`/` spp.` epithet, a
   `Candidatus ` prefix, or the `[` of a bracketed misapplied genus. Status
   stays `exact` — 77133 *is* a real tax_id with 13 real signatures — and the
   flag rides onto the `Taxon` node so a Part D query excludes them with
   `WHERE NOT t.placeholder` instead of string-matching the name, which is the
   string-matching this document argues against everywhere else.

   Measured at microbial scope: **572,636 of 864,099 taxa (66%) are
   placeholders**, 520,358 of them carrying an ` sp.` epithet — that is what
   NCBI's bacterial taxonomy mostly *is*. Of the 8,078 taxa BugSigDB cites,
   1,936 (24%) are placeholders, and 6,550 of the 105,097 disease associations
   (6.2%) rest on one. The marker set is a floor, not a ceiling: names like
   `Gammaproteobacteria bacterium SCGC AG-485_A06` are placeholders by any
   reading and are not flagged, because widening the rule past NCBI's own
   markers would be guessing.

`Resolution.status` ∈ `exact` | `synonym` | `merged` | `promoted` |
`ambiguous` | `deleted` | `unresolved`. `resolve()` never raises, and never
returns a `tax_id` for the last three. `placeholder` and `normalized` are
**orthogonal booleans**, deliberately not extra statuses: collapsing them into
the enum would lose the difference between "77133 is a real id" and "the name
matched nothing".

Measured over BugSigDB: `exact` 115,042, `merged` 413, `promoted` 163,
`deleted` 16 (of 115,634 mentions), collapsing to 8,078 distinct taxa.

---

## 4. The ontology declaration

`microbiomekg.ontology.ONTOLOGY`, written to `ontology.json`, referenced by
`blueprint.json`'s top-level `"ontology"` key so the declarations become a
build-time gate. It is **composed, not authored**: `microbiomekg/ontology/` is
a package holding the evidence vocabulary (`vocabulary.py`), the shared spine
every source writes into (`core.py`), and one module per source exporting
`CLASSES`, `RELATIONSHIPS` and `ASSOCIATION_RELATIONSHIPS`. Source modules are
discovered rather than listed, and two of them declaring the same class
differently is a `FragmentConflict`, not a silent override — see §8.

```python
ASSOCIATION_RELATIONSHIPS = (
    "ASSOCIATED_WITH", "ASSOCIATED_WITH_PHENOTYPE", "ASSOCIATED_WITH_EXPOSURE",
)

"ASSOCIATED_WITH": {
    "domain": "Taxon", "range": "Disease",
    "required_properties": EVIDENCE_CONTRACT,          # the fourteen fields
    "property_types": EVIDENCE_PROPERTY_TYPES,
    "enforcement": {"required_properties": "warn", "property_types": "error"},
},
```

**`ASSOCIATION_RELATIONSHIPS` is a declaration, replacing a heuristic.**
`tests/test_ontology.py` used to work out which relationships carried the
evidence contract by looking for one that required both a direction and a study
design. That passes for the wrong reason the moment a provenance edge happens
to carry both, and it silently covers nothing if a rename breaks the marker.
The three names are now stated, and the test asserts they are declared rather
than inferring which they are.

**Severity is split on who owns the gap**, which is the lifecycle the kglite
ontology guide prescribes:

- `warn`, permanently: the three `*.required_properties` rules on the
  association relationships (13.9% / 6.2% / 20.5%), `IN_CONDITION.required`
  (15.4%), `AT_BODY_SITE.required` (0.5%). These are
  upstream curation reality. Failing the build on BugSigDB's missing group
  sizes would only mean never building; the number belongs in the build log,
  not the exit code.
- `error`: `REPORTED_BY.required_properties`, every `property_types` check,
  `PART_OF_STUDY.required`/`cardinality`, `PUBLISHED_AS.cardinality`. These are
  things *our* prep guarantees, so a violation is a regression here and should
  stop the build. All measure 0.

**`IN_CONDITION.required` counts something narrower than it used to, and its
description says so.** With three condition relationships, "the signature names
some condition" is a disjunction over three, and the ontology cannot express
"at least one of these relationships" (`exempt` covers only
`required_properties` and `property_types`). Declaring `required` on all three
would report ~99% violations on the two narrow ones; declaring it on none would
drop the gate. It is declared on `IN_CONDITION` alone and reads as **signatures
with no disease-coded condition** — 2,292 of 14,846 (15.4%), up from the 200
(1.3%) that had no condition of any kind. The 200 is still measured: the prep
script prints it as the `empty` condition-pairing method.

**`ancestry: True` on `HAS_PARENT`, never `transitive: True`.** They are
mutually exclusive and mean different things: `transitive` is a promise that the
closure is *stored*, and it enrolls `transitivity_violation`, which flags every
`a→b→c` with no stored `a→c`. We store parent pointers only, so `transitive`
would report ~100% violations on a perfectly correct taxonomy. `ancestry`
records that the chain is meaningful and is walked with `*1..`, and enrolls no
check — exactly the parent-pointer shape. (The 512-class cap says the same thing
from the other side: a 3M-node taxonomy is *data*, not classes.)

Classes are kept minimal and only `ReportedTaxon` is abstract, because it is
the only place an abstract class buys a union endpoint that the *blueprint* can
also load (§2 — the range side wanted the same trick and could not have it).
A concrete class naming no live node type is a returned warning, so **classes
land with their data**: `Metabolite` and `Pathway` are declared because HMDB
and Reactome load rows for them, and a source whose raw input is absent is left
out of the composed document entirely (`ontology_for(sources)`) rather than
declaring a type the build did not fill.

Materialization (`materialize_ontology()`) is **not** used. It would stamp
`:ReportedTaxon` on 863k `Taxon` nodes to make one query shape shorter, and
`MATCH (t:Taxon|UnresolvedTaxon)` already expresses the union without a managed
label to maintain.

---

## 5. Storage: microbial scope, default (in-memory)

**Recommendation: `--scope microbial` (Bacteria + Archaea + Fungi + everything
cited), `storage="default"`.** Measured on this machine:

| Scope | Taxa | Nodes | Edges | Load | Peak RSS | `.kgl` | Sources |
|---|---|---|---|---|---|---|---|
| `cited` | 10,515 | 30,827 | 289,735 | 0.6 s | — | 4 MB | BugSigDB only |
| `microbial` | 864,099 | 930,985 | 1,234,745 | **2.3 s** | **1.38 GB** | 44 MB | all six |
| `all` | 2,993,228 | ~3.1 M | ~3.4 M | (not built) | ~4 GB est. | — | — |

The `cited` row is the increment-1 measurement and has not been rebuilt; the
`microbial` row is the shipping graph as of 2026-09-03, and its peak RSS
includes §6's five BM25 indexes.

An evidence-filtered `ASSOCIATED_WITH` scan runs in **14 ms** at microbial
scope (min of five; it was 7 ms over the two-source graph, which had 103,461
of the 105,097 association edges but a third of the nodes), and a BM25 index
over all 864,099 scientific names builds in **0.2 s** (443,091 terms). There is no memory or latency argument for `mapped` or `disk`
here, and `disk` would additionally **refuse `build_text_index()`** — the BM25
index is heap-resident by design, and text search over taxon names and
synonyms is a core feature of this graph, not a nicety. Revisit only if a later
source pushes the graph past ~10M nodes.

Loading the *whole* 3.0M-node dump buys nothing: 2.0M of the 2.9M taxa are
under Eukaryota and will never be cited by a microbiome source.

**But the clade filter must never lose a fact.** 192 of the taxa BugSigDB cites
live outside Bacteria/Archaea/Fungi (viruses, protists, host plants). Without
special handling the loader vivifies them as untitled stub nodes and says so in
a single warning nobody reads. `prep_taxonomy.py --scope microbial` therefore
unions the clade walk with `cited_taxa.csv`; verified afterwards by
`build_text_index('Taxon','scientific_name')` reporting `skipped: 0` where it
previously reported `skipped: 192`.

Every scope also includes the **full ancestor chain** of everything it selects,
so `parent_tax_id` never dangles and `-[:HAS_PARENT*1..]->` always terminates at
a domain. `root`'s self-parent is blanked; a self-loop there would make the walk
non-terminating.

---

## 6. Text search (BM25, `build_text_index`)

| Node type | Property | What it is for |
|---|---|---|
| `Taxon` | `scientific_name` | the everyday lookup |
| `Taxon` | `synonyms` | reconciliation by an old name — "Bacillus coli" → *Escherichia coli* |
| `Disease` | `label` | condition free text, since the key is a MONDO or EFO CURIE and few users know either |
| `Signature` | `description` | the curator's sentence: "genus-level microbes correlating with odor intensity" |
| `Paper` | `title` | literature entry point |

Not indexed: `Study.title` (identical to `Paper.title`), `BodySite.label` (237
values, an exact match is better), any numeric or CURIE field.

`Taxon.synonyms` is a `" | "`-joined **string**, capped at 20 names per taxon
(68 taxa hit the cap at microbial scope). It is not a list property — see §8.
**A synonym lookup should say which rank it wants.** BM25 scores a short
document higher, and a strain's synonym string repeats its species binomial in
fewer words, so `text_bm25(t, 'synonyms', 'Lactobacillus reuteri')` returns
three *strains* before it reaches species 1598 (Part D, D12).

Index sizes at microbial scope with all six sources: `Taxon.scientific_name`
864,099 documents / 443,091 terms; `Taxon.synonyms` 103,174 / 98,652 (760,925
taxa have no synonym at all, so BM25 skips them — an absent property is not an
empty document); `Signature.description` 14,425 / 6,383 (421 signatures have no
description); `Disease.label` 808 / 952; `Paper.title` 2,486 / 4,372. All five
build in well under a second, and `scripts/build.py` builds exactly this list. `Phenotype.label` (62) and
`Exposure.label` (43) are not indexed — at that size an exact match beats BM25.

---

## 7. Demo queries

All eight run against the built graph.

**Q1 — taxon → disease with an evidence filter.** The query the whole model
exists for: only shotgun or RCT evidence, both arms ≥ 30 subjects, a citation
present.

```cypher
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease)
WHERE r.evidence_level IN ['observational-shotgun', 'interventional-rct']
  AND r.group_0_size >= 30 AND r.group_1_size >= 30
  AND r.direction = 'increased' AND r.pmid IS NOT NULL
RETURN d.title AS disease, t.title AS taxon,
       count(r) AS n_signatures, count(DISTINCT r.study_id) AS n_studies
ORDER BY n_studies DESC, n_signatures DESC LIMIT 10
```

Top row: *Peptostreptococcus stomatis* ↑ in colorectal cancer, 17 signatures
across 8 studies — followed by *Parvimonas micra* and *Fusobacterium
nucleatum*, which is the textbook CRC result and a good sanity check that the
pipeline is not scrambling anything.

**Q2 — biomarker signature for one condition.**

```cypher
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease {condition_id: 'MONDO:0011122'})
WHERE NOT t.placeholder
RETURN t.title AS taxon, t.rank AS rank, r.direction AS direction,
       count(DISTINCT r.study_id) AS studies,
       collect(DISTINCT r.evidence_level) AS levels
ORDER BY studies DESC LIMIT 20
```

**Q3 — the ancestry walk: everything under a genus, with its evidence.** This is
what `ancestry: True` documents.

```cypher
MATCH (g:Taxon {title: 'Bacteroides'})<-[:HAS_PARENT*1..]-(t:Taxon)
MATCH (t)-[r:ASSOCIATED_WITH]->(d:Disease)
WHERE r.evidence_level STARTS WITH 'observational'
RETURN t.title AS taxon, d.title AS disease, r.direction, r.pmid
ORDER BY taxon
```

**Q4 — shortestPath between a taxon and a disease.**

```cypher
MATCH p = shortestPath((t:Taxon {id: 853})-[*..4]-(d:Disease {condition_id: 'MONDO:0011122'}))
RETURN length(p) AS hops, [n IN nodes(p) | labels(n)[0]] AS types
```

Returns 1 hop when a direct association exists — the flattened edge is doing its
job. For the *evidence* path rather than the shortcut, ask for it explicitly:

```cypher
MATCH p = (t:Taxon {id: 853})-[:REPORTED_BY]->(s:Signature)-[:IN_CONDITION]->(d:Disease)
RETURN s.title, s.evidence_level, s.group_0_size, s.group_1_size LIMIT 5
```

**Q5 — per-field evidence completeness**, the breakdown the audit's single
percentage rolls up:

```cypher
MATCH (:Taxon)-[r:ASSOCIATED_WITH]->(:Disease)
RETURN count(r) AS edges,
       sum(CASE WHEN r.direction       IS NULL THEN 1 ELSE 0 END) AS no_direction,
       sum(CASE WHEN r.pmid            IS NULL THEN 1 ELSE 0 END) AS no_pmid,
       sum(CASE WHEN r.group_0_size    IS NULL THEN 1 ELSE 0 END) AS no_group0,
       sum(CASE WHEN r.statistical_test IS NULL THEN 1 ELSE 0 END) AS no_stat
```

→ `105097, 894, 1051, 13509, 1292`. Swap `ASSOCIATED_WITH` for the three-way
alternation to census every association type at once.

**Q6 — resolve an obsolete name through the synonym index.**

```cypher
MATCH (t:Taxon) WHERE text_bm25(t, 'synonyms', 'Bacillus coli') > 0
RETURN t.title, t.rank, text_bm25(t, 'synonyms', 'Bacillus coli') AS score
ORDER BY score DESC LIMIT 3
```

→ *Escherichia coli* (7.27) at the top; the next two hits are one of its own
strains (6.84) and an unrelated *Bacillus* (6.69), so the margin is real but
narrow — which is why D12 filters on rank.

**Q7 — what failed to reconcile, and what it cost.**

```cypher
MATCH (u:UnresolvedTaxon)-[:REPORTED_BY]->(s:Signature)
RETURN u.title AS raw_name, u.status, u.note, count(s) AS signatures
```

→ `Staphylococcales | deleted | 3120442 listed in delnodes.dmp | 16`

**Q8 — the ontology audit.** The project's headline metric.

```cypher
CALL ontology_audit() YIELD rule, severity, violations, exempted, total, pct
RETURN rule, severity, violations, total, pct ORDER BY pct DESC
```

```
ABUNDANCE_CHANGED_BY.required_properties      warn    1380 / 1380    100.00%
CONFERS_RESISTANCE_TO.required_properties     warn    8052 / 13691    58.80%
CARRIES_RESISTANCE_GENE.required_properties   warn    3717 / 6415     57.90%
VIA_MECHANISM.required_properties             warn    3717 / 6513     57.10%
ASSOCIATED_WITH_EXPOSURE.required_properties  warn     485 / 2369     20.50%
IN_CONDITION.required                         warn    2292 / 14846    15.40%
ASSOCIATED_WITH.required_properties           warn   15985 / 105097   15.20%
ASSOCIATED_WITH_PHENOTYPE.required_properties warn     293 / 4717      6.20%
AT_BODY_SITE.required                         warn      78 / 14846     0.50%
ASSOCIATED_WITH.property_types                error       0 / 105097    0.00%
REPORTED_BY.required_properties               error       0 / 114742    0.00%
IS_DRUG.required_properties                   error       0 / 15        0.00%
… 76 rules total, 45 of them at 0 violations
```

The four rules above `ASSOCIATED_WITH` are what a new source looks like when
its columns do not cover this graph's contract, not a regression:
gutMDisorder records no study design and no per-association arm sizes, and
CARD's carriage and drug-class edges carry no group sizes or statistical test
because there are none to carry. The number to watch is the *denominator* —
`IS_DRUG.required_properties` read 0 / 0 for a whole release while the
relationship silently loaded nothing (§8).

Drill down to individual edges with
`CALL edge_property_violation() YIELD relationship, check, source, target, property`,
and split by source type with `CALL ontology_audit({by: 'domain_class'})`.

---

## 8. Building it, and what the blueprint could not express

```bash
uv venv .venv && uv pip install --python .venv/bin/python pandas openpyxl kglite

.venv/bin/python scripts/build.py --scope microbial
```

`build.py` is the whole pipeline and the only supported entry point: it empties
`data/csv/`, runs every `scripts/prep_<source>.py` (discovered, not listed) in
**declared dependency order** — each prep names the preps whose tables it reads
in its own `DEPENDS_ON` and `build.py` topologically sorts them, so
`prep_taxonomy` runs after everything that writes `cited_taxa.csv` and
`prep_chembl` after the gutMDisorder table its `IS_DRUG` join reads — composes
`blueprint.json` from `blueprints/*.json`, writes the ontology document and a
`blueprint.load.json` **into the CSV directory** with every path bound to that
build, loads it with the chunk-size workaround below, builds §6's five BM25
indexes, prints the counts, the audit and G10's expansion factor for every
declared relationship, and saves `graph/microbiomekg.kgl`.

Three of those are answers to defects rather than choices. The **order** is
declared because name order silently loaded `IS_DRUG` with zero edges. The
load blueprint is **written beside the CSVs** because `blueprint.json`'s
`settings.root` is `./data/csv` and a build given `--csv` elsewhere loaded the
default directory and reported its numbers. And the *checked-in*
`blueprint.json` is always composed from the whole fragment set, never from the
sources one machine happened to have, because it is a tracked artifact with a
drift gate (`tests/test_fragments.py`) — a partial build rewriting it left the
repo dirty and the gate red. A source whose declared CSVs are not in `--csv` is
left out of the *load* blueprint instead, which is the same rule as the
`MISSING_INPUT` skip: a node type loaded empty gives its ontology rules a 0 / 0
denominator.

**Adding a source is adding files, never editing shared ones.** A source brings
`scripts/prep_<source>.py`, `blueprints/<source>.json`,
`microbiomekg/ontology/<source>.py` and `tests/test_<source>.py`. The blueprint
fragments and the ontology modules are composed by
`microbiomekg.fragments.merge_fragments`, whose rule is the reason for the
split: two fragments declaring the *same* thing is how a source says "I write
rows into this table too" and merges; declaring *more* is additive; declaring
the same key with a **different** value raises `FragmentConflict` naming both
fragments. A merger that let the last writer win would turn a real
disagreement about which CSV backs `Disease` into a silently different graph.
Shared *rows* work the same way: a second source's taxon–disease association is
a row in `taxon_disease.csv`, not a second relationship, because a junction
entry names one relationship, one CSV and one target type (item 5 below). That
is what `microbiomekg.tables.Writer(merge=True, owner=…)` is for.

**`KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE=1000000` is not optional, and this is
a kglite defect.** `scripts/build.py` sets it; anything loading the blueprint
by hand must too. The
blueprint junction-edge loader streams each junction CSV in 100,000-row chunks
and calls the connect path once per chunk; parallel edges are written on the
*first* call for a relationship type and **deduplicated on every call after it**.
`taxon_disease.csv` is ~103k rows of deliberately parallel edges, so a default
build silently drops every repeat of a pair it saw in the first chunk — **with
no warning and no error**. Setting the chunk size above the row count restores
the exact count (verified both ways). Worth reporting upstream: the chunk
boundary changes the *result*, not just the memory profile.

Six other things the blueprint or the ontology could not express. **These go to
the engine, not into a workaround this repo pretends is a design.**

1. **No list property from CSV.** `map_blueprint_type` accepts only
   `string`/`int`/`float`/`bool`/`date`-family plus the spatial and temporal
   virtual types. `add_nodes` turns a DataFrame column of Python lists into a
   native list property and `from_records` does the same for a JSON array, but a
   CSV column cannot. `Taxon.synonyms` is therefore a `" | "`-joined string —
   fine for BM25 and `contains()`, but `'Bacillus coli' IN t.synonyms` is not
   available. The alternative (a `TaxonName` sub-node per name) would add ~3.5M
   nodes to serve a lookup that already happens in Python at prep time.
2. **FK edges cannot carry properties** — only junction edges can. Any
   evidence-bearing edge therefore needs its own CSV even when the data is 1:1
   with a node row. That is why `taxon_disease.csv` exists as a separate file
   rather than being columns on `signature.csv`.
3. **No secondary labels.** `NodeSpec` has no `labels` field, so the ontology
   guide's advice to model multi-role nodes with secondary labels is not
   reachable from a blueprint build; the escape hatches are a post-build
   `SET n:X` or `materialize_ontology()`. This bites because `is_a` is a
   **forest** — `Taxon` can have exactly one parent class, so it cannot be both
   `ReportedTaxon` (union of things a signature names) and a future
   `Associatable` (union of things that associate with a disease). When
   `Metabolite` and `Drug` arrive with their own association edges, either the
   forest is re-rooted or the relationships get distinct names.
4. **The ontology audits edge properties only.** There is no
   `required_properties` for *node* properties, which is the single fact that
   decided §1's edge-vs-node split. And `required_properties` reports per edge,
   not per property, so a fourteen-field contract yields one percentage and the
   per-field breakdown has to be a Cypher query (Q5).
5. **One relationship cannot span a union range from a blueprint.**
   `connections.junction_edges` is a map *keyed by relationship name* inside one
   node spec, and each entry names exactly one `target` node type. So
   `ASSOCIATED_WITH` cannot be loaded from three CSVs pointing at `Disease`,
   `Phenotype` and `Exposure` — the second entry would collide on the key. The
   *ontology* can express it (abstract class + `is_a`, exactly what
   `ReportedTaxon` does on the domain side); the loader cannot. This repo
   therefore ships three relationship names for one relation, and every "any
   association" query is a three-way alternation
   (`ASSOCIATION_RELATIONSHIPS` in `microbiomekg/ontology.py`). It is the
   single largest modelling compromise in this document. What would fix it: a
   per-row target type, or an optional `relationship:` field on the junction
   entry so the map key can be a local alias.
6. **The ontology cannot say "at least one of these relationships".**
   `required: true` is per relationship, and `exempt` covers only
   `required_properties` and `property_types` (`EXEMPTABLE_CHECKS`), so there
   is no way to declare that a `Signature` must have an `IN_CONDITION` **or**
   an `IN_PHENOTYPE` **or** an `IN_EXPOSURE`. §4 explains the reading that
   keeps the gate honest instead; the metric it used to report — signatures
   with no condition of any kind — now has to come from the prep script's own
   counter. Falls away entirely if (5) is fixed.
7. **Relationship-type alternation is a syntax error inside `EXISTS { }`.**
   `MATCH (n)-[:A|B]->()` parses; `WHERE EXISTS { (n)-[:A|B]->() }` and
   `WHERE EXISTS { MATCH (n)-[:A|B]->() }` both fail with
   *"Unexpected token in EXISTS pattern: |"* (kglite 0.16.21, reproduced on a
   two-node scratch graph). Given (5) forces three relationship names, the
   natural "signatures that name no condition at all" query —
   `WHERE NOT EXISTS { (s)-[:IN_CONDITION|IN_PHENOTYPE|IN_EXPOSURE]->() }` —
   is unavailable, and has to be written as three separate `NOT EXISTS`
   clauses. This one looks like a parser gap rather than a design choice.

One more loader behaviour, recorded because it is the opposite of the usual
trap: **an undeclared CSV column is still loaded.** Every column a node spec
does not `skip` reaches the graph as a property, whether or not
`properties` names it. So a query answering is not proof that the property is
part of the contract — an undeclared column carries no declared type, is
invisible to the ontology's `property_types` check, and would vanish the day
the loader stopped being generous. `matched_on` and `confounders` lived in that
state until D11 was written; the fix was to declare them (and to extract
`antibiotics_exclusion`, which genuinely was missing).

Two upstream data traps, both silent, recorded so the next source does not
re-learn them:

- BugSigDB's two taxon columns use **different delimiters**: `MetaPhlAn taxon
  names` separates taxa with `,`, `NCBI Taxonomy IDs` separates them with `;`,
  and both use `|` between lineage ranks. Pairing them that way aligns on all
  14,225 rows that carry taxa; using the same delimiter for both misaligns
  11,273 of them — and the misalignment is *plausible*, so it would have
  attached wrong names to right ids for most of the graph.
- 4.2% of BugSigDB rows carry taxon *names* with no id column. Pairing the two
  columns positionally makes those rows produce zero taxa — the whole row
  vanishes without a warning. The name-only path resolves them by name instead,
  which is precisely what §3 exists for.
- The DOI column mixes bare DOIs, `https://doi.org/…` and DataCite URLs, and
  DOIs are case-insensitive by spec, so the same paper appears three times
  unless the value is normalised (`normalise_doi()`).
- BugSigDB writes missing values as the literal string `"NA"`. Passing that
  through would fill every evidence gap with a non-null value and drive the
  audit to 0.00% — a green gate that means nothing. `na()` in
  `prep_bugsigdb.py` maps it to an empty cell, which kglite reads as an absent
  property.

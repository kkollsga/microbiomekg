# The graph model

MicroMap's shape (taxa, diseases, metabolites, pathways, drugs, resistance,
papers) with one thing added that it does not have: **an association edge
cannot exist without saying how it was demonstrated**, and the ontology
reports what fraction of them fail that.

Everything below is built and measured, on a clean `scripts/build.py` run of
2026-09-03 carrying **eleven** sources: NCBI taxonomy + BugSigDB (increment 1),
gutMDisorder (increment 2), then CARD, HMDB, Reactome and ChEMBL, then MiMeDB,
NJC19, the two published drug screens — Maier 2018 and Zimmermann 2019, one per
direction — and MASI, the aggregator that curates the literature both of those
screens are in. KEGG is licence-gated and off by default,
so no number here includes it. A source is
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
| `Drug` | `CHEMBL:<parent molecule id>`, else `PRESTWICK:<catalogue number>`, else `ZIMMERMANN2019:<screened name>` | `pref_name` | ChEMBL `max_phase = 4` **and** every molecule a mechanism names; plus each screened compound no join route reaches | 3 |
| `ProteinTarget` | `CHEMBL:<target id>` | `pref_name` | ChEMBL; `uniprot`, `tax_id` properties | 3 |
| `ResistanceGene` | `ARO:3002999` | `name` | CARD `card.json` model, named from `aro.obo` | 3 |
| `DrugClass` | `ARO:0000032` | `label` | CARD ARO category `Drug Class` | 3 |
| `ResistanceMechanism` | `ARO:0001004` | `label` | CARD ARO category `Resistance Mechanism` | 3 |
| `Substance` | `MASI:PMDBD<n>` | `name` | MASI's own accession — a drug, a medicinal herb or its compound, a dietary compound or an environmental chemical | 4 |

**One secondary label, `Condition`, on `Disease` / `Phenotype` / `Exposure`.**
It is the abstract class `ASSOCIATED_WITH` and `IN_CONDITION` range over (§4),
stamped by the blueprint so it is also matchable: `MATCH (c:Condition)` is the
931 nodes of the three types, and `labels(n)[0]` is still the node's own type.
Nothing else carries one, and §8 item 3 says why `ReportedTaxon` deliberately
does not.

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

**Accounting.** 14,987 condition mentions in; 13,959 `IN_CONDITION` edges
(12,843 to a `Disease`, 678 to a `Phenotype`, 438 to an `Exposure`) + 1,028
ledger rows out. The two sinks sum to the input, which is C18's rule applied to
the condition column.

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
a **list** when several did, so `WHERE 'feces' IN m.selection_rule` counts the
rule rather than trusting this paragraph. `status` rides on the node for
the same reason: it is what makes "measured or predicted" a filter.

**Three sources write `Metabolite` nodes, and `source` says which.** 9,056 in
total: HMDB 7,773, MiMeDB 1,237, NJC19 46. MiMeDB's are compounds no HMDB record
holds, under their own selection rule (§"MiMeDB" below); NJC19's are the 46 of
its 283 compounds nothing else holds at all — mostly macromolecules
(`Mucin`, `Xylan`, `Arabinogalactan`) and ions and gases, which a *human
metabolome* database has no reason to carry. `microbial_origin` stays HMDB's
claim and only HMDB's: "an organism exchanges this compound" is a different
assertion from "this compound is of microbial origin", and pectin is a plant
polymer.

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
- `ASSOCIATED_WITH` (112,966 edges: 105,880 to a `Disease`, 4,717 to a
  `Phenotype`, 2,369 to an `Exposure`) carries
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
| `ASSOCIATED_WITH` | `Taxon` → `Condition` (`Disease` ∪ `Phenotype` ∪ `Exposure`) | **the evidence contract** |
| `REPORTED_BY` | `ReportedTaxon` → `Signature` | reconciliation provenance |
| `PART_OF_STUDY` | `Signature` → `Study` | — |
| `IN_CONDITION` | `Signature` → `Condition` | — |
| `AT_BODY_SITE` | `Signature` → `BodySite` | — |
| `ABUNDANCE_CHANGED_BY` | `Taxon` → `Intervention` | **the same contract** |
| `CONFERS_RESISTANCE_TO` | `ResistanceGene` → `DrugClass` | **CARD's eight-property contract** |
| `VIA_MECHANISM` | `ResistanceGene` → `ResistanceMechanism` | **the same eight** |
| `CARRIES_RESISTANCE_GENE` | `Taxon` → `ResistanceGene` | **the same eight**, plus what the taxid means |
| `PRODUCES` | `Taxon` → `Metabolite` | **the eight-property exchange contract** (HMDB and NJC19 share it) |
| `CONSUMES` | `Taxon` → `Metabolite` | **the same eight** |
| `DEGRADES` | `Taxon` → `Metabolite` | **the same eight** |
| `NO_EXCHANGE_WITH` | `Taxon` → `Metabolite` | **the same eight** — a curated *refutation* |
| `INHIBITS_GROWTH_OF` | `Drug` → `Taxon` | **a nine-property growth contract** — Maier 2018's screen hits |
| `DOES_NOT_INHIBIT_GROWTH_OF` | `Drug` → `Taxon` | **the same nine** — the same screen's *measured* non-hits |
| `METABOLISES` | `Taxon` → `Drug` | **a nine-property metabolism contract** — Zimmermann 2019's screen hits, the *other* direction |
| `DOES_NOT_METABOLISE` | `Taxon` → `Drug` | **the same nine** — that screen's *measured* non-hits |
| `METABOLISES_SUBSTANCE` | `Taxon` → `Substance` | **the same nine** — MASI's *curated* metabolism, kept off the screen's relationship |
| `DOES_NOT_METABOLISE_SUBSTANCE` | `Taxon` → `Substance` | **the same nine** — MASI's curated refutations |
| `ABUNDANCE_CHANGED_BY_SUBSTANCE` | `Taxon` → `Substance` | **the same nine**, plus `direction` — MASI's curated abundance shifts |
| `ABUNDANCE_UNCHANGED_BY_SUBSTANCE` | `Taxon` → `Substance` | **the same nine** — MASI's curated "no significant change" |
| `SAME_COMPOUND_AS` | `Substance` → `Drug` | — (the declared identity between a MASI substance and a `Drug`) |
| `IN_PATHWAY` | `Metabolite` → `Pathway` | **a seven-property pathway contract**, plus `evidence_code` |
| `PART_OF_PATHWAY` | `Pathway` → `Pathway` | — (sub-pathway pointer, `ancestry`, a **DAG**) |
| `PUBLISHED_AS` | `Study` → `Paper` | — |

**One relation, one relationship name, over a union range.** `ASSOCIATED_WITH`
runs from a `Taxon` to a `Condition` — the abstract class `Disease`, `Phenotype`
and `Exposure` are `is_a`, the way `ReportedTaxon` works on the domain side.
The blueprint expresses it directly: `taxon_condition.csv` is one junction CSV,
the entry's `target` is the list of the three types, and `target_type_column`
names the `condition_type` column that routes each row (kglite 0.16.22). The
routing column is *not* an edge property; the target node's own type is what a
query narrows on, so `-[:ASSOCIATED_WITH]->(:Disease)` is exactly the disease
subset and `-[:ASSOCIATED_WITH]->()` is every association. `IN_CONDITION` is
the same shape.

Until 0.16.22 this needed three relationship names — `ASSOCIATED_WITH`,
`ASSOCIATED_WITH_PHENOTYPE`, `ASSOCIATED_WITH_EXPOSURE`, and the same again for
`IN_CONDITION` — because a junction entry named exactly one target type. That
was the largest modelling compromise in this document (§8), and it cost more
than three names: the audit reported *three* rules, so the headline
"what fraction of associations lack evidence" covered only the disease third of
them, and `IN_CONDITION.required` could only ask "no disease-coded condition"
rather than "no condition at all".

**The four drug↔taxon relationships are four by choice, not by engine
limitation** — the opposite case, and worth stating beside it so the two are not
read as the same kind of split. They split along two independent axes and both
splits were argued before either source landed.

*Hit against measured non-hit.* Nothing stopped one relationship carrying an
`effect` property; what stops it is that a refutation stored as a property is
counted as an observation by every query that does not know to exclude it, and
nothing in the query text would say so. That is the rule `NO_EXCHANGE_WITH`
already applies to the exchange layer. `effect` rides on all four edges as well,
so a query that wants the whole measured population groups on one property
instead of unioning two labels.

*Inhibition against metabolism.* `Drug → Taxon` and `Taxon → Drug` are opposite
claims — the drug stops the bacterium growing, the bacterium chemically changes
the drug — and Part D's D8 required them to be different edge types before
either screen was fetched (`ALTERS_TAXON` and `ALTERS_SUBSTANCE`, "two edge
types, never one"), because collapsing them conflates antimicrobial killing with
drug metabolism, which is MDAD's documented weakness. The *direction* carries it
as well as the name: the agent is on the tail in both, so
`MATCH (d:Drug)-[]->(t:Taxon)` is the growth screen and nothing else, and
`tests/test_acceptance.py` asserts exactly that.

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

**Measured headline over all three sources: 15.80% of taxon–disease edges
(16,768 of 105,880) are missing at least one contract field**, plus 293 of 4,717
phenotype edges (6.21%), 485 of 2,369 exposure edges (20.46%) and **1,380 of
1,380 intervention edges (100%)**. Those are what `ontology_audit()` returns and
what the build prints, and they are the numbers the project exists to make
visible.

**The number moved when the second source landed, and again when the third
did, and that is the audit working.** BugSigDB alone measured 14,349 of 103,461
= 13.87%; gutMDisorder took it to 15.20% and MASI to 15.80%, whose 783
association edges are violations for the same reason in a third variant — its
disease export is eleven columns and not one of them is a design, a host, a
sequencing type, a statistical test or an arm size. Every one of
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
| `in-vitro` | Measured in culture: growth, a metabolite assay, an MIC over controls, or a gene→product step shown by knockout or expression. | `Study design = laboratory experiment` with no live host named; CARD's curated models; NJC19's verified events; all 47,825 Maier 2018 growth-screen edges, hits and measured non-hits alike. |
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
otherwise. And `publications` is a **list** of `PMID:` CURIEs, so
`UNWIND r.publications` is the per-citation tally; `pmid` holds the first of
them so the contract's integer column is filled, and it is *a* citation for the
determinant, not a claim to be the principal one.

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

**The contract is eight properties, not the shared fourteen**, for CARD's
reason: `direction`, `sequencing_type` and the two group sizes describe a
differential-abundance observation and a production claim is not one. What is
declared is `evidence_level`, `reported_name` and the six provenance fields —
every one written by a loader rather than read from upstream, so the rule sits
at zero and *can* move. It was **nine** until NJC19 started writing rows into
the same table: `hmdb_status` is HMDB's detection status, NJC19 has no column
that could fill it, and a required field only one author can write turns the
other author's every edge into a violation of a rule meant to read zero. It is
still declared, still type-checked, and still written on all 578 HMDB edges —
`tests/test_hmdb.py` asserts that separately, which is where a
source-specific field's guarantee belongs. `knowledge_level` is
`knowledge_assertion` on all 224 and `agent_type` is `manual_agent`: the
annotation is a person's entry in a hand-built tree whatever the compound's
detection status. What the status changes is `evidence_level` — `in-vitro` where
the metabolite is `detected`/`quantified`, `computational-predicted` otherwise.
Those answer different questions and Part B keeps them in different columns;
folding them would make `prediction` mean "nobody has run the assay yet".
`publications` is a PMID **list** capped at 25 with `n_publications` beside
it — the count is the untruncated one, so `size(r.publications)` and
`r.n_publications` disagree by design on 353 edges — and HMDB mints **no `Paper` node**: its references are free-text
citation strings, so a minted node would have no title, which is what
`paper.csv` is keyed and BM25-indexed on.

### NJC19 — the consumption edge, and the conjugate join that makes it count

**8,905 edges over 820 taxa and 241 compounds: `CONSUMES` 4,784, `PRODUCES`
2,840, `NO_EXCHANGE_WITH` 894, `DEGRADES` 387.** This is the only source in the
graph that says an organism *takes a compound up*, and D6's Metabolite Exchange
Score — **MES = 2·P·C / (P + C)** — is identically zero for every metabolite
while the consumer count is. 96 metabolites now carry both halves.

**`PRODUCES` is one relationship with two authors.** NJC19's export events go
into `taxon_metabolite.csv`, the file HMDB wrote, because a blueprint junction
entry names one relationship, one CSV and one target type (§8) — so a second
source's production claim is a *row*, not a second relationship
(`microbiomekg.tables`). `primary_source` is what tells them apart and it is on
every edge. The one thing that had to change to allow it: **`hmdb_status` left
the required contract.** It was the ninth property of `PRODUCTION_CONTRACT`,
NJC19 has no column that could fill it, and leaving it required would have made
every NJC19 edge a violation of a rule designed to read zero — an audit number
meaning "a second source landed" rather than "evidence is missing". The
remaining eight are
`microbiomekg.ontology.vocabulary.EXCHANGE_CONTRACT`, every one written by a
prep rather than read from upstream, so the rule still sits at zero and still
*can* move. `hmdb_status` stays declared and type-checked as an optional
property, and `tests/test_hmdb.py` asserts HMDB still writes it on all 578 of
its own.

**The compound side is free text with no cross-reference of any kind** — no
ChEBI, HMDB, KEGG, PubChem or InChIKey on any of the 283 compounds — so every
one is joined to an existing `Metabolite` by name, and `metabolite_join` records
the route: `exact` (131 compounds), `conjugate` (33), `synonym` (13), `stereo`
(8), `synonym-conjugate` (5), `stereo-conjugate` (4), `synonym-stereo` (1), and
`minted` (46) for what nothing holds.

**The conjugate route is the whole reason D6 has a non-zero answer.** HMDB
records `Acetic acid` and `Butyric acid`; NJC19 says `Acetate` and `Butyrate`.
Without the `-ate` ↔ `-ic acid` step the consumers land on minted nodes, the
producers stay on HMDB's, and MES is 0 for both halves of every short-chain
fatty acid in the graph — which is precisely the trap D5's "key note" already
recorded for CHEBI:17968 vs CHEBI:30772, arriving a second time from the other
side. Butyrate's producer count went from 6 to **109** because the join reaches
CHEBI:30772; had it not, 103 producers would sit on a node nobody queries.

**But the source's own spelling is tried first, so a real conjugate split
survives as two nodes.** `Formate` reaches CHEBI:15740 because the graph holds a
node with that exact name, while HMDB's 10 formate producers sit on
`Formic acid` (CHEBI:30751). Both nodes therefore carry a partial picture. That
is deliberate: ChEBI holds the acid and the base as two terms, this graph keys
`Metabolite` on ChEBI, and silently merging them would be an identity claim the
project has not made. `metabolite_join = 'exact'` is what says it happened, and
it is countable.

**912 negatives, kept as their own relationship.** `NO_EXCHANGE_WITH` rather
than a flag on the positive edge, because a refutation stored as a property is
counted as an observation by every query that does not know to exclude it — and
nothing in the query text would say so. `source_relation` names which activity
was refuted (`import-negative` 720, `degrade-negative` 87, `export-negative` 87);
894 of the 912 survive, and the 18 that do not sit on rows whose organism is a
host cell type or a taxon NCBI renamed, each a ledger row in
`unresolved_exchange.csv`.

**Three shapes the sheet's own legend defines, and all three are load-bearing.**
180 rows carry two activities and a *scoped* reference cell
(`import:415, 418;export:417`), so each direction keeps its own literature.
2,426 rows (26.6%) stand on nothing but `(G)`-marked references — a species-filed
row whose entire basis was read at genus level — and `genus_level_evidence` is
the boolean guard G5 needs. Six `Species` values are **host cell types**, not
organisms, and are excluded by name: letting them fail reconciliation writes six
`UnresolvedTaxon` tombstones, each asserting NCBI has lost a taxon, which is a
false statement about the taxonomy arrived at by doing nothing.

**The organism column is the cleanest of any source here.** 823 of 838 species
names resolve and **every one lands at rank `species`** — unlike HMDB's
mixed-rank organism strings, which is why `EXCHANGE_RANK_CEILING` (`genus`) is a
guard against a promotion surprise rather than a working filter. The 15 that do
not are nomenclatural churn, and they become tombstones.

> **The replication count is no longer 1, and both reasons are correct
> behaviour.** D5's stated required qualifier was that
> `count(DISTINCT p.source_record_id)` per (taxon, metabolite) pair is 1. It
> reaches **3** now: 43 pairs carry more than one record, because HMDB and NJC19
> independently curate the same production (29 pairs — the cross-source
> corroboration this relationship has never had before), and because several
> NJC19 species strings promote onto one NCBI species (*Thermoanaerobacter
> thermohydrosulfuricus*, *T. indiensis* and *T. ethanolicus* are three curated
> rows under one node). `reported_name` keeps every source string, so the
> collapse is inspectable; a pair carrying more records than distinct
> (source, organism string, compound string) triples *would* be double-counting,
> and `tests/test_acceptance.py` asserts none does.

### MiMeDB — a source that writes no edge, and why that is the finding

**1,237 `Metabolite` nodes and nothing else. No `PRODUCES`, no relationship of
any kind.** MiMeDB was fetched to close D5 — per-taxon metabolite production —
and no published bulk download can: they are one MySQL table each (`SELECT *
FROM metabolites`, 29,295 rows in v2.0; `SELECT * FROM microbes`, 2,648) and the
join between them is in neither. Measured on the bytes of all four v2 files:
**zero `MMDBm` ids in the metabolites dump, zero `MMDBc` ids in the microbes
dump**, CSV and XML alike, with each id appearing exactly once per row of its
*own* table — 29,295 and 2,648 times — so the zeros are a measurement and not a
mis-spelled pattern. There is no precursor, product, enzyme, reaction or
source-organism column anywhere.
`microbiomekg.ontology.mimedb.RELATIONSHIPS` is `{}` and `tests/test_mimedb.py`
asserts the zero, so an edge appearing here later is a deliberate change rather
than an accident.

**v2.0 changed the release, not the finding.** The loader reads
`data/raw/mimedb/v2/` and falls back to v1.0 beside it, and
`Metabolite.mimedb_release` says which it read — a build report is a terminal
scroll and the graph outlives it. What v2 added is 1,654 metabolite records, 474
organisms, three cross-references (`vmh_id`, and the EPA DSSTox pair
`epa_substance_id` / `epa_compound_id`) and one count. What it did not add is a
pair table.

**The count is the new fact, and it is the size of what is withheld.**
`microbe_relations` is an integer per metabolite — MiMeDB's own count of the
microbes it relates that compound to — filled on all 29,295 rows and summing to
**830,984 taxon–metabolite pairs**, naming not one of them. Those pairs exist,
they are reachable only through the site's per-metabolite web pages, and this
project does not scrape them; so D5's gap at MiMeDB is closed as a question
rather than left open. The count rides on the node as
**`mimedb_microbe_relation_count`**, deliberately not under the source's own
column name: a property called `microbe_relations` sitting on a node in a graph
with zero MiMeDB edges reads as a degree, and the whole point is that it is not
one. An absent value stays empty rather than becoming `0`, because "MiMeDB
relates this compound to no microbe" is a claim only a filled cell makes.

**`activity` is reported and loaded nowhere — not even as a `Taxon` property.**
It is the only column in either table that reads like a relation: `Production
(export)` on 113 v2 rows and `Consumption (import)` on 2, up from 45 rows in
v1.0, and **naming no compound anywhere on the row**. A `Taxon.mimedb_activity`
was considered and rejected on three counts. It is a production claim with **no
object**, and D5 is precisely the query that would read it as one — the graph
would answer "MiMeDB says this organism produces" and be unable to say what.
This source writes no `Taxon` at all, so carrying it would mean either 2,648
unconnected nodes or a property smuggled onto taxa another source owns. And the
column's vocabulary is NJC19's verbatim, while NJC19 itself is loaded here *with*
its compounds and directions — so the best case is a lossy duplicate of edges the
graph already has properly. The prep prints the two counts and the sentence "names
no compound", which is the honest form of the same information.

*(The v1 provenance note inferred this column was an import from NJC19's
predecessor because `microbes.data_source` reads `NJS16` on 63 rows. The two
sets are **disjoint** in both releases — every `activity` row has an empty
`data_source` and every `NJS16` row an empty `activity` — so the vocabulary
match is the only evidence, and it does not carry that inference.)*

The microbes table is read anyway and reported, never loaded: **2,642 of 2,648
rows carry an NCBI taxid** (the six without are fungi; v1.0's 2,174 all had one)
and resolve 1,665 exact / 964 promoted / 13 merged / 0 unresolved — the cleanest
organism column of any source profiled for this project, attached to nothing.
Quoting it is what separates "MiMeDB does not close D5" from "MiMeDB has
nothing"; loading it would add 2,648 unconnected `Taxon` nodes.

**What it contributes is compound identity for a source that has none.** NJC19's
compounds carry no cross-reference, so a compound HMDB does not hold becomes a
minted `NJC19:` stub with no InChIKey and no formula. MiMeDB's names close some
of those: `Pectin`, `Chitin`, `Inulin`, `Stachyose`, `Menaquinone` and others
reach a node with a structure. 25 of the metabolites NJC19's edges land on are
MiMeDB's, over 279 edges — and that pair of numbers is **unchanged from v1.0**,
which is itself the measurement: the `njc19-compound` rule had already selected
every compound NJC19 needed, so v2's extra records widened the file and not the
bridge. That bridge is the reason `SELECTION_RULES` has an `njc19-compound` rule
at all.

**The selection rule, because 41% of the file is glycerophospholipids.** A
record is loaded when it is `observed` (`detected` or `quantified` = 1),
`origin-classified` (`metabolite_type` filled — of the loaded set,
`Co-metabolite` 664 and `Primary` 46, MiMeDB's only evidence-graded axis), or
`njc19-compound`. **v2 split `detected` from `quantified`**: they were `1` on
exactly the same 711 rows in v1.0 — one fact written twice — and are 1,674 and
1,413 here, so the `observed` rule is a real disjunction now rather than a
doubled-up flag. `predicted` is still effectively empty (`NULL` on 29,221 rows),
so the 23.1M BLAST-propagated pathways the research document warns about are
**not here** in either release; there is no predicted layer to keep separate.

**The `njc19-compound` rule carries a second condition that is not tidiness.**
A record qualifies only if **no spelling of that compound already reaches a
node**. Without it, MiMeDB mints a node for a compound the graph holds under a
different name and NJC19 then prefers the new one: measured, on `Propanoate
(Propionate)`, which HMDB holds as `Propionic acid` (CHEBI:30768) and MiMeDB
names `propanoic acid`. The head name's conjugate is tried before any synonym,
so the MiMeDB node won, and **97 NJC19 propionate producers landed on a node
HMDB's 12 were not on** — one compound, two nodes, and D6's MES computed over
half its evidence each side. That is the exact failure the conjugate rule exists
to prevent, re-introduced by the source meant to help.

**Three identity traps, of which v2 added one.** `hmdb_id` holds *both* the
padded (`HMDB0003402`) and the legacy five-digit (`HMDB03402`) spelling — 258 of
its 3,904 filled values — so a literal join misses every legacy id silently,
which reads as "MiMeDB has no HMDB id for this". And after normalising the
padding, **149 accessions are claimed by two or more MiMeDB records each, over
329 records**: `HMDB0000158` by both `L-Tyrosine` and `D-Tyrosine`,
`HMDB0000598` by `Sulfide` and `Sulfur`, `HMDB0000208` by `Oxoglutaric acid` and
`alpha-Ketoglutarate`. A contested accession is **not a join key** — both records
keep their own `MIMEDB:` identity, and the ledger says why. That is the rule
`reconcile` already applies to an ambiguous organism name, applied to a
compound. The third trap is **`cmmc_inchikey`, new in v2 and the one that looks
most authoritative**: it is the InChIKey of the *parent* compound in the
Chemically Modified Microbial Compounds set, and on 428 of the 1,763 rows that
fill it, it differs from that row's own `moldb_inchikey`. It is loaded as a
cross-reference and is deliberately **not** one of the tests below — matching on
it would fold a microbial conjugate onto the compound it was made from.

A record whose compound the graph already holds is **not written at all**, and
"already holds" is tested three ways in order: the normalised accession, the
**full** `moldb_inchikey` (never its first block — block 2 is stereochemistry,
isotopes and protonation, so a skeleton match folds `D-` onto `L-`; and never
`cmmc_inchikey`), then the casefolded name. `Writer` keys `metabolite.csv` on
`metabolite_id` and the first row per key wins, so a merged row's properties
would be discarded silently — an outcome that reads like a successful join in
the row count and is not one. Each skip is a row in
`data/csv/unresolved_mimedb.csv` naming the node that won.

**Licence: CC BY-NC 4.0**, on the node rather than the graph, so a commercially
redistributable cut is one `WHERE m.source <> 'mimedb'`. It is documented
upstream and **not verified**: no file in either release carries a licence
header, and the page that states it is behind the same Cloudflare challenge as
the downloads.

### MASI — an aggregator, loaded as one, and the 62.5% it restates

**13,122 edges and 1,350 `Substance` nodes, and not one of them on a
relationship a primary source owns.** MASI (Zeng et al., *NAR* 49:D776, 2021,
PMID 33313900) curates microbiota–active-substance interactions **out of the
primary literature**. It measured nothing; it is a curator's index of what other
people measured — and two of the people it indexes are already sources here.

**The number that shaped every decision below.** Of MASI's 12,512 interaction
records, **5,419 cite PMID 29555994 (Maier 2018) and 2,884 cite PMID 31158845
(Zimmermann 2019)** — 66.4% of the file. Resolved to (taxon, compound) pairs,
**7,161 of the 11,456 edges it produces restate a pair one of those two screens
already carries a measured edge for: 62.5%.** Both screens are loaded from their
own supplementary tables with every cell of their matrices, negatives included;
MASI curates their positives.

**So its substances are `Substance` nodes and its relationships are its own.**
The alternative was available and was rejected on that measurement rather than
on taste: a MASI metabolism record could have pointed at the `Drug` node its
compound joins to and been called `METABOLISES`, which is the same claim in the
same direction. It would have put ~1,815 restatements of Zimmermann's own cells
into the same relationship as those cells, so `MATCH (t:Taxon)-[:METABOLISES]->
(d:Drug)` — **the query D8 is written as** — would have counted a curated
restatement and a measured screen cell as two observations, with nothing in the
query text to say so. The schema survey's rule is that an aggregated claim is a
separate edge with its own provenance; here it is a separate edge, on a separate
relationship, pointing at a separate node type, with the identity between the
two declared as an edge rather than performed as a merge. **The duplication is
opt-in in one hop instead of opt-out in a `WHERE` clause nobody writes.**

There is a second reason and it would not have been sufficient on its own: 278
of the 1,350 substances have **no therapeutic category at all** — *Cadmium*,
*Black tea extract*, *Permethrin* — and typing those `Drug` is the C14 error
(node type from what the thing is, never from the column it arrived in) in a
different column.

**And where a restatement exists, the edge says so.**
`duplicates_primary_source` is a **list** of the source tokens of every
loaded primary source that measures that exact (taxon, compound) pair —
`maier2018` 4,783, `zimmermann2019` 1,331, both 1,047 — and is **null**
otherwise. "What does MASI add that this graph did not already have" is one
`WHERE r.duplicates_primary_source IS NULL`, and 4,295 edges answer it. The
overlap is computed at prep time by reading the screens' own edge tables, which
is what `DEPENDS_ON = ["chembl", "maier2018", "zimmermann2019"]` buys: an
aggregator that ran *before* the sources it aggregates could not have measured
its own redundancy.

**Two categories, four relationships, and the second pair is deliberately not
`INHIBITS_GROWTH_OF`.** `Interaction_Category` has exactly two values over all
12,512 rows.

| relationship | edges | from |
|---|---:|---|
| `METABOLISES_SUBSTANCE` | 3,356 | `Microbes metabolize substances`, minus the 404 marked otherwise |
| `DOES_NOT_METABOLISE_SUBSTANCE` | 16 | `Metabolism_Effect_on_Drug = 'Microbe does not metabolize drug'` |
| `ABUNDANCE_CHANGED_BY_SUBSTANCE` | 7,579 | `Substances alter microbe abundance` with `Microbe_Change` Increase/Decrease |
| `ABUNDANCE_UNCHANGED_BY_SUBSTANCE` | 505 | the same category's `No significant change` |

The abundance pair reuses neither `INHIBITS_GROWTH_OF` nor
`ABUNDANCE_CHANGED_BY`. Not `INHIBITS_GROWTH_OF` because MASI's claim is an
abundance shift — 995 of these records are `In vivo` in a host, which is
gutMDisorder's shape, not a monoculture growth measurement — and because 4,778
of the pairs it resolves to are pairs Maier's screen already measured, so the
merge would have put a weaker restatement into the one relationship D8 *and* D18
both read. Not `ABUNDANCE_CHANGED_BY` because that relationship's range is
`Intervention` and a blueprint junction edge names exactly one target type per
source node type (§8) — the same engine limitation that splits `ASSOCIATED_WITH`
three ways, and stated here so the two splits are not read as the same kind of
decision.

**The measured negative is its own relationship on both pairs**, for the reason
`NO_EXCHANGE_WITH` and `DOES_NOT_INHIBIT_GROWTH_OF` are: a refutation stored as
a property is counted as an observation by every query that does not know to
exclude it. `effect` rides on all four, so the whole population is still one
property. **`DOES_NOT_METABOLISE_SUBSTANCE` is only 16 edges and the reason is
the most quotable fact in this source**: 388 of the 404 curated "this microbe
does not metabolise this drug" statements are about `Unclassified gut
microbiota`, which is not an organism and reaches no NCBI id.

**`SAME_COMPOUND_AS`: 883 of 1,350, by two name routes, and no identifier
route exists.** The join is the shared `microbiomekg.drugs` module over
`drug.csv` — the substance's own spelling (727) then its salt-stripped form
(156) — and where it lands, the `Substance` node carries `drug_id` and one
`SAME_COMPOUND_AS` edge onto the existing `Drug`. **MASI mints no `Drug` node
ever**, which is the one thing that separates it from both screens and is
asserted as such. Its cross-reference block is the richest of any source here —
709 DrugBank ids, 1,067 PubChem CIDs, 1,067 InChIKeys, 561 KEGG ids — and
**none of it reaches anything**, because the fetched ChEMBL molecule JSONL
carries no cross-references at all. That is the wall `IS_DRUG` already
documents, hit from the other side.

**41 substances are never offered to the join at all**, because MASI's own
`Substance_subcategory` files them as `Drug Class` or `Drug category` —
*ACE inhibitors*, *Alpha blockers*. Matching a class onto whichever molecule
shares its spelling is the level-4-ATC error `microbiomekg.drugs` refuses in so
many words. The 16 substances with no therapeutic category that *do* reach a
`Drug` by name — *Nicotine* → CHEMBL3, *Berberine*, *Permethrin* — are allowed
(they are the same molecules) and every one is a ledger row, so a false merge
appears in a count rather than in nobody's notes.

**Three routes to a taxon id, and the microbe dictionary is worth a quarter of
the source.** `Microbe-Tax-ID` is `n.a.` on 4,965 interaction rows;
`microbesInfo` recovers an id for 3,007 of them (2,922 edges) and knows only a
*genus* for 92 more microbes (991 edges), where the claim is made at the genus
and `taxon_id_route` says so. Where the record and the dictionary disagree —
three microbes, 69 rows, every one a **class** id against a **phylum** id for a
name NCBI spells at both ranks — the record's own id wins and the disagreement
is a ledger row, because neither is wrong and preferring one silently would make
the graph's rank depend on read order.

**This is the only source here with no broadest-accepted rank.** Both screens
refuse a resolution broader than `genus`, because every organism they screened
is one cultured isolate. MASI genuinely curates above genus — 45 families, 21
classes, 14 orders and 11 phyla, and the two organisms its disease table cites
most are *Firmicutes* and *Bacteroidetes* — so a ceiling would drop real
curation. `reported_rank` (MASI's own `microbe_tax_level`, lower-cased) beside
`original_rank` (NCBI's) is what a query filters on: G5's two-rank split doing
the work a ceiling would do badly. Promotion is unchanged — strains and
subspecies still promote to the species ceiling (C7).

**`evidence_level` is derived per row, not defaulted.** `in-vitro` 8,272,
`unknown` 2,249, `in-vivo-model` 935. The rule reads `Experiment_System` and
`Experiment_Model_Species`: in vivo in a non-human host is `in-vivo-model`, in
vitro is `in-vitro`, and the 2,396 rows whose system column is `n.a.` are
`unknown` — as are the 41 in-vivo *human* rows, because nothing in the file says
those studies were observational and `observational-unspecified` would be a
guess about a design. The 8,303 rows whose model species reads
`High-throughput incubation assays` are the two screens' own cells and land at
`in-vitro`, which is what the primary sources give them.

**The disease half: a fourth `ASSOCIATED_WITH` source, keyed by name because
there is no id.** 783 edges from 784 records. MASI's disease export carries 56
labels and **no DOID, MONDO or EFO column anywhere**, so the hub is reached
through `MondoIndex.mondo_by_name` — a term's own `name:` (358 edges) or an
**`EXACT`** synonym claimed by exactly one live term (326) — and the route is on
the `Disease` node as `condition_join`, so it stays countable and reversible. 15
of the 56 labels reach nothing and keep `MASI:DIS<n>` with `mondo_id` null, the
same half-joined shape BugSigDB's 503 own-CURIE terms already have. Three of
those misses are worth naming: `Rheumatoid arthrits` is the source's typo,
`coeliac disease` is a **second MASI id for celiac disease** that MONDO spells
only as a `RELATED` synonym, and `Skin and mucosal infections` is not a disease
term. Nothing corrects them — a spelling rule standing in for a curated
equivalence is what `MONDO:equivalentTo` exists to avoid, and reading a
`RELATED` synonym as identity is the same false merge from the synonym side.

**All 783 disease edges violate the fourteen-property contract, and that is the
audit working.** Eight properties are fillable — `direction`, `evidence_level`,
`pmid` and the §5(b) provenance block. The other six describe a
differential-abundance *study*: this export has no design, host species,
sequencing type, statistical test or arm sizes. `Association-type` is one value
on all 784 rows (`Microbe abundance associates with disease`) and is a curation
category, not a design; writing it into `study_design` would improve the audit
number by misdescribing the data, which is the call gutMDisorder's
`Research Type` already got.

**Probiotic annotation lands on `Taxon`, and it is three-state.** `if_probiotic`
is `Yes` on 46 microbes and `n.a.` on 760, and `n.a.` means *not recorded*, never
*not a probiotic*. So `Taxon.probiotic` is **true** on 44 taxa, **false** on the
496 other organisms MASI curates, and **null** on every taxon MASI does not
mention — collapsing null into false would make a claim about 862,000 taxa the
source never named. `probiotic_use_species`, `probiotic_research_stage` and
`probiotic_reported_name` ride beside it, written by `prep_taxonomy.py` from a
table this prep leaves behind, which is why that prep names `masi` in its
`DEPENDS_ON`. **The reported name is not decoration**: 806 MASI microbes collapse
onto 540 taxa, so *E. coli* Nissle 1917 promotes onto the same 562 as plain
*E. coli*, and `taxon_probiotic.csv` is keyed on `tax_id` with first-row-per-key
winning — which silently dropped 5 of the 46 claims until a probiotic claim was
made to beat a non-claim. `tests/test_masi.py` keeps that fixed.

**What it refuses, all of it counted.** 1,048 interaction records name a microbe
that reaches no NCBI id — `Unclassified gut microbiota` 474 and `Unidentified
gut microbes` 311 between them — and become `UnresolvedTaxon` tombstones keyed on
**MASI's accession rather than the name**, because 24 microbe ids are written
under more than one spelling (`PMDBM140` is *Clostridioides*, *Clostridium* and
*Peptoclostridium difficile*) and a name-keyed tombstone would split one refusal
into three. 8 records carry a `Microbe_Change` this model has no direction for
(`delay microbiota maturation`), and a category this loader has not read would
be a ledger row rather than a guess. `Interation_Record_ID` (the source's own
spelling) is **not unique** — 2,891 ids appear on two rows, always one curated
statement about two microbes — so `source_record_id` is
`masi:<record>|<microbe>|<substance>` and neither organism is lost.

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

**6,030 `Drug` nodes of ChEMBL's own — 6,408 in the graph, the other 378 minted
by the two drug screens into the same table (355 from Maier, 23 from
Zimmermann) — plus 1,518 `ProteinTarget` nodes, 6,984
`HAS_MECHANISM` edges, 1,493 `OF_ORGANISM` edges and 15 `IS_DRUG` edges.** Three JSONL files, CC
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
protein of one of 28 bacteria. **That is one leg of D8 and it is not the main
one**: "which drugs act on a bacterial protein" is answerable from ChEMBL, but
binding a protein an organism has is a different claim from stopping that
organism growing, and for 28 mostly-pathogen taxa it is an antibacterial's
intended target rather than a gut-commensal effect. **ChEMBL carries no
drug↔taxon edge at all**, and it still does not: the direct layer is Maier
2018's (§ above), and `tests/test_acceptance.py` asserts that every
`Drug`–`Taxon` edge in the graph belongs to that screen — the restatement of the
guard that used to assert there were none, so a shortcut through a shared
organism is still a red test.

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

### Maier 2018 — the first direct drug→taxon edge, and 42,233 measured negatives

**47,825 edges over 38 taxa and 1,197 drugs: `INHIBITS_GROWTH_OF` 5,592,
`DOES_NOT_INHIBIT_GROWTH_OF` 42,233.** This is the only source in the graph that
says a drug does something to a bacterium *directly*. ChEMBL's route from a drug
to a taxon runs through the protein it acts on, which is a different claim;
gutMDisorder's `ABUNDANCE_CHANGED_BY` is an abundance observation in a host, not
a growth measurement in culture. It is what moved D8 and D18 off `partial`, and
it arrived because MASI — the aggregator that curates this literature — was
believed unrecoverable at the time (an expired TLS certificate, not a dead
host; `docs/sources.md` §14 carries the retraction), while the landmark screen
MASI aggregates is a supplementary table anyone can download
(`docs/sources.md` §15). The order turned out to be the right one anyway: the
screen measures where the aggregator curates.

**The negatives are the larger half and they are a *measurement*.** A screen
runs every cell: 1,197 drugs × 40 isolates = 47,880, of which 55 are written
`NA`. So "this drug was tested against this bacterium and did nothing at 20 µM"
is a fact this graph can now state, which no other source here supports for
drugs — MASI would have curated positives, and gutMDisorder curates what somebody
published. They are their own relationship rather than a flag, for the reason
`NO_EXCHANGE_WITH` is: see the note in §2. The 55 `NA` cells become **neither**
relationship and are ledger rows, because a pair the screen did not measure is
not a non-hit — that is the one error in this loader that would have looked
harmless in every count.

**The hit threshold is derived and confirmed four ways, because the sheet never
states it.** `S3a. Adjusted p-values` publishes a p-value per cell and an
`n_hit` count per drug, and no cutoff. `p < 0.01` reproduces `n_hit` on **all
1,197 rows** (0.05 reproduces 791, 0.001 reproduces 879). It then reproduces
three things it was not fitted to: the per-species human-targeted hit counts in
both figure source-data workbooks (40 of 40 isolates, 25 of 25); the paper's
abstract — 203 of 835 human-targeted drugs hit at least one strain = **24.3%**
against its "24% of the drugs with human targets"; and supplementary table 4's
independent TP/TN/FP/FN column, whose 170 `TP`/`FP` rows all sit on hit edges
and whose 209 `TN`/`FN` rows all sit on non-hit edges. `HIT_THRESHOLD` decides
the *type* of every edge in the source, so `scripts/prep_maier2018.py`
re-derives the first of those on every run and refuses to write when it stops
holding.

**The ChEMBL join is 72.4%, by three routes, and the route is on every edge.**
Tried verbatim-first, the same precedence `njc19.name_variants` uses: the exact
casefolded `pref_name` (**455**), a level-5 ATC code (**390**), the name with a
salt or hydrate suffix removed (**22**). The other **330** become `Drug` nodes
keyed on their Prestwick catalogue number with `approved = false` and
`source = 'maier2018'` — every library row carries a catalogue number and a
PubChem CID, so none is ledgered for want of an identifier. Only the
seven-character ATC form is a key: level 4 names a *class*, and joining `L01BB`
would put every nitrogen-mustard analogue on one node. Stripping a salt suffix
moves *towards* this model's own identity rather than away from it — `Drug` is
keyed on the parent molecule precisely so metformin and metformin hydrochloride
are one node — which is why that route exists and why it is tried last.

**39 drugs are reached by two routes that disagree, and every one is the same
disagreement.** The name route lands on a ChEMBL *salt* node and the ATC code
lands on its parent: `Estradiol Valerate` reaches CHEMBL1511 by name and
CHEMBL135 (estradiol) by ATC. That is this model's own documented parent gap
showing through — a salt no `mechanism.jsonl` row names has no parent evidence
in the fetched subset and keeps its own id (§ChEMBL above) — not a defect in the
join. Verbatim-first decides it and `unresolved_maier2018.csv` names both
candidates, so the number is read rather than trusted.

**A screen fact about a drug ChEMBL already holds cannot go on its node, and
`drug_class` is therefore on the edge.** `drug.csv` is keyed on `drug_id` and
the first row per key wins, so the Prestwick annotation for the 867 joined drugs
is discarded at the node — the same constraint recorded for MASI. Putting
`drug_class` on the edge is what makes "which *human-targeted* drugs inhibit
this taxon" answerable for all 1,197 rather than only for the 330 minted here.
The four `prestwick_id` / `pubchem_cid` / `screen_drug_class` /
`screen_target_species` node columns are filled on minted nodes and empty on
ChEMBL's 6,030, which is what `microbiomekg.tables.Writer`'s merge is for.

**Two of the forty organism strings are not taxon names, and the fix is a closed
map rather than a rule.** 38 resolve verbatim (24 exact, 12 synonym, 4 promoted;
every one at rank `species` after promotion). Supplementary table 2 writes the
*B. fragilis* toxigenicity phenotype **inside** the species column —
`Bacteroides fragilis nontoxigenic` and `Bacteroides fragilis enterotoxigenic
(ET)` — and no `names.dmp` entry spells either. Letting them fail writes two
`UnresolvedTaxon` tombstones each asserting NCBI has lost *Bacteroides
fragilis*, which is false, and costs 2,394 edges;
`microbiomekg.ontology.maier2018.SPECIES_OVERRIDES` is the two verbatim strings
and nothing else, the same shape as NJC19's six host cell types. A
suffix-stripping rule general enough to catch them would mangle the next
organism name, and two hand-written phrases in one file are not a grammar. The
strings survive on the edge as `reported_name` with the isolate's designation in
`strain`.

**40 isolates collapse to 38 taxa, and each collapse is two edges rather than
one.** The screen ran a non-toxigenic and an enterotoxigenic *B. fragilis*, and
*E. coli* IAI1 and ED1a, side by side. They are one taxon and two independent
measurements — C13's rule — told apart by `nt_code` and `strain`. Every isolate
is a cultured strain, so `reported_rank` is `strain-level isolate` on every edge
and `original_rank` keeps NCBI's rank for whatever the name first resolved to
(`strain` for the two *E. coli*, `subspecies` for *F. nucleatum* and
*B. longum*): G5's two-rank split, applied to a source whose unit of measurement
really is a strain.

**The contract is nine properties, not fourteen.** Six of the fourteen —
`direction`, the two group sizes, `sequencing_type`, `statistical_test`,
`study_design` — describe a differential-abundance observation, and a
monoculture growth screen has none of them; requiring them would report a
permanent ~100% violation meaning "this is not an abundance study", the same
reasoning that gave CARD eight and ChEMBL's `HAS_MECHANISM` seven. What is
required is the §5(b) provenance block plus `evidence_level`, `publications` and
**`effect`** — the one field that says which of the two measurements an edge is.
Every one is written by the prep unconditionally, so both rules are declared at
**`error`**, where a violation is a regression here rather than a gap upstream.

**`evidence_level` is `in-vitro` on all 47,825 and the licence is
`Maier2018-unstated`.** The first is Part B's own definition of the tier
("measured in culture: growth… an MIC over controls") and the file carries no
per-row design, host or assay column that could move it. The second is the
weakest licence token in the graph and it says so rather than guessing: journal
supplementary material of a subscription article carries no separate data
licence, and inventing `CC-BY-4.0` on 47,825 edges would put a redistribution
claim in the graph that nobody made. Because G3 puts the licence on the edge,
`WHERE r.source_licence <> 'Maier2018-unstated'` is the redistributable cut and
this one token contaminates nothing else.

**The figure source data is deliberately not loaded, and one sheet is why it is
worth saying.** `data/raw/maier2018/MOESM13/14/15/16_ESM.xlsx` are the four
figure source-data workbooks. `MOESM15` sheet `3c` is a drug × isolate table
with a concentration and a `=`/`<` qualifier and reads exactly like a hit list —
but **all 29 of its drugs have `n_hit = 0` in the screen and none of its 212
pairs is a hit**, so loading it as inhibition would have written 212 edges the
same paper's own p-value matrix contradicts. `MOESM13` `1c` and `MOESM16` `5a`
are per-species hit counts, aggregates of `S3a`, and their contribution is that
they independently confirmed the derived threshold. `MOESM16` `5b` is drug ×
*E. coli* gene, and there is no gene node type here for a chemical-genomics
score.

### Zimmermann 2019 — the other direction, and why there is no `Gene` node

**20,054 edges over 66 taxa and 271 drugs: `METABOLISES` 2,575,
`DOES_NOT_METABOLISE` 17,479.** This is the half of D8 Maier cannot answer —
*the bacterium changes the drug*, not *the drug changes the bacterium* — from
Zimmermann et al., *Nature* 570:462-467 (2019), PMID 31158845: 271 orally
administered drugs against 76 human gut strains, LC-MS at 12 h against t=0 over
four independent cultures, every cell measured (`docs/sources.md` §16).

**The direction is the model, not a stylistic choice.** The agent is on the tail
of every edge in this layer: Maier's run `Drug → Taxon` because the drug is
acting, these run `Taxon → Drug` because the bacterium is. Reversing either to
make the pair look symmetric would put the agent on the wrong end of half the
edges and would silently break the assertion `tests/test_acceptance.py` keeps —
that every `Drug → Taxon` edge in the graph is the growth screen's. Four
relationships across two directions, and the split reasoning is in §2.

**Four of the eighty measured columns are not organisms, and they read exactly
like the other seventy-six.** `Control pH 4` through `Control pH 7` sit
*between* strain columns in the screen, carry the same five sub-columns, and
produce **38 apparent hits between them** under the rule that calls a real one.
They are the abiotic-degradation controls — drug that disappears with no
bacterium present. Nothing structural distinguishes them, so a loader that
walked the block layout would have written 1,084 cells of *chemistry* as
microbial metabolism, and would have reported 80 screened strains against the
paper's 76. `microbiomekg.ontology.zimmermann2019.is_control_column` is the only
place that knows, each excluded column is a ledger row, and excluding them is
what makes the published 76 reproduce from the sheet. It is the Maier lesson
(the figure sheet that reads like a hit list and is not) one layer down: what
looks like a measurement of an organism may not be one.

**The call rule is derived, and the file publishes only half of it.** The screen
gives each drug its own `Drug adaptive FC threshold %` — 20 for 124 of the 271,
higher for the rest — so the depletion cutoff is *read*. The comparison and the
significance cutoff are not stated anywhere, and both change the answer:
**`% consumed >= the drug's own threshold` with `p(FDR) <= 0.05` reproduces the
paper's headline exactly, 176 of 271 drugs (65%) metabolised by at least one
strain**, where `p < 0.05` gives 175 (fourteen cells sit at exactly 0.05),
`p <= 0.01` gives 133, and swapping the per-drug threshold for its 20% floor
gives 190. `scripts/prep_zimmermann2019.py` re-derives that headline on every
run and refuses to write when it stops holding, because the rule decides the
*type* of every edge here. A second, weaker check comes from a sheet with no
part in the derivation: all 20 parent drugs the gene table names a metaboliser
for are among the 176 — which also holds at 0.01 and fails at 0.001, so it rules
out an over-strict cutoff and does not separate the two plausible ones. Recorded
as the weaker check it is rather than counted as a second confirmation.

**Seventeen of the 271 compounds have a node only because the *other* screen
minted one, and that is what `DEPENDS_ON` is for.** The join is three routes
tried verbatim-first — the screened `MOLENAME` (**195**), supplementary table
2's own parent-drug `name` column (**43**), the screened name with a salt suffix
removed (**10**) — for **248 of 271 = 91.5%**; the other **23** are minted as
`ZIMMERMANN2019:<screened name>` with `approved = false`. There is no ATC route
(the sheet has no ATC column) and no CAS route (the cell is multi-valued with
inline annotations, `34381-68-5, 37517-30-9 [acebutolol]`, and parsing an
identifier out of it would be a grammar rather than a lookup). Of the 248,
**231 land on ChEMBL nodes and 17 on nodes `prep_maier2018.py` minted** — so
this prep declares `DEPENDS_ON = ["chembl", "maier2018"]`. Running it first
would mint a second node for each of those 17, and the split would be invisible:
both nodes would carry edges, both would look right, and D8's own question —
"does drug D inhibit gut bacteria, **or get metabolised by them**" — would return
half an answer for every one of them. The shared machinery is
`microbiomekg/drugs.py`; what stays per-source is the *order* the routes are
tried in, because that order is a claim about which of a file's own columns is
the most trustworthy spelling, and the two screens do not carry the same
columns.

**Two of the 76 strain names are left unresolved on purpose, and five are
corrected — the rule is what separates them.** An override is written only when
something *other than the spelling* confirms it. Three are confirmed by the
row's own culture-collection number (`Pretovella copri`/DSM18205 →
*Prevotella copri*; `Bryantia formataxigens`/DSM14469 → *Bryantella
formatexigens*; `Eubacterium biforme`/DSM3989 → *Holdemanella biformis*, which
`names.dmp` still spells at strain level), one by exhaustion (*Odoribacter
splanchnicus* is the **only** name in all of `names.dmp` at edit distance 1 from
`Odoribacter splanchnius`), and one because the binomial is a verbatim prefix of
the string (`Lactobacillus  reuteri CF48-3A`, the same shape as Maier's
*B. fragilis* toxigenicity qualifiers). **`Bacteroides WH2` and `Bifidobacterium
ruminatum` meet none of those tests**: NCBI holds two live candidates for each —
`Bacteroides sp. WH2` (311784) against *B. cellulosilyticus* WH2 (1268240), and
*B. ruminantium* (78346) against *B. ruminale*, a synonym of *B. thermophilum*
(33905) — and the reference column says `WH2` and `fecal isolate`. They stay
`UnresolvedTaxon` tombstones **carrying both candidate ids**, at 271
measurements each. That is a deliberate refusal, not a failure: picking one
would attribute a whole row to an organism nobody screened and no count in the
graph would show it, and a tombstone that only said "no name match" would leave
the next reader nothing to act on.

**76 strains collapse to 66 taxa, and each collapse is parallel edges.** Seven
*B. fragilis* isolates and three *B. thetaiotaomicron* were screened side by
side; they are one taxon and independent measurements (C13), told apart by
`screen_column` and `strain` on every edge. `reported_rank` is `strain-level
isolate` throughout and `original_rank` keeps NCBI's rank for whatever the name
first resolved to — G5's two-rank split again.

**The contract is the same nine as the growth screen**, for the same reason: six
of the fourteen association properties describe a differential-abundance
observation a monoculture assay does not have. The negative is *bounded* by what
the sheet states rather than by a concentration — `incubation_hours = 12` and
`replicates = 4` are on every edge, and there is no `screen_concentration_um`
because the workbook states none anywhere and inventing one would be a
measurement nobody made. `evidence_level` is `in-vitro` on all 20,054, and the
licence is `Zimmermann2019-unstated` — deliberately a *different* token from
`Maier2018-unstated`, because two subscription articles are two permissions and
a reader excluding one has no reason to lose the other.

#### No `Gene` node — the recommendation, and what would change it

The paper's second half identifies **30 bacterial gene products** that
metabolise **20 of the drugs**, with a RefSeq locus tag, a PATRIC id and a
RefSeq protein id each. That is a real, clean, identifier-bearing table, and it
is the strongest case this graph has yet had for a gene node type. It still does
not earn one, on four counts:

1. **It is a different experiment.** The genes were found by expressing a
   library of them in *E. coli*, not by measuring the 76 strains. "Gene X
   metabolises drug D" and "strain S metabolises drug D" are separate claims
   with separate evidence, and a `Gene` node would sit between them implying a
   path — *taxon has gene, gene metabolises drug* — that the data does not
   support. **Five of the 37 (organism, drug) pairs the gene table covers
   disagree with the screen outright**: the gene worked in *E. coli* and the
   donor strain did not deplete the drug in culture.
2. **No Part D query asks for a gene.** D8 asks "which strains", D13 asks which
   *pathway or gene* carries a **metabolite production** claim — a different
   layer, served by Reactome and HMDB. A node type nothing queries is a type
   whose contract nothing checks.
3. **Part B's W7 does ask for "the gene where identified", and an edge property
   answers it in one hop.** `gene_locus_tags`, `gene_products`,
   `gene_protein_ids` and `n_gene_products` ride on the `METABOLISES` /
   `DOES_NOT_METABOLISE` edge for the pairs table 13 covers. The five
   disagreements land on `DOES_NOT_METABOLISE` edges, where they stay visible —
   dropping them, or moving them onto the hit edge, would be inventing agreement
   between two experiments.
4. **Scale.** 30 nodes over three organisms. Maier declined a gene node for 23
   *E. coli* chemical-genomics genes on the same reasoning, and the two
   decisions should not diverge on 30 against 23.

**What would change it**, stated so the next reader does not have to re-derive
the argument: a source that measures gene presence *per taxon* — a pangenome, a
gutSMASH cluster call, or CARD's own `CARRIES_RESISTANCE_GENE` shape extended
past resistance — would make *taxon has gene* a measured edge rather than an
implication, and at that point the gene becomes the join between two independent
measurements instead of an ornament on one. `ResistanceGene` is already that
node in miniature for AMR; a general `Gene` should arrive the same way, with a
source behind each of its two edges, not from a supplementary table that names
30 of them.

The join from the gene table to the screen is worth one line because it is the
only identifier the two sheets share: **a PATRIC feature id's first component is
an NCBI taxid** (`fig|226186.12.peg.149` → 226186). That is resolved to a
species and then matched against the screened column *whose own
culture-collection number appears inside the strain taxon's name* — both halves,
because three columns are *B. thetaiotaomicron* and a species-only match would
attribute one isolate's gene to all three. The name alone would not do it
either: NCBI has since renamed 483217 to `Phocaeicola dorei DSM 17855` while the
sheet still says *Bacteroides*, so the binomial no longer agrees and the
collection number still does. Anything that matches zero or more than one column
is a ledger row.

---

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
   1,936 (24%) are placeholders, and 6,553 of the 105,880 disease associations
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
ASSOCIATION_RELATIONSHIPS = ("ASSOCIATED_WITH",)

"Condition": {"abstract": True},                       # Disease/Phenotype/Exposure is_a it

"ASSOCIATED_WITH": {
    "domain": "Taxon", "range": "Condition",
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
The name is now stated, and the test asserts it is declared rather than
inferring which it is. There is one of them since the union range collapsed the
three, which is also what makes the audit's headline row cover every
association rather than the disease third of them.

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
of the 105,880 association edges but a third of the nodes), and a BM25 index
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
| `Taxon` | `synonyms_text` | reconciliation by an old name — "Bacillus coli" → *Escherichia coli* (the queryable `synonyms` beside it is a list, which BM25 cannot index) |
| `Disease` | `label` | condition free text, since the key is a MONDO or EFO CURIE and few users know either |
| `Signature` | `description` | the curator's sentence: "genus-level microbes correlating with odor intensity" |
| `Paper` | `title` | literature entry point |

Not indexed: `Study.title` (identical to `Paper.title`), `BodySite.label` (237
values, an exact match is better), any numeric or CURIE field.

`Taxon.synonyms` is a **native list**, capped at 20 names per taxon (68 taxa
hit the cap at microbial scope), so `'Bacillus coli' IN t.synonyms` and
`UNWIND t.synonyms` are queries rather than a Python re-parse. The BM25 lane
reads `Taxon.synonyms_text`, the same names joined with `" | "`, because
`build_text_index` refuses a list-valued property — *"BM25 indexes text: a
numeric or list-valued property is not indexable"*. `prep_taxonomy.py` writes
both from one list in one place, so they cannot disagree; §8 records the gap.
**A synonym lookup should say which rank it wants.** BM25 scores a short
document higher, and a strain's synonym string repeats its species binomial in
fewer words, so `text_bm25(t, 'synonyms_text', 'Lactobacillus reuteri')` returns
three *strains* before it reaches species 1598 (Part D, D12).

Index sizes at microbial scope with all six sources: `Taxon.scientific_name`
864,099 documents / 443,091 terms; `Taxon.synonyms_text` 103,174 / 98,652 (760,925
taxa have no synonym at all, so BM25 skips them — an absent property is not an
empty document); `Signature.description` 14,425 / 6,383 (421 signatures have no
description); `Disease.label` 808 / 952; `Paper.title` 2,486 / 4,372. All five
build in well under a second, and `scripts/build.py` builds exactly this list. `Phenotype.label` (62) and
`Exposure.label` (43) are not indexed — at that size an exact match beats BM25.

---

## 6b. Semantic name lookup — opt-in (`--with-vectors`, character n-grams, `text_score`)

**Off by default**, the way `--with-kegg` is. `scripts/build.py` always builds
§6's five BM25 indexes; it builds this lane only when asked:

```bash
.venv/bin/python scripts/build.py                  # BM25 only — the default .kgl
.venv/bin/python scripts/build.py --with-vectors   # both lanes
```

**The sentence that decides it: reconciliation at load time does not use this
lane.** `microbiomekg/reconcile.py` resolves every organism name a source
prints by exact match, by NCBI synonym, by authority stripping
(`Clostridium difficile (Hall and O'Toole 1935) Lawson et al. 2016`) and by
merged-id remapping — never by a vector. So the tax_id on every edge, and the
`REPORTED_BY` audit trail recording how each spelling resolved, are *identical*
in both builds. What the vector lane buys is query-time tolerance for a name
the **user** misspells, and nothing else.

| Node type | Property | Vectors | What it is for |
|---|---|---|---|
| `Taxon` | `scientific_name` | 864,110 | a printed name -> a tax_id, typos included |
| `Disease` | `label` | 808 | free text -> a MONDO/EFO CURIE nobody memorises |

### What it costs and what it buys

Measured 2026-09-03 at `--scope microbial` over the ten-source graph
(`bench/results/2026-09-03-ten-sources.md`, §1, §3 and §4 — not re-measured
here):

| | default (BM25 only) | `--with-vectors` | the lane's delta |
|---|---|---|---|
| build wall time | ~4.0 min | 5.4 min | **+82.6 s** (28.2 s embed + 54.4 s HNSW) |
| `.kgl` on disk | 46.7 MB | 212.7 MB | **+165.9 MB** |
| `kglite.load()`, warm | 1.03 s | 2.41 s | **+1.39 s** |
| resident memory, served | 1.2 GB | 3.7 GB | **+2.5 GB** |
| the five BM25 indexes | 276 ms, +14.3 MB | the same | — (why they are unconditional) |

The **delta** is the transferable number, not the left column: the eleven-source
default `.kgl` is 49.3 MB now, having grown with MASI and again with the list
properties, and this capture has not been re-run.

What it buys is one measured thing: the five misspellings in
`tests/test_semantic_lookup.py` — `Clostridium dificile`, `Fecalibacterium`,
`Akkermansia muciniphilia`, `Citrobacter frundii`, `Lactobacillus plantari` —
reach the right tax_id at rank 1, **5/5**, and no token-level index reaches any
of them. The lexical lane alone already resolves the correctly-spelled old
binomials NCBI keeps as bare synonyms (*Ruminococcus gnavus* → 33038,
*Propionibacterium acnes* → 1747, *Lactobacillus rhamnosus* → 47715), **3/3**,
and the vector lane misses at least one of those — asserted, so that the day
either lane stops earning its place the suite says so.

So the trade is a 4.6× `.kgl`, a 3× serving footprint and a quarter of the
build's wall time (82.6 s of 5.4 min), for typo tolerance at the prompt. Worth it for an interactive agent
session where a user types organism names from memory; not worth it for a
pipeline that queries by tax_id, and not for shipping the graph.

### What the default `.kgl` gives a consumer, and what it withholds

It gives them the **whole graph** — every node, edge, property and evidence
field is identical, because the lane adds an index and changes no data — plus
§6's five BM25 indexes
(`Taxon.scientific_name`, `Taxon.synonyms_text`, `Disease.label`,
`Signature.description`, `Paper.title`). So exact lookups, an old binomial
through the synonym index, and free-text entry into diseases, signatures and
papers all work; and every tax_id in it was already reconciled at load time by
exact/synonym/authority/merged-id matching.

It withholds `text_score()`, and withholds it **loudly**: on a graph with no
vector store the call raises rather than scoring zero —

```
Cypher execution error: vector_score(): no embedding 'scientific_name_emb'
found for node type 'Taxon'
```

— which takes the whole query down, including a hybrid
`score_fuse(text_bm25(…), text_score(…))` whose BM25 lane would have been fine
on its own. That is the better of the two failure modes (a silent 0.0 would
rank arbitrarily and look like an answer), but it means anything offering a
hybrid lookup has to **ask first and route**, not catch: `graph.list_embeddings()`
is `[]` and `graph.embedding_dim('Taxon', 'scientific_name')` is `None` on a
default build. That is the check `tests/test_semantic_lookup.py` skips on.

### The embedder, and why `ef_search` is pinned

**The embedder is `microbiomekg.embedder.CharGramEmbedder`, not a downloaded
model, and that is a deliberate scope statement rather than a shortfall.** It
hashes 3/4/5-character n-grams of the casefolded name into 256 signed
dimensions and L2-normalises, so cosine similarity **is** n-gram overlap.
`text_score()` here therefore means *spelled like*, never *means the same as*:
it resolves `Akkermansia muciniphilia`, and it will not connect "bowel" to
"intestinal". Two reasons it is the right instrument anyway: the lookup this
graph needs is a name-reconciliation problem, not a semantic one (Part C); and
a published model would make the build depend on a model download. The hash is
`zlib.crc32` rather than `hash()` because Python salts string hashing per
process — a salted hash would embed the same name differently on every run and
the store would quietly stop matching queries after a restart.

**`ef_search` is pinned to 512 and the default is not safe here** — see §8
item 9. At kglite's default 64, one fixture in five came back catastrophically
wrong through Cypher's `ORDER BY text_score(...)` index pushdown, as an
ordinary result set.

**How the two lanes are used is a routing rule, not a blend.** Lexical first
(the synonym index resolves an exactly-spelled old binomial), vector on a miss,
and the vector query fuses *two* lanes — the whole name and the epithet alone —
because a genus rename destroys the first word and leaves the second.
`mcp/microbiomekg.skills/reconciliation.md` is the authority; the measured
outcomes are in `tests/test_semantic_lookup.py`, which skips wholesale when the
graph was built without `--with-vectors`.

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

→ `105880, 894, 1051, 14292, 2075`. Swap `ASSOCIATED_WITH` for the three-way
alternation to census every association type at once.

**Q6 — resolve an obsolete name through the synonym index.**

```cypher
MATCH (t:Taxon) WHERE text_bm25(t, 'synonyms_text', 'Bacillus coli') > 0
RETURN t.title, t.rank, text_bm25(t, 'synonyms_text', 'Bacillus coli') AS score
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
ASSOCIATED_WITH.required_properties           warn   17546 / 112966   15.50%
IN_CONDITION.required                         warn    1206 / 14846     8.10%
AT_BODY_SITE.required                         warn      78 / 14846     0.50%
ASSOCIATED_WITH.property_types                error       0 / 112966    0.00%
REPORTED_BY.required_properties               error       0 / 114742    0.00%
IS_DRUG.required_properties                   error       0 / 15        0.00%
… 111 rules total, 104 of them at 0 violations
```

The four rules above `ASSOCIATED_WITH` are what a new source looks like when
its columns do not cover this graph's contract, not a regression:
gutMDisorder records no study design and no per-association arm sizes, and
CARD's carriage and drug-class edges carry no group sizes or statistical test
because there are none to carry. The number to watch is the *denominator* —
`IS_DRUG.required_properties` read 0 / 0 for a whole release while the
relationship silently loaded nothing (§8).

**Two of these rows are the union range arriving**, and both moved in the
direction that says the earlier number was the wrong question.
`ASSOCIATED_WITH.required_properties` used to be three rules — 16,768 / 105,880
(15.80%) for the disease third plus 293 / 4,717 and 485 / 2,369 that nothing
quoted — and only the first was ever called "the headline". One rule over
17,546 / 112,966 is that headline actually covering the relation. And
`IN_CONDITION.required` fell from 2,292 / 14,846 (15.40%) to 1,206 (8.10%),
because it used to count signatures with no *disease*-coded condition; it now
counts signatures naming **no condition at all**, which is the metric §4 wanted
and could not express.

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
build, loads it, builds §6's five BM25
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
a row in `taxon_condition.csv`, not a second relationship, because a junction
entry names one relationship and one CSV. That is what
`microbiomekg.tables.Writer(merge=True, owner=…)` is for. The *target type* is
no longer part of that constraint — the entry names a list of them and a
routing column (item 5 below) — which is why the three condition tables are now
one.

**The `KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE=1000000` workaround is gone, and
this build sets no chunk size at all.** It was here because the blueprint
junction-edge loader streamed each junction CSV in 100,000-row chunks and
re-decided *per chunk* whether the connection type was new: the first chunk
registered it and every later chunk merged by endpoints, so `taxon_condition.csv`
— 112,966 rows of deliberately parallel edges — lost every repeat of a pair the
first chunk had seen, with no warning and no error. kglite 0.16.22 decides the
regime once per CSV and holds it, so the chunk size bounds peak RAM without
changing the graph. Measured both ways on the eleven-source build: at the
default chunk size 0.16.22 loads **934,206 nodes and 1,324,684 edges**, the
same totals the override produced on 0.16.21, and every junction relationship's
edge count equals its CSV's logical row count.

Two tests hold it there rather than the constant.
`tests/test_loader_contracts.py` runs ten parallel edges through a *three-row*
chunk and asserts all ten survive with their own properties; the
`tests/test_acceptance.py::test_every_junction_row_became_an_edge` family
asserts rows == edges for all 29 junction relationships of the real build. The
second is the one that cannot be satisfied by a build that quietly dropped
rows, and it needs no re-measuring when a source lands.

Twelve things the blueprint, the ontology or the query surface could not
express. **These go to the engine, not into a workaround this repo pretends is
a design** — and that is now a claim with a track record rather than a policy:
**kglite 0.16.22 was cut for this list, and closed eight of the twelve.**

| item | status |
|---|---|
| 1. no list property from CSV | **closed** — `"list"` column type |
| 2. FK edges cannot carry properties | **closed** — `fk_edges` reads `properties` (nothing here needed to move) |
| 3. no secondary labels | **closed** — `labels` on a node spec; `Condition` is stamped, `ReportedTaxon` deliberately is not |
| 4. audit reports per edge, not per property | **half closed** — `{by: 'property'}`; *node*-property rules still do not exist |
| 5. one relationship cannot span a union range | **closed** — `target` list + `target_type_column` |
| 6. ontology cannot say "at least one of these" | **stands**, and no longer bites — (5) removed the case |
| 7. `[:A\|B]` is a syntax error inside `EXISTS { }` | **closed** — fixed, verified here |
| 8. `text_bm25()` on an unindexed property fails silently in one shape | **closed** — both shapes raise |
| 9. an HNSW index changes the answer and Cypher cannot opt out | **stands** |
| 10. `embed_texts()` cannot be scoped to a selection | **stands** |
| 11. `score_fuse()` has no per-lane normalisation | **stands** |
| 12. a missing skills pack booted silently | **closed** — boot error, and `--selftest` counts skills |

Two more that this migration found and that are *not* in the list above,
because they are the residue of closing item 1 rather than anything this repo
worked around before: **`build_text_index` refuses a list-valued property**, so
`Taxon.synonyms` needs the joined `Taxon.synonyms_text` twin beside it; and the
**ontology's `property_types` grammar has no list type** — it accepts
`string`/`integer`/`float`/`boolean`/`date`/`datetime`/`timestamp`/`point`/`any`
and nothing else — so a list property is declared `any` there and its shape
goes unchecked while its presence is still required.

1. **No list property from CSV.** **Closed by kglite 0.16.22**, which added
   the `"list"` / `"array"` column type: a cell holding a JSON array loads as a
   list. `microbiomekg.tables.as_list` writes them and 61 declarations across
   the eleven fragments read them, so `'Bacillus coli' IN t.synonyms`,
   `UNWIND m.selection_rule` and `'maier2018' IN r.duplicates_primary_source`
   are queries rather than a Python re-parse. Two residues, both recorded
   because they are the next engine asks rather than choices made here:
   `build_text_index` refuses a list-valued property, so `Taxon.synonyms` is
   accompanied by a joined `Taxon.synonyms_text` that carries the BM25 lane;
   and the *ontology*'s `property_types` grammar still accepts only
   `string`/`integer`/`float`/`boolean`/`date`/`datetime`/`timestamp`/`point`/`any`,
   so a list property is declared `any` there and its shape is unchecked while
   its presence still is.
2. **FK edges cannot carry properties** — only junction edges can. **Closed by
   kglite 0.16.22**: an `fk_edges` entry now reads `properties`,
   `property_types` and `rename`, the same three keys a junction edge reads.
   Nothing here moves because of it — `taxon_condition.csv` is many-to-many and
   would be a junction table whatever FK edges could carry — but the reason it
   is a separate file is now "the relation is many-to-many", not "the engine
   cannot put a property on an FK edge".
3. **No secondary labels.** **Closed by kglite 0.16.22**: a node spec takes a
   `labels` list, stamped after the node *and* edge phases so a stub some edge
   vivified carries them too. `Disease`, `Phenotype` and `Exposure` now carry
   `Condition`, so the abstract union the range check reasons about is a thing
   a query can name — `MATCH (c:Condition)` — without `materialize_ontology()`,
   which changes query semantics graph-wide, and without re-rooting the `is_a`
   forest, which allows one parent per class. `labels(n)[0]` is still the
   node's own type, which the build report and every type-counting query
   depend on.

   **`ReportedTaxon` is deliberately *not* stamped**, and the reason is the
   useful half of this item. It is the domain of `REPORTED_BY` — an abstract
   class over `Taxon` and `UnresolvedTaxon` — and stamping it would put the
   label on all 864,132 `Taxon` nodes, of which 8,078 were ever reported by
   anything. `Condition` is true of every node of its three types; "an organism
   as some source named it" is true of a hundredth of `Taxon`, so the label
   would answer `MATCH (n:ReportedTaxon)` with 864,356 and mean nothing. A
   union label is worth stamping when it is a property of the *type*; where it
   is a property of the individual, the edge is what says so, and
   `MATCH (n)-[:REPORTED_BY]->()` is that query. The forest constraint the
   original note worried about is still real — when `Metabolite` and `Drug`
   grow their own association edges, `Associatable` is a second union over
   `Taxon` — and `labels` is now the answer to it.
4. **The ontology audits edge properties only.** There is still no
   `required_properties` for *node* properties, which is the single fact that
   decided §1's edge-vs-node split, and that half of this item **stands**.
   The other half — "reports per edge, not per property, so a fourteen-field
   contract yields one percentage" — is **closed by kglite 0.16.22**:
   `CALL ontology_audit({by: 'property'})` fans a `required_properties` rule
   into one row per *declared* property, and `edge_property_violation()` yields
   a `properties` list rather than only the first failing name. `scripts/build.py`
   prints the census on every build, D15 reads it, and it says what a Cypher
   aggregation could not: `ASSOCIATED_WITH`'s 15.5% is **`group_0_size` on
   14,837 edges and `group_1_size` on 14,732** with six of the fourteen
   complete, and `CONFERS_RESISTANCE_TO`'s 58.8% is *one* field, `pmid`. It is
   a census — an edge missing both group sizes is in both rows — so the rows
   sum to more than the rule's violations and never back to them.
5. **One relationship cannot span a union range from a blueprint.**
   **Closed by kglite 0.16.22.** A junction entry's `target` now takes a list
   of node types plus an optional `target_type_column` naming the column that
   holds each row's target type, so `ASSOCIATED_WITH` is one relationship over
   `Disease` ∪ `Phenotype` ∪ `Exposure` loaded from one `taxon_condition.csv`,
   and `IN_CONDITION` is the same. The ontology `range` is the abstract
   `Condition` the three are `is_a`, exactly as `ReportedTaxon` works on the
   domain side, so `ontology_audit()` reports **one** rule.

   This was the single largest modelling compromise in this document, and
   collapsing it changed two numbers rather than only the query syntax. The
   headline completeness rule went from 16,768 / 105,880 (the disease third,
   the only one anybody quoted) to 17,546 / 112,966 — the whole relation. And
   nothing was lost on the way in: `-[:ASSOCIATED_WITH]->(:Disease)` is still
   exactly the disease subset, because the target node's own type is what
   separates them and always was. `target_type_column` is routing only; it does
   not become an edge property.
6. **The ontology cannot say "at least one of these relationships".**
   `required: true` is per relationship, and `exempt` covers only
   `required_properties` and `property_types` (`EXEMPTABLE_CHECKS`), so there
   is no way to declare that a node must have an `A` **or** a `B`. **This stands
   as an engine limitation and no longer bites here**, because (5) removed the
   case that needed it: `IN_CONDITION.required` is one rule over the union, so
   it counts signatures naming no condition *of any kind* — 1,206 of 14,846
   (8.1%) — which is the metric §4 wanted. It read 2,292 (15.4%) as
   "no disease-coded condition" before, and the 1,086 difference is exactly the
   signatures whose only condition is a phenotype or an exposure.
7. **Relationship-type alternation is a syntax error inside `EXISTS { }`.**
   **Fixed in kglite 0.16.22** and verified here on a scratch graph:
   `WHERE EXISTS { (n)-[:A|B]->() }`, the `MATCH`-prefixed spelling and the
   `NOT EXISTS` form all return what the equivalent `MATCH` returns. It was a
   parser gap — the subquery's pattern re-serializer had no `|` case — and it
   mattered because (5) forced three relationship names, so the natural
   "signatures that name no condition at all" query had to be written as three
   separate `NOT EXISTS` clauses. Both halves are gone: the query is now one
   clause over one relationship name.
8. **`text_bm25()` on an unindexed property fails two different ways, and the
   likelier query shape is the silent one.** **Fixed in kglite 0.16.22** and
   verified here: both shapes now raise, naming `build_text_index(...)`. It was
   the *documented fast path* that stayed silent — a query that both filters and
   ranks, `WHERE text_bm25(n, 'p', $q) > 0 … ORDER BY …`, returned zero rows
   and no error (reproduced on 0.16.21 for `Metabolite.name` and
   `UnresolvedTaxon.raw_name`), so the mistake was invisible in exactly the form
   an author is most likely to write and "no hits" was indistinguishable from
   "nothing matched". Two skill queries shipped broken that way and passed a
   test that only asserted the Cypher executed.
   `tests/test_mcp_skills.py::test_no_block_ranks_on_a_property_with_no_bm25_index`
   stays as it is — it checks `has_text_index()` directly rather than trusting
   the engine to complain, which is a better test than the one the fix would
   allow, and it costs nothing to keep.
9. **An HNSW vector index changes the answer, and Cypher gives no way to opt
   out.** `ORDER BY text_score(…) DESC LIMIT n` is pushed into the vector index
   when one exists, so an approximate result arrives as an ordinary result set.
   On §6b's character-n-gram vectors — the "unclustered high-dimensional"
   corpus kglite's semantic-search guide warns recall degrades on — the default
   `ef_search = 64` did not degrade gracefully: `Citrobacter frundii` returned
   *Enterobacteriaceae bacterium HGPR34* at cosine **0.428** while *Citrobacter
   freundii* sat unfound at **0.808**, one catastrophic miss in five fixtures.
   `ef_search = 512` fixes it (all five agree with an exact scan, 1-2 ms
   against the exact scan's 21 ms) and `scripts/build.py` pins it, with
   `tests/test_semantic_lookup.py::test_the_index_agrees_with_an_exact_scan`
   as the gate. Two things would have made this a tuning question rather than a
   wrong-answer question: `vector_search(exact=True)` has **no Cypher
   equivalent**, so a query cannot ask for the exact scan it is fast enough to
   afford; and nothing in the result says the index served it.
10. **`embed_texts()` cannot be scoped to a selection.** It embeds every node
   of a type, so "embed only the 7,910 taxa carrying an association edge"
   is not expressible — the fallback is `add_embeddings()` with an explicit id
   dict, which loses the model id and the per-node text hashes `embed_texts`
   records and therefore loses `mode='changed'` re-embedding too. Here the
   whole-scope store fit the budget (§6b) so it did not bite; on a larger
   taxonomy it would force the provenance-free path.
11. **`score_fuse()` has no per-lane normalisation, so mixing BM25 with cosine
   is a weighting problem the caller has to solve by hand.** BM25 is unbounded
   and cosine is capped at 1, so at equal weights the lexical lane simply *is*
   the ranking: on this repo's eight reconciliation fixtures, equal weights
   resolve 4 of 8 and `[0.05, 0.475, 0.475]` resolves 7 of 8. The documented
   alternative — RRF over `rank() OVER (…)` window functions — puts the lanes
   on one scale but costs a full sort per lane (445 ms against 150 ms over
   864,099 taxa here) and, on this corpus, ranked *worse* than either fused
   form. A rank- or min-max-normalising lane wrapper would make the hybrid
   query the one-liner the guide presents it as. Recorded in
   `mcp/microbiomekg.skills/reconciliation.md`, which routes in two stages
   instead.
12. **A skill pack is discovered from the *manifest* basename, not the graph's.**
   `mcp/microbiomekg_mcp.yaml` auto-loads `mcp/microbiomekg_mcp.skills/`, so a
   pack named for the graph it documents — `mcp/microbiomekg.skills/` — is
   found only through the list form, `skills: [true, ./microbiomekg.skills]`.
   That half stands: it is a naming convention, not a defect. **The silence
   around it is closed by kglite 0.16.22.** A `skills:` path that does not
   exist used to boot cleanly with *every* skill gone, the bundled methodology
   included, while `--selftest` printed `Selftest PASSED` — it counted tools
   and never counted skills. Now the bad path is a boot error naming what was
   written and where it resolved to, and `--selftest` prints the count and the
   names: `✓ skills: 12 served: amr, cypher_query, drugs, evidence_audit, …`.
   `tests/test_mcp_manifest.py::test_a_skills_path_that_does_not_exist_fails_the_boot`
   is the guard, and the selftest assertion now requires this repo's seven to
   be among the names.

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

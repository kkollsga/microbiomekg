---
name: drugs
description: "TRIGGER for drug questions — 'does this drug inhibit gut
  bacteria', 'was this drug ever tested against it', 'which bacteria metabolise
  it', 'is this T2D association actually a metformin effect', 'what does this
  antibacterial target', 'which taxa did this intervention change'. Read the
  three-legs section first: a measured non-hit is its own relationship here, so
  'no result' and 'tested, no effect' are different answers and only one of them
  is in the graph. SKIP for AMR gene carriage (amr) and for taxon-disease
  evidence itself (taxon_disease_evidence)."
references_tools: [cypher_query]
applies_when:
  graph_has_node_type: [Drug]
---

# Drugs and the microbiome: four legs, and the negative that is a result

Four different claims connect a `Taxon` and a `Drug`, and they are **not**
interchangeable. Say which one you used.

| Leg | Path | The claim |
|---|---|---|
| 1 | `Drug -> ProteinTarget -> Taxon` | the drug binds a protein this organism has |
| 2 | `Taxon -> Intervention -> Drug` | the drug changed this taxon's abundance in a host |
| 3 | `Drug -> Taxon`, direct | the drug did, or did not, stop this isolate growing in culture |
| 4 | `Taxon -> Drug`, direct | this isolate did, or did not, chemically deplete the drug |

**Legs 3 and 4 point opposite ways on purpose.** The agent is on the tail of
each: leg 3 is the drug acting, leg 4 is the bacterium acting. `(d:Drug)-[]->(t:Taxon)`
is the growth screen and nothing else; `(t:Taxon)-[]->(d:Drug)` is the
metabolism screen and nothing else. Never merge them and never read one as the
other — "the drug kills the bug" and "the bug eats the drug" are opposite
findings with opposite clinical readings.

**Each has two relationship types and you must use both.**
`INHIBITS_GROWTH_OF` / `METABOLISES` are hits; `DOES_NOT_INHIBIT_GROWTH_OF` /
`DOES_NOT_METABOLISE` are pairs the screen **tested and found nothing** — a
measurement, not an absence of curation. A query that matches only the first
cannot tell "tested, clean" from "never tested", and those are the two answers a
clinician most needs apart. The four `effect` values are distinct
(`inhibited` / `no-effect` / `metabolised` / `not-metabolised`) so one property
groups the whole measured population without mixing the two screens.

## Leg 3 — the growth screen (Maier 2018, D8)

```cypher
MATCH (d:Drug)-[r:INHIBITS_GROWTH_OF]->(t:Taxon)
WHERE r.drug_class = 'human-targeted drugs'
RETURN d.title AS drug, t.title AS organism, r.nt_code AS isolate,
       r.strain AS strain, r.adjusted_p_value AS adjusted_p,
       r.screen_concentration_um AS screened_at_um,
       r.ic25_um AS ic25_um, r.ic25_qualifier AS ic25_qualifier,
       r.validation_outcome AS validation, r.source_licence AS licence
ORDER BY organism, drug
```

**5,592 `INHIBITS_GROWTH_OF` edges over 399 drugs and 38 taxa** (287 of the 399
approved), and **42,233 `DOES_NOT_INHIBIT_GROWTH_OF` edges**. 1,197 marketed
drugs x 40 human gut isolates, every cell measured; **203 of 835 human-targeted
drugs (24.3%) inhibit at least one**.

The three-outcome question, which is the one to run when a caller names a drug:

```cypher
MATCH (d:Drug {id: $drug_id})
OPTIONAL MATCH (d)-[:INHIBITS_GROWTH_OF]->(t:Taxon)
OPTIONAL MATCH (d)-[:DOES_NOT_INHIBIT_GROWTH_OF]->(u:Taxon)
RETURN count(DISTINCT t) AS inhibited,
       count(DISTINCT u) AS tested_no_effect,
       'anything not in either count was never tested' AS caveat
```

**Four limits to state with any leg-3 answer.**

- **Monoculture, one concentration.** A non-hit is "no growth inhibition at
  20 µM in pure culture", never "no effect on the microbiome". A drug that shifts
  a community through pH, cross-feeding or the host is invisible to this assay.
- **38 taxa, not the gut.** Only those 40 isolates were screened. A taxon with no
  edge was not tested; `WHERE NOT (d)--(t)` is "unknown", not "safe".
- **Strain collapses to species.** Two *B. fragilis* isolates and two *E. coli*
  isolates each land on one taxon as **two parallel edges** — `nt_code`,
  `strain` and `reported_name` keep them apart. Never `count(r)` as a count of
  taxa.
- **Licence.** Every leg-3 edge is `source_licence = 'Maier2018-unstated'`,
  the strictest in the graph. `WHERE r.source_licence <> 'Maier2018-unstated'`
  is the redistributable cut.

**Drug identity is a join, and its route is on the edge.** 842 of the 1,197
screened compounds reach a ChEMBL node (`drug_join` = `name` 455, `atc` 361,
`salt-name` 26); the other 355 are `PRESTWICK:` nodes with `approved = false`.
An `approved = false` drug here may be a marketed drug ChEMBL's subset does not
name — check `d.source` before reading it as "unapproved".

## Leg 1 — the drug acts on a bacterial protein (ChEMBL, D8)

```cypher
MATCH (d:Drug)-[m:HAS_MECHANISM]->(p:ProteinTarget)-[:OF_ORGANISM]->(t:Taxon)
WHERE t.lineage_domain = 'Bacteria'
RETURN d.title AS drug, d.approved AS approved, p.title AS target,
       p.uniprot AS uniprot, t.title AS organism, m.action_type AS action,
       m.evidence_level AS level, m.source_licence AS licence
ORDER BY organism, drug
```

**95 drugs reach 28 bacterial taxa** through 1,493 `OF_ORGANISM` edges over 94
target organisms; **65 of the 95 are approved**. The `Drug` node set is 6,408
(3,120 approved, 297 withdrawn, 378 minted by the two screens), with 1,518
`ProteinTarget`s and 6,984 `HAS_MECHANISM` edges split `in-vitro` 3,153 /
`interventional-rct` 2,059 / `unknown` 1,772.

Report `approved` rather than filtering it away: the 30 unapproved molecules are
what a *mechanism* reading needs and what a *clinical* reading must exclude.

**What this leg is not.** For 28 mostly-pathogen taxa this is an antibacterial's
intended target, not a gut-commensal side effect — and binding a protein is not
the same claim as stopping growth. Where leg 3 covers the same pair, prefer it.

## Leg 2 — an intervention changed a taxon's abundance (gutMDisorder)

```cypher
MATCH (t:Taxon)-[r:ABUNDANCE_CHANGED_BY]->(i:Intervention)
RETURN i.title AS intervention, i.drugbank_id AS drugbank, t.title AS taxon,
       r.direction AS direction, r.evidence_level AS level,
       r.host_species AS host, r.p_value AS p, r.pmid AS pmid
ORDER BY level, intervention
```

**1,380 edges over 220 interventions and 395 taxa**, split `in-vivo-model` 822 /
`interventional-rct` 558. The mouse split is a *rule*, not a reading of each
design: the whole mouse workbook lands as `in-vivo-model` whatever the study
did, because a mouse RCT is not human interventional evidence.

`ABUNDANCE_CHANGED_BY` is deliberately **not** an `ASSOCIATED_WITH`. Do not
merge them, and do not read a direction across them: "this drug increased the
taxon" and "this taxon is increased in this disease" point opposite ways as
often as not — which is the whole of D18 below.

Joining leg 2 to a drug identity:

```cypher
MATCH (t:Taxon)-[r:ABUNDANCE_CHANGED_BY]->(i:Intervention)-[:IS_DRUG]->(d:Drug)
RETURN d.title AS drug, i.title AS intervention, t.title AS taxon,
       r.direction AS direction, r.evidence_level AS level,
       r.host_species AS host, r.pmid AS pmid
ORDER BY drug, taxon
```

**85 edges over 15 drugs and 57 taxa.** The join is thin on purpose: the only
available link is an exact, casefolded, whole-label name match, reaching **15 of
222 interventions**. Accepting `Acetylsalicylic acid` as `ASPIRIN` would invent
an intervention nobody curated.

## The competing-explanation check (D18) — the highest-value use of this layer

Run **both** drug->taxon legs. They answer different questions and the pair is
more informative than either: an abundance shift with no growth inhibition
argues for an *indirect* mechanism.

```cypher
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease {id: $disease_id})
MATCH (drug:Drug {id: $drug_id})
      -[g:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->(t)
OPTIONAL MATCH (t)-[a:ABUNDANCE_CHANGED_BY]->(:Intervention)-[:IS_DRUG]->(drug)
WITH t, collect(DISTINCT r.direction) AS direction_in_disease,
     count(DISTINCT r.study_id) AS disease_studies,
     collect(DISTINCT g.effect) AS growth_effect,
     collect(DISTINCT g.nt_code) AS isolates_screened,
     collect(DISTINCT a.direction) AS abundance_effect
RETURN t.title AS taxon, direction_in_disease, disease_studies,
       growth_effect, isolates_screened, abundance_effect,
       'competing explanation' AS reading
ORDER BY disease_studies DESC
```

Metformin (`CHEMBL:CHEMBL1431`) x type 2 diabetes (`MONDO:0005148`) returns
**32 rows**, and `growth_effect` is `['no-effect']` on **every one**: metformin
was measured against all 38 screened taxa and inhibited none. The abundance leg
independently reaches **21 taxa over 24 edges**, 17 of them with a T2D
association.

**Report the negative as the finding, not as an empty result.** "Metformin does
not inhibit these organisms in culture" is a constraint on the mechanism — it
argues against direct killing and for an indirect route — and it is a stronger
statement than the abundance correlation it sits beside.

**State the limit with the answer.** The published metformin confounders are an
*Escherichia* increase and an *Intestinibacter* decrease — both drug effects,
not T2D signals — plus a *Lactobacillus* increase that reversed under
adjustment. The screen covers three of those four at species level
(*Escherichia coli*, *Lacticaseibacillus paracasei*, *Bifidobacterium*);
***Intestinibacter* was not one of the 40 isolates**, so the most consistent of
the four confounders has no growth measurement here at all. Say so.

Widening past one drug — the question the screen makes askable:

```cypher
MATCH (t:Taxon)-[:ASSOCIATED_WITH]->(:Disease {id: $disease_id})
MATCH (d:Drug)-[g:INHIBITS_GROWTH_OF]->(t)
RETURN d.title AS drug, g.drug_class AS class,
       count(DISTINCT t) AS disease_taxa_inhibited
ORDER BY disease_taxa_inhibited DESC LIMIT 25
```

For T2D: **380 drugs inhibit at least one of the 32 taxa, 186 of them
human-targeted rather than antibacterial.**

The scale of the general problem, worth quoting when a caller is ranking
associations: metformin treatment status was recoverable from microbial
composition, while **metformin-untreated T2D status itself was not**; of 41 drug
categories, 19 associated singly with the microbiome and only **6** survived
multi-drug correction, taking taxonomic associations from 154 to 47.

## Leg 4 — the metabolism screen (Zimmermann 2019, D8)

```cypher
MATCH (t:Taxon)-[r:METABOLISES]->(d:Drug {pref_name: 'SULFASALAZINE'})
RETURN t.title AS organism, r.strain AS strain,
       r.percent_consumed AS percent_consumed,
       r.drug_threshold_percent AS threshold_for_this_drug,
       r.fdr_p_value AS fdr_p, r.incubation_hours AS hours, r.replicates AS n,
       r.gene_locus_tags AS genes, r.source_licence AS licence
ORDER BY percent_consumed DESC
```

**2,575 `METABOLISES` edges over 172 drugs and 66 taxa** (147 of the 172
approved), and **17,479 `DOES_NOT_METABOLISE` edges**. 271 oral drugs x 76 gut
strains, every cell measured by LC-MS at 12 h over four cultures; **172 of the
271 are metabolised by at least one taxon** (the paper's 176 counts four more
that only one refused strain metabolised — see the limits).

The four-outcome question, which is the one to run when a caller names a drug:

```cypher
MATCH (d:Drug {pref_name: 'SULFASALAZINE'})
OPTIONAL MATCH (t:Taxon)-[:METABOLISES]->(d)
OPTIONAL MATCH (u:Taxon)-[:DOES_NOT_METABOLISE]->(d)
OPTIONAL MATCH (d)-[:INHIBITS_GROWTH_OF]->(v:Taxon)
OPTIONAL MATCH (d)-[:DOES_NOT_INHIBIT_GROWTH_OF]->(w:Taxon)
RETURN count(DISTINCT t) AS metabolised_by, count(DISTINCT u) AS tested_untouched,
       count(DISTINCT v) AS inhibits, count(DISTINCT w) AS tested_no_inhibition,
       'anything else was never tested, in either screen' AS caveat
```

**195 drugs and 26 taxa are in both screens**, so for those the four counts are
one answer. Sulfasalazine: 52 metabolised_by, 14 tested_untouched.

**The gene, where identified — no `Gene` node, it is on the edge.**

```cypher
MATCH (t:Taxon)-[r:METABOLISES]->(d:Drug)
WHERE r.gene_locus_tags <> ''
RETURN d.title AS drug, t.title AS organism, r.strain AS strain,
       r.gene_locus_tags AS genes, r.gene_products AS products,
       r.gene_protein_ids AS refseq
ORDER BY drug, organism
```

32 `METABOLISES` edges carry it — **and 5 `DOES_NOT_METABOLISE` edges do too**,
because the genes were found in a gain-of-function library expressed in
*E. coli* and on those five pairs that experiment and the whole-cell screen
disagree. Report the disagreement; it is not a data error.

**Four limits to state with any leg-4 answer.**

- **"Not in this assay" is not "not at all", and the flagship example is a
  negative.** *Eggerthella lenta* reducing digoxin is the textbook result, and
  this screen scored that pair a **non-hit** (4.0% consumed against a 20%
  threshold, FDR p = 0.55) because digoxin reduction needs the *cgr* operon
  under arginine-poor conditions and the screen ran one medium for 12 h. **15
  other taxa** *do* metabolise digoxin here, over 21 screened isolates. Always
  quote `incubation_hours` and the drug's own `drug_threshold_percent` beside a
  negative.
- **66 taxa, not the gut.** Only those 76 strains were screened, and two strain
  names were left **deliberately unresolved** (`Bacteroides WH2`,
  `Bifidobacterium ruminatum`) because NCBI holds two candidates for each — they
  are `UnresolvedTaxon` nodes carrying both ids, and four drugs are metabolised
  only by one of them.
- **Strain collapses to species, so `count(r)` is not a taxon count.**
  *Bacteroides fragilis* metabolises 116 drugs here and no single one of its
  seven isolates metabolised more than 89, because those seven are one node.
  Use `count(DISTINCT r.screen_column)` for strains.
- **Licence.** Every leg-4 edge is `source_licence = 'Zimmermann2019-unstated'`,
  a *different* token from leg 3's `Maier2018-unstated`, so the two screens can
  be excluded independently.

## What is still not here

**No metabolite identity.** The screen detected the products but published them
as mass features (`Bisacodyl_183.0685`) with no name, ChEBI or HMDB id, so leg 4
says *that* a drug was depleted and never *into what*. Do not join it to the
`Metabolite` layer.

**No `Gene` node.** The gene products are edge properties, not entities;
"which taxa carry gene X" is not answerable, and neither screen measured gene
presence per strain.

Pair all of this with the confounder columns on the signatures — `matched_on`,
`confounders`, `antibiotics_exclusion` (see `signature_enrichment`) — which say
which studies already controlled for medication.

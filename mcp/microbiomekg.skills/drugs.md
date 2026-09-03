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

# Drugs and the microbiome: three legs, and the negative that is a result

Three different claims reach a `Taxon` from a `Drug`, and they are **not**
interchangeable. Say which one you used.

| Leg | Path | The claim |
|---|---|---|
| 1 | `Drug -> ProteinTarget -> Taxon` | the drug binds a protein this organism has |
| 2 | `Taxon -> Intervention -> Drug` | the drug changed this taxon's abundance in a host |
| 3 | `Drug -> Taxon`, direct | the drug did, or did not, stop this isolate growing in culture |

**Leg 3 has two relationship types and you must use both.**
`INHIBITS_GROWTH_OF` is a hit; `DOES_NOT_INHIBIT_GROWTH_OF` is a pair the screen
**tested and found nothing** — a measurement, not an absence of curation. A
query that matches only the first cannot tell "tested, clean" from "never
tested", and those are the two answers a clinician most needs apart.

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
target organisms; **65 of the 95 are approved**. The `Drug` node set is 6,385
(3,120 approved, 297 withdrawn, 355 minted by the screen), with 1,518
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

## What is still not here

**No relationship says a bacterium metabolises a drug.** That is D8's other
half — Zimmermann et al., 76 gut bacteria x 271 oral drugs, 176 metabolised —
and it is not loaded. Never answer "which bacteria metabolise this drug" from
leg 1 or leg 3: binding a protein and being killed by a drug are both the
opposite direction of causation.

Pair all of this with the confounder columns on the signatures — `matched_on`,
`confounders`, `antibiotics_exclusion` (see `signature_enrichment`) — which say
which studies already controlled for medication.

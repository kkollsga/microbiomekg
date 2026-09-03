---
name: drugs
description: "TRIGGER for drug questions — 'does this drug affect gut bacteria',
  'which bacteria metabolise it', 'is this T2D association actually a metformin
  effect', 'what does this antibacterial target', 'which taxa did this
  intervention change'. Read the two-legs section first: this graph has a drug
  -> bacterial *protein* leg and an intervention -> *taxon* leg, and neither is
  the drug -> taxon edge most such questions assume. SKIP for AMR gene carriage
  (amr) and for taxon-disease evidence itself (taxon_disease_evidence)."
references_tools: [cypher_query]
applies_when:
  graph_has_node_type: [Drug]
---

# Drugs and the microbiome: two legs, and the edge that is not here

**`MATCH (d:Drug)-[r]-(t:Taxon)` returns 0.** There is no drug-taxon shortcut,
deliberately: "this drug inhibits this bacterium" and "this bacterium
metabolises this drug" are opposite claims, and a graph that collapsed them
into one edge would answer confidently and wrongly. Every route below is two
hops, and the intermediate node is what says which claim it is.

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
target organisms; **65 of the 95 are approved**. The whole ChEMBL layer is
6,030 `Drug`s (3,120 approved, 297 withdrawn), 1,518 `ProteinTarget`s and 6,984
`HAS_MECHANISM` edges split `in-vitro` 3,153 / `interventional-rct` 2,059 /
`unknown` 1,772.

Report `approved` rather than filtering it away: the 30 unapproved molecules
are what a *mechanism* reading needs and what a *clinical* reading must
exclude, and they answer different questions.

**What this leg is not.** For 28 mostly-pathogen taxa this is an
antibacterial's intended target, not a gut-commensal side effect. It does not
answer "does this human-targeted drug perturb my microbiome".

## Leg 2 — an intervention changed a taxon's abundance (gutMDisorder)

```cypher
MATCH (t:Taxon)-[r:ABUNDANCE_CHANGED_BY]->(i:Intervention)
RETURN i.title AS intervention, i.drugbank_id AS drugbank, t.title AS taxon,
       r.direction AS direction, r.evidence_level AS level,
       r.host_species AS host, r.p_value AS p, r.pmid AS pmid
ORDER BY level, intervention
```

**1,380 edges over 220 interventions and 395 taxa**, split `in-vivo-model` 822
/ `interventional-rct` 558. The mouse split is a *rule*, not a reading of each
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
available link is an exact, casefolded, whole-label name match, and it reaches
**15 of 222 interventions**. Accepting `Acetylsalicylic acid` as `ASPIRIN`
would invent an intervention nobody curated. A drug outside those 15 has no
route from `Drug` to `Taxon` — say so rather than reaching through a shared
protein.

## The competing-explanation check (D18) — the highest-value use of this layer

```cypher
MATCH (t:Taxon)-[r:ASSOCIATED_WITH]->(d:Disease {id: $disease_id})
MATCH (t)-[a:ABUNDANCE_CHANGED_BY]->(i:Intervention)-[:IS_DRUG]->(drug:Drug {id: $drug_id})
WITH t, collect(DISTINCT r.direction) AS direction_in_disease,
     collect(DISTINCT a.direction) AS drug_effect,
     a.evidence_level AS drug_level, a.pmid AS drug_pmid,
     count(DISTINCT r.study_id) AS disease_studies
RETURN t.title AS taxon, direction_in_disease, disease_studies,
       drug_effect, drug_level, drug_pmid,
       'competing explanation' AS reading
ORDER BY disease_studies DESC
```

Metformin (`CHEMBL:CHEMBL1431`) x type 2 diabetes (`MONDO:0005148`) reaches
**21 taxa over 24 `ABUNDANCE_CHANGED_BY` edges**, 17 of which also carry a T2D
association; the query returns **19 rows** (two taxa carry a metformin record
from two papers).

**State the limit with the answer.** The published metformin confounders are an
*Escherichia* increase and an *Intestinibacter* decrease — both drug effects,
not T2D signals — plus a *Lactobacillus* increase that reversed under
adjustment. **This graph curates a metformin edge for none of those three.** Of
the named set only *Bifidobacterium* appears. So the query answers with the
taxa this corpus happens to have, not the ones the confounding literature
names.

The scale of the general problem, worth quoting when a caller is ranking
associations: metformin treatment status was recoverable from microbial
composition, while **metformin-untreated T2D status itself was not**; of 41
drug categories, 19 associated singly with the microbiome and only **6**
survived multi-drug correction, taking taxonomic associations from 154 to 47.

Pair this with the confounder columns on the signatures — `matched_on`,
`confounders`, `antibiotics_exclusion` (see `signature_enrichment`) — which
say which studies already controlled for medication.

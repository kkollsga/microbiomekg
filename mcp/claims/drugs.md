# Claims checked in `mcp/microbiomekg.skills/drugs.md`

Every heading below names a section of that skill; the claims under it
are executed against the built graph by `tests/test_skill_claims.py`,
and every number in that section must appear among their expected
values. See `tests/skill_claims.py` for the syntax and the escape
hatches.

## Drugs and the microbiome: four legs, and the negative that is a result

<!-- claim external: 1, 2, 3, 4 — the numbers this skill files its four legs
     under. A structure of the document, not a measurement of the graph. -->

<!-- claim: MATCH (d:Drug)-[r]->(t:Taxon) WITH count(DISTINCT type(r)) AS growth
     MATCH (t2:Taxon)-[r2:METABOLISES|DOES_NOT_METABOLISE]->(:Drug)
     RETURN growth, count(DISTINCT type(r2)) AS metabolism == 2, 2 -->

## Leg 3 — the growth screen (Maier 2018, D8)

<!-- claim: MATCH (d:Drug)-[r:INHIBITS_GROWTH_OF]->(t:Taxon)
     WITH count(r) AS hits, count(DISTINCT d) AS drugs, count(DISTINCT t) AS taxa,
          count(DISTINCT CASE WHEN d.approved THEN d END) AS approved
     MATCH (d2:Drug)-[m:DOES_NOT_INHIBIT_GROWTH_OF]->(:Taxon)
     WITH hits, drugs, taxa, approved, count(m) AS nonhits
     MATCH (d3:Drug)-[g:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->(:Taxon)
     WITH hits, drugs, taxa, approved, nonhits, count(DISTINCT d3) AS screened,
          count(DISTINCT g.nt_code) AS isolates,
          count(DISTINCT CASE WHEN g.drug_class = 'human-targeted drugs' THEN d3 END) AS human,
          count(DISTINCT CASE WHEN g.drug_class = 'human-targeted drugs'
                              AND type(g) = 'INHIBITS_GROWTH_OF' THEN d3 END) AS human_hits
     RETURN hits, drugs, taxa, approved, nonhits, screened, isolates, human_hits,
            human, round(1000.0 * human_hits / human) / 10.0 AS pct
     == 5592, 399, 38, 287, 42233, 1197, 40, 203, 835, 24.3 -->

<!-- claim: MATCH (d:Drug)-[r:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->(t:Taxon)
     WITH count(DISTINCT r.screen_concentration_um) AS concentrations,
          max(r.screen_concentration_um) AS micromolar,
          count(DISTINCT t) AS taxa, count(DISTINCT r.nt_code) AS isolates,
          count(DISTINCT CASE WHEN t.title = 'Bacteroides fragilis' THEN r.nt_code END) AS bfragilis,
          count(DISTINCT CASE WHEN t.title = 'Escherichia coli' THEN r.nt_code END) AS ecoli
     RETURN micromolar, taxa, isolates, bfragilis, ecoli, concentrations
     == 20, 38, 40, 2, 2, 1 -->

<!-- claim: MATCH (d:Drug)-[r:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->()
     RETURN count(DISTINCT CASE WHEN r.drug_join <> 'minted' THEN d END) AS joined,
            count(DISTINCT d) AS screened,
            count(DISTINCT CASE WHEN r.drug_join = 'name' THEN d END) AS by_name,
            count(DISTINCT CASE WHEN r.drug_join = 'atc' THEN d END) AS by_atc,
            count(DISTINCT CASE WHEN r.drug_join = 'salt-name' THEN d END) AS by_salt,
            count(DISTINCT CASE WHEN r.drug_join = 'minted' THEN d END) AS minted
     == 842, 1197, 455, 361, 26, 355 -->

## Leg 1 — the drug acts on a bacterial protein (ChEMBL, D8)

<!-- claim: MATCH (d:Drug)-[m:HAS_MECHANISM]->(p:ProteinTarget)-[:OF_ORGANISM]->(t:Taxon)
     WHERE t.lineage_domain = 'Bacteria'
     RETURN count(DISTINCT d) AS drugs, count(DISTINCT t) AS taxa,
            count(DISTINCT CASE WHEN d.approved THEN d END) AS approved,
            count(DISTINCT CASE WHEN NOT d.approved THEN d END) AS unapproved
     == 95, 28, 65, 30 -->

<!-- claim: MATCH ()-[o:OF_ORGANISM]->(t:Taxon) WITH count(o) AS of_organism,
          count(DISTINCT t) AS target_organisms
     MATCH (d:Drug) WITH of_organism, target_organisms, count(d) AS drugs,
          sum(CASE WHEN d.approved THEN 1 ELSE 0 END) AS approved,
          sum(CASE WHEN d.withdrawn THEN 1 ELSE 0 END) AS withdrawn,
          sum(CASE WHEN d.source <> 'chembl' THEN 1 ELSE 0 END) AS minted
     MATCH (p:ProteinTarget)
     WITH of_organism, target_organisms, drugs, approved, withdrawn, minted,
          count(p) AS targets
     MATCH ()-[m:HAS_MECHANISM]->()
     RETURN of_organism, target_organisms, drugs, approved, withdrawn, minted, targets,
            count(m) AS mechanisms,
            sum(CASE WHEN m.evidence_level = 'in-vitro' THEN 1 ELSE 0 END) AS in_vitro,
            sum(CASE WHEN m.evidence_level = 'interventional-rct' THEN 1 ELSE 0 END) AS rct,
            sum(CASE WHEN m.evidence_level = 'unknown' THEN 1 ELSE 0 END) AS unknown
     == 1493, 94, 6408, 3120, 297, 378, 1518, 6984, 3153, 2059, 1772 -->

<!-- claim: MATCH (d:Drug)-[:HAS_MECHANISM]->(:ProteinTarget)-[:OF_ORGANISM]->(t:Taxon)
     WHERE t.lineage_domain = 'Bacteria' RETURN count(DISTINCT t) AS taxa == 28 -->

## Leg 2 — an intervention changed a taxon's abundance (gutMDisorder)

<!-- claim: MATCH (t:Taxon)-[r:ABUNDANCE_CHANGED_BY]->(i:Intervention)
     RETURN count(r) AS edges, count(DISTINCT i) AS interventions,
            count(DISTINCT t) AS taxa,
            sum(CASE WHEN r.evidence_level = 'in-vivo-model' THEN 1 ELSE 0 END) AS mouse,
            sum(CASE WHEN r.evidence_level = 'interventional-rct' THEN 1 ELSE 0 END) AS rct
     == 1380, 220, 395, 822, 558 -->

<!-- claim: MATCH (t:Taxon)-[r:ABUNDANCE_CHANGED_BY]->(i:Intervention)-[:IS_DRUG]->(d:Drug)
     WITH count(r) AS edges, count(DISTINCT d) AS drugs, count(DISTINCT t) AS taxa,
          count(DISTINCT i) AS joined
     MATCH (every:Intervention)
     RETURN edges, drugs, taxa, joined, count(every) AS interventions
     == 85, 15, 57, 15, 222 -->

## The competing-explanation check (D18) — the highest-value use of this layer

<!-- claim: MATCH (t:Taxon)-[:ASSOCIATED_WITH]->(:Disease {id: 'MONDO:0005148'})
     MATCH (:Drug {id: 'CHEMBL:CHEMBL1431'})-[g:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->(t)
     WITH count(DISTINCT t) AS rows
     MATCH (t2:Taxon)-[a:ABUNDANCE_CHANGED_BY]->(:Intervention)-[:IS_DRUG]->(:Drug {id: 'CHEMBL:CHEMBL1431'})
     WITH rows, count(a) AS edges, count(DISTINCT t2) AS taxa,
          count(DISTINCT CASE WHEN EXISTS { MATCH (t2)-[:ASSOCIATED_WITH]->(:Disease {id: 'MONDO:0005148'}) }
                              THEN t2 END) AS with_t2d
     MATCH (:Drug {id: 'CHEMBL:CHEMBL1431'})-[m:DOES_NOT_INHIBIT_GROWTH_OF]->(t3:Taxon)
     RETURN rows, count(DISTINCT t3) AS screened, taxa, edges, with_t2d
     == 32, 38, 21, 24, 17 -->

<!-- claim: MATCH (d:Drug)-[r:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->(t:Taxon)
     RETURN count(DISTINCT r.nt_code) AS isolates,
            count(DISTINCT CASE WHEN t.title CONTAINS 'Intestinibacter' THEN t END) AS intestinibacter
     == 40, 0 -->

<!-- claim: MATCH (t:Taxon)-[:ASSOCIATED_WITH]->(:Disease {id: 'MONDO:0005148'})
     MATCH (d:Drug)-[g:INHIBITS_GROWTH_OF]->(t)
     RETURN count(DISTINCT d) AS drugs, count(DISTINCT t) AS taxa,
            count(DISTINCT CASE WHEN g.drug_class = 'human-targeted drugs' THEN d END) AS human
     == 380, 32, 186 -->

<!-- claim external: 41, 19, 6, 154, 47 — Forslund 2021's multi-drug correction,
     a published re-analysis of cohorts this graph does not hold. Quoted for
     scale; nothing here can reproduce it. -->

## Leg 4 — the metabolism screen (Zimmermann 2019, D8)

<!-- claim: MATCH (t:Taxon)-[r:METABOLISES]->(d:Drug)
     WITH count(r) AS hits, count(DISTINCT d) AS drugs, count(DISTINCT t) AS taxa,
          count(DISTINCT CASE WHEN d.approved THEN d END) AS approved
     MATCH (t2:Taxon)-[m:DOES_NOT_METABOLISE]->(:Drug)
     WITH hits, drugs, taxa, approved, count(m) AS nonhits
     MATCH (t3:Taxon)-[s:METABOLISES|DOES_NOT_METABOLISE]->(d3:Drug)
     RETURN hits, drugs, taxa, approved, nonhits, count(DISTINCT d3) AS screened,
            max(s.incubation_hours) AS hours == 2575, 172, 66, 147, 17479, 271, 12 -->

<!-- claim external: 76, 176 — Zimmermann 2019's own design and headline: 76
     strains screened, 176 drugs metabolised. The graph holds 66 taxa and 172
     drugs because strains collapse to species and two strain names were left
     unresolved. -->

<!-- claim: MATCH (d:Drug)-[:INHIBITS_GROWTH_OF|DOES_NOT_INHIBIT_GROWTH_OF]->(t:Taxon)
     WITH collect(DISTINCT d) AS growth_drugs, collect(DISTINCT t) AS growth_taxa
     MATCH (t2:Taxon)-[:METABOLISES|DOES_NOT_METABOLISE]->(d2:Drug)
     WITH count(DISTINCT CASE WHEN d2 IN growth_drugs THEN d2 END) AS drugs,
          count(DISTINCT CASE WHEN t2 IN growth_taxa THEN t2 END) AS taxa
     MATCH (d3:Drug {pref_name: 'SULFASALAZINE'})
     OPTIONAL MATCH (m:Taxon)-[:METABOLISES]->(d3)
     OPTIONAL MATCH (u:Taxon)-[:DOES_NOT_METABOLISE]->(d3)
     RETURN drugs, taxa, count(DISTINCT m) AS metabolised_by,
            count(DISTINCT u) AS tested_untouched == 195, 26, 52, 14 -->

<!-- claim: MATCH ()-[r:METABOLISES|DOES_NOT_METABOLISE]->(d:Drug)
     WHERE r.gene_locus_tags <> ''
     RETURN count(r) AS edges, count(DISTINCT d) AS drugs == 37, 20 -->

<!-- claim: MATCH ()-[r:METABOLISES|DOES_NOT_METABOLISE]->() WHERE r.gene_locus_tags <> ''
     RETURN sum(CASE WHEN type(r) = 'METABOLISES' THEN 1 ELSE 0 END) AS hits,
            sum(CASE WHEN type(r) = 'DOES_NOT_METABOLISE' THEN 1 ELSE 0 END) AS misses
     == 32, 5 -->

<!-- claim: MATCH (t:Taxon)-[r:DOES_NOT_METABOLISE]->(d:Drug {pref_name: 'DIGOXIN'})
     WHERE t.title = 'Eggerthella lenta'
     WITH r.percent_consumed AS consumed, r.drug_threshold_percent AS threshold,
          r.fdr_p_value AS fdr, r.incubation_hours AS hours
     MATCH (t2:Taxon)-[m:METABOLISES]->(:Drug {pref_name: 'DIGOXIN'})
     RETURN consumed, threshold, fdr, hours, count(DISTINCT t2) AS taxa,
            count(DISTINCT m.screen_column) AS isolates
     == 4.0, 20, 0.55, 12, 15, 21 -->

<!-- claim: MATCH (t:Taxon)-[r:METABOLISES|DOES_NOT_METABOLISE]->(:Drug)
     WITH count(DISTINCT t) AS taxa
     MATCH (u:UnresolvedTaxon) WHERE u.source = 'zimmermann2019'
     RETURN taxa, count(u) AS unresolved == 66, 2 -->

<!-- claim external: 76, 4 — the screen's 76 strains, and the four drugs
     (ALPRENOLOL, DIPHENYLPYRALINE, IRSOGLADINE MALEATE, MEMANTINE) metabolised
     only by the strain this loader refused to guess at; both are properties of
     the published table, not of a loaded edge. -->

<!-- claim: MATCH (t:Taxon)-[r:METABOLISES]->(d:Drug) WHERE t.title = 'Bacteroides fragilis'
     WITH r.screen_column AS isolate, count(DISTINCT d) AS per_isolate
     WITH count(isolate) AS isolates, max(per_isolate) AS most
     MATCH (t2:Taxon)-[r2:METABOLISES]->(d2:Drug) WHERE t2.title = 'Bacteroides fragilis'
     RETURN count(DISTINCT d2) AS drugs, isolates, most == 116, 7, 89 -->

## What is still not here

<!-- claim: MATCH ()-[r:METABOLISES|DOES_NOT_METABOLISE]->() WHERE r.gene_products <> ''
     RETURN count(DISTINCT r.gene_products) AS products == 20 -->

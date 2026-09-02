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

(Filled from `docs/research/` by the coordinator after the research agents
report.)

## Part C — Pitfalls

(Catalog written by the test agent; each entry names its guarding test.)

## Part D — Acceptance queries

(Finalised after Parts B and C are reviewed.)

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

Every id, name class, delimiter and count below was read out of the real
sources on 2026-09-02 — NCBI `new_taxdump` (2026-09-02 build) and the
BugSigDB `full_dump.csv` export stamped `2026-09-02_20:58_UTC`, 14,846 data
rows. Nothing here is from memory. The fixtures under `tests/fixtures/` are
cut from those same two files, so each example below is reproducible against
the fixture without a network call.

Fixture inventory:

- `tests/fixtures/taxdump_mini/` — 219 nodes (64 taxa of interest + 155
  lineage scaffolding to `root`), 532 name rows, 6 `merged.dmp` rows, 3
  `delnodes.dmp` rows. Every line is copied verbatim from the real dump.
- `tests/fixtures/bugsigdb_mini.csv` — 34 real rows + 8 hand-built
  adversarial rows, in the real 51-column export format including the
  leading licence banner line.

Test modules: `tests/test_reconcile.py` (the taxonomy pitfalls, C1–C9),
`tests/test_ontology.py` (C11, C17, and the ontology-artifact drift guard
C21), `tests/test_build.py` (the end-to-end build, C10, C12–C19) and
`tests/test_loader_contracts.py` (C13's and C16's kglite-engine behaviours,
which run whether or not this repo's code exists).

Test-name convention below: `file::test_name`.

### C1. Name classes — a name is not a key

`names.dmp` has one row per (tax_id, name, name class). The classes that a
resolver may look through are `scientific name`, `synonym`,
`equivalent name`, `genbank synonym` and `includes`. `authority` is **not**
one of them: it holds the citation-decorated form
(`Clostridioides difficile (Hall and O'Toole 1935) Lawson et al. 2016`) and
matching on it would attach papers to strings no author writes.

Real: tax 562 alone carries 16 name rows across six classes, including the
`includes` rows `Achromobacter sp. ATCC 35328` and `bacterium 10a` — names
that are *not* E. coli in any paper, but which NCBI files under 562.

Guard: `tests/test_reconcile.py::test_scientific_name_resolves_exact`,
`::test_includes_class_is_searched`, `::test_lookup_is_case_insensitive`,
`::test_authority_class_is_not_a_lookup_class` (which uses
`Lactobacillus plantari`, a `(sic)` misspelling that exists *only* inside an
`authority` string for 1590 — matching that class would resolve it).

### C2. Homonyms across kingdoms — `first-wins` invents facts

Three genus names in the fixture resolve to more than one taxon, verified in
`names.dmp`:

| name | tax_ids | what they are |
|---|---|---|
| `Bacillus` | **1386**, **55087** | bacterial genus (`Bacillus <firmicutes>`) / stick-insect genus (`Bacillus <walking sticks>`) |
| `Proteus` | **583**, **210425** | enterobacterial genus / the olm, a salamander (`Proteus <salamanders>`) |
| `Morganella` | **581**, **90690**, **108061** | enterobacteria / basidiomycete fungi / scale insects |

NCBI disambiguates in the `unique name` column, which most exports throw
away. `Morganella` is a three-way collision, so even a "if exactly two, take
the bacterial one" heuristic fails.

The resolver must return `status="ambiguous"` with all candidates in
`candidates` and **no** `tax_id`. A first-wins index keyed on lowercase name
would silently file every `Bacillus` signature under a stick insect or a
bacterium depending on file order in `names.dmp`.

Guard: `tests/test_reconcile.py::test_homonym_genus_is_ambiguous`
(parametrised over the three names and their exact candidate tuples).

### C3. Homonyms *within* bacteria — the kingdom heuristic is not enough

C2 invites the fix "prefer the bacterial candidate". It does not work.
`Bacteroides corrodens` is a `synonym` of **both**:

- **539** — `Eikenella corrodens` (Betaproteobacteria), unique name
  `Bacteroides corrodens <b-proteobacteria>`
- **827** — `Campylobacter ureolyticus` (Campylobacterota), unique name
  `Bacteroides corrodens <e-proteobacteria>`

Both are oral/gut bacteria that appear in microbiome papers. Likewise
`Bacillus brevis` is a synonym of **1393** (`Brevibacillus brevis`) and of
**2815668** (`Phalces brevis`, a stick insect).

Guard: `tests/test_reconcile.py::test_intra_bacterial_homonym_is_ambiguous`.

### C4. Renamed taxa — and the ones NCBI kept only in authority form

The rename cases from the announcement, with the tax_id each resolves to and
the *exact* name class the old binomial is filed under:

| name used in papers | tax_id | how NCBI stores the old name |
|---|---|---|
| Clostridium difficile → Clostridioides difficile | **1496** | **authority-decorated `synonym` only** |
| Propionibacterium acnes → Cutibacterium acnes | **1747** | bare `synonym` |
| Ruminococcus gnavus → Mediterraneibacter gnavus | **33038** | bare `synonym` |
| Lactobacillus reuteri → Limosilactobacillus reuteri | **1598** | **authority-decorated `synonym` only** |
| Lactobacillus plantarum → Lactiplantibacillus plantarum | **1590** | **authority-decorated `synonym` only** |
| Lactobacillus rhamnosus → Lacticaseibacillus rhamnosus | **47715** | bare `synonym` |
| Eubacterium rectale → Agathobacter rectalis | **39491** | **authority-decorated `synonym` only** |

This is the sharpest trap in the whole catalog and it is invisible until you
grep the dump. NCBI is **inconsistent**: for 1747, 33038 and 47715 it keeps
both `Propionibacterium acnes` and
`Propionibacterium acnes (Gilchrist 1900) Douglas and Gunter 1946 (Approved Lists 1980)`.
For 1496, 1598, 1590 and 39491 it keeps **only** the decorated form —
`grep -P "\t\|\tClostridium difficile\t\|" names.dmp` returns nothing. A
resolver that indexes name classes literally therefore returns
`unresolved` for *Clostridium difficile*, the single most-cited renamed
organism in the clinical microbiome literature, while happily resolving
*Propionibacterium acnes*. The failure is silent and looks like a data gap.

The fix is a second, normalised index that strips a **recognised authority
tail** (a parenthesised authority, an `Author Year` / `Author et al. Year`
tail, `emend.`, `(Approved Lists 1980)`, `(sic)`), consulted **only when the
exact index misses**. Exact-first is not optional — see C5.

Guard: `tests/test_reconcile.py::test_legacy_binomial_resolves_via_authority_stripping`
(parametrised over all seven rows above, asserting tax_id **and** that the
four decorated-only cases come back `status="synonym"`, not `"unresolved"`).

### C5. Authority stripping must not outrank exact matches

A greedy normaliser — "cut everything from the first capitalised token after
the epithet" — maps `Escherichia coli K-12` to `escherichia coli`, so the
normalised index maps `escherichia coli` to **{562, 83333}** and a
normalised-first resolver reports `Escherichia coli` as **ambiguous**. This
was reproduced on the fixture while writing these tests.

Contract: consult the exact index first and return its answer if non-empty;
consult the normalised index only on a miss. Then `Escherichia coli` → 562
`exact`, `Escherichia coli K-12` → 83333 `exact` (then promoted, C7), and
`Clostridium difficile` → 1496 `synonym`.

Guard: `tests/test_reconcile.py::test_exact_match_beats_normalised_match`.

### C6. Merged and deleted ids in older exports

`merged.dmp` maps a retired id to its survivor; `delnodes.dmp` lists ids that
were withdrawn with no successor. Both appear in exports made before the
change. Real rows in the fixture:

- `1440055 | 1496 |` and `1581190 | 1496 |` — two retired *Clostridioides
  difficile* ids.
- `1129128 | 1598 |`, `299639 | 47715 |`, `83834 | 1590 |`,
  `105824 | 853 |`.
- Deleted, verified absent from both `nodes.dmp` and `merged.dmp`:
  **1009**, **1029**, **1036**.

A merged id must resolve to the survivor with `status="merged"` and
`original_tax_id` preserved — dropping the original loses the ability to
explain why an old paper's id is not in the graph. A deleted id must come
back `status="deleted"` with **no** `tax_id`: inventing one is worse than
admitting the loss. An id in none of the three files (fixture uses
**999999999**) is `unresolved`.

Guard: `tests/test_reconcile.py::test_merged_id_resolves_to_survivor`,
`::test_deleted_id_has_no_tax_id`, `::test_unknown_id_is_unresolved`,
`tests/test_build.py::test_merged_old_id_absent_new_id_present` and
`::test_merged_row_lands_on_the_survivor`.

### C7. Strains and subspecies must promote, keeping the original

- **83333** `Escherichia coli K-12`, rank `strain`, parent **562** rank
  `species`.
- **1682** `Bifidobacterium longum subsp. infantis`, rank `subspecies`,
  parent **216816** `Bifidobacterium longum`, rank `species`.

With `rank_ceiling="species"` both promote to the parent with
`status="promoted"`, `tax_id` = the species, `original_tax_id` = the strain
or subspecies id and `original_rank` = `"strain"` / `"subspecies"`. Losing
`original_tax_id` makes the promotion unauditable; not promoting leaves the
graph with a `:Taxon` that no species-level query finds.

A taxon already at or above the ceiling is **not** promoted: `Bacillus`
(1386, `genus`) and `Lachnospiraceae` (186803, `family`) come back `exact`.

Guard: `tests/test_reconcile.py::test_strain_promotes_to_species`,
`::test_subspecies_promotes_to_species`, `::test_strain_name_promotes_too`,
`::test_rank_at_or_above_ceiling_is_not_promoted`,
`::test_rank_ceiling_genus_promotes_a_species`,
`tests/test_build.py::test_below_species_rows_land_on_the_species_node`.

### C8. Rank-less nodes break naive lineage walking

The fixture's 219 nodes carry 25 distinct rank strings. Walking "up until you
hit a rank" or "the parent is always the next standard rank" fails on:

- **1** `root`, rank `no rank`, whose parent is **itself** (`1 | 1 | no rank`).
  A promotion loop with no self-parent guard hangs here — and the 120 s
  pytest ceiling is what turns that into a *failed* test rather than a
  wedged suite.
- **131567** `cellular organisms`, rank `cellular root` — a rank string most
  rank tables do not contain.
- 23 nodes at rank `clade` (e.g. **1783257** in the *Akkermansia muciniphila*
  lineage) and 6 more at `no rank`, sitting *between* standard ranks.
- **48479** (`environmental samples`, `no rank`) is the parent of **77133**
  `uncultured bacterium`, and **2646097** (`no rank`) the parent of **29523**
  `Bacteroides sp.` — so "parent of a species is a genus" is false in the
  fixture, not just in theory.

The promotion loop must be driven by an explicit *below-ceiling* rank set and
must terminate on a self-parent, never by assuming a rank ladder.

Guard: `tests/test_reconcile.py::test_promotion_terminates_at_self_parent_root`,
`::test_rankless_and_clade_nodes_do_not_break_resolution`,
`::test_species_whose_parent_is_rankless_still_resolves`,
`tests/test_build.py::test_taxon_lineage_is_walkable_to_root`.

### C9. Placeholder and bracketed names are real nodes, not junk

All four of these are `scientific name` rows in the real dump and all four
are in the fixture:

- **77133** `uncultured bacterium` — 13 BugSigDB rows cite it. It is a real
  tax_id and a real signature member, but it is not an organism anyone can
  act on. It must resolve (to 77133) and be *flagged*, not dropped.
- **29523** `Bacteroides sp.` — a genus-level placeholder filed at rank
  `species`. Its `sp.` suffix means "some species of"; treating it as a
  species sibling of *Bacteroides fragilis* double-counts the genus.
- **1512** `[Clostridium] symbiosum` — the brackets are NCBI's marker for
  "the name is misapplied; this is not really *Clostridium*", and they are
  **part of the scientific name string**. Whether the plain binomial also
  resolves is a *per-taxon curation fact*, not a rule: for 1512 NCBI happens
  to also file `Clostridium symbiosum` as a `synonym`, so it resolves without
  any unbracketing step — but nothing guarantees that for the next bracketed
  taxon. Never write an unbracketing normaliser; look the name up and let
  `names.dmp` answer.
- **2500537** `Candidatus Cibiobacter qucibialis` — `Candidatus` is a status
  prefix, not a genus. Stripping it yields `Cibiobacter qucibialis`, which is
  not in `names.dmp`.

Contract: resolve them exactly as written, and carry a flag so
`Part D` queries can exclude them; never silently normalise the brackets or
the `Candidatus` prefix away, and never drop the row.

Guard: `tests/test_reconcile.py::test_placeholder_names_resolve_verbatim`,
`::test_unbracketed_name_resolves_through_the_synonym_row`,
`::test_stripping_the_candidatus_prefix_does_not_match`.

### C10. BugSigDB: the taxon column is a *lineage path*, not a taxon list

The export's own encoding, read off the real file:

- The file starts with a **licence banner line** before the header. Reading
  it with `pd.read_csv(path)` gives a one-column frame; `skiprows=1` is
  required.
- `NCBI Taxonomy IDs` holds **`;`-separated taxa**, and each taxon is a
  **`|`-separated lineage path whose last element is the taxon**. Example
  from `bsdb:22728514/4/1`:
  `3379134|1224|1236|2887326|468|469;1783272|201174|1760|85009|31957|1912216|33011;…`
  → the taxa are **469**, **33011**, … — not 3379134, 1224, 1236.
- Splitting on `|` as well as `;` yields **9,458** distinct ids across the
  full dump where the correct answer is **8,152** — 1,306 phantom taxa, every
  one of them an *ancestor* that the study never reported, each acquiring
  edges it did not earn.
- The parallel `MetaPhlAn taxon names` column uses a **different outer
  delimiter**: `,` between taxa, `|` between ranks (`k__…|p__…|s__…`). The
  two columns zip positionally (verified: **0** length mismatches over the
  14,225 rows that have both), but only if each is split on its own
  delimiter.
- Missing is the literal string `"NA"`, never an empty cell — so
  `pd.read_csv(..., keep_default_na=False)` plus an explicit `"NA"` check,
  otherwise `"NA"` becomes `NaN` and a float column (C16).

Guard: `tests/test_build.py::test_only_leaf_taxa_are_cited`,
`::test_ancestors_acquire_no_association_edges`. Note the ancestors are
legitimately *present* as `:Taxon` nodes — `HAS_PARENT` has to be walkable —
so the assertion is that they carry no `REPORTED_BY` and no
`ASSOCIATED_WITH` edge, not that they are absent.

### C11. BugSigDB: `Study design` is multi-valued *and* contains commas

`Study design` is comma-joined, and one of its atomic values contains a
comma: `cross-sectional observational, not case-control`. So
`bsdb:...` rows literally read
`laboratory experiment,cross-sectional observational, not case-control`.

Naively splitting on `,` over the full dump produces the phantom design
values `cross-sectional observational` and `not case-control`, giving 9
tokens where the real vocabulary is 7 designs plus `NA`. The seven atomic
values, all present in the fixture, are:

`case-control`, `cross-sectional observational, not case-control`,
`laboratory experiment`, `prospective cohort`,
`time series / longitudinal observational`,
`randomized controlled trial`, `meta-analysis`.

The split must be against that known vocabulary (longest-match first), not
on the delimiter. `EVIDENCE_LEVELS` must have a key for each of the seven.

Guard: `tests/test_ontology.py::test_evidence_levels_cover_every_fixture_design`,
`::test_evidence_levels_cover_the_whole_bugsigdb_vocabulary`,
`::test_naive_comma_split_is_not_the_design_vocabulary`,
`::test_the_multi_design_fixture_row_splits_into_two_known_designs`,
`::test_evidence_levels_values_are_the_declared_levels`.

### C12. BugSigDB: direction is relative to Group 1, and disagreement is data

`Abundance in Group 1` ∈ {`increased`, `decreased`, `NA`} (7,741 / 6,683 /
422 in the full dump). It is the abundance in **Group 1** relative to Group
0, and `Group 0 name` / `Group 1 name` are free text — `bsdb:39/2/1` has
Group 0 `after excercise` and Group 1 `youth Neck before`, i.e. Group 1 is
*not* reliably the case arm. So `increased` maps to "increased in Group 1",
and the group names must ride along on the edge; it may not be flattened to
"increased in disease".

Across the full dump **8,818** (taxon, condition) pairs carry *both*
`increased` and `decreased` from different studies — for example
(**410072**, `Obesity`). Collapsing them into one signed edge destroys a
real, reportable disagreement, which is exactly the A1/A2 contract.

Guard: `tests/test_build.py::test_direction_is_stored_per_association`,
`::test_conflicting_directions_survive_as_separate_edges`.

### C13. Cross-source dedupe: two studies are two edges

`bsdb:23459324/3/2`, `bsdb:23459324/4/1` and `bsdb:23459324/6/1` are three
signatures from **the same study, same PMID (23459324), same condition
(Obesity, MONDO:0011122), same taxon (1598 *Limosilactobacillus reuteri*),
same direction (increased)** — but different experiments with different
sample sizes (64/108, 64/32, 79/140). They are three pieces of evidence, not
one.

Contract: a `Signature` node per source row, and taxon–condition association
edges hung off the signature. A `MERGE`-style collapse on (taxon, condition)
would turn 3 into 1 and make "list the supporting studies" (A1) unanswerable.
The count that proves it: the fixture's 42 rows resolve to **53** distinct
taxa but **71** taxon-report edges.

Guard: `tests/test_build.py::test_same_pair_from_three_signatures_is_three_edges`,
`::test_conflicting_directions_survive_as_separate_edges`,
`::test_golden_edge_counts`.

**And the loader will silently undo it at scale.** Reproduced against kglite
0.16.21 while writing these tests: the blueprint's junction-CSV loader streams
in chunks and **deduplicates parallel edges from the second chunk onwards**.
With `KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE=3` and a junction CSV holding ten
identical `A1 -> B1` pairs, the built graph has **three** edges. The default
chunk is 100,000 rows and the full-dump `taxon_disease.csv` is ~118k rows of
deliberately parallel edges, so a default build drops every repeat of a pair
it saw in the first chunk — precisely the evidence multiplicity this whole
document exists to protect, removed with no warning and no error. The build
command must raise the chunk size above the row count.

Guard: `tests/test_loader_contracts.py::test_junction_loader_keeps_parallel_edges`
and `::test_junction_loader_drops_parallel_edges_beyond_one_chunk` — the
second pins the *bug*, deliberately not as an xfail, so a kglite release that
repairs it turns the test red and the chunk-size override can be removed.

### C14. Disease identity: the column named `EFO ID` is not EFO, and not disease

Real prefixes in that one column, counted over the fixture's 20 distinct
terms: `EFO` (9), `MONDO` (5), `CHEBI` (2), `EXO` (1), `GSSO` (1), `HP` (1),
`NCBITAXON` (1). Over the full dump it also carries `GO:` and `ENVO:`. So:

- **Not one ontology.** `MONDO:0005575` (Colorectal cancer) and
  `EFO:0002755` (Diet) live in the same column.
- **Not all diseases.** `CHEBI:33281` (`Antimicrobial agent`) is a chemical,
  `EXO:0000114` (`Socioeconomic status`) an exposure, `HP:0002745` (`Oral
  leukoplakia`) a phenotype, `GSSO:000707` a social attribute, and
  `NCBITAXON:568703` (`Lactobacillus rhamnosus GG`, on `bsdb:23339708/4/2`)
  is **an organism** — a probiotic used as the exposure. Typing all of them
  `:Disease` puts a *Lactobacillus* strain in the disease list.
- **Both `Condition` and `EFO ID` are comma-multi-valued**, and they do not
  always agree: over the full dump **42 rows** have different comma counts in
  the two columns, so a positional zip is provably wrong for those rows. Worse,
  the id string `MONDO:0024647,MONDO:0008171` appears with condition
  `Nephrolithiasis,Urolithiasis` on one row and `Urolithiasis,Nephrolithiasis`
  on another — the same id order under two label orders, so the zip is not
  merely incomplete, it is *contradictory*.
- **Same id, two labels**: `MONDO:0002009` appears as both
  `Major depressive disorder` and `Unipolar depression`. The id is the key;
  the label is one observed spelling among several.
- **Two ids, near-same condition**: the fixture has `MONDO:0005575`
  (Colorectal cancer, `bsdb:25104642/3/2`) and `MONDO:0024331` (Colorectal
  carcinoma, `bsdb:25432777/2/2`). These are *not* the same term and must not
  be merged by string similarity — but a Part D query for colorectal disease
  has to find both, which is what the ontology's `is_a` forest is for.

Contract: node type is chosen by the id's **prefix**, never by the column
name; the free-text `Condition` is stored as an observed label, not as the
key; the label↔id association is taken as a set per row, never zipped by
position.

Guard: `tests/test_build.py::test_condition_terms_keep_their_source_ontology`,
`::test_non_disease_terms_are_distinguishable`,
`::test_two_colorectal_terms_stay_distinct`,
`::test_multi_condition_row_links_to_both_terms`.

### C15. Paper identity: PMID is not always there, and DOI is not normalised

- **58 rows** in the full dump have `PMID = NA`; the fixture keeps 5, from
  **5 distinct studies** (`Study 11`, `Study 39`, `Study 513`, `Study 562`,
  and the adversarial `Study ADV7`). Keying `:Paper` on PMID alone maps all
  five to one node called `NA` — five different papers merged into one, with
  every edge misattributed. Over the full dump that is **12 distinct studies**
  collapsing into one node.
- **43 rows** have no PMID but *do* have a DOI (`bsdb:513/1/1` →
  `https://doi.org/10.3390/applmicrobiol1020014`).
- `bsdb:11/1/1` has **neither** PMID nor DOI nor URL. Its only identity is
  BugSigDB's own `Study` id, which is therefore the required fallback key.
- **DOIs are not normalised in the source**: bare (`10.3748/wjg.15.2887`),
  full URL (`https://doi.org/10.1186/s13099-022-00527-8`), and DataCite
  (`10.5281/zenodo.7544549`) forms all appear. The same paper reached from
  two sources under two DOI spellings becomes two `:Paper` nodes.

Contract: paper key = PMID if present, else normalised DOI (lowercased, URL
prefix stripped), else `study:<BugSigDB Study id>`. The fixture's 42 rows
yield **38** distinct papers under that rule and **34** under "PMID only,
NA collapses".

Guard: `tests/test_build.py::test_papers_without_pmid_do_not_collapse`,
`::test_doi_forms_are_normalised`.

### C16. Integer id pitfalls in kglite

Measured against kglite 0.16.21, not assumed:

- A pandas column that gains a `NaN` becomes `float64`. Passed as
  `unique_id_field`, kglite coerces whole-number floats back to int (the
  "Float IDs" note in `KGLite/docs/python/guides/blueprints.md`) — **but the
  NaN row itself is skipped**, with `nodes_skipped: 1` and `has_errors: True`
  in the returned dict and a `UserWarning` on stderr. Both are trivially
  ignorable. Nothing raises. This is C18 wearing a different hat: the
  loader's return dict must be read, not discarded.
- On a **property**, the float survives: a `Group 1 sample size` column with
  one `NA` stores `15.0`, and — the part that bites later — **fixes the
  property's schema type to `Float64` for the whole graph**. A subsequent
  load of the same property from a clean `Int64` column fails with
  `Type mismatch for property 'n1': existing schema has 'Float64', but data
  has 'Int64'`. The first CSV loaded wins, forever. Cast sample sizes to a
  nullable `Int64` before the first `add_nodes`.
- kglite stores an integer id as a **compact 32-bit key**, falling back to a
  full 64-bit key when any value is outside `0..2**32-1`. NCBI tax_ids are
  comfortably inside that (the fixture's largest is 2,815,668; NCBI's current
  maximum is ~3.8M), so `tax_id` stays on the fast path — but only while it
  is an *int*. A tax_id that reaches kglite as the **string** `"562"` lands
  in a different key space, and `WHERE t.tax_id = 562` then matches nothing
  while `= "562"` matches — a silent empty result, not an error. Parse the
  last element of every lineage path with `int()` at the edge of the loader.

Guard: `tests/test_build.py::test_tax_ids_are_integers_not_strings`,
`::test_sample_sizes_are_integers_not_floats`,
`::test_missing_sample_size_is_absent_not_the_string_NA`, and — against the
engine directly — `tests/test_loader_contracts.py::test_integer_ids_survive_a_nan_in_the_column`,
`::test_a_nan_pins_a_property_to_float_for_the_whole_graph`,
`::test_a_string_tax_id_does_not_match_an_integer_comparison`.

### C17. Evidence completeness must be countable, not invisible

The A1 contract is that an edge with unknown evidence exists but is
*countable*. Over the fixture's **73** `ASSOCIATED_WITH` edges, the per-field
gap census is:

| evidence property | edges lacking it |
|---|---|
| `pmid` | 6 |
| `statistical_test` | 6 |
| `group_1_size` | 5 |
| `sequencing_type` | 5 |
| `study_design` | 3 |
| `group_0_size` | 2 |
| `direction` | 1 |
| `evidence_level`, `source`, `signature_id` | 0 (always derived/written) |
| **edges missing at least one** | **16** (21.9%) |

Two things about the instrument, both verified against kglite 0.16.21:

- `CALL ontology_audit()` counts **edges** missing at least one required
  property — so its `violations` column is the union (16), never the sum of
  the column above. Its columns are `rule, severity, violations, exempted,
  total, pct`.
- `CALL edge_property_violation()` emits **one row per violating edge**,
  naming only the *first* missing property in declaration order — not one row
  per missing field. It tells you *which* edges are incomplete; the per-field
  table above needs a Cypher query
  (`MATCH ()-[r:ASSOCIATED_WITH]->() WHERE r.<prop> IS NULL`). A gap report
  built from the procedure alone silently under-counts every field but the
  first.

Setting `enforcement: "error"` on the association's `required_properties`
would fail the build on upstream data reality; per KGLite's ontology guide
those stay `warn`. Rules over fields *this repo* writes (`REPORTED_BY`'s
`reported_name` / `resolution_status` / `source`) are legitimately `error` —
a violation there is our bug, not BugSigDB's.

One hole the table hides: `evidence_level` is never absent because the
derivation returns the string `"unknown"` when the design is missing. A
required-property check cannot see it, so "how many edges have an unknown
evidence level" is a `WHERE r.evidence_level = 'unknown'` query, not an audit
row. That is a deliberate choice (never silently "observational"), but it
means the audit's 21.9% is a floor, not the whole gap.

Guard: `tests/test_ontology.py::test_every_evidence_property_is_required_on_associations`,
`::test_evidence_rules_are_not_enforcement_error`,
`tests/test_build.py::test_ontology_audit_counts_the_missing_evidence_edges`,
`::test_edge_property_violation_names_the_evidence_free_row`,
`::test_per_field_evidence_gap_census`,
`::test_audit_denominators_are_not_zero`.

### C18. Silent drops — every input row must be accounted for

The failure mode that hides all the others: a row that resolves to nothing
and leaves no trace. Every row must land in exactly one of three places —
an edge, a record in `unresolved_taxa.csv`, or an explicit, reported filter
count. The three sinks must sum to the input row count.

Concrete leaks in this data:

- `bsdb:19533811/2/NA` (a real row) has `NCBI Taxonomy IDs = NA`,
  `MetaPhlAn taxon names = NA` and `Abundance in Group 1 = NA` — an *empty
  signature*. It contributes zero taxon edges. **621** rows of the full dump
  are like it. That is a legitimate filter, but it must be counted, not
  absorbed.
- The three adversarial rows that must appear in `unresolved_taxa.csv` with
  the stated status: `bsdb:adv-deleted/1/1` (tax 1009, `deleted`),
  `bsdb:adv-ambig/1/1` (`Bacteroides corrodens`, `ambiguous`, candidates
  539 and 827), `bsdb:adv-unknown/1/1` (tax 999999999, `unresolved`).
- kglite's own quiet drops: `add_nodes` / `add_connections` return
  `nodes_skipped` / `has_errors` and emit `UserWarning`s (target node not
  found, null FK, type mismatch) rather than raising. A blueprint build that
  does not read them reports success while dropping edges.
- **The leak these guards actually caught (2026-09-02).** The first
  implementation read only `NCBI Taxonomy IDs` and never fell back to
  `MetaPhlAn taxon names`, so the two name-only adversarial rows lost their
  taxa with no counter anywhere: 72 mentions reported instead of 74, 2
  unresolved records instead of 3, 72 association edges instead of 73. In the
  *current* BugSigDB export the two columns are always `NA` together (621
  rows, both), so nothing in the real data would have exposed it — but it
  means `resolve(name=...)`, the half of the interface that exists for the C4
  rename problem, was dead code, and the next source (HMDB, CARD, KEGG) gives
  names, not tax_ids. Fixed the same day; the adversarial rows are what
  keep it fixed.

`TaxonomyIndex.resolve` never raises — which is right, and is exactly why a
`Resolution` whose status is not `exact`/`synonym`/`merged`/`promoted` must
be written to the unresolved sink by the caller.

Guard: `tests/test_build.py::test_every_taxon_mention_is_accounted_for`,
`::test_adversarial_rows_are_in_the_unresolved_report`,
`::test_ambiguous_record_lists_its_candidates`,
`::test_unresolved_taxa_are_still_joined_to_their_signature`,
`::test_empty_signature_row_exists_but_reports_nothing`,
`::test_name_only_rows_are_resolved_not_ignored`,
`::test_every_input_row_became_a_signature`.

### C19. Golden counts, so "it built" is not the assertion

A build test that asserts `count > 0` passes on a graph that lost 90% of its
rows. The fixture is small enough to state exactly what it must produce.
Every number was derived **twice, independently** — once from
`bugsigdb_mini.csv` + `taxdump_mini/` in the test module's own terms, once by
reading the pipeline's output — and the two agree.

| node type | golden | | relationship | golden |
|---|---|---|---|---|
| `Signature` | **42** | | `HAS_PARENT` | **142** |
| `Study` | **38** | | `REPORTED_BY` | **74** |
| `Paper` | **33** | | `ASSOCIATED_WITH` | **73** |
| `Disease` | **20** | | `IN_CONDITION` | **43** |
| `BodySite` | **9** | | `AT_BODY_SITE` | **44** |
| `Taxon` | **143** | | `PART_OF_STUDY` | **42** |
| `UnresolvedTaxon` | **3** | | `PUBLISHED_AS` | **33** |

and the derived quantities:

| quantity | golden |
|---|---|
| input rows | **42** (34 real + 8 adversarial) |
| taxon mentions in | **74** |
| taxa some signature named | **53** |
| lineage ancestors carried for `HAS_PARENT` | **90** (143 − 53) |
| unresolved records | **3** |
| association edges missing ≥1 evidence field | **16** |

Three of these numbers are where the guards actually bit during this
session's first run against the implementation: `UnresolvedTaxon` was **2**,
`REPORTED_BY` **72** and `ASSOCIATED_WITH` **72**, because the loader read
only the `NCBI Taxonomy IDs` column and ignored the taxon *names* — see C18.

`Taxon` is 143 rather than 53 because the lineage has to stay walkable: the
90 extra nodes are ancestors, and they must carry **no** `REPORTED_BY` and
**no** `ASSOCIATED_WITH` edge (C10). `Paper` is 33 rather than 38 because
five studies have no PMID and correctly get no `:Paper` at all (C15).

Guard: `tests/test_build.py::test_golden_node_counts`,
`::test_golden_edge_counts`, `::test_only_leaf_taxa_are_cited`,
`::test_shortest_path_taxon_to_disease`,
`::test_shortest_path_between_two_co_reported_taxa`,
`::test_taxon_lineage_is_walkable_to_root`.

### C20. The ontology artifact drifts from the ontology module

`blueprint.json` gates the build on a *file*, `ontology.json`; the document
is *edited* in `microbiomekg/ontology.py`. They drifted within a day of both
existing: the checked-in file required `group0_sample_size`,
`group1_sample_size` and `source_id` while the module (and the prep scripts)
had moved to `group_0_size`, `group_1_size` and `signature_id`.

A drifted artifact is worse than no artifact. The gate does not fail loudly —
it audits property names nothing writes, so it reports a violation on
*every* edge for a field that does not exist, while the fields that really
are missing go uncounted. The audit stays green-ish, the number moves, and
nothing says why.

Contract: `ontology.json` is generated (`python -m microbiomekg.ontology`)
and never hand-edited, and a test compares it to the module.

Guard: `tests/test_ontology.py::test_the_checked_in_ontology_json_matches_the_module`.

### C21. Interface gaps this catalog exposes

Recorded here because they are contract changes, not test bugs.

1. **`Resolution` has no way to say "resolved, but not an organism".** C9's
   placeholder taxa — `uncultured bacterium` (77133), `Bacteroides sp.`
   (29523), `Candidatus Cibiobacter qucibialis` (2500537) — resolve
   *exactly*, yet are not actionable. Nothing in the field set distinguishes
   them from *Escherichia coli*, so Part D queries must re-derive it from the
   name string, which is the string-matching this document argues against.
   **Recommendation: add a boolean (`placeholder`), do not overload
   `status`** — the taxon *is* resolved, and collapsing the two would lose
   the difference between "77133 is a real id" and "the name matched
   nothing".
2. **No status for "resolved only after normalisation".** C4's four
   decorated-only cases come back `status="synonym"`, which is true but does
   not record that an authority tail had to be stripped. `note` carries it
   today, and
   `tests/test_reconcile.py::test_decorated_only_synonym_records_the_normalisation`
   pins that, so the audit trail exists — but it is prose, not a field, and
   nothing can aggregate it.
3. **`rank_ceiling` says nothing about the rank vocabulary.** The 219-node
   fixture alone carries 25 distinct rank strings including `clade`,
   `no rank` and `cellular root`. The *below-ceiling* set has to be
   enumerated explicitly, and belongs in `docs/model.md`: "above species" is
   not a total order over NCBI's rank strings.
4. **`reported_rank` on the edge is the source's claim, not NCBI's.** Both
   below-species adversarial rows use MetaPhlAn's `t__` prefix, so both land
   as `reported_rank = "strain"` even though 1682 is a `subspecies` in
   `nodes.dmp`. That is defensible — it is what the source said — but it
   means the NCBI rank of a promoted taxon survives only inside the prose of
   `resolution_note` (`"promoted from 1682 (subspecies) to 216816
   (species)"`). A separate `original_rank` column on the edge would make it
   queryable.
5. **`ONTOLOGY` does not name its association relationships.**
   `tests/test_ontology.py` has to *infer* which relationships carry the
   evidence contract (it takes those requiring both a direction and a study
   design) so it can hold them to `warn` while letting this repo's own
   `REPORTED_BY` sit at `error`. An explicit `ASSOCIATION_RELATIONSHIPS`
   tuple would turn a heuristic into a declaration.
6. **`CALL edge_property_violation()` under-reports.** One row per violating
   edge, naming only the first missing property — see C17. Anything that
   needs a per-field gap census must use Cypher instead, and a reader who
   assumes otherwise will report a confidently wrong breakdown.

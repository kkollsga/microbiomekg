# MicrobiomeKG

A microbiome knowledge graph on [kglite](https://github.com/kkollsga/kglite),
with the evidence model as the point: every association edge carries its study
design, direction, sample sizes and citing paper, and the measured negatives —
"tested and nothing happened" — are kept as their own relationships rather than
folded away.

Three verbs over one data directory, from Python or the shell:

```python
import microbiomekg as mkg
mkg.status("./data")      # per source: absent / present / stale / manual, with the fix
mkg.fetch("./data")       # fills what it can; the browser-only steps come back as data
mkg.build("./data")       # builds from what is present; .graph is a kglite graph
```

```bash
microbiomekg status --data ./data
microbiomekg build  --data ./data
microbiomekg serve  --graph graph/microbiomekg.kgl     # the MCP server, read-only
```

No data and no built graph ships: 26% of evidence-bearing edges have no
redistribution permission, so what ships is the pipeline.

```{toctree}
:maxdepth: 2
:caption: Guides

usecases-and-pitfalls
queries-by-task
model
sources
evaluation
benchmarks
```

```{toctree}
:maxdepth: 1
:caption: Design notes

design/library-pipeline
design/release-readiness
design/capability-gaps
```

```{toctree}
:maxdepth: 1
:caption: Research

research/researcher-workflows
research/existing-graphs-and-schemas
research/source-formats
```

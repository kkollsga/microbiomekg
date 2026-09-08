# MicrobiomeKG

A microbiome knowledge graph on [kglite](https://github.com/kkollsga/kglite),
with the evidence model as the point: every association edge carries its study
design, direction, sample sizes and citing paper, and the measured negatives —
"tested and nothing happened" — are kept as their own relationships rather than
folded away.

Prepare, fetch and build over one data directory:

```python
import microbiomekg as mkg
data = "./my-data"
mkg.prepare(data)                 # create input directories and print what each file needs
mkg.fetch(data, missing=True)     # fetch missing automatic inputs, then report again
result = mkg.build(data)          # build from what is present; no file saved by default
```

```bash
.venv/bin/microbiomekg status --data ./my-data --create
.venv/bin/microbiomekg fetch  --data ./my-data --missing
.venv/bin/microbiomekg build  --data ./my-data
.venv/bin/microbiomekg serve --graph graph/microbiomekg.kgl  # the MCP server, read-only
```

No data and no built graph ships: 26% of evidence-bearing edges have no
redistribution permission, so what ships is the pipeline.

```{toctree}
:maxdepth: 2
:caption: Guides

getting-started
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

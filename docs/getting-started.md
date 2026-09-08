# Getting started

Install MicrobiomeKG from PyPI, then choose one directory for the raw inputs:

```bash
python -m pip install microbiomekg
```

Use a virtual environment if you want to isolate it from other Python packages.

## Prepare, fetch, build

The normal shell flow is:

```bash
microbiomekg status --data ./my-data --create
microbiomekg fetch --data ./my-data --missing
microbiomekg status --data ./my-data
microbiomekg build --data ./my-data
```

The first command creates the raw-input parent directories and shows a table
with one row per dataset: availability, file size and age. For a dataset with
several inputs, size is their total size on disk and age is the oldest local
file. Availability is `yes`, `no`, or `partial` with the present/required count.
Only missing files and files older than the threshold get a URL and expected
filename below the table. Shared inputs appear once in those details.

The default threshold is 30 days. Adjust it with
`status --data ./my-data --max-age-days 90`, or
`mkg.prepare(data, max_age_days=90)` in Python. CLI and Python `fetch` accept the
same report option. The threshold controls the report only; `fetch --missing`
still selects missing inputs, not old ones. Directory creation is the only
write performed by `status --create`; plain `status` is read-only.

`fetch --missing` runs the automatic fetchers needed for currently missing
default inputs, deduplicating inputs shared by sources. It prints the report
again afterward, including anything that still needs manual work. Downloads
may be partial: rerun the command after an interruption. A selected source's
existing fetcher may also check or update its other files. If all default
inputs are already complete, no fetcher runs.

Some inputs cannot be fetched end to end: HMDB and MiMeDB require browser
downloads, and MASI's origin has an expired certificate. Follow the URL and
destination printed for each file. For HMDB, save the downloaded ZIP in
`./my-data/raw/hmdb/`, then extract `hmdb_metabolites.xml` into that same
directory. The HMDB fetcher detects a ZIP placed there but does not extract it. The graph can still be built from the
sources that are present; its report names every skipped source and reason.

KEGG is licence-gated and is not selected by `--missing`. Select it explicitly
with `--missing --only kegg` when you need it. A bare `fetch` retains the
full-fetch behaviour, including references and KEGG.

## The same path from Python

```python
import microbiomekg as mkg

data = "./my-data"
prepared = mkg.prepare(data)             # create=True by default
mkg.fetch(data, missing=True)
result = mkg.build(data)
graph = result.graph
```

`prepare` creates the input directories, prints the same dataset table and conditional download details, and returns a `dict[str, SourceStatus]`. It never downloads.
Use `mkg.prepare(data, create=False)` for a report without directory creation,
or `mkg.status(data)` for the silent, read-only status objects. Each
`SourceStatus.files` tuple contains `InputFile` records with local metadata and
acquisition details.

Age means time since a file's local modification time, not its upstream release
date. `stale` means its size
does not match the size recorded by the fetch manifest. Status does not check
for a newer upstream release or verify a digest, and `present` means the file
exists rather than that its contents are valid; `build` performs content
validation. Python builds keep the graph in memory and do not save a `.kgl`
file unless you pass `save=True` (and optionally `out=...`).

"""Data preparation, inspection, fetching and building from Python.

One directory is the entire input (``docs/design/library-pipeline.md``): raw
files under ``<data_dir>/raw/<source>/``, and nothing else — a build holds its
tables in memory and hands them to the engine as frames. Each function takes
that directory and nothing else it has to be told; the flags are the two
gates.

    import microbiomekg as mkg
    mkg.prepare("./data")                        # create folders and show next steps
    mkg.fetch("./data", missing=True)             # fills missing inputs, then reports
    result = mkg.build("./data", with_kegg=False, with_vectors=False)
    result.graph                                 # a kglite KnowledgeGraph, or None
"""

from __future__ import annotations

from pathlib import Path

from microbiomekg import download as _fetch
from microbiomekg import pipeline as _build
from microbiomekg.sources import InputFile, SourceStatus, missing_fetchers, status
from microbiomekg.preparation import prepare, validate_max_age_days

__all__ = [
    "BuildResult",
    "InputFile",
    "SourceStatus",
    "build",
    "fetch",
    "prepare",
    "status",
]

BuildResult = _build.BuildResult


def fetch(
    data_dir: str | Path = "data",
    *,
    only: list[str] | None = None,
    force: bool = False,
    chembl_sqlite: bool = False,
    missing: bool = False,
    max_age_days: float = 30,
) -> dict[str, SourceStatus]:
    """Fetch every automatic source into ``<data_dir>/raw/``, then report.

    Never raises on a manual source: the three browser-only origins are
    recorded as ``manual`` with the exact steps, and the returned status
    carries them as ``how_to_get``. ``only`` names fetchers
    (:data:`microbiomekg.download.SOURCES` keys, e.g. ``["ncbi", "bugsigdb"]``).
    With ``missing=True``, select only fetchers needed for missing declared
    inputs, excluding optional sources unless named in ``only``. Selected
    fetchers may check or update other files according to their cache policy.
    Browser-only files remain in the returned status for manual completion.
    ``max_age_days`` sets the final report threshold; it does not select downloads.
    """
    validate_max_age_days(max_age_days)
    if missing:
        only = missing_fetchers(status(data_dir), only)
        if not only:
            return prepare(data_dir, create=False, max_age_days=max_age_days)
    _fetch.run(
        Path(data_dir) / "raw", only=only, force=force, chembl_sqlite=chembl_sqlite
    )
    return prepare(data_dir, create=False, max_age_days=max_age_days)


def build(
    data_dir: str | Path = "data",
    *,
    with_kegg: bool = False,
    with_vectors: bool = False,
    scope: str = "microbial",
    out: str | Path | None = None,
    save: bool = False,
) -> BuildResult:
    """Build from whatever ``<data_dir>/raw/`` holds; report what was skipped.

    Returns a :class:`BuildResult` whose ``graph`` is the kglite graph, or
    ``None`` when nothing loaded (an empty directory — then ``skipped`` names
    every source), and whose ``store`` holds every table the preps produced,
    the ledgers of what would not resolve included. ``save`` writes ``out`` (default ``graph/microbiomekg.kgl``);
    off by default here, because a caller holding the graph object usually
    wants to query it, not a file.
    """
    data_dir = Path(data_dir)
    return _build.build(
        data_dir / "raw",
        scope=scope,
        out=out,
        save=save,
        with_vectors=with_vectors,
        gates=frozenset({"kegg"} if with_kegg else ()),
    )

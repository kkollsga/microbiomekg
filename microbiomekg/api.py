"""The three verbs, as Python: ``status``, ``fetch``, ``build``.

One directory is the entire input (``docs/design/library-pipeline.md``): raw
files under ``<data_dir>/raw/<source>/``, the flat CSVs a build writes under
``<data_dir>/csv/``. Each function takes that directory and nothing else it
has to be told; the flags are the two gates.

    import microbiomekg as mkg
    mkg.status("./data")                         # {source: SourceStatus}
    mkg.fetch("./data")                          # fills what it can, then status
    result = mkg.build("./data", with_kegg=False, with_vectors=False)
    result.graph                                 # a kglite KnowledgeGraph, or None
"""

from __future__ import annotations

from pathlib import Path

from microbiomekg import download as _fetch
from microbiomekg import pipeline as _build
from microbiomekg.sources import SourceStatus, status

__all__ = ["BuildResult", "SourceStatus", "build", "fetch", "status"]

BuildResult = _build.BuildResult


def fetch(
    data_dir: str | Path = "data",
    *,
    only: list[str] | None = None,
    force: bool = False,
    chembl_sqlite: bool = False,
) -> dict[str, SourceStatus]:
    """Fetch every automatic source into ``<data_dir>/raw/``, then report.

    Never raises on a manual source: the three browser-only origins are
    recorded as ``manual`` with the exact steps, and the returned status
    carries them as ``how_to_get``. ``only`` names fetchers
    (:data:`microbiomekg.download.SOURCES` keys, e.g. ``["ncbi", "bugsigdb"]``).
    """
    _fetch.run(
        Path(data_dir) / "raw", only=only, force=force, chembl_sqlite=chembl_sqlite
    )
    return status(data_dir)


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
    every source). ``save`` writes ``out`` (default ``graph/microbiomekg.kgl``);
    off by default here, because a caller holding the graph object usually
    wants to query it, not a file.
    """
    data_dir = Path(data_dir)
    return _build.build(
        data_dir / "raw",
        data_dir / "csv",
        scope=scope,
        out=out,
        save=save,
        with_vectors=with_vectors,
        gates=frozenset({"kegg"} if with_kegg else ()),
    )

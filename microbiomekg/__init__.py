"""MicrobiomeKG — a microbiome knowledge graph with an auditable evidence model.

Prepare and load from one data directory (``docs/design/library-pipeline.md``)::

    import microbiomekg as mkg
    mkg.prepare("./data")    # create the layout and print the next steps
    mkg.status("./data")     # per source: absent / present / stale / manual
    mkg.fetch("./data")      # fills what it can; the manual steps come back as data
    mkg.build("./data")      # builds from what is present; .graph is a kglite graph

They are loaded on first use, so ``import microbiomekg`` itself does no I/O
and pulls in nothing heavy; :mod:`microbiomekg.reconcile` and
:mod:`microbiomekg.ontology` stay importable on their own for the tests.
"""

from __future__ import annotations

from importlib import metadata as _metadata

__all__ = [
    "__version__",
    "build",
    "fetch",
    "prepare",
    "status",
    "reconcile",
    "ontology",
]

try:
    __version__ = _metadata.version("microbiomekg")
except _metadata.PackageNotFoundError:  # a checkout that was never installed
    __version__ = "0.0.0"


def __getattr__(name: str):
    if name in ("build", "fetch", "prepare", "status"):
        from microbiomekg import api

        return getattr(api, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

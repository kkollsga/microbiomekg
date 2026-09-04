"""One prep per source: raw files in ``data/raw/<src>/`` → tables in the store.

A prep is discovered by glob, never listed; ``DEPENDS_ON`` places it in the
build (:func:`microbiomekg.pipeline.order_preps`), and an absent raw input is a
:class:`microbiomekg.rawdata.MissingInput` the build catches and reports as the
skip. A prep is a function: ``run(raw, store, ...)`` puts its tables into a
:class:`microbiomekg.tables.Frames` store and returns their row counts.
"""

"""One prep per source: raw files in ``data/raw/<src>/`` → flat CSVs.

A prep is discovered by glob, never listed; ``DEPENDS_ON`` places it in the
build (:func:`microbiomekg.build.order_preps`), and an absent raw input leaves
by :func:`microbiomekg.rawdata.missing_input` — exit 3, the one code the build
reads as "skip this source". Run one directly with
``python -m microbiomekg.preps.prep_<src> --raw data/raw --out data/csv``.
"""

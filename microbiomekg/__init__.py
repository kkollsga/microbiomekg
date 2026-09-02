"""MicrobiomeKG — a microbiome knowledge graph with an auditable evidence model.

The importable surface is deliberately small and free of I/O side effects, so
tests can exercise it without a data download:

- :mod:`microbiomekg.reconcile` — NCBI taxonomy name/id reconciliation.
- :mod:`microbiomekg.ontology`  — the ``define_ontology`` document and the
  study-design → ``evidence_level`` mapping.
"""

__all__ = ["reconcile", "ontology"]

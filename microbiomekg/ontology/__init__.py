"""The declared semantic layer, composed from one module per source.

:data:`ONTOLOGY` is the document handed to ``KnowledgeGraph.define_ontology``
and written to ``ontology.json`` for the blueprint's build-time gate. Its point
is the ``required_properties`` declaration on ``ASSOCIATED_WITH``: that is what
turns "does this taxon–disease edge say how it was demonstrated?" from an
opinion into a number ``ontology_audit()`` reports on every rebuild.

**Why this is a package and not a file.** Every source has to appear in the
ontology, so a single module is the one file two agents adding two sources both
edit — and a merge conflict there is resolved by guessing. Instead:

* :mod:`.vocabulary` holds the evidence vocabularies and the fourteen-property
  contract, which are the project's, not any source's;
* :mod:`.core` holds the shared spine — ``Taxon``, the three condition types,
  ``Study``/``Paper``, and the association relationships every source writes
  rows into;
* ``microbiomekg/ontology/<source>.py`` holds exactly what that source adds,
  exporting ``CLASSES``, ``RELATIONSHIPS`` and ``ASSOCIATION_RELATIONSHIPS``.

Source modules are discovered, not listed, so adding a source is adding a file.
They are composed by :func:`microbiomekg.fragments.merge_fragments`, which
merges identical declarations and *raises* on contradictory ones: two sources
may both declare a shared class, and neither may quietly redefine it.
"""

from __future__ import annotations

import importlib
import json
import pkgutil
from pathlib import Path
from types import ModuleType

from ..fragments import merge_fragments
from .vocabulary import (
    AGENT_TYPES,
    ASSOCIATION_RANGES,
    EVIDENCE_CONTRACT,
    EVIDENCE_LEVEL_VALUES,
    EVIDENCE_LEVELS,
    EVIDENCE_PROPERTY_TYPES,
    EXCHANGE_CONTRACT,
    EXCHANGE_PROPERTY_TYPES,
    KNOWLEDGE_LEVELS,
    NON_HOST_SPECIES,
    OBSERVATIONAL_BY_SEQUENCING,
    SOURCE_EVIDENCE,
    SOURCE_LICENCE,
    agent_type,
    evidence_level,
    exchange_declaration,
    knowledge_level,
    split_study_designs,
)

__all__ = [
    "AGENT_TYPES",
    "ASSOCIATION_RANGES",
    "ASSOCIATION_RELATIONSHIPS",
    "EVIDENCE_CONTRACT",
    "EVIDENCE_LEVELS",
    "EVIDENCE_LEVEL_VALUES",
    "EVIDENCE_PROPERTY_TYPES",
    "EXCHANGE_CONTRACT",
    "EXCHANGE_PROPERTY_TYPES",
    "KNOWLEDGE_LEVELS",
    "NON_HOST_SPECIES",
    "OBSERVATIONAL_BY_SEQUENCING",
    "ONTOLOGY",
    "SOURCE_EVIDENCE",
    "SOURCE_LICENCE",
    "SOURCE_MODULES",
    "agent_type",
    "ontology_for",
    "evidence_level",
    "exchange_declaration",
    "knowledge_level",
    "split_study_designs",
    "write_json",
]

#: Modules in this package that are not a source's declaration.
_NOT_A_SOURCE = frozenset({"core", "vocabulary", "__main__"})


def _load_modules() -> list[tuple[str, ModuleType]]:
    """``core`` first, then every source module in name order.

    Deterministic by construction: the composed document must not depend on
    filesystem order, and ``core`` goes first so the shared spine is what a
    source's addition merges *into* (which is also the order the merge reports
    a conflict in).
    """
    names = sorted(
        m.name
        for m in pkgutil.iter_modules([str(Path(__file__).parent)])
        if m.name not in _NOT_A_SOURCE and not m.name.startswith("_")
    )
    return [
        (f"microbiomekg.ontology.{name}", importlib.import_module(f".{name}", __name__))
        for name in ["core", *names]
    ]


SOURCE_MODULES: list[tuple[str, ModuleType]] = _load_modules()

#: Every relationship that carries the evidence contract, in declaration order.
ASSOCIATION_RELATIONSHIPS: tuple[str, ...] = tuple(
    dict.fromkeys(
        rel
        for _, module in SOURCE_MODULES
        for rel in getattr(module, "ASSOCIATION_RELATIONSHIPS", ())
    )
)


def ontology_for(sources: list[str] | None = None) -> dict:
    """The declaration document for a build that loaded ``sources``.

    ``None`` means every source — :data:`ONTOLOGY`. A *partial* build needs a
    partial document for the same reason a partial build needs a partial
    blueprint: a rule over a relationship the build did not load reports
    ``0 / 0``, and a gate that cannot fail is worse than no gate. The spine is
    always included.
    """
    wanted = None if sources is None else {"core", *sources}
    chosen = [
        (name, module)
        for name, module in SOURCE_MODULES
        if wanted is None or name.rsplit(".", 1)[-1] in wanted
    ]
    if wanted is not None:
        missing = wanted - {name.rsplit(".", 1)[-1] for name, _ in chosen}
        if missing:
            raise ValueError(f"no ontology module for {', '.join(sorted(missing))}")
    return {
        "classes": merge_fragments(
            (name, getattr(module, "CLASSES", {})) for name, module in chosen
        ),
        "relationships": merge_fragments(
            (name, getattr(module, "RELATIONSHIPS", {})) for name, module in chosen
        ),
    }


ONTOLOGY: dict = ontology_for()


def write_json(path: str | Path = "ontology.json", document: dict | None = None) -> Path:
    """Write a declaration document where the blueprint's ``ontology`` points.

    Defaults to :data:`ONTOLOGY`; pass :func:`ontology_for`'s result for a
    build that loaded only some sources.
    """
    p = Path(path)
    p.write_text(json.dumps(ONTOLOGY if document is None else document, indent=2) + "\n",
                 encoding="utf-8")
    return p

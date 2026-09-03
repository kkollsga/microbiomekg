"""KEGG: a compound→map vocabulary that may not ship, behind a build flag.

KEGG is "explicitly not a public database, nor is it a publicly funded
database" (docs/sources.md §7): academic users may use the website, a service
built on it needs an academic service-provider licence, and any non-academic
use needs a commercial one. A graph carrying KEGG content therefore cannot be
published, which is why the whole slice sits behind ``scripts/build.py
--with-kegg`` and is **off by default**, and why every row it writes carries
``source_licence = 'KEGG-restricted'`` — a per-edge licence is what makes a
mixed-licence graph shippable in parts instead of not at all (G3).

**This module declares no class and no relationship, and that is the design.**
KEGG writes rows into the ``Pathway`` node and the ``IN_PATHWAY`` edge
:mod:`.reactome` declares; it adds no vocabulary of its own. The consequence is
what makes the flag safe: a default build composes ``microbiomekg/blueprints/kegg.json`` and
this module anyway, and they contribute nothing — no node type loaded empty, no
audit rule at ``0 / 0``. The flag's whole blast radius is the rows, which is
exactly the licence boundary and nothing else.

**The flag does not change which metabolites exist, either.** The metabolite
selection rule in :mod:`scripts.prep_hmdb` deliberately does not consult KEGG's
files: a metabolite kept *because* KEGG links it would be a KEGG-derived
selection sitting in a graph built without the flag. So ``--with-kegg`` adds
``KEGG:map*`` pathway nodes and their ``IN_PATHWAY`` rows and nothing else, and
the KEGG links whose compound has no metabolite node are reported rather than
silently dropped.

**What KEGG cannot contribute.** No taxon join exists: ``/list/organism`` was
retired upstream (HTTP 400) and the ``/list/genome`` roster that replaced it has
lost the taxonomic-lineage column, so there is no taxid in any of the six files.
There are therefore no taxon–pathway edges from KEGG, here or later, without a
name-matching step against ``names.dmp`` that the strain-qualified organism
names (`Sorangium cellulosum So ce56`) would make lossy. And
``conv/compound/pubchem`` returns PubChem **Substance** ids, not Compound ids —
`C00001` (water) maps to `pubchem:3303` where water's CID is 962 — so it is not
loaded at all rather than written into a `pubchem_cid` beside HMDB's, where it
would be wrong and look plausible.
"""

from __future__ import annotations

from .vocabulary import register_source

__all__ = [
    "ASSOCIATION_RELATIONSHIPS",
    "BUILD_FLAG",
    "CLASSES",
    "EVIDENCE_LEVEL",
    "RELATIONSHIPS",
    "SOURCE",
]

SOURCE = "kegg"

#: The flag ``scripts/build.py`` gates this source on. Named here so the prep
#: script's refusal message and the build's skip message cannot drift apart.
BUILD_FLAG: str = "--with-kegg"

#: KEGG maps are drawn by hand, so the claim is a curator's. There is no
#: per-link evidence field anywhere in the six files, which is why
#: :data:`EVIDENCE_LEVEL` is ``unknown`` rather than something derived —
#: fabricating a level for a source that ships none is the F10 failure the
#: schema survey names.
register_source(
    SOURCE,
    knowledge_level="knowledge_assertion",
    agent_type="manual_agent",
    licence="KEGG-restricted",
)

#: ``unknown`` is a value, not a gap: `WHERE r.evidence_level = 'unknown'`
#: counts it, where a null would not.
EVIDENCE_LEVEL: str = "unknown"

#: KEGG declares no taxon–condition association, and no class or relationship
#: at all — see the module docstring.
ASSOCIATION_RELATIONSHIPS: tuple[str, ...] = ()

CLASSES: dict[str, dict] = {}

RELATIONSHIPS: dict[str, dict] = {}

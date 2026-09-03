"""What is on this machine, per source — the first-class ``status`` output.

An operator on a fresh clone runs ``status`` and gets a to-do list rather than
a failed build: which automatic fetches to run, which files to download by
hand and where to put them, which sources are optional and why
(``docs/design/library-pipeline.md`` rule 6). Nothing here is listed by hand:
the sources are the preps under :mod:`microbiomekg.preps`, the files each
needs are its own ``RAW_INPUTS`` declaration, the way to get them is
:data:`microbiomekg.fetch.FETCHES` / :data:`microbiomekg.fetch.MANUAL`, and
the licence is what the source's ontology module registered. A source present
in one of those and absent from another is a test failure
(``tests/test_sources.py``), which is the fifth check the four-file source
shape gets.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from microbiomekg import fetch
from microbiomekg.build import LICENCE_GATED, PREPS_DIR, declared_inputs
from microbiomekg.ontology import SOURCE_LICENCE

__all__ = ["STATES", "SourceStatus", "discover", "status"]

#: ``present`` — every declared input is on disk; ``stale`` — present, but a
#: file differs in size from what the fetch manifest recorded for it, so the
#: operator replaced it since; ``manual`` — absent, and no client can fetch it
#: (browser-only origin); ``absent`` — absent, and ``fetch`` can get it.
STATES = ("absent", "present", "stale", "manual")

#: NCBI Taxonomy is a US Government work and carries no evidence, so no
#: ontology module registers a licence for it (``docs/sources.md`` §1). Every
#: other source's token comes from its own module's ``register_source``.
_UNREGISTERED_LICENCES = {"taxonomy": "public-domain"}


@dataclass(frozen=True)
class SourceStatus:
    """One source's state on this machine, with the fix for it as data."""

    name: str
    state: str
    path: Path
    inputs: tuple[str, ...]
    missing: tuple[str, ...]
    how_to_get: str
    licence: str
    gated_by: str | None = None

    @property
    def optional(self) -> bool:
        """Licence-gated: off by default, and the report prices the gap."""
        return self.gated_by is not None


def discover() -> list[str]:
    """Every source with a prep, in name order — discovered, never listed."""
    return sorted(p.stem.removeprefix("prep_") for p in PREPS_DIR.glob("prep_*.py"))


def _manifest(raw: Path) -> dict:
    path = raw / "manifest.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _stale(raw: Path, rel: str, manifest: dict) -> bool:
    """The manifest knows this file and its size is not what was recorded."""
    entry = manifest.get(rel)
    if not entry or entry.get("bytes") is None:
        return False
    return (raw / rel).stat().st_size != entry["bytes"]


def status(data_dir: str | Path) -> dict[str, SourceStatus]:
    """Per source: absent / present / stale / manual, with the fix for each.

    ``data_dir`` is the one directory that is the entire input; the raw files
    live under ``data_dir/raw/<source>/`` in the layout ``fetch`` writes.
    """
    raw = Path(data_dir) / "raw"
    manifest = _manifest(raw)
    out: dict[str, SourceStatus] = {}
    for name in discover():
        inputs = declared_inputs(PREPS_DIR / f"prep_{name}.py")
        missing = tuple(rel for rel in inputs if not (raw / rel).is_file())
        if missing:
            state = "manual" if name in fetch.MANUAL else "absent"
        elif any(_stale(raw, rel, manifest) for rel in inputs):
            state = "stale"
        else:
            state = "present"
        out[name] = SourceStatus(
            name=name,
            state=state,
            path=raw / inputs[0].split("/", 1)[0],
            inputs=inputs,
            missing=missing,
            how_to_get=fetch.how_to_get(name),
            licence=SOURCE_LICENCE.get(name) or _UNREGISTERED_LICENCES[name],
            gated_by=LICENCE_GATED.get(name),
        )
    return out

"""What is on this machine, per source — the first-class ``status`` output.

An operator on a fresh clone runs ``status`` and gets a to-do list rather than
a failed build: which automatic fetches to run, which files to download by
hand and where to put them, which sources are optional and why
(``docs/design/library-pipeline.md`` rule 6). Nothing here is listed by hand:
the sources are the preps under :mod:`microbiomekg.preps`, the files each
needs are its own ``RAW_INPUTS`` declaration, the way to get them is
:data:`microbiomekg.download.FETCHES` / :data:`microbiomekg.download.MANUAL`, and
the licence is what the source's ontology module registered. A source present
in one of those and absent from another is a test failure
(``tests/test_sources.py``), which is the fifth check the four-file source
shape gets.
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from microbiomekg import download
from microbiomekg.pipeline import LICENCE_GATED, PREPS_DIR, declared_inputs
from microbiomekg.ontology import SOURCE_LICENCE

__all__ = ["STATES", "InputFile", "SourceStatus", "discover", "status"]

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
class InputFile:
    """One declared raw input. Metadata is inspected without reading its contents.

    ``age_seconds`` is time since the local modification time, not the age of
    the upstream dataset. ``sha256`` is the manifest's recorded digest; status
    does not recompute or verify it. ``stale`` means a recorded size mismatch,
    not that a newer upstream release exists.
    """

    relative_path: str
    state: str
    url: str | None
    fetcher: str | None
    size_bytes: int | None = None
    modified_at: datetime | None = None
    age_seconds: float | None = None
    sha256: str | None = None

    @property
    def manual(self) -> bool:
        """The known origin needs an operator download."""
        return self.url is not None and self.fetcher is None


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
    files: tuple[InputFile, ...] = ()

    @property
    def size_bytes(self) -> int:
        """Bytes present across this source's declared inputs."""
        return sum(f.size_bytes or 0 for f in self.files)

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
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _input_file(raw: Path, rel: str, manifest: dict, now: datetime) -> InputFile:
    origin = download.origin_of(rel)
    path = raw / rel
    entry = manifest.get(rel)
    entry = entry if isinstance(entry, dict) else {}
    metadata = {}
    if path.is_file():
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
        state = (
            "stale"
            if entry.get("bytes") is not None and entry["bytes"] != stat.st_size
            else "present"
        )
        metadata = dict(
            size_bytes=stat.st_size,
            modified_at=modified,
            age_seconds=max(0, (now - modified).total_seconds()),
            sha256=entry.get("sha256"),
        )
    else:
        state = "manual" if origin and origin.manual else "absent"
    return InputFile(
        relative_path=rel,
        state=state,
        url=origin.url if origin else None,
        fetcher=origin.fetcher if origin else None,
        **metadata,
    )


def status(data_dir: str | Path) -> dict[str, SourceStatus]:
    """Per source: absent / present / stale / manual, with the fix for each.

    ``data_dir`` is the one directory that is the entire input; the raw files
    live under ``data_dir/raw/<source>/`` in the layout ``fetch`` writes.
    """
    raw = Path(data_dir) / "raw"
    manifest = _manifest(raw)
    out: dict[str, SourceStatus] = {}
    now = datetime.now(timezone.utc)
    for name in discover():
        inputs = declared_inputs(PREPS_DIR / f"prep_{name}.py")
        files = tuple(_input_file(raw, rel, manifest, now) for rel in inputs)
        missing = tuple(
            f.relative_path for f in files if f.state in ("absent", "manual")
        )
        if missing:
            state = "manual" if any(f.state == "manual" for f in files) else "absent"
        elif any(f.state == "stale" for f in files):
            state = "stale"
        else:
            state = "present"
        how = download.how_to_get(name, data_dir)
        if missing and state == "absent":
            fetchers = sorted(
                {f.fetcher for f in files if f.state == "absent" and f.fetcher}
            )
            if fetchers:
                how = (
                    f"microbiomekg fetch --data {shlex.quote(str(data_dir))}"
                    + "".join(f" --only {fetcher}" for fetcher in fetchers)
                )
        out[name] = SourceStatus(
            name=name,
            state=state,
            path=raw / inputs[0].split("/", 1)[0],
            inputs=inputs,
            missing=missing,
            how_to_get=how,
            licence=SOURCE_LICENCE.get(name) or _UNREGISTERED_LICENCES[name],
            gated_by=LICENCE_GATED.get(name),
            files=files,
        )
    return out


def missing_fetchers(
    table: dict[str, SourceStatus], only: list[str] | None = None
) -> list[str]:
    """Deduplicated fetchers for missing declared inputs; optional sources opt in.

    Selection is at fetcher level: a selected fetcher can also check or update
    its other files using its existing cache policy.
    """
    if only is not None:
        unknown = set(only) - download.SOURCES.keys()
        if unknown:
            raise ValueError(f"Unknown fetchers: {', '.join(sorted(unknown))}")
    return sorted(
        {
            f.fetcher
            for st in table.values()
            if not st.optional
            or (only is not None and download.FETCHES[st.name] in only)
            for f in st.files
            if f.state == "absent"
            and f.fetcher is not None
            and (only is None or f.fetcher in only)
        }
    )

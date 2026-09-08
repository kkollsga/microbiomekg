"""Guidance shared by Python preparation and the CLI status/fetch reports."""

from __future__ import annotations

import math
from pathlib import Path

from microbiomekg.sources import InputFile, SourceStatus, status

__all__ = ["prepare"]


def _size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.0f} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def _age(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    if seconds < 60:
        return "<1 min"
    if seconds < 3600:
        return f"{int(seconds // 60)} min"
    if seconds < 86400:
        return f"{int(seconds // 3600)} h"
    return f"{int(seconds // 86400)} d"


def validate_max_age_days(value: float) -> float:
    """Reject invalid thresholds before creating directories or fetching."""
    if not math.isfinite(value) or value < 0:
        raise ValueError("max_age_days must be finite and non-negative")
    return value


def _download_details(data: Path, file: InputFile) -> None:
    destination = data / "raw" / file.relative_path
    reason = "missing" if file.size_bytes is None else "over age threshold"
    print(f"\n{file.relative_path} ({reason})")
    print(f"    URL: {file.url or 'no origin registered'}")
    print(f"    Expected file: {destination}")
    if file.manual:
        if file.relative_path == "hmdb/hmdb_metabolites.xml":
            archive = destination.with_name("hmdb_metabolites.zip")
            print(f"    Download in a browser; save as: {archive}")
            print(f"    Extract the archive to obtain: {destination}")
        else:
            print(f"    Download in a browser; save as: {destination}")


def _report(data: Path, table: dict[str, SourceStatus], max_age_days: float) -> None:
    print(f"Data: {data}")
    rows = [("Dataset", "Available", "Size", "Age")]
    for name, st in table.items():
        present = [f for f in st.files if f.size_bytes is not None]
        available = (
            "yes"
            if len(present) == len(st.files)
            else (f"partial ({len(present)}/{len(st.files)})" if present else "no")
        )
        oldest = max(
            (f.age_seconds for f in present if f.age_seconds is not None), default=None
        )
        rows.append(
            (
                name,
                available,
                _size(st.size_bytes) if present else "—",
                _age(oldest) if present else "—",
            )
        )
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    for i, row in enumerate(rows):
        print(
            "  ".join(value.ljust(width) for value, width in zip(row, widths)).rstrip()
        )
        if i == 0:
            print("  ".join("-" * width for width in widths))
    print(
        f"\nAge: oldest local file age (since modification); threshold: {max_age_days:g} days."
    )
    for name, st in table.items():
        if st.optional:
            print(f"{name} (optional, {st.gated_by})")
    changed = [
        name for name, st in table.items() if any(f.state == "stale" for f in st.files)
    ]
    if changed:
        print(f"Manifest size differs (stale): {', '.join(changed)}")
    seen = set()
    for st in table.values():
        for file in st.files:
            over_age = (
                file.age_seconds is not None and file.age_seconds > max_age_days * 86400
            )
            if (file.size_bytes is None or over_age) and file.relative_path not in seen:
                _download_details(data, file)
                seen.add(file.relative_path)


def prepare(
    data_dir: str | Path = "data", *, create: bool = True, max_age_days: float = 30
) -> dict[str, SourceStatus]:
    """Create the input layout, print a status table, and return statuses.

    ``max_age_days`` controls which existing files get download details (default
    30 days). Dataset age is the oldest local input modification age, not an
    upstream release date. The threshold does not trigger downloads.

    No downloads or file-content validation run here. ``create=False`` only
    inspects, including when the directory does not exist. The directories
    belong to the operator's data area and are never automatically pruned.
    Use :func:`microbiomekg.api.fetch` with ``missing=True`` for the automatic
    inputs, then call this function again for remaining manual steps.
    """
    validate_max_age_days(max_age_days)
    data = Path(data_dir)
    table = status(data)
    if create:
        for st in table.values():
            for rel in st.inputs:
                (data / "raw" / rel).parent.mkdir(parents=True, exist_ok=True)
    _report(data, table, max_age_days)
    return table

"""Guidance shared by Python preparation and the CLI status/fetch reports."""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

from microbiomekg.sources import SourceStatus, missing_fetchers, status

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


def _command() -> str:
    """Use the current environment even when its bin directory is not on PATH."""
    executable = Path(sys.executable).absolute()
    script = executable.with_name(
        "microbiomekg.exe" if sys.platform == "win32" else "microbiomekg"
    )
    if script.is_file():
        try:
            return shlex.quote("./" + script.relative_to(Path.cwd()).as_posix())
        except ValueError:
            return shlex.quote(str(script))
    return f"{shlex.quote(str(executable))} -m microbiomekg.cli"


def _report(data: Path, table: dict[str, SourceStatus]) -> None:
    print(f"Data: {data}")
    print("File status / size / local file age (since modification)")
    print("Present means on disk; stale means size differs from the fetch manifest.")
    print("Upstream versions and file contents are not checked here.")
    for name, st in table.items():
        gate = f"  (optional, {st.gated_by})" if st.optional else ""
        print(f"\n{name}  {st.state}  {_size(st.size_bytes)}  {st.licence}{gate}")
        for f in st.files:
            size = "—" if f.size_bytes is None else _size(f.size_bytes)
            print(
                f"  {f.state:<7} {size:>10}  {_age(f.age_seconds):>7}  {f.relative_path}"
            )
            if f.state in ("absent", "manual"):
                print(f"    URL: {f.url or 'no origin registered'}")
                if f.manual:
                    destination = data / "raw" / f.relative_path
                    if name == "hmdb":
                        archive = destination.with_name("hmdb_metabolites.zip")
                        print(f"    Download in a browser; save as: {archive}")
                        print(f"    Extract the archive to obtain: {destination}")
                    else:
                        print(f"    Download in a browser; save as: {destination}")
                else:
                    print(
                        f"    Fetcher: {f.fetcher}; destination: {data / 'raw' / f.relative_path}"
                    )
        if any(f.state == "manual" for f in st.files):
            if name == "masi":
                print(
                    "    The source may require accepting its expired certificate in your browser."
                )
    quoted = shlex.quote(str(data))
    command = _command()
    print("\nNext steps:")
    if missing_fetchers(table):
        print(
            "Fetch missing automatic inputs (selected fetchers may also update their other files):"
        )
        print(f"  {command} fetch --data {quoted} --missing")
    else:
        print("No automatic downloads needed for the required inputs.")
    if any(f.state == "manual" for st in table.values() for f in st.files):
        print("Complete the browser downloads above, then check status again.")
    if any(f.state == "stale" for st in table.values() for f in st.files):
        print("Inspect files marked stale: their size differs from the recorded size.")
    print(f"  {command} status --data {quoted}")
    print(
        "Build from the available inputs; missing sources will be reported as skipped:"
    )
    print(f"  {command} build --data {quoted}")


def prepare(
    data_dir: str | Path = "data", *, create: bool = True
) -> dict[str, SourceStatus]:
    """Create the input layout, print its status and next steps, return statuses.

    No downloads or file-content validation run here. ``create=False`` only
    inspects, including when the directory does not exist. The directories
    belong to the operator's data area and are never automatically pruned.
    Use :func:`microbiomekg.api.fetch` with ``missing=True`` for the automatic
    inputs, then call this function again for remaining manual steps.
    """
    data = Path(data_dir)
    table = status(data)
    if create:
        for st in table.values():
            for rel in st.inputs:
                (data / "raw" / rel).parent.mkdir(parents=True, exist_ok=True)
    _report(data, table)
    return table

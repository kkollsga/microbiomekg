"""``microbiomekg`` on the command line: ``fetch``, ``status``, ``build``, ``serve``.

    microbiomekg fetch  --data ./data      # fills what it can; prints the manual steps
    microbiomekg status --data ./data      # per source: absent / present / stale / manual
    microbiomekg build  --data ./data      # builds from what is present; reports the rest
    microbiomekg serve  --graph graph/microbiomekg.kgl   # the MCP server on stdio

``--data`` is the one directory that is the entire input; everything after it
is passed to the verb's own parser, so ``microbiomekg build --data ./data
--with-kegg --no-save`` reads as it should.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from microbiomekg import download, pipeline, serve
from microbiomekg.sources import status

__all__ = ["main"]


def _split_data(argv: list[str]) -> tuple[Path, list[str]]:
    """Pull ``--data DIR`` out of ``argv``; the rest goes to the verb."""
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--data", type=Path, default=Path("data"))
    known, rest = ap.parse_known_args(argv)
    return known.data, rest


def print_status(data_dir: Path) -> int:
    """One line per source; the fix for each absent one underneath it."""
    table = status(data_dir)
    width = max(len(name) for name in table)
    for name, st in table.items():
        gate = f"  (optional, {st.gated_by})" if st.gated_by else ""
        print(f"{name:<{width}}  {st.state:<8}  {st.licence}{gate}")
        if st.state != "present":
            for rel in st.missing:
                print(f"{'':<{width}}    missing {rel}")
            print(f"{'':<{width}}    -> {st.how_to_get}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(
        prog="microbiomekg",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("verb", choices=("fetch", "status", "build", "serve"))
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    args = ap.parse_args(argv)
    if args.verb == "serve":
        return serve.main(args.rest)
    data, rest = _split_data(args.rest)
    if args.verb == "status":
        return print_status(data)
    if args.verb == "fetch":
        return download.main(["--raw", str(data / "raw"), *rest])
    return pipeline.main(
        ["--raw", str(data / "raw"), "--csv", str(data / "csv"), *rest]
    )


if __name__ == "__main__":
    raise SystemExit(main())

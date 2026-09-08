"""``microbiomekg`` on the command line: ``fetch``, ``status``, ``build``, ``serve``.

    microbiomekg fetch  --data ./data --missing   # fills missing inputs; reports the rest
    microbiomekg status --data ./data --create    # prepare input folders and inspect files
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
from microbiomekg.sources import missing_fetchers, status
from microbiomekg.preparation import prepare, validate_max_age_days

__all__ = ["main"]


def _split_data(argv: list[str]) -> tuple[Path, list[str]]:
    """Pull ``--data DIR`` out of ``argv``; the rest goes to the verb."""
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--data", type=Path, default=Path("data"))
    known, rest = ap.parse_known_args(argv)
    return known.data, rest


def print_status(
    data_dir: Path, *, create: bool = False, max_age_days: float = 30
) -> int:
    """Print the same guidance as the Python data-loading path."""
    prepare(data_dir, create=create, max_age_days=max_age_days)
    return 0


def _age_threshold(value: str) -> float:
    try:
        return validate_max_age_days(float(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _age_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--max-age-days",
        type=_age_threshold,
        default=30,
        help="show download details above this local file age (default: 30 days)",
    )


def _fetch(data: Path, rest: list[str]) -> int:
    ap = download.argument_parser()
    ap.prog = "microbiomekg fetch"
    ap.add_argument(
        "--missing",
        action="store_true",
        help="fetch missing required inputs; optional sources need --only",
    )
    _age_option(ap)
    args = ap.parse_args(["--raw", str(data / "raw"), *rest])
    selected = missing_fetchers(status(data), args.only) if args.missing else args.only
    failures = []
    if selected != []:
        failures = download.run(
            args.raw, only=selected, force=args.force, chembl_sqlite=args.chembl_sqlite
        )
    print_status(data, max_age_days=args.max_age_days)
    return int(bool(failures))


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
        status_parser = argparse.ArgumentParser(prog="microbiomekg status")
        status_parser.add_argument(
            "--create", action="store_true", help="create the raw input directories"
        )
        _age_option(status_parser)
        opts = status_parser.parse_args(rest)
        return print_status(data, create=opts.create, max_age_days=opts.max_age_days)
    if args.verb == "fetch":
        return _fetch(data, rest)
    return pipeline.main(["--raw", str(data / "raw"), *rest])


if __name__ == "__main__":
    raise SystemExit(main())

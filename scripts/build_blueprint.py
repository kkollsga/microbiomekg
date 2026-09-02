#!/usr/bin/env python3
"""``blueprints/*.json`` -> ``blueprint.json``.

The blueprint is one file kglite reads and N files people write. Each source
declares what it uses in ``blueprints/<source>.json`` — the node types it
writes rows for, the junction edges it fills — and this script composes them
with :func:`microbiomekg.fragments.merge_fragments`, whose rule is:

* declaring the **same** thing twice is how a source says "I write rows into
  this table too" and merges silently;
* declaring **more** — an extra property, an extra junction edge under a node
  type another fragment owns — is additive;
* declaring the same key with a **different** value raises, naming both
  fragments. Two sources disagreeing about which CSV backs ``Disease`` is a bug
  in one of them, and a merger that picked a winner would hide it.

``blueprints/core.json`` is the shared spine (the taxon side, the three
condition types, ``Study``/``Paper``, and the association junction edges every
source writes rows into) and is always composed first, so a source fragment is
read as an addition to it. Fragments may carry ``_``-prefixed keys as comments;
they are stripped from the output.

``--sources`` composes a *partial* blueprint — the spine plus the named
sources. That is not a convenience: a blueprint declaring a node type whose CSV
is not there loads it as empty, and an ontology rule over an empty type is a
gate that cannot fail. So a build that prepped only some sources declares only
those (``scripts/build.py`` does this automatically for a source whose raw
input is absent), and a per-source test builds its own source's blueprint.

Usage::

    python scripts/build_blueprint.py                      # rewrite blueprint.json
    python scripts/build_blueprint.py --check              # fail if it would change
    python scripts/build_blueprint.py --sources bugsigdb   # the spine + one source
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from microbiomekg.fragments import merge_fragments  # noqa: E402

#: Composed first: the shape a source fragment adds to.
SPINE = "core"


def fragment_paths(directory: Path) -> list[Path]:
    """``core.json`` first, then every other fragment in name order."""
    paths = sorted(p for p in directory.glob("*.json"))
    spine = [p for p in paths if p.stem == SPINE]
    return spine + [p for p in paths if p.stem != SPINE]


def strip_comments(value: Any) -> Any:
    """Drop ``_``-prefixed keys, which are a fragment's notes to its reader."""
    if isinstance(value, dict):
        return {k: strip_comments(v) for k, v in value.items() if not k.startswith("_")}
    if isinstance(value, list):
        return [strip_comments(v) for v in value]
    return value


def compose(directory: Path, sources: list[str] | None = None) -> dict:
    """The composed blueprint. ``sources`` keeps only those (plus the spine)."""
    paths = fragment_paths(directory)
    if sources is not None:
        wanted = {SPINE, *sources}
        unknown = wanted - {p.stem for p in paths}
        if unknown:
            raise SystemExit(f"no fragment for {', '.join(sorted(unknown))} in {directory}")
        paths = [p for p in paths if p.stem in wanted]
    if not paths:
        raise SystemExit(f"no blueprint fragments under {directory}")
    # Stripped per fragment, before merging: two fragments' notes are two
    # different strings under one key, which is exactly what the merge refuses.
    return merge_fragments(
        (str(p.relative_to(directory.parent)), strip_comments(json.loads(p.read_text())))
        for p in paths
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fragments", type=Path, default=Path("blueprints"))
    ap.add_argument("--out", type=Path, default=Path("blueprint.json"))
    ap.add_argument(
        "--sources",
        nargs="*",
        default=None,
        help="Compose the spine plus only these sources. Default: every fragment.",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit 1 if the composed blueprint differs from --out. "
        "A drifted blueprint.json loads a different graph than the fragments "
        "describe, which is the one failure nothing else here would catch.",
    )
    args = ap.parse_args(argv)

    merged = compose(args.fragments, args.sources)
    text = json.dumps(merged, indent=2) + "\n"

    if args.check:
        current = args.out.read_text() if args.out.is_file() else ""
        if current != text:
            print(
                f"{args.out} has drifted from {args.fragments}/ — "
                f"run `python scripts/build_blueprint.py`",
                file=sys.stderr,
            )
            return 1
        print(f"{args.out} matches {args.fragments}/")
        return 0

    args.out.write_text(text, encoding="utf-8")
    print(
        f"{args.out} <- {', '.join(p.name for p in fragment_paths(args.fragments) if args.sources is None or p.stem in {SPINE, *args.sources})} "
        f"({len(merged.get('nodes', {}))} node types)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

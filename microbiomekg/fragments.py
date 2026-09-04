"""Merge per-source declaration fragments into one document.

Both of this project's build-time declarations — the kglite blueprint and the
``define_ontology`` document — are single files that every source has to appear
in. That makes them the one place two agents adding two sources collide, and a
merge conflict in a 400-line JSON file is resolved by *guessing* which half
survives. So neither is authored as a single file any more: each source
declares what it uses in its own fragment (``microbiomekg/blueprints/<source>.json`` and
``microbiomekg/ontology/<source>.py``) and this module composes them.

The composition rule is the whole point, and it is deliberately not
"last writer wins":

* two fragments may declare the **same** thing — a shared node type, a shared
  relationship — and that is how a source says "I write rows into this";
* they may **add** to it — a property, a junction edge under a node type
  another fragment declared;
* but if they declare the same key with **different** values, that is a
  :class:`FragmentConflict` naming both fragments and the path, never a silent
  override. Two sources disagreeing about which table backs ``Disease`` is a
  bug in one of them, and the build must not pick a winner.

Merging is deterministic: fragments are composed in the order given, lists keep
first-seen order, and dict key order follows first declaration. The same
fragments in the same order always produce a byte-identical document, which is
what lets ``scripts/build_blueprint.py --check`` be a drift gate.

The fragments ship inside the package (``microbiomekg/blueprints/``), so
:func:`compose` needs no directory argument from an installed build; the
``--fragments`` flag exists for a test composing a directory of its own.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

__all__ = [
    "FRAGMENTS_DIR",
    "SPINE",
    "FragmentConflict",
    "compose",
    "fragment_paths",
    "merge_fragments",
    "strip_comments",
]

#: Where the fragments live: inside the package, so an installed build has them.
FRAGMENTS_DIR = Path(__file__).resolve().parent / "blueprints"

#: Composed first: the shape a source fragment adds to.
SPINE = "core"


class FragmentConflict(ValueError):
    """Two fragments declared the same key with different values."""


def _path(parts: tuple[str, ...]) -> str:
    return ".".join(parts) or "<root>"


def _merge_into(
    base: dict[str, Any],
    origin: dict[str, str],
    incoming: Mapping[str, Any],
    source: str,
    parts: tuple[str, ...],
) -> None:
    for key, value in incoming.items():
        here = parts + (str(key),)
        if key not in base:
            base[key] = _copy(value)
            # Every path inside the subtree, not just its root: the fragment
            # that first declared `nodes.Disease` is the one a later conflict
            # on `nodes.Disease.file` has to name.
            _claim(origin, value, source, here)
            continue

        current = base[key]
        if isinstance(current, dict) and isinstance(value, Mapping):
            _merge_into(current, origin, value, source, here)
        elif isinstance(current, list) and isinstance(value, list):
            # An ordered union, not a concatenation: a shared junction edge's
            # `properties` list is declared by the source that owns the shape
            # and extended by the sources that add columns to the same table,
            # and neither should have to know about the other's entries.
            for item in value:
                if item not in current:
                    current.append(_copy(item))
        elif current != value:
            raise FragmentConflict(
                f"{_path(here)} is {current!r} in {origin.get(_path(here), '?')} "
                f"but {value!r} in {source}"
            )


def _claim(
    origin: dict[str, str], value: Any, source: str, parts: tuple[str, ...]
) -> None:
    origin[_path(parts)] = source
    if isinstance(value, Mapping):
        for key, child in value.items():
            _claim(origin, child, source, parts + (str(key),))


def _copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_copy(v) for v in value]
    return value


def merge_fragments(
    fragments: Iterable[tuple[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    """Compose ``(name, document)`` fragments into one document.

    ``name`` is only ever used in the error message, so it should be whatever
    the reader would go and open — a file path or a module name.

    Raises:
        FragmentConflict: two fragments declared the same key with different
            values. The message names the path and both fragments.
    """
    merged: dict[str, Any] = {}
    origin: dict[str, str] = {}
    for name, document in fragments:
        _merge_into(merged, origin, document, name, ())
    return merged


def fragment_paths(directory: Path = FRAGMENTS_DIR) -> list[Path]:
    """``core.json`` first, then every other fragment in name order."""
    paths = sorted(p for p in Path(directory).glob("*.json"))
    spine = [p for p in paths if p.stem == SPINE]
    return spine + [p for p in paths if p.stem != SPINE]


def strip_comments(value: Any) -> Any:
    """Drop ``_``-prefixed keys, which are a fragment's notes to its reader."""
    if isinstance(value, dict):
        return {k: strip_comments(v) for k, v in value.items() if not k.startswith("_")}
    if isinstance(value, list):
        return [strip_comments(v) for v in value]
    return value


def compose(directory: Path = FRAGMENTS_DIR, sources: list[str] | None = None) -> dict:
    """The composed blueprint. ``sources`` keeps only those (plus the spine).

    A partial blueprint is not a convenience: a blueprint declaring a node type
    whose table is not in the store loads it as empty, and an ontology rule
    over an empty type is a gate that cannot fail. So a build that prepped only some
    sources declares only those (:mod:`microbiomekg.pipeline` does this for a
    source whose raw input is absent), and a per-source test builds its own.
    """
    directory = Path(directory)
    paths = fragment_paths(directory)
    if sources is not None:
        wanted = {SPINE, *sources}
        unknown = wanted - {p.stem for p in paths}
        if unknown:
            raise SystemExit(
                f"no fragment for {', '.join(sorted(unknown))} in {directory}"
            )
        paths = [p for p in paths if p.stem in wanted]
    if not paths:
        raise SystemExit(f"no blueprint fragments under {directory}")
    # Stripped per fragment, before merging: two fragments' notes are two
    # different strings under one key, which is exactly what the merge refuses.
    return merge_fragments(
        (
            str(p.relative_to(directory.parent)),
            strip_comments(json.loads(p.read_text())),
        )
        for p in paths
    )


def main(argv: list[str] | None = None) -> int:
    """``microbiomekg/blueprints/*.json`` -> ``blueprint.json``.

    ``--check`` does not write; it exits 1 if the composed blueprint differs
    from ``--out``. A drifted ``blueprint.json`` loads a different graph than
    the fragments describe, which is the one failure nothing else would catch,
    so ``make gate`` runs this.
    """
    ap = argparse.ArgumentParser(description=main.__doc__)
    ap.add_argument("--fragments", type=Path, default=FRAGMENTS_DIR)
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
        help="Do not write; exit 1 if the composed blueprint differs from --out.",
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
    composed = [
        p.name
        for p in fragment_paths(args.fragments)
        if args.sources is None or p.stem in {SPINE, *args.sources}
    ]
    print(
        f"{args.out} <- {', '.join(composed)} "
        f"({len(merged.get('nodes', {}))} node types)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

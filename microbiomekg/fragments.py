"""Merge per-source declaration fragments into one document.

Both of this project's build-time declarations — the kglite blueprint and the
``define_ontology`` document — are single files that every source has to appear
in. That makes them the one place two agents adding two sources collide, and a
merge conflict in a 400-line JSON file is resolved by *guessing* which half
survives. So neither is authored as a single file any more: each source
declares what it uses in its own fragment (``blueprints/<source>.json`` and
``microbiomekg/ontology/<source>.py``) and this module composes them.

The composition rule is the whole point, and it is deliberately not
"last writer wins":

* two fragments may declare the **same** thing — a shared node type, a shared
  relationship — and that is how a source says "I write rows into this";
* they may **add** to it — a property, a junction edge under a node type
  another fragment declared;
* but if they declare the same key with **different** values, that is a
  :class:`FragmentConflict` naming both fragments and the path, never a silent
  override. Two sources disagreeing about which CSV backs ``Disease`` is a bug
  in one of them, and the build must not pick a winner.

Merging is deterministic: fragments are composed in the order given, lists keep
first-seen order, and dict key order follows first declaration. The same
fragments in the same order always produce a byte-identical document, which is
what lets ``scripts/build_blueprint.py --check`` be a drift gate.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

__all__ = ["FragmentConflict", "merge_fragments"]


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
            # on `nodes.Disease.csv` has to name.
            _claim(origin, value, source, here)
            continue

        current = base[key]
        if isinstance(current, dict) and isinstance(value, Mapping):
            _merge_into(current, origin, value, source, here)
        elif isinstance(current, list) and isinstance(value, list):
            # An ordered union, not a concatenation: a shared junction edge's
            # `properties` list is declared by the source that owns the shape
            # and extended by the sources that add columns to the same CSV, and
            # neither should have to know about the other's entries.
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


def merge_fragments(fragments: Iterable[tuple[str, Mapping[str, Any]]]) -> dict[str, Any]:
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

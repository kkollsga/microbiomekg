#!/usr/bin/env python3
"""Launch the MicrobiomeKG MCP server, or self-test its configuration.

kglite's manifest has no ``graph:`` key — the graph is argv and the manifest is
only the tool surface — so a bare ``kglite-mcp-server --mcp-config …`` serves
*no graph* and fails in a way that looks like an empty database. This script is
the pairing, and it is the only supported way to start the server::

    .venv/bin/python scripts/serve.py              # serve on stdio
    .venv/bin/python scripts/serve.py --selftest   # green/red config check

Register it with an MCP client as the command, with ``--`` nothing after it:
the server speaks stdio, so its **stdout is the protocol** and anything this
script prints there would corrupt the stream. Everything below writes to
stderr for that reason.

Read-only: no ``--writable``, and the manifest declares no
``extensions.writable``. The graph is a published measurement whose goldens
``tests/test_acceptance.py`` asserts; an agent that could edit an evidence edge
could invalidate every one of them silently.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

#: The graph is the operator's (relative to the working directory, like the
#: build's ``--out`` default); the manifest ships inside the package.
GRAPH = Path("graph/microbiomekg.kgl")
MANIFEST = Path(__file__).resolve().parent / "mcp" / "microbiomekg_mcp.yaml"


def server_binary() -> str | None:
    """The ``kglite-mcp-server`` the *wheel* installed, preferred over PATH.

    The wheel ships the command as a console script beside this venv's
    interpreter, and that copy is the one carrying the Python embedder factory
    the manifest's ``extensions.embedder`` needs. A PATH lookup can find a
    standalone ``cargo install`` binary instead, which has no libpython and
    would refuse the factory at boot — so the venv is checked first and PATH is
    only the fallback.
    """
    local = Path(sys.executable).parent / "kglite-mcp-server"
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    return shutil.which("kglite-mcp-server")


def build_argv(binary: str, selftest: bool, graph: Path, manifest: Path) -> list[str]:
    argv = [binary, "--graph", str(graph), "--mcp-config", str(manifest)]
    if selftest:
        argv.append("--selftest")
    return argv


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", type=Path, default=GRAPH)
    ap.add_argument("--mcp-config", type=Path, default=MANIFEST, dest="manifest")
    ap.add_argument(
        "--selftest",
        action="store_true",
        help="Drive a live MCP handshake and print one line per capability "
        "instead of serving. Exits non-zero on any failure, so it doubles as "
        "a smoke gate.",
    )
    args = ap.parse_args(argv)

    binary = server_binary()
    if binary is None:
        print(
            "ERROR: kglite-mcp-server not found. It ships in the kglite wheel — "
            "`uv pip install --python .venv/bin/python kglite` — as a console "
            "script beside this interpreter.",
            file=sys.stderr,
        )
        return 1
    if not args.graph.exists():
        print(
            f"ERROR: no graph at {args.graph}. Build it with "
            f"`.venv/bin/python scripts/build.py --scope microbial`.",
            file=sys.stderr,
        )
        return 1
    if not args.manifest.is_file():
        print(f"ERROR: no manifest at {args.manifest}", file=sys.stderr)
        return 1

    command = build_argv(binary, args.selftest, args.graph, args.manifest)
    print(f"exec: {' '.join(command)}", file=sys.stderr)
    # `microbiomekg` must import inside the server's Python for the manifest's
    # embedder factory to resolve. From a checkout the package's parent is on
    # no path the server would find by itself, so it is handed over here;
    # an installed package makes the entry redundant and harmless.
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(Path(__file__).resolve().parent.parent)]
        + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    os.execve(command[0], command, env)


if __name__ == "__main__":
    raise SystemExit(main())

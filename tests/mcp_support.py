"""Shared helpers for the MCP-surface tests: a stdio client and a frontmatter reader.

Two things this venv does not have, and why each is hand-rolled rather than
installed:

- **No ``mcp`` client package.** The protocol over stdio is newline-delimited
  JSON-RPC 2.0 — one object per line, no ``Content-Length`` framing — so a
  client is thirty lines. :class:`MCPClient` is that, and it is deliberately
  *not* a general one: it drives the handshake, ``tools/list`` and
  ``tools/call``, and raises on anything it does not understand rather than
  degrading.
- **No PyYAML.** :func:`read_frontmatter` parses the flat subset the skills in
  ``mcp/microbiomekg.skills/`` actually use — scalars, inline lists, one level
  of nested mapping, block scalars — and **raises on anything outside it**. A
  parser that silently ignored a key it could not read would let a broken
  ``applies_when`` pass this suite and go dark on the real server, so the
  authoritative check is not this parser at all: it is that the server injects
  the skill into a tool description (``tools/list``), which only happens when
  mcp-methods itself parsed the frontmatter.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "graph" / "microbiomekg.kgl"
MANIFEST = ROOT / "mcp" / "microbiomekg_mcp.yaml"
SKILLS_DIR = ROOT / "mcp" / "microbiomekg.skills"

#: mcp-methods caps an injected skill body at 16 KB hard, with a 4 KB soft
#: target. Past the hard cap the body is truncated with a marker, so a skill
#: over it ships methodology the agent never sees.
SKILL_BODY_HARD_CAP = 16 * 1024


def server_binary() -> str | None:
    """The wheel's ``kglite-mcp-server``, or None when it is not installed."""
    local = Path(sys.executable).parent / "kglite-mcp-server"
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    from shutil import which

    return which("kglite-mcp-server")


class MCPClient:
    """A newline-delimited JSON-RPC client over the server's stdio.

    Context-managed: ``__enter__`` completes the ``initialize`` handshake and
    sends ``notifications/initialized``, so the server is ready for tool calls
    on the first statement of the block.
    """

    def __init__(self, argv: list[str], cwd: Path = ROOT, timeout: float = 90.0) -> None:
        env = dict(os.environ)
        # The manifest's embedder factory is `microbiomekg.embedder:build`, and
        # the repo root reaches the server's Python by no other route.
        env["PYTHONPATH"] = os.pathsep.join(
            [str(ROOT)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
        )
        self._proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(cwd),
            env=env,
        )
        self._next_id = 0
        self.server_info: dict = {}
        self.instructions: str = ""

    def __enter__(self) -> MCPClient:
        result = self.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "microbiomekg-tests", "version": "0"},
            },
        )
        self.server_info = result.get("serverInfo", {})
        self.instructions = result.get("instructions", "") or ""
        self._notify("notifications/initialized")
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover - a wedged child
                self._proc.kill()
        for stream in (self._proc.stdin, self._proc.stdout, self._proc.stderr):
            if stream is not None:
                stream.close()

    def _send(self, message: dict) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.write(json.dumps(message) + "\n")
        self._proc.stdin.flush()

    def _notify(self, method: str, params: dict | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def request(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        assert self._proc.stdout is not None
        while True:
            line = self._proc.stdout.readline()
            if not line:
                stderr = self._proc.stderr.read() if self._proc.stderr else ""
                raise RuntimeError(
                    f"server closed stdout before answering {method!r}. stderr tail:\n"
                    + "\n".join(stderr.strip().splitlines()[-15:])
                )
            message = json.loads(line)
            # Server-initiated notifications carry no id; skip them rather than
            # mistaking one for this request's answer.
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"{method} failed: {message['error']}")
            return message.get("result", {})

    def tools(self) -> dict[str, dict]:
        return {tool["name"]: tool for tool in self.request("tools/list")["tools"]}

    def call(self, name: str, arguments: dict) -> str:
        """Call a tool, returning its concatenated text content.

        ``isError`` is raised rather than returned: every caller here is
        asserting a successful query, and a tool error arriving as an ordinary
        string is how a broken query passes as an answer.
        """
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        text = "\n".join(
            block.get("text", "") for block in result.get("content", []) if block.get("type") == "text"
        )
        if result.get("isError"):
            raise RuntimeError(f"tool {name} returned isError with: {text}")
        return text


def read_frontmatter(path: Path) -> tuple[dict, str]:
    """Split a skill file into (frontmatter mapping, body).

    Supports exactly what these skills use: ``key: scalar``, ``key: [a, b]``,
    ``key:`` followed by ``- item`` lines, a one-level nested mapping, and a
    folded/literal block scalar. Anything else raises — see the module
    docstring for why silence would be worse than a failure.
    """
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not match:
        raise ValueError(f"{path}: no YAML frontmatter between --- fences")
    lines = match.group(1).split("\n")
    body = match.group(2)

    data: dict = {}
    key: str | None = None
    container: dict | list | None = None
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        stripped = raw.strip()

        if indent and container is not None:
            if stripped.startswith("- "):
                if not isinstance(container, list):
                    raise ValueError(f"{path}: list item under a mapping key {key!r}")
                container.append(_scalar(stripped[2:]))
            elif ":" in stripped:
                if not isinstance(container, dict):
                    raise ValueError(f"{path}: mapping entry under a list key {key!r}")
                sub_key, _, sub_value = stripped.partition(":")
                container[sub_key.strip()] = _scalar(sub_value.strip())
            else:
                raise ValueError(f"{path}: unparsable frontmatter line {raw!r}")
            continue

        if ":" not in stripped:
            raise ValueError(f"{path}: unparsable frontmatter line {raw!r}")
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if value in ("|", ">"):
            block, i = _block_scalar(lines, i)
            data[key] = block
            container = None
        elif value == "":
            # A list or a nested mapping follows; which one the next line says.
            nxt = next((line for line in lines[i:] if line.strip()), "")
            container = [] if nxt.strip().startswith("- ") else {}
            data[key] = container
        else:
            if value.startswith('"') and not value.endswith('"'):
                # A double-quoted scalar wrapped over indented continuation
                # lines — how every skill writes its `description`.
                parts = [value]
                while i < len(lines) and not parts[-1].rstrip().endswith('"'):
                    parts.append(lines[i].strip())
                    i += 1
                value = " ".join(parts)
            data[key] = _scalar(value)
            container = None
    return data, body


def _scalar(value: str):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [_scalar(part) for part in inner.split(",")] if inner else []
    if value in ("true", "false"):
        return value == "true"
    return value


def _block_scalar(lines: list[str], i: int) -> tuple[str, int]:
    collected: list[str] = []
    while i < len(lines):
        line = lines[i]
        if line.strip() and not line.startswith((" ", "\t")):
            break
        collected.append(line.strip())
        i += 1
    return "\n".join(collected).strip(), i


#: Fenced ```cypher blocks, as authored. The skills put one statement per
#: block on purpose: `graph.cypher()` takes one statement, and a test that
#: split a two-statement block on blank lines would be guessing.
CYPHER_FENCE = re.compile(r"```cypher\n(.*?)```", re.DOTALL)


def cypher_blocks(body: str) -> list[str]:
    return [block.strip() for block in CYPHER_FENCE.findall(body)]

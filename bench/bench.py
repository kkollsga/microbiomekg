#!/usr/bin/env python3
"""The MicrobiomeKG performance harness: build, load, save, index, query, MCP.

Run it from the repo root with the repo's venv::

    .venv/bin/python bench/bench.py --label eight-sources          # everything
    .venv/bin/python bench/bench.py --sections query,control       # queries only
    .venv/bin/python bench/bench.py --quick --sections query       # smoke it

It writes two files per capture: ``bench/results/<date>-<label>.json`` (every
sample of every cell, for a later re-read) and ``bench/results/<date>-<label>.md``
(the capture table). ``bench/README.md`` says what each cell means.

**The protocol this obeys is KGLite's** — ``../../Rust/KGLite/CLAUDE.md``,
"Performance protocol", because the thing being measured is kglite serving this
graph. Six of its nine items are mechanised here rather than left to the
operator:

1. *Release mode only.* The venv's ``kglite`` is the PyPI wheel; the harness
   refuses to run against a locally built debug extension (:func:`check_release`),
   because a debug build silently disables the assertions the engine's own
   suite relies on and its timings are not comparable to anything.
2. *``min`` over ``median`` for sub-millisecond cells — except two classes.*
   :func:`summarise` picks the statistic per cell and records **which**: ``min``
   by default; ``median`` when a cell is heavy-tailed by the protocol's own
   test (its ``min`` sits 30%+ below its own median, so the ``min`` is a lucky
   round rather than a rate); ``mean`` for cells declared once-per-event (a
   build, a save, a cold-ish load), where the repeats are structurally
   different from the first and a ``min`` would report only the cheap ones.
3. *Tighten noisy cells.* Round counts are chosen from a pilot: 200 rounds for
   sub-10-µs cells, 100 up to 10 ms, then whatever fits the time budget, with
   20 warmup iterations (5 for cells over 100 ms).
4. *Control cells as the drift meter.* :data:`CONTROLS` are four cells whose
   value cannot move when a source lands — three pure-executor Cypher cells and
   one that does not touch kglite at all — and the capture **fails the control
   contract** and says so if any of their medians sits below 2x the measured
   noise floor. The floor is measured, not assumed (:data:`FLOOR_QUERY`).
5. *Read the distribution.* Every cell carries min/median/mean/p95/max and is
   flagged when ``max / median >= 30`` — a rare expensive branch, which the
   protocol says to chase rather than average away.
6. *Run under whatever load the machine has, and record it.* The capture's
   metadata carries the load average at start and end and the machine state, so
   a later reader can tell a hot capture from a cold one.

The query cells are **not synthetic**. They are extracted from
``docs/usecases-and-pitfalls.md`` Part D at run time — every ``answerable-now``
and ``partial`` query, as authored — so a new source that edits Part D moves the
benchmark with it, and a query that stops running is a finding rather than a
silently dropped row. The three reconciliation cells come from
``microbiomekg/mcp/microbiomekg.skills/reconciliation.md`` for the same reason: that file is
the authority for the hybrid lookup, and D12's fenced block carries only its
lexical half.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import resource
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

USECASES = ROOT / "docs" / "usecases-and-pitfalls.md"
RECONCILIATION = (
    ROOT / "microbiomekg" / "mcp" / "microbiomekg.skills" / "reconciliation.md"
)
MANIFEST = ROOT / "microbiomekg" / "mcp" / "microbiomekg_mcp.yaml"
RESULTS = Path(__file__).resolve().parent / "results"

#: Where the harness writes the graphs it builds. Deliberately **outside the
#: repo and outside ``graph/``**: a capture must not clobber the shipped
#: ``graph/microbiomekg.kgl`` that ``scripts/serve.py`` serves and
#: ``tests/test_acceptance.py`` asserts against, and a 450 MB build artifact
#: has no business accumulating in a git tree. It is on the same volume as the
#: repo on purpose — the shipped build writes there, and an internal-disk
#: scratch would measure a different device. Remove it with ``rm -rf``; nothing
#: else owns it.
SCRATCH = Path("/Volumes/EksternalHome/coding-cache/microbiomekg-bench")

#: kglite's blueprint junction loader deduplicates parallel edges from the
#: second chunk onward, and this graph's parallel edges are its independent
#: observations. Same constant, same reason, as ``scripts/build.py``.
JUNCTION_CHUNK_SIZE = "1000000"

#: The cheapest possible ``graph.cypher()`` round trip. Its median is the
#: capture's **noise floor**: the cost of dispatch and result materialisation
#: with no graph work behind it. Every control is required to sit at 2x this or
#: more (protocol item 8), and a query cell near it is reported as measuring
#: dispatch rather than the query.
FLOOR_QUERY = "RETURN 1 AS x"

#: Unchanged-path control cells — the machine-drift meter. A control that moves
#: between captures means the instrument moved, not the graph.
#:
#: The first three are **pure executor**: ``UNWIND range(...)`` touches no node,
#: no edge and no index, so no source landing can move them. The fourth is not
#: kglite at all — a fixed 16 MiB SHA-256 — and is the cross-check that says
#: whether a drift is kglite's or the machine's (protocol item 8: measure a
#: claim two independent ways).
#:
#: A *graph* control was tried and rejected: the obvious candidates
#: (``MATCH (t:Taxon) RETURN count(t)``, a label count) answer from a metadata
#: fast path in 0.9 us — at the noise floor, measuring nothing — and the ones
#: that do real work (a lineage walk, a 1-hop expansion) move when the taxonomy
#: dump or a source's cited-taxa set moves, which is the failure mode protocol
#: item 8 names: "a control chosen because our source can't touch it silently
#: expires when the thing that moves is a dependency". ``lineage_walk`` is kept
#: as a *reported* cell rather than a control for exactly that reason.
CONTROLS: tuple[tuple[str, str], ...] = (
    ("ctrl_unwind_200k", "UNWIND range(1, 200000) AS i RETURN count(i) AS n"),
    ("ctrl_unwind_20k", "UNWIND range(1, 20000) AS i RETURN count(i) AS n"),
    (
        "ctrl_unwind_case_20k",
        "UNWIND range(1, 20000) AS i "
        "RETURN sum(CASE WHEN i % 7 = 0 THEN i ELSE 0 END) AS n",
    ),
)

#: The non-kglite control: 16 MiB of SHA-256. Pure CPU, no allocation, no I/O.
SHA_CONTROL_BYTES = 16 * 1024 * 1024

#: Query shapes the evaluation asks for by name that Part D does not carry as
#: its own fenced block. Each says where it came from.
EXTRA_QUERIES: tuple[tuple[str, str, dict | None, str], ...] = (
    (
        "point_taxon_by_id",
        "MATCH (t:Taxon {id: 851}) RETURN t.title AS name, t.rank AS rank, "
        "t.placeholder AS placeholder",
        None,
        "point lookup on the blueprint pk — the cheapest shape the graph has",
    ),
    (
        "lineage_walk",
        "MATCH (t:Taxon {id: 562})-[:HAS_PARENT*1..12]->(a:Taxon) RETURN count(a) AS n",
        None,
        "variable-length walk over the NCBI ancestor chain (docs/model.md §5)",
    ),
)

#: The reconciliation lookups, by their block index in
#: ``microbiomekg/mcp/microbiomekg.skills/reconciliation.md``. D12's own fenced block is the
#: lexical half only; the misspelling case the evaluation asks for is the fused
#: one, and it is authored there.
RECON_CELLS: tuple[tuple[str, int, dict], ...] = (
    (
        "recon_bm25_synonym",
        0,
        {"name": "Lactobacillus reuteri", "rank": "species"},
    ),
    (
        "recon_vector_2lane",
        1,
        {"name": "Clostridium dificile", "epithet": "dificile", "rank": "species"},
    ),
    (
        "recon_hybrid_fused",
        2,
        {"name": "Clostridium dificile", "epithet": "dificile", "rank": "species"},
    ),
)

#: The Part D cells the MCP section re-issues over the protocol. They are named
#: rather than re-written so the MCP row and the section-5 row are the *same
#: query text* — a comparison against a paraphrase would measure the paraphrase.
#: ``mcp_floor`` is added alongside them: the protocol round trip with no graph
#: work behind it, which is the agent surface's fixed cost on its own.
MCP_QUERY_IDS: tuple[str, ...] = ("D2", "D15.1")


# --------------------------------------------------------------------------
# timing core
# --------------------------------------------------------------------------


@dataclass
class Cell:
    """One measured thing, with every sample kept.

    ``statistic`` is not chosen by the caller except for ``once_per_event``:
    :func:`summarise` applies the protocol's own tests to the samples and
    records which rule fired, so a row in the capture can always say why it is
    quoting the number it quotes.
    """

    name: str
    samples: list[float]
    unit: str = "s"
    rows: int | None = None
    note: str = ""
    once_per_event: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return summarise(self)


def summarise(cell: Cell) -> dict[str, Any]:
    """Distribution, chosen statistic, and the flags protocol items 4/8 want."""
    s = sorted(cell.samples)
    n = len(s)
    if n == 0:
        return {"name": cell.name, "n": 0, "note": cell.note, "statistic": "none"}
    lo, med, hi = s[0], statistics.median(s), s[-1]
    mean = statistics.fmean(s)
    heavy_tailed = n >= 5 and med > 0 and lo < 0.70 * med
    rare_branch = n >= 5 and med > 0 and hi >= 30 * med

    if cell.once_per_event:
        statistic, why = (
            "mean",
            "once-per-event cost; min would report only the cheap repeats",
        )
    elif heavy_tailed:
        statistic, why = (
            "median",
            f"heavy-tailed: min is {lo / med:.0%} of its own median",
        )
    else:
        statistic, why = "min", "repeatable cell; min is the best-case rate"

    return {
        "name": cell.name,
        "n": n,
        "unit": cell.unit,
        "rows": cell.rows,
        "note": cell.note,
        "statistic": statistic,
        "statistic_reason": why,
        "value": {"min": lo, "median": med, "mean": mean}[statistic],
        "min": lo,
        "median": med,
        "mean": mean,
        "p95": s[min(n - 1, int(round(0.95 * (n - 1))))],
        "max": hi,
        "stdev": statistics.stdev(s) if n > 1 else 0.0,
        "max_over_median": (hi / med) if med else None,
        "rare_branch": rare_branch,
        "heavy_tailed": heavy_tailed,
        **cell.extra,
    }


def measure(
    name: str,
    fn: Callable[[], Any],
    *,
    budget_s: float = 2.0,
    scale: float = 1.0,
    note: str = "",
    once_per_event: bool = False,
    max_rounds: int = 5000,
) -> Cell:
    """Time ``fn`` under the protocol's round/warmup policy.

    A five-call pilot sets the round count and the warmup: 200 rounds for a
    sub-10-us cell, 100 up to 10 ms, then whatever the time budget allows, never
    fewer than 5. The pilot's own samples are discarded — they are the warmup.
    """
    pilot = []
    for _ in range(5):
        t = time.perf_counter()
        result = fn()
        pilot.append(time.perf_counter() - t)
    est = min(pilot)

    if est < 10e-6:
        rounds, warmup = 200, 20
    elif est < 10e-3:
        rounds, warmup = 100, 20
    elif est < 100e-3:
        rounds, warmup = 20, 5
    else:
        rounds, warmup = 5, 1
    rounds = max(5, min(max_rounds, int(rounds * scale)))
    if est * rounds > budget_s * max(scale, 1.0):
        rounds = max(5, int((budget_s * max(scale, 1.0)) / est))

    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(rounds):
        t = time.perf_counter()
        result = fn()
        samples.append(time.perf_counter() - t)

    rows = len(result) if isinstance(result, (list, tuple)) else None
    return Cell(name, samples, rows=rows, note=note, once_per_event=once_per_event)


# --------------------------------------------------------------------------
# environment
# --------------------------------------------------------------------------


def check_release() -> dict[str, Any]:
    """Refuse to time a debug-built extension (protocol item 2).

    The wheel's ``WHEEL`` metadata names maturin and an abi3 platform tag; a
    locally built debug extension arrives through ``maturin develop`` and has
    no such record beside it. This is a gate, not a note: debug-profile numbers
    "must be discarded", so the harness declines to produce them.
    """
    import kglite

    site = Path(kglite.__file__).resolve().parent
    dist = next(site.parent.glob("kglite-*.dist-info"), None)
    wheel = (dist / "WHEEL").read_text(encoding="utf-8") if dist else ""
    tag = next(
        (
            line.split(":", 1)[1].strip()
            for line in wheel.splitlines()
            if line.startswith("Tag:")
        ),
        "",
    )
    if "abi3" not in tag:
        raise SystemExit(
            f"kglite at {site} does not look like a released abi3 wheel (WHEEL tag "
            f"{tag!r}). Performance numbers from a debug build are invalid — "
            f"install the published wheel before capturing."
        )
    return {"version": kglite.__version__, "wheel_tag": tag, "path": str(site)}


def loadavg() -> list[float]:
    return list(os.getloadavg())


def machine_metadata(label: str) -> dict[str, Any]:
    head = subprocess.run(
        ["git", "log", "--oneline", "-1"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    return {
        "captured": time.strftime("%Y-%m-%d %H:%M:%S%z"),
        "source_set": label,
        "machine": subprocess.run(
            ["sysctl", "-n", "hw.model"], capture_output=True, text=True
        ).stdout.strip(),
        "cpu": subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True
        ).stdout.strip()
        or platform.processor(),
        "memory_gb": round(
            int(
                subprocess.run(
                    ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True
                ).stdout.strip()
            )
            / 2**30,
            1,
        ),
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "kglite": check_release(),
        "git_head": head,
        "git_dirty_paths": len(dirty.splitlines()),
        "loadavg_start": loadavg(),
    }


# --------------------------------------------------------------------------
# query extraction — Part D is the benchmark, verbatim
# --------------------------------------------------------------------------

CYPHER_FENCE = re.compile(r"```cypher\n(.*?)```", re.DOTALL)
SECTION = re.compile(r"\n### (D\d+)[^\n]*\n")
STATUS = re.compile(r"\*Status:\*\s*\*\*`?([a-z-]+)")


def _statements(block: str) -> list[str]:
    """The runnable statements in one fenced block.

    ``graph.cypher()`` takes one statement and Part D puts two in a fence where
    the second is the same question's audit trail (D12, D15, D16). They are
    separated by a blank line, which is the only separator the document offers;
    a chunk that is only a ``//`` comment is not a statement. Every chunk this
    produces is *probed* before it is timed, so a wrong split shows up as a
    named "did not run" row rather than a silently missing measurement.
    """
    out = []
    for chunk in block.split("\n\n"):
        body = "\n".join(
            line for line in chunk.splitlines() if not line.strip().startswith("//")
        ).strip()
        if body:
            out.append(body)
    return out


def part_d_queries() -> list[tuple[str, str, dict | None, str]]:
    """Every ``answerable-now`` / ``partial`` Part D query, as ``(id, cypher, params, note)``."""
    doc = USECASES.read_text(encoding="utf-8")
    part_d = doc.split("## Part D — Acceptance queries", 1)[1]
    pieces = SECTION.split(part_d)[1:]
    found: list[tuple[str, str, dict | None, str]] = []
    for name, body in zip(pieces[0::2], pieces[1::2]):
        status_match = STATUS.search(body)
        status = status_match.group(1) if status_match else "unknown"
        if status not in ("answerable-now", "partial"):
            continue
        statements = [
            q for block in CYPHER_FENCE.findall(body) for q in _statements(block)
        ]
        for index, query in enumerate(statements, start=1):
            # A section with one statement keeps the bare D-number; one with
            # several numbers them in document order, so `D15.1` is the audit
            # and `D15.2` the per-field census it rolls up.
            cell = name if len(statements) == 1 else f"{name}.{index}"
            found.append((cell, query, None, status))
    return found


def reconciliation_queries() -> list[tuple[str, str, dict | None, str]]:
    blocks = CYPHER_FENCE.findall(RECONCILIATION.read_text(encoding="utf-8"))
    out = []
    for name, index, params in RECON_CELLS:
        body = _statements(blocks[index])[0]
        out.append((name, body, params, "reconciliation skill"))
    return out


def query_set() -> list[tuple[str, str, dict | None, str]]:
    extras = [(n, q, p, note) for n, q, p, note in EXTRA_QUERIES]
    return part_d_queries() + reconciliation_queries() + extras


# --------------------------------------------------------------------------
# section 1 — the build
# --------------------------------------------------------------------------


class RSSSampler(threading.Thread):
    """Peak resident memory of a process tree, sampled from ``ps``.

    ``getrusage(RUSAGE_CHILDREN)`` reports the maximum over *terminated*
    children and cannot separate the build process (which loads the graph) from
    the prep child that happened to be the largest, and this capture needs both.
    So: one ``ps`` every 200 ms, a peak per pid, and each pid attributed to the
    build segment that was running when it was first seen. ``getrusage`` is
    still read at the end as the independent cross-check protocol item 8 wants.
    """

    def __init__(self, root_pid: int, interval: float = 0.2) -> None:
        super().__init__(daemon=True)
        self.root_pid = root_pid
        self.interval = interval
        self.stop_flag = threading.Event()
        self.peak_by_pid: dict[int, int] = {}
        self.peak_tree_kb = 0
        #: Peak of the whole tree, and of the root alone, *while each segment
        #: was running*. Attributing a pid to the segment it first appeared in
        #: would file the root process — the one that holds the graph — under
        #: `startup` and make that row the whole build's peak.
        self.peak_tree_by_segment: dict[str, int] = {}
        self.peak_root_by_segment: dict[str, int] = {}
        self.segment = "startup"

    def run(self) -> None:
        while not self.stop_flag.is_set():
            self._sample()
            self.stop_flag.wait(self.interval)
        self._sample()

    def _sample(self) -> None:
        try:
            out = subprocess.run(
                ["ps", "-eo", "pid=,ppid=,rss="],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout
        except Exception:  # pragma: no cover - ps is not expected to fail
            return
        children: dict[int, list[int]] = {}
        rss: dict[int, int] = {}
        for line in out.splitlines():
            parts = line.split()
            if len(parts) != 3:
                continue
            pid, ppid, kb = (int(p) for p in parts)
            children.setdefault(ppid, []).append(pid)
            rss[pid] = kb
        tree, stack = [], [self.root_pid]
        while stack:
            pid = stack.pop()
            if pid in rss:
                tree.append(pid)
                stack.extend(children.get(pid, ()))
        total = 0
        for pid in tree:
            kb = rss[pid]
            total += kb
            if kb > self.peak_by_pid.get(pid, 0):
                self.peak_by_pid[pid] = kb
        segment = self.segment
        self.peak_tree_kb = max(self.peak_tree_kb, total)
        self.peak_tree_by_segment[segment] = max(
            self.peak_tree_by_segment.get(segment, 0), total
        )
        self.peak_root_by_segment[segment] = max(
            self.peak_root_by_segment.get(segment, 0), rss.get(self.root_pid, 0)
        )


#: Lines ``scripts/build.py`` flushes to mark a phase boundary. Timestamping
#: them as they arrive segments the whole build from one run, rather than
#: re-running each prep separately and paying for the build twice.
BUILD_MARKERS = (
    (re.compile(r"^=== (prep_\w+\.py)"), "prep"),
    (re.compile(r"^=== blueprint <-"), "blueprint"),
    (re.compile(r"^=== ontology ->"), "ontology"),
    (re.compile(r"^=== from_blueprint"), "from_blueprint"),
    (re.compile(r"^--- text indexes"), "bm25_indexes"),
    (re.compile(r"^--- vector indexes"), "vector_indexes"),
    (re.compile(r"^--- nodes"), "report"),
    (re.compile(r"^saved "), "save"),
)


def segment_name(line: str) -> str | None:
    for pattern, kind in BUILD_MARKERS:
        match = pattern.match(line)
        if match:
            return match.group(1) if kind == "prep" else kind
    return None


def run_build(
    scratch: Path, log: Path, extra_args: Iterable[str] = ()
) -> dict[str, Any]:
    """``scripts/build.py`` end to end, segmented and RSS-sampled.

    Writes into ``scratch`` rather than ``data/csv`` and ``graph/`` — the
    shipped graph is what ``scripts/serve.py`` serves and what
    ``tests/test_acceptance.py`` asserts against, and a benchmark must not be
    able to invalidate either.
    """
    csv_dir = scratch / "csv"
    out = scratch / "build.kgl"
    csv_dir.mkdir(parents=True, exist_ok=True)
    argv = [
        sys.executable,
        str(ROOT / "scripts" / "build.py"),
        "--csv",
        str(csv_dir),
        "--out",
        str(out),
        "--scope",
        "microbial",
        *extra_args,
    ]
    before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss

    started = time.perf_counter()
    # PYTHONUNBUFFERED is what makes the segment table true. Only some of
    # `scripts/build.py`'s phase markers pass `flush=True`; behind a pipe the
    # rest sit in a block buffer until the process exits, so their timestamps
    # all land at the end and whichever segment precedes them swallows their
    # time. The first capture read `from_blueprint` at 90.8 s and the BM25
    # lane, the vector lane, the report and the save at 0.0 s each for exactly
    # that reason.
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    proc = subprocess.Popen(
        argv,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    sampler = RSSSampler(proc.pid)
    sampler.start()

    marks: list[tuple[str, float]] = [("startup", 0.0)]
    with log.open("w", encoding="utf-8") as fh:
        for line in proc.stdout:  # type: ignore[union-attr]
            elapsed = time.perf_counter() - started
            fh.write(f"{elapsed:9.3f} {line}")
            name = segment_name(line)
            if name:
                marks.append((name, elapsed))
                sampler.segment = name
    proc.wait()
    total = time.perf_counter() - started
    sampler.stop_flag.set()
    sampler.join(timeout=5)
    after = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss

    segments = [
        {"segment": name, "start_s": start, "seconds": end - start}
        for (name, start), (_, end) in zip(marks, marks[1:] + [("end", total)])
    ]
    # The build names the source set it actually loaded on its last line; a
    # capture that took its label from the operator's `--label` alone would be
    # wrong exactly when a source was skipped for an absent raw file.
    loaded = ""
    for line in log.read_text(encoding="utf-8").splitlines():
        if "sources loaded:" in line:
            loaded = line.split("sources loaded:", 1)[1].strip()

    return {
        "returncode": proc.returncode,
        "sources_loaded": loaded,
        "wall_seconds": total,
        "segments": segments,
        "peak_rss_root_mb": sampler.peak_by_pid.get(proc.pid, 0) / 1024,
        "peak_rss_tree_mb": sampler.peak_tree_kb / 1024,
        "peak_rss_by_segment_mb": {
            seg: kb / 1024 for seg, kb in sampler.peak_tree_by_segment.items()
        },
        "peak_rss_root_by_segment_mb": {
            seg: kb / 1024 for seg, kb in sampler.peak_root_by_segment.items()
        },
        # The independent cross-check on the ps sampler (protocol item 8): the
        # kernel's own high-water mark over every child this process has reaped,
        # in bytes on macOS. It cannot separate the build from its preps, which
        # is why the sampler exists — but if the two disagree by much, the
        # sampler missed a spike between two 200 ms ticks.
        "getrusage_children_peak_mb": after / 1e6,
        "getrusage_children_peak_before_mb": before / 1e6,
        "csv_dir": str(csv_dir),
        "graph": str(out),
        "graph_bytes": out.stat().st_size if out.exists() else 0,
        "csv_rows": csv_row_census(csv_dir),
        "log": str(log),
    }


def csv_row_census(csv_dir: Path) -> dict[str, Any]:
    """Data rows per CSV the build wrote, counted the way ``build.py`` counts."""
    per_file, total = {}, 0
    for path in sorted(csv_dir.glob("*.csv")):
        rows = 0
        with path.open("rb") as fh:
            while chunk := fh.read(1 << 20):
                rows += chunk.count(b"\n")
        rows = max(rows - 1, 0)
        per_file[path.name] = rows
        total += rows
    return {"total_rows": total, "files": len(per_file), "per_file": per_file}


# --------------------------------------------------------------------------
# sections 2-4 — load, index, save, reload (run in child processes)
# --------------------------------------------------------------------------


def child_build_graph(args: argparse.Namespace) -> None:
    """Child task: ``from_blueprint`` + every index, timed and sized one at a time.

    One child run answers sections 2, 3 and 4 together, because the numbers are
    the same run's: the load is separated from the prep by being *here* and not
    in ``scripts/build.py``; each index is timed alone; and the ``.kgl`` is
    saved after each one so the size a given index adds is the difference
    between two real files rather than an estimate.

    The per-index size deltas are **order-dependent and cumulative** — a save
    consolidates the whole graph, so the delta is "what the file grew by when
    this index joined the ones before it", in ``scripts/build.py``'s order.
    """
    os.environ["KGLITE_BLUEPRINT_JUNCTION_CHUNK_SIZE"] = JUNCTION_CHUNK_SIZE
    import kglite

    from microbiomekg.pipeline import TEXT_INDEXES, VECTOR_INDEXES  # noqa: PLC0415
    from microbiomekg.embedder import CharGramEmbedder  # noqa: PLC0415

    result: dict[str, Any] = {"indexes": [], "saves": []}
    blueprint = Path(args.blueprint)
    scratch = Path(args.scratch)

    t = time.perf_counter()
    graph = kglite.from_blueprint(blueprint, verbose=False, save=False)
    result["from_blueprint_seconds"] = time.perf_counter() - t
    result["rss_after_load_mb"] = (
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
    )
    result["nodes"] = list(graph.cypher("MATCH (n) RETURN count(n) AS n"))[0]["n"]
    result["edges"] = list(graph.cypher("MATCH ()-[r]->() RETURN count(r) AS r"))[0][
        "r"
    ]

    def save_to(path: Path, tag: str) -> int:
        t0 = time.perf_counter()
        graph.save(str(path))
        seconds = time.perf_counter() - t0
        size = path.stat().st_size
        result["saves"].append({"tag": tag, "seconds": seconds, "bytes": size})
        return size

    baseline = save_to(scratch / "stage-none.kgl", "no-index")
    previous = baseline

    for node_type, prop in TEXT_INDEXES:
        t0 = time.perf_counter()
        stats = graph.build_text_index(node_type, prop)
        seconds = time.perf_counter() - t0
        size = save_to(
            scratch / f"stage-bm25-{node_type}-{prop}.kgl", f"bm25:{node_type}.{prop}"
        )
        result["indexes"].append(
            {
                "index": f"BM25 {node_type}.{prop}",
                "lane": "bm25",
                "seconds": seconds,
                "documents": stats.get("indexed", 0),
                "terms": stats.get("terms", 0),
                "skipped": stats.get("skipped", 0),
                "kgl_bytes": size,
                "delta_bytes": size - previous,
            }
        )
        previous = size
    bm25_path = scratch / "bm25.kgl"
    result["bm25_only"] = {
        "path": str(bm25_path),
        "bytes": save_to(bm25_path, "bm25-only"),
    }
    previous = result["bm25_only"]["bytes"]

    graph.set_embedder(CharGramEmbedder())
    for node_type, prop, ef_search in VECTOR_INDEXES:
        t0 = time.perf_counter()
        embed_stats = graph.embed_texts(node_type, prop, show_progress=False)
        embed_seconds = time.perf_counter() - t0
        t0 = time.perf_counter()
        index_stats = graph.build_vector_index(node_type, prop, ef_search=ef_search)
        index_seconds = time.perf_counter() - t0
        size = save_to(
            scratch / f"stage-vec-{node_type}-{prop}.kgl", f"vector:{node_type}.{prop}"
        )
        result["indexes"].append(
            {
                "index": f"vector {node_type}.{prop}",
                "lane": "vector",
                "seconds": embed_seconds + index_seconds,
                "embed_seconds": embed_seconds,
                "hnsw_seconds": index_seconds,
                "documents": embed_stats.get("embedded", 0),
                "dimension": embed_stats.get("dimension", 0),
                "skipped": embed_stats.get("skipped", 0),
                "indexed": index_stats.get("indexed", 0),
                "ef_search": ef_search,
                "kgl_bytes": size,
                "delta_bytes": size - previous,
            }
        )
        previous = size

    full_path = scratch / "full.kgl"
    result["full"] = {"path": str(full_path), "bytes": save_to(full_path, "full")}
    result["peak_rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
    Path(args.json_out).write_text(json.dumps(result, indent=2), encoding="utf-8")


def child_load(args: argparse.Namespace) -> None:
    """Child task: one ``kglite.load()`` in a fresh process, and nothing else.

    A fresh process per load on purpose. Repeating a load inside one process
    measures a warm allocator and a warm arena, which is not the number a
    consumer pays; the only shared warmth left is the page cache, and the
    caller decides what that is by *when* it launches this.
    """
    import kglite

    t = time.perf_counter()
    graph = kglite.load(args.file)
    seconds = time.perf_counter() - t
    payload = {
        "seconds": seconds,
        "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6,
        "bytes": Path(args.file).stat().st_size,
    }
    if args.counts:
        payload["nodes"] = list(graph.cypher("MATCH (n) RETURN count(n) AS n"))[0]["n"]
        payload["edges"] = list(graph.cypher("MATCH ()-[r]->() RETURN count(r) AS r"))[
            0
        ]["r"]
    Path(args.json_out).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_child(task: str, work_dir: Path, **kwargs: Any) -> dict[str, Any]:
    """Run one child task and read back its JSON. Never guess from stdout.

    ``work_dir`` is where the handshake file goes; a child's own ``--scratch``
    is passed through ``kwargs`` and is deliberately a different name, because
    the two collided once and cost a capture.
    """
    out = work_dir / f"child-{task}-{os.getpid()}-{int(time.time() * 1000)}.json"
    argv = [
        sys.executable,
        str(Path(__file__).resolve()),
        "child",
        "--task",
        task,
        "--json-out",
        str(out),
    ]
    for key, value in kwargs.items():
        if value is False or value is None:
            continue  # a store_true flag is omitted, never passed "False"
        flag = "--" + key.replace("_", "-")
        argv.extend([flag] if value is True else [flag, str(value)])
    proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0 or not out.exists():
        raise SystemExit(
            f"child task {task} failed ({proc.returncode}); stderr tail:\n"
            + "\n".join(proc.stderr.strip().splitlines()[-20:])
        )
    return json.loads(out.read_text(encoding="utf-8"))


def run_load_series(path: Path, scratch: Path, repeats: int) -> dict[str, Any]:
    """Load timings: the first touch after the write, then the warm repeats.

    **Neither of these is a cold-cache number and the capture says so.** Purging
    the macOS unified buffer cache needs ``sudo purge``, which this harness does
    not have and will not ask for; so the honest pair is *first load after the
    save that wrote the file* (the file's pages are in cache because writing put
    them there) and *repeat loads* (in cache because reading put them there).
    The difference between the two is what page-cache state is worth here, and
    it is not the difference between cold and warm.
    """
    samples = []
    for i in range(repeats):
        payload = run_child("load", scratch, file=path, counts=(i == 0))
        samples.append(payload)
    first, rest = samples[0], samples[1:]
    return {
        "path": str(path),
        "bytes": first["bytes"],
        "first_touch_after_write_s": first["seconds"],
        "first_touch_peak_rss_mb": first["peak_rss_mb"],
        "warm_repeats": [s["seconds"] for s in rest],
        "warm_cell": Cell(
            f"load {path.name} (warm)",
            [s["seconds"] for s in rest],
            once_per_event=True,
            note="fresh process per sample; page cache warm from earlier reads",
        ).summary()
        if rest
        else None,
        "nodes": first.get("nodes"),
        "edges": first.get("edges"),
    }


# --------------------------------------------------------------------------
# section 5-6 — queries and controls
# --------------------------------------------------------------------------


def probe(graph, query: str, params: dict | None) -> tuple[bool, int, str]:
    try:
        rows = list(
            graph.cypher(query, params=params) if params else graph.cypher(query)
        )
        return True, len(rows), ""
    except Exception as exc:  # a query that stops running is a finding, not a crash
        return False, 0, str(exc).splitlines()[0][:200]


def run_queries(graph, scale: float) -> dict[str, Any]:
    cells, skipped = [], []
    for name, query, params, note in query_set():
        ok, rows, error = probe(graph, query, params)
        if not ok:
            skipped.append({"name": name, "error": error, "query": query})
            continue

        def call(q=query, p=params):
            return list(graph.cypher(q, params=p) if p else graph.cypher(q))

        cell = measure(name, call, scale=scale, note=note)
        cell.rows = rows
        cell.extra["query"] = " ".join(query.split())
        cells.append(cell.summary())
    return {"cells": cells, "did_not_run": skipped}


def run_controls(graph, scale: float) -> dict[str, Any]:
    """The controls, plus the floor they are measured against."""
    floor = measure(
        "noise_floor",
        lambda: list(graph.cypher(FLOOR_QUERY)),
        scale=scale,
        note="cheapest possible cypher round trip: dispatch + materialisation",
    )
    floor_summary = floor.summary()
    floor_median = floor_summary["median"]

    cells = []
    for name, query in CONTROLS:
        cell = measure(
            name,
            lambda q=query: list(graph.cypher(q)),
            scale=scale,
            note="pure executor: touches no node, edge or index",
        )
        summary = cell.summary()
        summary["over_floor"] = (
            summary["median"] / floor_median if floor_median else None
        )
        summary["passes_2x_floor"] = bool(
            summary["over_floor"] and summary["over_floor"] >= 2
        )
        cells.append(summary)

    buf = b"\x5a" * SHA_CONTROL_BYTES
    sha = measure(
        "ctrl_sha256_16mib",
        lambda: hashlib.sha256(buf).hexdigest(),
        scale=scale,
        note="not kglite at all — the CPU/thermal cross-check",
    )
    sha_summary = sha.summary()
    sha_summary["over_floor"] = (
        sha_summary["median"] / floor_median if floor_median else None
    )
    sha_summary["passes_2x_floor"] = True
    cells.append(sha_summary)

    return {
        "floor": floor_summary,
        "cells": cells,
        "contract_holds": all(c["passes_2x_floor"] for c in cells),
    }


# --------------------------------------------------------------------------
# section 7 — the MCP surface
# --------------------------------------------------------------------------


def run_mcp(graph_path: Path, graph, scale: float) -> dict[str, Any]:
    """The same queries over stdio JSON-RPC and in-process, side by side.

    Boot is reported separately from per-call latency because they are different
    costs to a different party: an agent pays boot once per session (it includes
    loading the ``.kgl``) and per-call on every question. ``mcp_floor`` is the
    round trip with no graph work behind it — the overhead itself.
    """
    from tests.mcp_support import MCPClient, server_binary  # noqa: PLC0415

    binary = server_binary()
    if binary is None:
        return {"skipped": "kglite-mcp-server is not installed beside this interpreter"}

    by_id = {name: query for name, query, _, _ in part_d_queries()}
    missing = [name for name in MCP_QUERY_IDS if name not in by_id]
    if missing:
        return {"skipped": f"Part D no longer carries {', '.join(missing)}"}
    cells = [("mcp_floor", FLOOR_QUERY)] + [
        (name, by_id[name]) for name in MCP_QUERY_IDS
    ]

    argv = [binary, "--graph", str(graph_path), "--mcp-config", str(MANIFEST)]
    boot = time.perf_counter()
    client = MCPClient(argv)
    with client:
        boot_seconds = time.perf_counter() - boot
        rows = []
        for name, query in cells:
            over_mcp = measure(
                name,
                lambda q=query: client.call("cypher_query", {"query": q}),
                scale=scale,
                note="one tools/call over stdio JSON-RPC",
            )
            direct = measure(
                f"{name}_direct",
                lambda q=query: list(graph.cypher(q)),
                scale=scale,
                note="the same query in-process through graph.cypher()",
            )
            mcp_summary, direct_summary = over_mcp.summary(), direct.summary()
            rows.append(
                {
                    "cell": name,
                    "mcp": mcp_summary,
                    "direct": direct_summary,
                    "overhead_s": mcp_summary["value"] - direct_summary["value"],
                    "ratio": (mcp_summary["value"] / direct_summary["value"])
                    if direct_summary["value"]
                    else None,
                }
            )
    return {
        "binary": binary,
        "boot_and_handshake_s": boot_seconds,
        "note": "boot includes loading the .kgl and the initialize handshake",
        "cells": rows,
    }


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


def render(capture: dict[str, Any]) -> str:
    """Hand the capture to :mod:`bench.render`, which is a separate module so a
    capture can be re-rendered from its JSON without re-measuring."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from render import render_markdown  # noqa: PLC0415

    return render_markdown(capture)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

SECTIONS = ("build", "load", "saveload", "index", "query", "control", "mcp")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command")

    child = sub.add_parser("child", help=argparse.SUPPRESS)
    child.add_argument("--task", required=True, choices=("build_graph", "load"))
    child.add_argument("--json-out", required=True)
    child.add_argument("--blueprint")
    child.add_argument("--scratch")
    child.add_argument("--file")
    child.add_argument("--counts", action="store_true")

    ap.add_argument(
        "--label", default="current", help="the source set this capture covers"
    )
    ap.add_argument(
        "--note",
        default="",
        help="a paragraph recorded in the capture's metadata. "
        "Protocol item 7: a capture that will be compared "
        "across sessions has to carry the machine state it "
        "was taken under, and the load average alone does not "
        "say what else was competing for the machine.",
    )
    ap.add_argument("--sections", default=",".join(SECTIONS))
    ap.add_argument("--scratch", type=Path, default=SCRATCH)
    ap.add_argument(
        "--graph",
        type=Path,
        default=None,
        help="an existing .kgl for the query/control/mcp sections; "
        "default is the one this capture's build produced, "
        "falling back to graph/microbiomekg.kgl",
    )
    ap.add_argument(
        "--build-args",
        default="",
        help="extra argv for scripts/build.py, space separated "
        "(`--with-kegg`, or `--skip-prep` to time a load-only "
        "build against CSVs already in --scratch/csv)",
    )
    ap.add_argument("--load-repeats", type=int, default=4)
    ap.add_argument(
        "--scale", type=float, default=1.0, help="multiply every round count"
    )
    ap.add_argument("--quick", action="store_true", help="validation run: few rounds")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    if args.command == "child":
        {"build_graph": child_build_graph, "load": child_load}[args.task](args)
        return 0

    scale = 0.1 if args.quick else args.scale
    wanted = [s for s in args.sections.split(",") if s]
    unknown = [s for s in wanted if s not in SECTIONS]
    if unknown:
        raise SystemExit(f"unknown section(s): {', '.join(unknown)}")
    args.scratch.mkdir(parents=True, exist_ok=True)

    capture: dict[str, Any] = {"meta": machine_metadata(args.label), "sections": {}}
    if args.note:
        capture["meta"]["note"] = args.note
    started = time.perf_counter()

    if "build" in wanted:
        print("[build] scripts/build.py end to end …", file=sys.stderr, flush=True)
        capture["sections"]["build"] = run_build(
            args.scratch, args.scratch / "build.log", args.build_args.split()
        )

    blueprint = args.scratch / "csv" / "blueprint.load.json"
    if {"load", "saveload", "index"} & set(wanted):
        if not blueprint.is_file():
            raise SystemExit(
                f"no {blueprint} — run the build section first, or point --scratch "
                f"at a scratch directory that has one"
            )
        print(
            "[load/index] from_blueprint + every index, one at a time …",
            file=sys.stderr,
            flush=True,
        )
        staged = run_child(
            "build_graph", args.scratch, blueprint=blueprint, scratch=args.scratch
        )
        capture["sections"]["load"] = {
            "from_blueprint_seconds": staged["from_blueprint_seconds"],
            "peak_rss_after_load_mb": staged["rss_after_load_mb"],
            "peak_rss_whole_child_mb": staged["peak_rss_mb"],
            "nodes": staged["nodes"],
            "edges": staged["edges"],
        }
        capture["sections"]["index"] = {
            "indexes": staged["indexes"],
            "saves": staged["saves"],
        }
        capture["sections"]["saveload"] = {
            "bm25_only_bytes": staged["bm25_only"]["bytes"],
            "full_bytes": staged["full"]["bytes"],
            "vector_delta_bytes": staged["full"]["bytes"]
            - staged["bm25_only"]["bytes"],
            "saves": staged["saves"],
            "load_bm25_only": run_load_series(
                Path(staged["bm25_only"]["path"]), args.scratch, args.load_repeats
            ),
            "load_full": run_load_series(
                Path(staged["full"]["path"]), args.scratch, args.load_repeats
            ),
        }

    graph_path = args.graph
    if graph_path is None:
        built = args.scratch / "full.kgl"
        graph_path = built if built.exists() else ROOT / "graph" / "microbiomekg.kgl"

    if {"query", "control", "mcp"} & set(wanted):
        import kglite

        print(f"[query] loading {graph_path} …", file=sys.stderr, flush=True)
        t = time.perf_counter()
        graph = kglite.load(str(graph_path))
        # The served graph has an embedder — `microbiomekg/mcp/microbiomekg_mcp.yaml` names
        # this exact factory under `extensions.embedder`. Without it every
        # `text_score()` cell raises rather than being slow, so the vector lane
        # would leave the capture as two "did not run" rows and the MCP
        # comparison would be against a differently-configured graph.
        from microbiomekg.embedder import CharGramEmbedder  # noqa: PLC0415

        graph.set_embedder(CharGramEmbedder())
        capture["meta"]["query_graph"] = {
            "path": str(graph_path),
            "bytes": graph_path.stat().st_size,
            "mtime": time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(graph_path.stat().st_mtime)
            ),
            "load_seconds": time.perf_counter() - t,
            "nodes": list(graph.cypher("MATCH (n) RETURN count(n) AS n"))[0]["n"],
            "edges": list(graph.cypher("MATCH ()-[r]->() RETURN count(r) AS r"))[0][
                "r"
            ],
            # Asked of the graph rather than taken from `--label`: the capture
            # must be able to say which sources it covers even when the operator
            # mislabels it, and a source that failed to load is invisible to
            # every other line of metadata here.
            "primary_sources": sorted(
                str(row["s"])
                for row in graph.cypher(
                    "MATCH ()-[r]->() WHERE r.primary_source IS NOT NULL "
                    "RETURN DISTINCT r.primary_source AS s"
                )
            ),
        }
        if "control" in wanted:
            capture["sections"]["control"] = run_controls(graph, scale)
        if "query" in wanted:
            capture["sections"]["query"] = run_queries(graph, scale)
        if "mcp" in wanted:
            print("[mcp] booting the server …", file=sys.stderr, flush=True)
            capture["sections"]["mcp"] = run_mcp(graph_path, graph, scale)

    capture["meta"]["loadavg_end"] = loadavg()
    capture["meta"]["harness_seconds"] = time.perf_counter() - started

    RESULTS.mkdir(parents=True, exist_ok=True)
    stem = args.out or (RESULTS / f"{time.strftime('%Y-%m-%d')}-{args.label}")
    stem = Path(str(stem).removesuffix(".md").removesuffix(".json"))
    stem.with_suffix(".json").write_text(
        json.dumps(capture, indent=2), encoding="utf-8"
    )
    stem.with_suffix(".md").write_text(render(capture), encoding="utf-8")
    print(f"wrote {stem}.json and {stem}.md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

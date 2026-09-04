"""Render a capture JSON as the markdown table set ``bench/results/`` holds.

Kept apart from :mod:`bench.bench` so a capture can be re-rendered without
re-measuring: the JSON keeps every sample, and the markdown is a view of it. If
a column here is wrong, fix it and re-render — do not re-run the machine.

Every timing row carries the statistic it quotes and why, because the protocol's
statistic rule is per cell, not per table: ``min`` for a repeatable cell,
``median`` for one whose own distribution says its ``min`` is a lucky round, and
``mean`` for a once-per-event cost. A row is flagged ``rare branch`` when its
max sits at 30x its median or more — the protocol reads that as an expensive
branch to chase, not as noise.
"""

from __future__ import annotations

from typing import Any


def fmt_time(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 0:
        return "-" + fmt_time(-seconds)
    if seconds < 1e-3:
        return f"{seconds * 1e6:.1f} µs"
    if seconds < 1:
        return f"{seconds * 1e3:.2f} ms"
    if seconds < 120:
        return f"{seconds:.2f} s"
    return f"{seconds / 60:.1f} min"


def fmt_mb(byte_count: float | None) -> str:
    return "—" if byte_count is None else f"{byte_count / 1e6:,.1f} MB"


def fmt_int(value: Any) -> str:
    return "—" if value is None else f"{value:,}"


def flags(cell: dict[str, Any]) -> str:
    marks = []
    if cell.get("rare_branch"):
        marks.append(f"**rare branch** (max/median {cell['max_over_median']:.0f}x)")
    if cell.get("heavy_tailed"):
        marks.append("heavy-tailed")
    return "; ".join(marks)


def timing_table(cells: list[dict[str, Any]], *, rows_column: bool = True) -> list[str]:
    head = ["| cell | statistic | value | min | median | mean | p95 | max | n |"]
    if rows_column:
        head = [
            "| cell | rows | statistic | value | min | median | mean | p95 | max | n |"
        ]
    head.append("|" + "---|" * (10 if rows_column else 9))
    out = list(head)
    for cell in cells:
        row = [f"`{cell['name']}`"]
        if rows_column:
            row.append(fmt_int(cell.get("rows")))
        row += [
            cell["statistic"],
            f"**{fmt_time(cell['value'])}**",
            fmt_time(cell["min"]),
            fmt_time(cell["median"]),
            fmt_time(cell["mean"]),
            fmt_time(cell["p95"]),
            fmt_time(cell["max"]),
            str(cell["n"]),
        ]
        out.append("| " + " | ".join(row) + " |")
    return out


def notes_list(cells: list[dict[str, Any]]) -> list[str]:
    lines = []
    for cell in cells:
        mark = flags(cell)
        if mark:
            lines.append(f"- `{cell['name']}` — {mark}")
    return lines


def section_meta(meta: dict[str, Any]) -> list[str]:
    kglite = meta["kglite"]
    graph = meta.get("query_graph", {})
    lines = [
        "## Capture metadata",
        "",
        "| | |",
        "|---|---|",
        f"| captured | {meta['captured']} |",
        f"| source set | **{meta['source_set']}** |",
        f"| machine | {meta['machine']}, {meta['cpu']}, {meta['memory_gb']} GB |",
        f"| OS / Python | {meta['os']} / {meta['python']} |",
        f"| kglite | {kglite['version']} (`{kglite['wheel_tag']}` — released wheel) |",
        f"| repo HEAD | `{meta['git_head']}` ({meta['git_dirty_paths']} uncommitted paths) |",
        f"| load average | {meta['loadavg_start'][0]:.2f} at start, "
        f"{meta.get('loadavg_end', [float('nan')])[0]:.2f} at end (1 min) |",
        f"| harness wall time | {fmt_time(meta.get('harness_seconds'))} |",
    ]
    if graph:
        lines += [
            f"| graph timed | `{graph['path']}` ({fmt_mb(graph['bytes'])}, "
            f"written {graph['mtime']}) |",
            f"| graph size | {fmt_int(graph['nodes'])} nodes, "
            f"{fmt_int(graph['edges'])} edges |",
            f"| edge sources in that graph | "
            f"{', '.join(graph.get('primary_sources', ())) or '—'} |",
        ]
    lines += [
        "",
        "Taken under whatever load the machine had (protocol item 9); the load "
        "average above is that record. Every timing below is from the released "
        "PyPI wheel — no debug extension was built for any number here.",
        "",
    ]
    if meta.get("note"):
        lines += ["> " + line for line in meta["note"].split("\n")] + [""]
    return lines


def section_build(build: dict[str, Any]) -> list[str]:
    lines = [
        "## 1. Build — `scripts/build.py` end to end",
        "",
        f"Wall time **{fmt_time(build['wall_seconds'])}** "
        f"(exit {build['returncode']}), writing "
        f"{fmt_int(build['tables']['total_rows'])} table rows across "
        f"{build['tables']['files']} tables and a "
        f"{fmt_mb(build['graph_bytes'])} `.kgl`.",
        "",
        f"Sources the build itself reports loading: **{build.get('sources_loaded') or '—'}**.",
        "",
        "Statistic: **single run**. A build is a once-per-event cost that reads "
        "7.5 GB of raw input; it is reported as the one wall time it took, not "
        "as a distribution, and the segment times below are that same run "
        "carved at the phase markers `scripts/build.py` flushes.",
        "",
        "| segment | seconds | share | peak RSS (tree) | peak RSS (build proc) |",
        "|---|---|---|---|---|",
    ]
    total = build["wall_seconds"]
    tree = build.get("peak_rss_by_segment_mb", {})
    root = build.get("peak_rss_root_by_segment_mb", {})
    for segment in build["segments"]:
        name = segment["segment"]
        lines.append(
            f"| `{name}` | {segment['seconds']:.1f} | "
            f"{100 * segment['seconds'] / total:.1f}% | "
            f"{f'{tree[name]:,.0f} MB' if name in tree else '—'} | "
            f"{f'{root[name]:,.0f} MB' if name in root else '—'} |"
        )
    lines += [
        "",
        f"Peak RSS: **{build['peak_rss_root_mb']:,.0f} MB** for the build process "
        f"itself (the one that loads the graph and builds the indexes), "
        f"**{build['peak_rss_tree_mb']:,.0f} MB** for the whole process tree at "
        f"its widest moment. Sampled from `ps` every 200 ms — the prep scripts "
        f"are child processes, and `getrusage(RUSAGE_CHILDREN)` cannot tell them "
        f"apart from the parent — it is read anyway as the cross-check "
        f"({build.get('getrusage_children_peak_mb', 0):,.0f} MB from "
        f"`getrusage(RUSAGE_CHILDREN)`); a large disagreement would mean the "
        f"sampler missed a spike between two ticks.",
        "",
        "`scripts/build.py` prints its `saved …` line **after** `graph.save()` "
        "returns, so the save's own time sits inside the `report` segment above "
        "it and the `save` row is only the tail between that line and process "
        "exit. Section 3 measures `save()` directly and is the number to quote.",
        "",
        "### CSV rows written (top 15 tables)",
        "",
        "| table | rows |",
        "|---|---|",
    ]
    top = sorted(build["tables"]["per_file"].items(), key=lambda kv: -kv[1])[:15]
    for name, rows in top:
        lines.append(f"| `{name}` | {rows:,} |")
    lines.append("")
    return lines


def section_load(load: dict[str, Any]) -> list[str]:
    return [
        "## 2. Load from blueprint — `from_blueprint` alone",
        "",
        "| | |",
        "|---|---|",
        f"| `from_blueprint` | **{fmt_time(load['from_blueprint_seconds'])}** |",
        f"| nodes / edges | {fmt_int(load['nodes'])} / {fmt_int(load['edges'])} |",
        f"| peak RSS after the load | {load['peak_rss_after_load_mb']:,.0f} MB |",
        f"| peak RSS of the whole child (load + all indexes + saves) | "
        f"{load['peak_rss_whole_child_mb']:,.0f} MB |",
        "",
        "Statistic: **single run**, in a fresh child process that does nothing "
        "else first — this is the load separated from the prep, which is the "
        "separation section 1's segment table cannot make (the build process "
        "has already read and written 228 MB of CSV by the time it loads).",
        "",
    ]


def section_index(index: dict[str, Any]) -> list[str]:
    lines = [
        "## 4. Index build — each index alone, with the bytes it adds",
        "",
        "| index | lane | build time | documents | terms / dim | `.kgl` after | "
        "size it added |",
        "|---|---|---|---|---|---|---|",
    ]
    for entry in index["indexes"]:
        detail = (
            f"{entry['terms']:,} terms"
            if entry["lane"] == "bm25"
            else f"dim {entry['dimension']}, ef_search {entry['ef_search']}"
        )
        lines.append(
            f"| `{entry['index']}` | {entry['lane']} | "
            f"{fmt_time(entry['seconds'])} | {fmt_int(entry['documents'])} | "
            f"{detail} | {fmt_mb(entry['kgl_bytes'])} | "
            f"**{entry['delta_bytes'] / 1e6:+,.1f} MB** |"
        )
    vectors = [e for e in index["indexes"] if e["lane"] == "vector"]
    if vectors:
        lines += [
            "",
            "The vector lane's time splits two ways:",
            "",
            "| index | embed | HNSW build | vectors indexed |",
            "|---|---|---|---|",
        ]
        for entry in vectors:
            lines.append(
                f"| `{entry['index']}` | {fmt_time(entry['embed_seconds'])} | "
                f"{fmt_time(entry['hnsw_seconds'])} | {fmt_int(entry['indexed'])} |"
            )
    lines += [
        "",
        "Statistic: **single run each**. Every row is one index built once on a "
        "graph that already carries the rows above it, then saved to its own "
        "file — so the size column is the difference between two real files "
        "rather than an estimate. The deltas are therefore **cumulative and "
        "order-dependent** (`save()` consolidates the whole graph on the way "
        "out); the order is `scripts/build.py`'s. A delta under ~0.1 MB is at "
        "the level of save-to-save compression variance and can come out "
        'negative — read those rows as "this index costs nothing on disk", '
        "not as a saving.",
        "",
    ]
    return lines


def _load_rows(entry: dict[str, Any], label: str) -> list[str]:
    warm = entry.get("warm_cell")
    return [
        f"| {label} | {fmt_mb(entry['bytes'])} | "
        f"{fmt_time(entry['first_touch_after_write_s'])} | "
        f"{fmt_time(warm['value']) if warm else '—'} | "
        f"{entry['first_touch_peak_rss_mb']:,.0f} MB |"
    ]


def section_saveload(save: dict[str, Any]) -> list[str]:
    saves = {entry["tag"]: entry for entry in save["saves"]}
    bm25, full = saves.get("bm25-only", {}), saves.get("full", {})
    lines = [
        "## 3. Save / load round trip",
        "",
        "| variant | `.kgl` | `save()` | ",
        "|---|---|---|",
        f"| BM25 lane only | {fmt_mb(save['bm25_only_bytes'])} | "
        f"{fmt_time(bm25.get('seconds'))} |",
        f"| BM25 + vector lane | {fmt_mb(save['full_bytes'])} | "
        f"{fmt_time(full.get('seconds'))} |",
        f"| **the vector lane's delta** | "
        f"**{save['vector_delta_bytes'] / 1e6:+,.1f} MB** | "
        f"**{(full.get('seconds', 0) - bm25.get('seconds', 0)):+.2f} s** |",
        "",
        "| load | `.kgl` | first touch after the write | warm repeats | peak RSS |",
        "|---|---|---|---|---|",
    ]
    lines += _load_rows(save["load_bm25_only"], "BM25 lane only")
    lines += _load_rows(save["load_full"], "BM25 + vector lane")
    delta_first = (
        save["load_full"]["first_touch_after_write_s"]
        - save["load_bm25_only"]["first_touch_after_write_s"]
    )
    warm_full = save["load_full"].get("warm_cell")
    warm_bm25 = save["load_bm25_only"].get("warm_cell")
    delta_warm = (
        (warm_full["value"] - warm_bm25["value"]) if warm_full and warm_bm25 else None
    )
    lines += [
        f"| **the vector lane's delta** | "
        f"**{save['vector_delta_bytes'] / 1e6:+,.1f} MB** | "
        f"**{delta_first:+.2f} s** | "
        f"**{f'{delta_warm:+.2f} s' if delta_warm is not None else '—'}** | |",
        "",
        "Statistic: **mean of fresh processes** for the warm column (a "
        "once-per-event cost — one load per process, so no sample is warmed by "
        "the one before it except through the page cache), **single run** for "
        "the first-touch column and for every `save()`.",
        "",
        "**Neither load column is a cold-cache number, and no number here is.** "
        "Dropping the macOS unified buffer cache needs `sudo purge`; this "
        "harness has no sudo and does not ask for it. What the two columns "
        "actually separate is *pages in cache because the save just wrote them* "
        "from *pages in cache because an earlier load just read them* — a real "
        "difference, but not the cold/warm one. A genuine cold load on this "
        "machine is **not measured**, and is not estimated here either.",
        "",
    ]
    return lines


def near_floor(cells: list[dict[str, Any]], floor: float | None) -> list[str]:
    """Query cells sitting within 3x the dispatch floor.

    Protocol item 8 requires a *control* to clear 2x the noise floor because
    below that it measures nothing. The same arithmetic applies to a query
    cell: at 1.8 us against a 1.0 us floor, a point lookup's number is mostly
    the cost of asking, and quoting it as "the lookup takes 1.8 us" would be a
    claim the instrument cannot support.
    """
    if not floor:
        return []
    close = [c for c in cells if c["value"] < 3 * floor]
    if not close:
        return []
    return [
        "",
        "**At the dispatch floor** — these cells are within 3x the "
        f"{fmt_time(floor)} noise floor, so most of what they report is the "
        "cost of issuing a query, not of answering it:",
        "",
    ] + [
        f"- `{c['name']}` — {fmt_time(c['value'])}, {c['value'] / floor:.1f}x the floor"
        for c in close
    ]


def section_query(query: dict[str, Any], floor: float | None = None) -> list[str]:
    lines = [
        "## 5. Query — every `answerable-now` / `partial` Part D acceptance query",
        "",
        "Extracted from `docs/usecases-and-pitfalls.md` Part D at run time and "
        "run as authored — these are the contract's own queries, not synthetic "
        "ones. A section with several statements contributes one cell each, "
        "numbered in document order: `D15.1` is the audit call, `D15.2` the "
        "per-field census it rolls up.",
        "",
    ]
    lines += timing_table(query["cells"])
    lines += near_floor(query["cells"], floor)
    marks = notes_list(query["cells"])
    if marks:
        lines += ["", "**Distribution flags:**", ""] + marks
    if query["did_not_run"]:
        lines += ["", "**Did not run** (reported rather than dropped):", ""]
        for entry in query["did_not_run"]:
            lines.append(f"- `{entry['name']}` — {entry['error']}")
    lines.append("")
    return lines


def section_control(control: dict[str, Any]) -> list[str]:
    floor = control["floor"]
    lines = [
        "## 6. Control cells — the machine-drift meter",
        "",
        f"Noise floor (`RETURN 1`, dispatch + materialisation with no graph work "
        f"behind it): **{fmt_time(floor['median'])}** median, "
        f"{fmt_time(floor['min'])} min. Protocol item 8 requires each control's "
        f"median at **2x that or more**; the ratio is in the last column.",
        "",
        "| control | statistic | value | median | max/median | x floor | ≥2x floor |",
        "|---|---|---|---|---|---|---|",
    ]
    for cell in control["cells"]:
        over = cell.get("over_floor")
        lines.append(
            f"| `{cell['name']}` | {cell['statistic']} | "
            f"**{fmt_time(cell['value'])}** | {fmt_time(cell['median'])} | "
            f"{cell['max_over_median']:.1f}x | "
            f"{f'{over:,.0f}x' if over else '—'} | "
            f"{'yes' if cell['passes_2x_floor'] else '**NO**'} |"
        )
    lines += [
        "",
        f"Control contract: **{'holds' if control['contract_holds'] else 'BROKEN'}**.",
        "",
    ]
    return lines


def section_mcp(mcp: dict[str, Any]) -> list[str]:
    if mcp.get("skipped"):
        return ["## 7. MCP overhead", "", f"Skipped: {mcp['skipped']}", ""]
    lines = [
        "## 7. MCP overhead — the same query over stdio vs in-process",
        "",
        f"Server boot + `initialize` handshake: "
        f"**{fmt_time(mcp['boot_and_handshake_s'])}**, paid once per agent "
        f"session. It includes loading the `.kgl`, so it is roughly section 3's "
        f"warm load plus the process start.",
        "",
        "| query | over MCP | in-process | overhead | ratio | statistic |",
        "|---|---|---|---|---|---|",
    ]
    for row in mcp["cells"]:
        # A 24 us surface cost is not resolvable inside a 374 ms query: the
        # difference of two cells is only a measurement when it clears the
        # spread of the noisier one. Say so rather than printing a number
        # (a negative one, on a bad round) the reader would take literally.
        spread = row["mcp"]["p95"] - row["mcp"]["min"]
        overhead = (
            fmt_time(row["overhead_s"])
            if abs(row["overhead_s"]) > spread
            else f"below this cell's own spread (±{fmt_time(spread)})"
        )
        lines.append(
            f"| `{row['cell']}` | **{fmt_time(row['mcp']['value'])}** | "
            f"{fmt_time(row['direct']['value'])} | "
            f"{overhead} | "
            f"{row['ratio']:.2f}x | "
            f"{row['mcp']['statistic']} / {row['direct']['statistic']} |"
        )
    lines += [
        "",
        "`mcp_floor` is `RETURN 1` on both sides: its overhead column **is** the "
        "agent surface's fixed cost — JSON-RPC encode, a pipe round trip, the "
        "server's result rendering — with no graph work behind it. The other two "
        "rows are that plus the query. Note the MCP side also *renders* its "
        "answer as text and inlines at most 15 rows, so the two sides return "
        "different amounts of material for the same engine work; that rendering "
        "is part of what the surface costs and is deliberately not subtracted.",
        "",
    ]
    return lines


RENDERERS = {
    "build": section_build,
    "load": section_load,
    "saveload": section_saveload,
    "index": section_index,
    "query": section_query,
    "control": section_control,
    "mcp": section_mcp,
}
ORDER = ("build", "load", "saveload", "index", "query", "control", "mcp")


def render_markdown(capture: dict[str, Any]) -> str:
    meta = capture["meta"]
    lines = [
        f"# MicrobiomeKG performance capture — {meta['captured'][:10]} "
        f"({meta['source_set']})",
        "",
        "Produced by `bench/bench.py`; see `bench/README.md` for what each cell "
        "means and how to reproduce it. Every sample of every cell is in the "
        "`.json` beside this file.",
        "",
    ]
    lines += section_meta(meta)
    floor = capture["sections"].get("control", {}).get("floor", {}).get("median")
    for name in ORDER:
        if name not in capture["sections"]:
            continue
        section = capture["sections"][name]
        lines += (
            RENDERERS[name](section, floor)
            if name == "query"
            else RENDERERS[name](section)
        )
    return "\n".join(lines).rstrip() + "\n"

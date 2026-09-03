"""The manifest is a configuration file with no compiler — so the server checks it.

``kglite-mcp-server`` fails *silently* when it is misconfigured: an unresolved
path drops a tool group, a missing graph serves an empty database, a
PATH-shadowing binary answers with a different feature set. The absence of an
error at boot is therefore not evidence of anything, which is why
``--selftest`` exists: it re-spawns the server with the same flags, drives a
real handshake, and exits non-zero on any failure.

That is the gate here. The assertions below the selftest are the claims the
selftest does not make — that the server is read-only, that the three text
channels carry the text this project put in them.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from tests.mcp_support import (
    GRAPH,
    MANIFEST,
    MCPClient,
    ROOT,
    SKILLS_DIR,
    server_binary,
)

BINARY = server_binary()

#: Every skill this repo ships, by its filename stem.
SKILL_NAMES = sorted(p.stem for p in SKILLS_DIR.glob("*.md"))

pytestmark = pytest.mark.skipif(
    BINARY is None,
    reason="kglite-mcp-server is not installed; it ships in the kglite wheel "
    "(`uv pip install --python .venv/bin/python kglite`)",
)


def _skip_without_graph() -> None:
    if not GRAPH.exists():
        pytest.skip(
            f"no graph at {GRAPH} — build it with "
            f"`.venv/bin/python scripts/build.py --scope microbial`"
        )


def test_manifest_exists_and_names_the_skills_pack():
    assert MANIFEST.is_file(), f"no manifest at {MANIFEST}"
    text = MANIFEST.read_text(encoding="utf-8")
    # The pack directory is named for the graph, not for this file, so the
    # auto-detected `<basename>_mcp.skills/` layer does not find it. The list
    # form of `skills:` is what loads it, and dropping that line would silently
    # remove every skill in this repo from the tool descriptions.
    assert "./microbiomekg.skills" in text
    # Read-only is a property of what is *absent*: no `extensions.writable`,
    # and scripts/serve.py passes no `--writable`. Comment lines are dropped
    # first — the manifest *explains* the absence, and grepping the prose would
    # make this assertion fail on the sentence that documents it.
    declarations = [
        line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")
    ]
    assert not any("writable" in line for line in declarations), declarations


def test_selftest_passes_against_the_manifest():
    """The one check that can go red for a whole class of misconfiguration."""
    _skip_without_graph()
    completed = subprocess.run(
        [sys.executable, "scripts/serve.py", "--selftest"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, f"selftest failed:\n{output}"
    assert "Selftest PASSED" in output, output
    # Non-vacuity: a selftest that reported PASSED without registering the
    # graph tools, or against an empty graph, would satisfy the two lines
    # above. These are the capabilities it must have found.
    assert "✓ graph tools registered" in output, output
    assert "✓ graph hydrates" in output, output
    # 931,992 before the two drug screens landed. Maier mints 355 `Drug` nodes
    # for the library entries no ChEMBL join route reaches; Zimmermann mints 23
    # more and two `UnresolvedTaxon` tombstones for the strain names NCBI holds
    # two candidates for. 932,372 until MiMeDB v2.0 replaced v1.0 as the loaded
    # release and its wider `observed` rule kept 302 more compounds — nodes
    # only; the edge count did not move, because no MiMeDB release carries an
    # association to write an edge from. MASI then added 1,350 `Substance`
    # nodes, 122 `UnresolvedTaxon` tombstones, 18 `Disease` nodes, 42 `Paper`
    # nodes and 22 taxa nothing else cited.
    assert "934206 node(s)" in output, output
    # And the skills, which the selftest could not see until kglite 0.16.22:
    # a `skills:` path that did not exist booted cleanly with *every* skill
    # gone, the bundled methodology included, while the graph tools answered
    # normally and this line still printed PASSED (docs/model.md §8 item 12).
    # It now names the count, and this repo's seven must all be in it.
    served = next(
        (line for line in output.splitlines() if "skills:" in line and "served" in line),
        None,
    )
    assert served, f"the selftest no longer reports a skill count:\n{output}"
    for skill in SKILL_NAMES:
        assert skill in served, f"{skill} is not among the skills served: {served}"


def test_a_skills_path_that_does_not_exist_fails_the_boot(tmp_path):
    """The failure §8 item 12 recorded, now loud — asserted rather than hoped.

    One bad path used to cost an agent every skill in the session with no
    diagnostic anywhere: the server booted, the graph tools worked, and
    `--selftest` printed PASSED. It is a boot error now, and this is the check
    that would notice if it went quiet again.
    """
    _skip_without_graph()
    manifest = tmp_path / "microbiomekg_mcp.yaml"
    manifest.write_text(
        MANIFEST.read_text().replace("./microbiomekg.skills", "./not-a-pack.skills"),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, "scripts/serve.py", "--selftest",
         "--mcp-config", str(manifest)],
        cwd=ROOT, capture_output=True, text=True, timeout=90,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode != 0, f"a missing skills pack booted cleanly:\n{output}"
    assert "not-a-pack.skills" in output, output


def test_server_is_read_only():
    """A mutation must be refused, and the refusal must name the switch.

    Not a hypothetical: the goldens in ``tests/test_acceptance.py`` are
    measurements of this graph's edges, and an agent able to write would
    invalidate them without leaving a trace in any file this repo tracks.
    """
    _skip_without_graph()
    with MCPClient([BINARY, "--graph", str(GRAPH), "--mcp-config", str(MANIFEST)]) as client:
        with pytest.raises(RuntimeError) as excinfo:
            client.call("cypher_query", {"query": "CREATE (n:Taxon {id: -1, scientific_name: 'x'})"})
        assert "writable" in str(excinfo.value).lower(), excinfo.value
        # And the graph is untouched: the refusal is a refusal, not a rollback.
        assert "864132" in client.call(
            "cypher_query", {"query": "MATCH (t:Taxon) RETURN count(t) AS c"}
        )


def test_initialize_instructions_carry_the_evidence_rules():
    """`instructions:` is the init channel — seen once, so it holds only the
    three rules that orient a session, not methodology (that is a skill)."""
    _skip_without_graph()
    with MCPClient([BINARY, "--graph", str(GRAPH), "--mcp-config", str(MANIFEST)]) as client:
        assert client.server_info.get("name") == "MicrobiomeKG"
        instructions = client.instructions
        assert "evidence_level" in instructions
        assert "ontology_audit" in instructions
        for phrase in ("Never aggregate direction", "single cohort"):
            assert phrase.lower() in instructions.lower(), instructions


def test_overview_prefix_rides_the_bare_graph_overview():
    """`overview_prefix:` re-surfaces with the schema on every bare
    graph_overview(), which is the whole reason the evidence-field reminder and
    the UnresolvedTaxon warning live there rather than in `instructions`."""
    _skip_without_graph()
    with MCPClient([BINARY, "--graph", str(GRAPH), "--mcp-config", str(MANIFEST)]) as client:
        overview = client.call("graph_overview", {})
        for phrase in ("evidence_level", "knowledge_level", "primary_source",
                       "publications", "UnresolvedTaxon", "Ledger", "placeholder"):
            assert phrase.lower() in overview.lower(), f"{phrase!r} missing from graph_overview()"

"""The skills pack: frontmatter, gating, tool references, and every Cypher block.

A skill is prose the server injects into a tool description, so nothing about
it is compiled and every failure mode is silent — a mistyped `references_tools`
attaches the skill to no tool, an `applies_when` naming a node type this graph
lacks makes it permanently invisible, and a Cypher block with a stale property
name teaches an agent a query that errors.

Three independent checks, because no one of them can see the others' failures:

1. **The server parsed it.** `tools/list` must carry each skill's marker on
   exactly the tools it names. This is the authoritative frontmatter check: the
   file's own parse (``tests.mcp_support.read_frontmatter``) is a convenience
   for the assertions below, but mcp-methods is what actually decides.
2. **The gate is satisfiable.** Every node type in `applies_when` exists here.
3. **The Cypher runs.** Every fenced block executes against the real graph with
   this module's parameter table.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.mcp_support import (
    GRAPH,
    MANIFEST,
    SKILL_BODY_HARD_CAP,
    SKILLS_DIR,
    MCPClient,
    cypher_blocks,
    read_frontmatter,
    server_binary,
)

kglite = pytest.importorskip("kglite")

SKILL_FILES = sorted(SKILLS_DIR.glob("*.md"))

#: One skill per Part D use-case *family*, not per query. A skill added or
#: removed without a decision shows up here rather than in a diff nobody reads.
EXPECTED_SKILLS = {
    "amr",
    "drugs",
    "evidence_audit",
    "metabolites_pathways",
    "reconciliation",
    "signature_enrichment",
    "taxon_disease_evidence",
}

#: Parameters for the fenced Cypher. Base values are the ones Part D's golden
#: checks use; a skill whose queries need a different subject overrides them, so
#: each block runs against data that actually exists rather than merely parsing.
BASE_PARAMS = {
    "taxon_id": 851,                      # Fusobacterium nucleatum
    "taxon_ids": [821, 851, 1263, 40520, 239935, 33038],
    "disease_id": "MONDO:0005575",        # colorectal cancer
    "drug_id": "CHEMBL:CHEMBL1431",       # metformin
    "drug_class": "fluoroquinolone antibiotic",
    "metabolite_id": "CHEBI:30772",       # butyric acid — the acid, not the base
    "name": "Clostridium dificile",
    "epithet": "dificile",
    "rank": "species",
}
PARAM_OVERRIDES = {
    "amr": {"taxon_id": 562},                       # E. coli carries determinants
    "metabolites_pathways": {"taxon_id": 1496, "name": "butyric acid"},
    "drugs": {"disease_id": "MONDO:0005148"},       # T2D — where metformin lands
    "reconciliation": {"taxon_id": 1598},           # Limosilactobacillus reuteri
}


def params_for(skill: str) -> dict:
    return {**BASE_PARAMS, **PARAM_OVERRIDES.get(skill, {})}


@pytest.fixture(scope="session")
def graph():
    if not GRAPH.exists():
        pytest.skip(
            f"no graph at {GRAPH} — build it with "
            f"`.venv/bin/python scripts/build.py --scope microbial`"
        )
    loaded = kglite.load(str(GRAPH))
    from microbiomekg.embedder import CharGramEmbedder

    # text_score() needs an embedder to turn a query string into a vector; the
    # server gets one from the manifest, and this fixture is that half of the
    # contract. Without it the reconciliation blocks would raise here while
    # working perfectly on the real server.
    loaded.set_embedder(CharGramEmbedder())
    return loaded


@pytest.fixture(scope="session")
def injected_tools():
    """`tools/list` from a live server — the only place skill activation is real."""
    binary = server_binary()
    if binary is None:
        pytest.skip("kglite-mcp-server is not installed (it ships in the kglite wheel)")
    if not GRAPH.exists():
        pytest.skip(f"no graph at {GRAPH}")
    with MCPClient([binary, "--graph", str(GRAPH), "--mcp-config", str(MANIFEST)]) as client:
        return client.tools()


def test_the_pack_is_the_expected_set_of_families():
    assert {path.stem for path in SKILL_FILES} == EXPECTED_SKILLS


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.stem)
def test_frontmatter_parses_and_carries_the_load_bearing_keys(path: Path):
    frontmatter, body = read_frontmatter(path)
    assert frontmatter["name"] == path.stem, "the skill name must match its filename"
    # `description` is the routing heuristic and is never truncated, so it is
    # the highest-value half; a skill without one injects methodology an agent
    # has no reason to read.
    assert frontmatter.get("description"), "no description (the routing heuristic)"
    assert "TRIGGER" in frontmatter["description"] and "SKIP" in frontmatter["description"]
    assert isinstance(frontmatter.get("references_tools"), list)
    assert frontmatter["references_tools"], "references_tools is load-bearing, not decorative"
    assert isinstance(frontmatter.get("applies_when"), dict)
    assert frontmatter["applies_when"].get("graph_has_node_type")
    assert len(body.encode("utf-8")) <= SKILL_BODY_HARD_CAP, (
        f"body is {len(body.encode('utf-8'))} bytes, over mcp-methods' 16 KB hard cap — "
        f"past it the body is truncated with a marker and the tail never reaches an agent"
    )


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.stem)
def test_applies_when_names_node_types_this_graph_has(path: Path, graph):
    """A gate naming a type the graph lacks makes the skill permanently silent."""
    frontmatter, _ = read_frontmatter(path)
    declared = set(frontmatter["applies_when"]["graph_has_node_type"])
    assert declared <= set(graph.node_types), (
        f"{path.name} gates on {sorted(declared - set(graph.node_types))}, "
        f"which this graph does not have — the skill would never activate"
    )


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.stem)
def test_references_only_tools_the_server_exposes(path: Path, injected_tools):
    frontmatter, _ = read_frontmatter(path)
    unknown = set(frontmatter["references_tools"]) - set(injected_tools)
    assert not unknown, (
        f"{path.name} references {sorted(unknown)}; this server exposes "
        f"{sorted(injected_tools)}. A skill referencing a tool that is not "
        f"registered attaches to nothing and is never read."
    )


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.stem)
def test_the_server_injects_the_skill_into_exactly_the_tools_it_names(path: Path, injected_tools):
    """The authoritative frontmatter check: injection only happens on a parse."""
    frontmatter, _ = read_frontmatter(path)
    marker = f"<!-- mcp-skill:{frontmatter['name']} -->"
    named = set(frontmatter["references_tools"]) | {frontmatter["name"]}
    for tool_name, tool in injected_tools.items():
        present = marker in tool.get("description", "")
        if tool_name in named:
            assert present, f"{frontmatter['name']} is not injected into {tool_name}"
        else:
            assert not present, f"{frontmatter['name']} leaked into {tool_name}"


def has_vector_lane(graph) -> bool:
    """Whether this build carries the embedding store the misspelling lane needs.

    The same gate ``tests/test_semantic_lookup.py`` uses. ``scripts/build.py``
    writes it only under ``--with-vectors``, and on a graph without one
    ``text_score()`` **raises** rather than scoring zero — so a block that calls
    it is untestable here, not failing.
    """
    return graph.embedding_dim("Taxon", "scientific_name") is not None


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.stem)
def test_every_cypher_block_executes(path: Path, graph):
    frontmatter, body = read_frontmatter(path)
    blocks = cypher_blocks(body)
    assert blocks, f"{path.name} teaches a query skill with no Cypher in it"
    params = params_for(frontmatter["name"])
    produced_rows = False
    for index, query in enumerate(blocks):
        if "text_score(" in query and not has_vector_lane(graph):
            continue  # the vector lane is opt-in; the test below covers its absence
        try:
            rows = list(graph.cypher(query, params=params))
        except Exception as exc:  # noqa: BLE001 - the message is the whole point
            pytest.fail(f"{path.name} block {index + 1} failed: {exc}\n\n{query}")
        produced_rows = produced_rows or bool(rows)
    # Non-vacuity: a block can parse, run and match nothing because a property
    # was renamed. At least one block per skill must reach real data.
    assert produced_rows, f"{path.name}: no block returned a single row"


def test_the_vector_lane_is_either_present_or_the_documented_fallback_works(graph):
    """A default build has no vector lane, and the skill must survive that.

    Three things have to hold together, or an agent following `reconciliation`
    on a default graph gets a tool error instead of an answer: the probe the
    skill teaches has to agree with the build, the queries it forbids have to be
    the ones that actually fail, and the fallback it names has to return rows.
    """
    present = has_vector_lane(graph)
    rows = list(graph.cypher("CALL db.indexes()"))
    assert any(row["type"] == "FULLTEXT" for row in rows), "no BM25 index at all"
    assert any(row["type"] == "VECTOR" for row in rows) == present, (
        "`CALL db.indexes()` is the only probe the skill can offer an agent, and "
        "it disagrees with `embedding_dim` about whether this build has vectors"
    )
    if present:
        return

    _, body = read_frontmatter(SKILLS_DIR / "reconciliation.md")
    blocks = cypher_blocks(body)
    params = {**params_for("reconciliation"), "epithet": "wh2"}
    vector = [q for q in blocks if "text_score(" in q]
    assert vector, "reconciliation no longer teaches the vector lane"
    for query in vector:
        with pytest.raises(Exception):
            list(graph.cypher(query, params=params))

    lexical = [q for q in blocks if "text_bm25(" in q and "text_score(" not in q]
    tombstone = [q for q in blocks if "UnresolvedTaxon" in q]
    assert lexical and tombstone, (
        "the skill promises a fallback of the lexical lane plus the tombstone "
        "query when there is no vector store; one of them is no longer there"
    )
    for query in lexical + tombstone:
        assert list(graph.cypher(query, params=params)), (
            f"the documented fallback returns nothing on a vectorless graph, so "
            f"the degradation path the skill promises does not exist:\n{query}"
        )


#: `text_bm25(n, 'p', …)` where `n.p` has no BM25 index raises. Through kglite
#: 0.16.21 one query shape did not: a `WHERE text_bm25(...) > 0` filter
#: *combined with* an ORDER BY returned **zero rows and no error**, and that
#: shape is the documented fast path, so it was exactly the one a skill is
#: likely to teach. 0.16.22 fixed it (docs/model.md §8 item 8) and this check
#: still does not rely on the engine complaining: asking `has_text_index()`
#: names the missing index instead of waiting for a query to fail on it, which
#: holds whatever a later release does with the error.
BM25_CALL = re.compile(r"text_bm25\(\s*(\w+)\s*,\s*'([^']+)'")
NODE_BINDING = re.compile(r"\((\w+)\s*:\s*(\w+)")


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.stem)
def test_no_block_ranks_on_a_property_with_no_bm25_index(path: Path, graph):
    _, body = read_frontmatter(path)
    for index, query in enumerate(cypher_blocks(body)):
        bindings = dict(
            (variable, node_type) for variable, node_type in NODE_BINDING.findall(query)
        )
        for variable, prop in BM25_CALL.findall(query):
            node_type = bindings.get(variable)
            assert node_type, f"{path.name} block {index + 1}: unbound variable {variable!r}"
            assert graph.has_text_index(node_type, prop), (
                f"{path.name} block {index + 1} calls text_bm25 on "
                f"{node_type}.{prop}, which has no BM25 index — the query returns "
                f"nothing, silently. Index it in scripts/build.py TEXT_INDEXES or "
                f"use CONTAINS."
            )

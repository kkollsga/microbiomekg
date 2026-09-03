"""The acceptance queries, driven through the MCP protocol rather than the API.

``tests/test_acceptance.py`` asserts Part D's goldens against a graph built
in-process from ``data/csv/``. That leaves a whole layer untested: the agent
never touches that API. It sends JSON-RPC over stdio to ``kglite-mcp-server``,
which loads the *saved* ``graph/microbiomekg.kgl``, applies the manifest, and
returns text. Every step of that is somewhere a golden can quietly stop being
true — a rebuild that dropped a source, a manifest that opened writes, a
serialisation that lost the parallel edges.

So this module asserts the *same* numbers as ``test_acceptance.py`` over the
*other* path. Two independent routes to one claim is the point; a single one
cannot detect its own instrument.

The 120 s per-test ceiling in ``pyproject.toml`` applies here as everywhere: a
server handshake that hangs is a FAILED test, never a raised timeout.
"""

from __future__ import annotations

import re

import pytest

from tests.mcp_support import GRAPH, MANIFEST, MCPClient, server_binary

BINARY = server_binary()

pytestmark = pytest.mark.skipif(
    BINARY is None,
    reason="kglite-mcp-server is not installed; it ships in the kglite wheel "
    "(`uv pip install --python .venv/bin/python kglite`)",
)

#: Quoted from ``tests/test_acceptance.py``'s GOLDEN, deliberately by value
#: rather than by import: if the two ever disagree, that is the finding. Both
#: are measurements of the 2026-09-03 six-source build.
D2_EDGES = 40
D2_STUDIES = 21
D2_INCREASED = 39
D2_DISSENTING_RECORD = "bsdb:41270896/1/2"
D15_RULE = "ASSOCIATED_WITH.required_properties"
D15_VIOLATIONS = 15985
D15_TOTAL = 105097

#: Every skill this repo ships. All seven must reach `cypher_query`, which is
#: the tool every one of them names.
PACK = (
    "amr",
    "drugs",
    "evidence_audit",
    "metabolites_pathways",
    "reconciliation",
    "signature_enrichment",
    "taxon_disease_evidence",
)


@pytest.fixture(scope="module")
def client():
    if not GRAPH.exists():
        pytest.skip(
            f"no graph at {GRAPH} — build it with "
            f"`.venv/bin/python scripts/build.py --scope microbial`"
        )
    with MCPClient([BINARY, "--graph", str(GRAPH), "--mcp-config", str(MANIFEST)]) as connected:
        yield connected


def cell(text: str, column: str) -> str:
    """One value out of `cypher_query`'s CSV-ish inline table.

    The tool answers with `N row(s):`, a **tab**-separated header line, then the
    rows, then an active-graph footer. Parsing it is the price of asserting
    through the protocol instead of around it — and the separator is checked
    rather than assumed, because a silently different one would turn every
    assertion below into a KeyError instead of a wrong number.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    start = next(i for i, line in enumerate(lines) if re.match(r"^\d+ row\(s\):", line))
    header = [name.strip() for name in lines[start + 1].split("\t")]
    row = [value.strip() for value in lines[start + 2].split("\t")]
    assert column in header, f"no {column!r} column in {header!r}; full answer:\n{text}"
    value = dict(zip(header, row))[column]
    # String cells arrive quoted; numeric ones do not. Strip so a caller
    # compares against the value, not against the tool's rendering of it.
    return value[1:-1] if len(value) >= 2 and value[0] == value[-1] == '"' else value


def test_tools_list_carries_every_skill_on_cypher_query(client):
    tools = client.tools()
    description = tools["cypher_query"]["description"]
    for skill in PACK:
        assert f"<!-- mcp-skill:{skill} -->" in description, (
            f"{skill} is not injected into cypher_query — an agent inspecting tools "
            f"never sees its methodology"
        )
    # The routing half must arrive too: `description` is what an agent reads to
    # decide *which* skill applies, and it is never truncated.
    assert "## When to use" in description
    assert "## Methodology" in description


def test_gating_keeps_the_code_graph_skills_off_this_graph(client):
    """`applies_when` is the reason a skill pack is not just a prompt.

    kglite bundles code-graph skills gated on `graph_has_node_type: [Function,
    Class]`. This graph has neither, so they must be silent — if they are not,
    gating is not running and *our* gates are decorative too.
    """
    description = client.tools()["cypher_query"]["description"]
    for bundled in ("code_graph_analysis", "code_graph_views", "read_code_source"):
        assert f"<!-- mcp-skill:{bundled} -->" not in description, (
            f"{bundled} is active on a graph with no Function/Class nodes"
        )
    # And the gate is not simply refusing everything: our own skills are gated
    # on node types this graph *does* have, and they got through.
    assert "<!-- mcp-skill:amr -->" in description


def test_d2_through_the_protocol(client):
    """D2 — one row per signature, never one aggregated row.

    Asserted as counts rather than as 40 returned rows because `cypher_query`
    inlines at most 15; the count is the golden either way, and one row instead
    of forty is the parallel-edge collapse this project exists to notice.
    """
    answer = client.call(
        "cypher_query",
        {
            "query": """
                MATCH (t:Taxon {id: 851})-[r:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0005575'})
                RETURN count(r) AS edges,
                       count(DISTINCT r.study_id) AS studies,
                       sum(CASE WHEN r.direction = 'increased' THEN 1 ELSE 0 END) AS increased
            """
        },
    )
    assert int(cell(answer, "edges")) == D2_EDGES, answer
    assert int(cell(answer, "studies")) == D2_STUDIES, answer
    assert int(cell(answer, "increased")) == D2_INCREASED, answer


def test_d2_keeps_the_single_dissenting_edge(client):
    """G4 through the protocol: disagreement is reported, never out-voted."""
    answer = client.call(
        "cypher_query",
        {
            "query": """
                MATCH (t:Taxon {id: 851})-[r:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0005575'})
                WHERE r.direction = 'decreased'
                RETURN r.source_record_id AS signature, r.study_id AS study
            """
        },
    )
    assert "1 row(s):" in answer, answer
    assert cell(answer, "signature") == D2_DISSENTING_RECORD, answer


def test_d15_audit_through_the_protocol(client):
    """D15 — the headline number, and the query that keeps the rest honest."""
    answer = client.call(
        "cypher_query",
        {
            "query": f"""
                CALL ontology_audit() YIELD rule, severity, violations, total, pct
                WHERE rule = '{D15_RULE}'
                RETURN rule, severity, violations, total, pct
            """
        },
    )
    assert cell(answer, "severity") == "warn", answer
    assert int(cell(answer, "violations")) == D15_VIOLATIONS, answer
    # A zero denominator is the failure this golden exists to catch: a rule
    # auditing property names nothing writes passes at 0 of 0.
    assert int(cell(answer, "total")) == D15_TOTAL, answer
    assert float(cell(answer, "pct")) == pytest.approx(15.2, abs=0.05), answer


def test_d15_per_source_census_through_the_protocol(client):
    """The breakdown the single percentage rolls up — and the reason it is not
    comparable across sources: every gutMDisorder edge is a violation because
    the source has no `study_design` column at all."""
    answer = client.call(
        "cypher_query",
        {
            "query": """
                MATCH (:Taxon)-[r:ASSOCIATED_WITH]->(:Disease)
                WHERE r.primary_source = 'gutmdisorder'
                RETURN count(r) AS edges,
                       sum(CASE WHEN r.study_design IS NULL THEN 1 ELSE 0 END) AS no_design
            """
        },
    )
    edges = int(cell(answer, "edges"))
    assert edges == 1636, answer
    assert int(cell(answer, "no_design")) == edges, answer

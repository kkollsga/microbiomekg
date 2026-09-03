"""Every Cypher this project publishes must project properties that exist.

kglite *warns* on a projection naming a property no node of that label carries
— `warning: WHERE references property 'hmdb_status' which no Metabolite node
has` — and then returns the column as null on every row. Nothing fails, so a
documented query can teach an agent a field that was renamed three releases ago
and every test stays green: `docs/usecases-and-pitfalls.md` D5 projected
`m.hmdb_status` (the property is `m.status`) and `p.enzyme` (no source carries
one) for as long as both existed.

Two gates here, over the skills an agent reads *and* Part D, which is the user
contract:

1. **Every projected `alias.property` exists somewhere on that label or
   relationship type.** Existence, not this query's rows: `r.resolution_note`
   is null for most subjects and real for 581 edges, and a per-result null
   check would call that dead. A property nothing carries is a defect
   regardless of the subject.
2. **Every Part D block runs and returns rows.** The skills already have that
   gate in `tests/test_mcp_skills.py`; Part D had none, and a fence holding two
   statements silently returned nothing at all when pasted as written.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.mcp_support import GRAPH, SKILLS_DIR, cypher_blocks, read_frontmatter

kglite = pytest.importorskip("kglite")

ROOT = Path(__file__).resolve().parents[1]
PART_D = ROOT / "docs" / "usecases-and-pitfalls.md"

#: `(alias:Label` and `[alias:REL_TYPE` — how a query says what a name is.
NODE_BINDING = re.compile(r"\((\w+)\s*:\s*([A-Za-z_]\w*)")
REL_BINDING = re.compile(r"\[(\w+)\s*:\s*([A-Z_][A-Z_|]*)")
PROJECTION = re.compile(r"\b(\w+)\.(\w+)\b")

#: `count(x)`, `collect(x)`, `size(x)` — a function name is not a binding, and
#: `n.count` is not a projection of one either.
NOT_A_BINDING = frozenset(
    {"count", "collect", "sum", "min", "max", "avg", "round", "size", "toLower",
     "toUpper", "length", "labels", "nodes", "type", "startNode", "endNode"}
)


@pytest.fixture(scope="session")
def graph():
    if not GRAPH.exists():
        pytest.skip(
            f"no graph at {GRAPH} — build it with "
            f"`.venv/bin/python scripts/build.py --scope microbial`"
        )
    loaded = kglite.load(str(GRAPH))
    if loaded.embedding_dim("Taxon", "scientific_name") is not None:
        from microbiomekg.embedder import CharGramEmbedder

        loaded.set_embedder(CharGramEmbedder())
    return loaded


@pytest.fixture(scope="session")
def carried(graph):
    """`(kind, label, property) -> is it on anything at all` — cached, because a
    Taxon scan is not free and the same fields recur across blocks."""
    seen: dict[tuple[str, str, str], bool] = {}

    def check(kind: str, label: str, prop: str) -> bool:
        key = (kind, label, prop)
        if key not in seen:
            pattern = f"(n:{label})" if kind == "node" else f"()-[n:{label}]->()"
            rows = list(
                graph.cypher(f"MATCH {pattern} WHERE n.{prop} IS NOT NULL RETURN count(n) AS n")
            )
            seen[key] = bool(rows and rows[0]["n"])
        return seen[key]

    return check


def part_d_blocks() -> list[tuple[str, str]]:
    text = PART_D.read_text(encoding="utf-8")
    blocks = re.findall(r"```cypher\n(.*?)```", text, re.DOTALL)
    return [(f"partD-{index}", block.strip()) for index, block in enumerate(blocks, 1)]


def skill_blocks() -> list[tuple[str, str]]:
    out = []
    for path in sorted(SKILLS_DIR.glob("*.md")):
        _, body = read_frontmatter(path)
        for index, block in enumerate(cypher_blocks(body), 1):
            out.append((f"{path.stem}-{index}", block))
    return out


ALL_BLOCKS = part_d_blocks() + skill_blocks()


@pytest.mark.parametrize("name,query", ALL_BLOCKS, ids=[name for name, _ in ALL_BLOCKS])
def test_no_published_query_projects_a_property_nothing_carries(name, query, carried):
    nodes = {a: label for a, label in NODE_BINDING.findall(query) if a not in NOT_A_BINDING}
    rels = {a: types for a, types in REL_BINDING.findall(query) if a not in NOT_A_BINDING}
    dead = []
    for alias, prop in PROJECTION.findall(query):
        if alias in NOT_A_BINDING or prop in NOT_A_BINDING:
            continue
        if alias in nodes and not carried("node", nodes[alias], prop):
            dead.append(f"{nodes[alias]}.{prop}")
        elif alias in rels and not any(
            carried("rel", one, prop) for one in rels[alias].split("|")
        ):
            dead.append(f"{rels[alias]}.{prop}")
    assert not dead, (
        f"{name} projects {sorted(set(dead))}, which nothing in the graph carries. "
        f"kglite warns and returns null on every row rather than failing, so this "
        f"reads as an answer. Use the property the nodes actually have, or drop the "
        f"projection.\n\n{query}"
    )


PART_D_BLOCKS = part_d_blocks()


@pytest.mark.parametrize(
    "name,query", PART_D_BLOCKS, ids=[name for name, _ in PART_D_BLOCKS]
)
def test_every_part_d_block_runs_and_answers(name, query, graph):
    """Part D is the user contract; a block in it that returns nothing is a
    broken promise, and two statements in one fence is how that happens."""
    try:
        rows = list(graph.cypher(query))
    except Exception as exc:  # noqa: BLE001 - the message is the whole point
        pytest.fail(f"{name} failed: {exc}\n\n{query}")
    assert rows, (
        f"{name} runs and returns nothing. One statement per fence: kglite takes "
        f"a single statement, and a second one after it is read as a continuation "
        f"that matches nothing.\n\n{query}"
    )

"""The prose an agent reads must be as true as the Cypher it runs.

``tests/test_mcp_skills.py`` proves every fenced block in the skill pack
parses, executes and returns rows. It cannot see a *sentence* that is wrong,
and on 2026-09-03 an evaluation found the shipped ``metabolites_pathways``
skill telling agents there was no ``CONSUMES`` edge in a graph holding 4,784 of
them, with the manifest under-counting the graph's sources — all 810 tests
green, because the stale skill's queries still ran.

This module closes that. Every number and every existential phrase in a skill
body, in a skill's routing ``description`` and in the manifest's two prose keys
must be covered by a claim in ``mcp/claims/`` (``tests/skill_claims`` documents
the form and the escape hatches), and every graph claim is executed against the
built graph. Four failures are possible and all four are wanted:

1. a claim's query disagrees with its expected value — the prose drifted from
   the data, which is the defect this module exists for;
2. a number in the prose is covered by no claim — someone added an unchecked
   assertion, and the gate refuses to let it in silently;
3. a claim is filed under a section that no longer exists — the sidecar and the
   skill have come apart, so nothing was being checked;
4. an annotation is malformed — a claim nobody can run is worse than no claim.

``test_the_gate_can_fail`` keeps the whole thing non-vacuous: it runs the
scanner over hand-written text carrying each defect and asserts each is seen.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import skill_claims
from tests.mcp_support import GRAPH
from tests.skill_claims import (
    Claim,
    ClaimSyntaxError,
    canonical,
    checkable_numbers,
    claims_by_section,
    existential_phrases,
    manifest_units,
    parse_claim,
    skill_units,
    split_sections,
)

kglite = pytest.importorskip("kglite")

SKILL_FILES = sorted(skill_claims.SKILLS_DIR.glob("*.md"))


@pytest.fixture(scope="session")
def graph():
    """The saved graph, which is the artefact the MCP server actually serves."""
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


def _units():
    collected = []
    for path in SKILL_FILES:
        collected.extend(skill_units(path))
    collected.extend(manifest_units())
    return collected


UNITS = _units()
GRAPH_CLAIMS = list(
    dict.fromkeys(
        claim for unit in UNITS for claim in unit.claims if not claim.external
    )
)


def _matches(actual, expected: str) -> bool:
    """``4784`` against 4784, ``55.8`` against 55.79..., and nothing else."""
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        return False
    decimals = len(expected.partition(".")[2])
    return abs(float(actual) - float(expected)) < 0.5 * 10 ** (-decimals)


@pytest.mark.parametrize(
    "claim", GRAPH_CLAIMS, ids=[f"{c.where}:{'/'.join(c.values)}" for c in GRAPH_CLAIMS]
)
def test_every_graph_claim_reproduces_on_the_built_graph(claim: Claim, graph):
    if claim.needs_vectors and graph.embedding_dim("Taxon", "scientific_name") is None:
        pytest.skip(
            "this claim is about the vector lane and the graph has no embedding "
            "store — rebuild with `scripts/build.py --with-vectors` to check it"
        )
    try:
        rows = list(graph.cypher(claim.cypher))
    except Exception as exc:  # noqa: BLE001 - the message is the whole point
        pytest.fail(f"{claim.where}: claim query failed: {exc}\n\n{claim.cypher}")
    assert len(rows) == 1, (
        f"{claim.where}: a claim must aggregate to exactly one row; this one "
        f"returned {len(rows)}.\n\n{claim.cypher}"
    )
    actual = list(rows[0].values())
    assert len(actual) == len(claim.values), (
        f"{claim.where}: the query returns {len(actual)} columns and the claim "
        f"expects {len(claim.values)} values.\n\n{claim.cypher}"
    )
    wrong = [
        f"{name}: prose says {expected}, graph says {value!r}"
        for (name, value), expected in zip(rows[0].items(), claim.values)
        if not _matches(value, expected)
    ]
    assert not wrong, (
        f"{claim.where}: the prose says something the graph does not.\n  "
        + "\n  ".join(wrong)
        + f"\n\n{claim.cypher}"
    )


@pytest.mark.parametrize("unit", UNITS, ids=[unit.where for unit in UNITS])
def test_every_number_in_the_agent_surface_carries_a_claim(unit):
    """A bare number is an unchecked assertion; here it is a failure."""
    expected = {value for claim in unit.claims for value in claim.values}
    uncovered = sorted({n for n in checkable_numbers(unit.text) if n not in expected})
    assert not uncovered, (
        f"{unit.where}: {', '.join(uncovered)} is asserted with no claim to check "
        f"it. Add `<!-- claim: <cypher> == <value> -->` under `## {unit.section}` "
        f"in the file's sidecar in mcp/claims/, or "
        f"`<!-- claim external: <value> — <whose number it is> -->` when the graph "
        f"cannot measure it. See tests/skill_claims.py for the escape hatches.\n\n"
        f"{unit.text[:400]}"
    )


@pytest.mark.parametrize("unit", UNITS, ids=[unit.where for unit in UNITS])
def test_every_existential_phrase_in_the_agent_surface_carries_a_claim(unit):
    """"There is no CONSUMES edge in this graph at all" was the whole defect.

    An existential carries no number for the check above to catch, so it is
    covered by the presence of a claim rather than by a value — normally a
    count the graph reports as 0.
    """
    phrases = existential_phrases(unit.text)
    if not phrases:
        return
    assert unit.claims, (
        f"{unit.where}: says {phrases!r} and no claim checks it. An existential "
        f"statement about the graph's contents is the shape the 2026-09-03 defect "
        f"took; annotate it under `## {unit.section}` with the count that proves it."
    )


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.stem)
def test_each_skill_carries_at_least_one_executed_claim(path: Path):
    """Coverage is satisfiable by writing no numbers; that is not the deal.

    Every skill in this pack quantifies its layer — that is what makes them
    worth injecting — so every one must put at least one of those numbers in
    front of the graph.
    """
    executed = [c for unit in skill_units(path) for c in unit.claims if not c.external]
    assert executed, (
        f"{path.name} carries no executable claim about the graph; "
        f"mcp/claims/{path.name} is where they go"
    )


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.stem)
def test_no_claim_is_filed_under_a_section_that_no_longer_exists(path: Path):
    """A renamed section silently unhooks its claims — so it is an error.

    ``skill_units`` raises on it; this asserts the raise reaches a test rather
    than only whichever other test happened to touch the file first.
    """
    skill_units(path)  # raises ClaimSyntaxError if a sidecar heading is orphaned
    sidecar = skill_claims.CLAIMS_DIR / path.name
    if sidecar.is_file():
        assert claims_by_section(sidecar), f"{sidecar} declares no claims"


def test_the_gate_can_fail():
    """The mutation test, run every time instead of once by hand.

    Each stanza is a defect this module must see. A refactor that makes the
    scanner permissive turns this red, rather than turning the whole gate into
    a green that cannot go red.
    """
    body = "## Coverage\n\nThere are 4,784 consumption edges over 714 taxa.\n"
    claim = parse_claim(
        " MATCH ()-[r:CONSUMES]->() RETURN count(r), count(DISTINCT startNode(r)) "
        "== 4784, 714 ",
        "",
        "fixture",
    )
    covered = {v for v in claim.values}
    assert not [n for n in checkable_numbers(body) if n not in covered]

    # The mutation: one number moves and its cover is gone.
    mutated = checkable_numbers(body.replace("4,784", "4,000"))
    assert "4000" in mutated and "4000" not in covered

    # The existential phrasing of the same defect, which carries no number.
    assert existential_phrases("There is no CONSUMES edge in this graph at all.")
    assert existential_phrases("MiMeDB is not loaded.")
    assert not existential_phrases("96 metabolites have a non-zero MES.")

    # Escape hatches stay narrow: code, years, versions and labels are not claims.
    assert checkable_numbers("`LIMIT 10`, CARD 4.0.2, Maier 2018, leg 3, 40 isolates") == ["40"]
    assert checkable_numbers("which of the six sources wrote this") == ["6"]
    assert checkable_numbers("Four legs, four different claims") == []
    assert canonical("4,784") == "4784" and canonical("55.8%") == "55.8"

    # Sections are the scope, and they come from the headings.
    assert [name for name, _ in split_sections("# A\ntext\n## B\nmore")] == [
        "preamble", "A", "B",
    ]

    # A malformed annotation is an error, never a skip.
    for payload, kind in (
        (" RETURN 1 ", ""),                        # no `==`
        (" RETURN count(r) == ", ""),              # no expected value
        (" count them == 4 ", ""),                 # not Cypher
        (" 63 ", " external"),                     # no reason
        (" 63 — because ", " external"),           # reason too short
    ):
        with pytest.raises(ClaimSyntaxError):
            parse_claim(payload, kind, "fixture")

    # A thousands separator inside a claim cannot be told from the separator
    # between two values, so it becomes two — and the column count is what
    # catches it, loudly, when the claim runs.
    assert parse_claim(" RETURN count(r) == 5,592 ", "", "fixture").values == ("5", "592")

"""Reading the *prose* of the agent surface as something the graph can falsify.

The skills in ``mcp/microbiomekg.skills/`` and the two block scalars in
``mcp/microbiomekg_mcp.yaml`` are injected verbatim into what an agent reads,
so a sentence in them is part of the product in the way a docstring is not.
``tests/test_mcp_skills.py`` proves every fenced Cypher block *runs*; nothing
proved that the sentences around it were *true*, and on 2026-09-03 an
evaluation found a shipped skill telling agents there was no ``CONSUMES`` edge
in a graph that holds 4,784 of them — with 810 tests green, because every one
of that skill's queries still parsed, ran and returned rows.

This module is the missing half.

**Where the claims live.** Not in the skill: its body *is* the tool description
an agent reads, it is capped at 16 KB, and a page of assertion Cypher in the
middle of it is noise the agent pays for. Each gated file has a sidecar in
``mcp/claims/`` whose ``##`` headings mirror the skill's own sections, and the
claims for a section sit under its heading there. Section scope is deliberate:
it survives any rewording, and breaks only when a *number* changes or a
*section* is renamed — both of which are edits that should be re-measured.

**A claim** carries a query and the answer it must give::

    <!-- claim: MATCH ()-[r:CONSUMES]->() RETURN count(r) == 4784 -->

One annotation may check several values at once, in ``RETURN`` order::

    <!-- claim: MATCH (d:Drug)-[r:INHIBITS_GROWTH_OF]->(t:Taxon)
         RETURN count(r), count(DISTINCT d), count(DISTINCT t) == 5592, 399, 38 -->

A claim that only holds on a ``--with-vectors`` build declares it, and is
skipped rather than failed on a graph with no embedding store::

    <!-- claim vectors: MATCH (t:Taxon) ... RETURN t.id == 1496 -->

A number that is genuinely not a graph measurement — an assay condition, a
figure from a cited paper, a label — is declared instead of measured, and must
say who it belongs to::

    <!-- claim external: 63 — Johnson 2019: identical V4 sequences belong to
         different species with 63% probability. Not measurable here. -->

**Checkable tokens** — every number and every existential phrase in the prose.
A number is *covered* when a claim in its section expects that exact value; an
existential phrase is covered when its section carries any claim at all.
Anything uncovered fails the gate, which is what stops a new unchecked number
being added silently.

Escape hatches, all of them explicit and all of them documented here:

- a number inside ``backticks`` is part of a query fragment, an identifier or a
  CURIE, not a claim (``LIMIT 10``, ``CHEBI:30772``, ``[0.05, 0.475, 0.475]``);
- a four-digit year (1900-2099) written without a thousands separator is a
  date. A real four-digit count is written ``1,935``, which this repo does
  anyway, and is then checked;
- a dotted version (``4.0.2``) is a version, and ``Leg 3`` / ``type 2 diabetes``
  is a label — the word in front is what makes it one;
- ``1.`` opening a line is a list marker;
- in a skill's ``description``, a phrase in 'single quotes' is an example of
  what a *user* might type, not an assertion about the graph;
- and anything else is ``claim external:`` with a reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "mcp" / "microbiomekg.skills"
CLAIMS_DIR = ROOT / "mcp" / "claims"
MANIFEST = ROOT / "mcp" / "microbiomekg_mcp.yaml"
MANIFEST_CLAIMS = CLAIMS_DIR / "manifest.md"

#: The manifest keys whose text reaches an agent: `instructions` is the
#: handshake blob, `overview_prefix` rides every bare graph_overview(). Both are
#: prose about the graph, so both are gated. Any other key is configuration.
MANIFEST_PROSE_KEYS = ("instructions", "overview_prefix")

#: The pseudo-section for a skill's YAML `description` — the routing heuristic,
#: never truncated, and the half an agent reads first.
DESCRIPTION = "description"

#: A reason on `claim external:` has to carry information, the way
#: `scripts/check_lint_allowances.py` requires one on an `#[allow]`. A bare
#: "external" would turn the escape hatch into a way of switching the gate off.
MIN_EXTERNAL_REASON = 25


class ClaimSyntaxError(ValueError):
    """A claim annotation that cannot be read. Never silently skipped."""


@dataclass(frozen=True)
class Claim:
    """One annotation: a query with its expected answer, or a declared
    non-graph value with the reason it is not measurable here."""

    external: bool
    values: tuple[str, ...]
    cypher: str = ""
    reason: str = ""
    needs_vectors: bool = False
    where: str = ""

    def __str__(self) -> str:
        kind = "external" if self.external else "graph"
        return f"{self.where} [{kind}] {', '.join(self.values)}"


@dataclass
class Unit:
    """One gated section of prose, with the claims declared for it."""

    where: str
    section: str
    text: str
    claims: list[Claim] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing claims
# ---------------------------------------------------------------------------

CLAIM_RE = re.compile(
    r"<!--\s*claim(?P<kind>\s+external|\s+vectors)?\s*:(?P<payload>.*?)-->",
    re.DOTALL,
)
_VALUE_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*$", re.MULTILINE)


def _split_values(raw: str, where: str) -> tuple[str, ...]:
    values = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not values:
        raise ClaimSyntaxError(f"{where}: claim declares no expected value")
    for value in values:
        if not _VALUE_RE.match(value):
            raise ClaimSyntaxError(
                f"{where}: expected value {value!r} is not a plain number. "
                f"Write 5592, never 5,592 — the comma separates the values."
            )
    return values


def parse_claim(payload: str, kind: str, where: str) -> Claim:
    payload = " ".join(payload.split())
    site = f"{where}: {payload[:70]}"
    if kind.strip() == "external":
        body, dash, reason = payload.partition("—")
        if not dash:
            raise ClaimSyntaxError(
                f"{site}: an external claim is `<value>[, <value>] — <reason>`; "
                f"no em dash found"
            )
        reason = reason.strip()
        if len(reason) < MIN_EXTERNAL_REASON:
            raise ClaimSyntaxError(
                f"{site}: external reason is {len(reason)} characters, under the "
                f"{MIN_EXTERNAL_REASON} this gate requires. Say whose number it is "
                f"and why the graph cannot measure it."
            )
        return Claim(True, _split_values(body, site), reason=reason, where=where)
    cypher, sep, expected = payload.rpartition("==")
    if not sep:
        raise ClaimSyntaxError(
            f"{site}: a graph claim is `<cypher> == <value>[, <value>]`; no `==` found"
        )
    cypher = cypher.strip()
    if not cypher.upper().startswith(("MATCH", "CALL", "RETURN", "UNWIND", "WITH")):
        raise ClaimSyntaxError(f"{site}: {cypher!r} does not read like Cypher")
    return Claim(
        False,
        _split_values(expected, site),
        cypher=cypher,
        needs_vectors=kind.strip() == "vectors",
        where=where,
    )


def split_sections(text: str) -> list[tuple[str, str]]:
    """``[(heading, body)]``, with anything before the first heading as
    ``preamble``. The heading *text* is the key, so a section survives being
    moved or reworded inside — but not renamed."""
    marks = [(m.start(), m.end(), m.group(1)) for m in HEADING_RE.finditer(text)]
    if not marks:
        return [("preamble", text)]
    out = [("preamble", text[: marks[0][0]])]
    for index, (_, end, title) in enumerate(marks):
        stop = marks[index + 1][0] if index + 1 < len(marks) else len(text)
        out.append((title, text[end:stop]))
    return out


def claims_by_section(path: Path) -> dict[str, list[Claim]]:
    """Read a sidecar: ``##`` headings naming sections, each holding claims."""
    if not path.is_file():
        return {}
    sections: dict[str, list[Claim]] = {}
    for name, body in split_sections(path.read_text(encoding="utf-8")):
        for match in CLAIM_RE.finditer(body):
            claim = parse_claim(
                match.group("payload"),
                match.group("kind") or "",
                f"{path.name} [{name}]",
            )
            sections.setdefault(name, []).append(claim)
    return sections


# ---------------------------------------------------------------------------
# Finding the checkable tokens in prose
# ---------------------------------------------------------------------------

FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]*`")
NUMBER_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?%?(?![\w])")
YEAR_RE = re.compile(r"^(?:1[89]|20)\d\d$")
VERSION_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+){2,}")

#: `1.` opening a line is a numbered-list marker, not a measurement.
LIST_MARKER_RE = re.compile(r"^\s*\d+\.\s", re.MULTILINE)

#: `Leg 3`, `Guard 1`, `Stage 2`, `type 2 diabetes` — a pointer to a section of
#: the same document, or a name that happens to carry a digit. Neither asserts
#: anything about the graph, and flagging them would make the gate tiresome
#: enough to get loosened. The word in front is what makes it a label, and
#: `Legs 3 and 4` is one label rather than two numbers.
LABEL_RE = re.compile(
    r"\b(?:leg|stage|guard|step|part|phase|rule|section|table|figure|item|lane|"
    r"note|point|question|outcome|way|type|rank)s?[\s-]\d+(?:\s+and\s+\d+)?",
    re.IGNORECASE,
)

#: Spelled-out numbers are checked too — the manifest's "which of the **six**
#: sources wrote this edge" was wrong by four and no digit-scanner would have
#: seen it. They are only checked in front of a noun the graph can count, so
#: "Four legs, four different claims" (a document's structure) stays prose.
#: ``one`` is deliberately absent: English uses it as an article ("one row per
#: signature", "at least one taxon") far more often than as a count, and a
#: detector that flags those trains the author to switch the gate off.
WORD_NUMBERS = {
    "zero": "0",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
}
COUNTABLE_NOUNS = (
    "sources?|edges?|nodes?|taxa|taxon|organisms?|metabolites?|drugs?|diseases?"
    r"|signatures?|pathways?|producers?|consumers?|strains?|isolates?|genes?"
    r"|determinants?|mechanisms?|tombstones?|records?|values?|propert(?:y|ies)"
    r"|fields?|relationships?|studies|papers?"
)
WORD_NUMBER_RE = re.compile(
    r"\b("
    + "|".join(WORD_NUMBERS)
    + r")[\s-](?:\w+[\s-])?(?:"
    + COUNTABLE_NOUNS
    + r")\b",
    re.IGNORECASE,
)

#: An existential claim carries no number, so nothing above can see it — and it
#: is the shape the 2026-09-03 defect took ("there is no CONSUMES edge in this
#: graph at all"). Each pattern must be answered by a claim in its section; a
#: count of 0 is the usual one. Kept deliberately narrow: these say something
#: about the graph's *contents*, not about the world.
EXISTENTIAL_PATTERNS = (
    r"\bno\s+(?:\S+\s+){0,2}(?:edges?|nodes?)\b",
    r"(?<!non-)\bzero\s+\w+",
    r"\b(?:is|are|was|were)\s+not\s+loaded\b",
    r"\b(?:does|do|did)\s+not\s+exist\b",
    r"\bnot\s+in\s+(?:this|the)\s+graph\b",
    r"\bnone\s+at\s+all\b",
    r"\bnothing\s+at\s+all\b",
)
EXISTENTIAL_RE = re.compile("|".join(EXISTENTIAL_PATTERNS), re.IGNORECASE)


def canonical(token: str) -> str:
    """`4,784` and `55.8%` as the value an annotation writes: `4784`, `55.8`."""
    return token.replace(",", "").rstrip("%")


def _mask_code(text: str) -> str:
    """Fenced blocks and inline code become a neutral word.

    A placeholder rather than an empty string, so ``no `Gene` node`` still reads
    as an existential phrase after masking.
    """
    text = FENCE_RE.sub(" CODE ", text)
    text = INLINE_CODE_RE.sub(" CODE ", text)
    return LIST_MARKER_RE.sub("  ", text)


def checkable_numbers(text: str) -> list[str]:
    """Every number in ``text`` that asserts something about the graph."""
    masked = LABEL_RE.sub(" LABEL ", VERSION_RE.sub(" VERSION ", _mask_code(text)))
    found = []
    for raw in NUMBER_RE.findall(masked):
        token = raw.rstrip(",")  # a trailing sentence comma, not a separator
        plain = canonical(token)
        if "," not in token and not token.endswith("%") and YEAR_RE.match(plain):
            continue  # a date; a four-digit count is written with a separator
        found.append(plain)
    for match in WORD_NUMBER_RE.finditer(masked):
        found.append(WORD_NUMBERS[match.group(1).lower()])
    return found


def existential_phrases(text: str) -> list[str]:
    return [match.group(0) for match in EXISTENTIAL_RE.finditer(_mask_code(text))]


def quoted_examples_removed(description: str) -> str:
    """A TRIGGER's 'my 30 significant genera' is the user's words, not a claim."""
    return re.sub(r"'[^']*'", " CODE ", description)


# ---------------------------------------------------------------------------
# Assembling the gated units
# ---------------------------------------------------------------------------


def _bind(
    where: str, sections: list[tuple[str, str]], claims: dict[str, list[Claim]]
) -> list[Unit]:
    names = {name for name, _ in sections}
    unknown = sorted(set(claims) - names)
    if unknown:
        raise ClaimSyntaxError(
            f"mcp/claims/{where}: claims filed under {unknown}, which names no "
            f"section of it. A renamed section needs its claims renamed with it; "
            f"the sections are {sorted(names)}"
        )
    return [
        Unit(f"{where} [{name}]", name, text, list(claims.get(name, [])))
        for name, text in sections
    ]


def skill_units(path: Path) -> list[Unit]:
    """Every gated section of one skill: its description, then its body."""
    from tests.mcp_support import read_frontmatter

    frontmatter, body = read_frontmatter(path)
    sections = [
        (DESCRIPTION, quoted_examples_removed(str(frontmatter.get("description", ""))))
    ]
    sections += split_sections(body)
    return _bind(path.name, sections, claims_by_section(CLAIMS_DIR / path.name))


def manifest_sections(path: Path = MANIFEST) -> list[tuple[str, str]]:
    """The manifest's two prose block scalars, keyed by their YAML key."""
    lines = path.read_text(encoding="utf-8").splitlines()
    sections = []
    for index, line in enumerate(lines):
        key = line.split(":", 1)[0]
        if key not in MANIFEST_PROSE_KEYS or not line.rstrip().endswith(("|", ">")):
            continue
        body, cursor = [], index + 1
        while cursor < len(lines) and (
            not lines[cursor].strip() or lines[cursor].startswith(" ")
        ):
            body.append(lines[cursor])
            cursor += 1
        sections.append((key, "\n".join(body)))
    return sections


def manifest_units() -> list[Unit]:
    return _bind(MANIFEST.name, manifest_sections(), claims_by_section(MANIFEST_CLAIMS))


def all_units() -> list[Unit]:
    units: list[Unit] = []
    for path in sorted(SKILLS_DIR.glob("*.md")):
        units.extend(skill_units(path))
    units.extend(manifest_units())
    return units

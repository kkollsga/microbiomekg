#!/usr/bin/env python3
"""Generate ``tests/fixtures/hmdb_mini/hmdb_metabolites.xml`` — 62 metabolites.

Every record below is here because it is a **trap from
``docs/research/source-formats.md`` §2**, and the file names each one so the
test module can assert against a row whose purpose is written down rather than
inferred from a magic accession. The 40 filler records at the end exist for one
reason: to make the fixture's status distribution look like the real file's
(88.8% never observed), so a loader that quietly selected everything would fail
the count rather than merely look busy.

Regenerate with::

    .venv/bin/python tests/fixtures/make_hmdb_mini.py

The taxon names are constrained by ``tests/fixtures/taxdump_mini``: every name
that is meant to resolve is in that dump, and every name that is meant to fail
is not. Note the two rank cases — ``Bacillota`` is in the mini dump as the
phylum 1239 and exercises the production rank ceiling, while ``Firmicutes`` is
absent from it and exercises the unresolved path. **On the real dump they are
the same trap wearing two faces:** NCBI files the exact string ``Firmicutes``
as a *synonym of 1783272 `Bacillati`, a kingdom*, so it resolves — to the wrong
thing — and only the rank ceiling stops the edge.
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent / "hmdb_mini" / "hmdb_metabolites.xml"

#: The disease name that carries 20,020 of HMDB's 27,670 disease rows — 72% of
#: the whole layer, where the next name down has 831. The fixture puts it on
#: three records so "the disease rows are counted and not loaded" is testable.
MEGA_DISEASE = "3-methylglutaconic aciduria type II, X-linked"

#: U+FB01. `Biﬁdobacterium` is a distinct string from `Bifidobacterium` and
#: nothing in names.dmp matches it.
LIGATURE = "Biﬁdobacterium"

#: (accession, name, status, chebi, kegg, pubchem, biospecimens, origins,
#:  microbes, diseases, secondary, pmids)
#: `microbes` is {genus-level term: [species-level terms]}, mirroring HMDB's
#: two-level free-text organism tree.
RECORDS: list[dict] = [
    dict(
        why="microbial + feces + chebi Reactome maps; a genus with a species "
        "child (only the species becomes an edge) beside a childless genus",
        accession="HMDB0000011",
        name="Butyric acid",
        status="quantified",
        chebi="17968",
        kegg="C00246",
        pubchem="264",
        biospecimens=["Blood", "Feces", "Urine"],
        origins=["Endogenous", "Food"],
        microbes={
            "Faecalibacterium": ["Faecalibacterium prausnitzii"],
            "Roseburia": [],
        },
        secondary=["HMDB00011", "HMDB0004935"],
        pmids=["10362454", "7762816", "10362454"],
    ),
    dict(
        why="detected, so still in-vitro; Akkermansia muciniphila is D5's taxon",
        accession="HMDB0000012",
        name="Acetic acid",
        status="detected",
        chebi="30089",
        kegg="C00033",
        pubchem="176",
        biospecimens=["Blood", "Feces"],
        origins=["Endogenous"],
        microbes={"Bacteroides": [], "Akkermansia": ["Akkermansia muciniphila"]},
        pmids=["11052553"],
    ),
    dict(
        why="expected -> computational-predicted, and no Feces: selected by the "
        "microbial rule alone",
        accession="HMDB0000013",
        name="Trimethylamine N-oxide",
        status="expected",
        chebi="15724",
        kegg="C01104",
        pubchem="1145",
        biospecimens=["Blood", "Urine"],
        origins=["Endogenous"],
        microbes={"Escherichia": ["Escherichia coli"]},
        pmids=["2593832"],
    ),
    dict(
        why="the substring trap: `Antimicrobial agent` is a drug that KILLS "
        "microbes and must not be read as microbial origin. No feces, no "
        "mapped chebi -> selected by nothing",
        accession="HMDB0000014",
        name="Triclosan",
        status="predicted",
        chebi="164200",
        kegg="",
        pubchem="5564",
        biospecimens=[],
        origins=["Synthetic"],
        microbes={},
        roles=["Industrial application/Household products/Antimicrobial agent"],
    ),
    dict(
        why="feces-only: no microbial origin, chebi not in the Reactome mini",
        accession="HMDB0000015",
        name="Skatole",
        status="expected",
        chebi="9169",
        kegg="C08313",
        pubchem="6736",
        biospecimens=["Feces"],
        origins=["Food"],
        microbes={},
    ),
    dict(
        why="reactome-chebi only: predicted, never in feces, but ChEBI2Reactome "
        "maps its id — the third selection rule, on its own",
        accession="HMDB0000016",
        name="Deoxycholic acid",
        status="predicted",
        chebi="28834",
        kegg="C04483",
        pubchem="222528",
        biospecimens=["Blood"],
        origins=["Endogenous"],
        microbes={},
    ),
    dict(
        why="the U+FB01 ligature typo: a distinct string from Bifidobacterium "
        "that names.dmp cannot match",
        accession="HMDB0000017",
        name="Propionic acid",
        status="quantified",
        chebi="17272",
        kegg="C00163",
        pubchem="1032",
        biospecimens=["Feces"],
        origins=["Endogenous"],
        microbes={LIGATURE: [], "Bifidobacterium": []},
        pmids=["7061274"],
    ),
    dict(
        why="the rank-mixing row: a phylum, a community, a Gram stain and a "
        "string absent from names.dmp, all at HMDB's 'genus' level",
        accession="HMDB0000018",
        name="Succinic acid",
        status="quantified",
        chebi="15741",
        kegg="C00042",
        pubchem="1110",
        biospecimens=["Feces", "Blood"],
        origins=["Endogenous"],
        microbes={
            "Bacillota": [],
            "Firmicutes": [],
            "Human gut microbiota": [],
            "Gram-negative bacteria": [],
        },
        pmids=["11380830"],
    ),
    dict(
        why="a placeholder organism: `Bacteroides sp.` is a real NCBI node "
        "(29523) and must resolve and carry the placeholder flag, not be "
        "dropped by a name substring (G9)",
        accession="HMDB0000019",
        name="Indole-3-acetic acid",
        status="detected",
        chebi="16411",
        kegg="C00954",
        pubchem="802",
        biospecimens=["Feces"],
        origins=["Endogenous"],
        microbes={"Bacteroides sp.": []},
        pmids=["11418788"],
    ),
    dict(
        why="a misspelled species under a resolvable genus. A leaf-only rule "
        "would lose the claim entirely; the genus edge must survive",
        accession="HMDB0000020",
        name="Hippuric acid",
        status="quantified",
        chebi="18089",
        kegg="C01586",
        pubchem="464",
        biospecimens=["Feces", "Urine"],
        origins=["Food"],
        microbes={"Akkermansia": ["Akkermansia muciniphilia"]},
        pmids=["12865413"],
    ),
    dict(
        why="a synonym that is an NCBI placeholder name: `Clostridium "
        "symbiosum` is a synonym of `[Clostridium] symbiosum` (1512)",
        accession="HMDB0000021",
        name="Formic acid",
        status="detected",
        chebi="30751",
        kegg="C00058",
        pubchem="284",
        biospecimens=["Feces"],
        origins=["Endogenous"],
        microbes={"Clostridium symbiosum": []},
    ),
    dict(
        why="first of the ChEBI-key collision pair — one ChEBI id, two HMDB "
        "accessions, therefore one Metabolite node",
        accession="HMDB0000022",
        name="Lactic acid",
        status="quantified",
        chebi="78320",
        kegg="C00186",
        pubchem="612",
        biospecimens=["Feces"],
        origins=["Endogenous"],
        microbes={"Lactobacillus": []},
    ),
    dict(
        why="second of the collision pair: same chebi, different accession",
        accession="HMDB0000023",
        name="D-Lactic acid",
        status="detected",
        chebi="78320",
        kegg="C00256",
        pubchem="61503",
        biospecimens=["Feces"],
        origins=["Endogenous"],
        microbes={},
    ),
    dict(
        why="the single lowercase kegg_id in the file (`c0338` in HMDB 5.0): "
        "the KEGG join must upper-case or this metabolite silently misses",
        accession="HMDB0000024",
        name="Pyruvic acid",
        status="quantified",
        chebi="32816",
        kegg="c00022",
        pubchem="1060",
        biospecimens=["Feces"],
        origins=["Endogenous"],
        microbes={},
    ),
    dict(
        why="a kegg_id KEGG has withdrawn since HMDB 5.0 — reported, never "
        "silently dropped",
        accession="HMDB0000025",
        name="Withdrawn compound",
        status="expected",
        chebi="",
        kegg="C00626",
        pubchem="",
        biospecimens=["Feces"],
        origins=["Food"],
        microbes={},
    ),
    dict(
        why="the disease layer's dominant name, three times over: counted and "
        "not loaded",
        accession="HMDB0000026",
        name="Glutaric acid",
        status="quantified",
        chebi="17859",
        kegg="C00489",
        pubchem="743",
        biospecimens=["Feces", "Urine"],
        origins=["Endogenous"],
        microbes={},
        diseases=[
            (MEGA_DISEASE, ""),
            (MEGA_DISEASE, "250950"),
            ("Colorectal cancer", "114500"),
        ],
    ),
    dict(
        why="a kegg_id of the `D` (drug) namespace, which cannot join a "
        "compound list at all",
        accession="HMDB0000027",
        name="A drug-namespace compound",
        status="expected",
        chebi="",
        kegg="D00109",
        pubchem="",
        biospecimens=["Feces"],
        origins=["Food"],
        microbes={},
    ),
    dict(
        why="no chebi at all, so the node is keyed on its HMDB accession",
        accession="HMDB0000028",
        name="Unmapped microbial metabolite",
        status="quantified",
        chebi="",
        kegg="",
        pubchem="",
        biospecimens=["Feces"],
        origins=["Endogenous"],
        microbes={"Bacteroides": ["Bacteroides thetaiotaomicron"]},
        pmids=["9607216"],
    ),
    dict(
        why="an empty <chebi_id/> element: `.text` is None, and reading it "
        "straight writes the string 'None' into the CSV",
        accession="HMDB0000029",
        name="Empty-element compound",
        status="detected",
        chebi=None,
        kegg=None,
        pubchem=None,
        biospecimens=["Feces"],
        origins=[],
        microbes={},
    ),
    dict(
        why="microbial origin with NO organism named beneath it. 67 of HMDB's "
        "224 microbial records are like this: a real origin claim with "
        "nothing to point an edge at, which is why '224 microbial "
        "metabolites' is not '224 production edges'",
        accession="HMDB0000031",
        name="Origin without an organism",
        status="quantified",
        chebi="",
        kegg="",
        pubchem="",
        biospecimens=["Blood"],
        origins=["Endogenous"],
        microbes={},
        bare_microbe=True,
    ),
    dict(
        why="a cross-kingdom homonym: `Bacillus` is a bacterial genus (1386) "
        "AND a genus of stick insects (55087). names.dmp cannot choose; "
        "the microbial-origin context can, and it is HMDB's single most "
        "common organism term (13 metabolites in the real file)",
        accession="HMDB0000032",
        name="Homonym compound",
        status="quantified",
        chebi="",
        kegg="",
        pubchem="",
        biospecimens=["Feces"],
        origins=["Endogenous"],
        microbes={"Bacillus": []},
    ),
    dict(
        why="a metabolite with more references than the publication cap, so "
        "`n_publications` and the truncated list disagree on purpose",
        accession="HMDB0000030",
        name="Well-studied metabolite",
        status="quantified",
        chebi="16991",
        kegg="C00039",
        pubchem="6083",
        biospecimens=["Feces"],
        origins=["Endogenous"],
        microbes={"Blautia": []},
        pmids=[str(20000000 + i) for i in range(30)],
    ),
]

#: 40 filler records that no rule selects. They are what makes the fixture's
#: shape honest: HMDB is 88.8% never-observed, and a loader keeping everything
#: has to fail a count rather than merely produce more rows.
RECORDS += [
    dict(
        why="filler: predicted/expected, no feces, no mapped chebi",
        accession=f"HMDB{40000 + i:07d}",
        name=f"Predicted compound {i}",
        status="predicted" if i % 2 else "expected",
        chebi="",
        kegg="",
        pubchem="",
        biospecimens=["Blood"] if i % 3 else [],
        origins=["Food"],
        microbes={},
    )
    for i in range(40)
]


def term(name: str, children: str = "", level: int = 1) -> str:
    kids = f"<descendants>{children}</descendants>" if children else ""
    return (
        f"<term>{escape(name)}</term><definition/><parent_id/>"
        f"<level>{level}</level><type>{'parent' if children else 'child'}</type>"
        f"<synonyms></synonyms>{kids}"
    )


def descendant(name: str, children: str = "", level: int = 1) -> str:
    return f"<descendant>{term(name, children, level)}</descendant>"


def ontology_block(record: dict) -> str:
    """The `Disposition` root, plus a `Role` root when the record needs one."""
    source_children = "".join(descendant(o, level=3) for o in record.get("origins", []))
    microbes = record.get("microbes") or {}
    if record.get("bare_microbe"):
        # The `Microbe` node with no descendants at all — 67 real records.
        source_children += descendant(
            "Biological", descendant("Microbe", "", level=4), level=3
        )
    elif microbes:
        genera = "".join(
            descendant(
                genus,
                "".join(descendant(sp, level=6) for sp in species),
                level=5,
            )
            for genus, species in microbes.items()
        )
        source_children += descendant(
            "Biological", descendant("Microbe", genera, level=4), level=3
        )
    roots = [
        f"<root>{term('Disposition', descendant('Source', source_children, level=2), 1)}</root>"
    ]
    for path in record.get("roles", []):
        parts = path.split("/")
        block = ""
        for depth, part in enumerate(reversed(parts), start=1):
            block = descendant(part, block, level=len(parts) + 2 - depth)
        roots.append(f"<root>{term('Role', block, 1)}</root>")
    return "<ontology>" + "".join(roots) + "</ontology>"


def element(tag: str, value) -> str:
    """``<tag>value</tag>``, or a self-closing element when value is None.

    HMDB writes an absent scalar as ``<chebi_id/>``, not as an omitted element,
    and the two are different bugs to make: one gives ``.text is None``, the
    other gives ``find() is None``. The fixture carries both spellings.
    """
    if value is None:
        return f"<{tag}/>"
    return f"<{tag}>{escape(str(value))}</{tag}>"


def render(record: dict) -> str:
    parts = [
        element("accession", record["accession"]),
        element("status", record["status"]),
    ]
    if record.get("secondary"):
        parts.append(
            "<secondary_accessions>"
            + "".join(element("accession", a) for a in record["secondary"])
            + "</secondary_accessions>"
        )
    parts += [
        element("name", record["name"]),
        element("chemical_formula", "C4H8O2"),
        element("inchikey", f"KEY-{record['accession'][-4:]}-N"),
        ontology_block(record),
        "<biological_properties><biospecimen_locations>"
        + "".join(element("biospecimen", b) for b in record.get("biospecimens", []))
        + "</biospecimen_locations></biological_properties>",
    ]
    if record.get("diseases"):
        parts.append(
            "<diseases>"
            + "".join(
                f"<disease>{element('name', n)}{element('omim_id', o or None)}"
                f"<references></references></disease>"
                for n, o in record["diseases"]
            )
            + "</diseases>"
        )
    parts += [
        element("pubchem_compound_id", record.get("pubchem")),
        element("chebi_id", record.get("chebi")),
        element("kegg_id", record.get("kegg")),
    ]
    if record.get("pmids"):
        parts.append(
            "<general_references>"
            + "".join(
                f"<reference>{element('reference_text', 'Author A: A title. J. 2001.')}"
                f"{element('pubmed_id', p)}</reference>"
                for p in record["pmids"]
            )
            + "</general_references>"
        )
    body = "\n  ".join(parts)
    return f"<metabolite>\n  <!-- {escape(record['why'])} -->\n  {body}\n</metabolite>"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<hmdb xmlns="http://www.hmdb.ca">\n'
        + "\n".join(render(r) for r in RECORDS)
        + "\n</hmdb>\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT} ({len(RECORDS)} metabolites, {OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

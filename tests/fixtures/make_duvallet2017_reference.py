"""Derive ``duvallet2017_genera.tsv`` — the published non-specific genus set
that ``docs/benchmarks.md`` G7 scores D14's breadth ranking against — from
the paper's supplementary file S3.

Duvallet C, Gibbons SM, Gurry T, Irizarry RA, Alm EJ. *Meta-analysis of gut
microbiome studies identifies disease-specific and shared responses.* Nat
Commun 8:1784 (2017), PMID 29209090, PMC5716994, CC BY 4.0. The file is
``final/supp-files/file-S3.nonspecific_genera.txt`` in the authors'
MicrobiomeHD repository (``microbiomekg fetch --only duvallet2017`` puts it
under ``data/raw/duvallet2017/``); the Zenodo raw-data record behind the
paper is CC BY-NC and is not used.

Every row of S3 is a genus significant (q < 0.05) in at least one of the 28
case-control datasets — 144 of them — and its ``overall`` column is
``health``, ``disease`` or ``mixed`` for the 51 that were significant in the
same direction in at least two *diseases* (the paper's 24 + 20 + 7), blank
otherwise. This table keeps the 51 labelled rows, with the RDP lineage cut to
the genus name, because the number the benchmark asks for is how many of
D14's top-ranked genera are in that set. Two spellings are the source's own
and are kept verbatim: ``Escherichia/Shigella`` (RDP does not separate them)
and the ``Clostridium_XlVb``-style RDP cluster names, which is why the
reference has no plain *Clostridium* and the benchmark counts it as a miss
rather than mapping it.

The committed TSV is the reviewable artefact; this script is how it was cut,
and ``tests/test_acceptance.py`` asserts its shape.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RAW = ROOT / "data" / "raw" / "duvallet2017" / "file-S3.nonspecific_genera.txt"
OUT = HERE / "duvallet2017_genera.tsv"
LABELS = ("health", "disease", "mixed")


def rows(source: Path) -> list[tuple[str, str]]:
    out = []
    for line in source.read_text(encoding="utf-8").splitlines()[1:]:
        lineage, _, overall = line.partition("\t")
        if overall in LABELS:
            out.append((lineage.rsplit("g__", 1)[1], overall))
    return out


def main() -> int:
    if not RAW.is_file():
        print(f"no {RAW}: microbiomekg fetch --only duvallet2017", file=sys.stderr)
        return 3
    table = rows(RAW)
    counts = {label: sum(1 for _, o in table if o == label) for label in LABELS}
    assert counts == {"health": 24, "disease": 20, "mixed": 7}, counts
    OUT.write_text(
        "genus\toverall\n" + "".join(f"{g}\t{o}\n" for g, o in table),
        encoding="utf-8",
    )
    print(f"{OUT.name}: {len(table)} genera ({counts})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

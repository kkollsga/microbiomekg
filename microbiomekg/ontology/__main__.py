"""``python -m microbiomekg.ontology [path]`` — regenerate ``ontology.json``."""

from __future__ import annotations

import sys

from . import write_json

if __name__ == "__main__":
    print(write_json(sys.argv[1] if len(sys.argv) > 1 else "ontology.json"))

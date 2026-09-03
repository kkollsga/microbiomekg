#!/usr/bin/env python3
"""Thin caller: the code lives in :mod:`microbiomekg.serve`.

Kept so the documented command keeps working from a checkout without the
package installed; it puts the package's parent on the path and defers.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from microbiomekg.serve import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

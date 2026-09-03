"""A deterministic character-n-gram embedder — no model, no download, no network.

Why this rather than a sentence-transformer. The lookup this graph needs is
**name reconciliation**: a paper prints ``Clostridium dificile`` and the graph
holds ``Clostridioides difficile``. That is a *string* problem — a dropped
letter, a Latinised ending, an old genus — not a semantic one, and the
published embedding models this project could reach (``fastembed``,
``sentence-transformers``) are neither installed nor installable here without a
model download, which the build is not allowed to make. A character-n-gram
hashing embedder is the honest substitute: it is deterministic, needs nothing
but ``numpy``, and cosine similarity over it *is* n-gram overlap, which is
exactly the signal a misspelling preserves and BM25's whole-token lane loses.

It is not a semantic model and must not be described as one. ``text_score()``
over this store answers "spelled like", never "means the same as": it will not
connect *bowel* to *intestinal*, and a skill that promises it would be lying.
The vector lane's job here is to be the half of a hybrid lookup that survives a
typo, with BM25 supplying the half that rewards an exact token — see
``score_fuse`` in ``mcp/microbiomekg.skills/reconciliation.md``.

The hash is ``zlib.crc32``, not :func:`hash`, because Python salts string
hashing per process: a salted hash would embed the same name to a different
vector on every run, and the store would silently stop matching the queries the
server embeds after a restart.
"""

from __future__ import annotations

import re
import zlib

import numpy as np

#: Vector width. 256 keeps a taxon store of ~10k names at ~10 MB while leaving
#: n-gram collisions rare enough that the five Part C misspellings resolve.
DIMENSION = 256

#: N-gram widths, over the space-padded normalised string. 3 carries the typo
#: tolerance (a dropped letter destroys only the ~3 grams that span it); 4 and 5
#: carry enough word shape that a genus name does not match every congener.
NGRAMS = (3, 4, 5)

#: Stamped onto the embedding store so ``embedding_info()`` reports which
#: embedder wrote it — a model swap must be detectable, and this one has no
#: HuggingFace id to report.
MODEL_ID = f"microbiomekg-chargram-{DIMENSION}d-{''.join(str(n) for n in NGRAMS)}"

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalise(text: str) -> str:
    """Casefold, collapse everything non-alphanumeric to single spaces, pad.

    The padding is what makes a word's first and last letters carry n-grams of
    their own, so ``Fecalibacterium`` and ``Faecalibacterium`` still share their
    endings after the second character diverges.
    """
    return " " + _NON_ALNUM.sub(" ", text.casefold()).strip() + " "


class CharGramEmbedder:
    """The ``EmbeddingModel`` protocol over hashed character n-grams.

    Signed hashing (the sign taken from a second byte of the same checksum)
    makes colliding n-grams cancel on average rather than accumulate, which is
    what keeps a 256-wide vector usable over a 443k-term vocabulary.
    """

    def __init__(self, dimension: int = DIMENSION, ngrams: tuple[int, ...] = NGRAMS) -> None:
        self.dimension = int(dimension)
        self.ngrams = tuple(ngrams)
        self.model_id = MODEL_ID if (dimension, tuple(ngrams)) == (DIMENSION, NGRAMS) else (
            f"microbiomekg-chargram-{dimension}d-{''.join(str(n) for n in ngrams)}"
        )

    def _vector(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dimension, dtype=np.float32)
        if not isinstance(text, str) or not text.strip():
            return vec
        s = normalise(text)
        counts: dict[int, float] = {}
        for n in self.ngrams:
            if len(s) < n:
                continue
            for i in range(len(s) - n + 1):
                h = zlib.crc32(s[i : i + n].encode("utf-8"))
                slot = h % self.dimension
                sign = 1.0 if (h >> 16) & 1 else -1.0
                counts[slot] = counts.get(slot, 0.0) + sign
        for slot, raw in counts.items():
            # Sublinear term frequency, sign preserved: a name that repeats a
            # gram five times is not five times more about it.
            vec[slot] = np.sign(raw) * (1.0 + np.log(abs(raw))) if raw else 0.0
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm else vec

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t).tolist() for t in texts]


def build(model: str | None = None) -> CharGramEmbedder:
    """``extensions.embedder.factory`` entry point (``module:attr``).

    ``model`` is the manifest's ``model:`` string; it names the width so a
    manifest and a build that disagree are visible rather than silently
    mismatched. Anything else is an error, not a fallback — a server embedding
    queries at a different width than the store was written at scores nothing.
    """
    if model in (None, "", MODEL_ID):
        return CharGramEmbedder()
    raise RuntimeError(
        f"extensions.embedder.model must be {MODEL_ID!r} (the width the graph's "
        f"vectors were written at), got {model!r}"
    )

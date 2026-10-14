"""Summary claims must point at collected evidence, or say they are unverified.

The synthesis summary is free text. Each sentence is checked for evidence
references (E1, E2, ...): a sentence citing evidence that was never
collected is dropped, a sentence citing nothing is kept but marked
"Unverified:", and a sentence that already says "Unknown:" stays as it is.
"""

import re
from dataclasses import dataclass

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_REF = re.compile(r"\bE(\d{1,3})\b")
UNVERIFIED = "Unverified: "
_OPEN = ("unknown:", "unverified:")


@dataclass(frozen=True)
class Grounded:
    summary: str
    dropped: int
    unverified: int


def ground_summary(summary: str, known: set[str]) -> Grounded:
    kept: list[str] = []
    dropped = unverified = 0
    for sentence in (s.strip() for s in _SENTENCE.split(summary.strip())):
        if not sentence:
            continue
        refs = {f"E{n}" for n in _REF.findall(sentence)}
        if refs - known:
            dropped += 1
            continue
        if not refs and not sentence.lower().startswith(_OPEN):
            unverified += 1
            sentence = UNVERIFIED + sentence
        kept.append(sentence)
    return Grounded(" ".join(kept), dropped, unverified)

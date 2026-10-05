"""Cleans user-written ticket text and normalizes fire/EMS synonyms.

Users write tickets from phones and email, so descriptions carry greetings, signatures,
forwarded headers and typos. This strips the junk and maps device/system names onto one
vocabulary ("truck laptop", "CF-33", "tuffbook" -> toughbook) before embedding.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from rapidfuzz import fuzz, process

# Whole lines that are email noise and carry no information about the problem.
_JUNK_LINE = re.compile(
    r"""^(
        (caution|warning|external)\b.*\b(outside|external|originated)\b.* |   # external-sender banners
        \[?external\]?:?\s*$ |
        sent\ from\ my\ .* |
        get\ outlook\ for\ .* |
        (from|sent|to|cc|bcc|date|importance):\s.* |                            # forwarded headers
        -{2,}\s*(original|forwarded)\ message\s*-{2,} |
        _{5,} |
        on\ .{5,80}\ wrote:\s* |
        .*\bconfidential(ity)?\b.*\b(intended|recipient)\b.* |
        (hi|hello|hey|good\ (morning|afternoon|evening)|greetings)(\s*[,!.]|(\s+\w+){1,2}\s*[,!])?\s*   # "Hi team,"
    )$""",
    re.IGNORECASE | re.VERBOSE,
)
# A sign-off starts the signature block, which runs to the next blank line.
_SIGN_OFF = re.compile(
    r"^(thanks|thank\ you|thx|regards|best\ regards|kind\ regards|respectfully|v/r|sincerely|cheers)\b[\w\s]{0,15}[,!.]?\s*$",
    re.IGNORECASE | re.VERBOSE,
)
_SIGNATURE_LINE = re.compile(r"\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}|\S+@\S+\.\w+")
_SIGNATURE_MAX_LEN = 60
_LEADING_GREETING = re.compile(r"^(hi|hello|hey)( (team|all|it|there|guys))?[,!]\s*", re.IGNORECASE)
_SUBJECT = re.compile(r"^subject:\s*((re|fw|fwd):\s*)*", re.IGNORECASE)
_REPLY_PREFIX = re.compile(r"^((re|fw|fwd):\s*)+", re.IGNORECASE)

_CONTRACTIONS = {
    "cant": "can't", "cannot": "can't", "wont": "won't", "dont": "don't", "doesnt": "doesn't",
    "isnt": "isn't", "didnt": "didn't", "wouldnt": "wouldn't", "couldnt": "couldn't",
    "arent": "aren't", "wasnt": "wasn't", "havent": "haven't", "aint": "isn't",
}
_CONTRACTION_RE = re.compile(r"\b(" + "|".join(_CONTRACTIONS) + r")\b")
_FUZZY_TOKEN = re.compile(r"\b[a-z]{5,}\b")


def clean_text(text: str) -> str:
    """Removes email junk, lowercases, and collapses whitespace."""
    text = (text or "").replace("’", "'").replace("‘", "'").replace("\r\n", "\n")
    kept: list[str] = []
    in_signature = False
    seen: set[str] = set()
    for raw in text.split("\n"):
        line = raw.strip().lstrip(">").strip()
        if not line:
            in_signature = False
            continue
        if in_signature or _JUNK_LINE.match(line):
            continue
        if len(line) < _SIGNATURE_MAX_LEN and _SIGNATURE_LINE.search(line):
            continue
        if _SIGN_OFF.match(line):
            in_signature = True
            continue
        line = _SUBJECT.sub("", line)
        line = _REPLY_PREFIX.sub("", line)
        line = _LEADING_GREETING.sub("", line)
        key = line.lower()
        if not line or key in seen:  # quoted replies repeat earlier lines
            continue
        seen.add(key)
        kept.append(line)
    out = " ".join(kept).lower()
    out = _CONTRACTION_RE.sub(lambda m: _CONTRACTIONS[m.group(1)], out)
    return re.sub(r"\s+", " ", out).strip()


@dataclass
class Processed:
    clean_text: str
    normalized_text: str
    concepts: set[str] = field(default_factory=set)


class Normalizer:
    def __init__(self, synonyms: dict[str, list[str]], fuzzy_threshold: float = 90):
        self.fuzzy_threshold = fuzzy_threshold
        self._variant_to_concept: dict[str, str] = {}
        for concept, variants in synonyms.items():
            for v in [concept, *variants]:
                self._variant_to_concept[v.lower().replace("_", " ")] = concept
        # Longest first so "computer aided dispatch" wins over "dispatch".
        alternation = "|".join(
            re.escape(v) for v in sorted(self._variant_to_concept, key=len, reverse=True)
        )
        self._phrase_re = re.compile(rf"(?<![\w'-])({alternation})(?![\w'-])")
        self._fuzzy_choices = [v for v in self._variant_to_concept if v.isalpha() and len(v) >= 5]

    @classmethod
    def from_file(cls, path: str | Path, fuzzy_threshold: float = 90) -> "Normalizer":
        with open(path, encoding="utf-8") as f:
            return cls(yaml.safe_load(f) or {}, fuzzy_threshold)

    @staticmethod
    def _label(concept: str) -> str:
        return concept.replace("_", " ")

    def process(self, text: str) -> Processed:
        cleaned = clean_text(text)
        concepts: set[str] = set()

        def replace_phrase(m: re.Match) -> str:
            concept = self._variant_to_concept[m.group(1)]
            concepts.add(concept)
            return self._label(concept)

        normalized = self._phrase_re.sub(replace_phrase, cleaned)

        def replace_typo(m: re.Match) -> str:
            word = m.group(0)
            if word in self._variant_to_concept:
                return word
            hit = process.extractOne(
                word, self._fuzzy_choices, scorer=fuzz.ratio, score_cutoff=self.fuzzy_threshold
            )
            if not hit:
                return word
            concept = self._variant_to_concept[hit[0]]
            concepts.add(concept)
            return self._label(concept)

        normalized = _FUZZY_TOKEN.sub(replace_typo, normalized)
        return Processed(clean_text=cleaned, normalized_text=normalized, concepts=concepts)

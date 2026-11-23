"""Keyword retrieval (BM25) over the knowledge base, with a confidence score.

Pure Python on purpose: the knowledge base is a dozen short documents, so an embedding model would add
a dependency and an API call without improving results much. See README "Design decisions".
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass

from .knowledge import Document

log = logging.getLogger("pawpal.retriever")

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do", "does", "for", "from", "get",
    "has", "have", "how", "i", "if", "in", "is", "it", "its", "me", "my", "of", "on", "or", "our",
    "should", "so", "that", "the", "their", "them", "there", "they", "this", "to", "too", "up", "was",
    "we", "what", "when", "where", "which", "who", "why", "will", "with", "you", "your", "need", "needs",
    "much", "many", "any", "about", "day", "days", "pet", "pets", "dog", "dogs", "cat", "cats", "more",
    "some", "than", "then", "would", "could", "also", "just", "one", "every", "each", "very", "most",
    "often", "much", "ok", "okay", "want", "help", "please", "tell", "know", "him", "her", "his", "she",
    "he", "be", "been", "being", "am", "not", "no", "yes", "all", "out", "into", "over", "under", "again",
}


def stem(word: str) -> str:
    """Very small suffix stripper so 'walks', 'walking' and 'walk' match."""
    for suffix in ("ings", "ing", "ies", "es", "ed", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            if suffix == "ies":
                word += "y"
            break
    if len(word) > 3 and word[-1] == word[-2]:  # 'scoopp' style doubles from 'scooping' etc.
        word = word[:-1]
    return word


def tokenize(text: str) -> list[str]:
    """Lowercase, split on non-letters, drop stopwords, stem."""
    out = []
    for word in re.findall(r"[a-z]+", text.lower()):
        if word in STOPWORDS or len(word) < 2:
            continue
        word = stem(word)
        if word not in STOPWORDS:  # catches 'getting' -> 'get'
            out.append(word)
    return out


@dataclass
class Hit:
    doc: Document
    score: float


@dataclass
class Retrieval:
    """The result of one search: ranked hits plus how well the query is covered."""

    query: str
    hits: list[Hit]
    confidence: float  # 0..1, IDF-weighted share of query terms found in the top document
    unknown_terms: list[str]

    @property
    def docs(self) -> list[Document]:
        return [h.doc for h in self.hits]

    @property
    def ids(self) -> list[str]:
        return [h.doc.id for h in self.hits]


class Retriever:
    """BM25 ranking with a species filter."""

    def __init__(self, docs: list[Document], k1: float = 1.5, b: float = 0.75):
        if not docs:
            raise ValueError("Retriever needs at least one document")
        self.docs = docs
        self.k1, self.b = k1, b
        self._tf = [Counter(tokenize(d.search_text)) for d in docs]
        self._len = [sum(tf.values()) for tf in self._tf]
        self._avg_len = sum(self._len) / len(self._len)
        df = Counter(term for tf in self._tf for term in tf)
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        # A word the knowledge base has never seen is treated as the rarest possible word: if the
        # question hinges on it, we cannot answer it, so it should pull confidence down hard.
        self._unknown_idf = math.log(1 + (n + 0.5) / 0.5)

    def _bm25(self, i: int, terms: list[str]) -> float:
        tf, length = self._tf[i], self._len[i]
        score = 0.0
        for t in terms:
            f = tf.get(t, 0)
            if f:
                score += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * length / self._avg_len))
        return score

    def search(self, query: str, species: str | None = None, top_k: int = 3) -> Retrieval:
        terms = list(dict.fromkeys(tokenize(query)))  # unique, order kept
        if not terms:
            log.info("retrieve query=%r -> no searchable words", query)
            return Retrieval(query, [], 0.0, [])
        scored = [
            Hit(doc, self._bm25(i, terms))
            for i, doc in enumerate(self.docs)
            if species is None or doc.applies_to(species)
        ]
        hits = sorted((h for h in scored if h.score > 0), key=lambda h: h.score, reverse=True)[:top_k]

        unknown = [t for t in terms if t not in self.idf]
        confidence = 0.0
        if hits:
            top_terms = self._tf[self.docs.index(hits[0].doc)]
            weight = {t: self.idf.get(t, self._unknown_idf) for t in terms}
            matched = sum(w for t, w in weight.items() if t in top_terms)
            confidence = round(matched / sum(weight.values()), 2)
        log.info(
            "retrieve query=%r species=%s -> %s confidence=%.2f unknown=%s",
            query, species, [(h.doc.id, round(h.score, 2)) for h in hits], confidence, unknown,
        )
        return Retrieval(query, hits, confidence, unknown)

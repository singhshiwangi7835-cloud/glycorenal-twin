"""Tiny retrieval (RAG): TF-IDF over the guideline notes in data/guidelines/*.md.

Each note is split into chunks (one bullet or paragraph each); the top 3 chunks for a query are
added to the prompt with the note's title and source line, so the assistant can cite them.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

GUIDES = Path(__file__).resolve().parents[2] / "data" / "guidelines"


@lru_cache
def _index():
    chunks = []
    for path in sorted(GUIDES.glob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        title = lines[0].lstrip("# ").strip() if lines else path.stem
        source = next((ln.replace("Source:", "").split("Status:")[0].strip()
                       for ln in lines if ln.startswith("Source:")), "")
        for ln in lines[1:]:
            text = ln.strip().lstrip("- ").strip()
            if text and not text.startswith("Source:"):
                chunks.append({"title": title, "source": source, "file": path.name, "text": text})
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
    matrix = vec.fit_transform([f"{c['title']} {c['text']}" for c in chunks]) if chunks else None
    return chunks, vec, matrix


def retrieve(query: str, k: int = 3) -> list[dict]:
    chunks, vec, matrix = _index()
    if not chunks or not query.strip():
        return []
    scores = cosine_similarity(vec.transform([query]), matrix)[0]
    best = scores.argsort()[::-1][:k]
    return [{**chunks[i], "score": round(float(scores[i]), 3)} for i in best if scores[i] > 0]

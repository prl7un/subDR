"""로컬 전용 RAG(검색 증강) 모듈.

강의자료(PDF)는 저작권이 있는 자료라 원문을 외부로 전송하지 않는다. build_rag_index.py가
텍스트만 미리 추출해 rag_index.json으로 저장해두면, 이 모듈은 그 인덱스를 로드해 TF-IDF
(문자 n-gram) 기반으로 완전히 로컬에서 검색한다 — 신경망 임베딩 모델이나 외부 API가
전혀 필요 없어 가볍고 빠르며, 이 컴퓨터 밖으로 나가는 데이터가 없다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

INDEX_PATH = Path(__file__).parent / "rag_index.json"
DEFAULT_TOP_K = 2
DEFAULT_MIN_SCORE = 0.08


@dataclass
class Chunk:
    topic: str
    source: str
    page: int
    text: str


class RagIndex:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.vectorizer = None
        self.matrix = None
        if chunks:
            self.vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
            self.matrix = self.vectorizer.fit_transform([c.text for c in chunks])

    def retrieve(
        self, query: str, topic: str, top_k: int = DEFAULT_TOP_K, min_score: float = DEFAULT_MIN_SCORE
    ) -> list[Chunk]:
        if not self.chunks or not query.strip():
            return []
        idxs = [i for i, c in enumerate(self.chunks) if c.topic == topic]
        if not idxs:
            return []
        q_vec = self.vectorizer.transform([query])
        sims = cosine_similarity(q_vec, self.matrix[idxs])[0]
        ranked = sorted(zip(idxs, sims), key=lambda pair: pair[1], reverse=True)
        return [self.chunks[i] for i, score in ranked[:top_k] if score >= min_score]


_index: RagIndex | None = None


def load_index() -> RagIndex:
    global _index
    if _index is not None:
        return _index
    if not INDEX_PATH.exists():
        _index = RagIndex([])
        return _index
    data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    chunks = [Chunk(**c) for c in data.get("chunks", [])]
    _index = RagIndex(chunks)
    return _index


def is_available() -> bool:
    return len(load_index().chunks) > 0


def retrieve(query: str, topic: str, top_k: int = DEFAULT_TOP_K) -> list[Chunk]:
    return load_index().retrieve(query, topic, top_k=top_k)

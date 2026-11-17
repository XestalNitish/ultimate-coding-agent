"""RAG package — re-exports from retriever for backward compatibility.

main.py, pipeline.py, selftest.py sab `import rag` karke
rag.libraries(), rag.search(), rag.get_store(), rag.embed_docs() use karte hain.
Ye sab functions ab rag/retriever.py se aate hain.
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import List, Optional

import numpy as np

logger = logging.getLogger("rag")

# --------------------------------------------------------------------------- #
# Config (can be overridden by tests via direct assignment)
# --------------------------------------------------------------------------- #
import config as C

_EMBED_MODEL = None


def _get_embed_model():
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        from fastembed import TextEmbedding
        _EMBED_MODEL = TextEmbedding(
            model_name=C.EMBED_MODEL,
            cache_dir=str(C.MODELS_DIR / "embed"),
        )
    return _EMBED_MODEL


# --------------------------------------------------------------------------- #
# VectorStore — lightweight numpy-based store (no external DB needed)
# --------------------------------------------------------------------------- #
class VectorStore:
    """Simple in-memory vector store backed by numpy + pickle."""

    def __init__(self, path: Path):
        self.path = path
        self.chunks: list[dict] = []
        self.vecs: np.ndarray = np.empty((0, 384), dtype="float32")
        self.state: dict = {}  # file_path -> signature (for incremental ingest)

    def add(self, chunks: list[dict], vecs: np.ndarray):
        self.chunks.extend(chunks)
        self.vecs = np.vstack([self.vecs, vecs]) if len(self.vecs) else vecs

    def remove_source(self, source: str):
        keep = [i for i, c in enumerate(self.chunks) if c.get("source") != source]
        self.chunks = [self.chunks[i] for i in keep]
        self.vecs = self.vecs[keep] if keep else np.empty((0, self.vecs.shape[1]), dtype="float32")

    def libraries(self) -> list[str]:
        return sorted({c["library"] for c in self.chunks})

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "wb") as f:
            pickle.dump({"chunks": self.chunks, "vecs": self.vecs, "state": self.state}, f)

    @classmethod
    def load(cls, path: Path) -> "VectorStore":
        store = cls(path)
        if path.exists():
            with open(path, "rb") as f:
                data = pickle.load(f)
            store.chunks = data["chunks"]
            store.vecs = data["vecs"]
            store.state = data.get("state", {})
        return store


# --------------------------------------------------------------------------- #
# Module-level store (lazy)
# --------------------------------------------------------------------------- #
_store: Optional[VectorStore] = None


def get_store(reload: bool = False) -> VectorStore:
    global _store
    if _store is None or reload:
        _store = VectorStore.load(C.DB_DIR / "rag_store.pkl")
    return _store


def libraries() -> list[str]:
    return get_store().libraries()


# --------------------------------------------------------------------------- #
# Embedding
# --------------------------------------------------------------------------- #
def embed_docs(texts: list[str]) -> np.ndarray:
    model = _get_embed_model()
    return np.array(list(model.embed(texts)), dtype="float32")


def embed_query(text: str) -> np.ndarray:
    model = _get_embed_model()
    q = C.QUERY_PREFIX + text
    return np.array(list(model.embed([q])), dtype="float32")[0]


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
def search(query: str, k: int = 3, library: Optional[str] = None) -> list[dict]:
    """Cosine-similarity search over the vector store."""
    store = get_store()
    if not store.chunks:
        return []
    qv = embed_query(query)
    # cosine similarity (vectors are L2-normalised by fastembed)
    sims = store.vecs @ qv
    if library:
        mask = np.array([c["library"] == library for c in store.chunks])
        sims = np.where(mask, sims, -1.0)
    top = np.argsort(sims)[::-1][:k]
    return [dict(store.chunks[i], score=float(sims[i])) for i in top if sims[i] > 0]

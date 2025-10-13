# retriever.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import numpy as np

try:
    from .embedder import GGUFEmbedder
except ImportError:  # fallback when module executed as script
    from embedder import GGUFEmbedder

@dataclass
class KBItem:
    id: str
    text: str
    source: str
    vec: Optional[np.ndarray] = None  # diisi saat indexing

class MiniKB:
    """
    Knowledge base mini (in-memory) + pre-embedding dokumen.
    """
    def __init__(self, items: List[KBItem], embedder: GGUFEmbedder):
        self.items = items
        self.embedder = embedder

    def build_index(self) -> None:
        texts = [it.text for it in self.items]
        vecs = self.embedder.embed_batch(texts, normalize=True)
        for it, v in zip(self.items, vecs):
            it.vec = v

    @staticmethod
    def cosine_sim(q: np.ndarray, d: np.ndarray) -> float:
        # vektor sudah normalized => cukup dot product
        return float(np.dot(q, d))

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        qv = self.embedder.embed_one(query, normalize=True)
        scored: List[Dict[str, Any]] = []
        for it in self.items:
            if it.vec is None:
                continue
            score = self.cosine_sim(qv, it.vec)
            scored.append({
                "id": it.id,
                "text": it.text,
                "source": it.source,
                "score": score,
            })
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

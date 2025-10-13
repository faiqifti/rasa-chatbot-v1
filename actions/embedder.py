# # embedder.py
# from __future__ import annotations
# from typing import List, Iterable
# import numpy as np
# from llama_cpp import Llama

# model_path = "/models/embeddinggemma-300M-Q8_0.gguf"

# class GGUFEmbedder:
#     """
#     Membuat embedding menggunakan model GGUF via llama-cpp-python.
#     Cocok untuk model embedding seperti embeddinggemma-300M-GGUF.
#     """
#     def __init__(self, model_path: str, n_threads: int = 4, n_ctx: int = 2048):
#         # embedding=True penting agar endpoint create_embedding aktif
#         self.llm = Llama(
#             model_path=model_path,
#             embedding=True,
#             n_threads=n_threads,
#             n_ctx=n_ctx,
#             logits_all=False,
#         )

#     @staticmethod
#     def _normalize(v: np.ndarray) -> np.ndarray:
#         n = np.linalg.norm(v)
#         return v / n if n > 0 else v

#     def embed_one(self, text: str, normalize: bool = True) -> np.ndarray:
#         """
#         Embedding satu teks (query atau dokumen).
#         """
#         # llama-cpp >=0.2.x: create_embedding(input="...")
#         out = self.llm.create_embedding(input=text)
#         vec = np.array(out["data"][0]["embedding"], dtype=np.float32)
#         return self._normalize(vec) if normalize else vec

#     def embed_batch(self, texts: Iterable[str], normalize: bool = True) -> List[np.ndarray]:
#         """
#         Embedding batch teks (lebih cepat untuk banyak dokumen).
#         """
#         out = self.llm.create_embedding(input=list(texts))
#         vecs = [np.array(d["embedding"], dtype=np.float32) for d in out["data"]]
#         if normalize:
#             vecs = [self._normalize(v) for v in vecs]
#         return vecs

# actions/embedder.py
from __future__ import annotations
import os, numpy as np
from typing import Optional
from llama_cpp import Llama

class GGUFEmbedder:
    def __init__(self, model_path: str, threads: Optional[int] = None, n_threads: Optional[int] = None):
        if not os.path.exists(model_path):
            raise ValueError(f"Model path does not exist: {model_path}")
        # normalize thread arguments (support both `threads` & `n_threads`)
        if threads is None:
            threads = n_threads if n_threads is not None else 4
        # Strict, conservative init for encoder-only models
        self.llm = Llama(
            model_path=model_path,
            embedding=True,      # <-- MUST be True
            n_ctx=2048,
            n_threads=threads,
            n_batch=64,          # small and safe; we'll avoid batch anyway
            n_gpu_layers=0,      # force CPU (avoid Metal path)
            n_seq_max=1,         # <-- important for embeddings
            logits_all=False,
            vocab_only=False,
            use_mmap=True,
            use_mlock=False,
        )

    @staticmethod
    def _norm(v: np.ndarray) -> np.ndarray:
        n = np.linalg.norm(v)
        return v / n if n > 0 else v

    def embed_one(self, text: str, normalize: bool = True) -> np.ndarray:
        # guard: empty text can crash some builds
        txt = text if text and text.strip() else "[EMPTY]"
        out = self.llm.create_embedding(input=txt)
        vec = np.array(out["data"][0]["embedding"], dtype=np.float32)
        return self._norm(vec) if normalize else vec

    def embed_batch(self, texts, normalize: bool = True):
        # SAFEST PATH: loop per item (avoid batch)
        vecs = [self.embed_one(t, normalize) for t in texts]
        return vecs

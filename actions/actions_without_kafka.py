# # actions.py
# import os
# from pathlib import Path
# from typing import Optional, List, Dict, Any

# # Rasa SDK
# from rasa_sdk import Action, Tracker
# from rasa_sdk.executor import CollectingDispatcher

# # Local Helper Modules
# from .embedder import GGUFEmbedder
# from .ranker import select_top1, NoAnswerError
# from .redis_cache import get_from_cache, set_to_cache, create_qdrant_cache_key

# # Qdrant Client
# from qdrant_client import QdrantClient
# from qdrant_client.http.models import Filter, FieldCondition, MatchValue

# # Environment Loading
# from dotenv import load_dotenv
# load_dotenv()

# # ===== Konfigurasi dasar =====
# BASE_DIR = Path(__file__).resolve().parent.parent
# MODELS_DIR = BASE_DIR / "models"

# # ===== ENV / Konfigurasi =====
# ENV_MODEL_PATH = os.getenv("EMBED_MODEL_PATH")
# ENV_THRESHOLD = float(os.getenv("RAG_THRESHOLD", "0.35"))
# ENV_TOPK = int(os.getenv("RAG_TOPK", "5"))
# ENV_THREADS = int(os.getenv("EMBED_THREADS", "4"))

# QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
# QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
# QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "kb_documents")

# # ===== Candidate model paths =====
# def _candidate_model_paths() -> List[Path]:
#     candidates: List[Path] = []
#     if ENV_MODEL_PATH:
#         candidates.append(Path(ENV_MODEL_PATH))
#     candidates.extend([
#         MODELS_DIR / "bge-m3-q4_k_m.gguf",
#         MODELS_DIR / "gte-multilingual-base-q4_k_m.gguf",
#         MODELS_DIR / "nomic-embed-text-v1.5.Q2_K.gguf",
#     ])
#     return candidates

# # ===== Lazy init embedder =====
# _EMBEDDER: Optional[GGUFEmbedder] = None
# _EMBED_MODEL_PATH: Optional[str] = None

# def _init_embedder() -> GGUFEmbedder:
#     """Load model embedding GGUF sekali (singleton)."""
#     global _EMBEDDER, _EMBED_MODEL_PATH
#     if _EMBEDDER is not None:
#         return _EMBEDDER

#     errors = []
#     for candidate in _candidate_model_paths():
#         resolved = candidate.expanduser()
#         if not resolved.exists():
#             errors.append(f"{resolved} (missing)")
#             continue
#         try:
#             selected = resolved.resolve()
#             emb = GGUFEmbedder(str(selected), threads=ENV_THREADS)
#             _EMBEDDER = emb
#             _EMBED_MODEL_PATH = str(selected)
#             return emb
#         except Exception as exc:
#             errors.append(f"{resolved} ({exc})")

#     raise RuntimeError(
#         "Gagal memuat model embedding GGUF.\n"
#         "Solusi: set ENV EMBED_MODEL_PATH atau letakkan file model di models/.\n"
#         "Kandidat yang dicoba:\n - " + "\n - ".join(errors)
#     )

# # ===== Qdrant client (lazy) =====
# _QDRANT: Optional[QdrantClient] = None

# def _get_qdrant() -> QdrantClient:
#     global _QDRANT
#     if _QDRANT is not None:
#         return _QDRANT
#     _QDRANT = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
#     return _QDRANT

# # ===== Helper: search ke Qdrant with Caching =====
# def _search_qdrant(query: str, top_k: int) -> List[Dict[str, Any]]:
#     """
#     Search Qdrant for a query, with Redis caching handled by the redis_cache module.
#     """
#     print(f"\n[LOG] Executing search for query: {query!r}")
#     # 1. Use the new module to create and check the cache key
#     cache_key = create_qdrant_cache_key(query)
#     cached_result = get_from_cache(cache_key)
#     if cached_result is not None:
#         print("[LOG] Cache HIT. Returning result from Redis.")
#         return cached_result
    
#     print("[LOG] Cache MISS. Proceeding to generate embedding and search Qdrant.")
#     # 2. If not in cache, perform the expensive operations
#     emb = _embedder.embed_one(query).tolist()
#     qdrant_client = _get_qdrant()

#     q_filter: Optional[Filter] = None
#     results = qdrant_client.search(
#         collection_name=QDRANT_COLLECTION,
#         query_vector=emb,
#         limit=top_k,
#         query_filter=q_filter,
#         with_payload=True,
#         with_vectors=False,
#     )
    
#     out: List[Dict[str, Any]] = []
#     for r in results:
#         payload = r.payload or {}
#         out.append({
#             "id": payload.get("kb_id") or payload.get("id") or r.id,
#             "text": payload.get("text") or "",
#             "source": payload.get("source") or "",
#             "score": float(r.score),
#         })

#     # 3. Store the result in the cache using the new module
#     print(f"[LOG] Storing new result in Redis cache with key: {cache_key!r}")
#     set_to_cache(cache_key, out)

#     return out

# # ===== Init (ringan, tidak melakukan ingest) =====
# _embedder = _init_embedder()

# # ===== Actions =====
# class ActionRetrieveTop1(Action):
#     def name(self) -> str:
#         return "action_retrieve_top1"

#     def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict):
#         q = (tracker.latest_message.get("text") or "").strip()
#         print(f"\n--- Triggered {self.name()} for user message: {q!r} ---")
#         if not q:
#             dispatcher.utter_message(text="Pertanyaan tidak terbaca.")
#             return []

#         try:
#             results = _search_qdrant(q, top_k=ENV_TOPK)
#             print(f"[DBG] query={q!r} qdrant_top1={results[:1]}")
#         except Exception as exc:
#             print(f"[ERROR] An exception occurred during search: {exc}")
#             dispatcher.utter_message(text=f"Gagal mencari di Qdrant: {exc}")
#             return []

#         try:
#             top1 = select_top1(results, threshold=ENV_THRESHOLD)
#             dispatcher.utter_message(
#                 text=f"{top1['text']}\n\nSumber: {top1['source']} (score={top1['score']:.2f})"
#             )
#         except NoAnswerError as e:
#             dispatcher.utter_message(
#                 text=f"Maaf, belum ada jawaban yang cocok di knowledge base. ({e})"
#             )
#         return []

# class ActionEmbedderInfo(Action):
#     def name(self) -> str:
#         return "action_embedder_info"

#     def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict):
#         print(f"\n--- Triggered {self.name()} ---")
#         try:
#             client = _get_qdrant()
#             cnt = client.count(QDRANT_COLLECTION, exact=False).count
#         except Exception:
#             cnt = None

#         dispatcher.utter_message(
#             text=(
#                 "Embedder siap.\n"
#                 f"Model: {_EMBED_MODEL_PATH or '-'}\n"
#                 f"Threads: {ENV_THREADS}\n"
#                 f"Top-K: {ENV_TOPK}, Threshold: {ENV_THRESHOLD}\n"
#                 f"Qdrant: {QDRANT_URL}, Collection: {QDRANT_COLLECTION}, Points: {cnt if cnt is not None else '?'}"
#             )
#         )
#         return []
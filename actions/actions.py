# # # This files contains your custom actions which can be used to run
# # # custom Python code.
# # #
# # # See this guide on how to implement these action:
# # # https://rasa.com/docs/rasa/custom-actions


# # # This is a simple example for a custom action which utters "Hello World!"

# # # from typing import Any, Text, Dict, List
# # #
# # # from rasa_sdk import Action, Tracker
# # # from rasa_sdk.executor import CollectingDispatcher
# # #
# # #
# # # class ActionHelloWorld(Action):
# # #
# # #     def name(self) -> Text:
# # #         return "action_hello_world"
# # #
# # #     def run(self, dispatcher: CollectingDispatcher,
# # #             tracker: Tracker,
# # #             domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
# # #
# # #         dispatcher.utter_message(text="Hello World!")
# # #
# # #         return []

# # from rasa_sdk import Action, Tracker
# # from rasa_sdk.executor import CollectingDispatcher

# # class ActionSapa(Action):
# #     def name(self): return "action_sapa"

# #     def run(self, dispatcher, tracker, domain):
# #         dispatcher.utter_message(text="Halo! Ini chatbot local pengembangan KamBRIng.")
# #         return []

# # actions.py
# from __future__ import annotations
# from collections import Counter
# from math import sqrt
# import re

# from rasa_sdk import Action, Tracker
# from rasa_sdk.executor import CollectingDispatcher


# # --- Embedding dummy: bag-of-words + cosine -------------------------------
# TOKEN_RE = re.compile(r"[A-Za-zÀ-ž0-9_]+", re.UNICODE)

# def tokenize(text: str):
#     return [t.lower() for t in TOKEN_RE.findall(text or "")]

# def embed_bow(text: str) -> Counter:
#     # vektor berupa Counter frekuensi token
#     return Counter(tokenize(text))

# def cosine(a: Counter, b: Counter) -> float:
#     if not a or not b:
#         return 0.0
#     # dot
#     keys = set(a) & set(b)
#     dot = sum(a[k] * b[k] for k in keys)
#     # norms
#     na = sqrt(sum(v * v for v in a.values()))
#     nb = sqrt(sum(v * v for v in b.values()))
#     return (dot / (na * nb)) if na and nb else 0.0


# # --- Knowledge base mini (2-3 item) ---------------------------------------
# KB = [
#     {
#         "id": "faq#limit_transfer",
#         "text": "Limit transfer harian rekening reguler adalah Rp25 juta.",
#         "source": "kb/transfer.md",
#     },
#     {
#         "id": "faq#biaya_admin",
#         "text": "Biaya administrasi bulanan rekening reguler adalah Rp7.500.",
#         "source": "kb/biaya.md",
#     },
#     {
#         "id": "faq#blokir_kartu",
#         "text": "Kartu ATM yang hilang dapat diblokir melalui call center atau cabang terdekat.",
#         "source": "kb/kartu.md",
#     },
# ]

# # precompute embeddings (dummy)
# for item in KB:
#     item["vec"] = embed_bow(item["text"])


# SIM_THRESHOLD = 0.25  # ambang kesesuaian minimal (atur sesuai kebutuhan)


# class ActionRetrieveTop1(Action):
#     def name(self) -> str:
#         return "action_retrieve_top1"

#     def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict):
#         query = (tracker.latest_message.get("text") or "").strip()
#         if not query:
#             dispatcher.utter_message(text="Pertanyaannya apa ya?")
#             return []

#         qv = embed_bow(query)

#         # cari top-1
#         best = None
#         best_score = -1.0
#         for item in KB:
#             score = cosine(qv, item["vec"])
#             if score > best_score:
#                 best, best_score = item, score

#         if not best or best_score < SIM_THRESHOLD:
#             dispatcher.utter_message(text="Maaf, belum ada jawaban yang cocok di knowledge base.")
#             return []

#         jawab = f"{best['text']}\n\nSumber: {best['source']} (skor={best_score:.2f})"
#         dispatcher.utter_message(text=jawab)
#         return []

# actions.py (ringkas)
import os
from pathlib import Path
from typing import List, Optional
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from .embedder import GGUFEmbedder
from .retriever import MiniKB, KBItem
from .ranker import select_top1, NoAnswerError

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE_DIR, "models", "nomic-embed-text-v1.5.Q2_K.gguf")  # or your nomic gguf

_embedder = GGUFEmbedder(MODEL_PATH, threads=4)

def _candidate_model_paths() -> List[Path]:
    """Kembalikan daftar kandidat path model embedding (prioritas ENV)."""
    env_path = os.getenv("EMBED_MODEL_PATH")
    base_dir = Path(__file__).resolve().parent.parent / "models"
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend([
        base_dir / "nomic-embed-text-v1.5.Q2_K.gguf",
        base_dir / "embeddinggemma-300M-Q8_0.gguf",
        base_dir / "embeddinggemma-300M.Q4_0.gguf",
    ])
    return candidates

_EMBED_MODEL_PATH: Optional[str] = None

def _init_embedder() -> GGUFEmbedder:
    """Coba load model pertama yang valid; beri pesan jelas bila gagal."""
    global _EMBED_MODEL_PATH
    errors = []
    for candidate in _candidate_model_paths():
        resolved = candidate.expanduser()
        if not resolved.exists():
            errors.append(f"{resolved} (missing)")
            continue
        try:
            selected = resolved.resolve()
            embedder = GGUFEmbedder(str(selected), n_threads=4)
            global _EMBED_MODEL_PATH
            _EMBED_MODEL_PATH = str(selected)
            return embedder
        except Exception as exc:
            errors.append(f"{resolved} ({exc})")
    raise RuntimeError(
        "Gagal memuat model embedding GGUF. Set variabel lingkungan EMBED_MODEL_PATH "
        "atau letakkan file `.gguf` di folder models/. Dicoba: " + "; ".join(errors)
    )

# Init sekali saat action server start
_embedder = _init_embedder()
_kb = MiniKB(
    items=[
        KBItem("faq#limit", "Limit transfer harian rekening reguler adalah Rp25 juta.", "kb/transfer.md"),
        KBItem("faq#admin", "Biaya administrasi bulanan rekening reguler adalah Rp7.500.", "kb/biaya.md"),
        KBItem("faq#blokir","Kartu ATM hilang dapat diblokir via call center atau cabang terdekat.","kb/kartu.md"),
    ],
    embedder=_embedder,
)
_kb.build_index()

class ActionRetrieveTop1(Action):
    def name(self): return "action_retrieve_top1"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict):
        q = (tracker.latest_message.get("text") or "").strip()
        if not q:
            dispatcher.utter_message(text="Pertanyaan tidak terbaca.")
            return []
        results = _kb.search(q, top_k=5)
        try:
            top1 = select_top1(results, threshold=0.35)
            dispatcher.utter_message(text=f"{top1['text']}\n\nSumber: {top1['source']} (score={top1['score']:.2f})")
        except NoAnswerError as e:
            dispatcher.utter_message(text=f"Maaf, belum ada jawaban yang cocok di knowledge base. ({e})")
        return []

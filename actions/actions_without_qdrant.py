import os
from pathlib import Path
from typing import List, Optional
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

from .embedder import GGUFEmbedder
from .retriever import MiniKB, KBItem
from .ranker import select_top1, NoAnswerError

# ===== Konfigurasi dasar =====
BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"

# Ambil dari ENV bila ada
ENV_MODEL_PATH = os.getenv("EMBED_MODEL_PATH")  # path absolut/relatif ke .gguf
ENV_THRESHOLD = float(os.getenv("RAG_THRESHOLD", "0.35"))
ENV_TOPK = int(os.getenv("RAG_TOPK", "5"))
ENV_THREADS = int(os.getenv("EMBED_THREADS", "4"))

# ===== Kandidat model =====
def _candidate_model_paths() -> List[Path]:
    """
    Kembalikan kandidat path model embedding (prioritas ENV, lalu beberapa nama umum).
    Urutan penting: yang lebih 'pasti cocok' diletakkan lebih awal.
    """
    candidates: List[Path] = []
    if ENV_MODEL_PATH:
        candidates.append(Path(ENV_MODEL_PATH))

    # Tambahkan model yang sudah terbukti di percobaanmu
    candidates.extend([
        MODELS_DIR / "bge-m3-q4_k_m.gguf",
        # fallback lain (kalau kamu punya filenya):
        MODELS_DIR / "gte-multilingual-base-q4_k_m.gguf",  # contoh; pastikan file nyata jika mau
        MODELS_DIR / "nomic-embed-text-v1.5.Q2_K.gguf",
        MODELS_DIR / "embeddinggemma-300M.Q4_0.gguf",
        MODELS_DIR / "embeddinggemma-300M-Q8_0.gguf",
    ])
    return candidates

# ===== Lazy init embedder =====
_EMBEDDER: Optional[GGUFEmbedder] = None
_EMBED_MODEL_PATH: Optional[str] = None

def _init_embedder() -> GGUFEmbedder:
    """
    Coba load model pertama yang valid; beri pesan jelas bila gagal.
    Hanya inisialisasi sekali (singleton sederhana).
    """
    global _EMBEDDER, _EMBED_MODEL_PATH
    if _EMBEDDER is not None:
        return _EMBEDDER

    errors = []
    for candidate in _candidate_model_paths():
        resolved = candidate.expanduser()
        if not resolved.exists():
            errors.append(f"{resolved} (missing)")
            continue
        try:
            selected = resolved.resolve()
            emb = GGUFEmbedder(str(selected), threads=ENV_THREADS)
            _EMBEDDER = emb
            _EMBED_MODEL_PATH = str(selected)
            return emb
        except Exception as exc:
            errors.append(f"{resolved} ({exc})")

    raise RuntimeError(
        "Gagal memuat model embedding GGUF.\n"
        "Solusi: set ENV EMBED_MODEL_PATH ke file .gguf yang valid atau letakkan file di models/.\n"
        "Kandidat yang dicoba:\n - " + "\n - ".join(errors)
    )

# ===== Siapkan KB & index di start-up =====
# Catatan: panggilan ini akan dieksekusi saat action server diimport.
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

# ===== Actions =====
class ActionRetrieveTop1(Action):
    def name(self) -> str:
        return "action_retrieve_top1"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict):
        q = (tracker.latest_message.get("text") or "").strip()
        if not q:
            dispatcher.utter_message(text="Pertanyaan tidak terbaca.")
            return []

        try:
            results = _kb.search(q, top_k=ENV_TOPK)

            # >>> DEBUG di sini
            print(f"[DBG] query={q!r} results={results[:1]}")
            # <<<
            
        except Exception as exc:
            dispatcher.utter_message(text=f"Gagal melakukan pencarian: {exc}")
            return []

        try:
            top1 = select_top1(results, threshold=ENV_THRESHOLD)
            dispatcher.utter_message(
                text=f"{top1['text']}\n\nSumber: {top1['source']} (score={top1['score']:.2f})"
            )
        except NoAnswerError as e:
            dispatcher.utter_message(
                text=f"Maaf, belum ada jawaban yang cocok di knowledge base. ({e})"
            )
        return []

# (Opsional) Action healthcheck sederhana
class ActionEmbedderInfo(Action):
    def name(self) -> str:
        return "action_embedder_info"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict):
        dispatcher.utter_message(
            text=(
                "Embedder siap.\n"
                f"Model: {_EMBED_MODEL_PATH or '-'}\n"
                f"Threads: {ENV_THREADS}\n"
                f"Top-K: {ENV_TOPK}, Threshold: {ENV_THRESHOLD}"
            )
        )
        return []

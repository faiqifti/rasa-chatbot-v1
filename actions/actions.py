# actions/actions.py
import os
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

# Local imports
from .embedder import GGUFEmbedder
from .ranker import select_top1, NoAnswerError
from .redis_cache import get_from_cache, set_to_cache
# NEW: Import the RabbitMQ producer functions
from .rabbitmq_producer import (
    track_incoming_message, 
    track_ready_message,
    track_processing_message,
    track_success_response,
    track_failed_response,
    track_delivered_message,
    track_error,
    track_metrics,
    QueueType,
    get_queue_stats,
    close_connection
)

# ==== Qdrant ====
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

# Environment Loading
from dotenv import load_dotenv
load_dotenv()

# ===== Konfigurasi dasar =====
BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"

# ===== ENV / Konfigurasi =====
ENV_MODEL_PATH = os.getenv("EMBED_MODEL_PATH")
ENV_THRESHOLD = float(os.getenv("RAG_THRESHOLD", "0.35"))
ENV_TOPK = int(os.getenv("RAG_TOPK", "5"))
ENV_THREADS = int(os.getenv("EMBED_THREADS", "4"))

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
# Variabel ini sekarang berfungsi sebagai default untuk action lain seperti action_embedder_info
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "kb_documents")

# ===== Candidate model paths =====
def _candidate_model_paths() -> List[Path]:
    candidates: List[Path] = []
    if ENV_MODEL_PATH:
        candidates.append(Path(ENV_MODEL_PATH))
    candidates.extend([
        MODELS_DIR / "bge-m3-q4_k_m.gguf",
        MODELS_DIR / "gte-multilingual-base-q4_k_m.gguf",
        MODELS_DIR / "nomic-embed-text-v1.5.Q2_K.gguf",
    ])
    return candidates

# ===== Lazy init embedder =====
_EMBEDDER: Optional[GGUFEmbedder] = None
_EMBED_MODEL_PATH: Optional[str] = None

def _init_embedder() -> GGUFEmbedder:
    global _EMBEDDER, _EMBED_MODEL_PATH
    if _EMBEDDER is not None:
        return _EMBEDDER
    errors = []
    for candidate in _candidate_model_paths():
        if candidate.exists():
            try:
                emb = GGUFEmbedder(str(candidate.resolve()), threads=ENV_THREADS)
                _EMBEDDER = emb
                _EMBED_MODEL_PATH = str(candidate.resolve())
                return emb
            except Exception as exc:
                errors.append(f"{candidate} ({exc})")
        else:
            errors.append(f"{candidate} (missing)")
    raise RuntimeError("Failed to load GGUF embedding model:\n - " + "\n - ".join(errors))

# ===== Qdrant client (lazy) =====
_QDRANT: Optional[QdrantClient] = None

def _get_qdrant() -> QdrantClient:
    global _QDRANT
    if _QDRANT is not None:
        return _QDRANT
    _QDRANT = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    return _QDRANT

# <--- PERUBAHAN DIMULAI DI SINI --- >

# ===== Helper: search ke Qdrant with caching =====
# Fungsi ini sekarang menerima 'collection_name' sebagai argumen
def _search_qdrant(query: str, collection_name: str, top_k: int) -> List[Dict[str, Any]]:
    # Kunci cache sekarang harus unik untuk setiap collection dan query
    cache_key = f"{collection_name}:{query}"
    cached_result = get_from_cache(cache_key)
    if cached_result:
        print(f"[LOG] Cache HIT for key: {cache_key!r}")
        return cached_result
    
    print(f"[LOG] Cache MISS for key: {cache_key!r}. Searching Qdrant in collection '{collection_name}'...")
    
    emb = _embedder.embed_one(query).tolist()
    client = _get_qdrant()
    results = client.search(
        collection_name=collection_name, # Menggunakan collection_name dari argumen
        query_vector=emb,
        limit=top_k,
        with_payload=True,
    )
    
    out: List[Dict[str, Any]] = []
    for r in results:
        payload = r.payload or {}
        out.append({
            "id": payload.get("kb_id") or r.id,
            "text": payload.get("text", ""),
            "source": payload.get("source", ""),
            "score": float(r.score),
        })
    
    set_to_cache(cache_key, out)
    return out

# <--- PERUBAHAN SELESAI DI SINI --- >

# ===== Init (ringan, tidak melakukan ingest) =====
_embedder = _init_embedder()

# ===== Actions =====
class ActionRetrieveTop1(Action):
    def name(self) -> str:
        return "action_retrieve_top1"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict):
        start_time = time.time()
        q = (tracker.latest_message.get("text") or "").strip()
        session_id = tracker.sender_id
        message_id = f"msg_{int(start_time)}"
        
        # <--- PERUBAHAN DIMULAI DI SINI --- >
        # 1. Dapatkan intent yang terdeteksi
        user_intent = tracker.latest_message['intent'].get('name')
        print(f"\n🔍 [DEBUG] Intent detected: {user_intent}")

        # 2. Buat pemetaan dari intent ke nama collection Qdrant
        intent_to_collection_map = {
            "query_simpanan_kb": "simpanan",
            "query_pinjaman_kb": "pinjaman",
            "query_kartu_kredit_kb": "kartu_kredit"
        }
        
        # 3. Tentukan collection target berdasarkan intent
        target_collection = intent_to_collection_map.get(user_intent)

        if not target_collection:
            # Fallback jika intent tidak dikenali atau action ini terpicu secara tidak sengaja
            error_msg = "Maaf, saya tidak yakin harus mencari informasi ini di mana. Bisa perjelas pertanyaan Anda?"
            dispatcher.utter_message(text=error_msg)
            print(f"❌ [ERROR] Action '{self.name()}' triggered with unhandled intent: '{user_intent}'")
            track_failed_response(
                session_id=session_id,
                message_id=message_id,
                error=f"Unhandled intent: {user_intent}",
                error_type="routing_error"
            )
            return []
        
        print(f"🎯 [DEBUG] Routing to collection: '{target_collection}'")
        # <--- PERUBAHAN SELESAI DI SINI --- >
        
        print(f"--- Triggered {self.name()} for user message: {q!r} ---")
        
        track_incoming_message(
            session_id=session_id,
            message=q,
            user_id=session_id,
            metadata={"action": self.name(), "intent": user_intent}
        )
        
        if not q:
            dispatcher.utter_message(text="Pertanyaan tidak terbaca.")
            track_failed_response(
                session_id=session_id,
                message_id=message_id,
                error="Empty user question",
                error_type="validation_error"
            )
            return []

        try:
            track_ready_message(
                session_id=session_id,
                message_id=message_id,
                metadata={"query": q, "top_k": ENV_TOPK, "collection": target_collection}
            )
            track_processing_message(
                session_id=session_id,
                message_id=message_id,
                processor="qdrant_retrieval",
                metadata={"query": q, "top_k": ENV_TOPK, "collection": target_collection}
            )
            
            # <--- PERUBAHAN DIMULAI DI SINI --- >
            # Panggil _search_qdrant dengan collection yang sudah ditentukan
            results = _search_qdrant(q, collection_name=target_collection, top_k=ENV_TOPK)
            # <--- PERUBAHAN SELESAI DI SINI --- >
            
            search_time = time.time() - start_time
            track_metrics(
                metric_name="search_duration_seconds",
                value=search_time,
                tags={"component": "qdrant_search", "collection": target_collection}
            )

        except Exception as exc:
            print(f"[ERROR] An exception occurred during search: {exc}")
            error_msg = f"Gagal mencari di Qdrant: {exc}"
            dispatcher.utter_message(text=error_msg)
            track_error(
                session_id=session_id,
                error=str(exc),
                component="qdrant_search",
                traceback=str(exc)
            )
            track_failed_response(
                session_id=session_id,
                message_id=message_id,
                error=error_msg,
                error_type="search_error"
            )
            return []

        try:
            top1 = select_top1(results, threshold=ENV_THRESHOLD)
            response_text = f"{top1['text']}\n\nSumber: {top1['source']} (score={top1['score']:.2f})"
            processing_time = time.time() - start_time
            
            track_success_response(
                session_id=session_id,
                message_id=message_id,
                response=top1['text'][:100] + "..." if len(top1['text']) > 100 else top1['text'],
                processing_time=processing_time,
                # metadata={"source_collection": target_collection, "score": top1['score']}
            )
            track_delivered_message(
                session_id=session_id,
                message_id=message_id,
                delivery_channel="rasa_dispatcher"
            )
            track_metrics(
                metric_name="response_duration_seconds", 
                value=processing_time,
                tags={"status": "success", "component": self.name(), "collection": target_collection}
            )
            track_metrics(
                metric_name="response_score",
                value=top1['score'],
                tags={"source": top1['source'], "collection": target_collection}
            )
            dispatcher.utter_message(text=response_text)

        except NoAnswerError as e:
            error_msg = f"Maaf, belum ada jawaban yang cocok di knowledge base. ({e})"
            dispatcher.utter_message(text=error_msg)
            processing_time = time.time() - start_time
            track_failed_response(
                session_id=session_id,
                message_id=message_id,
                error=str(e),
                error_type="no_answer"
            )
            track_metrics(
                metric_name="response_duration_seconds",
                value=processing_time,
                tags={"status": "no_answer", "component": self.name(), "collection": target_collection}
            )
            
        except Exception as e:
            error_msg = f"Terjadi kesalahan saat memproses pertanyaan: {e}"
            dispatcher.utter_message(text=error_msg)
            track_error(
                session_id=session_id,
                error=str(e),
                component="response_generation",
                traceback=str(e)
            )
            track_failed_response(
                session_id=session_id,
                message_id=message_id,
                error=str(e),
                error_type="processing_error"
            )
            
        return []

# Kelas ActionEmbedderInfo dan ActionGetRabbitMQStats tidak perlu diubah, biarkan seperti aslinya.
# ... (sisa kode Anda)
class ActionEmbedderInfo(Action):
    def name(self) -> str:
        return "action_embedder_info"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict):
        session_id = tracker.sender_id
        message_id = f"info_{int(time.time())}"
        
        print(f"--- Triggered {self.name()} ---")
        
        track_incoming_message(
            session_id=session_id,
            message="system_info_request",
            user_id=session_id,
            metadata={"action": self.name()}
        )
        
        try:
            client = _get_qdrant()
            # Catatan: Count ini menggunakan collection default dari env var.
            # Untuk info yang lebih detail, ini bisa diubah untuk me-list semua collection.
            cnt = client.count(QDRANT_COLLECTION, exact=False).count
        except Exception as e:
            cnt = None
            track_error(
                session_id=session_id,
                error=str(e),
                component="qdrant_count",
                traceback=str(e)
            )

        info_text = (
            "Embedder siap.\n"
            f"Model: {_EMBED_MODEL_PATH or '-'}\n"
            f"Threads: {ENV_THREADS}\n"
            f"Top-K: {ENV_TOPK}, Threshold: {ENV_THRESHOLD}\n"
            f"Qdrant: {QDRANT_URL}, Default Collection: {QDRANT_COLLECTION}, Points: {cnt if cnt is not None else '?'}"
        )
        
        track_success_response(
            session_id=session_id,
            message_id=message_id,
            response="System information retrieved",
            processing_time=0.1
        )
        
        dispatcher.utter_message(text=info_text)
        return []

class ActionGetRabbitMQStats(Action):
    def name(self) -> str:
        return "action_get_rabbitmq_stats"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict):
        session_id = tracker.sender_id
        
        print(f"--- Triggered {self.name()} ---")
        
        stats = get_queue_stats()
        
        if stats:
            stats_text = "📊 RabbitMQ Queue Statistics:\n\n"
            for queue_name, queue_stats in stats.items():
                stats_text += f"• {queue_name}:\n"
                stats_text += f"  - Messages Ready: {queue_stats['messages_ready']}\n"
                stats_text += f"  - Consumers: {queue_stats['consumers']}\n\n"
        else:
            stats_text = "❌ Unable to retrieve RabbitMQ statistics. Please check RabbitMQ connection."
        
        track_metrics(
            metric_name="monitoring_request",
            value=1.0,
            tags={"type": "rabbitmq_stats"}
        )
        
        dispatcher.utter_message(text=stats_text)
        return []

print("\n[DEBUG] Forcing initial connection to RabbitMQ on server startup...")
track_metrics(
    metric_name="server_startup",
    value=1.0,
    tags={"component": "rasa_action_server"}
)
try:
    stats = get_queue_stats()
    if stats:
        print("[DEBUG] Initial RabbitMQ connection successful. Queue stats:")
        for queue, info in stats.items():
            print(f"  {queue}: {info['messages_ready']} messages ready")
    else:
        print("[DEBUG] Could not retrieve initial RabbitMQ stats")
except Exception as e:
    print(f"[DEBUG] Error getting initial RabbitMQ stats: {e}")
import atexit
atexit.register(close_connection)
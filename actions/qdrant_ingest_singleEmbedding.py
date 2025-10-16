# # qdrant_ingest.py
# import os
# import uuid
# from pathlib import Path
# from typing import List, Dict

# from qdrant_client.http import models as qm
# from .qdrant_utils import get_client, ensure_collection

# # Reuse your GGUFEmbedder
# from .embedder import GGUFEmbedder  # adjust import if path differs

# from dotenv import load_dotenv
# load_dotenv()

# # BASE_DIR = Path(__file__).resolve().parent

# # Go up one level (from 'actions' to 'root')
# BASE_DIR = Path(__file__).resolve().parent.parent
# MODELS_DIR = BASE_DIR / "models"

# # ENV
# ENV_MODEL_PATH = os.getenv("EMBED_MODEL_PATH")
# QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "kb_documents")

# def candidate_model_paths() -> List[Path]:
#     out: List[Path] = []
#     if ENV_MODEL_PATH:
#         out.append(Path(ENV_MODEL_PATH))
#     out.extend([
#         MODELS_DIR / "bge-m3-q4_k_m.gguf",
#         MODELS_DIR / "gte-multilingual-base-q4_k_m.gguf",
#         MODELS_DIR / "nomic-embed-text-v1.5.Q2_K.gguf",
#         MODELS_DIR / "embeddinggemma-300M.Q4_0.gguf",
#         MODELS_DIR / "embeddinggemma-300M-Q8_0.gguf",
#     ])
#     return out

# def load_embedder() -> GGUFEmbedder:
#     errors = []
#     for p in candidate_model_paths():
#         if p.exists():
#             try:
#                 return GGUFEmbedder(str(p.resolve()))
#             except Exception as e:
#                 errors.append(f"{p} ({e})")
#         else:
#             errors.append(f"{p} (missing)")
#     raise RuntimeError("Tidak ada model embedding yang bisa dimuat:\n - " + "\n - ".join(errors))

# def docs_source() -> List[Dict]:
#     """
#     Ganti ini sesuai sumber dokumenmu (CSV/MD/db). Untuk demo:
#     """
#     return [
#         {"kb_id": 121, "text": "Limit transfer harian rekening reguler adalah Rp25 juta.", "source": "kb/transfer.md"},
#         {"kb_id": 122, "text": "Biaya administrasi bulanan rekening reguler adalah Rp7.500.", "source": "kb/biaya.md"},
#         {"kb_id": 123,"text": "Kartu ATM hilang dapat diblokir via call center atau cabang terdekat.","source":"kb/kartu.md"},
#     ]

# def main():
#     embedder = load_embedder()
#     # Determine dimension robustly (some embedders have .dim, otherwise infer)
#     try:
#         dim = getattr(embedder, "dim")
#         if not isinstance(dim, int) or dim <= 0:
#             raise AttributeError
#     except Exception:
#         # fallback: infer from a sample
#         sample = embedder.embed_one("dim probe")
#         dim = len(sample)

#     client = get_client()
#     ensure_collection(client, QDRANT_COLLECTION, dim, distance="Cosine")

#     items = docs_source()
#     points: List[qm.PointStruct] = []

#     for item in items:
#         vec = embedder.embed_one(item["text"])
#         pid = item.get("kb_id") or str(uuid.uuid4())
#         payload = {
#             "kb_id": item.get("kb_id"),
#             "text": item["text"],
#             "source": item.get("source", ""),
#         }
#         points.append(qm.PointStruct(
#             id=pid,  # string ids are supported
#             vector=vec.tolist(),
#             payload=payload
#         ))

#     # Upsert
#     client.upsert(collection_name=QDRANT_COLLECTION, points=points)
#     print(f"Upserted {len(points)} points into '{QDRANT_COLLECTION}' with dim={dim}")

# if __name__ == "__main__":
#     main()

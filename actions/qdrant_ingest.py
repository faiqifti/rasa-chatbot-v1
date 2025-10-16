# qdrant_ingest.py
import os
import uuid
from pathlib import Path
from typing import List, Dict

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from .qdrant_utils import get_client, ensure_collection

# Reuse your GGUFEmbedder
from .embedder import GGUFEmbedder  # adjust import if path differs

from dotenv import load_dotenv
load_dotenv()

# BASE_DIR = Path(__file__).resolve().parent

# Go up one level (from 'actions' to 'root')
BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"

# ENV
ENV_MODEL_PATH = os.getenv("EMBED_MODEL_PATH")
# QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "kb_documents") # QDRANT_COLLECTION tidak lagi digunakan karena kita punya beberapa collection

def candidate_model_paths() -> List[Path]:
    out: List[Path] = []
    if ENV_MODEL_PATH:
        out.append(Path(ENV_MODEL_PATH))
    out.extend([
        MODELS_DIR / "bge-m3-q4_k_m.gguf",
        MODELS_DIR / "gte-multilingual-base-q4_k_m.gguf",
        MODELS_DIR / "nomic-embed-text-v1.5.Q2_K.gguf",
        MODELS_DIR / "embeddinggemma-300M.Q4_0.gguf",
        MODELS_DIR / "embeddinggemma-300M-Q8_0.gguf",
    ])
    return out

def load_embedder() -> GGUFEmbedder:
    errors = []
    for p in candidate_model_paths():
        if p.exists():
            try:
                return GGUFEmbedder(str(p.resolve()))
            except Exception as e:
                errors.append(f"{p} ({e})")
        else:
            errors.append(f"{p} (missing)")
    raise RuntimeError("Tidak ada model embedding yang bisa dimuat:\n - " + "\n - ".join(errors))

def main():
    # 1. Muat Embedder dan tentukan dimensi vektor
    embedder = load_embedder()
    try:
        dim = getattr(embedder, "dim")
    except Exception:
        sample = embedder.embed_one("dim probe")
        dim = len(sample)
    
    # 2. Definisikan Knowledge Base untuk setiap produk
    knowledge_base = {
        "simpanan": [
            {"kb_id": 11001, "text": "Produk TabunganKu bebas biaya administrasi bulanan.", "source": "kb/simpanan/tabunganku.md"},
            {"kb_id": 11002, "text": "Suku bunga untuk tabungan Simpanan Plus adalah 3% per tahun untuk saldo di atas 50 juta.", "source": "kb/simpanan/simpanan_plus.md"},
            {"kb_id": 11003, "text": "Limit transfer harian antar rekening untuk nasabah reguler adalah 100 juta per hari.", "source": "kb/simpanan/limit.md"},
        ],
        "pinjaman": [
            {"kb_id": 22001, "text": "Syarat pengajuan Kredit Tanpa Agunan (KTA) adalah memiliki penghasilan tetap minimum 5 juta per bulan.", "source": "kb/pinjaman/kta.md"},
            {"kb_id": 22002, "text": "Bunga untuk Kredit Pemilikan Rumah (KPR) fixed 3 tahun pertama adalah 6.5%.", "source": "kb/pinjaman/kpr.md"},
            {"kb_id": 22003, "text": "Dokumen yang diperlukan untuk pinjaman usaha mikro adalah KTP, NPWP, dan Surat Izin Usaha.", "source": "kb/pinjaman/mikro.md"},
        ],
        "kartu_kredit": [
            {"kb_id": 33001, "text": "Iuran tahunan untuk Kartu Kredit Gold adalah Rp 500.000, gratis untuk tahun pertama.", "source": "kb/kk/gold.md"},
            {"kb_id": 33002, "text": "Untuk memblokir kartu kredit yang hilang, segera hubungi call center di nomor 14000.", "source": "kb/kk/blokir.md"},
            {"kb_id": 33003, "text": "Setiap transaksi menggunakan Kartu Kredit Platinum akan mendapatkan 2 poin reward.", "source": "kb/kk/platinum.md"},
        ]
    }

    client = get_client()

    # 3. Lakukan iterasi untuk setiap kategori produk
    for collection_name, documents in knowledge_base.items():
        print(f"\n--- Memproses Collection: {collection_name} ---")
        
        # Pastikan collection ada di Qdrant
        ensure_collection(client, collection_name, dim, distance="Cosine")

        points: List[qm.PointStruct] = []
        
        # Buat embedding untuk setiap dokumen dalam kategori ini
        for item in documents:
            vec = embedder.embed_one(item["text"])
            pid = item.get("kb_id") or str(uuid.uuid4())
            payload = {
                "kb_id": item.get("kb_id"),
                "text": item["text"],
                "source": item.get("source", ""),
            }
            points.append(qm.PointStruct(
                id=pid,
                vector=vec.tolist(),
                payload=payload
            ))

        # 4. Upsert data ke collection yang sesuai
        if points:
            client.upsert(collection_name=collection_name, points=points)
            print(f"Berhasil! Upserted {len(points)} points ke dalam collection '{collection_name}'")

if __name__ == "__main__":
    main()
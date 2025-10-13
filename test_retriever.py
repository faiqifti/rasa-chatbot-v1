# test_retriever.py
"""
Sanity test untuk MiniKB & GGUFEmbedder + retriever.search()

Cara pakai (REAL model):
  python3 test_retriever.py --model ./models/bge-m3-q4_k_m.gguf --threads 8

Atau (MOCK, tanpa model .gguf):
  python3 test_retriever.py --mock

Exit code 0 = lulus; selain itu = ada kegagalan penting.
"""
import os
import sys
import argparse
import math
from typing import List, Tuple

import numpy as np

# --- Import komponen yang diuji ---
# Sesuaikan path package kamu jika struktur berbeda
try:
    from actions.embedder import GGUFEmbedder  # jika embedder.py di actions/
    from actions.retriever import MiniKB, KBItem
except Exception:
    # fallback: kalau file ada di direktori yang sama
    from embedder import GGUFEmbedder
    from retriever import MiniKB, KBItem


# -----------------------------
# Mock embedder (tanpa .gguf)
# -----------------------------
class MockEmbedder:
    """
    Embedder tiruan: bag-of-words sederhana ke vektor 256-dim via hashing.
    Tujuan: menguji pipeline MiniKB.search tanpa butuh model .gguf.
    """
    def __init__(self, dim: int = 256):
        self.dim = dim

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [t.lower() for t in text.split() if t.strip()]

    def _hash_vec(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        for tok in self._tokenize(text):
            h = hash(tok) % self.dim
            vec[h] += 1.0
        # L2 normalize
        n = np.linalg.norm(vec)
        return vec / n if n > 0 else vec

    def embed_one(self, text: str, normalize: bool = True) -> np.ndarray:
        v = self._hash_vec(text)
        return v if normalize else v  # sudah normalized

    def embed_batch(self, texts: List[str], normalize: bool = True) -> List[np.ndarray]:
        return [self.embed_one(t, normalize) for t in texts]


# -----------------------------
# Data uji (Indonesia, domain banking)
# -----------------------------
def build_kb_items() -> List[KBItem]:
    return [
        KBItem(
            id="kb#limit",
            text="Limit transfer harian rekening reguler adalah Rp25 juta. Limit dapat berbeda untuk jenis rekening tertentu.",
            source="kb/limit.md",
        ),
        KBItem(
            id="kb#biaya",
            text="Biaya admin bulanan dikenakan pada akhir bulan untuk rekening tabungan reguler.",
            source="kb/biaya.md",
        ),
        KBItem(
            id="kb#blokir",
            text="Kartu ATM hilang dapat diblokir melalui call center atau kunjungan ke cabang terdekat.",
            source="kb/kartu.md",
        ),
        KBItem(
            id="kb#pin",
            text="Penggantian PIN kartu ATM dapat dilakukan di ATM atau cabang sesuai prosedur keamanan.",
            source="kb/pin.md",
        ),
        KBItem(
            id="kb#cuaca",
            text="Cuaca di Jakarta hari ini diperkirakan cerah berawan dengan kemungkinan hujan ringan.",
            source="kb/lainnya.md",
        ),
    ]


# -----------------------------
# Helper assertions
# -----------------------------
def assert_descending(scores: List[float]) -> None:
    for i in range(1, len(scores)):
        if scores[i] > scores[i - 1] + 1e-7:
            raise AssertionError(f"Skor tidak menurun di indeks {i-1}->{i}: {scores[i-1]:.4f} -> {scores[i]:.4f}")

def within_top(results: List[dict], target_id: str, k: int) -> bool:
    return any(r["id"] == target_id for r in results[:k])

def pretty_print(query: str, results: List[dict], k: int = 5) -> None:
    print(f'\n[QUERY] {query}')
    for i, r in enumerate(results[:k], 1):
        print(f"  {i:>2}. {r['id']:<10} score={r['score']:.4f}  src={r['source']}")
        # potong text agar ringkas
        snippet = r['text']
        if len(snippet) > 100:
            snippet = snippet[:100] + "…"
        print(f"      {snippet}")


# -----------------------------
# Main test flow
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Test MiniKB + GGUFEmbedder retriever")
    parser.add_argument("--model", help="Path ke model .gguf (contoh: ./models/bge-m3-q4_k_m.gguf)")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--mock", action="store_true", help="Gunakan MockEmbedder (tanpa .gguf)")
    parser.add_argument("--topk", type=int, default=5)
    args = parser.parse_args()

    # 1) Pilih embedder
    if args.mock:
        print("[INFO] Menggunakan MockEmbedder (tanpa model .gguf)")
        embedder = MockEmbedder(dim=256)
    else:
        if not args.model:
            print("[FAIL] --model wajib diisi kecuali pakai --mock")
            return 2
        model_path = os.path.abspath(os.path.expanduser(args.model))
        if not os.path.exists(model_path):
            print("[FAIL] File model tidak ditemukan:", model_path)
            return 2
        print(f"[INFO] Memuat GGUFEmbedder: {model_path} | threads={args.threads}")
        embedder = GGUFEmbedder(model_path=model_path, threads=args.threads)

    # 2) Bangun KB & index
    items = build_kb_items()
    kb = MiniKB(items=items, embedder=embedder)

    print("[INFO] Membangun index (pre-embedding dokumen)…")
    kb.build_index()
    # pastikan semua vec terisi
    not_indexed = [it.id for it in items if getattr(it, "vec", None) is None]
    if not_indexed:
        print("[FAIL] Ada item belum ter-embed:", not_indexed)
        return 3
    # dimensi konsisten
    dims = {it.vec.shape[0] for it in items}
    if len(dims) != 1:
        print("[FAIL] Dimensi embedding tidak konsisten:", dims)
        return 3
    dim = dims.pop()
    print(f"[OK] Index siap. dim={dim}, n_items={len(items)}")

    # 3) Jalankan beberapa query & evaluasi ringan
    queries_expect: List[Tuple[str, str]] = [
        ("limit transfer harian rekening reguler", "kb#limit"),
        ("biaya admin bulanan berapa", "kb#biaya"),
        ("cara blokir kartu ATM yang hilang", "kb#blokir"),
        # tambahkan yang tak terkait untuk sanity
        ("cuaca jakarta hari ini", "kb#cuaca"),
    ]

    any_soft_fail = False

    for q, expected in queries_expect:
        results = kb.search(q, top_k=args.topk)
        pretty_print(q, results, k=args.topk)

        # a) skor menurun
        assert_descending([r["score"] for r in results])

        # b) expected muncul di Top-3 (toleran terhadap variasi model)
        if within_top(results, expected, k=min(3, args.topk)):
            print(f"[OK] '{expected}' muncul di Top-{min(3, args.topk)}")
        else:
            print(f"[WARN] '{expected}' tidak di Top-3. Cek model/kueri/isi dokumen.")
            any_soft_fail = True

        # c) kalau Top-1 bukan expected, beri peringatan (masih soft fail)
        if results and results[0]["id"] != expected:
            print(f"[WARN] Top-1 = {results[0]['id']} (bukan {expected}). "
                  "Ini bisa terjadi jika model kurang pas bahasa/domain atau kalimat terlalu pendek.")

    # 4) Uji top_k bekerja
    q = "limit transfer"
    r5 = kb.search(q, top_k=5)
    r2 = kb.search(q, top_k=2)
    if len(r5) == 5 and len(r2) == 2 and r2[0]["id"] == r5[0]["id"]:
        print("[OK] Parameter top_k berfungsi (Top-1 konsisten).")
    else:
        print("[FAIL] Perilaku top_k tidak konsisten.")
        return 4

    # 5) Ringkasan
    if any_soft_fail:
        print("\n[SUMMARY] Test selesai dengan PERINGATAN (soft). Pipeline bekerja,"
              " namun relevansi Top-1 tidak selalu sesuai ekspektasi.")
        print("          Pertimbangkan: model multilingual (BGE-M3), query lebih panjang,"
              " atau tambah hybrid BM25 + cosine / reranker.")
        return 0

    print("\n[DONE] Semua cek utama lulus ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# How to run:
# python3.10 test_retriever.py --model ./models/bge-m3-q4_k_m.gguf --threads 8
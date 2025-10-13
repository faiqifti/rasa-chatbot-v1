# test_embedder.py
import argparse, sys, time, numpy as np

def main():
    parser = argparse.ArgumentParser(description="Sanity check for GGUFEmbedder")
    parser.add_argument("--model", required=True, help="Path to .gguf embedding model")
    parser.add_argument("--threads", type=int, default=4, help="CPU threads")
    args = parser.parse_args()

    # Import GGUFEmbedder dari actions/embedder.py
    try:
        from actions.embedder import GGUFEmbedder
    except Exception as e:
        print("[FAIL] Tidak bisa import GGUFEmbedder dari actions.embedder:", e)
        print("Hint: Pastikan struktur folder benar dan jalankan dari root project.")
        sys.exit(1)

    # 1) Inisialisasi
    t0 = time.time()
    try:
        emb = GGUFEmbedder(model_path=args.model, threads=args.threads)
    except Exception as e:
        print("[FAIL] Gagal inisialisasi model:", e)
        sys.exit(1)
    t1 = time.time()
    print(f"[OK] Model loaded in {t1 - t0:.2f}s | threads={args.threads}")

    # 2) Embed satu teks
    text = "Limit transfer harian rekening reguler adalah Rp25 juta."
    try:
        v = emb.embed_one(text)
    except Exception as e:
        print("[FAIL] create_embedding (single) error:", e)
        sys.exit(1)

    if not isinstance(v, np.ndarray) or v.ndim != 1 or v.size == 0:
        print("[FAIL] Output bukan vektor 1D non-empty")
        sys.exit(1)
    norm = float(np.linalg.norm(v))
    print(f"[OK] Single embedding: dim={v.size}, L2-norm={norm:.4f} (should be ~1.0)")

    # 3) Embed batch
    texts = [
        "biaya admin bulanan rekening tabungan",
        "bagaimana cara blokir kartu ATM yang hilang",
        "limit transfer harian untuk rekening reguler",
    ]
    try:
        batch_vecs = emb.embed_batch(texts)
    except Exception as e:
        print("[FAIL] create_embedding (batch via loop) error:", e)
        sys.exit(1)

    if len(batch_vecs) != len(texts):
        print("[FAIL] Panjang hasil batch tidak sesuai input")
        sys.exit(1)
    dims = {vec.size for vec in batch_vecs if isinstance(vec, np.ndarray)}
    if len(dims) != 1:
        print("[FAIL] Dimensi vektor batch tidak konsisten:", dims)
        sys.exit(1)
    print(f"[OK] Batch embedding: n={len(batch_vecs)}, dim={dims.pop()}")

    # 4) Sanity check cosine: teks se-topik harus > teks berbeda topik
    def cos(a, b): 
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        return float(np.dot(a, b) / (na * nb + 1e-12))

    v_admin = batch_vecs[0]
    v_limit = batch_vecs[2]
    v_atm   = batch_vecs[1]

    sim_related = cos(v_admin, v_limit)
    sim_unrelated = cos(v_admin, v_atm)
    print(f"[INFO] cosine( admin , limit )    = {sim_related:.4f}")
    print(f"[INFO] cosine( admin , atm lost ) = {sim_unrelated:.4f}")

    if sim_related > sim_unrelated:
        print("[OK] Cosine sanity passed (related > unrelated)")
    else:
        print("[WARN] Cosine sanity inconclusive (related <= unrelated) — "
              "model mungkin bukan embedding semantik atau threshold perlu disesuaikan.")

    print("[DONE] GGUFEmbedder basic checks complete.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

# How to run:
# python3.10 test_embedder.py --model ./models/nomic-embed-text-v1.5.Q2_K.gguf --threads 8
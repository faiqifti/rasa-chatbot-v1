# run from project root:  python tests/check_kb_index.py
import os, numpy as np

# import your classes from the actions package
from actions.embedder import GGUFEmbedder  # or STEmbedder if you're using sentence-transformers
from actions.retriever import MiniKB, KBItem

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
MODEL_PATH = os.path.join(ROOT, "models", "embeddinggemma-300M-Q8_0.gguf")  # or your nomic gguf

def main():
    # 1) init embedder
    e = GGUFEmbedder(MODEL_PATH, threads=4)

    # 2) build KB + index
    items = [
        KBItem("faq#limit", "Limit transfer harian rekening reguler adalah Rp25 juta.", "kb/transfer.md"),
        KBItem("faq#admin", "Biaya administrasi bulanan rekening reguler adalah Rp7.500.", "kb/biaya.md"),
        KBItem("faq#blokir","Kartu ATM hilang dapat diblokir via call center atau cabang terdekat.","kb/kartu.md"),
    ]
    kb = MiniKB(items, e)
    kb.build_index()

    # 3) print norms (should be ~1.0)
    for it in kb.items:
        n = None if it.vec is None else float(np.linalg.norm(it.vec))
        print(f"[KB] {it.id:12s} has_vec={it.vec is not None} norm={n}")

if __name__ == "__main__":
    main()

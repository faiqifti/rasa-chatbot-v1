# main_demo.py
try:
    from .embedder import GGUFEmbedder
    from .retriever import MiniKB, KBItem
    from .ranker import select_top1, NoAnswerError
except ImportError:  # fallback when executed directly (python actions/main_demo.py)
    from embedder import GGUFEmbedder
    from retriever import MiniKB, KBItem
    from ranker import select_top1, NoAnswerError

MODEL_PATH = "/models/nomic-embed-text-v1.5.Q2_K.gguf"  # ganti ke path model kamu

if __name__ == "__main__":
    # 1) Siapkan embedder
    emb = GGUFEmbedder(model_path=MODEL_PATH, n_threads=4)

    # 2) Siapkan KB mini
    items = [
        KBItem(id="faq#limit", text="Limit transfer harian rekening reguler adalah Rp25 juta.", source="kb/transfer.md"),
        KBItem(id="faq#admin", text="Biaya administrasi bulanan rekening reguler adalah Rp7.500.", source="kb/biaya.md"),
        KBItem(id="faq#blokir", text="Kartu ATM hilang dapat diblokir via call center atau cabang terdekat.", source="kb/kartu.md"),
    ]
    kb = MiniKB(items=items, embedder=emb)
    kb.build_index()

    # 3) Query user → retrieval → top1 + threshold
    user_query = "berapa batas maksimal transfer harian?"
    results = kb.search(user_query, top_k=5)

    try:
        top1 = select_top1(results, threshold=0.35)
        print(f"[JAWABAN]\n{top1['text']}\n\nSumber: {top1['source']} (score={top1['score']:.2f})")
    except NoAnswerError as e:
        print(f"[TIDAK ADA JAWABAN] {e}")

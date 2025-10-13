# smoke_actions.py
import os
import sys
import argparse
import importlib

class DummyDispatcher:
    def __init__(self):
        self.messages = []
    def utter_message(self, text: str):
        self.messages.append(text)
        print(text)

class DummyTracker:
    def __init__(self, text: str):
        self.latest_message = {"text": text}

def main():
    parser = argparse.ArgumentParser(description="Smoke test for actions.actions: ActionRetrieveTop1")
    parser.add_argument("--query", required=True, help="Teks pertanyaan pengguna")
    parser.add_argument("--model", help="Path ke .gguf (override ENV EMBED_MODEL_PATH)")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--topk", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.35)
    args = parser.parse_args()

    # set ENV lebih dulu (actions.actions akan init embedder saat import)
    if args.model:
        os.environ["EMBED_MODEL_PATH"] = args.model
    os.environ["EMBED_THREADS"] = str(args.threads)
    os.environ["RAG_TOPK"] = str(args.topk)
    os.environ["RAG_THRESHOLD"] = str(args.threshold)

    # pastikan root ada di sys.path
    sys.path.insert(0, os.path.abspath("."))

    try:
        mod = importlib.import_module("actions.actions")
    except Exception as e:
        print("[FAIL] Gagal import actions.actions:", e)
        print("Hint: pastikan ada actions/__init__.py dan jalankan dari project root.")
        return 2

    disp = DummyDispatcher()
    tracker = DummyTracker(args.query)
    domain = {}

    # info embedder
    if hasattr(mod, "ActionEmbedderInfo"):
        print("== Embedder Info ==")
        try:
            mod.ActionEmbedderInfo().run(disp, tracker, domain)
        except Exception as e:
            print("[WARN] Gagal memanggil ActionEmbedderInfo:", e)

    # uji retrieval
    print("\n== RetrieveTop1 ==")
    try:
        mod.ActionRetrieveTop1().run(disp, tracker, domain)
    except Exception as e:
        print("[FAIL] Gagal menjalankan ActionRetrieveTop1:", e)
        return 3

    return 0

if __name__ == "__main__":
    sys.exit(main())

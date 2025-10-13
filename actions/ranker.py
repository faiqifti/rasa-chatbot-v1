# ranker.py
from __future__ import annotations
from typing import Dict, Any, List

class NoAnswerError(Exception):
    pass

def select_top1(results: List[Dict[str, Any]], threshold: float = 0.35) -> Dict[str, Any]:
    """
    Pilih kandidat teratas. Jika skor < threshold, raise NoAnswerError.
    """
    if not results:
        raise NoAnswerError("Knowledge base kosong atau tidak ada kandidat hasil pencarian.")
    if threshold < 0 or threshold > 1:
        # menjaga agar konfigurasi aneh tidak membuat semua kandidat ditolak
        threshold = 0.35
    top = results[0]
    score = float(top.get("score", 0.0))
    if score < threshold:
        raise NoAnswerError(f"Tidak ada jawaban yang cukup relevan (score={score:.2f} < {threshold}).")
    return top

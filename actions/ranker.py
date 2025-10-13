# ranker.py
from __future__ import annotations
from typing import Dict, Any, List, Optional

class NoAnswerError(Exception):
    pass

def select_top1(results: List[Dict[str, Any]], threshold: float = 0.35) -> Dict[str, Any]:
    """
    Pilih kandidat teratas. Jika skor < threshold, raise NoAnswerError.
    """
    if not results:
        raise NoAnswerError("Knowledge base kosong atau tidak ada kandidat hasil pencarian.")
    top = results[0]
    if top.get("score", 0.0) < threshold:
        raise NoAnswerError(f"Tidak ada jawaban yang cukup relevan (score={top.get('score', 0):.2f} < {threshold}).")
    return top

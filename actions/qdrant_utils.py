# qdrant_utils.py
import os
from typing import Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

# NEW: load .env first
try:
    from dotenv import load_dotenv
    load_dotenv()  # reads .env in project root
except Exception:
    # dotenv is optional; skip if not installed
    pass

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

def get_client() -> QdrantClient:
    # You can also pass timeout/retries if desired
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

def ensure_collection(client: QdrantClient, collection: str, dim: int, distance: str = "Cosine"):
    dist = {
        "Cosine": qm.Distance.COSINE,
        "Dot": qm.Distance.DOT,
        "Euclid": qm.Distance.EUCLID
    }.get(distance, qm.Distance.COSINE)

    existing = [c.name for c in client.get_collections().collections]
    if collection in existing:
        # Optional: verify vector size & distance; recreate if mismatched
        info = client.get_collection(collection)
        cfg = info.config.params.vectors  # VectorParams or dict
        size_ok = getattr(cfg, "size", None) == dim
        dist_ok = getattr(cfg, "distance", None) == dist
        if not (size_ok and dist_ok):
            # safest: drop & recreate
            client.delete_collection(collection)
            client.create_collection(
                collection_name=collection,
                vectors_config=qm.VectorParams(size=dim, distance=dist),
            )
        return

    client.create_collection(
        collection_name=collection,
        vectors_config=qm.VectorParams(size=dim, distance=dist),
    )

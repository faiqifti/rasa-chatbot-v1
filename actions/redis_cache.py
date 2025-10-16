# redis_cache.py
import os
import json
import redis
from typing import Optional, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600")) # Default to 1 hour

# --- Lazy Initialization for Redis Client ---
_REDIS_CLIENT: Optional[redis.Redis] = None

def _get_redis_client() -> Optional[redis.Redis]:
    """
    Initializes and returns a Redis client instance.
    Returns None if the connection fails.
    """
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    
    try:
        # from_url handles connection pooling automatically
        client = redis.from_url(REDIS_URL, decode_responses=True)
        # Check if the connection is alive
        client.ping()
        print("✅ Successfully connected to Redis for caching.")
        _REDIS_CLIENT = client
        return _REDIS_CLIENT
    except redis.exceptions.ConnectionError as e:
        print(f"⚠️ Warning: Could not connect to Redis. Caching will be disabled. Error: {e}")
        return None

# --- Public Caching Functions ---

def get_from_cache(key: str) -> Optional[Any]:
    """
    Retrieves and deserializes a value from the Redis cache.

    Args:
        key (str): The key to look up.

    Returns:
        Optional[Any]: The deserialized Python object if found, otherwise None.
    """
    client = _get_redis_client()
    if not client:
        return None
        
    cached_value = client.get(key)
    if cached_value:
        print(f"[CACHE HIT] for key: {key!r}")
        return json.loads(cached_value)
    
    print(f"[CACHE MISS] for key: {key!r}")
    return None

def set_to_cache(key: str, value: Any):
    """
    Serializes a Python object to JSON and stores it in the Redis cache.

    Args:
        key (str): The key to store the value under.
        value (Any): The Python object to store.
    """
    client = _get_redis_client()
    if not client:
        return

    # Serialize the Python object (e.g., a list of dicts) to a JSON string
    value_to_store = json.dumps(value)
    client.set(key, value_to_store, ex=CACHE_TTL_SECONDS)

def create_qdrant_cache_key(query: str) -> str:
    """Creates a consistent cache key for a given search query."""
    return f"qdrant_results:{query.lower().strip()}"
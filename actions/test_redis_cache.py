# test_redis_cache.py
import time
from .redis_cache import set_to_cache, get_from_cache, create_qdrant_cache_key, CACHE_TTL_SECONDS

# --- Main test execution ---
if __name__ == "__main__":
    print("--- Testing Redis Cache Module ---")

    # 1. Define sample data to cache
    # This simulates the kind of data you get from Qdrant
    test_key = create_qdrant_cache_key("What is the daily transfer limit?")
    test_value = [
        {
            "id": "faq-limit",
            "text": "The daily transfer limit for a regular account is Rp25 million.",
            "source": "kb/transfer.md",
            "score": 0.9876
        }
    ]

    # --- Test Case 1: Cache Miss ---
    print("\n[Test 1] Attempting to get a value that is NOT in the cache...")
    retrieved_value_miss = get_from_cache(test_key)
    if retrieved_value_miss is None:
        print("✅ PASSED: Function correctly returned None for a missing key.")
    else:
        print(f"❌ FAILED: Expected None, but got: {retrieved_value_miss}")

    # --- Test Case 2: Set and Get (Cache Hit) ---
    print("\n[Test 2] Setting a value into the cache...")
    set_to_cache(test_key, test_value)

    print("\n[Test 3] Attempting to get the value we just set...")
    retrieved_value_hit = get_from_cache(test_key)
    
    if retrieved_value_hit == test_value:
        print("✅ PASSED: Successfully retrieved the correct value from the cache.")
    else:
        print(f"❌ FAILED: Value mismatch!")
        print(f"   Expected: {test_value}")
        print(f"   Got: {retrieved_value_hit}")
        
    # --- Test Case 3: Test Cache Expiration (TTL) ---
    print(f"\n[Test 4] Testing cache expiration. Waiting for {CACHE_TTL_SECONDS + 1} seconds (this is a long test from your config)...")
    print("NOTE: You can shorten CACHE_TTL_SECONDS in your .env for faster testing (e.g., set it to 3).")
    
    # Create a temporary key for this test
    ttl_test_key = "temp_test_key"
    set_to_cache(ttl_test_key, {"data": "this will expire"})
    print(f"Value set for key '{ttl_test_key}'. Now waiting...")
    
    # To avoid a very long wait, we'll only run this if TTL is short
    if CACHE_TTL_SECONDS <= 10:
        time.sleep(CACHE_TTL_SECONDS + 1)
        expired_value = get_from_cache(ttl_test_key)
        if expired_value is None:
            print(f"✅ PASSED: Value correctly expired and is no longer in the cache after {CACHE_TTL_SECONDS}s.")
        else:
            print("❌ FAILED: Value should have expired but was still found in the cache.")
    else:
        print("-> Skipping actual wait for TTL test as it's longer than 10 seconds.")
        
    print("\n--- Test complete ---")
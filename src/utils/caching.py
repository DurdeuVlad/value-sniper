import os
import pickle
import time
from datetime import datetime, timedelta
import pandas as pd

CACHE_DIR = os.path.join(os.getcwd(), ".cache")

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

class CacheManager:
    def __init__(self):
        pass

    def _get_path(self, key):
        """Generates a file path for a given cache key."""
        # Sanitize key for filename
        safe_key = "".join([c if c.isalnum() else "_" for c in key])
        return os.path.join(CACHE_DIR, f"{safe_key}.pkl")

    def save(self, key, data):
        """Saves data to the cache."""
        path = self._get_path(key)
        try:
            with open(path, "wb") as f:
                pickle.dump(data, f)
            # print(f"[CACHE] Saved: {key}")
        except Exception as e:
            print(f"[CACHE] Error saving {key}: {e}")
    
    def delete(self, key):
        """Delete a specific cache entry."""
        path = self._get_path(key)
        if os.path.exists(path):
            try:
                os.remove(path)
                return True
            except Exception as e:
                print(f"[CACHE] Error deleting {key}: {e}")
                return False
        return False

    def load(self, key, ttl_minutes=30):
        """
        Loads data from the cache if it exists and is not expired.
        Returns None if cache is miss or expired.
        """
        path = self._get_path(key)
        
        if not os.path.exists(path):
            return None
        
        # Check expiry
        file_age = time.time() - os.path.getmtime(path)
        if file_age > (ttl_minutes * 60):
            # print(f"[CACHE] Expired: {key}")
            return None
            
        try:
            with open(path, "rb") as f:
                data = pickle.load(f)
            # print(f"[CACHE] Hit: {key}")
            return data
        except Exception as e:
            print(f"[CACHE] Error loading {key}: {e}")
            return None

    def clear(self):
        """Clears all cache files."""
        for f in os.listdir(CACHE_DIR):
            os.remove(os.path.join(CACHE_DIR, f))

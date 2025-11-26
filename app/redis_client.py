import redis
import json
import os
from typing import Optional, Any, List
from datetime import timedelta


class RedisCache:
    """Redis caching layer for file metadata and references"""
    
    def __init__(self):
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.client = redis.from_url(redis_url, decode_responses=True)
        self.default_ttl = 3600  # 1 hour default TTL
    
    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """Set a value in cache with optional TTL"""
        try:
            from metrics import record_cache_operation
            
            if ttl is None:
                ttl = self.default_ttl
            
            # Convert value to JSON string if it's not a string
            if not isinstance(value, str):
                value = json.dumps(value)
            
            self.client.setex(key, ttl, value)
            record_cache_operation("set", self._get_cache_type(key))
            return True
        except Exception as e:
            print(f"Redis SET error: {str(e)}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache"""
        try:
            from metrics import record_cache_operation
            
            value = self.client.get(key)
            cache_type = self._get_cache_type(key)
            
            if value is None:
                record_cache_operation("get", cache_type, hit=False)
                return None
            
            record_cache_operation("get", cache_type, hit=True)
            
            # Try to parse as JSON, return as-is if it fails
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        except Exception as e:
            print(f"Redis GET error: {str(e)}")
            return None
    
    def delete(self, key: str) -> bool:
        """Delete a key from cache"""
        try:
            from metrics import record_cache_operation
            
            self.client.delete(key)
            record_cache_operation("delete", self._get_cache_type(key))
            return True
        except Exception as e:
            print(f"Redis DELETE error: {str(e)}")
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        try:
            return self.client.exists(key) > 0
        except Exception as e:
            print(f"Redis EXISTS error: {str(e)}")
            return False
    
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment a counter"""
        try:
            return self.client.incrby(key, amount)
        except Exception as e:
            print(f"Redis INCREMENT error: {str(e)}")
            return None
    
    def _get_cache_type(self, key: str) -> str:
        """Determine cache type from key pattern"""
        if key.startswith("file:metadata:"):
            return "metadata"
        elif key.startswith("files:list:"):
            return "filelist"
        elif key.startswith("node:health:"):
            return "nodehealth"
        else:
            return "other"
    
    def set_file_metadata(self, file_id: int, metadata: dict, ttl: int = None) -> bool:
        """Cache file metadata"""
        key = f"file:metadata:{file_id}"
        return self.set(key, metadata, ttl)
    
    def get_file_metadata(self, file_id: int) -> Optional[dict]:
        """Get cached file metadata"""
        key = f"file:metadata:{file_id}"
        return self.get(key)
    
    def set_file_list(self, file_list: List[dict], ttl: int = 300) -> bool:
        """Cache file list (shorter TTL as it changes frequently)"""
        key = "files:list:all"
        return self.set(key, file_list, ttl)
    
    def get_file_list(self) -> Optional[List[dict]]:
        """Get cached file list"""
        key = "files:list:all"
        return self.get(key)
    
    def invalidate_file_list(self) -> bool:
        """Invalidate file list cache"""
        return self.delete("files:list:all")
    
    def set_node_health(self, node_id: str, health_data: dict, ttl: int = 60) -> bool:
        """Cache node health status"""
        key = f"node:health:{node_id}"
        return self.set(key, health_data, ttl)
    
    def get_node_health(self, node_id: str) -> Optional[dict]:
        """Get cached node health status"""
        key = f"node:health:{node_id}"
        return self.get(key)
    
    def increment_downloads(self, file_id: int) -> Optional[int]:
        """Increment download counter for a file"""
        key = f"file:downloads:{file_id}"
        count = self.increment(key)
        # Set expiry if this is the first increment
        if count == 1:
            self.client.expire(key, 86400)  # 24 hours
        return count
    
    def get_popular_files(self, limit: int = 10) -> List[dict]:
        """Get most downloaded files from cache"""
        try:
            # Get all download counter keys
            keys = self.client.keys("file:downloads:*")
            
            # Get values and sort
            file_downloads = []
            for key in keys:
                file_id = key.split(":")[-1]
                downloads = int(self.client.get(key) or 0)
                file_downloads.append({"file_id": file_id, "downloads": downloads})
            
            # Sort by downloads and return top N
            file_downloads.sort(key=lambda x: x["downloads"], reverse=True)
            return file_downloads[:limit]
        except Exception as e:
            print(f"Error getting popular files: {str(e)}")
            return []
    
    def clear_all(self) -> bool:
        """Clear all cache (use with caution)"""
        try:
            self.client.flushdb()
            return True
        except Exception as e:
            print(f"Redis FLUSHDB error: {str(e)}")
            return False
    
    def get_cache_stats(self) -> dict:
        """Get cache statistics"""
        try:
            info = self.client.info("stats")
            return {
                "total_commands": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": round(
                    info.get("keyspace_hits", 0) / 
                    max(info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0), 1) * 100, 
                    2
                )
            }
        except Exception as e:
            print(f"Error getting cache stats: {str(e)}")
            return {}


# Global instance
redis_cache = RedisCache()

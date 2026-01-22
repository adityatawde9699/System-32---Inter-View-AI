"""
InterView AI - Redis Session Store.

Distributed session state management for multi-worker deployments.
Falls back to in-memory storage if Redis is unavailable.

Usage:
    store = RedisSessionStore()
    
    # Store orchestrator for a session
    store.set_orchestrator(session_id, orchestrator)
    
    # Retrieve orchestrator
    orchestrator = store.get_orchestrator(session_id)
    
    # List active sessions
    active = store.list_active()
"""

import json
import logging
import pickle
from typing import Optional
from datetime import datetime, timedelta

from src.app.orchestrator import InterviewOrchestrator

logger = logging.getLogger(__name__)


class RedisSessionStore:
    """
    Distributed session store using Redis or in-memory fallback.
    
    Features:
    - Store orchestrator instances with TTL
    - Share state across multiple Uvicorn workers
    - Graceful fallback to in-memory if Redis unavailable
    - Track session activity for cleanup
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        fallback_to_memory: bool = True,
        session_ttl_hours: int = 2,
    ):
        """
        Initialize session store with Redis or fallback.
        
        Args:
            redis_url: Redis connection URL
            fallback_to_memory: Use in-memory dict if Redis unavailable
            session_ttl_hours: Session time-to-live in hours
        """
        self._redis_url = redis_url
        self._session_ttl_seconds = session_ttl_hours * 3600
        self._fallback_to_memory = fallback_to_memory
        self._in_memory: dict[str, tuple[InterviewOrchestrator, float]] = {}
        self._redis = None
        
        self._try_connect_redis()
    
    def _try_connect_redis(self) -> None:
        """Attempt to connect to Redis."""
        try:
            import redis
            self._redis = redis.from_url(
                self._redis_url,
                socket_connect_timeout=2,
                socket_keepalive=True,
            )
            # Test connection
            self._redis.ping()
            logger.info("✅ Connected to Redis for session state")
        except Exception as e:
            logger.warning(f"⚠️ Redis connection failed: {e}")
            self._redis = None
            if not self._fallback_to_memory:
                raise RuntimeError("Redis unavailable and fallback disabled")
            logger.info("📝 Using in-memory session store as fallback")
    
    def set_orchestrator(self, session_id: str, orchestrator: InterviewOrchestrator) -> None:
        """
        Store an orchestrator instance.
        
        Args:
            session_id: Session ID
            orchestrator: InterviewOrchestrator instance
        """
        if self._redis:
            try:
                # Pickle orchestrator for storage
                orchestrator_bytes = pickle.dumps(orchestrator)
                # Store with TTL
                self._redis.setex(
                    f"session:{session_id}",
                    self._session_ttl_seconds,
                    orchestrator_bytes,
                )
                logger.debug(f"Stored orchestrator for {session_id} in Redis")
            except Exception as e:
                logger.error(f"Failed to store in Redis: {e}. Falling back to memory.")
                self._in_memory[session_id] = (orchestrator, datetime.now().timestamp())
        else:
            # In-memory fallback
            self._in_memory[session_id] = (orchestrator, datetime.now().timestamp())
    
    def get_orchestrator(self, session_id: str) -> Optional[InterviewOrchestrator]:
        """
        Retrieve an orchestrator instance.
        
        Args:
            session_id: Session ID
            
        Returns:
            InterviewOrchestrator if found, None otherwise
        """
        if self._redis:
            try:
                orchestrator_bytes = self._redis.get(f"session:{session_id}")
                if orchestrator_bytes:
                    orchestrator = pickle.loads(orchestrator_bytes)
                    logger.debug(f"Retrieved orchestrator for {session_id} from Redis")
                    return orchestrator
            except Exception as e:
                logger.error(f"Failed to retrieve from Redis: {e}")
                # Fall through to in-memory check
        
        # In-memory fallback
        if session_id in self._in_memory:
            orchestrator, stored_at = self._in_memory[session_id]
            # Check if expired
            age_seconds = datetime.now().timestamp() - stored_at
            if age_seconds < self._session_ttl_seconds:
                logger.debug(f"Retrieved orchestrator for {session_id} from memory")
                return orchestrator
            else:
                del self._in_memory[session_id]
        
        return None
    
    def delete_orchestrator(self, session_id: str) -> bool:
        """
        Remove an orchestrator instance.
        
        Args:
            session_id: Session ID
            
        Returns:
            True if deleted, False if not found
        """
        found = False
        
        if self._redis:
            try:
                result = self._redis.delete(f"session:{session_id}")
                found = result > 0
                if found:
                    logger.debug(f"Deleted orchestrator for {session_id} from Redis")
            except Exception as e:
                logger.error(f"Failed to delete from Redis: {e}")
        
        # Also check in-memory
        if session_id in self._in_memory:
            del self._in_memory[session_id]
            found = True
            logger.debug(f"Deleted orchestrator for {session_id} from memory")
        
        return found
    
    def list_active(self) -> list[str]:
        """
        List all active session IDs.
        
        Returns:
            List of session IDs
        """
        session_ids = set()
        
        if self._redis:
            try:
                # Get all session keys from Redis
                pattern_keys = self._redis.keys("session:*")
                session_ids.update(
                    key.decode().replace("session:", "") 
                    for key in pattern_keys
                )
            except Exception as e:
                logger.error(f"Failed to list Redis sessions: {e}")
        
        # Add in-memory sessions that haven't expired
        now = datetime.now().timestamp()
        for sid, (_, stored_at) in list(self._in_memory.items()):
            age_seconds = now - stored_at
            if age_seconds < self._session_ttl_seconds:
                session_ids.add(sid)
            else:
                del self._in_memory[sid]
        
        return list(session_ids)
    
    def cleanup_expired(self) -> int:
        """
        Clean up expired sessions from in-memory store.
        
        Redis handles TTL automatically, but in-memory dict needs manual cleanup.
        
        Returns:
            Number of sessions cleaned
        """
        count = 0
        now = datetime.now().timestamp()
        
        for sid, (_, stored_at) in list(self._in_memory.items()):
            age_seconds = now - stored_at
            if age_seconds >= self._session_ttl_seconds:
                del self._in_memory[sid]
                count += 1
        
        if count > 0:
            logger.info(f"Cleaned up {count} expired in-memory sessions")
        
        return count
    
    def get_stats(self) -> dict:
        """
        Get store statistics.
        
        Returns:
            Dictionary with backend type and session counts
        """
        stats = {
            "backend": "redis" if self._redis else "memory",
            "session_ttl_hours": self._session_ttl_seconds / 3600,
        }
        
        if self._redis:
            try:
                stats["redis_sessions"] = len(self._redis.keys("session:*"))
            except Exception:
                pass
        
        stats["memory_sessions"] = len(self._in_memory)
        stats["total_active"] = len(self.list_active())
        
        return stats

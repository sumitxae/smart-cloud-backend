import asyncio
import time
from collections import defaultdict
from typing import Dict

class APICircuitBreaker:
    """Circuit breaker to prevent API overload"""
    
    def __init__(self, max_concurrent_requests: int = 10):
        self.max_concurrent_requests = max_concurrent_requests
        self.active_requests: Dict[str, int] = defaultdict(int)
        self.locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.last_reset = time.time()
    
    async def __aenter__(self, endpoint: str):
        async with self.locks[endpoint]:
            if self.active_requests[endpoint] >= self.max_concurrent_requests:
                raise Exception(f"Too many concurrent requests to {endpoint}")
            self.active_requests[endpoint] += 1
    
    async def __aexit__(self, endpoint: str, exc_type, exc_val, exc_tb):
        async with self.locks[endpoint]:
            self.active_requests[endpoint] = max(0, self.active_requests[endpoint] - 1)
    
    def is_overloaded(self, endpoint: str) -> bool:
        return self.active_requests[endpoint] >= self.max_concurrent_requests

# Global circuit breaker instance
circuit_breaker = APICircuitBreaker(max_concurrent_requests=5)

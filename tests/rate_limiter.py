#!/usr/bin/env python3
"""
Rate Limiter Utility - Token Bucket Algorithm

A simple rate limiter that uses the token bucket algorithm to control
the rate of requests. Tokens are added at a fixed rate, and each request
consumes one token. If no tokens are available, the request is rejected.
"""

import time
from collections import deque


class RateLimiter:
    """
    Token bucket rate limiter.

    Args:
        max_requests: Maximum number of requests allowed in the time window
        time_window: Time window in seconds
    """

    def __init__(self, max_requests: int, time_window: float):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()  # Timestamps of recent requests

    def is_allowed(self) -> bool:
        """
        Check if a request is allowed under the rate limit.

        Returns:
            True if request is allowed, False if rate limit exceeded
        """
        now = time.time()

        # Remove expired timestamps (outside the time window)
        while self.requests and self.requests[0] <= now - self.time_window:
            self.requests.popleft()

        # Check if we're under the limit
        if len(self.requests) < self.max_requests:
            self.requests.append(now)
            return True

        return False

    def reset(self):
        """Reset the rate limiter, clearing all tracked requests."""
        self.requests.clear()


def test_rate_limiter():
    """Test the rate limiter functionality."""
    print("=== Rate Limiter Tests ===\n")

    # Test 1: Basic rate limiting
    print("Test 1: Basic rate limiting (3 requests per 1 second)")
    limiter = RateLimiter(max_requests=3, time_window=1.0)

    results = []
    for i in range(5):
        allowed = limiter.is_allowed()
        results.append(allowed)
        print(f"  Request {i+1}: {'✅ Allowed' if allowed else '❌ Rejected'}")

    assert results == [True, True, True, False, False], "Basic rate limiting failed"
    print("  ✓ Passed!\n")

    # Test 2: Window expiration
    print("Test 2: Window expiration (requests allowed after window)")
    limiter.reset()

    # Use up all tokens
    for _ in range(3):
        limiter.is_allowed()

    # Wait for window to expire
    print("  Waiting 1.1 seconds for window to expire...")
    time.sleep(1.1)

    allowed = limiter.is_allowed()
    print(f"  Request after expiry: {'✅ Allowed' if allowed else '❌ Rejected'}")
    assert allowed, "Window expiration failed"
    print("  ✓ Passed!\n")

    # Test 3: Reset functionality
    print("Test 3: Reset functionality")
    limiter = RateLimiter(max_requests=2, time_window=10.0)

    limiter.is_allowed()
    limiter.is_allowed()
    assert not limiter.is_allowed(), "Should be rate limited"

    limiter.reset()
    assert limiter.is_allowed(), "Should be allowed after reset"
    print("  ✓ Passed!\n")

    print("=== All tests passed! ===")


if __name__ == "__main__":
    test_rate_limiter()

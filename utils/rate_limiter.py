import time


class RateLimiter:
    """
    Fixed-delay rate limiter for Finnhub's 60 calls/minute free tier.
    Call limiter.wait() before each Finnhub API request.
    Uses 55 calls/min to stay safely under the limit.
    """

    def __init__(self, calls_per_minute: int = 55):
        self.min_interval = 60.0 / calls_per_minute
        self.last_call_time = 0.0

    def wait(self):
        elapsed = time.time() - self.last_call_time
        wait_time = self.min_interval - elapsed
        if wait_time > 0:
            time.sleep(wait_time)
        self.last_call_time = time.time()


# Single instance imported everywhere
finnhub_limiter = RateLimiter(calls_per_minute=55)

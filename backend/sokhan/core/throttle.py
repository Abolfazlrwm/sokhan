import threading
import time
from collections import deque
from collections.abc import Callable, Hashable


class FailureThrottle:
    def __init__(
        self,
        max_failures: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._clock = clock
        self._failures: dict[Hashable, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: Hashable, now: float) -> deque[float]:
        stamps = self._failures.get(key)
        if stamps is None:
            return deque()
        while stamps and now - stamps[0] >= self.window_seconds:
            stamps.popleft()
        if not stamps:
            del self._failures[key]
        return stamps

    def retry_after(self, key: Hashable) -> int:
        if self.max_failures <= 0:
            return 0
        with self._lock:
            now = self._clock()
            stamps = self._prune(key, now)
            if len(stamps) < self.max_failures:
                return 0
            return max(1, int(stamps[0] + self.window_seconds - now + 0.999))

    def record_failure(self, key: Hashable) -> None:
        with self._lock:
            now = self._clock()
            self._prune(key, now)
            self._failures.setdefault(key, deque()).append(now)

    def reset(self, key: Hashable) -> None:
        with self._lock:
            self._failures.pop(key, None)

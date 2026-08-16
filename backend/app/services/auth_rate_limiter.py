from collections import deque
from math import ceil
from threading import Lock
from time import monotonic
from typing import Callable


class AuthRateLimiter:
    def __init__(
        self,
        *,
        login_max_failures: int,
        login_window_seconds: int,
        verification_max_requests_per_ip: int,
        verification_global_max_requests: int,
        verification_window_seconds: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.login_max_failures = max(1, login_max_failures)
        self.login_window_seconds = max(1, login_window_seconds)
        self.verification_max_requests_per_ip = max(1, verification_max_requests_per_ip)
        self.verification_global_max_requests = max(1, verification_global_max_requests)
        self.verification_window_seconds = max(1, verification_window_seconds)
        self.clock = clock
        self._login_identifiers: dict[str, deque[float]] = {}
        self._login_clients: dict[str, deque[float]] = {}
        self._verification_clients: dict[str, deque[float]] = {}
        self._verification_global: deque[float] = deque()
        self._lock = Lock()

    @staticmethod
    def _prune(events: deque[float], cutoff: float) -> None:
        while events and events[0] <= cutoff:
            events.popleft()

    @staticmethod
    def _events(store: dict[str, deque[float]], key: str) -> deque[float]:
        events = store.get(key)
        if events is not None:
            return events
        if len(store) >= 10_000:
            store.pop(next(iter(store)))
        events = deque()
        store[key] = events
        return events

    @staticmethod
    def _retry_after(events: deque[float], limit: int, now: float, window: int) -> int:
        if len(events) < limit:
            return 0
        return max(1, ceil(events[0] + window - now))

    def login_retry_after(self, identifier: str, client_key: str) -> int:
        now = self.clock()
        cutoff = now - self.login_window_seconds
        with self._lock:
            identifier_events = self._events(self._login_identifiers, identifier)
            client_events = self._events(self._login_clients, client_key)
            self._prune(identifier_events, cutoff)
            self._prune(client_events, cutoff)
            return max(
                self._retry_after(
                    identifier_events, self.login_max_failures, now, self.login_window_seconds
                ),
                self._retry_after(
                    client_events, self.login_max_failures, now, self.login_window_seconds
                ),
            )

    def record_login_failure(self, identifier: str, client_key: str) -> None:
        now = self.clock()
        cutoff = now - self.login_window_seconds
        with self._lock:
            for store, key in (
                (self._login_identifiers, identifier),
                (self._login_clients, client_key),
            ):
                events = self._events(store, key)
                self._prune(events, cutoff)
                events.append(now)

    def clear_login_identifier(self, identifier: str) -> None:
        with self._lock:
            self._login_identifiers.pop(identifier, None)

    def consume_verification_request(self, client_key: str) -> int:
        now = self.clock()
        cutoff = now - self.verification_window_seconds
        with self._lock:
            client_events = self._events(self._verification_clients, client_key)
            self._prune(client_events, cutoff)
            self._prune(self._verification_global, cutoff)
            retry_after = max(
                self._retry_after(
                    client_events,
                    self.verification_max_requests_per_ip,
                    now,
                    self.verification_window_seconds,
                ),
                self._retry_after(
                    self._verification_global,
                    self.verification_global_max_requests,
                    now,
                    self.verification_window_seconds,
                ),
            )
            if retry_after:
                return retry_after
            client_events.append(now)
            self._verification_global.append(now)
            return 0

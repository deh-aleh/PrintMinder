import hashlib
import hmac
import os
import time
from collections import defaultdict, deque


_FINGERPRINT_KEY = os.urandom(32)  # per process: fingerprints are only ever compared within one run


def password_fingerprint(password: str) -> str:
    """Lets the throttle tell "the same wrong password again" from "a new guess" without keeping the password."""
    return hmac.new(_FINGERPRINT_KEY, password.encode(), hashlib.sha256).hexdigest()[:24]


def register_failure(throttle: "Throttle", ukey: str, ikey: str, password: str) -> None:
    """Count a failed login. A client that retries the SAME wrong password (libcups does 3-5 times per
    request) counts once, so a single typo cannot lock a user out; every new guess counts."""
    dkey = f"{ukey}|{password_fingerprint(password)}"
    if throttle.blocked(dkey, 1):
        return
    throttle.fail(dkey)
    throttle.fail(ukey)
    throttle.fail(ikey)


# Failed logins tolerated per window. Keyed per (user, ip) so a stranger cannot lock someone else out;
# the per-ip ceiling is higher because one IP may legitimately be a NAT or a proxy.
USER_FAILS, IP_FAILS = 5, 30


class Throttle:
    """Sliding-window failure counter; blocks a key after `limit` failures in `window` seconds."""

    def __init__(self, limit: int, window: float, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self._fails: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str) -> deque[float]:
        q = self._fails[key]
        cutoff = self.clock() - self.window
        while q and q[0] < cutoff:
            q.popleft()
        if not q:
            self._fails.pop(key, None)
            return deque()
        return q

    def blocked(self, key: str, limit: int | None = None) -> bool:
        return len(self._prune(key)) >= (limit or self.limit)

    def fail(self, key: str) -> None:
        self._prune(key)
        self._fails[key].append(self.clock())

    def clear(self, key: str) -> None:
        self._fails.pop(key, None)

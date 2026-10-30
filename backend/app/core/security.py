"""Per-IP sliding-window rate limiter (in-memory) and filename sanitising.
LIMITATION: state is per process; on multi-instance or restarting free hosts it is NOT a global guarantee."""
import re
import time
from collections import deque
from urllib.parse import quote

_MAX_KEYS = 10_000


class RateLimiter:
    def __init__(self, per_minute: int, clock=time.monotonic):
        self.limit, self.clock, self.hits = per_minute, clock, {}

    def check(self, key: str) -> int:
        """Return 0 if allowed (and record the hit), else seconds to wait."""
        now = self.clock()
        if len(self.hits) > _MAX_KEYS:
            self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < 60}
        q = self.hits.setdefault(key, deque())
        while q and now - q[0] >= 60:
            q.popleft()
        if len(q) >= self.limit:
            return max(1, int(60 - (now - q[0])) + 1)
        q.append(now)
        return 0


def safe_filename(title: str, ext: str = "xlsx") -> tuple[str, str]:
    """Return (ascii_fallback, utf8_percent_encoded) names. No user-controlled paths."""
    base = re.sub(r"[^\w\- ]", "", title, flags=re.UNICODE).strip().replace(" ", "_")[:60] or "workbook"
    ascii_base = re.sub(r"[^A-Za-z0-9_\-]", "", base) or "workbook"
    return f"{ascii_base}.{ext}", quote(f"{base}.{ext}")


def content_disposition(title: str) -> str:
    ascii_name, utf8_name = safe_filename(title)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"

import time
from collections import defaultdict, deque

from fastapi import HTTPException


class SlidingWindow:
    """單一 API 程序內的限流（示範部署一個容器）；多副本部署時改用 Redis。"""

    def __init__(self, limit: int, seconds: int) -> None:
        self.limit, self.seconds = limit, seconds
        self.hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.seconds:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(429, "操作太頻繁，請稍後再試")
        q.append(now)

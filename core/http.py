"""统一抓取客户端。

现状是 15 个脚本各自发 HTTP，重试和退避覆盖不到一半。这里把重试、退避、
按 host 限速、磁盘缓存和结构化错误收敛到一处。

能力边界按既有脚本的真实用法划定：GBK 等非 UTF-8 编码、返回原始字节、
表单 POST、JSON POST，以及个别必须跳过证书校验的政务接口。
"""
from __future__ import annotations

import hashlib
import json as jsonlib
import random
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Union

from core.config import SETTINGS, Settings

_SSL_CONTEXT = ssl.create_default_context()
_SSL_UNVERIFIED = ssl._create_unverified_context()  # noqa: SLF001
_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# 瞬时故障才重试：超时、限流、网关错误。4xx 里的其余状态是请求本身有问题，重试无意义。
_RETRY_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
# Yahoo 对短间隔重试非常敏感：0.8s 退避会把 429 打成后续 400。这些 host 拉长间隔。
_HOST_MIN_INTERVAL = {
    "query1.finance.yahoo.com": 1.5,
    "query2.finance.yahoo.com": 1.5,
    "fc.yahoo.com": 1.5,
}


def retry_after_seconds(exc: urllib.error.HTTPError) -> Optional[float]:
    """读 Retry-After。只解析秒数；HTTP-date 太少见，交给默认长退避。"""
    raw = ""
    if exc.headers:
        raw = exc.headers.get("Retry-After") or ""
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def backoff_seconds(
    attempt: int,
    last_error: Optional[BaseException],
    base_delay: float = 0.8,
) -> float:
    """第 attempt 次失败之后、下一次尝试之前该等多久。"""
    if isinstance(last_error, urllib.error.HTTPError) and last_error.code == 429:
        hinted = retry_after_seconds(last_error)
        if hinted is not None:
            return hinted
        return min(60.0, 8.0 * (2 ** (attempt - 1))) + random.uniform(0, 0.5)
    return base_delay * (2 ** (attempt - 1)) + random.uniform(0, base_delay / 4)


class FetchError(RuntimeError):
    """抓取失败。带上 url 与最后一次底层异常，便于日志定位到具体数据源。"""

    def __init__(self, url: str, attempts: int, cause: Optional[BaseException]) -> None:
        super().__init__("请求失败（尝试 {0} 次）: {1}: {2}".format(attempts, url, cause))
        self.url = url
        self.attempts = attempts
        self.cause = cause


@dataclass
class _HostThrottle:
    min_interval: float
    last_call: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def wait(self) -> None:
        with self.lock:
            elapsed = time.monotonic() - self.last_call
            if self.last_call and elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_call = time.monotonic()


class HttpClient:
    """带重试、限速与可选磁盘缓存的 HTTP 客户端。"""

    def __init__(self, settings: Settings = SETTINGS, referer: str = "") -> None:
        self._settings = settings
        self._referer = referer
        self._throttles: Dict[str, _HostThrottle] = {}
        self._lock = threading.Lock()

    # -- 内部 --------------------------------------------------------

    def _throttle_for(self, url: str) -> _HostThrottle:
        host = urllib.parse.urlparse(url).netloc
        interval = _HOST_MIN_INTERVAL.get(host, self._settings.http_min_interval)
        with self._lock:
            if host not in self._throttles:
                self._throttles[host] = _HostThrottle(interval)
            return self._throttles[host]

    def _cache_file(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        host = urllib.parse.urlparse(url).netloc.replace(":", "_") or "unknown"
        return self._settings.http_cache_dir / host / "{0}.bin".format(digest)

    def _read_cache(self, url: str, ttl: int) -> Optional[bytes]:
        if ttl <= 0:
            return None
        path = self._cache_file(url)
        if not path.exists() or time.time() - path.stat().st_mtime > ttl:
            return None
        try:
            return path.read_bytes()
        except OSError:
            return None

    def _write_cache(self, url: str, body: bytes) -> None:
        path = self._cache_file(url)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        except OSError:
            # 缓存写失败不应该影响主流程
            pass

    @staticmethod
    def _encode_body(
        data: Union[bytes, str, Dict[str, Any], None],
        json_body: Any,
        headers: Dict[str, str],
    ) -> Optional[bytes]:
        if json_body is not None:
            headers.setdefault("Content-Type", "application/json")
            return jsonlib.dumps(json_body, ensure_ascii=False).encode("utf-8")
        if data is None:
            return None
        if isinstance(data, bytes):
            return data
        if isinstance(data, str):
            return data.encode("utf-8")
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        return urllib.parse.urlencode(data).encode("utf-8")

    def _request(
        self,
        url: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        data: Union[bytes, str, Dict[str, Any], None] = None,
        json_body: Any = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        attempts: Optional[int] = None,
        cache_ttl: int = 0,
        verify_ssl: bool = True,
    ) -> bytes:
        if params:
            sep = "&" if "?" in url else "?"
            url = url + sep + urllib.parse.urlencode(params)

        cacheable = method == "GET" and cache_ttl > 0
        if cacheable:
            cached = self._read_cache(url, cache_ttl)
            if cached is not None:
                return cached

        request_headers: Dict[str, str] = {"User-Agent": _DEFAULT_UA}
        if self._referer:
            request_headers["Referer"] = self._referer
        if headers:
            request_headers.update(headers)
        body = self._encode_body(data, json_body, request_headers)

        request = urllib.request.Request(
            url, data=body, headers=request_headers, method=method
        )
        context = _SSL_CONTEXT if verify_ssl else _SSL_UNVERIFIED
        max_attempts = max(1, attempts or self._settings.http_attempts)
        wait = timeout or self._settings.http_timeout
        throttle = self._throttle_for(url)
        last_error: Optional[BaseException] = None
        base_delay = 0.8

        for attempt in range(1, max_attempts + 1):
            throttle.wait()
            try:
                with urllib.request.urlopen(
                    request, context=context, timeout=wait
                ) as response:
                    payload = response.read()
                if not payload.strip():
                    raise ValueError("响应为空")
                if cacheable:
                    self._write_cache(url, payload)
                return payload
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in _RETRY_STATUS:
                    raise FetchError(url, attempt, exc) from exc
            except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as exc:
                last_error = exc
            if attempt < max_attempts:
                time.sleep(backoff_seconds(attempt, last_error, base_delay))

        raise FetchError(url, max_attempts, last_error)

    # -- GET ---------------------------------------------------------

    def get_bytes(self, url: str, **kwargs: Any) -> bytes:
        return self._request(url, method="GET", **kwargs)

    def get(self, url: str, encoding: str = "utf-8", **kwargs: Any) -> str:
        """文本 GET。encoding 支持 gbk 等非 UTF-8 站点。"""
        return self._request(url, method="GET", **kwargs).decode(encoding, errors="replace")

    def get_json(self, url: str, encoding: str = "utf-8", **kwargs: Any) -> Any:
        body = self.get(url, encoding=encoding, **kwargs)
        try:
            return jsonlib.loads(body)
        except jsonlib.JSONDecodeError as exc:
            raise FetchError(url, 1, exc) from exc

    # -- POST --------------------------------------------------------

    def post_bytes(self, url: str, **kwargs: Any) -> bytes:
        return self._request(url, method="POST", **kwargs)

    def post(self, url: str, encoding: str = "utf-8", **kwargs: Any) -> str:
        return self.post_bytes(url, **kwargs).decode(encoding, errors="replace")

    def post_json(self, url: str, encoding: str = "utf-8", **kwargs: Any) -> Any:
        body = self.post(url, encoding=encoding, **kwargs)
        try:
            return jsonlib.loads(body)
        except jsonlib.JSONDecodeError as exc:
            raise FetchError(url, 1, exc) from exc


DEFAULT_CLIENT = HttpClient(referer="https://finance.qq.com/")

"""只读 http/https。内网、本机和超大响应在打开前停下。"""
from __future__ import annotations

import hashlib
import ipaddress
import os
import socket
import urllib.error
import urllib.request
from datetime import datetime
from urllib.parse import urlparse, urlunparse

from core.context.temporal import CN_TZ
from core.research.source_guard import markers

MAX_BYTES = 2_000_000
TIMEOUT = 12
MAX_REDIRECTS = 3
ALLOWED_TYPES = (
    "text/html",
    "text/plain",
    "application/xhtml+xml",
    "application/pdf",
    "application/octet-stream",
)
_BLOCKED_HOSTS = {"localhost", "localhost.localdomain"}


class SSRFError(Exception):
    pass


def network_mode() -> str:
    raw = (os.environ.get("RESEARCH_NETWORK_MODE") or "").strip().lower()
    if raw in ("live", "replay"):
        return raw
    return "replay"


def canonical_url(url: str) -> str:
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if parsed.port and parsed.port not in (80, 443):
        host = "{0}:{1}".format(host, parsed.port)
    scheme = (parsed.scheme or "").lower()
    return urlunparse((scheme, host, parsed.path or "/", "", parsed.query, ""))


def guard_url(url: str) -> dict:
    parsed = urlparse((url or "").strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return _blocked("只允许 http 和 https。")
    host = parsed.hostname or ""
    if not host or _host_blocked(host):
        return _blocked("地址不在允许范围。")
    return {"ok": True, "url": url, "host": host}


def resolve_blocked(host: str) -> bool:
    if _host_blocked(host):
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return True
        if _ip_blocked(ip):
            return True
    return False


def read_url(url: str, *, transport=None, live: bool = False, max_bytes: int = MAX_BYTES, timeout: int = TIMEOUT) -> dict:
    checked = guard_url(url)
    if not checked["ok"]:
        return checked
    if transport is None and not live:
        return {
            "ok": False,
            "error_code": "SOURCE_READ_FAILED",
            "message": "外网页面这轮不在夹具里打开。",
            "url": url,
        }
    if transport is None and resolve_blocked(checked["host"]):
        return _blocked("解析到了内网地址。")
    try:
        payload = transport(url) if transport is not None else _http_get(url, timeout=timeout, max_bytes=max_bytes)
    except SSRFError as exc:
        return _blocked(str(exc))
    if payload.get("error_code"):
        return payload
    body = payload.get("body") or b""
    if isinstance(body, str):
        body = body.encode("utf-8")
    if len(body) > max_bytes:
        return {
            "ok": False,
            "error_code": "SOURCE_TOO_LARGE",
            "message": "响应超过上限。",
            "url": url,
        }
    content_type = (payload.get("content_type") or "").split(";")[0].strip().lower()
    if content_type and content_type not in ALLOWED_TYPES and not body.startswith(b"%PDF"):
        return {
            "ok": False,
            "error_code": "SOURCE_UNREADABLE",
            "message": "内容类型不在允许范围。",
            "url": url,
        }
    from core.research.tools.reader import parse_download

    final_url = payload.get("final_url") or url
    parsed = parse_download(body, content_type or _sniff(body), final_url)
    if not parsed.get("ok"):
        parsed["url"] = final_url
        return parsed
    text = parsed.get("text") or ""
    parsed.update({
        "url": final_url,
        "canonical_url": canonical_url(final_url),
        "retrieved_at": datetime.now(CN_TZ).isoformat(timespec="seconds"),
        "content_type": content_type or parsed.get("content_type") or "",
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "injection_markers": markers(text),
    })
    return parsed


def _http_get(url: str, *, timeout: int, max_bytes: int) -> dict:
    class _Guard(urllib.request.HTTPRedirectHandler):
        max_redirections = MAX_REDIRECTS

        def redirect_request(self, req, fp, code, msg, headers, newurl):
            checked = guard_url(newurl)
            if not checked["ok"] or resolve_blocked(checked.get("host") or ""):
                raise SSRFError("重定向到了不允许的地址。")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = urllib.request.build_opener(_Guard)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; ResearchWorkspace/1.0)"},
    )
    try:
        response = opener.open(request, timeout=timeout)
    except SSRFError:
        raise
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "error_code": "SOURCE_UNREADABLE",
            "message": "页面返回 {0}。".format(exc.code),
            "url": url,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error_code": "SOURCE_UNREADABLE",
            "message": str(exc),
            "url": url,
        }
    final_url = url
    content_type = ""
    status = 200
    chunks = []
    try:
        total = 0
        while True:
            block = response.read(65536)
            if not block:
                break
            total += len(block)
            if total > max_bytes:
                return {
                    "ok": False,
                    "error_code": "SOURCE_TOO_LARGE",
                    "message": "响应超过上限。",
                    "url": url,
                }
            chunks.append(block)
        final_url = response.geturl() or url
        content_type = response.headers.get("Content-Type") or ""
        status = getattr(response, "status", 200) or 200
    finally:
        response.close()
    checked = guard_url(final_url)
    if not checked["ok"] or resolve_blocked(checked.get("host") or ""):
        return _blocked("最终地址不在允许范围。")
    return {
        "status": status,
        "content_type": content_type,
        "body": b"".join(chunks),
        "final_url": final_url,
    }


def _host_blocked(host: str) -> bool:
    name = (host or "").strip("[]").lower().rstrip(".")
    if name in _BLOCKED_HOSTS or name.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(name)
    except ValueError:
        return False
    return _ip_blocked(ip)


def _ip_blocked(ip: ipaddress._BaseAddress) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _blocked(message: str) -> dict:
    return {"ok": False, "error_code": "SSRF_BLOCKED", "message": message}


def _sniff(body: bytes) -> str:
    if body.startswith(b"%PDF"):
        return "application/pdf"
    return "text/html"

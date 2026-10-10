"""打开本地或允许的网页。登录墙、付费墙和验证码直接停。"""
from __future__ import annotations

import re
from pathlib import Path

from core.config import ROOT

_BLOCKED = ("captcha", "paywall", "please log in", "please login", "access denied")


def read_html(path: str, *, allow_network: bool = False) -> dict:
    target = _resolve(path, allow_network)
    if target.get("error_code"):
        return target
    raw = target["raw"]
    title = _tag(raw, "title") or _tag(raw, "h1")
    canonical = _canonical(raw) or path
    publisher = _meta(raw, "author") or ""
    published = _meta(raw, "article:published_time") or ""
    text = _article_text(raw)
    if _blocked(raw, text):
        return {
            "ok": False,
            "error_code": "SOURCE_READ_FAILED",
            "message": "页面是登录、付费或验证码，没有绕过。",
            "url": path,
        }
    if not text:
        return {
            "ok": False,
            "error_code": "SOURCE_READ_FAILED",
            "message": "页面没有可读正文。",
            "url": path,
        }
    return {
        "ok": True,
        "title": title,
        "url": canonical,
        "publisher": publisher,
        "published_at": published,
        "text": text,
        "raw": raw,
        "marked": marked_claims(raw),
    }


def marked_claims(raw: str) -> list:
    rows = []
    for index, match in enumerate(re.finditer(
        r"<p([^>]*)>(.*?)</p>",
        raw,
        flags=re.I | re.S,
    ), start=1):
        attrs = match.group(1)
        kind = re.search(r'data-claim="(FACT|ESTIMATE|INFERENCE|OPINION)"', attrs, flags=re.I)
        if not kind:
            continue
        text = _strip(match.group(2))
        premise = re.search(r'data-premise="([^"]+)"', attrs)
        if text:
            rows.append({
                "claim_type": kind.group(1).upper(),
                "text": text,
                "location": "p{0}".format(index),
                "premise_claim_ids": [item for item in (premise.group(1).split() if premise else []) if item],
            })
    return rows


def read_pdf(path: str) -> dict:
    target = Path(path)
    if not target.is_file():
        return {"ok": False, "error_code": "PDF_PARSE_FAILED", "message": "PDF 不存在：{0}".format(path)}
    data = target.read_bytes()
    if data.startswith(b"%PDF-TEXT"):
        return _marked_pdf(data.decode("utf-8", errors="replace"), path)
    try:
        from pypdf import PdfReader
    except ImportError:
        return {
            "ok": False,
            "error_code": "PDF_PARSE_FAILED",
            "message": "未安装 PDF 解析。不能把模型记忆写成某一页的原文。",
        }
    try:
        reader = PdfReader(str(target))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error_code": "PDF_PARSE_FAILED", "message": str(exc)}
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        pages.append({"page": index, "text": page.extract_text() or ""})
    return {"ok": True, "url": path, "title": target.stem, "pages": pages}


def parse_download(body: bytes, content_type: str, url: str) -> dict:
    """把下载字节收成统一正文。PDF 保留页码。"""
    if "pdf" in (content_type or "") or body.startswith(b"%PDF"):
        if body.startswith(b"%PDF-TEXT"):
            parsed = _marked_pdf(body.decode("utf-8", errors="replace"), url)
        else:
            parsed = _pdf_bytes(body, url)
        if not parsed.get("ok"):
            return parsed
        pages = parsed.get("pages") or []
        parsed["text"] = "\n".join(page.get("text") or "" for page in pages)
        parsed["content_type"] = "application/pdf"
        parsed["publisher"] = ""
        parsed["published_at"] = ""
        return parsed
    raw = body.decode("utf-8", errors="replace")
    title = _tag(raw, "title") or _tag(raw, "h1")
    text = _article_text(raw)
    if _blocked(raw, text):
        return {"ok": False, "error_code": "SOURCE_UNREADABLE", "message": "页面是登录、付费或验证码，没有绕过。", "url": url}
    if not text:
        return {"ok": False, "error_code": "SOURCE_UNREADABLE", "message": "页面没有可读正文。", "url": url}
    return {
        "ok": True,
        "title": title,
        "publisher": _meta(raw, "author") or "",
        "published_at": _meta(raw, "article:published_time") or "",
        "text": text,
        "raw": raw,
        "content_type": "text/html",
        "pages": [],
    }


def _pdf_bytes(body: bytes, url: str) -> dict:
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"ok": False, "error_code": "PDF_PARSE_FAILED", "message": "未安装 PDF 解析。不能把模型记忆写成某一页的原文。"}
    try:
        from io import BytesIO
        reader = PdfReader(BytesIO(body))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error_code": "PDF_PARSE_FAILED", "message": str(exc)}
    pages = [{"page": index, "text": page.extract_text() or ""} for index, page in enumerate(reader.pages, start=1)]
    return {"ok": True, "url": url, "title": "", "pages": pages}


def _marked_pdf(text: str, path: str) -> dict:
    pages = []
    current = None
    buf: list = []
    for line in text.splitlines():
        match = re.match(r"%%PAGE\s+(\d+)", line.strip())
        if match:
            if current is not None:
                pages.append({"page": current, "text": "\n".join(buf).strip()})
            current = int(match.group(1))
            buf = []
            continue
        buf.append(line)
    if current is not None:
        pages.append({"page": current, "text": "\n".join(buf).strip()})
    if not pages:
        return {"ok": False, "error_code": "PDF_PARSE_FAILED", "message": "没有页码。"}
    return {"ok": True, "url": path, "title": Path(path).stem, "pages": pages}


def _resolve(path: str, allow_network: bool) -> dict:
    if path.startswith("http://") or path.startswith("https://"):
        if not allow_network:
            return {
                "ok": False,
                "error_code": "SOURCE_READ_FAILED",
                "message": "这一轮没有打开外网。",
            }
        return {
            "ok": False,
            "error_code": "SOURCE_READ_FAILED",
            "message": "外网页面这轮不在夹具里打开。",
        }
    target = Path(path)
    if not target.is_absolute():
        target = ROOT / path
    if not target.is_file():
        return {"ok": False, "error_code": "SOURCE_READ_FAILED", "message": "打不开：{0}".format(path)}
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error_code": "SOURCE_READ_FAILED", "message": str(exc)}
    return {"raw": raw}


def _blocked(raw: str, text: str) -> bool:
    lowered = raw.lower()
    if any(token in lowered for token in _BLOCKED) and len(text) < 80:
        return True
    if "403" in lowered and "forbidden" in lowered and len(text) < 80:
        return True
    return False


def _article_text(raw: str) -> str:
    match = re.search(r"<article[\s\S]*?</article>", raw, flags=re.I)
    chunk = match.group(0) if match else raw
    chunk = re.sub(r"<nav[\s\S]*?</nav>", " ", chunk, flags=re.I)
    chunk = re.sub(r"<script[\s\S]*?</script>", " ", chunk, flags=re.I)
    return _strip(chunk)


def _strip(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", text).strip()


def _tag(raw: str, name: str) -> str:
    match = re.search(r"<{0}[^>]*>(.*?)</{0}>".format(name), raw, flags=re.I | re.S)
    return _strip(match.group(1)) if match else ""


def _canonical(raw: str) -> str:
    match = re.search(r'<link[^>]*rel="canonical"[^>]*href="([^"]+)"', raw, flags=re.I)
    return match.group(1) if match else ""


def _meta(raw: str, name: str) -> str:
    match = re.search(
        r'<meta[^>]*(?:name|property)="{0}"[^>]*content="([^"]+)"'.format(re.escape(name)),
        raw,
        flags=re.I,
    )
    return match.group(1) if match else ""

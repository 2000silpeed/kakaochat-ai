"""링크 아카이브 — URL 스크래핑 + LLM 요약 + 방별 저장/검색."""
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import get_config

logger = logging.getLogger("kakaochat.link_archive")

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_LINKS_FILE = _DATA_DIR / "links.jsonl"

SCRAPE_TIMEOUT = 10
MAX_CONTENT_LENGTH = 3000


@dataclass
class ArchivedLink:
    room: str
    sender: str
    url: str
    title: str
    summary: str
    ts: int
    archived_at: float


async def scrape_url(url: str) -> tuple[str, str]:
    """URL에서 제목과 본문 텍스트 추출. 실패 시 ('', '')."""
    try:
        async with httpx.AsyncClient(
            timeout=SCRAPE_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "KakaoChat-AI/1.0 LinkArchiver"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type:
            logger.debug(f"Non-HTML content: {content_type}")
            return ("", "")

        html = resp.text

        title = _extract_title(html)
        body = _extract_body_text(html)

        return (title, body[:MAX_CONTENT_LENGTH])

    except httpx.TimeoutException:
        logger.warning(f"Scrape timeout: {url}")
        return ("", "")
    except Exception:
        logger.warning(f"Scrape failed: {url}", exc_info=True)
        return ("", "")


def _extract_title(html: str) -> str:
    """HTML에서 <title> 추출 (외부 파서 없이)."""
    import re
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if match:
        title = match.group(1).strip()
        title = re.sub(r"<[^>]+>", "", title)
        title = re.sub(r"\s+", " ", title).strip()
        return title[:200]
    return ""


def _extract_body_text(html: str) -> str:
    """HTML에서 본문 텍스트 추출 (경량 파싱)."""
    import re
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def summarize_content(title: str, body: str, url: str) -> str:
    """LLM으로 링크 내용 요약. 실패 시 title만 반환."""
    if not body and not title:
        return ""

    cfg = get_config()
    model = cfg["llm"]["model"]

    prompt = (
        "다음 웹페이지 내용을 한국어 1-2문장으로 요약해줘. "
        "핵심 정보만 간결하게.\n\n"
        f"제목: {title}\n"
        f"URL: {url}\n"
        f"본문: {body[:2000]}"
    )

    try:
        if model.startswith("gemini/"):
            return await _summarize_gemini(prompt, model, cfg)
        elif model.startswith("openai/"):
            return await _summarize_openai(prompt, model, cfg)
        elif model.startswith("openrouter/"):
            return await _summarize_openrouter(prompt, model, cfg)
        elif model.startswith("claude/"):
            return title or url
    except Exception:
        logger.warning("LLM summarization failed", exc_info=True)

    return title or url


async def _summarize_gemini(prompt: str, model: str, cfg: dict) -> str:
    import os
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return ""

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model.removeprefix("gemini/"),
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=200,
        ),
    )
    if response and response.text:
        return response.text.strip()
    return ""


async def _summarize_openai(prompt: str, model: str, cfg: dict) -> str:
    import os
    import openai

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return ""

    client = openai.AsyncOpenAI(api_key=api_key)
    response = await client.chat.completions.create(
        model=model.removeprefix("openai/"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=200,
    )
    if response.choices:
        return response.choices[0].message.content.strip()
    return ""


async def _summarize_openrouter(prompt: str, model: str, cfg: dict) -> str:
    import os
    import openai

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return ""

    client = openai.AsyncOpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )
    response = await client.chat.completions.create(
        model=model.removeprefix("openrouter/"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=200,
    )
    if response.choices:
        return response.choices[0].message.content.strip()
    return ""


def save_link(link: ArchivedLink):
    """아카이브된 링크를 JSONL에 저장."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "room": link.room,
        "sender": link.sender,
        "url": link.url,
        "title": link.title,
        "summary": link.summary,
        "ts": link.ts,
        "archived_at": link.archived_at,
    }
    with open(_LINKS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


async def archive_links(room: str, sender: str, urls: list[str], ts: int) -> list[ArchivedLink]:
    """URL 리스트를 스크래핑 + 요약 + 저장. 아카이브된 링크 반환."""
    archived = []
    for url in urls:
        if _is_already_archived(url, room):
            logger.debug(f"Already archived: {url}")
            continue

        title, body = await scrape_url(url)
        summary = await summarize_content(title, body, url)

        link = ArchivedLink(
            room=room,
            sender=sender,
            url=url,
            title=title or url,
            summary=summary or title or url,
            ts=ts,
            archived_at=time.time(),
        )
        save_link(link)
        archived.append(link)
        logger.info(f"Link archived: {url} -> {title[:50] if title else '(no title)'}")

    return archived


def _is_already_archived(url: str, room: str) -> bool:
    """같은 방에서 같은 URL이 이미 아카이브되었는지 체크."""
    if not _LINKS_FILE.exists():
        return False
    with open(_LINKS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("url") == url and data.get("room") == room:
                    return True
            except json.JSONDecodeError:
                continue
    return False


def search_links(room: str, query: str, limit: int = 5) -> list[dict]:
    """방의 아카이브된 링크에서 키워드 검색."""
    if not _LINKS_FILE.exists():
        return []

    results = []
    query_lower = query.lower()
    with open(_LINKS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("room") != room:
                    continue
                searchable = f"{data.get('title', '')} {data.get('summary', '')} {data.get('url', '')}".lower()
                if query_lower in searchable:
                    results.append(data)
            except json.JSONDecodeError:
                continue

    results.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return results[:limit]


def get_recent_links(room: str, days: int = 7, limit: int = 10) -> list[dict]:
    """방의 최근 N일간 아카이브된 링크 반환."""
    if not _LINKS_FILE.exists():
        return []

    cutoff = time.time() - (days * 86400)
    results = []
    with open(_LINKS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("room") != room:
                    continue
                if data.get("archived_at", 0) >= cutoff:
                    results.append(data)
            except json.JSONDecodeError:
                continue

    results.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return results[:limit]


def format_link_context(links: list[dict]) -> str:
    """링크 목록을 LLM 컨텍스트 문자열로 포맷."""
    if not links:
        return ""
    lines = []
    for link in links:
        sender = link.get("sender", "")
        title = link.get("title", "")
        url = link.get("url", "")
        summary = link.get("summary", "")
        lines.append(f"- [{title}]({url}) (by {sender}): {summary}")
    return "\n".join(lines)

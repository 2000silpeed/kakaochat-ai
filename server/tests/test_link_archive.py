"""링크 아카이브 테스트."""
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.config import load_config
from app.link_archive import (
    ArchivedLink,
    save_link,
    search_links,
    get_recent_links,
    format_link_context,
    _extract_title,
    _extract_body_text,
    _is_already_archived,
    _LINKS_FILE,
)

load_config()


@pytest.fixture(autouse=True)
def clean_links_file(tmp_path, monkeypatch):
    """매 테스트마다 임시 links.jsonl 사용."""
    test_file = tmp_path / "links.jsonl"
    monkeypatch.setattr("app.link_archive._LINKS_FILE", test_file)
    monkeypatch.setattr("app.link_archive._DATA_DIR", tmp_path)
    return test_file


class TestExtractTitle:
    def test_basic_title(self):
        html = "<html><head><title>Test Page</title></head><body></body></html>"
        assert _extract_title(html) == "Test Page"

    def test_no_title(self):
        html = "<html><body>no title here</body></html>"
        assert _extract_title(html) == ""

    def test_title_with_whitespace(self):
        html = "<title>  Spaced   Title  </title>"
        assert _extract_title(html) == "Spaced Title"

    def test_title_with_nested_tags(self):
        html = "<title><span>Nested</span> Title</title>"
        assert _extract_title(html) == "Nested Title"


class TestExtractBodyText:
    def test_strips_tags(self):
        html = "<p>Hello</p><p>World</p>"
        assert "Hello" in _extract_body_text(html)
        assert "World" in _extract_body_text(html)

    def test_strips_scripts(self):
        html = "<script>alert('x')</script><p>Content</p>"
        result = _extract_body_text(html)
        assert "alert" not in result
        assert "Content" in result

    def test_strips_styles(self):
        html = "<style>body{color:red}</style><p>Content</p>"
        result = _extract_body_text(html)
        assert "color" not in result
        assert "Content" in result


class TestSaveAndSearch:
    def test_save_link(self, clean_links_file):
        link = ArchivedLink(
            room="AI스터디", sender="철수",
            url="https://example.com/rag",
            title="RAG Tutorial",
            summary="RAG 파이프라인 구축 가이드",
            ts=1712600000, archived_at=time.time(),
        )
        save_link(link)

        with open(clean_links_file) as f:
            data = json.loads(f.readline())
        assert data["url"] == "https://example.com/rag"
        assert data["room"] == "AI스터디"

    def test_search_by_keyword(self, clean_links_file):
        for i, (title, url) in enumerate([
            ("RAG Tutorial", "https://example.com/rag"),
            ("Docker Guide", "https://example.com/docker"),
        ]):
            save_link(ArchivedLink(
                room="AI스터디", sender="철수",
                url=url, title=title,
                summary=f"{title} summary",
                ts=1712600000 + i, archived_at=time.time(),
            ))

        results = search_links("AI스터디", "RAG")
        assert len(results) == 1
        assert results[0]["title"] == "RAG Tutorial"

    def test_search_room_isolation(self, clean_links_file):
        save_link(ArchivedLink(
            room="AI스터디", sender="철수",
            url="https://example.com/a",
            title="Link A", summary="A",
            ts=1712600000, archived_at=time.time(),
        ))
        save_link(ArchivedLink(
            room="개발방", sender="영희",
            url="https://example.com/b",
            title="Link B", summary="B",
            ts=1712600001, archived_at=time.time(),
        ))

        results = search_links("AI스터디", "Link")
        assert len(results) == 1
        assert results[0]["room"] == "AI스터디"

    def test_search_empty(self, clean_links_file):
        assert search_links("AI스터디", "없는키워드") == []


class TestGetRecentLinks:
    def test_recent_links(self, clean_links_file):
        now = time.time()
        save_link(ArchivedLink(
            room="AI스터디", sender="철수",
            url="https://example.com/recent",
            title="Recent", summary="최근",
            ts=int(now * 1000), archived_at=now,
        ))
        save_link(ArchivedLink(
            room="AI스터디", sender="영희",
            url="https://example.com/old",
            title="Old", summary="오래된",
            ts=int((now - 86400 * 30) * 1000),
            archived_at=now - 86400 * 30,
        ))

        results = get_recent_links("AI스터디", days=7)
        assert len(results) == 1
        assert results[0]["title"] == "Recent"

    def test_empty_room(self, clean_links_file):
        assert get_recent_links("빈방") == []


class TestIsAlreadyArchived:
    def test_not_archived(self, clean_links_file):
        assert not _is_already_archived("https://new.com", "AI스터디")

    def test_already_archived(self, clean_links_file):
        save_link(ArchivedLink(
            room="AI스터디", sender="철수",
            url="https://dup.com", title="Dup", summary="중복",
            ts=1712600000, archived_at=time.time(),
        ))
        assert _is_already_archived("https://dup.com", "AI스터디")

    def test_different_room_not_duplicate(self, clean_links_file):
        save_link(ArchivedLink(
            room="AI스터디", sender="철수",
            url="https://dup.com", title="Dup", summary="중복",
            ts=1712600000, archived_at=time.time(),
        ))
        assert not _is_already_archived("https://dup.com", "개발방")


class TestFormatLinkContext:
    def test_format(self):
        links = [
            {"sender": "철수", "title": "RAG Guide", "url": "https://ex.com/rag", "summary": "RAG 요약"},
        ]
        result = format_link_context(links)
        assert "RAG Guide" in result
        assert "https://ex.com/rag" in result
        assert "철수" in result

    def test_empty(self):
        assert format_link_context([]) == ""

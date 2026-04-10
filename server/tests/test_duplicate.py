"""v0.3: 중복 질문 감지 테스트."""
from unittest.mock import patch

import pytest

from app.config import load_config
from app.duplicate import check_duplicate, format_duplicate_response, DuplicateResult

load_config()


class TestCheckDuplicate:
    """중복 질문 감지 로직 테스트."""

    @patch("app.duplicate.search_memory")
    def test_duplicate_detected_above_threshold(self, mock_search):
        mock_search.return_value = [
            {
                "memory": "철수: RAG 파이프라인 구축할 때 청킹이 제일 중요해",
                "score": 0.95,
                "metadata": {"sender": "철수", "ts": 1712000000},
            }
        ]
        result = check_duplicate("RAG 파이프라인 어떻게 구축해?", "AI스터디")
        assert result is not None
        assert result.score >= 0.9
        assert result.sender == "철수"
        assert "RAG" in result.original_text

    @patch("app.duplicate.search_memory")
    def test_no_duplicate_below_threshold(self, mock_search):
        mock_search.return_value = [
            {
                "memory": "영희: Docker 컨테이너 관리법 공유",
                "score": 0.6,
                "metadata": {"sender": "영희", "ts": 1712000000},
            }
        ]
        result = check_duplicate("RAG 파이프라인 어떻게 구축해?", "AI스터디")
        assert result is None

    @patch("app.duplicate.search_memory")
    def test_no_duplicate_empty_results(self, mock_search):
        mock_search.return_value = []
        result = check_duplicate("새로운 질문이에요?", "AI스터디")
        assert result is None

    @patch("app.duplicate.search_memory")
    def test_duplicate_with_dict_results(self, mock_search):
        """Mem0가 {"results": [...]} 형태로 반환하는 경우."""
        mock_search.return_value = {
            "results": [
                {
                    "memory": "민수: Gemini API 호출 예제 코드 공유함",
                    "score": 0.92,
                    "metadata": {"sender": "민수", "ts": 1712100000},
                }
            ]
        }
        result = check_duplicate("Gemini API 어떻게 호출해?", "AI스터디")
        assert result is not None
        assert result.sender == "민수"

    @patch("app.duplicate.search_memory")
    def test_boundary_score_exact_threshold(self, mock_search):
        """threshold 정확히 0.9인 경우 → 중복 판정."""
        mock_search.return_value = [
            {
                "memory": "이전 답변",
                "score": 0.9,
                "metadata": {"sender": "유저", "ts": 1000},
            }
        ]
        result = check_duplicate("비슷한 질문", "방")
        assert result is not None

    @patch("app.duplicate.search_memory")
    def test_boundary_score_just_below(self, mock_search):
        """threshold 바로 아래 0.89 → 중복 아님."""
        mock_search.return_value = [
            {
                "memory": "이전 답변",
                "score": 0.89,
                "metadata": {"sender": "유저", "ts": 1000},
            }
        ]
        result = check_duplicate("비슷한 질문", "방")
        assert result is None

    @patch("app.duplicate.search_memory")
    def test_multiple_results_first_match(self, mock_search):
        """여러 결과 중 첫 번째 매칭."""
        mock_search.return_value = [
            {
                "memory": "첫 번째 (높은 점수)",
                "score": 0.95,
                "metadata": {"sender": "A", "ts": 1000},
            },
            {
                "memory": "두 번째 (낮은 점수)",
                "score": 0.7,
                "metadata": {"sender": "B", "ts": 2000},
            },
        ]
        result = check_duplicate("질문", "방")
        assert result is not None
        assert result.sender == "A"

    @patch("app.duplicate.search_memory")
    def test_missing_metadata_fields(self, mock_search):
        """metadata에 sender/ts가 없는 경우 기본값 처리."""
        mock_search.return_value = [
            {
                "memory": "과거 답변",
                "score": 0.95,
                "metadata": {},
            }
        ]
        result = check_duplicate("질문", "방")
        assert result is not None
        assert result.sender == ""
        assert result.ts == 0


class TestFormatDuplicateResponse:
    def test_format_with_sender(self):
        dup = DuplicateResult(
            original_text="RAG는 청킹이 핵심이야",
            score=0.95,
            sender="철수",
            ts=1712000000,
        )
        response = format_duplicate_response(dup)
        assert "철수님" in response
        assert "RAG는 청킹이 핵심이야" in response

    def test_format_without_sender(self):
        dup = DuplicateResult(
            original_text="이전 답변 내용",
            score=0.91,
            sender="",
            ts=1000,
        )
        response = format_duplicate_response(dup)
        assert "이전에" in response
        assert "이전 답변 내용" in response

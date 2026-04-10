"""v0.4: Weekly Digest 테스트."""
import time

import pytest

from app.config import load_config
from app.digest import (
    record_signal,
    get_weekly_signals,
    _build_digest_prompt,
    generate_digest,
    clear_old_signals,
    reset_signals,
    SignalEntry,
)

load_config()


def _now_ms():
    return int(time.time() * 1000)


def _old_ms(days: int):
    return int((time.time() - days * 86400) * 1000)


class TestRecordSignal:
    def setup_method(self):
        reset_signals()

    def test_record_and_retrieve(self):
        record_signal("AI스터디", "철수", "RAG 파이프라인 꿀팁", _now_ms(), "signal", 5, ["rag"])
        signals = get_weekly_signals("AI스터디")
        assert len(signals) == 1
        assert signals[0].sender == "철수"
        assert signals[0].msg_type == "signal"

    def test_record_til(self):
        record_signal("AI스터디", "영희", "TIL: ChromaDB에서 메타데이터 필터링", _now_ms(), "til", 6, ["chromadb"])
        signals = get_weekly_signals("AI스터디")
        assert len(signals) == 1
        assert signals[0].msg_type == "til"
        assert "chromadb" in signals[0].topics

    def test_multiple_signals(self):
        record_signal("AI스터디", "철수", "RAG 팁", _now_ms(), "signal", 5, ["rag"])
        record_signal("AI스터디", "영희", "LLM 인사이트", _now_ms(), "signal", 3, ["llm"])
        record_signal("AI스터디", "민수", "TIL: Docker 팁", _now_ms(), "til", 6, ["docker"])
        signals = get_weekly_signals("AI스터디")
        assert len(signals) == 3


class TestGetWeeklySignals:
    def setup_method(self):
        reset_signals()

    def test_filter_by_room(self):
        record_signal("AI스터디", "철수", "RAG 팁", _now_ms(), "signal", 5, ["rag"])
        record_signal("개발방", "영희", "Python 팁", _now_ms(), "signal", 4, ["python"])
        signals = get_weekly_signals(room="AI스터디")
        assert len(signals) == 1
        assert signals[0].room == "AI스터디"

    def test_all_rooms(self):
        record_signal("AI스터디", "철수", "RAG 팁", _now_ms(), "signal", 5, ["rag"])
        record_signal("개발방", "영희", "Python 팁", _now_ms(), "signal", 4, ["python"])
        signals = get_weekly_signals(room=None)
        assert len(signals) == 2

    def test_exclude_old_signals(self):
        record_signal("AI스터디", "철수", "오래된 팁", _old_ms(10), "signal", 5, ["rag"])
        record_signal("AI스터디", "영희", "최근 팁", _now_ms(), "signal", 4, ["llm"])
        signals = get_weekly_signals("AI스터디", days=7)
        assert len(signals) == 1
        assert signals[0].sender == "영희"

    def test_sorted_by_score(self):
        record_signal("AI스터디", "A", "낮은 점수", _now_ms(), "signal", 3, [])
        record_signal("AI스터디", "B", "높은 점수", _now_ms(), "signal", 8, [])
        record_signal("AI스터디", "C", "중간 점수", _now_ms(), "signal", 5, [])
        signals = get_weekly_signals("AI스터디")
        scores = [s.signal_score for s in signals]
        assert scores == sorted(scores, reverse=True)

    def test_empty_file(self):
        signals = get_weekly_signals("AI스터디")
        assert signals == []


class TestBuildDigestPrompt:
    def test_prompt_contains_signals(self):
        signals = [
            SignalEntry("AI스터디", "철수", "RAG 파이프라인 최적화 방법", _now_ms(), "signal", 5, ["rag"]),
            SignalEntry("AI스터디", "영희", "TIL: 프롬프트 엔지니어링 핵심", _now_ms(), "til", 6, ["prompt"]),
        ]
        prompt = _build_digest_prompt(signals, "AI스터디")
        assert "AI스터디" in prompt
        assert "철수" in prompt
        assert "영희" in prompt
        assert "RAG" in prompt
        assert "TIL" in prompt

    def test_prompt_format(self):
        signals = [
            SignalEntry("AI스터디", "철수", "테스트 메시지", _now_ms(), "signal", 5, ["python"]),
        ]
        prompt = _build_digest_prompt(signals, "AI스터디")
        assert "1." in prompt
        assert "📌 시그널" in prompt


class TestGenerateDigest:
    def setup_method(self):
        reset_signals()

    @pytest.mark.asyncio
    async def test_skip_insufficient_signals(self):
        record_signal("AI스터디", "철수", "RAG 팁", _now_ms(), "signal", 5, ["rag"])
        result = await generate_digest("AI스터디")
        assert result is None  # min_signals=3, only 1


class TestClearOldSignals:
    def setup_method(self):
        reset_signals()

    def test_clear_old_keep_recent(self):
        record_signal("AI스터디", "철수", "오래된 시그널", _old_ms(35), "signal", 5, [])
        record_signal("AI스터디", "영희", "최근 시그널", _now_ms(), "signal", 4, [])
        clear_old_signals(days=30)
        signals = get_weekly_signals(room=None, days=365)
        assert len(signals) == 1
        assert signals[0].sender == "영희"

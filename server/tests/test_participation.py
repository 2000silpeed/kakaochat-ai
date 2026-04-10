"""Phase 3: 참여 엔진 테스트."""
import time
import pytest

from app.config import load_config
from app.participation import (
    detect_mention,
    detect_question,
    classify_trigger,
    _check_rate_limit,
    _record_response,
    reset_consecutive,
    _response_timestamps,
)
import app.participation as participation_module

load_config()


class TestMentionDetection:
    def test_at_ai(self):
        assert detect_mention("@AI 오늘 뭐 논의했어?")

    def test_at_bot(self):
        assert detect_mention("@봇 알려줘")

    def test_at_bot_english(self):
        assert detect_mention("@bot help")

    def test_at_kachat(self):
        assert detect_mention("@카챗 검색해줘")

    def test_no_mention(self):
        assert not detect_mention("그냥 대화야")

    def test_mention_in_middle(self):
        assert detect_mention("저기 @AI 이거 뭐야?")


class TestQuestionDetection:
    def test_question_mark_with_pattern(self):
        assert detect_question("RAG 얘기 누가 했어?")

    def test_question_mwoyeotji(self):
        assert detect_question("어제 공유된 링크 뭐였지?")

    def test_question_allyeojwo(self):
        assert detect_question("Mem0 사용법 알려줘?")

    def test_no_question_mark(self):
        assert not detect_question("그냥 말이야")

    def test_question_mark_without_pattern(self):
        # ? 있지만 패턴 없음
        assert not detect_question("진짜?")

    def test_fullwidth_question(self):
        assert detect_question("이거 뭐야？")


class TestClassifyTrigger:
    def test_mention_priority(self):
        # 멘션이 질문보다 우선
        assert classify_trigger("@AI RAG 누가 했어?", "철수") == "mention"

    def test_question(self):
        assert classify_trigger("어제 링크 뭐였지?", "영희") == "question"

    def test_no_trigger(self):
        assert classify_trigger("ㅋㅋ 그렇구나", "민수") is None


class TestRateLimit:
    def setup_method(self):
        """매 테스트마다 상태 리셋."""
        _response_timestamps.clear()
        participation_module._consecutive_count = 0
        participation_module._cooldown_until = 0.0

    def test_first_response_allowed(self):
        assert _check_rate_limit()

    def test_per_minute_limit(self):
        _record_response()
        # config의 per_minute=1이므로 다음 응답 차단
        assert not _check_rate_limit()

    def test_consecutive_cooldown(self):
        # 3회 연속 후 쿨다운
        for _ in range(3):
            _response_timestamps.clear()  # 분당 제한 우회
            _record_response()
        assert not _check_rate_limit()

    def test_reset_consecutive(self):
        participation_module._consecutive_count = 2
        reset_consecutive()
        assert participation_module._consecutive_count == 0

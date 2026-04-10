"""Phase 4 v0.2: 지식 큐레이터 테스트."""
import pytest

from app.config import load_config
from app.curator import classify, extract_urls, MessageType

load_config()


class TestNoiseClassification:
    def test_kkk_is_noise(self):
        msg = classify("방", "유저", "ㅋㅋㅋㅋ", 1000)
        assert msg.msg_type == MessageType.NOISE

    def test_emoticon_is_noise(self):
        msg = classify("방", "유저", "이모티콘", 1000)
        assert msg.msg_type == MessageType.NOISE

    def test_single_char_is_noise(self):
        msg = classify("방", "유저", "ㅇ", 1000)
        assert msg.msg_type == MessageType.NOISE

    def test_consonants_only_noise(self):
        msg = classify("방", "유저", "ㅎㅎ", 1000)
        assert msg.msg_type == MessageType.NOISE


class TestSignalClassification:
    def test_url_boosts_score(self):
        msg = classify("방", "유저", "이거 봐 https://arxiv.org/abs/2401.15884 논문 좋다", 1000)
        assert msg.signal_score >= 2
        assert len(msg.urls) == 1

    def test_code_block_boosts_score(self):
        msg = classify("방", "유저", "이렇게 하면 돼 ```python\nprint('hello')```", 1000)
        assert msg.signal_score >= 2

    def test_long_message_boosts_score(self):
        long_text = "RAG 파이프라인을 구축할 때 가장 중요한 건 청킹 전략이야. " * 5
        msg = classify("방", "유저", long_text, 1000)
        assert msg.signal_score >= 1

    def test_signal_keyword_boosts_score(self):
        # "꿀팁"은 TIL 키워드이기도 함 → TIL 또는 SIGNAL
        msg = classify("방", "유저", "꿀팁: FastAPI에서 BackgroundTask 쓰면 응답 속도가 빨라짐", 1000)
        assert msg.signal_score >= 2
        assert msg.msg_type in (MessageType.SIGNAL, MessageType.TIL)

    def test_high_signal_url_only(self):
        msg = classify("방", "유저", "이거 참고하면 좋아 https://example.com 여기에 정리됨 " + "자세한 내용은 " * 20, 1000)
        assert msg.msg_type == MessageType.SIGNAL
        assert msg.signal_score >= 3


class TestTILDetection:
    def test_til_keyword(self):
        msg = classify("방", "유저", "TIL: ChromaDB metadata 필터링이 10배 빠르다", 1000)
        assert msg.msg_type == MessageType.TIL
        assert msg.til_keyword == "TIL"

    def test_mollattne(self):
        msg = classify("방", "유저", "오 몰랐네 이렇게 되는 거였어?", 1000)
        assert msg.msg_type == MessageType.TIL
        assert msg.til_keyword == "몰랐네"

    def test_singihada(self):
        msg = classify("방", "유저", "신기하다 파이썬에서 이게 되네", 1000)
        assert msg.msg_type == MessageType.TIL

    def test_ggultip(self):
        msg = classify("방", "유저", "이거 꿀팁인데 알려줄게", 1000)
        assert msg.msg_type == MessageType.TIL

    def test_cheoeum_alat(self):
        msg = classify("방", "유저", "처음 알았다 이런 기능이 있는 줄", 1000)
        assert msg.msg_type == MessageType.TIL

    def test_no_til(self):
        msg = classify("방", "유저", "점심 뭐 먹지 고민된다", 1000)
        assert msg.msg_type != MessageType.TIL


class TestURLExtraction:
    def test_single_url(self):
        urls = extract_urls("확인해봐 https://example.com 여기")
        assert urls == ["https://example.com"]

    def test_multiple_urls(self):
        urls = extract_urls("https://a.com 그리고 https://b.com/path?q=1")
        assert len(urls) == 2

    def test_no_url(self):
        urls = extract_urls("링크 없는 메시지")
        assert urls == []

    def test_github_url(self):
        urls = extract_urls("https://github.com/mem0ai/mem0 스타 2만개")
        assert len(urls) == 1
        assert "github.com" in urls[0]


class TestNormalClassification:
    def test_short_normal(self):
        msg = classify("방", "유저", "그렇구나 알겠어", 1000)
        assert msg.msg_type == MessageType.NORMAL
        assert msg.signal_score < 3

    def test_greeting(self):
        msg = classify("방", "유저", "안녕하세요 반갑습니다", 1000)
        assert msg.msg_type == MessageType.NORMAL

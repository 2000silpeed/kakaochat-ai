"""v0.3: 전문가 태깅 테스트."""
import pytest

from app.config import load_config
from app.expert import (
    extract_topics,
    record_contribution,
    find_expert,
    get_room_experts,
    reset_data,
)

load_config()


class TestExtractTopics:
    def test_single_topic(self):
        topics = extract_topics("RAG 파이프라인 구축법")
        assert "rag" in topics

    def test_multiple_topics(self):
        topics = extract_topics("LangChain으로 RAG 만들고 ChromaDB에 저장")
        assert "langchain" in topics or "랭체인" in topics
        assert "rag" in topics
        assert "chromadb" in topics

    def test_no_topic(self):
        topics = extract_topics("점심 뭐 먹지")
        assert topics == []

    def test_case_insensitive(self):
        topics = extract_topics("Python으로 FastAPI 서버 만들기")
        assert "python" in topics
        assert "fastapi" in topics

    def test_korean_topics(self):
        topics = extract_topics("딥러닝 모델 파인튜닝 방법")
        assert "딥러닝" in topics
        assert "파인튜닝" in topics


class TestRecordContribution:
    def setup_method(self):
        reset_data()

    def test_first_contribution(self):
        record_contribution("AI스터디", "철수", 5, "RAG 파이프라인 꿀팁 공유")
        experts = get_room_experts("AI스터디")
        assert len(experts) == 1
        assert experts[0]["sender"] == "철수"
        assert experts[0]["total_signal"] == 5

    def test_accumulated_signal(self):
        record_contribution("AI스터디", "철수", 3, "LLM 관련 팁")
        record_contribution("AI스터디", "철수", 4, "LLM 프롬프트 엔지니어링")
        experts = get_room_experts("AI스터디")
        assert experts[0]["total_signal"] == 7
        assert experts[0]["message_count"] == 2

    def test_topic_tracking(self):
        record_contribution("AI스터디", "철수", 5, "RAG와 LangChain 조합이 좋아")
        experts = get_room_experts("AI스터디")
        assert "rag" in experts[0]["top_topics"]

    def test_multiple_users(self):
        record_contribution("AI스터디", "철수", 5, "RAG 관련 정보")
        record_contribution("AI스터디", "영희", 7, "Docker 배포 방법")
        experts = get_room_experts("AI스터디")
        assert len(experts) == 2
        assert experts[0]["sender"] == "영희"  # 더 높은 시그널

    def test_different_rooms(self):
        record_contribution("AI스터디", "철수", 5, "RAG 정보")
        record_contribution("개발방", "철수", 3, "Python 팁")
        ai_experts = get_room_experts("AI스터디")
        dev_experts = get_room_experts("개발방")
        assert ai_experts[0]["total_signal"] == 5
        assert dev_experts[0]["total_signal"] == 3


class TestFindExpert:
    def setup_method(self):
        reset_data()

    def test_find_matching_expert(self):
        record_contribution("AI스터디", "철수", 6, "RAG 파이프라인 구축 방법 상세 설명")
        expert = find_expert("AI스터디", "RAG 어떻게 구축해?")
        assert expert == "철수"

    def test_no_expert_below_min_signal(self):
        record_contribution("AI스터디", "철수", 2, "RAG 관련 짧은 메모")
        expert = find_expert("AI스터디", "RAG 어떻게 구축해?")
        assert expert is None  # total_signal < min_signal_score (5)

    def test_no_expert_no_topic_match(self):
        record_contribution("AI스터디", "철수", 10, "Docker 배포 전문가")
        expert = find_expert("AI스터디", "RAG 어떻게 구축해?")
        assert expert is None  # 토픽 불일치

    def test_no_expert_empty_room(self):
        expert = find_expert("빈방", "아무 질문?")
        assert expert is None

    def test_no_expert_no_topics_in_query(self):
        record_contribution("AI스터디", "철수", 10, "RAG 전문가")
        expert = find_expert("AI스터디", "점심 뭐 먹지?")
        assert expert is None  # 질문에 토픽 키워드 없음

    def test_exclude_sender(self):
        record_contribution("AI스터디", "철수", 10, "RAG 파이프라인 전문 지식")
        expert = find_expert("AI스터디", "RAG 질문?", exclude_sender="철수")
        assert expert is None  # 질문자 본인 제외

    def test_best_expert_selected(self):
        record_contribution("AI스터디", "철수", 6, "RAG 기초")
        record_contribution("AI스터디", "영희", 10, "RAG 고급 파이프라인 최적화")
        record_contribution("AI스터디", "영희", 5, "RAG 임베딩 전략")
        expert = find_expert("AI스터디", "RAG 파이프라인 최적화 방법?")
        assert expert == "영희"  # 더 높은 시그널 + 더 많은 RAG 기여


class TestGetRoomExperts:
    def setup_method(self):
        reset_data()

    def test_empty_room(self):
        experts = get_room_experts("빈방")
        assert experts == []

    def test_top_n_limit(self):
        for i in range(10):
            record_contribution("AI스터디", f"유저{i}", i + 1, "Python 관련 팁")
        experts = get_room_experts("AI스터디", top_n=3)
        assert len(experts) == 3
        assert experts[0]["total_signal"] >= experts[1]["total_signal"]

    def test_sorted_by_signal(self):
        record_contribution("AI스터디", "A", 3, "Python 팁")
        record_contribution("AI스터디", "B", 10, "Python 전문가")
        record_contribution("AI스터디", "C", 7, "Python 중급")
        experts = get_room_experts("AI스터디")
        signals = [e["total_signal"] for e in experts]
        assert signals == sorted(signals, reverse=True)

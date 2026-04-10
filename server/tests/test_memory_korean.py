"""Gate 2: Mem0 한국어 테스트 10개 케이스.

실제 Mem0 + ChromaDB + HuggingFace 임베딩을 사용하는 통합 테스트.
테스트 전용 collection을 사용하여 격리.
"""
import os
import shutil
import pytest

from app.config import load_config, get_config
from app.memory import get_memory, store_message, search_memory, is_noise

# 테스트용 ChromaDB 경로
TEST_CHROMA_PATH = "data/chromadb_test"


@pytest.fixture(scope="module", autouse=True)
def setup_memory():
    """테스트용 Mem0 인스턴스 — 별도 collection + 종료 시 정리."""
    import app.memory as mem_module

    load_config()
    cfg = get_config()
    cfg["memory"]["collection_name"] = "kakaochat_test"

    # 이전 테스트 데이터 정리
    if os.path.exists(TEST_CHROMA_PATH):
        shutil.rmtree(TEST_CHROMA_PATH)

    # 메모리 싱글턴 리셋
    mem_module._memory = None

    yield

    # 정리
    mem_module._memory = None
    if os.path.exists(TEST_CHROMA_PATH):
        shutil.rmtree(TEST_CHROMA_PATH)


@pytest.fixture(scope="module")
def seed_messages():
    """테스트용 메시지 시딩."""
    messages = [
        ("AI스터디", "철수", "RAG 써봤는데 LangChain이랑 LlamaIndex 중에 LlamaIndex가 더 낫더라. 특히 한국어 문서 처리할 때 청킹이 깔끔해", 1712600000),
        ("AI스터디", "영희", "https://arxiv.org/abs/2401.15884 이 논문 진짜 좋다. RAG 최신 서베이", 1712600100),
        ("AI스터디", "민수", "ㅋㅋㅋㅋㅋ", 1712600200),
        ("AI스터디", "철수", "Gemini 2.0 Flash가 GPT-4o-mini보다 가성비 좋은 거 같아. 한국어도 잘 됨", 1712600300),
        ("AI스터디", "영희", "TIL: ChromaDB에서 metadata 필터링하면 검색 성능이 10배 올라간다", 1712600400),
        ("AI스터디", "지훈", "ㅎㅎ", 1712600500),
        ("AI스터디", "민수", "이모티콘", 1712600600),
        ("AI스터디", "지훈", "파이썬에서 asyncio.Queue 쓸 때 maxsize 설정 안 하면 메모리 터지는 거 조심", 1712600700),
        ("AI스터디", "철수", "Mem0라는 메모리 엔진 발견했는데, 그룹챗에서 누가 뭘 말했는지 기억해줌. 24M 시리즈A 받았대", 1712600800),
        ("AI스터디", "영희", "줄임말 테스트: ㄱㅅ ㅇㅈ ㄹㅇ 이거 진짜 좋음 ㅋ", 1712600900),
        ("AI스터디", "민수", "어제 발표된 Claude 4 써봤는데 코딩 능력이 미쳤음. 특히 긴 컨텍스트 처리가 좋아짐", 1712601000),
        ("AI스터디", "지훈", "https://github.com/mem0ai/mem0 여기 깃헙 레포인데 스타가 벌써 2만개", 1712601100),
    ]
    results = []
    for room, sender, text, ts in messages:
        result = store_message(room, sender, text, ts)
        results.append((text, result))
    return results


# --- Gate 2: 한국어 테스트 10개 케이스 ---

class TestKoreanMemory:
    """Mem0 한국어 성능 검증 (Gate 2)."""

    def test_01_rag_who_said(self, seed_messages):
        """'RAG 얘기 누가 했어?' → 철수/영희 결과 포함."""
        results = search_memory("RAG 얘기 누가 했어?", room="AI스터디")
        if isinstance(results, dict) and "results" in results:
            results = results["results"]
        assert len(results) > 0, "검색 결과 없음"
        memories_text = " ".join(r.get("memory", "") for r in results)
        assert any(
            keyword in memories_text for keyword in ["RAG", "LlamaIndex", "LangChain", "서베이"]
        ), f"RAG 관련 결과 없음: {memories_text[:200]}"

    def test_02_url_recall(self, seed_messages):
        """'어제 공유된 링크 뭐였지?' → URL 포함 결과."""
        results = search_memory("공유된 링크", room="AI스터디")
        if isinstance(results, dict) and "results" in results:
            results = results["results"]
        assert len(results) > 0, "검색 결과 없음"
        memories_text = " ".join(r.get("memory", "") for r in results)
        has_url = "http" in memories_text or "arxiv" in memories_text or "github" in memories_text
        assert has_url, f"URL 포함 결과 없음: {memories_text[:200]}"

    def test_03_noise_filter_kkk(self, seed_messages):
        """'ㅋㅋㅋㅋㅋ' → 노이즈로 분류, 저장 안 됨."""
        assert is_noise("ㅋㅋㅋㅋㅋ"), "ㅋㅋㅋ가 노이즈로 분류되지 않음"
        # seed_messages에서 ㅋㅋㅋㅋㅋ 저장 결과가 None이어야 함
        for text, result in seed_messages:
            if text == "ㅋㅋㅋㅋㅋ":
                assert result is None, "ㅋㅋㅋ가 메모리에 저장됨"

    def test_04_noise_filter_emoticon(self, seed_messages):
        """'이모티콘' → 노이즈로 분류."""
        assert is_noise("이모티콘"), "이모티콘이 노이즈로 분류되지 않음"
        for text, result in seed_messages:
            if text == "이모티콘":
                assert result is None, "이모티콘이 메모리에 저장됨"

    def test_05_noise_filter_hh(self, seed_messages):
        """'ㅎㅎ' → 노이즈로 분류."""
        assert is_noise("ㅎㅎ"), "ㅎㅎ이 노이즈로 분류되지 않음"

    def test_06_tech_keyword_search(self, seed_messages):
        """기술 키워드 검색: 'Gemini 가성비' → 관련 결과."""
        results = search_memory("Gemini 가성비", room="AI스터디")
        if isinstance(results, dict) and "results" in results:
            results = results["results"]
        assert len(results) > 0, "검색 결과 없음"
        memories_text = " ".join(r.get("memory", "") for r in results)
        assert any(
            kw in memories_text for kw in ["Gemini", "GPT", "가성비"]
        ), f"Gemini 관련 결과 없음: {memories_text[:200]}"

    def test_07_til_signal(self, seed_messages):
        """TIL 시그널 검색: 'TIL ChromaDB' → 관련 결과."""
        results = search_memory("ChromaDB 성능 팁", room="AI스터디")
        if isinstance(results, dict) and "results" in results:
            results = results["results"]
        assert len(results) > 0, "검색 결과 없음"
        memories_text = " ".join(r.get("memory", "") for r in results)
        assert any(
            kw in memories_text for kw in ["ChromaDB", "metadata", "필터링", "성능"]
        ), f"ChromaDB TIL 결과 없음: {memories_text[:200]}"

    def test_08_abbreviation_handling(self, seed_messages):
        """줄임말 포함 메시지가 저장되는지 확인."""
        for text, result in seed_messages:
            if "ㄱㅅ" in text:
                assert result is not None, "줄임말 포함 메시지가 저장되지 않음"
                break

    def test_09_user_specific_search(self, seed_messages):
        """특정 사용자 필터 검색: user_id='철수'."""
        results = search_memory("어떤 기술을 썼어?", user_id="철수")
        if isinstance(results, dict) and "results" in results:
            results = results["results"]
        # 철수 필터로 검색 시 결과가 있어야 함
        assert len(results) > 0, "철수 필터 검색 결과 없음"

    def test_10_mem0_entity_search(self, seed_messages):
        """Mem0 관련 검색: 'Mem0 메모리 엔진' → 관련 결과."""
        results = search_memory("Mem0 메모리 엔진", room="AI스터디")
        if isinstance(results, dict) and "results" in results:
            results = results["results"]
        assert len(results) > 0, "검색 결과 없음"
        memories_text = " ".join(r.get("memory", "") for r in results)
        assert any(
            kw in memories_text for kw in ["Mem0", "메모리", "그룹챗", "기억"]
        ), f"Mem0 관련 결과 없음: {memories_text[:200]}"

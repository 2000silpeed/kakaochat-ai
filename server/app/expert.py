"""전문가 태깅 — 주제별 전문가 추적 및 추천."""
import json
import logging
from pathlib import Path

from app.config import get_config

logger = logging.getLogger("kakaochat.expert")

_EXPERT_FILE = Path("data/experts.json")
_expert_data: dict | None = None


def _load_data() -> dict:
    global _expert_data
    if _expert_data is not None:
        return _expert_data
    if _EXPERT_FILE.exists():
        with open(_EXPERT_FILE, "r", encoding="utf-8") as f:
            _expert_data = json.load(f)
    else:
        _expert_data = {}
    return _expert_data


def _save_data():
    _EXPERT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_EXPERT_FILE, "w", encoding="utf-8") as f:
        json.dump(_expert_data, f, ensure_ascii=False, indent=2)


TOPIC_KEYWORDS = [
    "rag", "llm", "gpt", "claude", "gemini", "embedding", "임베딩",
    "벡터", "vector", "chromadb", "pinecone", "langchain", "랭체인",
    "프롬프트", "prompt", "파인튜닝", "fine-tuning", "fine tuning",
    "api", "python", "파이썬", "javascript", "자바스크립트",
    "react", "next.js", "fastapi", "django", "flask",
    "docker", "쿠버네티스", "kubernetes", "aws", "gcp", "azure",
    "딥러닝", "deep learning", "머신러닝", "machine learning",
    "트랜스포머", "transformer", "어텐션", "attention",
    "데이터", "db", "데이터베이스", "database", "sql", "nosql",
    "배포", "deploy", "ci/cd", "github", "git",
    "에이전트", "agent", "멀티모달", "multimodal",
    "whisper", "tts", "stt", "음성", "vision",
]


def extract_topics(text: str) -> list[str]:
    """메시지에서 주제 키워드 추출."""
    found = []
    text_lower = text.lower()
    for kw in TOPIC_KEYWORDS:
        if kw in text_lower:
            found.append(kw)
    return found


def record_contribution(room: str, sender: str, signal_score: int, text: str):
    """SIGNAL/TIL 메시지를 전문가 데이터에 기록."""
    data = _load_data()

    if room not in data:
        data[room] = {}
    if sender not in data[room]:
        data[room][sender] = {
            "total_signal": 0,
            "message_count": 0,
            "topics": {},
        }

    profile = data[room][sender]
    profile["total_signal"] += signal_score
    profile["message_count"] += 1

    topics = extract_topics(text)
    for topic in topics:
        profile["topics"][topic] = profile["topics"].get(topic, 0) + 1

    _save_data()
    logger.debug(f"Expert recorded: {sender} in {room}, score={signal_score}")


def find_expert(room: str, query: str, exclude_sender: str | None = None) -> str | None:
    """질문에 맞는 전문가 찾기. 반환: sender 이름 또는 None.

    exclude_sender: 질문자 본인은 제외.
    """
    cfg = get_config()
    expert_cfg = cfg.get("expert_tagging", {})
    min_signal = expert_cfg.get("min_signal_score", 5)

    data = _load_data()
    room_data = data.get(room, {})

    if not room_data:
        return None

    query_topics = extract_topics(query)
    if not query_topics:
        return None

    best_expert = None
    best_score = 0.0

    for sender, profile in room_data.items():
        if sender == exclude_sender:
            continue
        if profile["total_signal"] < min_signal:
            continue

        topic_score = sum(profile["topics"].get(t, 0) for t in query_topics)
        if topic_score == 0:
            continue

        weighted = topic_score * (1 + profile["total_signal"] / 10)
        if weighted > best_score:
            best_score = weighted
            best_expert = sender

    if best_expert:
        logger.info(f"Expert found: {best_expert} for {query_topics} (score={best_score:.1f})")

    return best_expert


def get_room_experts(room: str, top_n: int = 5) -> list[dict]:
    """방의 상위 전문가 목록."""
    data = _load_data()
    room_data = data.get(room, {})

    experts = []
    for sender, profile in room_data.items():
        top_topics = sorted(
            profile["topics"].items(), key=lambda x: x[1], reverse=True
        )[:3]
        experts.append({
            "sender": sender,
            "total_signal": profile["total_signal"],
            "message_count": profile["message_count"],
            "top_topics": [t[0] for t in top_topics],
        })

    experts.sort(key=lambda x: x["total_signal"], reverse=True)
    return experts[:top_n]


def reset_data():
    """테스트용 데이터 리셋."""
    global _expert_data
    _expert_data = {}
    if _EXPERT_FILE.exists():
        _EXPERT_FILE.unlink()

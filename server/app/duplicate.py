"""중복 질문 감지 — 코사인 유사도 기반 과거 답변 소환."""
import logging
from dataclasses import dataclass

from app.config import get_config
from app.memory import search_memory

logger = logging.getLogger("kakaochat.duplicate")


@dataclass
class DuplicateResult:
    original_text: str
    score: float
    sender: str
    ts: int


def check_duplicate(text: str, room: str) -> DuplicateResult | None:
    """중복 질문 감지. cosine > threshold이면 DuplicateResult 반환.

    question 분류 메시지에만 호출해야 함 (participation에서 필터링).
    """
    cfg = get_config()
    threshold = cfg["participation"]["similarity_threshold"]["duplicate"]

    results = search_memory(text, room=room, limit=3)
    if isinstance(results, dict) and "results" in results:
        results = results["results"]

    if not results:
        return None

    for r in results:
        score = r.get("score", 0)
        if score >= threshold:
            metadata = r.get("metadata", {})
            return DuplicateResult(
                original_text=r.get("memory", ""),
                score=score,
                sender=metadata.get("sender", ""),
                ts=metadata.get("ts", 0),
            )

    return None


def format_duplicate_response(dup: DuplicateResult) -> str:
    """중복 감지 결과를 사용자 친화적 응답으로 포맷."""
    sender_part = f"{dup.sender}님이" if dup.sender else "이전에"
    return (
        f"비슷한 질문이 있었어요! {sender_part} 공유한 내용이에요:\n"
        f"💬 {dup.original_text}"
    )

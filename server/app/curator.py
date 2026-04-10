"""지식 큐레이터 — 시그널/노이즈 분류, TIL 추출, 링크 아카이브."""
import logging
import re
from dataclasses import dataclass, field
from enum import Enum

from app.config import get_config

logger = logging.getLogger("kakaochat.curator")

# --- URL 패턴 ---
URL_PATTERN = re.compile(
    r'https?://[^\s<>"\'\)]+',
    re.IGNORECASE,
)

# --- 코드블록 패턴 ---
CODE_BLOCK_PATTERN = re.compile(r'```[\s\S]*?```|`[^`]+`')


class MessageType(str, Enum):
    NOISE = "noise"
    NORMAL = "normal"
    SIGNAL = "signal"
    TIL = "til"


@dataclass
class CuratedMessage:
    room: str
    sender: str
    text: str
    ts: int
    msg_type: MessageType = MessageType.NORMAL
    urls: list[str] = field(default_factory=list)
    signal_score: int = 0
    til_keyword: str | None = None


def classify(room: str, sender: str, text: str, ts: int) -> CuratedMessage:
    """메시지를 분류하고 시그널 점수를 매긴다.

    파이프라인: 노이즈 체크 → URL 추출 → 시그널 점수 → TIL 감지 → 최종 분류.
    """
    msg = CuratedMessage(room=room, sender=sender, text=text, ts=ts)
    cfg = get_config()
    curator_cfg = cfg.get("curator", {})

    # 1. 노이즈 체크
    if _is_noise(text, curator_cfg):
        msg.msg_type = MessageType.NOISE
        return msg

    # 2. URL 추출
    msg.urls = extract_urls(text)

    # 3. 시그널 점수 계산
    msg.signal_score = _calc_signal_score(text, msg.urls, curator_cfg)

    # 4. TIL 감지
    msg.til_keyword = _detect_til(text, curator_cfg)
    if msg.til_keyword:
        msg.msg_type = MessageType.TIL
        msg.signal_score += 3
        return msg

    # 5. 최종 분류
    if msg.signal_score >= 3:
        msg.msg_type = MessageType.SIGNAL
    else:
        msg.msg_type = MessageType.NORMAL

    return msg


def extract_urls(text: str) -> list[str]:
    """텍스트에서 URL 추출."""
    return URL_PATTERN.findall(text)


def _is_noise(text: str, curator_cfg: dict) -> bool:
    """노이즈 판별 (memory.py의 is_noise와 동일 로직)."""
    patterns = curator_cfg.get("noise_patterns", [])
    stripped = text.strip()
    for pattern in patterns:
        if re.match(pattern, stripped):
            return True
    if len(stripped) <= 1:
        return True
    return False


def _calc_signal_score(text: str, urls: list[str], curator_cfg: dict) -> int:
    """시그널 점수 계산. 높을수록 가치 있는 메시지.

    점수 기준:
    - URL 포함: +2
    - 코드블록 포함: +2
    - 길이 >= min_signal_length: +1
    - 시그널 키워드 포함: +2
    """
    score = 0

    if urls:
        score += 2

    if CODE_BLOCK_PATTERN.search(text):
        score += 2

    min_len = curator_cfg.get("min_signal_length", 100)
    if len(text) >= min_len:
        score += 1

    keywords = curator_cfg.get("signal_keywords", [])
    for kw in keywords:
        if kw.lower() in text.lower():
            score += 2
            break

    return score


def _detect_til(text: str, curator_cfg: dict) -> str | None:
    """TIL 시그널 감지. 해당 키워드 반환."""
    til_patterns = [
        (r'\bTIL\b', "TIL"),
        (r'몰랐[네다]', "몰랐네"),
        (r'신기하[다네]', "신기하다"),
        (r'꿀팁', "꿀팁"),
        (r'처음\s*알았', "처음 알았"),
        (r'오\s+몰랐', "오 몰랐"),
    ]
    for pattern, keyword in til_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return keyword
    return None

"""Weekly Digest — 주간 시그널 수집 + LLM 요약 생성."""
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import get_config, get_llm_api_key

logger = logging.getLogger("kakaochat.digest")

_SIGNALS_FILE = Path("data/signals.jsonl")


@dataclass
class SignalEntry:
    room: str
    sender: str
    text: str
    ts: int
    msg_type: str
    signal_score: int
    topics: list[str]


def record_signal(
    room: str,
    sender: str,
    text: str,
    ts: int,
    msg_type: str,
    signal_score: int,
    topics: list[str] | None = None,
):
    """SIGNAL/TIL 메시지를 시그널 로그에 기록."""
    entry = SignalEntry(
        room=room,
        sender=sender,
        text=text,
        ts=ts,
        msg_type=msg_type,
        signal_score=signal_score,
        topics=topics or [],
    )
    _SIGNALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_SIGNALS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
    logger.debug(f"Signal recorded: {sender} [{msg_type}]")


def get_weekly_signals(room: str | None = None, days: int = 7) -> list[SignalEntry]:
    """최근 N일간의 시그널 조회."""
    if not _SIGNALS_FILE.exists():
        return []

    cutoff_ts = int((time.time() - days * 86400) * 1000)
    signals = []

    with open(_SIGNALS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if data["ts"] >= cutoff_ts:
                    if room is None or data["room"] == room:
                        signals.append(SignalEntry(**data))
            except (json.JSONDecodeError, KeyError):
                continue

    signals.sort(key=lambda s: s.signal_score, reverse=True)
    return signals


def _build_digest_prompt(signals: list[SignalEntry], room: str) -> str:
    """시그널 목록 → LLM 프롬프트 구성."""
    entries = []
    for i, s in enumerate(signals, 1):
        type_label = "💡 TIL" if s.msg_type == "til" else "📌 시그널"
        topics_str = f" [{', '.join(s.topics)}]" if s.topics else ""
        entries.append(f"{i}. {type_label}{topics_str} — {s.sender}: {s.text}")

    entries_text = "\n".join(entries)

    return (
        f"아래는 '{room}' 오픈챗방에서 지난 한 주간 수집된 주요 메시지들이야.\n"
        f"이 내용을 바탕으로 주간 다이제스트를 작성해줘.\n\n"
        f"규칙:\n"
        f"- 주요 토픽별로 정리 (3~5개 섹션)\n"
        f"- 각 섹션에 핵심 내용 1~2줄 요약\n"
        f"- 기여자 이름을 언급해서 감사 표시\n"
        f"- TIL은 '이번 주 배운 것' 섹션에 모아줘\n"
        f"- 전체 200자 내외로 간결하게\n"
        f"- 마지막에 '다음 주도 활발한 논의 기대합니다! 🚀' 같은 마무리 한 줄\n\n"
        f"--- 메시지 목록 ---\n{entries_text}"
    )


async def generate_digest(room: str) -> str | None:
    """주간 다이제스트 생성. 시그널 부족 시 None."""
    cfg = get_config()
    digest_cfg = cfg.get("digest", {})
    min_signals = digest_cfg.get("min_signals", 3)
    max_signals = digest_cfg.get("max_signals", 50)

    signals = get_weekly_signals(room=room)
    if len(signals) < min_signals:
        logger.info(
            f"Digest skipped: only {len(signals)} signals "
            f"(min={min_signals}) in {room}"
        )
        return None

    signals = signals[:max_signals]

    prompt = _build_digest_prompt(signals, room)
    digest_text = await _call_llm_for_digest(prompt)

    if digest_text:
        header = "📋 주간 다이제스트\n\n"
        return header + digest_text

    return None


async def _call_llm_for_digest(prompt: str) -> str | None:
    """LLM 호출로 다이제스트 텍스트 생성."""
    cfg = get_config()
    model = cfg["llm"]["model"]
    api_key = get_llm_api_key()

    if not api_key:
        logger.error("LLM API key not set")
        return None

    system_prompt = (
        "너는 카카오톡 오픈챗방의 주간 다이제스트 작성자야. "
        "한 주간의 주요 논의를 깔끔하게 정리해줘. "
        "한국어로 작성하고, 이모지를 적절히 활용해. "
        "핵심만 간결하게."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    if model.startswith("gemini/"):
        return await _call_gemini(model.removeprefix("gemini/"), messages, api_key, cfg)
    elif model.startswith("openai/"):
        return await _call_openai(model.removeprefix("openai/"), messages, api_key, cfg)
    else:
        logger.error(f"Unsupported LLM model: {model}")
        return None


async def _call_gemini(model: str, messages: list, api_key: str, cfg: dict) -> str | None:
    from google import genai

    client = genai.Client(api_key=api_key)
    system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")

    response = client.models.generate_content(
        model=model,
        contents=user_msg,
        config=genai.types.GenerateContentConfig(
            system_instruction=system_msg,
            temperature=0.5,
            max_output_tokens=cfg["llm"]["max_tokens"],
        ),
    )
    if response and response.text:
        return response.text.strip()
    return None


async def _call_openai(model: str, messages: list, api_key: str, cfg: dict) -> str | None:
    import openai

    client = openai.AsyncOpenAI(api_key=api_key)
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.5,
        max_tokens=cfg["llm"]["max_tokens"],
    )
    if response.choices:
        return response.choices[0].message.content.strip()
    return None


def clear_old_signals(days: int = 30):
    """오래된 시그널 정리 (30일 이상)."""
    if not _SIGNALS_FILE.exists():
        return

    cutoff_ts = int((time.time() - days * 86400) * 1000)
    kept = []

    with open(_SIGNALS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if data["ts"] >= cutoff_ts:
                    kept.append(line)
            except (json.JSONDecodeError, KeyError):
                continue

    with open(_SIGNALS_FILE, "w", encoding="utf-8") as f:
        for line in kept:
            f.write(line + "\n")

    logger.info(f"Old signals cleaned: kept {len(kept)} entries")


def reset_signals():
    """테스트용 시그널 데이터 리셋."""
    if _SIGNALS_FILE.exists():
        _SIGNALS_FILE.unlink()

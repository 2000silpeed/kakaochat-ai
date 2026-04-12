"""참여 엔진 — 멘션 감지, 질문 감지, 빈도 제한, 중복 감지, 전문가 추천, LLM 응답 생성."""
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field

import os

from app.config import get_config, get_llm_api_key
from app.duplicate import check_duplicate, format_duplicate_response
from app.expert import find_expert
from app.memory import search_memory

logger = logging.getLogger("kakaochat.participation")


# --- Per-room 빈도 제한 ---
@dataclass
class RoomRateState:
    response_timestamps: deque = field(default_factory=deque)
    consecutive_count: int = 0
    cooldown_until: float = 0.0


_room_rate_states: dict[str, RoomRateState] = {}


def _get_rate_state(room: str) -> RoomRateState:
    if room not in _room_rate_states:
        _room_rate_states[room] = RoomRateState()
    return _room_rate_states[room]


def _check_rate_limit(room: str) -> bool:
    """Per-room 빈도 제한 체크. 응답 가능하면 True."""
    state = _get_rate_state(room)
    cfg = get_config()
    rl = cfg["participation"]["rate_limit"]
    now = time.time()

    if now < state.cooldown_until:
        logger.debug(f"[{room}] Cooldown active until {state.cooldown_until:.0f}")
        return False

    while state.response_timestamps and now - state.response_timestamps[0] > 60:
        state.response_timestamps.popleft()
    if len(state.response_timestamps) >= rl["per_minute"]:
        logger.debug(f"[{room}] Rate limit: per_minute exceeded")
        return False

    return True


def _record_response(room: str):
    """Per-room 응답 기록 → 빈도 제한 업데이트."""
    state = _get_rate_state(room)
    cfg = get_config()
    rl = cfg["participation"]["rate_limit"]

    state.response_timestamps.append(time.time())
    state.consecutive_count += 1

    if state.consecutive_count >= rl["consecutive_max"]:
        state.cooldown_until = time.time() + rl["cooldown_seconds"]
        state.consecutive_count = 0
        logger.info(f"[{room}] Cooldown activated for {rl['cooldown_seconds']}s")


def reset_consecutive(room: str):
    """다른 사람이 말하면 해당 방의 연속 카운트 리셋."""
    state = _get_rate_state(room)
    state.consecutive_count = 0


# --- 트리거 감지 ---
BOT_NAME_PATTERNS = [
    r"@AI\b",
    r"@봇\b",
    r"@bot\b",
    r"@카챗\b",
]

QUESTION_PATTERNS = [
    r"뭐였지",
    r"뭐야",
    r"뭔가요",
    r"누가.*했",
    r"누가.*말했",
    r"어떻게.*해",
    r"왜.*그래",
    r"알려줘",
    r"설명해",
    r"기억나",
    r"언제.*했",
]


def detect_mention(text: str) -> bool:
    """@AI, @봇 등 멘션 감지."""
    for pattern in BOT_NAME_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def detect_question(text: str) -> bool:
    """질문 감지: ? 포함 + 한국어 질문 패턴."""
    if "?" not in text and "？" not in text:
        return False
    for pattern in QUESTION_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


def classify_trigger(text: str, sender: str) -> str | None:
    """메시지 트리거 분류. 반환: 'mention', 'question', None."""
    if detect_mention(text):
        return "mention"
    if detect_question(text):
        return "question"
    return None


def _resolve_api_key(model: str) -> str:
    """모델 prefix에 따라 올바른 API 키 반환."""
    if model.startswith("gemini/"):
        return os.environ.get("GEMINI_API_KEY", "")
    if model.startswith("openai/"):
        return os.environ.get("OPENAI_API_KEY", "")
    return os.environ.get("LLM_API_KEY", "")


# --- LLM 응답 생성 ---
async def generate_response(
    room: str, sender: str, text: str, trigger: str,
    effective_model: str | None = None,
) -> str | None:
    """메모리 검색 + LLM으로 응답 생성. 실패 시 None (침묵)."""
    try:
        if not _check_rate_limit(room):
            logger.info(f"[{room}] Rate limited, staying silent")
            return None

        # 멘션에서 봇 이름 제거
        clean_text = text
        for pattern in BOT_NAME_PATTERNS:
            clean_text = re.sub(pattern, "", clean_text, flags=re.IGNORECASE).strip()

        # v0.3: 중복 질문 감지 (question 트리거에만)
        if trigger == "question":
            dup = check_duplicate(clean_text, room)
            if dup:
                logger.info(f"Duplicate detected (score={dup.score:.2f}): {clean_text[:50]}")
                response = format_duplicate_response(dup)
                _record_response(room)
                return response

        # 메모리 검색
        memories = search_memory(clean_text, room=room, limit=5)
        if isinstance(memories, dict) and "results" in memories:
            memories = memories["results"]

        memory_context = ""
        if memories:
            memory_lines = []
            for m in memories:
                mem_text = m.get("memory", "")
                if mem_text:
                    memory_lines.append(f"- {mem_text}")
            if memory_lines:
                memory_context = "\n".join(memory_lines)

        # v0.3: 전문가 추천
        expert = None
        if trigger == "question":
            expert = find_expert(room, clean_text, exclude_sender=sender)

        # LLM 호출
        response = await _call_llm(
            room, sender, clean_text, memory_context, trigger,
            expert=expert, effective_model=effective_model,
        )

        if response:
            _record_response(room)

        return response

    except Exception:
        logger.exception("Response generation failed (staying silent)")
        return None


async def _call_llm(
    room: str, sender: str, text: str, memory_context: str, trigger: str,
    expert: str | None = None, effective_model: str | None = None,
) -> str | None:
    """LLM 호출 (Gemini/OpenAI/Claude Session)."""
    cfg = get_config()
    model = effective_model or cfg["llm"]["model"]

    # Claude Code 세션 모드
    if model.startswith("claude/"):
        return await _call_claude_session(
            room, sender, text, memory_context, trigger, expert
        )

    api_key = _resolve_api_key(model)
    if not api_key:
        logger.error(f"LLM API key not set for model: {model}")
        return None

    system_prompt = (
        "너는 카카오톡 오픈챗방 AI 어시스턴트야. "
        "자연스럽고 간결하게 한국어로 답해. "
        "기억된 대화 맥락이 있으면 활용하고, 없으면 솔직히 모른다고 해. "
        "이모지는 적절히 사용하되 과하지 않게. "
        "답변은 2-3문장 이내로 짧게."
    )

    user_prompt = f"[{room}] {sender}의 메시지: {text}"
    if memory_context:
        user_prompt += f"\n\n관련 기억:\n{memory_context}"

    if trigger == "mention":
        user_prompt += "\n\n(너에게 직접 물어본 거야. 답변해줘.)"
    elif trigger == "question":
        user_prompt += "\n\n(방에서 나온 질문이야. 기억에 있으면 답해줘.)"

    if expert:
        user_prompt += f"\n\n(이 주제의 전문가: {expert}님. 답변 끝에 '{expert}님이 더 잘 아실 수 있어요'라고 추천해줘.)"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    if model.startswith("gemini/"):
        return await _call_gemini(model.removeprefix("gemini/"), messages, api_key, cfg)
    elif model.startswith("openai/"):
        return await _call_openai(model.removeprefix("openai/"), messages, api_key, cfg)
    else:
        logger.error(f"Unsupported LLM model: {model}")
        return None


async def _call_claude_session(
    room: str, sender: str, text: str, memory_context: str,
    trigger: str, expert: str | None = None,
) -> str | None:
    """Claude Code 세션을 통한 응답 생성."""
    from app.claude_session import get_session

    context_parts = []
    if memory_context:
        context_parts.append(f"관련 기억:\n{memory_context}")
    if trigger == "mention":
        context_parts.append("(너에게 직접 물어본 거야. 답변해줘.)")
    elif trigger == "question":
        context_parts.append("(방에서 나온 질문이야. 기억에 있으면 답해줘.)")
    if expert:
        context_parts.append(f"(이 주제의 전문가: {expert}님. 답변 끝에 '{expert}님이 더 잘 아실 수 있어요'라고 추천해줘.)")

    context = "\n".join(context_parts)

    session = await get_session(room)
    return await session.send_message(sender, text, context)


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
            temperature=cfg["llm"]["temperature"],
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
        temperature=cfg["llm"]["temperature"],
        max_tokens=cfg["llm"]["max_tokens"],
    )

    if response.choices:
        return response.choices[0].message.content.strip()
    return None

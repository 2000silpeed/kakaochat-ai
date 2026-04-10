"""Mem0 메모리 엔진 — 수신 메시지 임베딩 + 검색."""
import logging
import re

from mem0 import Memory

from app.config import get_config

logger = logging.getLogger("kakaochat.memory")

_memory: Memory | None = None


def _build_mem0_config() -> dict:
    cfg = get_config()
    mem_cfg = cfg["memory"]
    llm_cfg = cfg["llm"]

    # LLM provider 결정 (litellm 포맷 → mem0 provider 매핑)
    model = llm_cfg["model"]
    if model.startswith("gemini/"):
        llm_provider = "gemini"
        llm_model = model.removeprefix("gemini/")
    elif model.startswith("openai/"):
        llm_provider = "openai"
        llm_model = model.removeprefix("openai/")
    else:
        llm_provider = "litellm"
        llm_model = model

    return {
        "llm": {
            "provider": llm_provider,
            "config": {
                "model": llm_model,
                "temperature": 0.1,
            },
        },
        "embedder": {
            "provider": "huggingface",
            "config": {
                "model": mem_cfg["embedding_model"],
            },
        },
        "vector_store": {
            "provider": "chroma",
            "config": {
                "collection_name": mem_cfg["collection_name"],
                "path": "data/chromadb",
            },
        },
    }


def get_memory() -> Memory:
    global _memory
    if _memory is None:
        config = _build_mem0_config()
        logger.info(f"Mem0 초기화: embedder={config['embedder']['config']['model']}")
        _memory = Memory.from_config(config)
    return _memory


# --- 노이즈 필터 ---
def is_noise(text: str) -> bool:
    """config의 noise_patterns + 길이 기반 노이즈 판별."""
    cfg = get_config()
    patterns = cfg.get("curator", {}).get("noise_patterns", [])
    for pattern in patterns:
        if re.match(pattern, text.strip()):
            return True
    # 빈 메시지 또는 매우 짧은 의미 없는 메시지
    stripped = text.strip()
    if len(stripped) <= 1:
        return True
    return False


def store_message(
    room: str,
    sender: str,
    text: str,
    ts: int,
    msg_type: str = "normal",
    signal_score: int = 0,
) -> dict | None:
    """메시지를 Mem0에 저장. 노이즈면 None 반환.

    Mem0 엔티티 매핑:
    - user_id = sender (개인 메모리)
    - agent_id = room (방 전체 메모리)
    """
    if is_noise(text):
        logger.debug(f"Noise skipped: {text[:30]}")
        return None

    m = get_memory()
    messages = [{"role": "user", "content": f"{sender}: {text}"}]
    metadata = {
        "room": room,
        "sender": sender,
        "ts": ts,
        "msg_type": msg_type,
        "signal_score": signal_score,
    }
    result = m.add(
        messages,
        user_id=sender,
        agent_id=room,
        metadata=metadata,
    )
    logger.info(f"Memory stored: sender={sender}, type={msg_type}, text={text[:50]}")
    return result


def search_memory(
    query: str,
    user_id: str | None = None,
    room: str | None = None,
    limit: int = 10,
) -> list:
    """메모리 검색.

    user_id 지정 시 해당 사용자 메모리만, room 지정 시 해당 방 메모리만.
    둘 다 없으면 agent_id="all"로 전체 검색.
    """
    m = get_memory()
    kwargs = {"limit": limit}
    if user_id:
        kwargs["user_id"] = user_id
    if room:
        kwargs["agent_id"] = room
    if not user_id and not room:
        kwargs["agent_id"] = "all"
    results = m.search(query, **kwargs)
    return results


def get_all_memories(
    user_id: str | None = None,
    room: str | None = None,
    limit: int = 100,
) -> list:
    """전체 메모리 조회."""
    m = get_memory()
    kwargs = {"limit": limit}
    if user_id:
        kwargs["user_id"] = user_id
    if room:
        kwargs["agent_id"] = room
    if not user_id and not room:
        kwargs["agent_id"] = "all"
    return m.get_all(**kwargs)

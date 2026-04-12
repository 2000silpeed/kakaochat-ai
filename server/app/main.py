import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState

from app.config import get_config, load_config
from app.models import ChatMessage, ServerStatus
from app.room_registry import get_registry

_scheduler = None

logger = logging.getLogger("kakaochat")

# --- State ---
connected_clients: set[WebSocket] = set()
message_queue: asyncio.Queue[ChatMessage] = asyncio.Queue()
total_messages_received: int = 0


# --- Raw message logger ---
def log_raw_message(msg: ChatMessage):
    cfg = get_config()
    log_path = Path(cfg["logging"]["raw_log_file"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(msg.model_dump(), ensure_ascii=False) + "\n")


# --- 응답 전송 (브릿지에 Reply Action 명령) ---
async def _broadcast_response(room: str, text: str):
    """연결된 브릿지에 응답 명령 전송."""
    payload = json.dumps({
        "type": "reply",
        "room": room,
        "text": text,
    }, ensure_ascii=False)

    disconnected = set()
    for ws in connected_clients:
        try:
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.send_text(payload)
                logger.info(f"Reply sent to bridge: {text[:50]}")
        except Exception:
            disconnected.add(ws)
            logger.warning("Failed to send reply to bridge")

    for ws in disconnected:
        connected_clients.discard(ws)


# --- Message processor (background task) ---
async def process_messages():
    while True:
        msg = await message_queue.get()
        try:
            log_raw_message(msg)
            cfg = get_config()

            # target_rooms 화이트리스트 체크
            target_rooms = cfg.get("target_rooms", [])
            if target_rooms and msg.room not in target_rooms:
                logger.debug(f"Room '{msg.room}' not in target_rooms, skipping")
                continue

            logger.info(f"[{msg.room}] {msg.sender}: {msg.text[:80]}")

            # v0.5: Room Registry에 메시지 기록
            registry = get_registry()
            registry.record_message(msg.room)

            # v0.5: per-room response_mode 체크
            room_cfg = registry.get_effective_config(msg.room)
            effective_mode = room_cfg.get("response_mode", cfg.get("response_mode", "passive"))
            effective_model = room_cfg.get("llm_model", cfg["llm"]["model"])

            # Phase 4: 큐레이터 분류 → 노이즈가 아닌 것만 Mem0 저장
            from app.curator import classify, MessageType
            curated = classify(msg.room, msg.sender, msg.text, msg.ts)

            if curated.msg_type == MessageType.NOISE:
                logger.debug(f"Noise skipped: {msg.text[:30]}")
            else:
                try:
                    from app.memory import store_message
                    result = store_message(
                        msg.room, msg.sender, msg.text, msg.ts,
                        msg_type=curated.msg_type.value,
                        signal_score=curated.signal_score,
                    )
                    if result:
                        log_suffix = ""
                        if curated.msg_type == MessageType.TIL:
                            log_suffix = f" [TIL: {curated.til_keyword}]"
                        elif curated.msg_type == MessageType.SIGNAL:
                            log_suffix = f" [SIGNAL score={curated.signal_score}]"
                        if curated.urls:
                            log_suffix += f" [URLs: {len(curated.urls)}]"
                        logger.info(f"Memory stored: {msg.sender}{log_suffix}")
                except Exception:
                    logger.exception("Mem0 store failed (non-fatal)")

                # v0.3: SIGNAL/TIL 메시지 → 전문가 트래커 기록
                if curated.msg_type in (MessageType.SIGNAL, MessageType.TIL):
                    try:
                        from app.expert import record_contribution
                        record_contribution(
                            msg.room, msg.sender,
                            curated.signal_score, msg.text,
                        )
                    except Exception:
                        logger.exception("Expert tracking failed (non-fatal)")

                    # v0.4: 시그널 → 다이제스트 수집
                    try:
                        from app.digest import record_signal
                        from app.expert import extract_topics
                        record_signal(
                            msg.room, msg.sender, msg.text, msg.ts,
                            msg_type=curated.msg_type.value,
                            signal_score=curated.signal_score,
                            topics=extract_topics(msg.text),
                        )
                    except Exception:
                        logger.exception("Digest signal recording failed (non-fatal)")

            # /clear 명령 처리 (Claude 세션 모드)
            if msg.text.strip().startswith("/clear"):
                if effective_model.startswith("claude/"):
                    try:
                        from app.claude_session import clear_session
                        cleared = await clear_session(msg.room)
                        if cleared:
                            await _broadcast_response(msg.room, "세션이 초기화되었습니다.")
                            logger.info(f"Session cleared for '{msg.room}'")
                    except Exception:
                        logger.exception("Session clear failed")
                continue

            # Claude 세션 모드: 모든 non-noise 메시지를 세션에 피드
            if effective_model.startswith("claude/") and effective_mode == "active":
                try:
                    from app.claude_session import get_session
                    session = await get_session(msg.room)
                    if curated.msg_type != MessageType.NOISE:
                        from app.participation import classify_trigger, detect_mention
                        trigger = classify_trigger(msg.text, msg.sender)
                        if trigger:
                            from app.participation import generate_response, _check_rate_limit
                            if _check_rate_limit(msg.room):
                                response_text = await generate_response(
                                    msg.room, msg.sender, msg.text, trigger,
                                    effective_model=effective_model,
                                )
                                if response_text:
                                    await _broadcast_response(msg.room, response_text)
                                    registry.record_response(msg.room)
                except Exception:
                    logger.exception("Claude session failed (staying silent)")

            # Phase 3: 참여 엔진 (non-Claude 모드)
            elif effective_mode == "active":
                try:
                    from app.participation import classify_trigger, generate_response, reset_consecutive

                    trigger = classify_trigger(msg.text, msg.sender)
                    if trigger:
                        response_text = await generate_response(
                            msg.room, msg.sender, msg.text, trigger,
                            effective_model=effective_model,
                        )
                        if response_text:
                            await _broadcast_response(msg.room, response_text)
                            registry.record_response(msg.room)
                    else:
                        reset_consecutive(msg.room)
                except Exception:
                    logger.exception("Participation engine failed (staying silent)")

        except Exception:
            logger.exception("Error processing message")
        finally:
            message_queue.task_done()


# --- Weekly Digest 스케줄러 ---
async def _run_digest():
    """모든 타겟 방에 대해 다이제스트 생성 + 전송."""
    from app.digest import generate_digest, clear_old_signals

    cfg = get_config()
    target_rooms = cfg.get("target_rooms", [])

    if not target_rooms:
        logger.warning("Digest: no target_rooms configured, skipping")
        return

    for room in target_rooms:
        try:
            digest_text = await generate_digest(room)
            if digest_text:
                await _broadcast_response(room, digest_text)
                logger.info(f"Digest sent to {room}")
            else:
                logger.info(f"Digest skipped for {room} (insufficient signals)")
        except Exception:
            logger.exception(f"Digest failed for {room}")

    clear_old_signals()


def _schedule_digest_job():
    """APScheduler로 주간 다이제스트 cron 등록."""
    global _scheduler
    cfg = get_config()
    digest_cfg = cfg.get("digest", {})

    if not digest_cfg.get("enabled", False):
        logger.info("Digest scheduler disabled")
        return

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning("APScheduler not installed, digest scheduler disabled")
        return

    schedule = digest_cfg.get("schedule", "0 8 * * 1")
    timezone = digest_cfg.get("timezone", "Asia/Seoul")

    parts = schedule.split()
    trigger = CronTrigger(
        minute=parts[0],
        hour=parts[1],
        day=parts[2] if parts[2] != "*" else None,
        month=parts[3] if parts[3] != "*" else None,
        day_of_week=parts[4] if parts[4] != "*" else None,
        timezone=timezone,
    )

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(_run_digest, trigger, id="weekly_digest")
    _scheduler.start()
    logger.info(f"Digest scheduler started: {schedule} ({timezone})")


# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    logging.basicConfig(
        level=cfg["logging"]["level"],
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    logger.info(f"KakaoChat AI Server starting — mode={cfg['response_mode']}")
    logger.info(f"LLM: {cfg['llm']['model']}")

    task = asyncio.create_task(process_messages())
    _schedule_digest_job()
    yield
    task.cancel()
    if _scheduler:
        _scheduler.shutdown(wait=False)
    # Claude 세션 정리 (per-room 모델 오버라이드로 인해 항상 정리)
    from app.claude_session import stop_all_sessions
    await stop_all_sessions()
    logger.info("Server shutting down")


# --- App ---
app = FastAPI(title="KakaoChat AI Server", lifespan=lifespan)


@app.get("/health")
async def health():
    cfg = get_config()
    registry = get_registry()
    return {
        "status": "ok",
        "response_mode": cfg["response_mode"],
        "connected_clients": len(connected_clients),
        "total_messages_received": total_messages_received,
        "active_rooms": registry.active_count,
        "digest_enabled": cfg.get("digest", {}).get("enabled", False),
    }


@app.post("/auth/register")
async def register_auth(data: dict):
    """방에 Claude OAuth 토큰 등록."""
    from app.auth import register_token
    room = data.get("room", "")
    token = data.get("token", "")
    email = data.get("email", "")
    if not room or not token:
        return {"status": "error", "message": "room and token are required"}
    result = register_token(room, token, email)
    # 기존 세션이 있으면 새 토큰으로 재시작
    from app.claude_session import clear_session
    await clear_session(room)
    return result


@app.delete("/auth/{room}")
async def remove_auth(room: str):
    """방의 토큰 삭제."""
    from app.auth import remove_token
    removed = remove_token(room)
    if removed:
        from app.claude_session import clear_session
        await clear_session(room)
        return {"status": "ok", "room": room}
    return {"status": "not_found", "room": room}


@app.get("/auth/rooms")
async def list_auth_rooms():
    """등록된 방 목록 조회."""
    from app.auth import list_rooms
    return {"status": "ok", "rooms": list_rooms()}


@app.get("/sessions")
async def list_sessions():
    """Claude 세션 상태 조회."""
    from app.claude_session import get_all_status
    return {"status": "ok", "sessions": get_all_status()}


@app.post("/clear/{room}")
async def api_clear_session(room: str):
    """세션 초기화 API."""
    from app.claude_session import clear_session
    cleared = await clear_session(room)
    if cleared:
        return {"status": "ok", "room": room}
    return {"status": "not_found", "room": room}


# --- v0.5: Room 관리 API ---
@app.get("/rooms")
async def list_rooms():
    """활성 방 목록 + 통계."""
    registry = get_registry()
    return {"status": "ok", "rooms": registry.list_rooms()}


@app.get("/rooms/{room}")
async def get_room(room: str):
    """개별 방 상태 조회."""
    registry = get_registry()
    entry = registry.get(room)
    if not entry:
        return {"status": "not_found", "room": room}
    return {
        "status": "ok",
        "room": room,
        "stats": {
            "message_count": entry.stats.message_count,
            "response_count": entry.stats.response_count,
            "first_seen": entry.stats.first_seen,
            "last_active": entry.stats.last_active,
        },
        "effective_config": registry.get_effective_config(room),
    }


@app.patch("/rooms/{room}")
async def update_room_config(room: str, data: dict):
    """방별 설정 오버라이드 (response_mode, llm_model)."""
    registry = get_registry()
    allowed_keys = {"response_mode", "llm_model"}
    overrides = {k: v for k, v in data.items() if k in allowed_keys}
    if not overrides:
        return {"status": "error", "message": f"Allowed keys: {allowed_keys}"}

    old_cfg = registry.get_effective_config(room)
    registry.update_room_config(room, overrides)
    new_cfg = registry.get_effective_config(room)

    # Claude 모드에서 벗어나면 기존 세션 정리
    old_is_claude = old_cfg.get("llm_model", "").startswith("claude/") and old_cfg.get("response_mode") == "active"
    new_is_claude = new_cfg.get("llm_model", "").startswith("claude/") and new_cfg.get("response_mode") == "active"
    if old_is_claude and not new_is_claude:
        from app.claude_session import clear_session
        await clear_session(room)

    return {
        "status": "ok",
        "room": room,
        "effective_config": new_cfg,
    }


@app.post("/digest/{room}")
async def trigger_digest(room: str):
    """수동 다이제스트 트리거 (테스트/디버깅용)."""
    from app.digest import generate_digest
    digest_text = await generate_digest(room)
    if digest_text:
        await _broadcast_response(room, digest_text)
        return {"status": "ok", "room": room, "length": len(digest_text)}
    return {"status": "skipped", "room": room, "reason": "insufficient signals"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(default="")):
    global total_messages_received
    cfg = get_config()

    # Bearer token 인증 (설정된 경우)
    auth_token = cfg["server"].get("auth_token", "")
    if auth_token and token != auth_token:
        await ws.close(code=4001, reason="Unauthorized")
        return

    await ws.accept()
    connected_clients.add(ws)
    logger.info(f"Bridge connected (total: {len(connected_clients)})")

    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
                msg = ChatMessage(**data)
                total_messages_received += 1
                await message_queue.put(msg)

                # ACK
                await ws.send_text(json.dumps({"status": "ok", "ts": msg.ts}))

            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Invalid message: {e}")
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(json.dumps({"status": "error", "message": str(e)}))

    except WebSocketDisconnect:
        logger.info("Bridge disconnected")
    except Exception:
        logger.exception("WebSocket error")
    finally:
        connected_clients.discard(ws)
        logger.info(f"Bridge removed (total: {len(connected_clients)})")

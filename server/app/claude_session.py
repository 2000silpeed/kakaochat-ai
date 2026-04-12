"""Claude Code 세션 관리 — 방별 영속 세션 프로세스."""
import asyncio
import json
import logging
import uuid
from pathlib import Path

from app.config import get_config

logger = logging.getLogger("kakaochat.claude_session")

_sessions: dict[str, "ClaudeSession"] = {}

BOT_SYSTEM_PROMPT = (
    "너는 카카오톡 오픈챗방 AI 어시스턴트 '카챗AI'야.\n"
    "규칙:\n"
    "- 자연스럽고 간결하게 한국어로 답해\n"
    "- 답변은 2-3문장 이내로 짧게\n"
    "- 기억된 대화 맥락이 있으면 활용하고, 없으면 솔직히 모른다고 해\n"
    "- 이모지는 적절히 사용하되 과하지 않게\n"
    "- 코드나 기술 관련 질문에는 정확하게 답해\n"
    "- 너는 방 안의 대화를 계속 듣고 있으므로, 맥락을 파악해서 답변해\n"
    "- 도구(Bash, Read, Edit 등)는 절대 사용하지 마. 텍스트 답변만 해"
)


class ClaudeSession:
    def __init__(self, room: str, session_id: str | None = None):
        self.room = room
        self.session_id = session_id or str(uuid.uuid4())
        self.process: asyncio.subprocess.Process | None = None
        self._ready = False
        self._lock = asyncio.Lock()
        self._message_count = 0

    @property
    def room_dir(self) -> Path:
        safe_name = self.room.replace("/", "_").replace(" ", "_")
        return Path("data/rooms") / safe_name

    def _ensure_room_dir(self):
        room_dir = self.room_dir
        room_dir.mkdir(parents=True, exist_ok=True)
        claude_dir = room_dir / ".claude" / "memory"
        claude_dir.mkdir(parents=True, exist_ok=True)
        memory_index = claude_dir.parent / "memory" / "MEMORY.md"
        if not memory_index.exists():
            memory_index.write_text(
                f"# {self.room} 메모리\n\n"
                "이 방에서 학습한 내용이 여기에 기록됩니다.\n"
            )
        claude_md = room_dir / "CLAUDE.md"
        if not claude_md.exists():
            claude_md.write_text(
                f"# {self.room} 오픈챗방\n\n"
                "이 디렉터리는 카카오톡 오픈챗방의 컨텍스트를 저장합니다.\n"
                "대화 내용을 기억하고, 방 멤버들의 질문에 답변하세요.\n"
            )

    async def start(self):
        self._ensure_room_dir()
        cfg = get_config()
        claude_cfg = cfg.get("llm", {}).get("claude", {})
        model = claude_cfg.get("model", "sonnet")

        cmd = [
            "claude", "-p",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
            "--session-id", self.session_id,
            "--model", model,
            "--system-prompt", BOT_SYSTEM_PROMPT,
            "--add-dir", str(self.room_dir.resolve()),
            "--allowedTools", "",
            "--permission-mode", "plan",
        ]

        logger.info(f"Starting Claude session for '{self.room}' (id={self.session_id[:8]}...)")

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.room_dir.resolve()),
        )

        init_msg = await self._wait_for_init()
        if init_msg:
            self._ready = True
            logger.info(f"Claude session ready for '{self.room}'")
        else:
            logger.error(f"Claude session failed to initialize for '{self.room}'")

    async def _wait_for_init(self, timeout: float = 60) -> dict | None:
        try:
            end_time = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < end_time:
                line = await asyncio.wait_for(
                    self.process.stdout.readline(), timeout=10
                )
                if not line:
                    break
                try:
                    data = json.loads(line.decode().strip())
                    if data.get("type") == "system" and data.get("subtype") == "init":
                        return data
                except json.JSONDecodeError:
                    continue
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for init in '{self.room}'")
        return None

    async def send_message(self, sender: str, text: str, context: str = "") -> str | None:
        if not self._ready or not self.process or self.process.returncode is not None:
            logger.warning(f"Session not ready for '{self.room}', restarting...")
            await self.restart()
            if not self._ready:
                return None

        async with self._lock:
            return await self._send_and_receive(sender, text, context)

    async def _send_and_receive(self, sender: str, text: str, context: str) -> str | None:
        content = f"[{self.room}] {sender}: {text}"
        if context:
            content += f"\n\n추가 맥락:\n{context}"

        msg = json.dumps({
            "type": "user",
            "message": {"role": "user", "content": content},
        }, ensure_ascii=False)

        try:
            self.process.stdin.write((msg + "\n").encode())
            await self.process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            logger.error(f"Broken pipe for '{self.room}', restarting session")
            await self.restart()
            return None

        response_text = await self._collect_response()
        if response_text:
            self._message_count += 1
        return response_text

    async def _collect_response(self, timeout: float = 60) -> str | None:
        texts = []
        try:
            end_time = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < end_time:
                remaining = end_time - asyncio.get_event_loop().time()
                line = await asyncio.wait_for(
                    self.process.stdout.readline(),
                    timeout=min(remaining, 30),
                )
                if not line:
                    break

                try:
                    data = json.loads(line.decode().strip())
                except json.JSONDecodeError:
                    continue

                msg_type = data.get("type")

                if msg_type == "assistant":
                    content = data.get("message", {}).get("content", [])
                    for block in content:
                        if block.get("type") == "text":
                            texts.append(block["text"])

                elif msg_type == "result":
                    if not texts and data.get("result"):
                        texts.append(data["result"])
                    break

        except asyncio.TimeoutError:
            logger.warning(f"Timeout collecting response for '{self.room}'")

        return "\n".join(texts).strip() if texts else None

    async def restart(self):
        await self.stop()
        self.session_id = str(uuid.uuid4())
        self._message_count = 0
        await self.start()

    async def clear(self):
        logger.info(f"Clearing session for '{self.room}'")
        await self.restart()

    async def stop(self):
        if self.process and self.process.returncode is None:
            try:
                self.process.stdin.close()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self.process.terminate()
                    await asyncio.wait_for(self.process.wait(), timeout=3)
            except Exception:
                try:
                    self.process.kill()
                except ProcessLookupError:
                    pass
        self.process = None
        self._ready = False
        logger.info(f"Session stopped for '{self.room}'")

    def get_status(self) -> dict:
        return {
            "room": self.room,
            "session_id": self.session_id,
            "ready": self._ready,
            "message_count": self._message_count,
            "alive": self.process is not None and self.process.returncode is None,
        }


async def get_session(room: str) -> ClaudeSession:
    if room not in _sessions or not _sessions[room]._ready:
        cfg = get_config()
        max_sessions = cfg.get("llm", {}).get("claude", {}).get("max_concurrent_sessions", 3)
        if len(_sessions) >= max_sessions and room not in _sessions:
            oldest = min(_sessions.values(), key=lambda s: s._message_count)
            logger.warning(f"Max sessions reached, evicting '{oldest.room}'")
            await oldest.stop()
            del _sessions[oldest.room]

        session = ClaudeSession(room)
        await session.start()
        _sessions[room] = session

    return _sessions[room]


async def clear_session(room: str) -> bool:
    if room in _sessions:
        await _sessions[room].clear()
        return True
    return False


async def stop_all_sessions():
    for session in _sessions.values():
        await session.stop()
    _sessions.clear()
    logger.info("All Claude sessions stopped")


def get_all_status() -> list[dict]:
    return [s.get_status() for s in _sessions.values()]

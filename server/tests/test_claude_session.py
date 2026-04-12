"""Claude Code 세션 관리 테스트."""
import asyncio
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import load_config
from app.claude_session import (
    ClaudeSession,
    get_session,
    clear_session,
    stop_all_sessions,
    get_all_status,
    _sessions,
    BOT_SYSTEM_PROMPT,
)

load_config()


class TestClaudeSession:
    def test_room_dir_creation(self, tmp_path):
        session = ClaudeSession("AI스터디")
        with patch.object(type(session), "room_dir", new_callable=lambda: property(lambda self: tmp_path / "AI스터디")):
            session._ensure_room_dir()
            assert (tmp_path / "AI스터디" / ".claude" / "memory").exists()
            assert (tmp_path / "AI스터디" / "CLAUDE.md").exists()

    def test_session_id_auto_generated(self):
        session = ClaudeSession("테스트방")
        assert session.session_id is not None
        uuid.UUID(session.session_id)

    def test_session_id_custom(self):
        custom_id = str(uuid.uuid4())
        session = ClaudeSession("테스트방", session_id=custom_id)
        assert session.session_id == custom_id

    def test_initial_status(self):
        session = ClaudeSession("테스트방")
        status = session.get_status()
        assert status["room"] == "테스트방"
        assert status["ready"] is False
        assert status["message_count"] == 0
        assert status["alive"] is False

    def test_system_prompt_exists(self):
        assert "카카오톡" in BOT_SYSTEM_PROMPT
        assert "한국어" in BOT_SYSTEM_PROMPT


class TestClaudeSessionProcess:
    @pytest.mark.asyncio
    async def test_send_message_when_not_ready(self):
        session = ClaudeSession("테스트방")
        with patch.object(session, "restart", new_callable=AsyncMock) as mock_restart:
            mock_restart.side_effect = lambda: setattr(session, '_ready', False)
            result = await session.send_message("철수", "안녕?")
            assert result is None

    @pytest.mark.asyncio
    async def test_stop_without_process(self):
        session = ClaudeSession("테스트방")
        await session.stop()
        assert session._ready is False
        assert session.process is None

    @pytest.mark.asyncio
    async def test_clear_creates_new_session_id(self):
        session = ClaudeSession("테스트방")
        old_id = session.session_id
        with patch.object(session, "stop", new_callable=AsyncMock):
            with patch.object(session, "start", new_callable=AsyncMock):
                await session.clear()
        assert session.session_id != old_id

    @pytest.mark.asyncio
    async def test_collect_response_from_stream(self):
        session = ClaudeSession("테스트방")
        session._ready = True

        mock_process = AsyncMock()
        mock_process.returncode = None

        assistant_msg = json.dumps({
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "안녕하세요!"}]
            }
        }).encode() + b"\n"
        result_msg = json.dumps({
            "type": "result",
            "result": "안녕하세요!",
        }).encode() + b"\n"

        read_lines = iter([assistant_msg, result_msg])
        mock_process.stdout.readline = AsyncMock(side_effect=lambda: next(read_lines, b""))

        session.process = mock_process
        response = await session._collect_response(timeout=5)
        assert response == "안녕하세요!"


class TestSessionManager:
    def setup_method(self):
        _sessions.clear()

    @pytest.mark.asyncio
    async def test_clear_nonexistent_session(self):
        result = await clear_session("없는방")
        assert result is False

    @pytest.mark.asyncio
    async def test_stop_all_empty(self):
        await stop_all_sessions()
        assert len(_sessions) == 0

    def test_get_all_status_empty(self):
        assert get_all_status() == []

    def test_get_all_status_with_sessions(self):
        session = ClaudeSession("테스트방")
        _sessions["테스트방"] = session
        statuses = get_all_status()
        assert len(statuses) == 1
        assert statuses[0]["room"] == "테스트방"
        _sessions.clear()

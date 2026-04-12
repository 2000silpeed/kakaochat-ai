"""v0.5: Room Registry + per-room rate limiting 테스트."""
import time
import pytest

from app.config import load_config
from app.room_registry import RoomRegistry
from app.participation import (
    _check_rate_limit,
    _record_response,
    reset_consecutive,
    _get_rate_state,
    _room_rate_states,
)

load_config()


class TestRoomRegistry:
    def setup_method(self):
        self.registry = RoomRegistry()

    def test_register_new_room(self):
        entry = self.registry.register("AI스터디")
        assert entry.room == "AI스터디"
        assert entry.stats.message_count == 0
        assert entry.stats.first_seen > 0

    def test_register_idempotent(self):
        e1 = self.registry.register("AI스터디")
        e2 = self.registry.register("AI스터디")
        assert e1 is e2

    def test_record_message(self):
        self.registry.record_message("AI스터디")
        self.registry.record_message("AI스터디")
        entry = self.registry.get("AI스터디")
        assert entry.stats.message_count == 2

    def test_record_response(self):
        self.registry.record_message("AI스터디")
        self.registry.record_response("AI스터디")
        entry = self.registry.get("AI스터디")
        assert entry.stats.response_count == 1

    def test_list_rooms_sorted_by_last_active(self):
        self.registry.record_message("방A")
        time.sleep(0.01)
        self.registry.record_message("방B")
        rooms = self.registry.list_rooms()
        assert rooms[0]["room"] == "방B"
        assert rooms[1]["room"] == "방A"

    def test_active_count(self):
        assert self.registry.active_count == 0
        self.registry.record_message("방A")
        self.registry.record_message("방B")
        assert self.registry.active_count == 2

    def test_get_nonexistent_room(self):
        assert self.registry.get("없는방") is None

    def test_update_room_config(self):
        self.registry.update_room_config("AI스터디", {"response_mode": "off"})
        entry = self.registry.get("AI스터디")
        assert entry.config_override["response_mode"] == "off"

    def test_effective_config_default(self):
        self.registry.register("AI스터디")
        cfg = self.registry.get_effective_config("AI스터디")
        assert "response_mode" in cfg
        assert "llm_model" in cfg

    def test_effective_config_override(self):
        self.registry.update_room_config("AI스터디", {"response_mode": "off"})
        cfg = self.registry.get_effective_config("AI스터디")
        assert cfg["response_mode"] == "off"


class TestPerRoomRateLimit:
    def setup_method(self):
        _room_rate_states.clear()

    def test_independent_rooms(self):
        assert _check_rate_limit("방A")
        _record_response("방A")
        # 방A는 제한, 방B는 허용
        assert not _check_rate_limit("방A")
        assert _check_rate_limit("방B")

    def test_per_room_cooldown(self):
        for _ in range(3):
            state = _get_rate_state("방A")
            state.response_timestamps.clear()
            _record_response("방A")
        # 방A 쿨다운, 방B는 무관
        assert not _check_rate_limit("방A")
        assert _check_rate_limit("방B")

    def test_reset_consecutive_per_room(self):
        _record_response("방A")
        _record_response("방B")
        reset_consecutive("방A")
        assert _get_rate_state("방A").consecutive_count == 0
        assert _get_rate_state("방B").consecutive_count == 1

    def test_first_response_allowed(self):
        assert _check_rate_limit("새방")

    def test_per_minute_limit(self):
        _record_response("방A")
        assert not _check_rate_limit("방A")

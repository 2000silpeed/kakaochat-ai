"""Room Registry — 다중 채팅방 관리, 통계 추적, per-room 설정 오버라이드."""
import logging
import time
from dataclasses import dataclass, field
from threading import Lock

from app.config import get_config

logger = logging.getLogger("kakaochat.room_registry")


@dataclass
class RoomStats:
    first_seen: float = 0.0
    last_active: float = 0.0
    message_count: int = 0
    response_count: int = 0


@dataclass
class RoomEntry:
    room: str
    stats: RoomStats = field(default_factory=RoomStats)
    config_override: dict = field(default_factory=dict)


class RoomRegistry:
    def __init__(self):
        self._rooms: dict[str, RoomEntry] = {}
        self._lock = Lock()

    def register(self, room: str) -> RoomEntry:
        with self._lock:
            if room not in self._rooms:
                now = time.time()
                entry = RoomEntry(
                    room=room,
                    stats=RoomStats(first_seen=now, last_active=now),
                )
                self._rooms[room] = entry
                logger.info(f"Room registered: {room}")
            return self._rooms[room]

    def record_message(self, room: str):
        entry = self.register(room)
        entry.stats.last_active = time.time()
        entry.stats.message_count += 1

    def record_response(self, room: str):
        entry = self.register(room)
        entry.stats.response_count += 1

    def get(self, room: str) -> RoomEntry | None:
        return self._rooms.get(room)

    def list_rooms(self) -> list[dict]:
        result = []
        for entry in self._rooms.values():
            result.append({
                "room": entry.room,
                "message_count": entry.stats.message_count,
                "response_count": entry.stats.response_count,
                "last_active": entry.stats.last_active,
                "config_override": entry.config_override,
            })
        return sorted(result, key=lambda r: r["last_active"], reverse=True)

    def get_room_config(self, room: str, key: str, default=None):
        entry = self._rooms.get(room)
        if entry and key in entry.config_override:
            return entry.config_override[key]

        room_configs = get_config().get("rooms", {})
        if room in room_configs and key in room_configs[room]:
            return room_configs[room][key]

        return default

    def update_room_config(self, room: str, overrides: dict):
        entry = self.register(room)
        entry.config_override.update(overrides)
        logger.info(f"Room config updated: {room} -> {overrides}")

    def get_effective_config(self, room: str) -> dict:
        cfg = get_config()
        base = {
            "response_mode": cfg.get("response_mode", "passive"),
            "llm_model": cfg["llm"]["model"],
        }

        room_configs = cfg.get("rooms", {})
        if room in room_configs:
            base.update(room_configs[room])

        entry = self._rooms.get(room)
        if entry:
            base.update(entry.config_override)

        return base

    @property
    def active_count(self) -> int:
        return len(self._rooms)


_registry = RoomRegistry()


def get_registry() -> RoomRegistry:
    return _registry

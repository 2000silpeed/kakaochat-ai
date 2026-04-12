"""인증 토큰 관리 — 방별 Claude OAuth 토큰 저장/조회."""
import hashlib
import json
import logging
import os
import secrets
from pathlib import Path

from app.config import get_config

logger = logging.getLogger("kakaochat.auth")

_TOKENS_FILE = Path("data/tokens.json")
_tokens: dict | None = None


def _get_encryption_key() -> str:
    key = os.environ.get("KAKAOCHAT_SECRET_KEY", "")
    if not key:
        key_file = Path("data/.secret_key")
        if key_file.exists():
            key = key_file.read_text().strip()
        else:
            key = secrets.token_hex(32)
            key_file.parent.mkdir(parents=True, exist_ok=True)
            key_file.write_text(key)
            os.chmod(key_file, 0o600)
    return key


def _xor_encrypt(data: str, key: str) -> str:
    key_bytes = hashlib.sha256(key.encode()).digest()
    data_bytes = data.encode()
    encrypted = bytes(d ^ key_bytes[i % len(key_bytes)] for i, d in enumerate(data_bytes))
    return encrypted.hex()


def _xor_decrypt(hex_data: str, key: str) -> str:
    key_bytes = hashlib.sha256(key.encode()).digest()
    encrypted = bytes.fromhex(hex_data)
    decrypted = bytes(d ^ key_bytes[i % len(key_bytes)] for i, d in enumerate(encrypted))
    return decrypted.decode()


def _load_tokens() -> dict:
    global _tokens
    if _tokens is not None:
        return _tokens
    if _TOKENS_FILE.exists():
        with open(_TOKENS_FILE, "r", encoding="utf-8") as f:
            _tokens = json.load(f)
    else:
        _tokens = {}
    return _tokens


def _save_tokens():
    _TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(_tokens, f, ensure_ascii=False, indent=2)
    os.chmod(_TOKENS_FILE, 0o600)


def register_token(room: str, token: str, email: str = "") -> dict:
    """방에 Claude OAuth 토큰 등록."""
    tokens = _load_tokens()
    key = _get_encryption_key()

    tokens[room] = {
        "token_encrypted": _xor_encrypt(token, key),
        "email": email,
    }
    _save_tokens()
    logger.info(f"Token registered for room '{room}' (email={email})")
    return {"status": "ok", "room": room, "email": email}


def get_token(room: str) -> str | None:
    """방의 Claude OAuth 토큰 조회. 없으면 None."""
    tokens = _load_tokens()
    entry = tokens.get(room)
    if not entry:
        return None

    key = _get_encryption_key()
    try:
        return _xor_decrypt(entry["token_encrypted"], key)
    except Exception:
        logger.error(f"Failed to decrypt token for room '{room}'")
        return None


def remove_token(room: str) -> bool:
    """방의 토큰 삭제."""
    tokens = _load_tokens()
    if room in tokens:
        del tokens[room]
        _save_tokens()
        logger.info(f"Token removed for room '{room}'")
        return True
    return False


def list_rooms() -> list[dict]:
    """등록된 방 목록 (토큰은 제외)."""
    tokens = _load_tokens()
    return [
        {"room": room, "email": entry.get("email", "")}
        for room, entry in tokens.items()
    ]


def has_token(room: str) -> bool:
    """방에 토큰이 등록되어 있는지 확인."""
    tokens = _load_tokens()
    return room in tokens


def reset_tokens():
    """테스트용 토큰 데이터 리셋."""
    global _tokens
    _tokens = {}
    if _TOKENS_FILE.exists():
        _TOKENS_FILE.unlink()

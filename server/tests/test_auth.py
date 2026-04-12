"""인증 토큰 관리 테스트."""
import os

import pytest

from app.config import load_config
from app.auth import (
    register_token,
    get_token,
    remove_token,
    list_rooms,
    has_token,
    reset_tokens,
    _xor_encrypt,
    _xor_decrypt,
)

load_config()


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        key = "test-secret-key"
        original = "my-super-secret-token-123"
        encrypted = _xor_encrypt(original, key)
        decrypted = _xor_decrypt(encrypted, key)
        assert decrypted == original

    def test_encrypted_differs_from_original(self):
        key = "test-key"
        original = "secret-token"
        encrypted = _xor_encrypt(original, key)
        assert encrypted != original

    def test_different_keys_produce_different_results(self):
        data = "same-data"
        enc1 = _xor_encrypt(data, "key1")
        enc2 = _xor_encrypt(data, "key2")
        assert enc1 != enc2


class TestTokenManagement:
    def setup_method(self):
        reset_tokens()

    def test_register_and_get(self):
        register_token("AI스터디", "test-token-123", "user@test.com")
        token = get_token("AI스터디")
        assert token == "test-token-123"

    def test_get_nonexistent(self):
        token = get_token("없는방")
        assert token is None

    def test_has_token(self):
        register_token("AI스터디", "token-abc")
        assert has_token("AI스터디") is True
        assert has_token("없는방") is False

    def test_remove_token(self):
        register_token("AI스터디", "token-abc")
        assert remove_token("AI스터디") is True
        assert get_token("AI스터디") is None

    def test_remove_nonexistent(self):
        assert remove_token("없는방") is False

    def test_list_rooms(self):
        register_token("AI스터디", "token-1", "a@test.com")
        register_token("개발방", "token-2", "b@test.com")
        rooms = list_rooms()
        assert len(rooms) == 2
        room_names = [r["room"] for r in rooms]
        assert "AI스터디" in room_names
        assert "개발방" in room_names

    def test_list_rooms_empty(self):
        rooms = list_rooms()
        assert rooms == []

    def test_overwrite_token(self):
        register_token("AI스터디", "old-token", "old@test.com")
        register_token("AI스터디", "new-token", "new@test.com")
        token = get_token("AI스터디")
        assert token == "new-token"
        rooms = list_rooms()
        assert len(rooms) == 1
        assert rooms[0]["email"] == "new@test.com"

    def test_register_returns_status(self):
        result = register_token("AI스터디", "token", "user@test.com")
        assert result["status"] == "ok"
        assert result["room"] == "AI스터디"
        assert result["email"] == "user@test.com"

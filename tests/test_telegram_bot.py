import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch

from src.telegram_bot import (
    load_users,
    get_user_id,
    is_user_silenced,
)


class TestLoadUsers:
    def test_returns_empty_dict_when_no_file(self, tmp_path):
        fake_path = str(tmp_path / "nonexistent.json")
        with patch("src.telegram_bot.USERS_PATH", fake_path):
            result = load_users()
            assert result == {}

    def test_loads_users_from_file(self, tmp_path):
        users_file = tmp_path / "users.json"
        users_file.write_text(json.dumps({
            "123": {"name": "matheus"},
            "456": {"name": "cecilia"},
        }))
        with patch("src.telegram_bot.USERS_PATH", str(users_file)):
            result = load_users()
            assert result["123"]["name"] == "matheus"
            assert result["456"]["name"] == "cecilia"


class TestGetUserId:
    def test_returns_name_for_existing_user(self, tmp_path):
        users_file = tmp_path / "users.json"
        users_file.write_text(json.dumps({"123": {"name": "matheus"}}))
        with patch("src.telegram_bot.USERS_PATH", str(users_file)):
            assert get_user_id(123) == "matheus"

    def test_returns_none_for_unknown_user(self, tmp_path):
        users_file = tmp_path / "users.json"
        users_file.write_text(json.dumps({"123": {"name": "matheus"}}))
        with patch("src.telegram_bot.USERS_PATH", str(users_file)):
            assert get_user_id(999) is None


class TestIsUserSilenced:
    def test_returns_false_when_not_silenced(self, tmp_path):
        users_file = tmp_path / "users.json"
        users_file.write_text(json.dumps({"123": {"name": "matheus"}}))
        with patch("src.telegram_bot.USERS_PATH", str(users_file)):
            assert is_user_silenced(123) is False

    def test_returns_true_when_silenced(self, tmp_path):
        future = (datetime.now() + timedelta(hours=1)).isoformat()
        users_file = tmp_path / "users.json"
        users_file.write_text(json.dumps({
            "123": {"name": "matheus", "silenced_until": future}
        }))
        with patch("src.telegram_bot.USERS_PATH", str(users_file)):
            assert is_user_silenced(123) is True

    def test_returns_false_when_silence_expired(self, tmp_path):
        past = (datetime.now() - timedelta(hours=1)).isoformat()
        users_file = tmp_path / "users.json"
        users_file.write_text(json.dumps({
            "123": {"name": "matheus", "silenced_until": past}
        }))
        with patch("src.telegram_bot.USERS_PATH", str(users_file)):
            assert is_user_silenced(123) is False

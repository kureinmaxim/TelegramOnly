"""
Persistent storage for per-user preferences and special user list.
"""

import errno
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List

# Thread safety for concurrent handler access
_storage_lock = threading.Lock()

# Resolve storage path from env or default to project root file
_USER_STORE_PATH = os.getenv("USER_STORE_PATH", os.path.join(os.getcwd(), "users.json"))

# Data shape:
# {
#   "special_user_ids": [123, 456],
#   "users": {
#       "123": {"city": "City Name", "greeting": "Custom greeting"}
#   },
#   "settings": {"echo_enabled": false}
# }

def _ensure_defaults(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        data = {}
    data.setdefault("special_user_ids", [])
    data.setdefault("users", {})
    settings = data.setdefault("settings", {})
    settings.setdefault("echo_enabled", False)
    return data

def _load_data() -> Dict[str, Any]:
    with _storage_lock:
        if not os.path.exists(_USER_STORE_PATH):
            return _ensure_defaults({})
        try:
            with open(_USER_STORE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return _ensure_defaults(data)
        except Exception:
            # Corrupted file or read error -> fallback to defaults
            return _ensure_defaults({})

def _atomic_write(data: Dict[str, Any]) -> None:
    with _storage_lock:
        directory = os.path.dirname(_USER_STORE_PATH) or "."
        os.makedirs(directory, exist_ok=True)
        serialized = json.dumps(data, ensure_ascii=False, indent=2)
        fd, tmp_path = tempfile.mkstemp(prefix="users_", suffix=".json", dir=directory)
        renamed = False
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(serialized)
            try:
                os.replace(tmp_path, _USER_STORE_PATH)
                renamed = True
            except OSError as e:
                # Docker single-file bind mount pins the inode; os.replace
                # fails with EBUSY. Fall back to in-place truncate+write.
                if e.errno not in (errno.EBUSY, errno.EXDEV):
                    raise
                with open(_USER_STORE_PATH, "w", encoding="utf-8") as f:
                    f.write(serialized)
        finally:
            if not renamed:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass

# --- Public API ---

def get_user_city(user_id: int) -> Optional[str]:
    data = _load_data()
    user = data["users"].get(str(user_id))
    if not user:
        return None
    city = user.get("city")
    return city if city else None

def set_user_city(user_id: int, city: str) -> None:
    data = _load_data()
    user = data["users"].setdefault(str(user_id), {})
    user["city"] = city
    _atomic_write(data)

def get_user_greeting(user_id: int) -> Optional[str]:
    data = _load_data()
    user = data["users"].get(str(user_id))
    if not user:
        return None
    greeting = user.get("greeting")
    return greeting if greeting else None

def set_user_greeting(user_id: int, greeting: str) -> None:
    data = _load_data()
    user = data["users"].setdefault(str(user_id), {})
    user["greeting"] = greeting
    _atomic_write(data)

def is_special_user(user_id: int) -> bool:
    data = _load_data()
    try:
        return int(user_id) in data.get("special_user_ids", [])
    except Exception:
        return False

def add_special_user(user_id: int) -> None:
    data = _load_data()
    special = data.setdefault("special_user_ids", [])
    if int(user_id) not in special:
        special.append(int(user_id))
        _atomic_write(data)

def remove_special_user(user_id: int) -> None:
    data = _load_data()
    special = data.setdefault("special_user_ids", [])
    if int(user_id) in special:
        special.remove(int(user_id))
        _atomic_write(data)

def track_user(
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> None:
    """Record that a user interacted with the bot. Stores identity + last_seen."""
    data = _load_data()
    user = data["users"].setdefault(str(user_id), {})
    if username is not None:
        user["username"] = username
    if first_name is not None:
        user["first_name"] = first_name
    if last_name is not None:
        user["last_name"] = last_name
    user["last_seen"] = datetime.now(timezone.utc).isoformat()
    user.setdefault("first_seen", user["last_seen"])
    _atomic_write(data)


def list_users() -> Tuple[List[int], Dict[int, Dict[str, Any]]]:
    data = _load_data()
    special = [int(x) for x in data.get("special_user_ids", [])]
    users: Dict[int, Dict[str, Any]] = {}
    for k, v in data.get("users", {}).items():
        try:
            users[int(k)] = v
        except ValueError:
            continue
    return special, users

# --- Global settings ---

def get_echo_enabled() -> bool:
    data = _load_data()
    return bool(data.get("settings", {}).get("echo_enabled", False))

def set_echo_enabled(enabled: bool) -> None:
    data = _load_data()
    settings = data.setdefault("settings", {})
    settings["echo_enabled"] = bool(enabled)
    _atomic_write(data)

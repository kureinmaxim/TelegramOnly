# -*- coding: utf-8 -*-
"""
Модуль для управления Headscale (self-hosted Tailscale control plane).

Взаимодействует с Docker-контейнером Headscale через docker exec
для создания пользователей, генерации Pre-Auth ключей и мониторинга нод.

Структура конфигурации (headscale_config.json):
{
    "enabled": false,
    "container_name": "headscale",
    "server_url": "https://headscale.example.com",
    "default_user": "main_user",
    "key_expiration": "24h"
}
"""

import json
import os
import subprocess
import logging
import threading
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Thread safety
_hs_lock = threading.Lock()

# Путь к файлу конфигурации Headscale
_HS_CONFIG_PATH = os.getenv(
    "HEADSCALE_CONFIG_PATH",
    os.path.join(os.getcwd(), "headscale_config.json"),
)

DEFAULT_CONFIG = {
    "enabled": False,
    "container_name": "headscale",
    "server_url": "",
    "default_user": "main_user",
    "key_expiration": "24h",
    "created_at": None,
    "updated_at": None,
}


# === Internal helpers ===

def _load_config() -> Dict:
    """Загрузить конфигурацию Headscale из файла."""
    with _hs_lock:
        if not os.path.exists(_HS_CONFIG_PATH):
            return dict(DEFAULT_CONFIG)
        try:
            with open(_HS_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                config = dict(DEFAULT_CONFIG)
                config.update(data)
                return config
        except Exception as e:
            logger.error(f"Error loading Headscale config: {e}")
            return dict(DEFAULT_CONFIG)


def _save_config(config: Dict) -> bool:
    """Сохранить конфигурацию Headscale в файл."""
    with _hs_lock:
        try:
            config["updated_at"] = datetime.now().isoformat()
            if not config.get("created_at"):
                config["created_at"] = config["updated_at"]

            directory = os.path.dirname(_HS_CONFIG_PATH) or "."
            os.makedirs(directory, exist_ok=True)

            with open(_HS_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            return True
        except Exception as e:
            logger.error(f"Error saving Headscale config: {e}")
            return False


def _docker_exec(config: Dict, *args: str, timeout: int = 15) -> Tuple[bool, str]:
    """Run a headscale command inside the Docker container."""
    container = config.get("container_name", "headscale")
    cmd = ["docker", "exec", container, "headscale"] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, result.stderr.strip() or f"Exit code {result.returncode}"
    except FileNotFoundError:
        return False, "docker не найден в PATH"
    except subprocess.TimeoutExpired:
        return False, f"Таймаут ({timeout}с) при выполнении команды"
    except Exception as e:
        return False, str(e)


# === Public API ===

def is_headscale_enabled() -> bool:
    """Проверить, включён ли Headscale."""
    return _load_config().get("enabled", False)


def get_config() -> Dict:
    """Получить текущую конфигурацию Headscale."""
    return _load_config()


def enable_headscale() -> Tuple[bool, str]:
    """Включить Headscale."""
    config = _load_config()
    config["enabled"] = True
    if _save_config(config):
        return True, "✅ Headscale включён"
    return False, "❌ Ошибка при сохранении"


def disable_headscale() -> Tuple[bool, str]:
    """Выключить Headscale."""
    config = _load_config()
    config["enabled"] = False
    if _save_config(config):
        return True, "✅ Headscale выключен"
    return False, "❌ Ошибка при сохранении"


def set_server_url(url: str) -> Tuple[bool, str]:
    """Установить URL координатора Headscale."""
    url = url.strip().rstrip("/")
    if not url:
        return False, "❌ URL не может быть пустым"

    config = _load_config()
    config["server_url"] = url
    if _save_config(config):
        return True, f"✅ URL установлен: {url}"
    return False, "❌ Ошибка при сохранении"


def set_container_name(name: str) -> Tuple[bool, str]:
    """Установить имя Docker-контейнера Headscale."""
    name = name.strip()
    if not name:
        return False, "❌ Имя контейнера не может быть пустым"

    config = _load_config()
    config["container_name"] = name
    if _save_config(config):
        return True, f"✅ Контейнер: {name}"
    return False, "❌ Ошибка при сохранении"


def create_user(username: str) -> Tuple[bool, str]:
    """Создать пользователя в Headscale."""
    username = username.strip()
    if not username:
        return False, "❌ Имя пользователя не может быть пустым"

    config = _load_config()
    ok, output = _docker_exec(config, "users", "create", username)
    if ok:
        return True, f"✅ Пользователь создан: {username}"
    # «already exists» — не ошибка
    if "already exists" in output.lower():
        return True, f"ℹ️ Пользователь уже существует: {username}"
    return False, f"❌ Ошибка: {output}"


def create_preauth_key(
    user: Optional[str] = None,
    reusable: bool = True,
    expiration: Optional[str] = None,
) -> Tuple[bool, str, str]:
    """
    Создать Pre-Auth ключ для подключения клиента.

    Returns:
        (success, message, key)
    """
    config = _load_config()
    user = user or config.get("default_user", "main_user")
    expiration = expiration or config.get("key_expiration", "24h")

    args = ["preauthkeys", "create", "--user", user, "--expiration", expiration]
    if reusable:
        args.append("--reusable")

    ok, output = _docker_exec(config, *args)
    if not ok:
        return False, f"❌ Ошибка: {output}", ""

    # Headscale выводит ключ в последней строке или в таблице
    key = _parse_preauth_key(output)
    if key:
        return True, f"✅ Pre-Auth ключ создан (user: {user}, expiration: {expiration})", key
    return True, f"✅ Ключ создан, но не удалось распарсить вывод:\n{output}", output


def _parse_preauth_key(output: str) -> str:
    """Извлечь Pre-Auth ключ из вывода headscale."""
    # Headscale >= 0.23 выводит ключ на отдельной строке
    lines = output.strip().split("\n")
    for line in reversed(lines):
        line = line.strip()
        # Ключи обычно длинные hex/base64 строки
        if len(line) > 20 and " " not in line:
            return line
    # Fallback: вернуть весь вывод
    return output.strip()


def list_nodes() -> Tuple[bool, str, List[Dict]]:
    """Получить список подключённых нод."""
    config = _load_config()
    ok, output = _docker_exec(config, "nodes", "list", "-o", "json")
    if not ok:
        return False, f"❌ Ошибка: {output}", []

    try:
        nodes = json.loads(output)
        if not isinstance(nodes, list):
            nodes = []
        return True, f"✅ Найдено нод: {len(nodes)}", nodes
    except json.JSONDecodeError:
        return False, f"❌ Невалидный JSON:\n{output[:200]}", []


def list_users() -> Tuple[bool, str, List[str]]:
    """Получить список пользователей Headscale."""
    config = _load_config()
    ok, output = _docker_exec(config, "users", "list", "-o", "json")
    if not ok:
        return False, f"❌ Ошибка: {output}", []

    try:
        users = json.loads(output)
        if not isinstance(users, list):
            users = []
        names = [u.get("name", "?") for u in users if isinstance(u, dict)]
        return True, f"✅ Пользователей: {len(names)}", names
    except json.JSONDecodeError:
        return False, f"❌ Невалидный JSON:\n{output[:200]}", []


def get_status() -> Dict:
    """Получить статус Headscale (контейнер, ноды, URL)."""
    config = _load_config()
    status = {
        "enabled": config.get("enabled", False),
        "server_url": config.get("server_url", ""),
        "container_name": config.get("container_name", "headscale"),
        "container_running": False,
        "node_count": 0,
        "user_count": 0,
    }

    # Check if container is running
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", status["container_name"]],
            capture_output=True, text=True, timeout=5,
        )
        status["container_running"] = result.stdout.strip().lower() == "true"
    except Exception:
        pass

    # Get node count
    if status["container_running"]:
        ok, _, nodes = list_nodes()
        if ok:
            status["node_count"] = len(nodes)
        ok, _, users = list_users()
        if ok:
            status["user_count"] = len(users)

    return status


def export_client_instructions(preauth_key: str) -> str:
    """Сгенерировать инструкции для подключения клиента к Headscale."""
    config = _load_config()
    server_url = config.get("server_url", "https://headscale.example.com")

    return f"""== Подключение к Headscale ==

URL координатора: {server_url}
Pre-Auth ключ: {preauth_key}

--- Linux / macOS ---
tailscale up --login-server {server_url} --authkey {preauth_key}

--- Windows ---
1. Shift + клик на иконку Tailscale в трее
2. Preferences → Log in to custom control panel
3. URL: {server_url}
4. Или через PowerShell:
   tailscale up --login-server {server_url} --authkey {preauth_key}
"""

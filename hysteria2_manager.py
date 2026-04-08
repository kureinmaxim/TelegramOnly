# -*- coding: utf-8 -*-
"""
Модуль для управления Hysteria 2 конфигурацией.

Hysteria 2 — это высокоскоростной прокси-протокол на основе QUIC/UDP.
Отлично работает в сетях с потерями пакетов, поддерживает обфускацию.

Структура конфигурации:
{
    "enabled": false,
    "server": "IP или домен VPS",
    "port": 443,
    "password": "пароль аутентификации",
    "sni": "",
    "insecure": false,
    "up_mbps": 0,
    "down_mbps": 0,
    "obfs_type": "",
    "obfs_password": "",
    "tls_cert_path": "/etc/hysteria/server.crt",
    "tls_key_path": "/etc/hysteria/server.key",
    "masquerade_url": "https://www.microsoft.com",
    "clients": []
}
"""

import json
import os
import secrets
import subprocess
import logging
import threading
import urllib.parse
from io import BytesIO
from typing import Dict, Optional, List, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Thread safety
_hy2_lock = threading.Lock()

# Путь к файлу конфигурации Hysteria2
_HY2_CONFIG_PATH = os.getenv("HYSTERIA2_CONFIG_PATH",
                              os.path.join(os.getcwd(), "hysteria2_config.json"))

# Рекомендуемые порты для Hysteria2
# - 443: Стандартный HTTPS (UDP)
# - 8443: Альтернативный HTTPS
# - 4443: Часто используется для Hysteria
# - 10080: Alt port
RECOMMENDED_PORTS = [443, 8443, 4443, 10080]

# Masquerade URLs
AVAILABLE_MASQUERADE = [
    "https://www.microsoft.com",
    "https://www.apple.com",
    "https://www.google.com",
    "https://www.amazon.com",
    "https://www.cloudflare.com",
]

# Дефолтная конфигурация
DEFAULT_CONFIG = {
    "enabled": False,
    "server": "",
    "port": 443,
    "password": "",
    "sni": "",
    "insecure": False,
    "up_mbps": 0,
    "down_mbps": 0,
    "obfs_type": "",
    "obfs_password": "",
    "tls_cert_path": "/etc/hysteria/server.crt",
    "tls_key_path": "/etc/hysteria/server.key",
    "masquerade_url": "https://www.microsoft.com",
    "clients": [],
    "created_at": None,
    "updated_at": None,
}


def _normalize_clients(config: Dict) -> None:
    """
    Нормализовать список клиентов Hysteria2.
    """
    clients = config.get("clients") or []
    if not isinstance(clients, list):
        clients = []

    # Если клиентов нет, но есть password — создаём дефолтного клиента.
    if not clients and config.get("password"):
        clients = [{
            "name": "default",
            "password": config.get("password"),
            "created_at": datetime.now().isoformat()
        }]

    # Убедимся, что дефолтный клиент синхронизирован с config["password"]
    if config.get("password"):
        for client in clients:
            if client.get("name") == "default":
                client["password"] = config.get("password")
                break
        else:
            clients.append({
                "name": "default",
                "password": config.get("password"),
                "created_at": datetime.now().isoformat()
            })

    config["clients"] = clients


def _load_config() -> Dict:
    """Загрузить конфигурацию Hysteria2 из файла"""
    with _hy2_lock:
        if not os.path.exists(_HY2_CONFIG_PATH):
            return dict(DEFAULT_CONFIG)

        try:
            with open(_HY2_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                config = dict(DEFAULT_CONFIG)
                config.update(data)
                _normalize_clients(config)
                return config
        except Exception as e:
            logger.error(f"Error loading Hysteria2 config: {e}")
            return dict(DEFAULT_CONFIG)


def _save_config(config: Dict) -> bool:
    """Сохранить конфигурацию Hysteria2 в файл"""
    with _hy2_lock:
        try:
            config["updated_at"] = datetime.now().isoformat()
            if not config.get("created_at"):
                config["created_at"] = config["updated_at"]

            directory = os.path.dirname(_HY2_CONFIG_PATH) or "."
            os.makedirs(directory, exist_ok=True)

            with open(_HY2_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())

            return True
        except Exception as e:
            logger.error(f"Error saving Hysteria2 config: {e}")
            return False


# === Public API ===

def is_enabled() -> bool:
    """Проверить, включён ли Hysteria2"""
    config = _load_config()
    return config.get("enabled", False)


def enable() -> Tuple[bool, str]:
    """
    Включить Hysteria2.

    Returns:
        Tuple[bool, str]: (успех, сообщение)
    """
    config = _load_config()

    required = ["server", "password"]
    missing = [key for key in required if not config.get(key)]

    if missing:
        return False, f"Не настроены обязательные параметры: {', '.join(missing)}"

    config["enabled"] = True
    if _save_config(config):
        logger.info("Hysteria2 enabled")
        return True, "✅ Hysteria2 включён"

    return False, "❌ Ошибка при сохранении конфигурации"


def disable() -> Tuple[bool, str]:
    """
    Выключить Hysteria2.

    Returns:
        Tuple[bool, str]: (успех, сообщение)
    """
    config = _load_config()
    config["enabled"] = False

    if _save_config(config):
        logger.info("Hysteria2 disabled")
        return True, "🔴 Hysteria2 выключен"

    return False, "❌ Ошибка при сохранении конфигурации"


def get_status() -> Dict:
    """
    Получить статус Hysteria2.

    Returns:
        Dict с информацией о статусе
    """
    config = _load_config()

    required = ["server", "password"]
    configured = all(config.get(key) for key in required)

    return {
        "enabled": config.get("enabled", False),
        "configured": configured,
        "server": config.get("server", ""),
        "port": config.get("port", 443),
        "sni": config.get("sni", ""),
        "insecure": config.get("insecure", False),
        "has_password": bool(config.get("password")),
        "has_obfs": bool(config.get("obfs_type")),
        "obfs_type": config.get("obfs_type", ""),
        "up_mbps": config.get("up_mbps", 0),
        "down_mbps": config.get("down_mbps", 0),
        "masquerade_url": config.get("masquerade_url", ""),
        "tls_cert_path": config.get("tls_cert_path", ""),
        "tls_key_path": config.get("tls_key_path", ""),
        "clients_count": len(config.get("clients", [])),
        "updated_at": config.get("updated_at"),
    }


def get_config(include_secrets: bool = False) -> Dict:
    """
    Получить конфигурацию Hysteria2 (опционально с секретами).

    Args:
        include_secrets: включать ли пароли

    Returns:
        Dict с конфигурацией
    """
    config = _load_config()

    if not include_secrets:
        if config.get("password"):
            pw = config["password"]
            config["password"] = f"{pw[:4]}...{pw[-4:]}" if len(pw) > 8 else "***"
        if config.get("obfs_password"):
            opw = config["obfs_password"]
            config["obfs_password"] = f"{opw[:4]}..." if len(opw) > 4 else "***"
        # Mask client passwords
        for client in config.get("clients", []):
            if client.get("password"):
                cpw = client["password"]
                client["password"] = f"{cpw[:4]}..." if len(cpw) > 4 else "***"

    return config


# === Server IP ===

def get_server_public_ip() -> Optional[str]:
    """
    Получить публичный IP адрес сервера.
    """
    import urllib.request

    ip_services = [
        "https://api.ipify.org",
        "https://ipinfo.io/ip",
        "https://icanhazip.com",
        "https://ifconfig.me/ip",
        "https://checkip.amazonaws.com",
    ]

    for service in ip_services:
        try:
            with urllib.request.urlopen(service, timeout=5) as response:
                ip = response.read().decode('utf-8').strip()
                parts = ip.split('.')
                if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                    logger.info(f"Detected server IP: {ip} (via {service})")
                    return ip
        except Exception as e:
            logger.debug(f"Failed to get IP from {service}: {e}")
            continue

    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith(('10.', '172.', '192.168.', '127.')):
            return ip
    except Exception:
        pass

    return None


# === Setters ===

def set_server(server: Optional[str] = None) -> Tuple[bool, str]:
    """
    Установить адрес сервера Hysteria2.

    Args:
        server: IP или домен. Если None — автоопределение.
    """
    if not server or not server.strip():
        detected_ip = get_server_public_ip()
        if detected_ip:
            server = detected_ip
            auto_detected = True
        else:
            return False, "❌ Не удалось автоматически определить IP сервера\n\nИспользуйте: /hy2_set_server <IP>"
    else:
        auto_detected = False

    config = _load_config()
    config["server"] = server.strip()

    if _save_config(config):
        if auto_detected:
            return True, f"✅ Сервер установлен автоматически: {server}"
        return True, f"✅ Сервер установлен: {server}"
    return False, "❌ Ошибка при сохранении"


def set_port(port: int) -> Tuple[bool, str]:
    """
    Установить порт сервера Hysteria2.
    """
    if not isinstance(port, int) or port < 1 or port > 65535:
        return False, "❌ Порт должен быть числом от 1 до 65535"

    config = _load_config()
    config["port"] = port

    recommended = "⭐ рекомендуемый" if port in RECOMMENDED_PORTS else ""
    if _save_config(config):
        return True, f"✅ Порт установлен: {port} {recommended}\n⚠️ Не забудьте открыть UDP порт: `ufw allow {port}/udp`"
    return False, "❌ Ошибка при сохранении"


def set_password(password: str) -> Tuple[bool, str]:
    """
    Установить пароль аутентификации Hysteria2.
    """
    if not password or not password.strip():
        return False, "❌ Пароль не может быть пустым"

    password = password.strip()
    config = _load_config()
    config["password"] = password

    # Sync default client password
    _normalize_clients(config)

    if _save_config(config):
        return True, f"✅ Пароль установлен ({len(password)} символов)"
    return False, "❌ Ошибка при сохранении"


def set_sni(sni: str) -> Tuple[bool, str]:
    """
    Установить SNI для TLS.
    """
    config = _load_config()
    config["sni"] = sni.strip() if sni else ""

    if _save_config(config):
        return True, f"✅ SNI установлен: {config['sni'] or '(пусто, используется адрес сервера)'}"
    return False, "❌ Ошибка при сохранении"


def set_insecure(insecure: bool) -> Tuple[bool, str]:
    """
    Установить флаг insecure (пропуск проверки TLS).
    """
    config = _load_config()
    config["insecure"] = insecure

    if _save_config(config):
        status = "включён ⚠️" if insecure else "выключен ✅"
        return True, f"✅ Insecure mode: {status}"
    return False, "❌ Ошибка при сохранении"


def set_obfs(obfs_type: str, obfs_password: str = "") -> Tuple[bool, str]:
    """
    Установить обфускацию.

    Args:
        obfs_type: тип обфускации ("salamander" или "" для отключения)
        obfs_password: пароль обфускации
    """
    if obfs_type and obfs_type not in ("salamander", ""):
        return False, "❌ Поддерживается только тип обфускации: salamander"

    if obfs_type and not obfs_password:
        return False, "❌ Для обфускации необходим пароль"

    config = _load_config()
    config["obfs_type"] = obfs_type
    config["obfs_password"] = obfs_password

    if _save_config(config):
        if obfs_type:
            return True, f"✅ Обфускация включена: {obfs_type}"
        return True, "✅ Обфускация выключена"
    return False, "❌ Ошибка при сохранении"


def set_speed(up_mbps: int, down_mbps: int) -> Tuple[bool, str]:
    """
    Установить ограничения скорости (подсказка серверу).

    Args:
        up_mbps: скорость загрузки в Mbps (0 = авто)
        down_mbps: скорость скачивания в Mbps (0 = авто)
    """
    if up_mbps < 0 or down_mbps < 0:
        return False, "❌ Скорость не может быть отрицательной"

    config = _load_config()
    config["up_mbps"] = up_mbps
    config["down_mbps"] = down_mbps

    if _save_config(config):
        up_str = f"{up_mbps} Mbps" if up_mbps > 0 else "авто"
        down_str = f"{down_mbps} Mbps" if down_mbps > 0 else "авто"
        return True, f"✅ Скорость: ↑ {up_str} / ↓ {down_str}"
    return False, "❌ Ошибка при сохранении"


def set_masquerade(url: str) -> Tuple[bool, str]:
    """
    Установить URL маскировки (masquerade).
    """
    if not url or not url.strip():
        return False, "❌ URL не может быть пустым"

    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url

    config = _load_config()
    config["masquerade_url"] = url

    if _save_config(config):
        return True, f"✅ Masquerade URL: {url}"
    return False, "❌ Ошибка при сохранении"


# === Key/Cert Generation ===

def generate_password(length: int = 16) -> str:
    """Сгенерировать безопасный пароль."""
    return secrets.token_urlsafe(length)


def generate_self_signed_cert(
    cert_path: str = "/etc/hysteria/server.crt",
    key_path: str = "/etc/hysteria/server.key",
    domain: str = "www.microsoft.com",
    days: int = 36500,
) -> Tuple[bool, str]:
    """
    Сгенерировать self-signed TLS сертификат для Hysteria2.

    Tries:
        1. openssl CLI
        2. Python cryptography library
    """
    # Ensure directory exists
    cert_dir = os.path.dirname(cert_path) or "."
    try:
        os.makedirs(cert_dir, exist_ok=True)
    except Exception as e:
        return False, f"❌ Не удалось создать директорию {cert_dir}: {e}"

    # Method 1: openssl CLI
    try:
        cmd = [
            "openssl", "req", "-x509", "-nodes",
            "-newkey", "ec",
            "-pkeyopt", "ec_paramgen_curve:prime256v1",
            "-keyout", key_path,
            "-out", cert_path,
            "-subj", f"/CN={domain}",
            "-days", str(days),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            # Save paths to config
            config = _load_config()
            config["tls_cert_path"] = cert_path
            config["tls_key_path"] = key_path
            _save_config(config)
            logger.info(f"Generated TLS cert via openssl: {cert_path}")
            return True, f"✅ Сертификат сгенерирован (openssl)\n📄 Cert: `{cert_path}`\n🔑 Key: `{key_path}`"
    except FileNotFoundError:
        logger.debug("openssl not found, trying Python cryptography")
    except Exception as e:
        logger.debug(f"openssl failed: {e}")

    # Method 2: Python cryptography library
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.backends import default_backend
        import datetime as dt

        key = ec.generate_private_key(ec.SECP256R1(), default_backend())

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, domain),
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(dt.datetime.utcnow())
            .not_valid_after(dt.datetime.utcnow() + dt.timedelta(days=days))
            .sign(key, hashes.SHA256(), default_backend())
        )

        with open(key_path, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ))

        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        config = _load_config()
        config["tls_cert_path"] = cert_path
        config["tls_key_path"] = key_path
        _save_config(config)
        logger.info(f"Generated TLS cert via Python cryptography: {cert_path}")
        return True, f"✅ Сертификат сгенерирован (Python)\n📄 Cert: `{cert_path}`\n🔑 Key: `{key_path}`"

    except ImportError:
        return False, "❌ Не удалось сгенерировать сертификат.\nУстановите openssl или: `pip install cryptography`"
    except Exception as e:
        return False, f"❌ Ошибка генерации сертификата: {e}"


def generate_all() -> Tuple[bool, Dict, str]:
    """
    Сгенерировать всё: пароль + сертификат + автоопределить IP.

    Returns:
        Tuple[bool, Dict, str]: (успех, данные, сообщение)
    """
    results = {}
    messages = []

    # 1. Generate password
    password = generate_password()
    success, msg = set_password(password)
    results["password"] = password
    messages.append(msg)
    if not success:
        return False, results, "\n".join(messages)

    # 2. Auto-detect server IP
    success_srv, msg_srv = set_server(None)
    messages.append(msg_srv)
    if success_srv:
        config = _load_config()
        results["server"] = config.get("server", "")

    # 3. Generate TLS certificate
    success_cert, msg_cert = generate_self_signed_cert()
    results["cert_generated"] = success_cert
    messages.append(msg_cert)

    overall_success = success and success_cert
    return overall_success, results, "\n".join(messages)


# === Clients ===

def list_clients() -> List[Dict]:
    """
    Получить список клиентов Hysteria2.
    """
    config = _load_config()
    _normalize_clients(config)
    return config.get("clients", [])


def add_client(name: str, client_password: Optional[str] = None) -> Tuple[bool, str, Dict]:
    """
    Добавить клиента Hysteria2.
    """
    if not name or not name.strip():
        return False, "❌ Имя клиента не может быть пустым", {}

    name = name.strip()
    config = _load_config()
    _normalize_clients(config)

    for client in config.get("clients", []):
        if client.get("name") == name:
            return False, f"❌ Клиент с именем {name} уже существует", {}

    if not client_password:
        client_password = generate_password()

    client = {
        "name": name,
        "password": client_password,
        "created_at": datetime.now().isoformat()
    }

    config["clients"].append(client)
    if _save_config(config):
        return True, f"✅ Клиент добавлен: {name}", client
    return False, "❌ Ошибка при сохранении", {}


def remove_client(name_or_password: str) -> Tuple[bool, str]:
    """
    Удалить клиента по имени или паролю.
    """
    if not name_or_password or not name_or_password.strip():
        return False, "❌ Укажите имя клиента"

    name_or_password = name_or_password.strip()
    config = _load_config()
    _normalize_clients(config)

    if name_or_password == "default":
        return False, "❌ Нельзя удалить default клиента"

    clients = config.get("clients", [])
    new_clients = [
        c for c in clients
        if c.get("name") != name_or_password and c.get("password") != name_or_password
    ]

    if len(new_clients) == len(clients):
        return False, "❌ Клиент не найден"

    config["clients"] = new_clients
    if _save_config(config):
        return True, "✅ Клиент удалён"
    return False, "❌ Ошибка при сохранении"


# === Export Configurations ===

def generate_hy2_uri(client_password: Optional[str] = None, comment: str = "Hysteria2") -> str:
    """
    Генерация URI hy2:// для клиента.

    Format: hy2://password@server:port/?insecure=1&sni=xxx&obfs=salamander&obfs-password=xxx#comment
    """
    config = _load_config()

    server = config.get("server", "")
    port = config.get("port", 443)
    password = client_password or config.get("password", "")

    if not server or not password:
        return ""

    params = {}

    sni = config.get("sni", "")
    if sni:
        params["sni"] = sni

    if config.get("insecure"):
        params["insecure"] = "1"

    obfs_type = config.get("obfs_type", "")
    if obfs_type:
        params["obfs"] = obfs_type
        obfs_password = config.get("obfs_password", "")
        if obfs_password:
            params["obfs-password"] = obfs_password

    query_string = "&".join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()])
    comment_enc = urllib.parse.quote(comment)

    uri = f"hy2://{urllib.parse.quote(password)}@{server}:{port}"
    if query_string:
        uri += f"/?{query_string}"
    uri += f"#{comment_enc}"
    return uri


def get_client(name_or_password: str) -> Optional[Dict]:
    """
    Найти клиента Hysteria2 по имени или паролю.
    """
    if not name_or_password or not name_or_password.strip():
        return None

    needle = name_or_password.strip()
    for client in list_clients():
        if client.get("name") == needle or client.get("password") == needle:
            return client
    return None


def generate_client_uri(name_or_password: str) -> Tuple[bool, str, str]:
    """
    Сгенерировать hy2:// URI для конкретного клиента.
    """
    client = get_client(name_or_password)
    if not client:
        return False, "❌ Клиент не найден", ""

    client_name = client.get("name") or "client"
    client_password = client.get("password") or ""
    if not client_password:
        return False, f"❌ У клиента {client_name} отсутствует пароль", ""

    uri = generate_hy2_uri(client_password, f"Hysteria2-{client_name}")
    if not uri:
        return False, "❌ Не удалось сгенерировать Hysteria2 URI. Проверьте настройки сервера и пароль", ""

    return True, f"✅ URI для клиента {client_name} готов", uri


def generate_qr_png_bytes(content: str) -> Tuple[bool, Optional[BytesIO], str]:
    """
    Сгенерировать QR-код PNG в памяти.
    """
    if not content or not content.strip():
        return False, None, "❌ Нечего кодировать в QR"

    try:
        import qrcode
    except ImportError:
        return False, None, "❌ Библиотека qrcode не установлена. Обновите зависимости проекта"

    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(content.strip())
        qr.make(fit=True)

        image = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return True, buffer, "✅ QR-код сгенерирован"
    except Exception as e:
        logger.error(f"Failed to generate Hysteria2 QR image: {e}")
        return False, None, f"❌ Ошибка генерации QR: {e}"


def build_client_qr_payload(name_or_password: str) -> Tuple[bool, str, Dict]:
    """
    Подготовить данные клиента Hysteria2 для отправки QR-кода через Telegram.
    """
    client = get_client(name_or_password)
    if not client:
        return False, "❌ Клиент не найден", {}

    success, message, uri = generate_client_uri(name_or_password)
    if not success:
        return False, message, {}

    success, qr_buffer, qr_message = generate_qr_png_bytes(uri)
    if not success or qr_buffer is None:
        return False, qr_message, {}

    payload = {
        "name": client.get("name") or "client",
        "password": client.get("password") or "",
        "uri": uri,
        "qr_buffer": qr_buffer,
    }
    return True, "✅ QR-пакет для клиента Hysteria2 подготовлен", payload


def export_server_config() -> Dict:
    """
    Сгенерировать серверную конфигурацию Hysteria2 (для /etc/hysteria/config.yaml).

    Returns:
        Dict (YAML-like structure, сериализуется в YAML)
    """
    config = _load_config()

    server_config = {
        "listen": f":{config.get('port', 443)}",
        "tls": {
            "cert": config.get("tls_cert_path", "/etc/hysteria/server.crt"),
            "key": config.get("tls_key_path", "/etc/hysteria/server.key"),
        },
        "auth": {
            "type": "password",
            "password": config.get("password", ""),
        },
    }

    # Bandwidth (optional)
    up_mbps = config.get("up_mbps", 0)
    down_mbps = config.get("down_mbps", 0)
    if up_mbps > 0 or down_mbps > 0:
        bandwidth = {}
        if up_mbps > 0:
            bandwidth["up"] = f"{up_mbps} mbps"
        if down_mbps > 0:
            bandwidth["down"] = f"{down_mbps} mbps"
        server_config["bandwidth"] = bandwidth

    # Obfuscation (optional)
    obfs_type = config.get("obfs_type", "")
    obfs_password = config.get("obfs_password", "")
    if obfs_type and obfs_password:
        server_config["obfs"] = {
            "type": obfs_type,
            obfs_type: {
                "password": obfs_password,
            },
        }

    # Masquerade
    masquerade_url = config.get("masquerade_url", "")
    if masquerade_url:
        server_config["masquerade"] = {
            "type": "proxy",
            "proxy": {
                "url": masquerade_url,
                "rewriteHost": True,
            },
        }

    return server_config


def export_server_config_yaml() -> str:
    """
    Сгенерировать серверную конфигурацию в формате YAML.
    """
    config = export_server_config()

    # Simple YAML serialization (no pyyaml dependency)
    lines = []

    def _yaml_value(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        return f'"{v}"' if v else '""'

    def _dump_dict(d, indent=0):
        prefix = "  " * indent
        for key, val in d.items():
            if isinstance(val, dict):
                lines.append(f"{prefix}{key}:")
                _dump_dict(val, indent + 1)
            else:
                lines.append(f"{prefix}{key}: {_yaml_value(val)}")

    _dump_dict(config)
    return "\n".join(lines)


def export_client_config() -> Dict:
    """
    Сгенерировать клиентскую конфигурацию Hysteria2 (native format).
    """
    config = _load_config()

    client_config = {
        "server": f"{config.get('server', '')}:{config.get('port', 443)}",
        "auth": config.get("password", ""),
        "tls": {},
        "socks5": {
            "listen": "127.0.0.1:1080",
        },
        "http": {
            "listen": "127.0.0.1:8080",
        },
    }

    sni = config.get("sni", "")
    if sni:
        client_config["tls"]["sni"] = sni
    if config.get("insecure"):
        client_config["tls"]["insecure"] = True

    obfs_type = config.get("obfs_type", "")
    obfs_password = config.get("obfs_password", "")
    if obfs_type and obfs_password:
        client_config["obfs"] = {
            "type": obfs_type,
            obfs_type: {
                "password": obfs_password,
            },
        }

    up_mbps = config.get("up_mbps", 0)
    down_mbps = config.get("down_mbps", 0)
    if up_mbps > 0 or down_mbps > 0:
        bandwidth = {}
        if up_mbps > 0:
            bandwidth["up"] = f"{up_mbps} mbps"
        if down_mbps > 0:
            bandwidth["down"] = f"{down_mbps} mbps"
        client_config["bandwidth"] = bandwidth

    return client_config


def export_singbox_config() -> Dict:
    """
    Сгенерировать конфигурацию sing-box (client) с Hysteria2 outbound.
    """
    config = _load_config()

    outbound = {
        "type": "hysteria2",
        "tag": "proxy",
        "server": config.get("server", ""),
        "server_port": config.get("port", 443),
        "password": config.get("password", ""),
        "tls": {
            "enabled": True,
            "server_name": config.get("sni", "") or config.get("server", ""),
            "insecure": config.get("insecure", False),
        },
    }

    up_mbps = config.get("up_mbps", 0)
    down_mbps = config.get("down_mbps", 0)
    if up_mbps > 0:
        outbound["up_mbps"] = up_mbps
    if down_mbps > 0:
        outbound["down_mbps"] = down_mbps

    obfs_type = config.get("obfs_type", "")
    obfs_password = config.get("obfs_password", "")
    if obfs_type and obfs_password:
        outbound["obfs"] = {
            "type": obfs_type,
            "password": obfs_password,
        }

    return {
        "log": {"level": "warn"},
        "inbounds": [{
            "type": "socks",
            "listen": "127.0.0.1",
            "listen_port": 1080,
        }],
        "outbounds": [outbound],
    }


def export_clash_meta_config() -> str:
    """
    Сгенерировать конфигурацию Clash Meta (YAML) с Hysteria2 proxy.
    """
    config = _load_config()
    server = config.get("server", "")
    port = config.get("port", 443)
    password = config.get("password", "")
    sni = config.get("sni", "")
    insecure = config.get("insecure", False)
    obfs_type = config.get("obfs_type", "")
    obfs_password = config.get("obfs_password", "")

    lines = [
        "port: 7890",
        "socks-port: 7891",
        "mixed-port: 7892",
        "mode: rule",
        "log-level: info",
        "",
        "proxies:",
        "  - name: hysteria2",
        "    type: hysteria2",
        f"    server: {server}",
        f"    port: {port}",
        f"    password: {password}",
    ]

    if sni:
        lines.append(f"    sni: {sni}")
    if insecure:
        lines.append("    skip-cert-verify: true")
    if obfs_type:
        lines.append(f"    obfs: {obfs_type}")
        if obfs_password:
            lines.append(f"    obfs-password: {obfs_password}")

    lines.extend([
        "",
        "proxy-groups:",
        "  - name: PROXY",
        "    type: select",
        "    proxies:",
        "      - hysteria2",
        "      - DIRECT",
        "",
        "rules:",
        "  - MATCH,PROXY",
    ])

    return "\n".join(lines)


def export_subscription_list() -> List[str]:
    """
    Сформировать список URI для subscription.
    """
    links = []
    clients = list_clients()
    for client in clients:
        name = client.get("name") or "client"
        client_password = client.get("password") or ""
        link = generate_hy2_uri(client_password, f"Hysteria2-{name}")
        if link:
            links.append(link)
    return links


def export_subscription_base64() -> str:
    """
    Сформировать subscription в base64.
    """
    import base64

    links = export_subscription_list()
    raw = "\n".join([x for x in links if x]).strip()
    if not raw:
        return ""
    return base64.b64encode(raw.encode("utf-8")).decode("utf-8")


# === ApiXgRPC Profile Export (legacy apisb-profile) ===

def export_apisb_profile(client_name: Optional[str] = None) -> Dict:
    """
    Экспортировать профиль в legacy-формате `apisb-profile v1`, совместимом с ApiXgRPC.
    Использует dataclass-модели из apisb_export.py.

    Args:
        client_name: Имя клиента (если None — используется основной пароль).

    Returns:
        Dict — готовый JSON для импорта в ApiXgRPC.
    """
    from apisb_export import build_hysteria2_export

    config = _load_config()
    profile_name = client_name or "default"

    # Если указан конкретный клиент — подставить его пароль
    if client_name:
        for c in config.get("clients", []):
            if c.get("name") == client_name:
                config = dict(config)  # shallow copy
                config["password"] = c.get("password", config.get("password", ""))
                break

    return build_hysteria2_export(config, profile_name)


# === Service Management (runs on VPS) ===

def apply_config() -> Tuple[bool, str]:
    """
    Применить текущую конфигурацию к серверу Hysteria2.
    Записывает /etc/hysteria/config.yaml и перезапускает сервис.
    """
    config_yaml = export_server_config_yaml()
    config_path = "/etc/hysteria/config.yaml"

    try:
        os.makedirs("/etc/hysteria", exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(config_yaml)
            f.flush()
            os.fsync(f.fileno())

        logger.info(f"Hysteria2 server config written to {config_path}")

        # Restart service
        result = subprocess.run(
            ["systemctl", "restart", "hysteria-server"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return True, f"✅ Конфиг применён и сервис перезапущен\n📄 `{config_path}`"
        else:
            error = result.stderr.strip() or result.stdout.strip()
            return False, f"⚠️ Конфиг записан, но сервис не перезапустился:\n`{error}`"

    except PermissionError:
        return False, "❌ Нет прав на запись в /etc/hysteria/. Запустите с sudo."
    except Exception as e:
        return False, f"❌ Ошибка: {e}"


def service_control(action: str) -> Tuple[bool, str]:
    """
    Управление systemd сервисом Hysteria2.

    Args:
        action: start, stop, restart, status
    """
    if action not in ("start", "stop", "restart", "status"):
        return False, f"❌ Неизвестное действие: {action}"

    try:
        result = subprocess.run(
            ["systemctl", action, "hysteria-server"],
            capture_output=True, text=True, timeout=30,
        )

        if action == "status":
            output = result.stdout.strip() or result.stderr.strip()
            is_active = "active (running)" in output
            status_emoji = "🟢" if is_active else "🔴"
            return True, f"{status_emoji} Hysteria2 сервис:\n```\n{output[:500]}\n```"

        if result.returncode == 0:
            action_labels = {"start": "запущен", "stop": "остановлен", "restart": "перезапущен"}
            return True, f"✅ Hysteria2 {action_labels.get(action, action)}"
        else:
            error = result.stderr.strip() or result.stdout.strip()
            return False, f"❌ Ошибка: {error[:300]}"

    except FileNotFoundError:
        return False, "❌ systemctl не найден. Hysteria2 установлен?"
    except Exception as e:
        return False, f"❌ Ошибка: {e}"


def get_logs(lines: int = 30) -> Tuple[bool, str]:
    """
    Получить логи Hysteria2 сервиса.
    """
    try:
        result = subprocess.run(
            ["journalctl", "-u", "hysteria-server", "-n", str(lines), "--no-pager"],
            capture_output=True, text=True, timeout=15,
        )
        output = result.stdout.strip() or result.stderr.strip() or "(пусто)"
        # Truncate for Telegram message limit
        if len(output) > 3500:
            output = output[-3500:]
        return True, output

    except FileNotFoundError:
        return False, "❌ journalctl не найден"
    except Exception as e:
        return False, f"❌ Ошибка: {e}"


def install_hysteria2() -> Tuple[bool, str]:
    """
    Установить Hysteria2 на сервер (скачивает официальный скрипт).
    """
    try:
        # Check if already installed
        check = subprocess.run(["which", "hysteria"], capture_output=True, text=True)
        if check.returncode == 0:
            # Get version
            ver = subprocess.run(["hysteria", "version"], capture_output=True, text=True, timeout=10)
            version = ver.stdout.strip()[:100] if ver.returncode == 0 else "unknown"
            return True, f"✅ Hysteria2 уже установлен\n📦 Версия: `{version}`"

        # Download and run official installer
        result = subprocess.run(
            ["bash", "-c", "curl -fsSL https://get.hy2.sh/ | bash"],
            capture_output=True, text=True, timeout=120,
        )

        if result.returncode == 0:
            logger.info("Hysteria2 installed successfully")
            return True, "✅ Hysteria2 установлен!\n\nДальше:\n1. `/hy2_gen_all` — сгенерировать пароль и сертификат\n2. `/hy2_apply` — применить конфиг\n3. `/hy2_start` — запустить"
        else:
            error = result.stderr.strip()[:300]
            return False, f"❌ Ошибка установки:\n`{error}`"

    except Exception as e:
        return False, f"❌ Ошибка: {e}"


def test_connection() -> Tuple[bool, str]:
    """
    Тест доступности Hysteria2 сервера (проверяет UDP порт).
    """
    config = _load_config()
    server = config.get("server", "")
    port = config.get("port", 443)

    if not server:
        return False, "❌ Сервер не настроен"

    import socket

    try:
        # UDP port check — send empty packet and see if we get ICMP unreachable
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5)
        sock.sendto(b'\x00', (server, port))
        try:
            sock.recvfrom(1024)
        except socket.timeout:
            # Timeout is OK for UDP — means port is not explicitly rejected
            pass
        sock.close()

        return True, f"✅ UDP порт {server}:{port} доступен (не отклонён)"
    except Exception as e:
        return False, f"❌ Ошибка: {e}"

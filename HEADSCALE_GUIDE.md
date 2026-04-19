# 🕸️ Headscale — Руководство

> Self-hosted Tailscale координатор для mesh-сети.
>
> **Дата обновления:** 01.04.2026

---

## Что такое Headscale

**Headscale** — open-source реализация Tailscale control plane (координатора). Позволяет создать приватную mesh-сеть между устройствами без облачного сервиса Tailscale.

### Зачем нужен

- Доступ к **Home Assistant** из любой точки без проброса портов
- Mesh-сеть между устройствами (ноутбук, телефон, сервер, дом)
- P2P-соединения через WireGuard (Tailscale протокол)
- Работает совместно с VPN (ApiXgRPC) через **Mesh Bypass**

### Архитектура

```
┌─────────────────┐         ┌──────────────────────────────┐
│  Устройство 1   │         │  VPS                          │
│  (Tailscale)    │◄──WG──► │  Headscale координатор (:8080)│
└─────────────────┘         │  ├── Users                    │
                            │  ├── Pre-Auth Keys            │
┌─────────────────┐         │  └── Node registry            │
│  Устройство 2   │◄──WG──► │                               │
│  (Tailscale)    │         │  Доступен через Nginx SNI     │
└─────────────────┘         │  (headscale.domain.com → :8080)│
        │                   └──────────────────────────────┘
        │ P2P (direct)
        ▼
┌─────────────────┐
│  Дом (серый IP) │
│  ├── HA :8123   │
│  ├── Tailscale  │
│  └── IoT        │
└─────────────────┘
```

Устройства подключаются к координатору для обмена ключами, затем устанавливают прямые WireGuard-туннели между собой.

---

## Установка на VPS

### 1. Docker Compose

```bash
cd /opt/TelegramSimple

# Создать директории
mkdir -p headscale/config headscale/data

# Скачать пример конфига
curl -sL https://raw.githubusercontent.com/juanfont/headscale/main/config-example.yaml \
  -o headscale/config/config.yaml
```

### 2. Настроить конфиг

Отредактировать `headscale/config/config.yaml`:

```yaml
server_url: https://headscale.your-domain.com
listen_addr: 0.0.0.0:8080
private_key_path: /var/lib/headscale/private.key
noise:
  private_key_path: /var/lib/headscale/noise_private.key
ip_prefixes:
  - 100.64.0.0/10
  - fd7a:115c:a1e0::/48
```

### 3. Запустить

```bash
docker compose -f compose.yaml -f compose.headscale.yaml up -d

# Создать первого пользователя
docker exec headscale headscale users create main_user
```

### 4. Проверить

```bash
docker ps | grep headscale
docker exec headscale headscale nodes list
```

---

## Управление через Telegram бота

### Команды

| Команда | Описание |
|---------|----------|
| `/headscale_status` | Статус контейнера, URL, количество нод |
| `/headscale_enable` | Включить Headscale в конфиге бота |
| `/headscale_disable` | Выключить |
| `/headscale_set_url <url>` | Установить URL координатора |
| `/headscale_gen` | Сгенерировать Pre-Auth ключ |
| `/headscale_list_nodes` | Список подключённых устройств |
| `/headscale_create_user <name>` | Создать пользователя |

### Управление через admin-команды из ApiXgRPC CLI

```bash
admin run /headscale_status
admin run /headscale_gen
admin run /headscale_list_nodes
admin run /headscale_create_user guest
```

---

## Подключение устройств

### 1. Сгенерировать Pre-Auth ключ

```bash
# Через бота
/headscale_gen

# Через SSH
docker exec headscale headscale preauthkeys create --user main_user --reusable --expiration 24h
```

### 2. Установить Tailscale на устройстве

**macOS:**
```bash
brew install tailscale
```

**Linux:**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
```

**Windows:** скачать с https://tailscale.com/download

### 3. Подключиться к Headscale

```bash
tailscale up --login-server https://headscale.your-domain.com --authkey <PRE_AUTH_KEY>
```

### 4. Проверить

```bash
tailscale status
# Должны видеть другие устройства в mesh-сети
```

### Подключение iPhone / Android

iOS/Android не умеет `tailscale up --authkey`. Вместо preauth-ключа используется **24-символьный registration ID** из приложения + команда `nodes register` на VPS.

1. Установить Tailscale из App Store / Play Store.
2. Если уже залогинен — **Log out** (иконка аккаунта).
3. На экране логина тапнуть **"Log in with other"**. В свежих версиях кнопка скрыта — тапнуть шестерёнку / три точки в углу → **Use alternate coordination server**.
4. Ввести URL координатора (ваш `server_url`).
5. Приложение покажет инструкцию с ключом. Скопировать именно **короткий 24-символьный ID** (буквы+цифры без префикса), **не** длинный `nodekey:...` (64 hex).
6. Сразу (ключ живёт ~5 минут) выполнить на VPS:

   ```bash
   docker exec headscale headscale nodes register \
     --user main_user \
     --key <24-char-id>
   ```

7. iOS не отдаёт hostname — узел зарегистрируется как `localhost`. Переименовать:

   ```bash
   docker exec headscale headscale nodes list | cat
   docker exec headscale headscale nodes rename --identifier <id> iphone-<name>
   ```

---

## Mesh Bypass в ApiXgRPC

Когда на устройстве одновременно работают **ApiXgRPC VPN** (TUN режим) и **Tailscale**, включите **Mesh Bypass** чтобы трафик Tailscale не шёл через VPN:

- GUI: Settings → Mesh Bypass (checkbox)
- CLI: `config set mesh_bypass_enabled true`

Mesh Bypass добавляет прямые маршруты для подсетей Tailscale/Headscale:

| Подсеть | Назначение |
|---------|------------|
| `100.64.0.0/10` | Tailscale/Headscale IPv4 |
| `fd7a:115c:a1e0::/48` | Tailscale/Headscale IPv6 |

Трафик к этим подсетям идёт мимо VPN-туннеля напрямую.

---

## Nginx SNI Routing

Headscale слушает на `127.0.0.1:8080`, но внешние клиенты обращаются через HTTPS (порт 443). Xray (VLESS-Reality) уже занимает 443 → используется SNI routing:

```
Клиент → 443/TCP → Xray
                      ↓ non-VLESS (fallback)
                    Nginx :8443 (ssl_preread)
                      ├── headscale.domain.com → :8080
                      └── ha.domain.com → :8123
```

Настройка через бота:
```bash
/nginx_set_domain headscale.your-domain.com ha.your-domain.com
/nginx_enable
/nginx_config    # Скопировать результат в /etc/nginx/
```

> Подробнее: [NGINX_SNI_ROUTING.md](NGINX_SNI_ROUTING.md)

---

## Конфигурация бота

Headscale конфиг хранится в `headscale_config.json`:

```json
{
  "enabled": true,
  "container_name": "headscale",
  "server_url": "https://headscale.your-domain.com",
  "default_user": "main_user",
  "key_expiration": "24h"
}
```

| Поле | Описание |
|------|----------|
| `enabled` | Включён ли Headscale в боте |
| `container_name` | Имя Docker контейнера |
| `server_url` | Публичный URL координатора |
| `default_user` | Пользователь по умолчанию для Pre-Auth ключей |
| `key_expiration` | Срок действия Pre-Auth ключей |

---

## Docker файлы

### compose.headscale.yaml

```yaml
services:
  headscale:
    container_name: headscale
    image: headscale/headscale:latest
    command: serve
    restart: unless-stopped
    ports:
      - "127.0.0.1:8080:8080"
    volumes:
      - ./headscale/config:/etc/headscale
      - ./headscale/data:/var/lib/headscale
```

Запуск с основным compose:
```bash
docker compose -f compose.yaml -f compose.headscale.yaml up -d
```

---

## Troubleshooting

| Проблема | Решение |
|----------|---------|
| Контейнер не запускается | `docker logs headscale` — проверить ошибки конфига |
| `connection refused` при `tailscale up` | Проверить, что Nginx SNI routing настроен и домен резолвится |
| Устройства не видят друг друга | Проверить `tailscale status` на обоих, убедиться что один user |
| VPN ломает Tailscale | Включить Mesh Bypass в ApiXgRPC |
| Pre-Auth ключ expired | Сгенерировать новый: `/headscale_gen` |
| iOS: `registration ID must be 24 characters long` | Скопирован `nodekey:...` вместо короткого ID. Искать 24-символьный код на экране приложения |
| iOS: `node not found in registration cache` | Прошло >5 мин — ключ истёк. Открыть экран логина заново, получить свежий ID, сразу запустить `register` |
| iOS: нет кнопки "Log in with other" | В свежих версиях спрятана под шестерёнкой/⋯ на экране логина. Альтернатива — открыть `tailscale://login?server=<URL>` в Safari |
| iOS: узел зарегистрирован как `localhost` | iOS не отдаёт hostname. Переименовать через `headscale nodes rename --identifier <id> <name>` |

---

## Связанные документы

- [NGINX_SNI_ROUTING.md](NGINX_SNI_ROUTING.md) — Nginx SNI маршрутизация (как Headscale доступен снаружи)
- [SCRIPTS_CHEATSHEET.md](SCRIPTS_CHEATSHEET.md) — Шпаргалка по всем командам
- [docs/COMMANDS_REFERENCE.md](docs/COMMANDS_REFERENCE.md) — Полный справочник команд

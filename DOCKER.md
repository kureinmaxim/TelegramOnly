# Docker — Руководство

> Все контейнеры, Compose-файлы, Dockerfile и команды управления.
>
> **Дата обновления:** 02.04.2026

---

## Обзор контейнеров

| Контейнер | Образ | Порт | Назначение |
|-----------|-------|------|------------|
| `telegram-helper-lite` | `telegram-helper-lite:latest` (локальный) | 8000 | Бот + REST API (основной) |
| `dockhand` | `dockhand:latest` (локальный) | 8501 (localhost) | Диагностическая панель (Streamlit) |
| `headscale` | `headscale/headscale:latest` (Docker Hub) | 8080 (localhost) | Mesh VPN координатор (опциональный) |

### Схема

```
Docker Host (VPS)
│
├── telegram-helper-lite :8000 ← Бот + FastAPI
│   ├── /var/run/docker.sock    (управление другими контейнерами)
│   ├── volumes: .env, app_keys.json, vless_config.json,
│   │           hysteria2_config.json, tuic_config.json,
│   │           anytls_config.json, xhttp_config.json,
│   │           mtproto_config.json, headscale_config.json,
│   │           users.json, bot.log
│   └── DNS: 8.8.8.8, 1.1.1.1
│
├── dockhand :8501 (localhost only)
│   ├── /var/run/docker.sock    (мониторинг контейнеров)
│   ├── depends_on: telegram-helper
│   └── Streamlit UI
│
└── headscale :8080 (localhost only) — опциональный
    ├── ./headscale/config → /etc/headscale
    └── ./headscale/data → /var/lib/headscale
```

---

## Compose-файлы

### compose.yaml — основной

Содержит `telegram-helper-lite` и `dockhand`. Запуск:

```bash
docker compose up -d
```

### compose.headscale.yaml — overlay для Headscale

Добавляет контейнер `headscale`. Запуск вместе с основным:

```bash
docker compose -f compose.yaml -f compose.headscale.yaml up -d
```

---

## Контейнер: telegram-helper-lite

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

CMD ["python", "main.py"]
```

**Ключевые моменты:**
- Базовый образ: `python:3.12-slim`
- Запускается от непривилегированного пользователя `appuser`
- Кэширование: `requirements.txt` копируется первым для оптимизации слоёв
- `PIP_NO_CACHE_DIR=1` — уменьшает размер образа

### Volumes (bind mounts)

| Хост | Контейнер | Описание |
|------|-----------|----------|
| `.env` | `/app/.env` | Переменные окружения (токены, ключи) |
| `app_keys.json` | `/app/app_keys.json` | API и encryption ключи приложений |
| `vless_config.json` | `/app/vless_config.json` | Конфигурация VLESS-Reality |
| `hysteria2_config.json` | `/app/hysteria2_config.json` | Конфигурация Hysteria2 |
| `tuic_config.json` | `/app/tuic_config.json` | Конфигурация TUIC |
| `anytls_config.json` | `/app/anytls_config.json` | Конфигурация AnyTLS |
| `xhttp_config.json` | `/app/xhttp_config.json` | Конфигурация XHTTP |
| `mtproto_config.json` | `/app/mtproto_config.json` | Конфигурация MTProto |
| `headscale_config.json` | `/app/headscale_config.json` | Конфигурация Headscale |
| `users.json` | `/app/users.json` | Зарегистрированные пользователи |
| `bot.log` | `/app/bot.log` | Лог-файл бота |
| `/var/run/docker.sock` | `/var/run/docker.sock` | Управление Docker (Headscale) |

> **Важно:** Файлы данных (`app_keys.json`, `users.json`, `*_config.json`) **НЕ в git** — их нужно создавать вручную на сервере.
>
> **Ловушка с директориями:** если запустить `docker compose up` до того, как файл-volume создан на хосте, Docker создаст **директорию** с этим именем вместо файла. После этого `echo '{}' > file.json` выдаст `Is a directory`. Решение: `docker compose down`, затем `rm -rf имя_директории`, затем `echo '{}' > имя.json`, затем снова `docker compose up`.
>
> Безопасная инициализация всех конфигов перед первым запуском:
>
> ```bash
> cd /opt/TelegramSimple
> for f in vless_config.json hysteria2_config.json tuic_config.json \
>          anytls_config.json xhttp_config.json mtproto_config.json \
>          headscale_config.json naiveproxy_config.json app_keys.json \
>          users.json bot.log; do
>   [ -f "$f" ] || echo '{}' > "$f"
> done
> ```

### Порт

- `8000` → REST API (FastAPI/Uvicorn)

### Зависимости (requirements.txt)

| Пакет | Версия | Назначение |
|-------|--------|------------|
| `python-telegram-bot` | >=22.1 | Telegram Bot API |
| `fastapi` | >=0.109.0 | REST API сервер |
| `uvicorn` | >=0.27.0 | ASGI сервер |
| `anthropic` | >=0.25.0 | Claude AI |
| `openai` | >=1.16.0 | OpenAI GPT |
| `cryptography` | >=42.0.0 | AES-256-GCM шифрование |
| `requests` / `httpx` | — | HTTP клиенты |
| `deep-translator` | >=1.11.0 | Перевод текста |
| `ddgs` | >=1.0.0 | DuckDuckGo поиск (/factcheck) |
| `aiofiles` | >=23.0.0 | Асинхронный ввод/вывод |

---

## Контейнер: dockhand

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir streamlit docker requests pandas watchdog
COPY app.py .
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1
ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

**Ключевые моменты:**
- Streamlit-приложение для мониторинга
- Встроенный healthcheck
- Доступен **только с localhost** (`127.0.0.1:8501`) — используйте SSH-туннель

### Что мониторит

- Статус контейнера `telegram-helper-lite`
- Health check API (`http://telegram-helper:8000`)
- Логи контейнера в реальном времени
- Метрики: CPU, memory

### Доступ через SSH-туннель

```bash
# На локальном Mac
ssh -L 8501:localhost:8501 -p YOUR_SSH_PORT root@YOUR_SERVER_IP

# Открыть: http://localhost:8501
```

---

## Контейнер: headscale (опциональный)

### Образ

`headscale/headscale:latest` (Docker Hub)

### Volumes

| Хост | Контейнер | Описание |
|------|-----------|----------|
| `./headscale/config` | `/etc/headscale` | Конфигурация (`config.yaml`) |
| `./headscale/data` | `/var/lib/headscale` | БД и состояние |

### Первый запуск

```bash
# 1. Создать директории
mkdir -p headscale/config headscale/data

# 2. Скачать конфиг
curl -sL https://raw.githubusercontent.com/juanfont/headscale/main/config-example.yaml \
  -o headscale/config/config.yaml

# 3. Настроить server_url и listen_addr в config.yaml

# 4. Запустить
docker compose -f compose.yaml -f compose.headscale.yaml up -d

# 5. Создать пользователя
docker exec headscale headscale users create main_user
```

### Управление через бота

```
/headscale_enable            — включить
/headscale_disable           — выключить
/headscale_create_user <name>  — создать пользователя
/headscale_create_key <user>   — создать preauth-key
/headscale_list              — список нод
/headscale_status            — статус контейнера
```

---

## .dockerignore

```
__pycache__/
*.pyc *.pyo *.pyd
venv/
.env .env.*
.git/ .gitignore
.DS_Store
*.log bot.log
.vscode/ .idea/ *.swp
docs/
```

Исключает Python-кэши, IDE-файлы, логи и документацию из Docker-контекста.

---

## Основные команды

### Ежедневные

```bash
cd /opt/TelegramSimple

# Статус контейнеров
docker compose ps

# Логи основного бота
docker logs telegram-helper-lite --tail 50

# Логи в реальном времени
docker compose logs -f

# Перезапуск
docker compose restart

# Перезапуск с пересборкой
docker compose up -d --build
```

### С Headscale

```bash
# Запуск всего стека
docker compose -f compose.yaml -f compose.headscale.yaml up -d

# Остановка всего стека
docker compose -f compose.yaml -f compose.headscale.yaml down

# Только Headscale
docker compose -f compose.yaml -f compose.headscale.yaml up -d headscale
docker compose -f compose.yaml -f compose.headscale.yaml stop headscale
```

### Обновление кода

```bash
# С локальной машины
rsync -avz -e "ssh -p YOUR_SSH_PORT" \
  --exclude 'venv' --exclude '__pycache__' --exclude '.env' \
  --exclude 'app_keys.json' --exclude 'users.json' --exclude '*.log' \
  /path/to/TelegramSimple/ root@YOUR_SERVER_IP:/opt/TelegramSimple/

# На сервере
ssh -p YOUR_SSH_PORT root@YOUR_SERVER_IP
cd /opt/TelegramSimple
docker compose up -d --build
```

### Сборка без кэша

```bash
docker compose build --no-cache
docker compose up -d
```

---

## Очистка Docker

### Быстрая (освободить место)

```bash
docker compose down
docker builder prune -af
docker image prune -af
docker compose up -d --build
```

### Агрессивная (максимум места)

```bash
docker compose down
docker system prune -af --volumes
apt-get clean && apt-get autoclean
docker compose up -d --build
```

### По отдельности

```bash
docker builder prune -af      # Build cache (обычно самый большой)
docker image prune -af         # Неиспользуемые образы
docker container prune -f      # Остановленные контейнеры
docker volume prune -f         # Неиспользуемые volumes (осторожно!)
docker network prune -f        # Неиспользуемые сети
```

### Проверка использования

```bash
docker system df               # Общая статистика
df -h /                        # Использование диска
du -sh /var/lib/docker/*       # Размеры Docker
```

---

## Инициализация данных (после очистки)

При переустановке или первом деплое файлы данных нужно создать вручную:

```bash
cd /opt/TelegramSimple

# Файлы данных (НЕ в git)
echo '{"app_keys": {}, "default": {}}' > app_keys.json
echo '{}' > users.json
echo '{}' > vless_config.json
echo '{}' > hysteria2_config.json
echo '{}' > mtproto_config.json
echo '{}' > headscale_config.json
touch bot.log

# Права
chmod 666 app_keys.json users.json vless_config.json \
          hysteria2_config.json mtproto_config.json \
          headscale_config.json bot.log
chmod 600 .env

# Настроить .env
cp example.env .env
nano .env  # указать BOT_TOKEN, ADMIN_ID, etc.

# Собрать и запустить
docker compose up -d --build
```

---

## Troubleshooting

| Проблема | Решение |
|----------|---------|
| `pull access denied for telegram-helper-lite` | Нормально — это локальный образ, Docker соберёт из Dockerfile |
| Контейнер не стартует | `docker logs telegram-helper-lite` — проверить BOT_TOKEN в .env |
| `Permission denied` на volumes | `chmod 666` на файлы данных |
| `409 Conflict` (несколько ботов) | `docker compose down && docker rm telegram-helper-lite` |
| Нет места для сборки | `docker builder prune -af && docker image prune -af` |
| Dockhand недоступен | SSH-туннель: `ssh -L 8501:localhost:8501 ...` |
| Headscale не стартует | Проверить `headscale/config/config.yaml`, создать директории |
| Docker socket permission | Убедиться что `/var/run/docker.sock` доступен |

---

## Скрипт быстрого запуска

`scripts/docker_run.sh` — проверяет `.env`, собирает образ, запускает:

```bash
cd /opt/TelegramSimple
./scripts/docker_run.sh
```

---

## Связанные документы

- [VPS_GUIDE.md](VPS_GUIDE.md) — Установка и управление VPS
- [CLEANUP_SERVER.md](CLEANUP_SERVER.md) — Очистка сервера
- [HEADSCALE_GUIDE.md](HEADSCALE_GUIDE.md) — Руководство по Headscale
- [DOCKHAND_GUIDE.md](DOCKHAND_GUIDE.md) — Диагностическая панель
- [LOGS_GUIDE.md](LOGS_GUIDE.md) — Руководство по логам

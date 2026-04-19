# SETUP.md — Полное руководство по развёртыванию и обновлению TelegramOnly

> Объединённый гайд: первый деплой на чистый VPS + редеплой + Docker + настройка протоколов.

---

## Оглавление

1. [Первый деплой на чистый VPS](#1-первый-деплой-на-чистый-vps)
2. [Редеплой (обновление кода)](#2-редеплой-обновление-кода)
3. [Docker](#3-docker)
4. [Настройка протоколов через бота](#4-настройка-протоколов-через-бота)
5. [Частые ошибки и решения](#5-частые-ошибки-и-решения)
6. [Смена токена бота](#6-смена-токена-бота)

---

## 1. Первый деплой на чистый VPS

### Серверный путь

**Legacy:** `/opt/TelegramSimple` (уже работающие серверы, не переименовывать).
**Новые серверы:** `/opt/TelegramOnly`.

Все примеры ниже используют `/opt/TelegramSimple` — на новом сервере замените на `/opt/TelegramOnly`.

### 1.1. Подключиться к VPS

```bash
ssh root@IP_СЕРВЕРА
```

После серверного этапа SSH переключается на порт `22542`:

```bash
ssh -p 22542 root@IP_СЕРВЕРА
```

### 1.2. Загрузить и запустить серверный скрипт

**На вашем Mac** (локально):

```bash
cd "/Users/olgazaharova/Project/ProjectPython/TelegramOnly"
scp -P 22 scripts/deploy_fresh_vps.sh root@IP_СЕРВЕРА:/root/
```

**На сервере** (в SSH-сессии):

```bash
bash /root/deploy_fresh_vps.sh
```

Скрипт спрашивает протокол на порт 443 (VLESS-Reality или NaiveProxy), затем:

- Swap 1 GB
- Обновление системы + пакеты
- Docker
- VLESS-Reality (Xray) или NaiveProxy (Caddy)
- Hysteria2 + пароль
- SSH на порт 22542
- UFW firewall
- Fail2ban
- Подготовка каталога проекта + конфиг-файлы
- Сохранение credentials в `CREDENTIALS.txt`

Скрипт рассчитан на повторный запуск — продолжает с уже выполненных шагов.

### 1.3. Подготовить `.env`

**На Mac** (локально):

```bash
cd "/Users/olgazaharova/Project/ProjectPython/TelegramOnly"
cp example.env .env.deploy
```

Заполнить `.env.deploy` значениями из `CREDENTIALS.txt` на сервере:

```bash
ssh -p 22542 root@IP_СЕРВЕРА "cat /opt/TelegramSimple/CREDENTIALS.txt"
```

Минимальный `.env.deploy`:

```dotenv
BOT_TOKEN=токен_от_BotFather
ADMIN_USER_IDS=ваш_telegram_id
API_SECRET_KEY=из_CREDENTIALS
HMAC_SECRET=из_CREDENTIALS
ENCRYPTION_KEY=из_CREDENTIALS
API_URL=http://IP_СЕРВЕРА:8000/ai_query
```

#### Как узнать свой Telegram ID

```bash
export TG_TOKEN='ваш_BOT_TOKEN'
curl "https://api.telegram.org/bot$TG_TOKEN/getMe"        # проверить токен
# Откройте бота в Telegram, отправьте /start, затем:
curl -s "https://api.telegram.org/bot$TG_TOKEN/getUpdates" \
  | python3 -c 'import sys,json; data=json.load(sys.stdin); print(data["result"][-1]["message"]["from"]["id"])'
```

### 1.4. Загрузить код на сервер

**macOS / Linux:**

```bash
cd "/Users/olgazaharova/Project/ProjectPython/TelegramOnly"
rsync -avz -e 'ssh -p 22542' \
  --exclude 'venv' --exclude '__pycache__' --exclude '.env' \
  --exclude 'app_keys.json' --exclude 'users.json' --exclude '*.log' \
  --exclude '.git' --exclude 'docs/' \
  ./ root@IP_СЕРВЕРА:/opt/TelegramSimple/
```

**Windows (Git Bash):**

```bash
cd /c/Project/TelegramOnly && tar --exclude='venv' --exclude='.venv' --exclude='__pycache__' --exclude='.env' --exclude='.env.deploy' --exclude='app_keys.json' --exclude='users.json' --exclude='*.log' --exclude='.git' -czf - . | ssh -p 22542 root@IP_СЕРВЕРА "cd /opt/TelegramSimple && tar -xzf -"
```

### 1.5. Загрузить `.env`

```bash
scp -P 22542 .env.deploy root@IP_СЕРВЕРА:/opt/TelegramSimple/.env
```

Проверить на сервере (должен быть файл, не директория):

```bash
ls -l /opt/TelegramSimple/.env
```

### 1.6. Инициализировать volume-файлы и запустить

**На сервере:**

```bash
cd /opt/TelegramSimple

# Создать файлы, если не существуют
for f in vless_config.json hysteria2_config.json tuic_config.json \
         anytls_config.json xhttp_config.json mtproto_config.json \
         headscale_config.json naiveproxy_config.json app_keys.json \
         users.json bot.log; do
  [ -f "$f" ] || echo '{}' > "$f"
done

docker compose up -d --build telegram-helper
docker logs telegram-helper-lite --tail 20
```

### 1.7. Проверить

```bash
docker compose ps
docker logs telegram-helper-lite --tail 50
```

В Telegram отправьте боту `/start` и `/info`.

### 1.8. Исправить fail2ban (если в статусе `failed`)

```bash
cat >/etc/fail2ban/jail.local <<'EOF'
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 3

[sshd]
enabled = true
port = 22542
backend = systemd
journalmatch = _SYSTEMD_UNIT=ssh.service
maxretry = 3
bantime = 24h
EOF

systemctl restart fail2ban
fail2ban-client ping
fail2ban-client status sshd
```

---

## 2. Редеплой (обновление кода)

Обновляет только контейнер бота. Host-сервисы (Xray, Caddy, Hysteria2, MTProto) не затрагиваются.

### Что нельзя затирать на сервере

`.env`, `app_keys.json`, `users.json`, `vless_config.json`, `naiveproxy_config.json`, `hysteria2_config.json`, `tuic_config.json`, `anytls_config.json`, `xhttp_config.json`, `mtproto_config.json`, `headscale_config.json`, `bot.log`.

### Быстрый сценарий (macOS)

```bash
# 1. С Mac — залить код
cd "/Users/olgazaharova/Project/ProjectPython/TelegramOnly"
rsync -avz -e 'ssh -p 22542' \
  --exclude 'venv' --exclude '.venv' --exclude '__pycache__' \
  --exclude '.env' --exclude '.env.deploy' \
  --exclude 'app_keys.json' --exclude 'users.json' --exclude '*.log' \
  --exclude '.git' \
  ./ root@IP_СЕРВЕРА:/opt/TelegramSimple/

# 2. На сервере — пересобрать и запустить
ssh -p 22542 root@IP_СЕРВЕРА
cd /opt/TelegramSimple
docker compose up -d --build telegram-helper
docker logs telegram-helper-lite --tail 100
```

### Быстрый сценарий (Windows, Git Bash)

```bash
cd /c/Project/TelegramOnly && tar --exclude='venv' --exclude='.venv' --exclude='__pycache__' --exclude='.env' --exclude='.env.deploy' --exclude='app_keys.json' --exclude='users.json' --exclude='*.log' --exclude='.git' -czf - . | ssh -p 22542 root@IP_СЕРВЕРА "cd /opt/TelegramSimple && tar -xzf -"
```

### Перед запуском: проверить volume-файлы

```bash
cd /opt/TelegramSimple
for f in tuic_config.json anytls_config.json xhttp_config.json; do
  [ -f "$f" ] || echo '{}' > "$f"
done
```

Если `echo` выдаёт `Is a directory` — Docker создал директорию вместо файла:

```bash
docker compose down
rm -rf tuic_config.json anytls_config.json xhttp_config.json
echo '{}' > tuic_config.json
echo '{}' > anytls_config.json
echo '{}' > xhttp_config.json
docker compose up -d --build telegram-helper
```

### Пересборка без кеша (если старый код застрял)

```bash
docker compose build --no-cache telegram-helper
docker compose up -d telegram-helper
```

### Очистка Docker (если мало места)

```bash
docker builder prune -af
docker image prune -af
```

### MTProto на хосте после редеплоя

Если через бота менялись MTProto-параметры, синхронизируйте systemd unit:

```bash
cd /opt/TelegramSimple
python3 scripts/mtproto_sync_systemd.py
systemctl show -p ExecStart mtproto-proxy --no-pager
```

---

## 3. Docker

### Контейнеры

| Контейнер | Порт | Назначение |
|-----------|------|------------|
| `telegram-helper-lite` | 8000 | Бот + REST API |
| `dockhand` | 8501 (localhost) | Диагностика (Streamlit) |
| `headscale` | 8080 (localhost) | Mesh VPN (опциональный) |

### compose.yaml — ключевые настройки бота

```yaml
services:
  telegram-helper:
    user: "0:0"          # root — для записи в /etc/hysteria и nsenter
    pid: host            # доступ к host PID namespace (nsenter)
    privileged: true     # capabilities для nsenter
```

`nsenter` нужен для управления host-сервисами (systemctl, journalctl) из контейнера.

### Volumes (bind mounts)

| Хост | Контейнер | Описание |
|------|-----------|----------|
| `.env` | `/app/.env` | Токены и ключи |
| `*_config.json` | `/app/*_config.json` | Конфиги протоколов |
| `app_keys.json` | `/app/app_keys.json` | API ключи |
| `users.json` | `/app/users.json` | Пользователи |
| `bot.log` | `/app/bot.log` | Лог бота |
| `/usr/local/etc/xray` | `/usr/local/etc/xray` | Xray конфиг |
| `/etc/caddy-naive` | `/etc/caddy-naive` | Caddy/NaiveProxy |
| `/etc/hysteria` | `/etc/hysteria` | Hysteria2 certs |
| `/var/run/docker.sock` | `/var/run/docker.sock` | Docker API |

### Dockhand — доступ через SSH-туннель

```bash
ssh -L 8501:localhost:8501 -p 22542 root@IP_СЕРВЕРА
# Открыть: http://localhost:8501
```

### Headscale (опциональный)

```bash
docker compose -f compose.yaml -f compose.headscale.yaml up -d
docker exec headscale headscale users create main_user
```

### Полезные команды

```bash
docker compose ps                              # статус
docker logs telegram-helper-lite --tail 50     # логи
docker compose restart telegram-helper         # перезапуск
docker compose up -d --build telegram-helper   # пересборка
docker system df                               # место на диске
```

---

## 4. Настройка протоколов через бота

### VLESS-Reality (обычно настроен скриптом)

Проверка:

```
/vless_status
/vless_config
/vless_export
```

Если нужно с нуля:

```
/vless_sync
/vless_add_client phone
/vless_qr phone
```

### Hysteria2

```
/hy2_install
/hy2_set_server IP
/hy2_set_port 443
/hy2_gen_all              # авто insecure=1 для self-signed cert
/hy2_on
/hy2_add_client phone
/hy2_apply
/hy2_start
/hy2_qr phone
```

Firewall: `ufw allow 443/udp`

### TUIC

```
/tuic_set_server IP
/tuic_set_port 8444
/tuic_gen_all
/tuic_on
/tuic_add phone
/tuic_apply
/tuic_start
/tuic_qr phone
```

Firewall: `ufw allow 8444/udp`

### AnyTLS

```
/anytls_set_server IP
/anytls_set_port 8445
/anytls_gen_all
/anytls_on
/anytls_add phone
/anytls_apply
/anytls_start
/anytls_qr phone
```

Firewall: `ufw allow 8445/tcp`

### XHTTP

```
/xhttp_set_server IP
/xhttp_set_port 8446
/xhttp_gen_all
/xhttp_on
/xhttp_add phone
/xhttp_apply
/xhttp_start
/xhttp_qr phone
```

Firewall: `ufw allow 8446/tcp`

### NaiveProxy

```
/naive_install
/naive_set_domain example.com
/naive_set_port 443
/naive_gen_creds
/naive_on
/naive_apply
/naive_uri
```

### MTProto (установка на хосте VPS, не из Docker)

MTProto требует `apt`, `systemd`, прямой доступ к сети — ставить в SSH на сервере:

```bash
cd /opt/TelegramSimple
bash scripts/install_mtproto.sh --port 993 --domain google.com --workers 2
```

Рекомендуемый режим: **dd** (основной, без `-D`):

```bash
BASE_SECRET=$(head -c 16 /dev/urandom | xxd -ps -c 32)
CLIENT_SECRET="dd${BASE_SECRET}"
SERVER_IP="IP_СЕРВЕРА"
PORT="993"

cat >/etc/systemd/system/mtproto-proxy.service <<EOF
[Unit]
Description=MTProto Proxy
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/mtproto-proxy -u nobody -p 2398 -H ${PORT} -S ${BASE_SECRET} --aes-pwd /etc/mtproto-proxy/proxy-secret /etc/mtproto-proxy/proxy-multi.conf -M 1 --nat-info ${SERVER_IP}:${SERVER_IP}
Restart=on-failure
RestartSec=5
LimitNOFILE=infinity

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl restart mtproto-proxy
```

После установки — через бота только для просмотра:

```
/mt_status
/mt_config
/mt_export
```

Не используйте `/mt_install`, `/mt_apply`, `/mt_start` из Docker — они не могут управлять host systemd напрямую.

Синхронизация после изменений через бота:

```bash
python3 scripts/mtproto_sync_systemd.py
systemctl show -p ExecStart mtproto-proxy --no-pager
```

---

## 5. Частые ошибки и решения

### `.env` стал директорией

```bash
docker compose down
rm -rf /opt/TelegramSimple/.env
# С Mac:
scp -P 22542 .env.deploy root@IP_СЕРВЕРА:/opt/TelegramSimple/.env
docker compose up -d telegram-helper
```

### `Is a directory` при создании config.json

Docker создал директорию вместо файла. Решение:

```bash
docker compose down
rm -rf имя_файла
echo '{}' > имя_файла
docker compose up -d telegram-helper
```

### `nsenter: Operation not permitted`

В `compose.yaml` нужно `privileged: true` и `pid: host`.

### `systemctl not found` в контейнере

Нужен `pid: host` в compose.yaml — бот использует `nsenter` для host-команд.

### `authentication failed, status code: 403` (Hysteria2)

Sing-box передаёт только password, а сервер ожидает `user:password`. Убедитесь, что URI импортируется полностью (с `user:` частью).

### `Permission denied /etc/hysteria`

В compose.yaml нужно `user: "0:0"`.

### `404 Not Found` при Telegram API

Неверный `BOT_TOKEN`. Проверьте: `curl "https://api.telegram.org/bot$TOKEN/getMe"`.

### `apt lock` на сервере

```bash
ps -ef | grep -E 'apt|dpkg'
# Если зависший apt-get update:
kill <PID>
```

### Лишние файлы в `/opt/TelegramSimple`

```bash
rm -rf .bash_history .bashrc .profile .ssh .config .pytest_cache .DS_Store __pycache__
```

### `rsync: command not found`

```bash
apt-get update && apt-get install -y rsync
```

### Контейнер не стартует

```bash
docker logs telegram-helper-lite --tail 50
```

Обычно: неверный `BOT_TOKEN` или отсутствует `.env`.

### QR-код не работает после обновления

```bash
# Пересобрать контейнер (requirements.txt мог обновиться)
docker compose up -d --build telegram-helper
docker exec telegram-helper-lite python -c "import qrcode; print('ok')"
```

---

## 6. Смена токена бота

### 1. Перевыпустить у @BotFather

```
/revoke → выбрать бота → /token → скопировать новый токен
```

### 2. Обновить `.env.deploy` на Mac

```dotenv
BOT_TOKEN=новый_токен
```

### 3. Загрузить на сервер

```bash
cd /opt/TelegramSimple
docker compose down
# С Mac:
scp -P 22542 .env.deploy root@IP_СЕРВЕРА:/opt/TelegramSimple/.env
```

### 4. Перезапустить

```bash
cd /opt/TelegramSimple
docker compose up -d telegram-helper
docker logs telegram-helper-lite --tail 50
```

### 5. Проверить в Telegram

```
/start
/info
```

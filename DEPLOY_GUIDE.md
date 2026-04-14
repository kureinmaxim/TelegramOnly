# Deploy TelegramOnly

## Обзор

Полная инструкция по установке TelegramOnly на чистый VPS (Debian 11/12).

Серверный скрипт `deploy_fresh_vps.sh` при запуске предлагает выбор:

```text
Что установить на порт 443 (TCP)?

  [1] VLESS-Reality (Xray)  — лучший стелс, маскировка под TLS
  [2] NaiveProxy (Caddy)    — HTTPS-прокси, нужен домен, Chrome TLS
```

**VLESS-Reality** — не требует домен, лучший стелс, основной вариант.
**NaiveProxy** — требует домен (например `naive.kurein.me`), Chrome TLS fingerprint, запасной канал.

Серверный layout: `/opt/TelegramSimple` (исторический путь, не переименовывается).

---

## Фаза 1 — На сервере (SSH)

### Важно: первый вход на чистый VPS обычно идёт через `22`, но дальше работаем через `22542`

Актуальный сценарий теперь такой:

- первый вход на свежий Debian VPS может быть через стандартный `22`
- серверный этап сразу готовит дальнейшую работу под `22542`
- после серверного этапа все новые SSH/SCP/rsync-подключения используйте уже через `22542`

### Шаг 0: Подключиться к чистому серверу
Выполнять **на вашем Mac**:

```bash
ssh root@138.124.71.73
```

### Шаг 0.1: После серверного этапа переподключайтесь уже на `22542`

Как только серверный этап завершён и SSH уже переведён на новый порт, все новые подключения открывайте так:

```bash
ssh -p 22542 root@138.124.71.73
```

### Загрузить скрипт на сервер
Выполнять **на вашем Mac**, в отдельном локальном терминале:

```bash
cd "/Users/olgazaharova/Project/ProjectPython/TelegramOnly"
scp -P 22 scripts/deploy_fresh_vps.sh root@138.124.71.73:/root/
```

### Запустить скрипт на сервере
Выполнять **в уже открытой SSH-сессии на сервере**:

```bash
bash /root/deploy_fresh_vps.sh
```

Если скрипт оборвался, просто запускайте его повторно:

```bash
bash /root/deploy_fresh_vps.sh
```

Он рассчитан на повторный запуск и обычно продолжает установку с уже выполненных шагов.

### Что делает серверный скрипт

**Скрипт:** `scripts/deploy_fresh_vps.sh`

Скрипт спрашивает протокол на 443 (VLESS или NaiveProxy), затем:

- Swap 1 GB (критично для 1 GB RAM)
- Обновление системы + пакеты
- Docker
- **VLESS path:** Xray + генерация ключей Reality
- **NaiveProxy path:** Go + xcaddy + Caddy с forwardproxy (сборка ~5 мин)
- Hysteria2 + генерация пароля
- SSH на порт `22542`
- UFW firewall (SSH, TCP/443, UDP/443, TCP/8000, TCP/993; +80/tcp для NaiveProxy ACME)
- Fail2ban
- Подготовка `/opt/TelegramSimple` + конфиг-файлы (`vless_config.json` или `naiveproxy_config.json`)
- Сохранение credentials в `CREDENTIALS.txt`

---

## Фаза 2 — С вашего ПК

Все команды в этой фазе выполнять **только локально на вашем ПК**, а не в SSH-сессии сервера.
Если в приглашении терминала вы видите что-то вроде `root@...:~#`, значит вы все еще на сервере и команды `rsync`, `scp`, `curl`, `cd /Users/...` или `cd /c/...` там запускать не нужно.

### Что реально делать сразу после `bash /root/deploy_fresh_vps.sh`

Сообщение серверного скрипта:

```text
Следующий шаг:
С локального ПК выполните загрузку проекта и docker compose up.
```

нужно понимать так:

1. Перейти в `Фаза 2 — С вашего ПК`
2. Сначала создать и заполнить `.env.deploy`
3. Потом выполнить `rsync`
4. Потом загрузить `.env` через `scp`
5. И только после этого вернуться на сервер и делать `docker compose up -d telegram-helper`

То есть `docker compose up` — это **не первый** шаг после серверного скрипта, а последний шаг после подготовки `.env.deploy` и загрузки проекта.

### Шаг 1: Подготовить `.env`

#### Вариант A. Windows 11 + Git Bash

```bash
cd /c/Project/TelegramOnly
cp example.env .env.deploy
```

#### Вариант B. macOS / Linux

```bash
cd "/Users/olgazaharova/Project/ProjectPython/TelegramOnly"
cp example.env .env.deploy
```

Когда начинать этот шаг:

- **сразу после** успешного завершения `bash /root/deploy_fresh_vps.sh` на сервере
- после того как вы посмотрели `/opt/TelegramSimple/CREDENTIALS.txt`
- до `rsync`, `scp` и `docker compose up`

Как открыть и редактировать `.env.deploy` локально:

Вариант 1, через терминал:

```bash
cd "/Users/olgazaharova/Project/ProjectPython/TelegramOnly"
nano .env.deploy
```

Сохранение в `nano`:

1. `Ctrl + O`
2. `Enter`
3. `Ctrl + X`

Вариант 2, через Cursor/редактор:

- открыть файл `.env.deploy` прямо в проекте
- вставить значения
- сохранить как обычный текстовый файл

Перед редактированием полезно на сервере открыть `CREDENTIALS.txt` и выписать нужные значения:

```bash
cat /opt/TelegramSimple/CREDENTIALS.txt | cat
```

### Как получить `ADMIN_USER_IDS` и сразу проверить `BOT_TOKEN`

Это основной и рекомендуемый путь.

#### 1. Локально сохранить токен в переменную окружения

```bash
export TG_TOKEN='сюда_ваш_реальный_BOT_TOKEN'
```

#### 2. Проверить, что токен рабочий

```bash
curl "https://api.telegram.org/bot$TG_TOKEN/getMe"
```

Если всё правильно, в ответе будет:

```json
"ok": true
```

Пример реального успешного ответа:

```json
{"ok":true,"result":{"id":8554589276,"is_bot":true,"first_name":"mk","username":"mkurein_bot"}}
```

#### 3. Открыть бота в Telegram и отправить `/start`

Это нужно, чтобы `getUpdates` увидел ваше сообщение.

#### 4. Получить ваш Telegram ID

```bash
curl -s "https://api.telegram.org/bot$TG_TOKEN/getUpdates" | python3 -c 'import sys, json; data=json.load(sys.stdin); print(data["result"][-1]["message"]["from"]["id"])'
```

Пример успешного результата:

```bash
1290265278
```

Именно это число нужно подставить в `.env.deploy`:

```dotenv
ADMIN_USER_IDS=1290265278
```

Если админов несколько:

```dotenv
ADMIN_USER_IDS=1290265278,987654321
```

#### 5. Если `curl ... getMe` не работает

Чаще всего причина в одном из двух:

- не подставлен реальный токен
- команда запущена с шаблоном вроде `ВАШ_BOT_TOKEN`

Неправильно:

```bash
curl "https://api.telegram.org/botВАШ_BOT_TOKEN/getMe"
```

Правильно:

```bash
export TG_TOKEN='реальный_токен'
curl "https://api.telegram.org/bot$TG_TOKEN/getMe"
```

Заполнить `.env.deploy` (подставить значения из `CREDENTIALS.txt` на сервере):
```dotenv
BOT_TOKEN=ваш_токен_от_BotFather
ADMIN_USER_IDS=ваш_telegram_id
API_SECRET_KEY=значение_из_CREDENTIALS
HMAC_SECRET=значение_из_CREDENTIALS
ENCRYPTION_KEY=значение_из_CREDENTIALS
API_URL=http://138.124.71.73:8000/ai_query
DEFAULT_AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-api03-...
ANTHROPIC_MODEL=claude-opus-4-6
```

### Как получить `ANTHROPIC_API_KEY`

1. Зайдите в [Anthropic Console](https://console.anthropic.com/).
2. Откройте раздел `API Keys`.
3. Нажмите `Create Key`.
4. Скопируйте ключ вида `sk-ant-...` и вставьте его в `.env.deploy`.

Минимум для Anthropic:

```dotenv
DEFAULT_AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-opus-4-6
```

Если AI пока не нужен, бот можно поднять позже с этим ключом отдельно, но для AI-команд он обязателен.

### Шаг 2: Загрузить код на сервер
Если `rsync` не установлен на сервере, сначала выполните на VPS:

```bash
apt-get update && apt-get install -y rsync
```

#### Вариант A. Windows 11 + Git Bash

```bash
cd /c/Project/TelegramOnly && tar --exclude='venv' --exclude='.venv' --exclude='__pycache__' --exclude='.env' --exclude='.env.deploy' --exclude='app_keys.json' --exclude='users.json' --exclude='*.log' --exclude='.git' -czf - . | ssh -p 22542 root@138.124.71.73 "cd /opt/TelegramSimple && tar -xzf -"
```

Важно:

- это команда именно для `Git Bash`, не для `PowerShell`
- она копирует свежий код с вашего ПК на сервер, не затирая `.env` и серверные JSON-файлы
- если команда была вставлена частями и зависла, нажмите `Ctrl+C` и вставьте её заново одной строкой

#### Вариант B. macOS / Linux

Выполнять локально на вашем Mac:

```bash
cd "/Users/olgazaharova/Project/ProjectPython/TelegramOnly"
rsync -avz -e 'ssh -p 22542' \
  --exclude 'venv' --exclude '__pycache__' --exclude '.env' \
  --exclude 'app_keys.json' --exclude 'users.json' --exclude '*.log' \
  --exclude '.git' --exclude 'docs/' \
  ./ \
  root@138.124.71.73:/opt/TelegramSimple/
```

### Шаг 3: Загрузить `.env`

#### Вариант A. Windows 11 + Git Bash

```bash
cd /c/Project/TelegramOnly
scp -P 22542 .env.deploy root@138.124.71.73:/opt/TelegramSimple/.env
```

#### Вариант B. macOS / Linux

Выполнять локально **на вашем Mac** из папки проекта:

```bash
cd "/Users/olgazaharova/Project/ProjectPython/TelegramOnly"
scp -P 22542 .env.deploy root@138.124.71.73:/opt/TelegramSimple/.env
```

Сразу проверьте на сервере, что `.env` стал **обычным файлом**, а не директорией:

```bash
ls -l /opt/TelegramSimple/.env | cat
```

Ожидается строка, начинающаяся с `-rw-`, а не `drwx`.

### Шаг 4: Запустить Docker (только бот, без Dockhand)
Теперь вернуться в SSH-сессию на сервере и выполнить:

```bash
cd /opt/TelegramSimple
docker compose up -d telegram-helper
```

### Шаг 5: Проверить
В SSH-сессии на сервере:

```bash
docker compose ps | cat
docker logs telegram-helper-lite --tail 20 | cat
```

### Проверить `fail2ban`, если в сводке был `failed`

Это не блокирует запуск бота, но лучше исправить после первого деплоя.

На Debian VPS `sshd` часто пишет не в `/var/log/auth.log`, а в `journald`, поэтому стандартный jail может не стартовать.

Рабочий вариант:

```bash
cp /etc/fail2ban/jail.local /etc/fail2ban/jail.local.bak 2>/dev/null || true
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
sleep 3
systemctl status fail2ban --no-pager | cat
fail2ban-client ping | cat
fail2ban-client status | cat
fail2ban-client status sshd | cat
```

Ожидаемый результат:

- `systemctl status fail2ban` показывает `active (running)`
- `fail2ban-client ping` отвечает `Server replied: pong`
- `fail2ban-client status` показывает jail `sshd`
- `fail2ban-client status sshd` показывает `Currently banned: 0` и `Journal matches: _SYSTEMD_UNIT=ssh.service`

---

## Частые ошибки

### `404 Not Found` при `getUpdates` или `getMe`

Почти всегда это значит, что `BOT_TOKEN` скопирован неверно или не целиком.

Проверка:

```bash
curl "https://api.telegram.org/botВАШ_BOT_TOKEN/getMe"
```

Если токен рабочий, в ответе будет `"ok": true`.

### `"result": []` при `getUpdates`

Это значит, что бот еще не получил от вас сообщение.

Что сделать:

1. Откройте бота в Telegram.
2. Нажмите `Start` или отправьте обычное сообщение.
3. Повторите `getUpdates`.

### `rsync: command not found`

На сервере не установлен `rsync`.

Исправление:

```bash
apt-get update && apt-get install -y rsync
```

### `apt` lock / `Could not get lock /var/lib/apt/lists/lock`

На чистом Debian это частая проблема. Причины обычно две:

1. ещё работает автоматический `apt`/`cloud-init`
2. предыдущий запуск `deploy_fresh_vps.sh` завис на `apt-get update`

Сначала посмотрите, кто держит lock:

```bash
ps -ef | grep -E 'apt|dpkg' | cat
systemctl status apt-daily.service apt-daily-upgrade.service --no-pager | cat
```

Если видно, что завис **именно** процесс вида:

```text
apt-get ... update
```

а `apt-daily` уже не активен, его обычно можно безопасно остановить:

```bash
kill <PID>
sleep 2
ps -fp <PID> | cat
```

Если не остановился:

```bash
kill -9 <PID>
sleep 2
ps -fp <PID> | cat
```

Потом проверить, что lock ушёл:

```bash
fuser /var/lib/apt/lists/lock | cat
```

Если вывода нет, lock свободен и можно снова запускать:

```bash
bash /root/deploy_fresh_vps.sh
```

Важно:

- не удаляйте lock-файлы вручную
- не убивайте `dpkg`, `apt install`, `apt upgrade`, если не уверены
- останавливать безопаснее только зависший `apt-get update`

### В `/opt/TelegramSimple` случайно скопировались `.bashrc`, `.ssh`, `.config`, `.env.deploy`

Это обычно значит, что `rsync` или `scp` были запущены внутри SSH-сессии на сервере, а не на вашем Mac.

Признак ошибки:
- в терминале видно приглашение вида `root@server:~#`

Лишние файлы можно удалить так:

```bash
cd /opt/TelegramSimple
rm -rf .bash_history .bashrc .profile .ssh .config .claude .pytest_cache ".DS_Store" ".env.deploy" "__pycache_ и. ]_"
```

### `/opt/TelegramSimple/.env` стал директорией

Это критично для `compose.yaml`, потому что сервис монтирует:

```yaml
./.env:/app/.env
```

Если на хосте `/opt/TelegramSimple/.env` стал директорией, контейнер будет видеть `/app/.env` как директорию, а не как файл.

Исправление:

```bash
cd /opt/TelegramSimple
docker compose down
rm -rf /opt/TelegramSimple/.env
```

После этого **с Mac** заново загрузите файл:

```bash
cd "/Users/olgazaharova/Project/ProjectPython/TelegramOnly"
scp .env.deploy root@138.124.71.73:/opt/TelegramSimple/.env
```

Проверка:

```bash
ls -l /opt/TelegramSimple/.env | cat
```

Только после этого снова запускайте:

```bash
cd /opt/TelegramSimple
docker compose up -d telegram-helper
```

### `Permission denied (publickey,password)` при SSH

Проверьте:

1. Правильный порт SSH.
2. Правильный пароль или SSH-ключ.
3. Что `sshd` действительно слушает нужный порт.

Быстрая проверка с Mac:

```bash
ssh -p 22542 root@138.124.71.73
```

### Контейнер не стартует

Сразу проверьте:

```bash
ssh -p 22542 root@138.124.71.73 "cd /opt/TelegramSimple && docker compose ps | cat"
ssh -p 22542 root@138.124.71.73 "docker logs telegram-helper-lite --tail 50 | cat"
```

---

## Смена токена Telegram-бота

Если токен случайно попал в лог, чат или shell history, считайте его скомпрометированным и сразу перевыпускайте.

### Шаг 1: Перевыпустить токен у `@BotFather`

В Telegram:

```text
/revoke
```

Выберите нужного бота, затем:

```text
/token
```

Получите новый `BOT_TOKEN`.

### Шаг 2: Обновить локальный `.env.deploy` на Mac

Откройте и замените строку:

```dotenv
BOT_TOKEN=новый_токен
```

### Шаг 3: Обновить `.env` на сервере

Сначала остановите контейнер и убедитесь, что `.env` на хосте не директория:

```bash
cd /opt/TelegramSimple
docker compose down
ls -ld /opt/TelegramSimple/.env | cat
```

Если это директория, исправьте по инструкции выше из раздела `/opt/TelegramSimple/.env стал директорией`.

Потом **с Mac** заново загрузите файл:

```bash
cd "/Users/olgazaharova/Project/ProjectPython/TelegramOnly"
scp -P 22542 .env.deploy root@138.124.71.73:/opt/TelegramSimple/.env
```

### Шаг 4: Перезапустить бота

На сервере:

```bash
cd /opt/TelegramSimple
docker compose up -d telegram-helper
docker logs telegram-helper-lite --tail 50 | cat
```

### Шаг 5: Проверить бота

В Telegram:

```text
/start
/info
```

---

## Фаза 3 — Настройка через бота

После того как бот запущен, в Telegram:

### VLESS-Reality (уже настроен скриптом, проверить)

`VLESS-Reality` обычно уже поднимается серверным скриптом, поэтому после деплоя его не нужно устанавливать заново, а нужно проверить, что:

- сервис `xray` запущен
- порт `443/tcp` слушается
- файл `/opt/TelegramSimple/vless_config.json` содержит актуальные параметры клиента

Проверка на сервере:

```bash
systemctl status xray --no-pager | cat
ss -tulpn | grep 443 | cat
cat /opt/TelegramSimple/vless_config.json | cat
```

Что должно быть:

- `xray` = `active (running)`
- `443/tcp` слушается
- в `vless_config.json` есть:
  - `server`
  - `port`
  - `uuid`
  - `public_key`
  - `short_id`
  - `sni`
  - `fingerprint`

Быстрая проверка через бота:

```text
/vless_status
/vless_config
/vless_export
```

Если `/vless_export` отдаёт готовую ссылку, это самый удобный способ подключить клиента.

Если хотите настраивать вручную, берите параметры именно из:

```bash
cat /opt/TelegramSimple/vless_config.json | cat
```

Минимально нужны:

- `server`: `138.124.71.73`
- `port`: `443`
- `uuid`
- `public_key`
- `short_id`
- `sni`
- `fingerprint`
- `flow`: `xtls-rprx-vision`

Подробная отдельная инструкция:

```text
VLESS_GUIDE.md
```

### NaiveProxy (если выбран при установке)

Если скрипт установил NaiveProxy, проверка:

```bash
systemctl status caddy-naive --no-pager | cat
cat /opt/TelegramSimple/naiveproxy_config.json | cat
```

Через бота:

```text
/naive_status
/naive_config
/naive_uri       — клиентский URI для подключения
/naive_export    — экспорт JSON + ApiNgRPC profile
```

### Hysteria2 (синхронизировать с сервером)

```text
/hy2_set_server 138.124.71.73
/hy2_set_port 443
/hy2_set_password <пароль_из_CREDENTIALS>
/hy2_on
/hy2_export      — получить клиентский конфиг
```

### MTProto (установка на хосте VPS, не из Docker)

Команда `/mt_install` из бота внутри Docker-контейнера не подходит для реальной установки, потому что MTProto требует:

- `apt`
- `systemd`
- открытие порта на хосте
- установку бинарника `mtproto-proxy` в систему

Поэтому MTProto ставить нужно **в SSH-сессии на самом VPS**, а не через контейнер.

#### 1. Установить `cron`, если его нет

Скрипт `scripts/install_mtproto.sh` использует `crontab` для ежедневного обновления `proxy-secret` и `proxy-multi.conf`.

Если при запуске есть ошибка:

```text
crontab: command not found
```

выполните:

```bash
apt-get update && apt-get install -y cron
systemctl enable cron
systemctl start cron
```

#### 2. Установить MTProto на хосте VPS

В SSH-сессии на сервере:

```bash
cd /opt/TelegramSimple
bash scripts/install_mtproto.sh --port 993 --domain google.com --workers 2
```

Скрипт:

- соберёт `mtproto-proxy`
- создаст `systemd`-сервис
- откроет `993/tcp`
- попытается сгенерировать fake-TLS `Secret`
- сохранит клиентские параметры в `~/mtproto_client.txt`
- выведет готовые ссылки `tg://proxy?...` и `https://t.me/proxy?...`

#### 3. Рекомендуемый рабочий режим: `dd` (основной)

По фактическим тестам на этом VPS и клиентах Telegram наиболее надёжно работает **обычный `dd`-secret без `-D`**.

Рекомендуется использовать именно его как основной production-вариант:

```bash
BASE_SECRET=$(head -c 16 /dev/urandom | xxd -ps -c 32)
CLIENT_SECRET="dd${BASE_SECRET}"
SERVER_IP="138.124.71.73"
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

cat >/root/mtproto_client.txt <<EOF
Server: ${SERVER_IP}
Port: ${PORT}
Secret: ${CLIENT_SECRET}

tg://proxy?server=${SERVER_IP}&port=${PORT}&secret=${CLIENT_SECRET}
https://t.me/proxy?server=${SERVER_IP}&port=${PORT}&secret=${CLIENT_SECRET}
EOF

systemctl daemon-reload
systemctl restart mtproto-proxy
```

Почему именно `dd`:

- на этом VPS он показал себя стабильнее
- Telegram Desktop и mobile-клиент реально подключались
- не требует TLS-domain режима `-D`
- проще диагностируется и меньше зависит от особенностей сборки `mtproto-proxy`

#### 4. Экспериментальный режим: `ee + -D`

`ee + -D` можно пробовать только как дополнительный эксперимент. Он потенциально даёт более правдоподобную fake-TLS маскировку, но по фактическим тестам в этом окружении оказался менее надёжным.

Используйте этот режим только если хотите отдельно тестировать fake-TLS и готовы к нестабильной работе.

#### 5. Если сервис не стартует с ошибкой про `-S`

На некоторых сборках `mtproto-proxy` серверный параметр `-S` принимает только **32 hex-символа** (16 байт), а домен для fake-TLS нужно задавать отдельно через `-D`.

Симптом в логах:

```text
'S' option requires exactly 32 hex digits
```

В этом случае выполните на сервере:

```bash
BASE_SECRET=$(head -c 16 /dev/urandom | xxd -ps -c 32)
DOMAIN="google.com"
DOMAIN_HEX=$(printf '%s' "$DOMAIN" | xxd -ps -c 256)
CLIENT_SECRET="ee${BASE_SECRET}${DOMAIN_HEX}"
SERVER_IP="138.124.71.73"
PORT="993"

cat >/etc/systemd/system/mtproto-proxy.service <<EOF
[Unit]
Description=MTProto Proxy
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/mtproto-proxy -u nobody -p 2398 -H ${PORT} -S ${BASE_SECRET} -D ${DOMAIN} --aes-pwd /etc/mtproto-proxy/proxy-secret /etc/mtproto-proxy/proxy-multi.conf -M 1 --nat-info ${SERVER_IP}:${SERVER_IP}
Restart=on-failure
RestartSec=5
LimitNOFILE=infinity

[Install]
WantedBy=multi-user.target
EOF

cat >/root/mtproto_client.txt <<EOF
Server: ${SERVER_IP}
Port: ${PORT}
Domain: ${DOMAIN}
Secret: ${CLIENT_SECRET}

tg://proxy?server=${SERVER_IP}&port=${PORT}&secret=${CLIENT_SECRET}
https://t.me/proxy?server=${SERVER_IP}&port=${PORT}&secret=${CLIENT_SECRET}
EOF

systemctl daemon-reload
systemctl restart mtproto-proxy
```

Важно:

- серверу передаётся `-S ${BASE_SECRET}` и `-D google.com`
- клиенту Telegram нужен именно `CLIENT_SECRET` формата `ee<32hex><domain_hex>`
- режим `ee + -D` здесь считается **экспериментальным**, а не основным
- после такой ручной правки **не используйте** `/mt_install`, `/mt_apply`, `/mt_start` из бота, пока код проекта не будет исправлен, иначе unit-файл снова перезапишется неверно

#### 6. Проверить MTProto после установки

Используйте `grep`, потому что `rg` может не быть установлен на сервере:

```bash
systemctl status mtproto-proxy --no-pager | cat
ss -tulpn | grep 993 | cat
cat /root/mtproto_client.txt | cat
```

Ожидается:

- `mtproto-proxy.service` = `active (running)`
- в `/root/mtproto_client.txt` есть `Secret` и `tg://proxy?...`
- для рекомендуемого режима `Secret` должен начинаться с `dd`
- для экспериментального fake-TLS режима `Secret` будет начинаться с `ee`

#### 7. Подключить MTProto в Telegram

Самый удобный способ: открыть ссылку `tg://proxy?...` из `/root/mtproto_client.txt`.

Если вводить вручную:

- `Server`: `138.124.71.73`
- `Port`: `993`
- `Secret`: значение из `/root/mtproto_client.txt`

Если Telegram не подключается:

1. Полностью удалите старый MTProto proxy из Telegram.
2. Добавьте новый заново только по свежей ссылке из `/root/mtproto_client.txt`.
3. Сначала тестируйте рекомендуемый `dd`-режим.
4. `ee + -D` пробуйте только отдельно, как эксперимент.

#### 8. Синхронизация host systemd после изменений MTProto

Если бот работает в Docker, а `mtproto-proxy` запущен как host service, логика такая:

1. бот меняет `mtproto_config.json`
2. Debian-хост должен пересобрать `systemd unit`
3. только после этого новые клиенты и секреты реально начинают работать

Выполнять на сервере:

```bash
cd /opt/TelegramSimple
python3 scripts/mtproto_sync_systemd.py
systemctl show -p ExecStart mtproto-proxy --no-pager | cat
systemctl status mtproto-proxy --no-pager | cat
```

Это нужно делать после команд:

```text
/mt_gen_all
/mt_add_client <name>
/mt_del_client <name>
/mt_set_mode ...
/mt_set_domain ...
/mt_set_port ...
/mt_set_workers ...
/mt_set_tag ...
```

Особенно важно после `/mt_add_client`: в `ExecStart` должны появляться дополнительные `-S` для новых клиентов.

#### 9. Команды бота после установки MTProto на хосте

После успешной хостовой установки и синхронизации unit можно использовать команды бота уже для просмотра и проверки:

```text
/mt_status
/mt_config
/mt_export
```

Но команды, которые пытаются заново ставить MTProto из Docker, по-прежнему использовать не нужно:

```text
/mt_install
/mt_apply
/mt_start
```

### Проверка всего
```text
/vless_status
/hy2_status
/mt_status
```
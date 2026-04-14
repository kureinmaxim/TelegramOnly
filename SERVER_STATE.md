# Состояние сервера kurein.me — 2026-04-14

Документ фиксирует текущее состояние инфраструктуры, что уже сделано,
какими командами проверялось и что предстоит сделать.

---

## Домен и Cloudflare

### Что сделано

- Домен `kurein.me` куплен в **GoDaddy**
- NS-записи в GoDaddy заменены на Cloudflare:
  ```
  erin.ns.cloudflare.com
  leo.ns.cloudflare.com
  ```
- Управление DNS перенесено в **Cloudflare**
- В Cloudflare настроены A-записи:

| Имя | Тип | Значение | Proxy |
|-----|-----|----------|-------|
| `kurein.me` | A | `138.124.71.73` | DNS only (серая тучка) |
| `headscale.kurein.me` | A | `138.124.71.73` | DNS only (серая тучка) |

- **Proxy (оранжевая тучка) отключён** — обязательно для Xray Reality.
  Cloudflare не должен перехватывать трафик.

### Проверка DNS (с Mac)

```bash
nslookup kurein.me
# → Address: 138.124.71.73  ✅

nslookup headscale.kurein.me
# → Address: 138.124.71.73  ✅
```

### Почему curl https://kurein.me даёт ошибку SSL

```bash
curl -I https://kurein.me
# curl: (60) SSL: no alternative certificate subject name matches target host name 'kurein.me'
```

Это **ожидаемо и нормально**. Xray Reality на порту 443 использует TLS-маскировку
под `www.microsoft.com`, а не реальный сертификат kurein.me. SSL-ошибка означает,
что Reality работает корректно — сервер не выдаёт себя за kurein.me.

---

## Сервер 138.124.71.73

**OS:** Debian 6.1.0-38-cloud-amd64  
**Hostname:** hiplet-58741

### Что установлено и запущено

#### Xray (VLESS-Reality)

```bash
systemctl status xray --no-pager
# Active: active (running) since 2026-04-06 06:39:06 UTC
```

**Конфиг:** `/usr/local/etc/xray/config.json`

```json
{
  "log": {"loglevel": "warning"},
  "inbounds": [{
    "port": 443,
    "protocol": "vless",
    "settings": {
      "clients": [
        {"id": "502f38ce-610a-40c3-93e2-af4e5f2cd2c5", "flow": "xtls-rprx-vision"}
      ],
      "decryption": "none"
    },
    "streamSettings": {
      "network": "tcp",
      "security": "reality",
      "realitySettings": {
        "show": false,
        "dest": "www.microsoft.com:443",
        "xver": 0,
        "serverNames": ["www.microsoft.com"],
        "privateKey": "-HIEyQ9u36WLKWGAFxD3QCjEifPCAO03tmrtf9T-KEE",
        "shortIds": ["e3a45960"]
      }
    }
  }],
  "outbounds": [{"protocol": "freedom", "tag": "direct"}]
}
```

**Параметры клиента VLESS:**

| Поле | Значение |
|------|----------|
| server | `138.124.71.73` |
| port | `443` |
| uuid | `502f38ce-610a-40c3-93e2-af4e5f2cd2c5` |
| flow | `xtls-rprx-vision` |
| security | `reality` |
| sni / serverName | `www.microsoft.com` |
| shortId | `e3a45960` |
| fingerprint | `chrome` |
| public\_key | `OqJxcxcOEoph35yla3pSLTCxYTkU1Su9JtyGjsp6xVA` |

> Nginx установлен на :8443, но fallback в Xray не настроен (не требуется — Reality
> сама перенаправляет не-VLESS трафик на dest: `www.microsoft.com`).

**VLESS-ссылка для импорта в ApiNgRPC:**

```text
vless://502f38ce-610a-40c3-93e2-af4e5f2cd2c5@138.124.71.73:443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.microsoft.com&fp=chrome&pbk=OqJxcxcOEoph35yla3pSLTCxYTkU1Su9JtyGjsp6xVA&sid=e3a45960&type=tcp#kurein-vless
```

#### Hysteria2

Запущен как отдельный процесс, слушает **UDP 443**.

```bash
ss -tulpn | grep hysteria
# udp UNCONN 0 0 *:443 *:*  users:(("hysteria",pid=15889,fd=3))
```

> Конфиг и credentials — в `/opt/TelegramSimple/` (монтируется в контейнер бота).

#### MTProto Proxy

```bash
ss -tulpn | grep 993
# tcp LISTEN 0 4096 0.0.0.0:993  users:(("mtproto-proxy",...))
```

Работает как host-процесс (не Docker). Клиентские параметры:
```bash
cat /root/mtproto_client.txt
```

#### Telegram Bot (Docker)

```bash
docker ps
# telegram-helper-lite   Up 4 days   0.0.0.0:8000->8000/tcp
```

**Deployment path:** `/opt/TelegramSimple/`

Маунты контейнера:
```
/opt/TelegramSimple/app_keys.json         → /app/app_keys.json
/opt/TelegramSimple/hysteria2_config.json → /app/hysteria2_config.json
/opt/TelegramSimple/mtproto_config.json   → /app/mtproto_config.json
/opt/TelegramSimple/users.json            → /app/users.json
/opt/TelegramSimple/headscale_config.json → /app/headscale_config.json
/opt/TelegramSimple/.env                  → /app/.env
/opt/TelegramSimple/vless_config.json     → /app/vless_config.json
/opt/TelegramSimple/bot.log               → /app/bot.log
/var/run/docker.sock                      → /var/run/docker.sock
/usr/local/etc/xray                       → /usr/local/etc/xray  ← для apply_xray_config
```

> После `/vless_add_client` бот автоматически записывает обновлённый конфиг в `/usr/local/etc/xray/config.json` и просит выполнить `systemctl restart xray`.
> Права на директорию должны быть `drwxr-xrwx` (`chmod o+w /usr/local/etc/xray/`) и файл `chmod o+w /usr/local/etc/xray/config.json`.

#### SSH

```bash
ss -tulpn | grep 22542
# tcp LISTEN 0 128 0.0.0.0:22542
```

Порт изменён со стандартного 22 на **22542**.

Подключение с Mac:
```bash
ssh -p 22542 root@138.124.71.73
```

### Открытые порты (UFW)

```
22542/tcp   SSH
443/tcp     Xray VLESS-Reality
443/udp     Hysteria2
8000/tcp    Telegram Bot API
993/tcp     MTProto Proxy
```

### Что НЕ установлено

| Компонент | Статус |
|-----------|--------|
| Nginx | ✅ установлен, слушает 8443 |
| SSL сертификаты (Let's Encrypt) | ✅ получены 2026-04-12, истекают 2026-07-11 |
| Headscale | ✅ v0.28.0, Docker, слушает 127.0.0.1:8080 |
| Порт 80 в UFW | ❌ закрыт |
| Порт 8443 в UFW | ✅ открыт |

---

## Текущая архитектура (схема)

```
Интернет
    │
    ├─── TCP 443 ──→ Xray (VLESS-Reality)
    │                    └─ VLESS-клиент (ApiNgRPC) ✅
    │                    └─ fallback → (не настроен)
    │
    ├─── UDP 443 ──→ Hysteria2 ✅
    │
    ├─── TCP 993 ──→ MTProto Proxy ✅
    │
    ├─── TCP 8000 ─→ Docker: telegram-helper-lite ✅
    │
    └─── TCP 22542 → SSH ✅

kurein.me         → A → 138.124.71.73  (Cloudflare DNS only)
headscale.kurein.me → A → 138.124.71.73  (Cloudflare DNS only)
```

---

## Что предстоит сделать (план)

### ✅ Шаг 1 — SSL сертификаты (на VPS) — ВЫПОЛНЕНО 2026-04-12

```text
/etc/letsencrypt/live/kurein.me/fullchain.pem
/etc/letsencrypt/live/kurein.me/privkey.pem
Истекают: 2026-07-11 (автообновление через certbot.timer)
```

### ✅ Шаг 2 — Nginx на порту 8443 (на VPS) — ВЫПОЛНЕНО 2026-04-12

```text
/etc/nginx/sites-available/headscale  →  headscale.kurein.me:8443 → 127.0.0.1:8080
Nginx: active (running) since 2026-04-12 15:48:07 UTC
```

### ✅ Шаг 3 — Headscale (Docker, на VPS) — ВЫПОЛНЕНО 2026-04-12

```text
headscale/headscale:latest  v0.28.0
Слушает: 127.0.0.1:8080 (проксируется Nginx на :8443)
Health: curl -sk https://headscale.kurein.me:8443/health → {"status":"pass"}
Конфиг: /etc/headscale/config.yaml
БД:     /var/lib/headscale/db.sqlite
DERP:   https://controlplane.tailscale.com/derpmap/default
```

### ✅ Шаг 4 — Подключение клиентов — ВЫПОЛНЕНО 2026-04-12, обновлено 2026-04-14

```text
Узел 1: mac-kurein      (MacBook)        100.64.0.1  online ✅
Узел 2: debian-fuji     (Debian ноутбук) 100.64.0.2  offline (выключен)
Узел 3: iphone-kurein   (iPhone)         100.64.0.3  online ✅
```

Регистрация iPhone: через Tailscale app → Log in with other →
`https://headscale.kurein.me:8443` → команда `headscale nodes register --key <24-char-key> --user kurein`

Команды управления (на VPS):

```bash
docker exec headscale headscale nodes list | cat
docker exec headscale headscale users list | cat
```

### ✅ Итоговая архитектура — РЕАЛИЗОВАНА 2026-04-12

```
Интернет
    │
    ├─── TCP 443   ──→ Xray (VLESS-Reality) ──→ ApiNgRPC VPN ✅
    │
    ├─── UDP 443   ──→ Hysteria2 ✅
    │
    ├─── TCP 993   ──→ MTProto Proxy ✅
    │
    ├─── TCP 8000  ──→ Telegram Bot (Docker) ✅
    │
    ├─── TCP 8443  ──→ Nginx (SSL) ✅
    │                    └─ headscale.kurein.me:8443
    │                         └─ Headscale v0.28.0 :8080 ✅
    │
    └─── TCP 22542 ──→ SSH ✅

Tailscale mesh (через Headscale):
    mac-kurein     100.64.0.1  ←──→  100.64.0.2  debian-fuji
    iphone-kurein  100.64.0.3  ←──→  (все узлы)
```

## Подключение новых устройств к Headscale mesh

На VPS — сгенерировать новый ключ:

```bash
docker exec headscale headscale preauthkeys create --user 1 --expiration 24h --output json \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])" | cat
```

На новом устройстве (macOS/Linux):

```bash
sudo tailscale up \
  --login-server=https://headscale.kurein.me:8443 \
  --authkey=<ключ> \
  --accept-routes
```

На iOS/Android — в приложении Tailscale указать custom control server:
`https://headscale.kurein.me:8443`

---

## Mac (рабочая машина)

**Путь к проекту TelegramOnly:**
```
/Users/olgazaharova/Project/ProjectPython/TelegramOnly/
```

**`.env.deploy` существует:**
```bash
ls -la "/Users/olgazaharova/Project/ProjectPython/TelegramOnly/.env.deploy"
# -rw-r--r-- Apr 5 19:23  (файл есть)
```

**Подключение к серверу:**
```bash
ssh -p 22542 root@138.124.71.73
```

**Команды диагностики (запускать с Mac):**
```bash
# DNS
nslookup kurein.me
nslookup headscale.kurein.me

# Проверить порты на сервере удалённо
ssh -p 22542 root@138.124.71.73 "ss -tulpn | cat"

# Проверить Headscale (после установки)
curl -sk https://headscale.kurein.me:8443/health
```

---

## NaiveProxy — план (не реализован)

NaiveProxy маскирует трафик под Chrome HTTPS, обходит DPI.
Бот уже поддерживает управление через команды `/naive_*`.

**Проблема:** порт 443 на `138.124.71.73` занят Xray Reality.

**Выбранный вариант:** поднять на поддомене `naive.kurein.me` на порту `8444`.

```text
naive.kurein.me → A → 138.124.71.73 (Cloudflare Proxy OFF)
Caddy слушает: 8444
```

**Что нужно сделать на сервере:**
```bash
# 1. Установить Go и собрать Caddy с NaiveProxy плагином
apt install -y golang-go
go install github.com/caddyserver/xcaddy/cmd/xcaddy@latest
~/go/bin/xcaddy build \
  --with github.com/caddyserver/forwardproxy@caddy2=github.com/klzgrad/forwardproxy@naive \
  --output /usr/local/bin/caddy

# 2. Добавить DNS запись naive.kurein.me в Cloudflare

# 3. Через бота:
# /naive_set_domain naive.kurein.me
# /naive_set_port 8444
# /naive_gen_creds
# /naive_apply
```

**Стелс:** хороший (Chrome TLS fingerprint), но порт 8444 менее стелс чем 443.
Основной VPN остаётся VLESS Reality. NaiveProxy — запасной канал.

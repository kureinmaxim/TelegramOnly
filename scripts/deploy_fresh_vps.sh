#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# 🚀 DEPLOY FRESH VPS — Full mode (1GB RAM optimized)
# ═══════════════════════════════════════════════════════════════
# Target: Debian 12, 1 vCPU, 1GB RAM, 10GB Disk
# Stack:  Docker + TelegramOnly + [VLESS-Reality | NaiveProxy] + Hysteria2 + MTProto
#
# Usage:
#   1. First login to a fresh VPS via the provider default SSH port
#   2. Run: bash deploy_fresh_vps.sh
#   3. After the server stage, use SSH port 22542 for new connections
# ═══════════════════════════════════════════════════════════════

set -e
umask 077

SERVER_IP="${SERVER_IP:-}"
SSH_PORT="22542"
HY2_PORT="443"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

STEP=0
TOTAL=10
next() { STEP=$((STEP+1)); echo -e "\n${CYAN}[$STEP/$TOTAL] $1${NC}"; }

# ── Protocol selection dialog ────────────────────────────────
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  🚀 TelegramOnly VPS Deploy — Фаза 1                 ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BOLD}Что установить на порт 443 (TCP)?${NC}"
echo ""
echo -e "  ${CYAN}[1]${NC} VLESS-Reality (Xray)       — лучший стелс, маскировка под TLS"
echo -e "  ${CYAN}[2]${NC} NaiveProxy (Caddy)          — HTTPS-прокси, нужен домен, Chrome TLS"
echo ""
read -rp "Выбор [1/2] (Enter = 1): " PROTO_CHOICE
PROTO_CHOICE="${PROTO_CHOICE:-1}"

case "$PROTO_CHOICE" in
    2)
        PROTOCOL="naiveproxy"
        echo ""
        echo -e "${YELLOW}NaiveProxy требует домен с DNS A-записью на этот сервер.${NC}"
        echo -e "${YELLOW}Пример: naive.kurein.me → $(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP')${NC}"
        echo ""
        read -rp "Домен для NaiveProxy (например naive.kurein.me): " NAIVE_DOMAIN
        if [[ -z "$NAIVE_DOMAIN" ]]; then
            echo -e "${RED}❌ Домен обязателен для NaiveProxy. Используй вариант 1 (VLESS) без домена.${NC}"
            exit 1
        fi
        NAIVE_PORT="443"
        echo -e "${YELLOW}⚠️  Сборка Caddy с плагином займёт 3-5 минут (Go компиляция).${NC}"
        ;;
    *)
        PROTOCOL="vless"
        ;;
esac

# Detect server IP if not set
if [[ -z "$SERVER_IP" ]]; then
    SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s api.ipify.org 2>/dev/null || echo "YOUR_SERVER_IP")
fi

echo ""
echo -e "${GREEN}  Протокол: $([ "$PROTOCOL" = "vless" ] && echo 'VLESS-Reality' || echo 'NaiveProxy')${NC}"
echo -e "${GREEN}  IP:        $SERVER_IP${NC}"
[ "$PROTOCOL" = "naiveproxy" ] && echo -e "${GREEN}  Домен:     $NAIVE_DOMAIN${NC}"
echo ""

# ── 1. Swap (critical for 1GB RAM) ──────────────────────────
next "Создание swap 1GB..."
if [ ! -f /swapfile ]; then
    fallocate -l 1G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo 'vm.swappiness=10' >> /etc/sysctl.conf
    sysctl vm.swappiness=10
    echo -e "${GREEN}✅ Swap 1GB создан${NC}"
else
    echo "Swap уже существует"
    swapon --show
fi

# ── 2. System update ────────────────────────────────────────
next "Обновление системы..."
apt-get update -qq
apt-get upgrade -y -qq

# ── 3. Install packages ─────────────────────────────────────
next "Установка пакетов..."
PKGS="curl jq openssl ca-certificates git python3 python3-pip ufw fail2ban unattended-upgrades"
if [ "$PROTOCOL" = "naiveproxy" ]; then
    PKGS="$PKGS golang-go"
fi
apt-get install -y -qq $PKGS

# ── 4. Install Docker ───────────────────────────────────────
next "Установка Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo -e "${GREEN}✅ Docker установлен${NC}"
else
    echo "Docker уже установлен: $(docker --version)"
fi

# ── 5. Install protocol on port 443 TCP ─────────────────────
if [ "$PROTOCOL" = "vless" ]; then

    next "Установка Xray-core + VLESS-Reality..."
    if ! command -v xray &> /dev/null; then
        bash -c "$(curl -sL https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
        echo -e "${GREEN}✅ Xray установлен${NC}"
    else
        echo "Xray уже установлен: $(xray version | head -1)"
    fi

    VLESS_PORT="443"
    UUID=$(xray uuid)
    X25519_OUTPUT=$(/usr/local/bin/xray x25519 2>/dev/null)
    PRIVATE_KEY=$(echo "$X25519_OUTPUT" | grep -i "private" | awk -F': ' '{print $2}' | tr -d ' ')
    PUBLIC_KEY=$(echo "$X25519_OUTPUT"  | grep -i "public"  | awk -F': ' '{print $2}' | tr -d ' ')
    SHORT_ID=$(cat /dev/urandom | tr -dc 'a-f0-9' | head -c 8)
    SNI="www.microsoft.com"
    FINGERPRINT="chrome"

    if [ -z "$PRIVATE_KEY" ] || [ -z "$PUBLIC_KEY" ]; then
        echo -e "${YELLOW}⚠️ Повторная генерация ключей...${NC}"
        X25519_OUTPUT=$(/usr/local/bin/xray x25519)
        PRIVATE_KEY=$(echo "$X25519_OUTPUT" | head -1 | awk -F': ' '{print $2}' | tr -d ' ')
        PUBLIC_KEY=$(echo "$X25519_OUTPUT"  | tail -1 | awk -F': ' '{print $2}' | tr -d ' ')
    fi

    tee /usr/local/etc/xray/config.json > /dev/null << EOF
{
  "log": {"loglevel": "warning"},
  "inbounds": [{
    "port": $VLESS_PORT,
    "protocol": "vless",
    "settings": {
      "clients": [{"id": "$UUID", "flow": "xtls-rprx-vision"}],
      "decryption": "none"
    },
    "streamSettings": {
      "network": "tcp",
      "security": "reality",
      "realitySettings": {
        "show": false,
        "dest": "${SNI}:443",
        "xver": 0,
        "serverNames": ["$SNI"],
        "privateKey": "$PRIVATE_KEY",
        "shortIds": ["$SHORT_ID"]
      }
    }
  }],
  "outbounds": [{"protocol": "freedom", "tag": "direct"}]
}
EOF

    xray -test -config /usr/local/etc/xray/config.json
    chmod o+w /usr/local/etc/xray/
    chmod o+w /usr/local/etc/xray/config.json
    systemctl enable xray
    systemctl restart xray
    echo -e "${GREEN}✅ Xray VLESS-Reality запущен на TCP/$VLESS_PORT${NC}"

else  # naiveproxy

    next "Сборка Caddy + NaiveProxy..."
    CADDY_BIN="/usr/local/bin/caddy-naive"
    CADDY_DIR="/etc/caddy-naive"
    SERVICE_NAME="caddy-naive"
    NAIVE_USERNAME="naive-$(tr -dc 'a-z0-9' </dev/urandom | head -c 6)"
    NAIVE_PASSWORD="$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)"
    NAIVE_EMAIL="admin@${NAIVE_DOMAIN}"

    export PATH="$PATH:/root/go/bin"
    if ! command -v xcaddy >/dev/null 2>&1; then
        go install github.com/caddyserver/xcaddy/cmd/xcaddy@latest
    fi

    if [[ ! -x "$CADDY_BIN" ]]; then
        tmpdir="$(mktemp -d)"
        pushd "$tmpdir" >/dev/null
        xcaddy build \
            --output "$CADDY_BIN" \
            --with github.com/caddyserver/forwardproxy=github.com/klzgrad/forwardproxy@naive
        popd >/dev/null
        rm -rf "$tmpdir"
    fi

    mkdir -p "$CADDY_DIR" /var/lib/${SERVICE_NAME}

    tee "${CADDY_DIR}/Caddyfile" > /dev/null << EOF
{
    email ${NAIVE_EMAIL}
    order forward_proxy before file_server
}

${NAIVE_DOMAIN}:${NAIVE_PORT} {
    forward_proxy {
        basic_auth ${NAIVE_USERNAME} ${NAIVE_PASSWORD}
        hide_ip
        hide_via
        probe_resistance
    }
    respond "OK" 200
}
EOF

    tee "/etc/systemd/system/${SERVICE_NAME}.service" > /dev/null << EOF
[Unit]
Description=NaiveProxy via Caddy forwardproxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=${CADDY_BIN} run --config ${CADDY_DIR}/Caddyfile --adapter caddyfile
ExecReload=${CADDY_BIN} reload --config ${CADDY_DIR}/Caddyfile --adapter caddyfile
Restart=on-failure
RestartSec=5
LimitNOFILE=1048576
WorkingDirectory=/var/lib/${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable --now "$SERVICE_NAME"
    sleep 2

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo -e "${GREEN}✅ NaiveProxy (Caddy) запущен на TCP/$NAIVE_PORT${NC}"
    else
        echo -e "${RED}❌ NaiveProxy не запустился!${NC}"
        journalctl -u "$SERVICE_NAME" -n 20
    fi

fi

# ── 6. Install & Configure Hysteria2 ────────────────────────
next "Установка и настройка Hysteria2..."
if ! command -v hysteria &> /dev/null; then
    bash <(curl -fsSL https://get.hy2.sh/)
fi

HY2_PASSWORD=$(openssl rand -base64 16 | tr -d '=+/' | head -c 22)
HY2_CERT_DIR="/etc/hysteria"
mkdir -p "$HY2_CERT_DIR"

if [ ! -f "$HY2_CERT_DIR/server.crt" ]; then
    openssl req -x509 -nodes \
        -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
        -keyout "$HY2_CERT_DIR/server.key" \
        -out   "$HY2_CERT_DIR/server.crt" \
        -subj "/CN=www.microsoft.com" \
        -days 36500 2>/dev/null
fi

tee "$HY2_CERT_DIR/config.yaml" > /dev/null << EOF
listen: :$HY2_PORT

tls:
  cert: $HY2_CERT_DIR/server.crt
  key: $HY2_CERT_DIR/server.key

auth:
  type: password
  password: "$HY2_PASSWORD"

masquerade:
  type: proxy
  proxy:
    url: https://www.microsoft.com
    rewriteHost: true
EOF

tee /etc/systemd/system/hysteria-server.service > /dev/null << 'EOF'
[Unit]
Description=Hysteria2 Server
After=network.target

[Service]
ExecStart=/usr/local/bin/hysteria server -c /etc/hysteria/config.yaml
Restart=on-failure
RestartSec=5
LimitNOFILE=infinity

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable hysteria-server
systemctl restart hysteria-server
sleep 2

if systemctl is-active --quiet hysteria-server; then
    echo -e "${GREEN}✅ Hysteria2 запущен на UDP/$HY2_PORT${NC}"
else
    echo -e "${RED}❌ Hysteria2 не запустился!${NC}"
    journalctl -u hysteria-server -n 10
fi

# ── 7. Firewall + Security ──────────────────────────────────
next "Настройка UFW, Fail2ban..."
ufw default deny incoming
ufw default allow outgoing
ufw allow $SSH_PORT/tcp    # SSH
ufw allow 443/tcp          # VLESS или NaiveProxy
ufw allow 443/udp          # Hysteria2
ufw allow 8000/tcp         # TelegramOnly bot API
ufw allow 993/tcp          # MTProto
[ "$PROTOCOL" = "naiveproxy" ] && ufw allow 80/tcp  # ACME challenge для Let's Encrypt
ufw --force enable

tee /etc/fail2ban/jail.local > /dev/null << EOF
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 3

[sshd]
enabled = true
port = $SSH_PORT
backend = systemd
journalmatch = _SYSTEMD_UNIT=ssh.service
maxretry = 3
bantime = 24h
EOF
systemctl enable fail2ban
systemctl restart fail2ban

echo 'APT::Periodic::Update-Package-Lists "1";' | tee    /etc/apt/apt.conf.d/20auto-upgrades > /dev/null
echo 'APT::Periodic::Unattended-Upgrade "1";'   | tee -a /etc/apt/apt.conf.d/20auto-upgrades > /dev/null
echo -e "${GREEN}✅ UFW, Fail2ban настроены${NC}"

# ── 8. SSH port ──────────────────────────────────────────────
next "Смена SSH порта на $SSH_PORT..."
if ! grep -q "Port $SSH_PORT" /etc/ssh/sshd_config; then
    sed -i "s/^#*Port .*/Port $SSH_PORT/" /etc/ssh/sshd_config
    systemctl restart ssh || systemctl restart sshd
    echo -e "${GREEN}✅ SSH переведён на порт $SSH_PORT${NC}"
else
    echo "SSH уже на порту $SSH_PORT"
fi

# ── 9. Prepare /opt/TelegramSimple ──────────────────────────
next "Подготовка /opt/TelegramSimple..."
PROJECT_DIR="/opt/TelegramSimple"
mkdir -p $PROJECT_DIR

API_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
HMAC_KEY=$(openssl rand -hex 32)
ENC_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# Protocol-specific config files
if [ "$PROTOCOL" = "vless" ]; then
    cat > $PROJECT_DIR/vless_config.json << EOF
{
  "enabled": true,
  "server": "$SERVER_IP",
  "port": $VLESS_PORT,
  "uuid": "$UUID",
  "public_key": "$PUBLIC_KEY",
  "private_key": "$PRIVATE_KEY",
  "short_id": "$SHORT_ID",
  "sni": "$SNI",
  "fingerprint": "$FINGERPRINT",
  "flow": "xtls-rprx-vision"
}
EOF
    echo '{}' > $PROJECT_DIR/naiveproxy_config.json
else
    echo '{}' > $PROJECT_DIR/vless_config.json
    cat > $PROJECT_DIR/naiveproxy_config.json << EOF
{
  "enabled": true,
  "domain": "$NAIVE_DOMAIN",
  "server": "$SERVER_IP",
  "port": $NAIVE_PORT,
  "username": "$NAIVE_USERNAME",
  "password": "$NAIVE_PASSWORD",
  "scheme": "https",
  "local_socks_port": 10808,
  "padding": true,
  "caddyfile_path": "/etc/caddy-naive/Caddyfile",
  "service_name": "caddy-naive"
}
EOF
fi

cat > $PROJECT_DIR/app_keys.json << EOF
{
  "app_keys": {
    "apiai-v3": {
      "api_key": "$API_KEY",
      "encryption_key": "$ENC_KEY"
    }
  },
  "default": {
    "api_key": "$API_KEY",
    "encryption_key": "$ENC_KEY"
  }
}
EOF

echo '{}' > $PROJECT_DIR/users.json
echo '{}' > $PROJECT_DIR/hysteria2_config.json
echo '{}' > $PROJECT_DIR/mtproto_config.json
echo '{}' > $PROJECT_DIR/headscale_config.json
touch $PROJECT_DIR/bot.log

chmod 600 $PROJECT_DIR/app_keys.json $PROJECT_DIR/users.json \
          $PROJECT_DIR/vless_config.json $PROJECT_DIR/naiveproxy_config.json \
          $PROJECT_DIR/hysteria2_config.json $PROJECT_DIR/mtproto_config.json \
          $PROJECT_DIR/mtproto_config.json $PROJECT_DIR/headscale_config.json
chmod 640 $PROJECT_DIR/bot.log

echo -e "${GREEN}✅ Директория и файлы данных готовы${NC}"

# ── 10. Summary & Credentials ───────────────────────────────
next "Готово! Сводка:"

if [ "$PROTOCOL" = "vless" ]; then
    PROTO_LINK="vless://${UUID}@${SERVER_IP}:${VLESS_PORT}?encryption=none&flow=xtls-rprx-vision&security=reality&sni=${SNI}&fp=${FINGERPRINT}&pbk=${PUBLIC_KEY}&sid=${SHORT_ID}&type=tcp#VPS-Reality"
    PROTO_SECTION="━━━ VLESS-Reality (TCP/443) ━━━━━━━━━━━━━━━━━━━━━━━━━
UUID:        $UUID
Public Key:  $PUBLIC_KEY
Private Key: $PRIVATE_KEY
Short ID:    $SHORT_ID
SNI:         $SNI
Fingerprint: $FINGERPRINT

VLESS Link:
$PROTO_LINK"
else
    PROTO_LINK="naive+https://${NAIVE_USERNAME}:${NAIVE_PASSWORD}@${NAIVE_DOMAIN}:${NAIVE_PORT}#TelegramOnly-NaiveProxy"
    PROTO_SECTION="━━━ NaiveProxy (TCP/443) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Domain:   $NAIVE_DOMAIN
Username: $NAIVE_USERNAME
Password: $NAIVE_PASSWORD
Service:  caddy-naive

Client URI:
$PROTO_LINK"
fi

HY2_LINK="hy2://${HY2_PASSWORD}@${SERVER_IP}:${HY2_PORT}/?insecure=1#Hysteria2"

cat > $PROJECT_DIR/CREDENTIALS.txt << EOF
═══════════════════════════════════════════════════════════════
  🛡️  VPS Deploy Credentials — $(date +%Y-%m-%d)
  📍  Server: $SERVER_IP
  🔐  Protocol on 443: $([ "$PROTOCOL" = "vless" ] && echo 'VLESS-Reality' || echo 'NaiveProxy')
═══════════════════════════════════════════════════════════════

$PROTO_SECTION

━━━ Hysteria2 (UDP/443) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Password: $HY2_PASSWORD

Hysteria2 URI:
$HY2_LINK

━━━ API Security ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API Key:        $API_KEY
HMAC Key:       $HMAC_KEY
Encryption Key: $ENC_KEY

━━━ Следующий шаг ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
С локального Mac выполните загрузку проекта и docker compose up.
Инструкция: DEPLOY_GUIDE.md → Фаза 2.
═══════════════════════════════════════════════════════════════
EOF

chmod 600 $PROJECT_DIR/CREDENTIALS.txt

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ Фаза 1 завершена!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""

if [ "$PROTOCOL" = "vless" ]; then
    echo -e "  🛡️  VLESS-Reality: TCP/443 — $(systemctl is-active xray)"
else
    echo -e "  🔐  NaiveProxy:    TCP/443 — $(systemctl is-active caddy-naive)"
fi
echo -e "  ⚡  Hysteria2:     UDP/443 — $(systemctl is-active hysteria-server)"
echo -e "  🔥  UFW:           $(ufw status | head -1)"
echo -e "  🛑  Fail2ban:      $(systemctl is-active fail2ban)"
echo -e "  💾  Swap:          $(swapon --show --noheadings | awk '{print $3}')"
echo -e "  📁  Data dir:      $PROJECT_DIR"
echo ""
echo -e "${YELLOW}📋 Credentials сохранены в: $PROJECT_DIR/CREDENTIALS.txt${NC}"
echo -e "${YELLOW}   cat $PROJECT_DIR/CREDENTIALS.txt — просмотреть${NC}"
echo -e "${YELLOW}   rm $PROJECT_DIR/CREDENTIALS.txt  — удалить после копирования${NC}"
echo ""
echo -e "${CYAN}━━━ Следующий шаг (с Mac): ━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  cd /Users/olgazaharova/Project/ProjectPython/TelegramOnly"
echo "  cp example.env .env.deploy && nano .env.deploy"
echo ""
echo "  rsync -avz -e 'ssh -p $SSH_PORT' \\"
echo "    --exclude 'venv' --exclude '__pycache__' --exclude '.env' \\"
echo "    --exclude 'app_keys.json' --exclude 'users.json' --exclude '*.log' \\"
echo "    --exclude '.git' ./ root@$SERVER_IP:$PROJECT_DIR/"
echo ""
echo "  scp -P $SSH_PORT .env.deploy root@$SERVER_IP:$PROJECT_DIR/.env"
echo "  ssh -p $SSH_PORT root@$SERVER_IP 'cd $PROJECT_DIR && docker compose up -d telegram-helper'"

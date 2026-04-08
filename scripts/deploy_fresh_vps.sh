#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# 🚀 DEPLOY FRESH VPS — Full mode (1GB RAM optimized)
# ═══════════════════════════════════════════════════════════════
# Target: Debian 12, 1 vCPU, 1GB RAM, 10GB Disk
# Stack:  Docker + TelegramSimple + Xray + Hysteria2 + MTProto
# No:     Dockhand, Headscale
#
# Usage:
#   1. First login to a fresh VPS can be via the provider default SSH port
#   2. Run this script: bash deploy_fresh_vps.sh
#   3. After the server stage, use SSH port 22542 for new connections
#   OR copy-paste sections manually
# ═══════════════════════════════════════════════════════════════

set -e
umask 077

SERVER_IP="${SERVER_IP:-YOUR_SERVER_IP}"
SSH_PORT="22542"        # Change if custom
VLESS_PORT="443"        # TCP
HY2_PORT="443"          # UDP (no conflict with VLESS TCP)

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

STEP=0
TOTAL=10
next() { STEP=$((STEP+1)); echo -e "\n${CYAN}[$STEP/$TOTAL] $1${NC}"; }

echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  🚀 Deploy: VLESS + Hysteria2 + TelegramSimple Bot   ${NC}"
echo -e "${GREEN}  📍 Server: $SERVER_IP                                ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"

# ── 1. Swap (critical for 1GB RAM) ──────────────────────────
next "Создание swap 1GB..."
if [ ! -f /swapfile ]; then
    fallocate -l 1G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    # Optimize swap for low-RAM server
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
apt-get install -y -qq \
    curl jq openssl ca-certificates git \
    python3 python3-pip \
    ufw fail2ban unattended-upgrades

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

# ── 5. Install Xray ─────────────────────────────────────────
next "Установка Xray-core..."
if ! command -v xray &> /dev/null; then
    bash -c "$(curl -sL https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
    echo -e "${GREEN}✅ Xray установлен${NC}"
else
    echo "Xray уже установлен: $(xray version | head -1)"
fi

# ── 6. Configure VLESS-Reality ──────────────────────────────
next "Генерация ключей VLESS и настройка Xray..."
UUID=$(xray uuid)
X25519_OUTPUT=$(/usr/local/bin/xray x25519 2>/dev/null)
PRIVATE_KEY=$(echo "$X25519_OUTPUT" | grep -i "private" | awk -F': ' '{print $2}' | tr -d ' ')
PUBLIC_KEY=$(echo "$X25519_OUTPUT" | grep -i "public" | awk -F': ' '{print $2}' | tr -d ' ')
SHORT_ID=$(cat /dev/urandom | tr -dc 'a-f0-9' | head -c 8)
SNI="www.microsoft.com"
FINGERPRINT="chrome"

if [ -z "$PRIVATE_KEY" ] || [ -z "$PUBLIC_KEY" ]; then
    echo -e "${YELLOW}⚠️ Повторная генерация...${NC}"
    X25519_OUTPUT=$(/usr/local/bin/xray x25519)
    PRIVATE_KEY=$(echo "$X25519_OUTPUT" | head -1 | awk -F': ' '{print $2}' | tr -d ' ')
    PUBLIC_KEY=$(echo "$X25519_OUTPUT" | tail -1 | awk -F': ' '{print $2}' | tr -d ' ')
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
systemctl enable xray
systemctl restart xray
echo -e "${GREEN}✅ Xray запущен на TCP/$VLESS_PORT${NC}"

# ── 7. Install & Configure Hysteria2 ────────────────────────
next "Установка и настройка Hysteria2..."
if ! command -v hysteria &> /dev/null; then
    bash <(curl -fsSL https://get.hy2.sh/)
fi

HY2_PASSWORD=$(openssl rand -base64 16 | tr -d '=+/' | head -c 22)
HY2_CERT_DIR="/etc/hysteria"
mkdir -p "$HY2_CERT_DIR"

# Self-signed TLS cert
if [ ! -f "$HY2_CERT_DIR/server.crt" ]; then
    openssl req -x509 -nodes \
        -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
        -keyout "$HY2_CERT_DIR/server.key" \
        -out "$HY2_CERT_DIR/server.crt" \
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

# Systemd service
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

# ── 8. Firewall + Security ──────────────────────────────────
next "Настройка UFW, Fail2ban..."
ufw default deny incoming
ufw default allow outgoing
ufw allow $SSH_PORT/tcp       # SSH
ufw allow $VLESS_PORT/tcp     # VLESS (TCP)
ufw allow $HY2_PORT/udp       # Hysteria2 (UDP)
ufw allow 8000/tcp             # API (TelegramSimple)
ufw allow 993/tcp              # MTProto (будет позже)
ufw --force enable

# Fail2ban
tee /etc/fail2ban/jail.local > /dev/null << EOF
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 3

[sshd]
enabled = true
port = $SSH_PORT
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 24h
EOF
systemctl enable fail2ban
systemctl restart fail2ban

# Auto security updates
echo 'APT::Periodic::Update-Package-Lists "1";' | tee /etc/apt/apt.conf.d/20auto-upgrades > /dev/null
echo 'APT::Periodic::Unattended-Upgrade "1";' | tee -a /etc/apt/apt.conf.d/20auto-upgrades > /dev/null

echo -e "${GREEN}✅ UFW, Fail2ban настроены${NC}"

# ── 9. Prepare TelegramSimple directory ─────────────────────
next "Подготовка /opt/TelegramSimple..."
PROJECT_DIR="/opt/TelegramSimple"
mkdir -p $PROJECT_DIR

# Generate security keys
API_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
HMAC_KEY=$(openssl rand -hex 32)
ENC_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# Create data files (these are NOT in git)
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
          $PROJECT_DIR/vless_config.json $PROJECT_DIR/hysteria2_config.json \
          $PROJECT_DIR/mtproto_config.json $PROJECT_DIR/headscale_config.json
chmod 640 $PROJECT_DIR/bot.log

echo -e "${GREEN}✅ Директория и файлы данных готовы${NC}"

# ── 10. Summary ─────────────────────────────────────────────
next "Готово! Сводка:"

VLESS_LINK="vless://${UUID}@${SERVER_IP}:${VLESS_PORT}?encryption=none&flow=xtls-rprx-vision&security=reality&sni=${SNI}&fp=${FINGERPRINT}&pbk=${PUBLIC_KEY}&sid=${SHORT_ID}&type=tcp#VPS-Reality"
HY2_LINK="hy2://${HY2_PASSWORD}@${SERVER_IP}:${HY2_PORT}/?insecure=1#Hysteria2"

# Save credentials
cat > $PROJECT_DIR/CREDENTIALS.txt << EOF
═══════════════════════════════════════════════════════════════
  🛡️  VPS Deploy Credentials — $(date +%Y-%m-%d)
  📍  Server: $SERVER_IP
═══════════════════════════════════════════════════════════════

━━━ VLESS-Reality (TCP/$VLESS_PORT) ━━━━━━━━━━━━━━━━━━━━━━━━━
UUID:        $UUID
Public Key:  $PUBLIC_KEY
Private Key: $PRIVATE_KEY
Short ID:    $SHORT_ID
SNI:         $SNI
Fingerprint: $FINGERPRINT

VLESS Link:
$VLESS_LINK

━━━ Hysteria2 (UDP/$HY2_PORT) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Password:    $HY2_PASSWORD

Hysteria2 URI:
$HY2_LINK

━━━ API Security ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API Key:        $API_KEY
HMAC Key:       $HMAC_KEY
Encryption Key: $ENC_KEY

━━━ Следующий шаг ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
С локального ПК выполните загрузку проекта и docker compose up.
Инструкция: Phase 2 в deploy guide.
═══════════════════════════════════════════════════════════════
EOF

chmod 600 $PROJECT_DIR/CREDENTIALS.txt

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ Фаза 1 завершена!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "Сводка:"
echo -e "  🛡️  VLESS:     TCP/$VLESS_PORT — $(systemctl is-active xray)"
echo -e "  ⚡ Hysteria2: UDP/$HY2_PORT — $(systemctl is-active hysteria-server)"
echo -e "  🔥 UFW:       $(ufw status | head -1)"
echo -e "  🛑 Fail2ban:  $(systemctl is-active fail2ban)"
echo -e "  💾 Swap:       $(swapon --show --noheadings | awk '{print $3}')"
echo -e "  📁 Data dir:   $PROJECT_DIR"
echo ""
echo -e "${YELLOW}📋 Credentials сохранены в: $PROJECT_DIR/CREDENTIALS.txt${NC}"
echo -e "${YELLOW}   Скопируйте их себе и удалите файл!${NC}"
echo ""
echo -e "${CYAN}━━━ Следующий шаг (с локального ПК): ━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  # 1. Заполните .env:"
echo "  cd /path/to/TelegramOnly"
echo "  cp example.env .env.deploy"
echo "  nano .env.deploy  # BOT_TOKEN, ADMIN_ID, keys from CREDENTIALS.txt"
echo ""
echo "  # 2. Загрузите код на сервер:"
echo "  rsync -avz -e 'ssh -p $SSH_PORT' \\"
echo "    --exclude 'venv' --exclude '__pycache__' --exclude '.env' \\"
echo "    --exclude 'app_keys.json' --exclude 'users.json' --exclude '*.log' \\"
echo "    --exclude '.git' --exclude 'docs/' \\"
echo "    ./ root@$SERVER_IP:$PROJECT_DIR/"
echo ""
echo "  # 3. Загрузите .env:"
echo "  scp -P $SSH_PORT .env.deploy root@$SERVER_IP:$PROJECT_DIR/.env"
echo ""
echo "  # 4. Запустите Docker (на сервере):"
echo "  ssh -p $SSH_PORT root@$SERVER_IP 'cd $PROJECT_DIR && docker compose up -d telegram-helper'"
echo ""
echo "  Просмотрите файл локально на сервере: sudo less $PROJECT_DIR/CREDENTIALS.txt"

#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER="${SUDO_USER:-$(id -un)}"
APP_GROUP="$(id -gn "${APP_USER}")"
SERVICE_NAME="${SERVICE_NAME:-telegramonly}"
ENV_FILE="${APP_DIR}/.env"
VENV_DIR="${APP_DIR}/venv"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This installer is intended for Linux VPS hosts."
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "Only apt-based distributions are supported by this bootstrap script."
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  python3-dev \
  build-essential \
  libffi-dev \
  libssl-dev \
  git \
  curl

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/pip" install --upgrade pip setuptools wheel
"${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt"

if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${APP_DIR}/example.env" "${ENV_FILE}"
  chown "${APP_USER}:${APP_GROUP}" "${ENV_FILE}"
fi

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=TelegramOnly bot and API service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_GROUP}
WorkingDirectory=${APP_DIR}
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_DIR}/bin/python3 ${APP_DIR}/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"

if grep -qE '=(your_|sk-|YOUR_SERVER_IP|123456789)' "${ENV_FILE}"; then
  echo
  echo "Bootstrap is complete, but ${ENV_FILE} still contains placeholder values."
  echo "Edit ${ENV_FILE}, then run:"
  echo "  sudo systemctl restart ${SERVICE_NAME}"
  echo "  sudo systemctl status ${SERVICE_NAME} | cat"
  exit 0
fi

systemctl restart "${SERVICE_NAME}"
systemctl status "${SERVICE_NAME}" --no-pager | cat

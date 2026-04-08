# TelegramOnly VPS Install

This guide installs `TelegramOnly` as a standalone service on a fresh Linux VPS.

## 1. Clone The Repository

```bash
git clone <your-repo-url> TelegramOnly
cd TelegramOnly
```

## 2. Run Bootstrap Script

```bash
sudo bash scripts/install_telegramonly_vps.sh
```

What the script does:

- installs base system packages for Python runtime
- creates `venv/`
- installs `requirements.txt`
- creates `.env` from `example.env` if needed
- writes `telegramonly.service`
- enables the systemd service

## 3. Fill `.env`

At minimum, configure:

- `BOT_TOKEN`
- `ADMIN_USER_IDS`
- `API_SECRET_KEY`
- `HMAC_SECRET`
- `API_URL`
- AI keys if you use AI features

You can edit it with:

```bash
nano .env
```

## 4. Start The Service

```bash
sudo systemctl restart telegramonly
sudo systemctl status telegramonly | cat
```

Logs:

```bash
sudo journalctl -u telegramonly -f | cat
```

## 5. Enable Server Transports

This repository already contains helper scripts for the transport layer:

- `scripts/setup_vless_server.sh`
- `scripts/install_hysteria2.sh`
- `scripts/install_mtproto.sh`

Use only the transports you actually need on that VPS.

## 6. Export For ApiXgRPC

After the server is configured:

1. Open the bot
2. Run `/tgcapsule_export`
3. Choose one of the TelegramOnly export targets
4. Import the generated file into `ApiXgRPC`

## 7. Validation

Useful checks:

```bash
source venv/bin/activate && python3 main.py --api-only
source venv/bin/activate && python3 tests/test_api.py
```

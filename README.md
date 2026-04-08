# TelegramOnly

`TelegramOnly` is a standalone deployable fork of `TelegramSimple` focused on
Telegram-first access and `ApiXgRPC` client interoperability.

This repository now contains two layers in one place:

- a working Python runtime for bot + API + transport management;
- the `apix-profile v2` contract and fixtures for Telegram-only routing.

`TelegramSimple` can stay your stable legacy project, while `TelegramOnly` can be
installed on a fresh VPS as a separate server with the new export flow.

## What's New

- Telegram-only export profiles via `telegram_capsule_export.py`
- bot command `/tgcapsule_export`
- `apix-profile v2` with `routing_policy`
- canonical fixtures in `fixtures/`
- schema in `schema/apix-profile-v2.schema.json`

## Quick Start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp example.env .env
python3 main.py
```

Modes:

- `python3 main.py` - bot + API
- `python3 main.py --api-only` - API only
- `python3 main.py --bot-only` - bot only

## Fresh VPS Install

Fast path:

```bash
git clone <your-repo-url> TelegramOnly
cd TelegramOnly
sudo bash scripts/install_telegramonly_vps.sh
```

Then:

1. Edit `.env`
2. Configure transports you need (`VLESS-Reality`, `Hysteria2`, `MTProto`) using the bundled scripts and bot/admin commands
3. Start or restart the service:

```bash
sudo systemctl restart telegramonly
sudo systemctl status telegramonly | cat
```

Full deployment notes are in `INSTALL_VPS.md`.

## ApiXgRPC Flow

Recommended client flow:

1. Configure server-side transport in `TelegramOnly`
2. Export Telegram-only profile from the bot with `/tgcapsule_export`
3. Import the generated `apix-profile v2` into `ApiXgRPC`
4. Select the imported profile in `ApiXgRPC`
5. Use `ApiXgRPC` as the universal desktop client

## Important Files

- `main.py` - runtime entry point
- `handlers.py` - bot commands and callback menu
- `telegram_capsule_export.py` - Telegram-only export builders
- `schema/apix-profile-v2.schema.json` - profile schema
- `fixtures/*.apix.json` - reference exports
- `INSTALL_VPS.md` - deployment guide
- `ARCHITECTURE.md` - project architecture, stack, current features, and roadmap

## Compatibility

- `apix-profile v1` remains supported by `ApiXgRPC`
- `apix-profile v2` adds `routing_policy`
- `TelegramSimple` can remain untouched and be deployed separately

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

Legacy-compatible flow:

1. Keep an existing `TelegramSimple`-style server layout such as `/opt/TelegramSimple`
2. Continue reading the standard legacy Reality artifact `vless_config.json`
3. Continue using legacy bot/client exports such as `/vless_export`
4. Let `TelegramOnly` act as the new primary project without forcing an immediate server migration

## Important Files

- `main.py` - runtime entry point
- `handlers.py` - bot commands and callback menu
- `telegram_capsule_export.py` - Telegram-only export builders
- `schema/apix-profile-v2.schema.json` - profile schema
- `fixtures/*.apix.json` - reference exports
- `INSTALL_VPS.md` - deployment guide
- `SETUP.md` - обновление кода на уже настроенном VPS (Docker); **новые сервера:** `/opt/TelegramOnly` + имя `TelegramOnly`; **legacy:** `/opt/TelegramSimple` — путь в `rsync` и `docker compose` должен быть один и тот же
- `ARCHITECTURE.md` - project architecture, stack, current features, and roadmap
- `SECURITY.md` - security policy and reporting guidance
- `LICENSE` - MIT license for the public repository

## Compatibility

- `apix-profile v1` remains supported by `ApiXgRPC`
- `apix-profile v2` adds `routing_policy`
- `TelegramSimple` can remain untouched and be deployed separately
- `TelegramOnly` is the primary forward path, but it must keep reading the legacy Reality/VLESS contract used by `TelegramSimple`
- the legacy fallback contract is the classic `vless_config.json` fields:
  - `server`
  - `port`
  - `uuid`
  - `public_key`
  - `short_id`
  - `sni`
  - `fingerprint`
  - `flow`
- if those fields are present, old servers do not need to be recreated before a client can keep working

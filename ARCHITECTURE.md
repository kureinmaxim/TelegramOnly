# TelegramOnly Architecture

`TelegramOnly` is a standalone deployable server focused on Telegram-first access,
transport management, and interoperability with the `ApiXgRPC` desktop client.

It is intentionally positioned as a newer, more experimental sibling of
`TelegramSimple`: the old project can remain stable and unchanged, while
`TelegramOnly` evolves as the cleaner public server repository.

## Goals

- provide a single VPS-hosted runtime for Telegram bot control, REST API access, and transport management
- support Telegram-oriented routing/export flows without breaking legacy transport usage
- work as a server-side companion for `ApiXgRPC`
- keep deployment simple enough for fresh VPS installation
- remain practical for operators who need both automation and manual control

## High-Level Architecture

The project combines several layers in one Python codebase:

1. Control plane
   Telegram bot commands, admin CLI commands, helper scripts, and REST admin endpoints.
2. Application API
   FastAPI endpoints for AI queries, encrypted requests, health checks, admin commands, and diagnostics.
3. Security layer
   API key verification, app-level access control, timestamp/nonce/signature checks, encrypted payload handling, and rate limiting.
4. Transport management layer
   Managers for `VLESS-Reality`, `Hysteria2`, `MTProto`, and optional `Headscale`.
5. Export/interoperability layer
   Builders for `apix-profile v2`, `sing-box`, and `Clash Meta` Telegram-only exports.
6. Persistence layer
   File-based JSON configs and environment-based runtime configuration.

## Runtime Modes

`main.py` starts the project in one of three modes:

- `bot + API`
- `api-only`
- `bot-only`

This allows the same repository to be used both as a normal Telegram-operated server
and as a headless API service behind systemd or Docker.

## Main Components

### Entry Point

`main.py` is the runtime entry point. It:

- loads `.env`
- configures logging
- initializes shared config
- starts the Telegram bot
- starts the FastAPI server with `uvicorn`

### Telegram Bot

`bot.py` wires the Telegram bot using `python-telegram-bot`.

The bot is the main operator interface for:

- server inspection
- API/security key management
- AI provider selection
- transport configuration
- client export flows
- TelegramOnly export flow via `/tgcapsule_export`

`handlers.py` contains the operational logic behind those commands and callback menus.

### REST API

`api.py` provides the HTTP layer using `FastAPI`.

Main endpoint groups:

- health and service info
- prompt templates
- plain AI requests
- encrypted AI requests
- admin command execution
- combined config/status endpoints
- selected transport-specific helpers

This API is designed for programmatic integrations and for compatibility with local
or remote clients that do not want to depend directly on Telegram bot control.

### Security and Encryption

The security model is implemented primarily in:

- `security.py`
- `encryption.py`
- `app_keys.py`

Core mechanisms:

- default and per-app API keys
- encryption keys for secure message exchange
- HMAC/signature-based verification
- timestamp and nonce validation
- request logging and rate limiting
- encrypted request/response support for client integrations

Recent public hardening work also makes the repository more secure by default:

- full secret reveal is disabled by default in Telegram/admin helper flows
- server-only secrets such as transport private keys are not exported into client-facing artifacts
- deployment scripts reduce accidental secret leakage in stdout and generated files

## Transport Layer

The transport layer is the main networking value of the project.

### VLESS-Reality

Implemented through:

- `vless_manager.py`
- Xray-related install/apply/start helpers

Use cases:

- main stealth transport
- client QR and link generation
- export to client configs
- export to TelegramOnly profile formats

### Hysteria2

Implemented through:

- `hysteria2_manager.py`

Use cases:

- QUIC/UDP-based alternative transport
- better behavior on some lossy or mobile networks
- optional secondary candidate in Telegram-only export flows

### MTProto

Implemented through:

- `mtproto_manager.py`
- host-side install/sync scripts

Use cases:

- Telegram-native proxy compatibility
- operational fallback path
- scenarios where Telegram client simplicity is more important than universal routing

In the current architecture, MTProto remains important as a compatibility and fallback
tool, but not as the primary long-term stealth transport.

### Headscale

Implemented through:

- `headscale_manager.py`

This is optional infrastructure for operators who also want self-hosted mesh/VPN style
capabilities in the same operational toolbox.

## Export and Interoperability Layer

The most distinctive TelegramOnly-specific layer is:

- `telegram_capsule_export.py`

This module adds policy-aware exports without replacing legacy exports.

It currently supports:

- `apix-profile v2`
- `sing-box`
- `Clash Meta`

The `apix-profile v2` contract is defined in:

- `schema/apix-profile-v2.schema.json`

Reference fixtures live in:

- `fixtures/`

The key architectural idea is that TelegramOnly does not invent a new custom client
protocol. Instead, it exports known transport parameters plus a routing policy that
tells the client how to route Telegram traffic.

## TelegramOnly Routing Model

The central new concept is `routing_policy` with `mode = telegram_only`.

This allows clients such as `ApiXgRPC` to:

- proxy Telegram traffic through selected transports
- keep non-Telegram traffic direct
- prefer one transport and fall back to another
- preserve backward compatibility with older profile formats

Typical policy fields:

- `transport_candidates`
- `client_targets`
- `fallback_transport`
- `fail_mode`
- `telegram_domains`

This keeps the server export logic simple and moves routing execution to capable clients.

## Configuration and Persistence

The project mostly uses file-backed configuration and secrets:

- `.env`
- `users.json`
- `app_keys.json`
- `vless_config.json`
- `hysteria2_config.json`
- `mtproto_config.json`
- `headscale_config.json`

This makes the repository easy to operate on a small VPS, easy to back up, and easy to
inspect manually when debugging deployments.

## Deployment Model

TelegramOnly is designed for pragmatic VPS deployment.

The repository includes:

- direct Python/venv startup
- systemd-oriented bootstrap flow
- helper scripts for transport installation
- deployment notes for fresh Linux VPS instances

Primary deployment documentation:

- `README.md`
- `INSTALL_VPS.md`
- `scripts/install_telegramonly_vps.sh`

## What Is Implemented Today

Current implemented scope includes:

- working Python runtime for Telegram bot and REST API
- admin and operator command surface in Telegram
- AI provider integration with Anthropic/OpenAI-oriented flows
- file-based key and config management
- `VLESS-Reality` operational management
- `Hysteria2` operational management
- `MTProto` management and host-side synchronization helpers
- Telegram-only exports via `/tgcapsule_export`
- `apix-profile v2` schema and fixtures
- interoperability path for `ApiXgRPC` imports
- fresh VPS bootstrap and service installation
- public-repo hardening for secrets and deployment artifacts

## Technology Stack

Main technologies used in this repository:

- Python 3
- FastAPI
- Uvicorn
- python-telegram-bot
- python-dotenv
- JSON file persistence
- systemd
- Xray for `VLESS-Reality`
- Hysteria2 server tooling
- MTProto host-side service tooling

Supporting integration targets:

- `ApiXgRPC`
- `sing-box`
- `Clash Meta`

## Design Trade-Offs

This project intentionally chooses:

- operational simplicity over heavy platform abstraction
- explicit scripts over hidden automation
- file-based state over a database
- compatibility with existing operator workflows over a full rewrite

That makes it easier to deploy on small servers and easier to maintain manually, but it
also means the codebase is still partly evolutionary and not yet fully modularized.

## Future Plans

Planned or likely next steps:

- continue improving the TelegramOnly export UX and operator guidance
- keep strengthening secure-by-default behavior around secrets and remote admin actions
- expand compatibility testing between `TelegramOnly`, `TelegramSimple`, and `ApiXgRPC`
- improve validation and health checks for multi-transport deployments
- make client export artifacts more standardized and easier to consume automatically
- further separate server-only secrets from client-facing exports and docs
- refine mobile-network resilience strategy around `Reality`, `Hysteria2`, and fallback behavior
- gradually reduce legacy coupling inherited from `TelegramSimple`

## Long-Term Direction

Long term, `TelegramOnly` can serve as:

- a clean public server repository
- a Telegram-first transport/export lab
- the reference server-side companion for `ApiXgRPC`

while `TelegramSimple` remains available as the older stable branch of the overall idea.

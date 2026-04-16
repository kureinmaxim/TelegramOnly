# -*- coding: utf-8 -*-
"""
TelegramOnly export helpers for TelegramSimple.

This module builds policy-aware exports for Telegram-only routing on top of
existing Reality and Hysteria2 transports without changing legacy exports.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

import hysteria2_manager
import vless_manager
import tuic_manager
import anytls_manager
import xhttp_manager


ROUTING_MODE_TELEGRAM_ONLY = "telegram_only"
FAIL_MODE_FAIL_OPEN = "fail_open"
TELEGRAM_CLIENT_TARGETS = ["apixgrpc", "sing-box", "clash-meta"]
TELEGRAM_DOMAINS = [
    "telegram.org",
    "t.me",
    "telegram.me",
    "telegra.ph",
    "tdesktop.com",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _telegram_policy(
    transport_candidates: List[str],
    fallback_transport: str = "mtproto",
) -> Dict:
    return {
        "enabled": True,
        "mode": ROUTING_MODE_TELEGRAM_ONLY,
        "transport_candidates": transport_candidates,
        "client_targets": TELEGRAM_CLIENT_TARGETS,
        "fallback_transport": fallback_transport,
        "fail_mode": FAIL_MODE_FAIL_OPEN,
        "telegram_domains": list(TELEGRAM_DOMAINS),
        "telegram_ip_cidrs": [],
    }


def _normalize_reality_config(client_name: Optional[str] = None) -> Dict:
    config = vless_manager.get_vless_config(include_secrets=True)
    if client_name:
        for client in config.get("clients", []):
            if client.get("name") == client_name:
                config = dict(config)
                config["uuid"] = client.get("uuid", config.get("uuid", ""))
                break
    return config


def _normalize_hysteria2_config(client_name: Optional[str] = None) -> Dict:
    config = hysteria2_manager.get_config(include_secrets=True)
    if client_name:
        for client in config.get("clients", []):
            if client.get("name") == client_name:
                config = dict(config)
                # Userpass format: name:password (sing-box expects this in password field)
                config["password"] = f"{client_name}:{client.get('password', '')}"
                break
    return config


def export_apix_profile_v2(strategy: str, client_name: Optional[str] = None) -> Dict:
    strategy = (strategy or "").strip().lower()
    reality_cfg = _normalize_reality_config(client_name)
    hy2_cfg = _normalize_hysteria2_config(client_name)

    if strategy not in {"reality", "hysteria2", "auto"}:
        raise ValueError(f"Unsupported TelegramOnly strategy: {strategy}")

    if strategy == "hysteria2":
        protocol_type = "hysteria2"
        server_host = hy2_cfg.get("server", "")
        server_port = hy2_cfg.get("port", 443)
        reality_export = None
        hy2_export = {
            "enabled": True,
            "password": hy2_cfg.get("password", ""),
            "sni": hy2_cfg.get("sni", "") or "www.microsoft.com",
            "insecure": hy2_cfg.get("insecure", False),
            "up_mbps": hy2_cfg.get("up_mbps", 0),
            "down_mbps": hy2_cfg.get("down_mbps", 0),
            "obfs_type": hy2_cfg.get("obfs_type", ""),
            "obfs_password": hy2_cfg.get("obfs_password", ""),
        }
        candidates = ["hysteria2"]
        color = "#10b981"
        profile_label = "Hysteria2"
    else:
        protocol_type = "reality"
        server_host = reality_cfg.get("server", "")
        server_port = reality_cfg.get("port", 443)
        reality_export = {
            "enabled": True,
            "uuid": reality_cfg.get("uuid", ""),
            "public_key": reality_cfg.get("public_key", ""),
            "short_id": reality_cfg.get("short_id", ""),
            "sni": reality_cfg.get("sni", "www.microsoft.com"),
            "fingerprint": reality_cfg.get("fingerprint", "chrome"),
            "flow": reality_cfg.get("flow", "xtls-rprx-vision"),
            "network": reality_cfg.get("network", "tcp"),
        }
        hy2_export = None
        candidates = ["reality"]
        color = "#6366f1"
        profile_label = "Reality"
        if strategy == "auto":
            hy2_export = {
                "enabled": bool(hy2_cfg.get("server") and hy2_cfg.get("password")),
                "password": hy2_cfg.get("password", ""),
                "sni": hy2_cfg.get("sni", "") or "www.microsoft.com",
                "insecure": hy2_cfg.get("insecure", False),
                "up_mbps": hy2_cfg.get("up_mbps", 0),
                "down_mbps": hy2_cfg.get("down_mbps", 0),
                "obfs_type": hy2_cfg.get("obfs_type", ""),
                "obfs_password": hy2_cfg.get("obfs_password", ""),
            }
            candidates = ["reality", "hysteria2"]
            color = "#3b82f6"
            profile_label = "Auto"

    profile_name = client_name or "default"
    export = {
        "format": "apix-profile",
        "version": 2,
        "source": {
            "app": "TelegramSimple",
            "exported_at": _utc_now(),
        },
        "profile": {
            "id": f"{profile_name}-telegram-only-{strategy}",
            "name": f"{profile_name} TelegramOnly {profile_label}",
            "icon": "TG",
            "color": color,
            "protocol_type": protocol_type,
            "is_default": False,
        },
        "server": {
            "host": server_host,
            "port": server_port,
        },
        "vpn_mode": "auto",
        "reality": reality_export,
        "hysteria2": hy2_export,
        "routing_policy": _telegram_policy(candidates),
        "meta": {
            "subscription_name": f"TelegramOnly-{profile_name}-{strategy}",
            "server_label": profile_name,
        },
    }
    return export


def _telegram_singbox_route(final_outbound: str) -> Dict:
    return {
        "auto_detect_interface": True,
        "final": "direct",
        "rules": [
            {
                "protocol": "dns",
                "outbound": "dns-out",
            },
            {
                "domain_suffix": TELEGRAM_DOMAINS,
                "outbound": final_outbound,
            },
        ],
    }


def export_singbox_config(strategy: str, client_name: Optional[str] = None) -> Dict:
    strategy = (strategy or "").strip().lower()
    if strategy not in {"reality", "hysteria2"}:
        raise ValueError("Sing-box export supports only reality or hysteria2 strategy")

    if strategy == "reality":
        config = _normalize_reality_config(client_name)
        outbound = {
            "type": "vless",
            "tag": "proxy",
            "server": config.get("server", ""),
            "server_port": config.get("port", 443),
            "uuid": config.get("uuid", ""),
            "flow": config.get("flow", "xtls-rprx-vision"),
            "tls": {
                "enabled": True,
                "server_name": config.get("sni", "www.microsoft.com"),
                "reality": {
                    "enabled": True,
                    "public_key": config.get("public_key", ""),
                    "short_id": config.get("short_id", ""),
                },
                "utls": {
                    "enabled": True,
                    "fingerprint": config.get("fingerprint", "chrome"),
                },
            },
        }
    else:
        config = _normalize_hysteria2_config(client_name)
        outbound = {
            "type": "hysteria2",
            "tag": "proxy",
            "server": config.get("server", ""),
            "server_port": config.get("port", 443),
            "password": config.get("password", ""),
            "tls": {
                "enabled": True,
                "server_name": config.get("sni", "") or "www.microsoft.com",
                "insecure": config.get("insecure", False),
            },
        }
        if config.get("up_mbps", 0) > 0:
            outbound["up_mbps"] = config.get("up_mbps", 0)
        if config.get("down_mbps", 0) > 0:
            outbound["down_mbps"] = config.get("down_mbps", 0)
        if config.get("obfs_type") and config.get("obfs_password"):
            outbound["obfs"] = {
                "type": config.get("obfs_type"),
                "password": config.get("obfs_password"),
            }

    return {
        "log": {"level": "warn"},
        "dns": {
            "servers": [
                {"tag": "google", "address": "8.8.8.8"},
                {"tag": "cloudflare", "address": "1.1.1.1"},
            ],
            "final": "google",
        },
        "inbounds": [
            {
                "type": "socks",
                "tag": "socks-in",
                "listen": "127.0.0.1",
                "listen_port": 1080,
                "sniff": True,
            },
            {
                "type": "http",
                "tag": "http-in",
                "listen": "127.0.0.1",
                "listen_port": 1081,
                "sniff": True,
            },
        ],
        "outbounds": [
            outbound,
            {"type": "direct", "tag": "direct"},
            {"type": "dns", "tag": "dns-out"},
        ],
        "route": _telegram_singbox_route("proxy"),
    }


def export_clash_meta_config(strategy: str, client_name: Optional[str] = None) -> str:
    strategy = (strategy or "").strip().lower()
    if strategy not in {"reality", "hysteria2"}:
        raise ValueError("Clash Meta export supports only reality or hysteria2 strategy")

    lines = [
        "port: 7890",
        "socks-port: 7891",
        "mixed-port: 7892",
        "mode: rule",
        "log-level: info",
        "",
        "proxies:",
    ]

    if strategy == "reality":
        config = _normalize_reality_config(client_name)
        lines.extend([
            "  - name: TelegramOnly-Reality",
            "    type: vless",
            f"    server: {config.get('server', '')}",
            f"    port: {config.get('port', 443)}",
            f"    uuid: {config.get('uuid', '')}",
            f"    flow: {config.get('flow', 'xtls-rprx-vision')}",
            "    network: tcp",
            "    tls: true",
            f"    servername: {config.get('sni', 'www.microsoft.com')}",
            f"    client-fingerprint: {config.get('fingerprint', 'chrome')}",
            "    reality-opts:",
            f"      public-key: {config.get('public_key', '')}",
            f"      short-id: {config.get('short_id', '')}",
        ])
        proxy_name = "TelegramOnly-Reality"
    else:
        config = _normalize_hysteria2_config(client_name)
        lines.extend([
            "  - name: TelegramOnly-Hysteria2",
            "    type: hysteria2",
            f"    server: {config.get('server', '')}",
            f"    port: {config.get('port', 443)}",
            f"    password: {config.get('password', '')}",
        ])
        if config.get("sni"):
            lines.append(f"    sni: {config.get('sni')}")
        if config.get("insecure"):
            lines.append("    skip-cert-verify: true")
        if config.get("obfs_type"):
            lines.append(f"    obfs: {config.get('obfs_type')}")
            if config.get("obfs_password"):
                lines.append(f"    obfs-password: {config.get('obfs_password')}")
        proxy_name = "TelegramOnly-Hysteria2"

    lines.extend([
        "",
        "proxy-groups:",
        "  - name: TelegramOnly",
        "    type: select",
        "    proxies:",
        f"      - {proxy_name}",
        "      - DIRECT",
        "",
        "rules:",
    ])

    for domain in TELEGRAM_DOMAINS:
        lines.append(f"  - DOMAIN-SUFFIX,{domain},TelegramOnly")
    lines.append("  - MATCH,DIRECT")
    return "\n".join(lines)


# =====================================================================
# TUIC / AnyTLS / XHTTP — TelegramOnly exports
# =====================================================================

def _normalize_tuic_config(client_name: Optional[str] = None) -> Dict:
    config = tuic_manager.get_config(include_secrets=True)
    if client_name:
        for client in config.get("clients", []):
            if client.get("name") == client_name:
                config = dict(config)
                config["_client_uuid"] = client.get("uuid", "")
                config["_client_password"] = client.get("password", "")
                break
    else:
        clients = config.get("clients", [])
        if clients:
            config = dict(config)
            config["_client_uuid"] = clients[0].get("uuid", "")
            config["_client_password"] = clients[0].get("password", "")
    return config


def _normalize_anytls_config(client_name: Optional[str] = None) -> Dict:
    config = anytls_manager.get_config(include_secrets=True)
    if client_name:
        for client in config.get("clients", []):
            if client.get("name") == client_name:
                config = dict(config)
                config["_client_password"] = client.get("password", "")
                break
    else:
        clients = config.get("clients", [])
        if clients:
            config = dict(config)
            config["_client_password"] = clients[0].get("password", "")
    return config


def _normalize_xhttp_config(client_name: Optional[str] = None) -> Dict:
    config = xhttp_manager.get_config(include_secrets=True)
    if client_name:
        for client in config.get("clients", []):
            if client.get("name") == client_name:
                config = dict(config)
                config["_client_uuid"] = client.get("uuid", "")
                break
    else:
        clients = config.get("clients", [])
        if clients:
            config = dict(config)
            config["_client_uuid"] = clients[0].get("uuid", "")
    return config


def export_singbox_config_tuic(client_name: Optional[str] = None) -> Dict:
    """Sing-box Telegram-only config with TUIC outbound."""
    config = _normalize_tuic_config(client_name)

    outbound = {
        "type": "tuic",
        "tag": "proxy",
        "server": config.get("server", ""),
        "server_port": config.get("port", 443),
        "uuid": config.get("_client_uuid", ""),
        "password": config.get("_client_password", ""),
        "congestion_control": config.get("congestion_control", "bbr"),
        "udp_relay_mode": config.get("udp_relay_mode", "native"),
        "tls": {
            "enabled": True,
            "server_name": config.get("sni", "") or "www.microsoft.com",
            "insecure": config.get("insecure", False),
        },
    }
    alpn = config.get("alpn", ["h3"])
    if alpn:
        outbound["tls"]["alpn"] = alpn

    return {
        "log": {"level": "warn"},
        "dns": {
            "servers": [
                {"tag": "google", "address": "8.8.8.8"},
                {"tag": "cloudflare", "address": "1.1.1.1"},
            ],
            "final": "google",
        },
        "inbounds": [
            {"type": "socks", "tag": "socks-in", "listen": "127.0.0.1", "listen_port": 1080, "sniff": True},
            {"type": "http", "tag": "http-in", "listen": "127.0.0.1", "listen_port": 1081, "sniff": True},
        ],
        "outbounds": [
            outbound,
            {"type": "direct", "tag": "direct"},
            {"type": "dns", "tag": "dns-out"},
        ],
        "route": _telegram_singbox_route("proxy"),
    }


def export_singbox_config_anytls(client_name: Optional[str] = None) -> Dict:
    """Sing-box Telegram-only config with AnyTLS outbound."""
    config = _normalize_anytls_config(client_name)

    outbound = {
        "type": "anytls",
        "tag": "proxy",
        "server": config.get("server", ""),
        "server_port": config.get("port", 443),
        "password": config.get("_client_password", ""),
        "tls": {
            "enabled": True,
            "server_name": config.get("sni", "") or "www.microsoft.com",
            "insecure": config.get("insecure", False),
        },
    }

    return {
        "log": {"level": "warn"},
        "dns": {
            "servers": [
                {"tag": "google", "address": "8.8.8.8"},
                {"tag": "cloudflare", "address": "1.1.1.1"},
            ],
            "final": "google",
        },
        "inbounds": [
            {"type": "socks", "tag": "socks-in", "listen": "127.0.0.1", "listen_port": 1080, "sniff": True},
            {"type": "http", "tag": "http-in", "listen": "127.0.0.1", "listen_port": 1081, "sniff": True},
        ],
        "outbounds": [
            outbound,
            {"type": "direct", "tag": "direct"},
            {"type": "dns", "tag": "dns-out"},
        ],
        "route": _telegram_singbox_route("proxy"),
    }


def export_singbox_config_xhttp(client_name: Optional[str] = None) -> Dict:
    """Sing-box Telegram-only config with VLESS+XHTTP outbound."""
    config = _normalize_xhttp_config(client_name)

    outbound = {
        "type": "vless",
        "tag": "proxy",
        "server": config.get("server", ""),
        "server_port": config.get("port", 443),
        "uuid": config.get("_client_uuid", ""),
        "transport": {
            "type": "xhttp",
            "path": config.get("path", "/"),
        },
    }

    mode = config.get("mode", "auto")
    if mode and mode != "auto":
        outbound["transport"]["mode"] = mode

    host = config.get("host", "")
    if host:
        outbound["transport"]["host"] = host

    security = config.get("security", "tls")
    if security == "tls":
        outbound["tls"] = {
            "enabled": True,
            "server_name": config.get("sni", "") or "www.microsoft.com",
            "insecure": config.get("insecure", False),
        }

    return {
        "log": {"level": "warn"},
        "dns": {
            "servers": [
                {"tag": "google", "address": "8.8.8.8"},
                {"tag": "cloudflare", "address": "1.1.1.1"},
            ],
            "final": "google",
        },
        "inbounds": [
            {"type": "socks", "tag": "socks-in", "listen": "127.0.0.1", "listen_port": 1080, "sniff": True},
            {"type": "http", "tag": "http-in", "listen": "127.0.0.1", "listen_port": 1081, "sniff": True},
        ],
        "outbounds": [
            outbound,
            {"type": "direct", "tag": "direct"},
            {"type": "dns", "tag": "dns-out"},
        ],
        "route": _telegram_singbox_route("proxy"),
    }


def export_clash_meta_config_tuic(client_name: Optional[str] = None) -> str:
    """Clash Meta Telegram-only config with TUIC proxy."""
    config = _normalize_tuic_config(client_name)

    lines = [
        "port: 7890", "socks-port: 7891", "mixed-port: 7892",
        "mode: rule", "log-level: info", "",
        "proxies:",
        "  - name: TelegramOnly-TUIC",
        "    type: tuic",
        f"    server: {config.get('server', '')}",
        f"    port: {config.get('port', 443)}",
        f"    uuid: {config.get('_client_uuid', '')}",
        f"    password: {config.get('_client_password', '')}",
        f"    congestion-controller: {config.get('congestion_control', 'bbr')}",
        f"    udp-relay-mode: {config.get('udp_relay_mode', 'native')}",
    ]
    alpn = config.get("alpn", ["h3"])
    if alpn:
        lines.append("    alpn:")
        for a in alpn:
            lines.append(f"      - {a}")
    if config.get("sni"):
        lines.append(f"    sni: {config.get('sni')}")
    if config.get("insecure"):
        lines.append("    skip-cert-verify: true")

    lines.extend(_clash_telegram_rules("TelegramOnly-TUIC"))
    return "\n".join(lines)


def export_clash_meta_config_anytls(client_name: Optional[str] = None) -> str:
    """Clash Meta Telegram-only config with AnyTLS proxy."""
    config = _normalize_anytls_config(client_name)

    lines = [
        "port: 7890", "socks-port: 7891", "mixed-port: 7892",
        "mode: rule", "log-level: info", "",
        "proxies:",
        "  - name: TelegramOnly-AnyTLS",
        "    type: anytls",
        f"    server: {config.get('server', '')}",
        f"    port: {config.get('port', 443)}",
        f"    password: {config.get('_client_password', '')}",
    ]
    if config.get("sni"):
        lines.append(f"    sni: {config.get('sni')}")
    if config.get("insecure"):
        lines.append("    skip-cert-verify: true")

    lines.extend(_clash_telegram_rules("TelegramOnly-AnyTLS"))
    return "\n".join(lines)


def export_clash_meta_config_xhttp(client_name: Optional[str] = None) -> str:
    """Clash Meta Telegram-only config with VLESS+XHTTP proxy."""
    config = _normalize_xhttp_config(client_name)

    lines = [
        "port: 7890", "socks-port: 7891", "mixed-port: 7892",
        "mode: rule", "log-level: info", "",
        "proxies:",
        "  - name: TelegramOnly-XHTTP",
        "    type: vless",
        f"    server: {config.get('server', '')}",
        f"    port: {config.get('port', 443)}",
        f"    uuid: {config.get('_client_uuid', '')}",
        "    network: xhttp",
        "    xhttp-opts:",
        f"      path: {config.get('path', '/')}",
    ]
    mode = config.get("mode", "auto")
    if mode and mode != "auto":
        lines.append(f"      mode: {mode}")
    host = config.get("host", "")
    if host:
        lines.append(f"      host: {host}")

    security = config.get("security", "tls")
    if security == "tls":
        lines.append("    tls: true")
        if config.get("sni"):
            lines.append(f"    servername: {config.get('sni')}")
        if config.get("insecure"):
            lines.append("    skip-cert-verify: true")

    lines.extend(_clash_telegram_rules("TelegramOnly-XHTTP"))
    return "\n".join(lines)


def _clash_telegram_rules(proxy_name: str) -> List[str]:
    """Common Clash Meta proxy-groups + Telegram routing rules."""
    lines = [
        "",
        "proxy-groups:",
        "  - name: TelegramOnly",
        "    type: select",
        "    proxies:",
        f"      - {proxy_name}",
        "      - DIRECT",
        "",
        "rules:",
    ]
    for domain in TELEGRAM_DOMAINS:
        lines.append(f"  - DOMAIN-SUFFIX,{domain},TelegramOnly")
    lines.append("  - MATCH,DIRECT")
    return lines

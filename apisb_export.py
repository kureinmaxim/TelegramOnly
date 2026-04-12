# -*- coding: utf-8 -*-
"""
Единый legacy-формат экспорта профиля из TelegramOnly, совместимый с ApiXgRPC.

Формат: apisb-profile v1
Один профиль = один серверный endpoint + один transport (Reality или Hysteria2).

Спецификация: APISB_PROFILE_EXPORT_FORMAT.md
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional


ProtocolType = Literal["reality", "hysteria2", "mtproto"]
VpnMode = Literal["auto", "tun", "socks5"]


@dataclass
class ExportSource:
    app: str = "TelegramOnly"
    exported_at: str = ""


@dataclass
class ExportProfile:
    id: str = ""
    name: str = ""
    icon: str = ""
    color: str = ""
    protocol_type: ProtocolType = "reality"
    is_default: bool = False


@dataclass
class ExportServer:
    host: str = ""
    port: int = 443


@dataclass
class RealityExport:
    enabled: bool = True
    uuid: str = ""
    public_key: str = ""
    short_id: str = ""
    sni: str = "www.microsoft.com"
    fingerprint: str = "chrome"
    flow: str = "xtls-rprx-vision"
    network: str = "tcp"


@dataclass
class Hysteria2Export:
    enabled: bool = True
    password: str = ""
    sni: str = ""
    insecure: bool = False
    up_mbps: int = 0
    down_mbps: int = 0
    obfs_type: str = ""
    obfs_password: str = ""


@dataclass
class MtprotoExport:
    enabled: bool = True
    secret: str = ""
    fake_tls_domain: str = ""
    is_fake_tls: bool = True


@dataclass
class ExportMeta:
    subscription_name: str = ""
    server_label: str = ""


@dataclass
class ApiSbExportProfile:
    format: Literal["apisb-profile"] = "apisb-profile"
    version: Literal[1] = 1
    source: ExportSource = field(default_factory=ExportSource)
    profile: ExportProfile = field(default_factory=ExportProfile)
    server: ExportServer = field(default_factory=ExportServer)
    vpn_mode: VpnMode = "auto"
    reality: Optional[RealityExport] = None
    hysteria2: Optional[Hysteria2Export] = None
    mtproto: Optional[MtprotoExport] = None
    meta: ExportMeta = field(default_factory=ExportMeta)

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================================
# Factory functions
# ============================================================================

def build_reality_export(vless_cfg: dict, profile_name: str = "default") -> dict:
    """
    Построить apisb-profile v1 из конфигурации VLESS-Reality.

    Args:
        vless_cfg: Словарь из vless_config.json (результат _load_config()).
        profile_name: Имя профиля / клиента.

    Returns:
        dict — готовый JSON для импорта в ApiXgRPC.
    """
    return ApiSbExportProfile(
        source=ExportSource(
            app="TelegramOnly",
            exported_at=datetime.now(timezone.utc).isoformat(),
        ),
        profile=ExportProfile(
            id=f"{profile_name}-reality",
            name=f"{profile_name} Reality",
            icon="\U0001f6e1\ufe0f",
            color="#6366f1",
            protocol_type="reality",
        ),
        server=ExportServer(
            host=vless_cfg.get("server", ""),
            port=vless_cfg.get("port", 443),
        ),
        vpn_mode="auto",
        reality=RealityExport(
            enabled=True,
            uuid=vless_cfg.get("uuid", ""),
            public_key=vless_cfg.get("public_key", ""),
            short_id=vless_cfg.get("short_id", ""),
            sni=vless_cfg.get("sni", "www.microsoft.com"),
            fingerprint=vless_cfg.get("fingerprint", "chrome"),
            flow=vless_cfg.get("flow", "xtls-rprx-vision"),
            network=vless_cfg.get("network", "tcp"),
        ),
        hysteria2=None,
        meta=ExportMeta(
            subscription_name=f"TelegramOnly-{profile_name}",
            server_label=profile_name,
        ),
    ).to_dict()


def build_hysteria2_export(hy2_cfg: dict, profile_name: str = "default") -> dict:
    """
    Построить apisb-profile v1 из конфигурации Hysteria2.

    Args:
        hy2_cfg: Словарь из hysteria2_config.json (результат _load_config()).
        profile_name: Имя профиля / клиента.

    Returns:
        dict — готовый JSON для импорта в ApiXgRPC.
    """
    return ApiSbExportProfile(
        source=ExportSource(
            app="TelegramOnly",
            exported_at=datetime.now(timezone.utc).isoformat(),
        ),
        profile=ExportProfile(
            id=f"{profile_name}-hy2",
            name=f"{profile_name} Hysteria2",
            icon="\u26a1",
            color="#10b981",
            protocol_type="hysteria2",
        ),
        server=ExportServer(
            host=hy2_cfg.get("server", ""),
            port=hy2_cfg.get("port", 443),
        ),
        vpn_mode="auto",
        reality=None,
        hysteria2=Hysteria2Export(
            enabled=True,
            password=hy2_cfg.get("password", ""),
            sni=hy2_cfg.get("sni", ""),
            insecure=hy2_cfg.get("insecure", False),
            up_mbps=hy2_cfg.get("up_mbps", 0),
            down_mbps=hy2_cfg.get("down_mbps", 0),
            obfs_type=hy2_cfg.get("obfs_type", ""),
            obfs_password=hy2_cfg.get("obfs_password", ""),
        ),
        meta=ExportMeta(
            subscription_name=f"TelegramOnly-{profile_name}",
            server_label=profile_name,
        ),
    ).to_dict()


def build_mtproto_export(mt_cfg: dict, profile_name: str = "default") -> dict:
    """
    Построить apisb-profile v1 из конфигурации MTProto proxy.

    Args:
        mt_cfg: Словарь из mtproto_config.json (результат _load_config()).
        profile_name: Имя профиля / клиента.

    Returns:
        dict — готовый JSON для импорта в ApiXgRPC.
    """
    secret = mt_cfg.get("secret", "")
    return ApiSbExportProfile(
        source=ExportSource(
            app="TelegramOnly",
            exported_at=datetime.now(timezone.utc).isoformat(),
        ),
        profile=ExportProfile(
            id=f"{profile_name}-mtproto",
            name=f"{profile_name} MTProto",
            icon="\U0001f4e1",
            color="#3b82f6",
            protocol_type="mtproto",
        ),
        server=ExportServer(
            host=mt_cfg.get("server", ""),
            port=mt_cfg.get("port", 993),
        ),
        vpn_mode="auto",
        reality=None,
        hysteria2=None,
        mtproto=MtprotoExport(
            enabled=True,
            secret=secret,
            fake_tls_domain=mt_cfg.get("fake_tls_domain", ""),
            is_fake_tls=secret.startswith("dd") if secret else False,
        ),
        meta=ExportMeta(
            subscription_name=f"TelegramOnly-{profile_name}",
            server_label=profile_name,
        ),
    ).to_dict()

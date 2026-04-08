# -*- coding: utf-8 -*-
"""
Admin CLI Module - Execute bot commands without Telegram context.

This module provides a way to execute admin commands from an ApiXgRPC client
when the Telegram bot is disabled.

Author: Kurein M.N.
Date: 15.12.2025
"""

import logging
import os
import secrets
import base64
from typing import Tuple, Optional, List

from config import Config
import vless_manager
from utils import get_app_version, escape_markdown

logger = logging.getLogger(__name__)


class AdminCLI:
    """Execute bot admin commands without Telegram."""
    
    # Supported commands (command -> handler method name)
    COMMANDS = {
        "/help": "_cmd_help",
        "/ver": "_cmd_version",
        "/vless_status": "_cmd_vless_status",
        "/vless_config": "_cmd_vless_config",
        "/vless_set_port": "_cmd_vless_set_port",
        "/vless_on": "_cmd_vless_on",
        "/vless_off": "_cmd_vless_off",
        "/bot_status": "_cmd_bot_status",
        "/disable_bot": "_cmd_disable_bot",
        "/enable_bot": "_cmd_enable_bot",
        "/api": "_cmd_api",
        "/encryption_key": "_cmd_encryption_key",
        "/info": "_cmd_info",
        "/vless_set_port": "_cmd_vless_set_port",
        "/vless_link": "_cmd_vless_link",
    }
    
    def __init__(self, config: Config = None):
        """Initialize AdminCLI with optional config."""
        self.config = config or Config()
    
    def execute(self, command: str, args: List[str] = None) -> Tuple[bool, str]:
        """
        Execute an admin command.
        
        Args:
            command: Command string like "/help" or "/vless_status"
            args: Optional list of command arguments
            
        Returns:
            Tuple of (success: bool, response: str)
        """
        args = args or []
        cmd = command.lower().strip()
        
        # Check if command is supported
        if cmd not in self.COMMANDS:
            available = ", ".join(sorted(self.COMMANDS.keys()))
            return False, f"❌ Unknown command: {cmd}\n\nAvailable commands:\n{available}"
        
        # Get handler method
        handler_name = self.COMMANDS[cmd]
        handler = getattr(self, handler_name, None)
        
        if not handler:
            return False, f"❌ Handler not implemented: {handler_name}"
        
        try:
            result = handler(args)
            return True, result
        except Exception as e:
            logger.error(f"Error executing {cmd}: {e}")
            return False, f"❌ Error: {str(e)}"
    
    # === COMMAND HANDLERS ===
    
    def _cmd_help(self, args: List[str]) -> str:
        """Show available commands."""
        return """📚 Admin CLI Commands

🔧 System:
/help - This help message
/ver - Version information
/info - Server info

🤖 Bot Management:
/bot_status - Check if bot is enabled/disabled
/disable_bot - Disable Telegram bot
/enable_bot - Enable Telegram bot

🛡️ VLESS-Reality:
/vless_status - VLESS status
/vless_config - Show configuration
/vless_on - Enable VLESS
/vless_off - Disable VLESS

 Keys (apiai-v3):
/api - Show API key (FULL)
/encryption_key - Show encryption key (FULL)"""
    
    def _cmd_version(self, args: List[str]) -> str:
        """Show version info."""
        version_info = get_app_version()
        vless_status = vless_manager.get_vless_status()
        
        return f"""📋 Version Information

🔖 Version: {version_info.get('version', 'N/A')}
📦 Name: {version_info.get('name', 'TelegramSimple Lite')}
📝 Description: {version_info.get('description', 'N/A')}

🛡️ VLESS-Reality:
Status: {"🟢 Enabled" if vless_status["enabled"] else "🔴 Disabled"}
Configured: {"✅ Yes" if vless_status["configured"] else "❌ No"}
Server: {vless_status.get("server") or "not configured"}"""
    
    def _cmd_info(self, args: List[str]) -> str:
        """Show server info."""
        import socket
        import platform
        import os
        
        hostname = socket.gethostname()
        python_version = platform.python_version()
        
        # Get Linux distro info
        system = platform.system()
        if system == "Linux":
            try:
                # Try to read /etc/os-release for distro info
                with open('/etc/os-release', 'r') as f:
                    os_release = {}
                    for line in f:
                        if '=' in line:
                            key, value = line.strip().split('=', 1)
                            os_release[key] = value.strip('"')
                    distro = os_release.get('PRETTY_NAME', os_release.get('NAME', 'Linux'))
                    system = distro
            except:
                system = "Linux"
        
        # Check if running inside Docker container
        docker_status = "not detected"
        if os.path.exists('/.dockerenv'):
            docker_status = "🐳 Running inside container"
        elif os.path.exists('/proc/1/cgroup'):
            try:
                with open('/proc/1/cgroup', 'r') as f:
                    if 'docker' in f.read():
                        docker_status = "🐳 Running inside container"
            except:
                pass
        
        return f"""📊 Server Information

🖥️ Hostname: {hostname}
💻 System: {system}
🐍 Python: {python_version}
🐳 Docker: {docker_status}"""
    
    def _cmd_vless_status(self, args: List[str]) -> str:
        """Show VLESS status."""
        status = vless_manager.get_vless_status()
        
        status_emoji = "🟢" if status["enabled"] else "🔴"
        config_emoji = "✅" if status["configured"] else "❌"
        
        return f"""🛡️ VLESS-Reality Status

State: {status_emoji} {"Enabled" if status["enabled"] else "Disabled"}
Configuration: {config_emoji} {"Configured" if status["configured"] else "Not configured"}

Parameters:
• Server: {status.get("server") or "not set"}
• Port: {status.get("port", 443)}
• SNI: {status.get("sni", "www.microsoft.com")}
• Fingerprint: {status.get("fingerprint", "chrome")}

Keys:
• UUID: {"✅" if status["has_uuid"] else "❌"}
• Public Key: {"✅" if status["has_public_key"] else "❌"}
• Private Key: {"✅" if status["has_private_key"] else "❌"}
• Short ID: {"✅" if status["has_short_id"] else "❌"}

Updated: {status.get("updated_at", "never")}"""
    
    def _cmd_vless_config(self, args: List[str]) -> str:
        """Show VLESS configuration."""
        config = vless_manager.get_vless_config()
        
        if not config:
            return "❌ VLESS not configured. Use /vless_sync in Telegram bot."
        
        # Mask sensitive values
        uuid = config.get("uuid", "")
        masked_uuid = f"{uuid[:8]}...{uuid[-4:]}" if len(uuid) > 12 else "***"
        
        public_key = config.get("public_key", "")
        masked_key = f"{public_key[:8]}...{public_key[-4:]}" if len(public_key) > 12 else "***"
        
        return f"""🛡️ VLESS Configuration

Server: {config.get("server", "not set")}
Port: {config.get("port", 443)}
UUID: {masked_uuid}
Public Key: {masked_key}
Short ID: {config.get("short_id", "not set")}
SNI: {config.get("sni", "www.microsoft.com")}
Fingerprint: {config.get("fingerprint", "chrome")}

💡 For full keys, use Telegram bot."""
    
    def _cmd_vless_on(self, args: List[str]) -> str:
        """Enable VLESS."""
        success, message = vless_manager.enable_vless()
        return message
    
    def _cmd_vless_off(self, args: List[str]) -> str:
        """Disable VLESS."""
        success, message = vless_manager.disable_vless()
        return message
    
    def _cmd_vless_set_port(self, args: List[str]) -> str:
        """Change VLESS port."""
        if not args or len(args) < 1:
            return """❌ Usage: /vless_set_port <port>

Example: /vless_set_port 8443

⚠️ После смены порта не забудьте:
1. Перезапустить Xray: systemctl restart xray
2. Открыть порт в firewall: ufw allow <port>/tcp"""
        
        try:
            port = int(args[0])
        except ValueError:
            return f"❌ Invalid port: {args[0]}. Port must be a number."
        
        # Change port (message already includes restart reminder)
        success, message = vless_manager.set_vless_port(port)
        return message

    def _cmd_vless_link(self, args: List[str]) -> str:
        """Get VLESS import link."""
        link = vless_manager.generate_vless_link()
        if not link:
            return "❌ VLESS not fully configured (missing server/uuid/keys)"
        return link
    
    def _cmd_bot_status(self, args: List[str]) -> str:
        """Check if Telegram bot is enabled or disabled."""
        import os
        
        project_dir = "/opt/TelegramSimple" if os.path.exists("/opt/TelegramSimple") else os.getcwd()
        env_path = os.path.join(project_dir, ".env")
        
        # Check actual BOT_TOKEN status in .env file
        bot_token_active = False
        bot_token_commented = False
        
        try:
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('BOT_TOKEN='):
                        bot_token_active = True
                        break
                    elif line.startswith('#BOT_TOKEN=') or line.startswith('# BOT_TOKEN='):
                        bot_token_commented = True
        except Exception as e:
            return f"❌ Cannot read .env file: {e}"
        
        # Check marker file
        marker_path = os.path.join(project_dir, ".bot_disabled")
        marker_exists = os.path.exists(marker_path)
        
        if bot_token_active:
            # BOT_TOKEN is active - bot should be running
            if marker_exists:
                # Cleanup stale marker
                try:
                    os.remove(marker_path)
                except:
                    pass
            return """🤖 Bot Status

� Status: ENABLED (Running)
BOT_TOKEN is active in .env

To disable: /disable_bot"""
        elif bot_token_commented:
            # BOT_TOKEN is commented out
            disabled_info = ""
            if marker_exists:
                try:
                    with open(marker_path, 'r') as f:
                        disabled_info = f"\n📅 {f.read().strip()}"
                except:
                    pass
            return f"""🤖 Bot Status

🔴 Status: DISABLED
BOT_TOKEN is commented out in .env{disabled_info}

To enable: /enable_bot"""
        else:
            return """🤖 Bot Status

⚠️ Status: UNKNOWN
BOT_TOKEN not found in .env file"""
    
    def _cmd_disable_bot(self, args: List[str]) -> str:
        """Disable Telegram bot."""
        import subprocess
        import os
        
        # Check if already disabled
        marker_path = "/opt/TelegramSimple/.bot_disabled"
        local_marker = ".bot_disabled"
        if os.path.exists(marker_path) or os.path.exists(local_marker):
            return "⚠️ Bot is already disabled"
        
        try:
            # Run disable script non-interactively
            script_path = "/opt/TelegramSimple/scripts/disable_bot.sh"
            local_script = "scripts/disable_bot.sh"
            
            actual_script = script_path if os.path.exists(script_path) else local_script
            
            # Run the commands directly instead of script (to avoid interactive prompt)
            project_dir = "/opt/TelegramSimple" if os.path.exists("/opt/TelegramSimple") else os.getcwd()
            env_path = os.path.join(project_dir, ".env")
            
            # Backup token
            if os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    env_content = f.read()
                
                # Comment out BOT_TOKEN
                new_content = env_content.replace("BOT_TOKEN=", "#DISABLED_BOT_TOKEN=")
                
                with open(env_path, 'w') as f:
                    f.write(new_content)
            
            # Create marker
            marker = os.path.join(project_dir, ".bot_disabled")
            from datetime import datetime
            with open(marker, 'w') as f:
                f.write(f"Disabled at: {datetime.now()}")
            
            # Restart container
            result = subprocess.run(
                ["docker", "compose", "restart"],
                cwd=project_dir,
                capture_output=True, text=True, timeout=60
            )
            
            if result.returncode == 0:
                return """🔒 Bot Disabled Successfully!

• BOT_TOKEN commented out in .env
• Marker file .bot_disabled created
• Container restarted

API is still accessible.
To restore: /enable_bot"""
            else:
                return f"""⚠️ Bot disabled but container restart failed:
{result.stderr}

Run manually: docker compose restart"""
                
        except subprocess.TimeoutExpired:
            return "❌ Timeout during container restart"
        except Exception as e:
            return f"❌ Error disabling bot: {e}"
    
    def _cmd_enable_bot(self, args: List[str]) -> str:
        """Enable Telegram bot (restore from disabled state)."""
        import subprocess
        import os
        
        # Check if actually disabled
        marker_path = "/opt/TelegramSimple/.bot_disabled"
        local_marker = ".bot_disabled"
        project_dir = "/opt/TelegramSimple" if os.path.exists("/opt/TelegramSimple") else os.getcwd()
        
        marker = marker_path if os.path.exists(marker_path) else local_marker
        if not os.path.exists(marker):
            return "ℹ️ Bot is already enabled"
        
        try:
            env_path = os.path.join(project_dir, ".env")
            
            # Restore BOT_TOKEN
            if os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    env_content = f.read()
                
                # Uncomment BOT_TOKEN
                new_content = env_content.replace("#DISABLED_BOT_TOKEN=", "BOT_TOKEN=")
                
                with open(env_path, 'w') as f:
                    f.write(new_content)
            
            # Remove marker
            if os.path.exists(marker):
                os.remove(marker)
            
            # Restart container
            result = subprocess.run(
                ["docker", "compose", "restart"],
                cwd=project_dir,
                capture_output=True, text=True, timeout=60
            )
            
            if result.returncode == 0:
                return """✅ Bot Enabled Successfully!

• BOT_TOKEN restored in .env
• Marker file removed
• Container restarted

Bot is now running!"""
            else:
                return f"""⚠️ Bot enabled but container restart failed:
{result.stderr}

Run manually: docker compose restart"""
                
        except subprocess.TimeoutExpired:
            return "❌ Timeout during container restart"
        except Exception as e:
            return f"❌ Error enabling bot: {e}"
    
    def _cmd_xray_status(self, args: List[str]) -> str:
        """Check Xray service status."""
        import subprocess
        
        try:
            # Try systemctl status
            result = subprocess.run(
                ["systemctl", "is-active", "xray"],
                capture_output=True, text=True, timeout=5
            )
            status = result.stdout.strip()
            
            if status == "active":
                # Get more info
                info_result = subprocess.run(
                    ["systemctl", "show", "xray", "--property=MainPID,ActiveEnterTimestamp"],
                    capture_output=True, text=True, timeout=5
                )
                info_lines = info_result.stdout.strip().split('\n')
                pid = ""
                uptime = ""
                for line in info_lines:
                    if line.startswith("MainPID="):
                        pid = line.split("=")[1]
                    elif line.startswith("ActiveEnterTimestamp="):
                        uptime = line.split("=")[1]
                
                return f"""📦 Xray Status

✅ Status: Active (Running)
🔢 PID: {pid}
⏰ Started: {uptime or 'unknown'}

💡 Commands:
• systemctl restart xray - перезапустить
• journalctl -u xray -n 50 - логи"""
            else:
                return f"""📦 Xray Status

❌ Status: {status}

💡 To start: systemctl start xray"""
                
        except FileNotFoundError:
            return "❌ systemctl not available (not running on systemd)"
        except subprocess.TimeoutExpired:
            return "❌ Timeout checking Xray status"
        except Exception as e:
            return f"❌ Error checking Xray: {e}"
    
    def _cmd_xray_config(self, args: List[str]) -> str:
        """Show Xray config location and basic info."""
        import os
        
        config_paths = [
            "/usr/local/etc/xray/config.json",
            "/etc/xray/config.json",
            "/opt/xray/config.json"
        ]
        
        config_path = None
        for path in config_paths:
            if os.path.exists(path):
                config_path = path
                break
        
        if not config_path:
            return "❌ Xray config not found in standard locations"
        
        try:
            import json
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Extract basic info
            inbounds = config.get("inbounds", [])
            outbounds = config.get("outbounds", [])
            
            inbound_info = []
            for ib in inbounds:
                port = ib.get("port", "?")
                protocol = ib.get("protocol", "?")
                inbound_info.append(f"  • {protocol} on port {port}")
            
            return f"""📦 Xray Configuration

📍 Path: {config_path}
📥 Inbounds: {len(inbounds)}
{chr(10).join(inbound_info) if inbound_info else '  (none)'}
📤 Outbounds: {len(outbounds)}

💡 Sync config: python3 scripts/sync_xray_config.py"""
            
        except Exception as e:
            return f"❌ Error reading Xray config: {e}"
    
    def _cmd_api(self, args: List[str]) -> str:
        """Show API key - FULL for apiai-v3."""
        try:
            from app_keys import get_api_key
            
            # Get apiai-v3 key directly (main client)
            key = get_api_key("apiai-v3")
            
            if key:
                return f"""🔑 API Key (apiai-v3)

{key}

📋 Copy and paste into ApiXgRPC Settings"""
            else:
                # Fallback to default
                default_key = os.getenv("API_SECRET_KEY", "")
                if default_key:
                    return f"""🔑 API Key (default)

{default_key}

⚠️ apiai-v3 key not found, using default"""
                else:
                    return "❌ No API keys configured"
            
        except ImportError:
            api_key = os.getenv("API_SECRET_KEY", "")
            if api_key:
                return f"""🔑 API Key (default)

{api_key}"""
            return "❌ No API key configured"
    
    def _cmd_encryption_key(self, args: List[str]) -> str:
        """Show encryption key - FULL for apiai-v3."""
        try:
            from app_keys import get_encryption_key
            
            # Get apiai-v3 key directly (main client)
            key = get_encryption_key("apiai-v3")
            
            if key:
                return f"""🔐 Encryption Key (apiai-v3)

{key}

📋 Copy and paste into ApiXgRPC Settings"""
            else:
                # Fallback to default
                default_key = os.getenv("ENCRYPTION_KEY", "")
                if default_key:
                    return f"""🔐 Encryption Key (default)

{default_key}

⚠️ apiai-v3 key not found, using default"""
                else:
                    return "❌ No encryption keys configured"
            
        except ImportError:
            enc_key = os.getenv("ENCRYPTION_KEY", "")
            if enc_key:
                return f"""🔐 Encryption Key (default)

{enc_key}"""
            return "❌ No encryption key configured"



# Global instance
admin_cli = AdminCLI()


def execute_admin_command(command: str, args: List[str] = None) -> Tuple[bool, str]:
    """
    Execute an admin command.
    
    This is the main entry point for the API endpoint.
    
    Args:
        command: Command string like "/help"
        args: Optional command arguments
        
    Returns:
        Tuple of (success, response_text)
    """
    return admin_cli.execute(command, args)

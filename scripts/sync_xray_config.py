#!/usr/bin/env python3
"""
Sync Xray Config
Generates Xray config using vless_manager.py and writes it to /usr/local/etc/xray/config.json
This allows the TelegramSimple bot to control the actual Xray server.
"""

import sys
import os
import json
import logging

# Add parent directory to path to import vless_manager
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from vless_manager import export_xray_config, get_vless_status
except ImportError as e:
    print(f"Error importing vless_manager: {e}")
    sys.exit(1)

XRAY_CONFIG_PATH = "/usr/local/etc/xray/config.json"

def sync_config():
    print("Generating Xray configuration...")
    
    # Get server config from vless_manager
    xray_config = export_xray_config(is_server=True)
    status = get_vless_status()
    
    if not status['configured']:
        print("Warning: VLESS is not fully configured in vless_manager. Using partial config.")
    
    # Write to Xray config file
    try:
        os.makedirs(os.path.dirname(XRAY_CONFIG_PATH), exist_ok=True)
        
        with open(XRAY_CONFIG_PATH, 'w') as f:
            json.dump(xray_config, f, indent=2)
            
        print(f"Successfully wrote Xray config to {XRAY_CONFIG_PATH}")
        print(f"Server Port: {status.get('port', 443)}")
        print(f"UUID: {xray_config['inbounds'][0]['settings']['clients'][0]['id']}")
        print(f"SNI: {xray_config['inbounds'][0]['streamSettings']['realitySettings']['serverNames'][0]}")
        
    except PermissionError:
        print(f"Error: Permission denied writing to {XRAY_CONFIG_PATH}. Run as root.")
        sys.exit(1)
    except Exception as e:
        print(f"Error writing config: {e}")
        sys.exit(1)

if __name__ == "__main__":
    sync_config()

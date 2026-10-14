"""Ixon Cloud API: authentication and device proxy access."""

import sys
import base64
import getpass
import os
import requests
import json
import time
from pathlib import Path
# from .ui import pick_from_list, print_numbered_list

IXON_APP_ID   = "9J9IZzeT4xN4"
IXON_API_BASE = "https://api.ayayot.com"
TOKEN_CACHE = Path("cache/ixon_token.json")

def authenticate() -> tuple[dict, list[dict]]:
    """Login to Ixon, discover devices with InfluxDB. Done once per session.

    Returns (ixon_headers, influx_devices).
    """

    # First check if we have an authentication cached, which is not expired
    cached = _load_cached_login()
    if cached:
        return cached # If exists and not expired, return this and skip the process

    email = os.environ.get("IXON_EMAIL") or input("  Ixon email: ").strip()
    # getpass hides the typed password, showing * for each character instead
    password = (os.environ.get("IXON_PASS")
                or getpass.getpass("  Ixon password: ", echo_char="*").strip())

    # Try without 2FA first, then prompt if required
    otp = ""
    while True:
        if otp == "":
            creds = base64.b64encode(f"{email}:{password}".encode()).decode()
        else:
            creds = base64.b64encode(f"{email}:{otp}:{password}".encode()).decode()

        headers = {
            "Api-Version": "2",
            "Api-Application": IXON_APP_ID,
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/json",
        }

        resp = requests.post(
            f"{IXON_API_BASE}/access-tokens",
            headers=headers,
            json={"expiresIn": 3600},
        )

        if resp.status_code == 201:
            break

        # Check if 2FA is required via structured error message
        needs_2fa = False
        try:
            errors = resp.json().get("data", [])
            for e in errors:
                msg = e.get("message", "").lower()
                needs_2fa = "2fa" in msg or "two factor" in msg
                if needs_2fa:
                    break
        except (ValueError, AttributeError):
            pass

        if needs_2fa:
            if otp == "":
                otp = input(f"  Ixon 2FA code required for this account: ").strip()
                if otp:
                    continue
            else:
                print("Invalid 2FA code.")
                otp = input(f"  Ixon 2FA code: ").strip()
                if otp:
                    continue

        print(f"Ixon login failed — HTTP {resp.status_code}: {resp.text[:200]}")
        sys.exit(1)

    token = resp.json()["data"]["secretId"]
    headers["Authorization"] = f"Bearer {token}"
    print("Ixon authenticated. Token valid for 1 hour.")

    # Company
    resp2 = requests.get(
        f"{IXON_API_BASE}/companies",
        headers=headers,
        params={"fields": "publicId,name"},
    )
    headers["Api-Company"] = resp2.json()["data"][0]["publicId"]

    # Discover devices with InfluxDB servers
    print(f"  Discovering devices...")
    resp3 = requests.get(
        f"{IXON_API_BASE}/agents",
        headers=headers,
        params={"fields": "publicId,name"},
    )

    devices = []
    for agent in resp3.json()["data"]:
        resp4 = requests.get(
            f"{IXON_API_BASE}/agents/{agent['publicId']}/servers",
            headers=headers,
        )
        if resp4.status_code == 200:
            for server in resp4.json()["data"]:
                if "influx" in server.get("name", "").lower():
                    devices.append({
                        "agent_name": agent["name"],
                        "agent_id": agent["publicId"],
                        "server_id": server["publicId"],
                        "server_name": server["name"],
                    })

    if not devices:
        print("No InfluxDB servers found on any device.")
        sys.exit(1)

    # Save authentication for the next hour
    _save_cached_login(headers,devices)

    print(f"Found {len(devices)} device(s) with InfluxDB.")
    return headers, devices


def start_session(ixon_headers: dict, devices: list[dict], cfg: dict
              ) -> tuple[requests.Session, str]:
    
    """Create WebAccess proxy session.
    
    Auto re-authenticates if the Ixon token has expired."""

    # Prepare
    names = [f"{d['agent_name']} ({d['server_name']})" for d in devices]

    device = devices[names.index(cfg.get("device", ""))]

    # WebAccess session
    print(f"  Connecting to {device['agent_name']}...")
    resp = requests.post(
        f"{IXON_API_BASE}/web-access",
        headers=ixon_headers,
        json={"server": {"publicId": device["server_id"]}},
    )

    if resp.status_code in (401, 403):
        print("Ixon session expired. Re-authenticating...")
        TOKEN_CACHE.unlink(missing_ok=True) # Delete the cache to force a real login
        new_headers, new_devices = authenticate() # New login
        ixon_headers.clear()
        ixon_headers.update(new_headers)
        devices.clear()
        devices.extend(new_devices)
        # Recursive iteration, calls itself again
        return start_session(ixon_headers, devices, cfg)

    if resp.status_code != 201:
        msg = resp.json().get("data", [{}])[0].get("message", resp.text[:200])
        print(f"WebAccess failed: {msg}")
        if "not online" in msg.lower():
            print(f"    The device is offline. Try a different one.")
        # Recursive iteration, calls itself again
        return start_session(ixon_headers, devices, cfg)

    proxy_url = resp.json()["data"]["url"]
    base_url = proxy_url.split("?")[0].rstrip("/")

    # InfluxDB API

    api_token = os.environ.get("API_TOKEN", "") # Get API token from .env, else return empty string
    if not api_token:
        print("API_TOKEN is not set. Add it to your .env file.")
        sys.exit(1)

    """
    device_key = device["agent_name"]
    api_token = (cfg.get("device_tokens", {}).get(device_key, "")
                    or os.environ.get("API_TOKEN", ""))
    if not api_token:
        print(f"No API token saved for {device_key}.")
        print(f"    Find it in InfluxDB -> Load Data -> API Tokens")
        api_token = input("  InfluxDB API token: ").strip()
        if not api_token:
            print("Cannot connect without an API token.")
            # Recursive iteration, calls itself again
            return start_session(ixon_headers, devices, cfg)

        Testing
        # Save for next time
        device_tokens = cfg.get("device_tokens", {})
        device_tokens[device_key] = api_token
        cfg["device_tokens"] = device_tokens"""

    session = requests.Session()
    session.headers["Authorization"] = f"Token {api_token}"
    session.get(proxy_url, timeout=15)

    ## Verify connection — prompt for new token on 401
    test = session.get(f"{base_url}/api/v2/buckets", timeout=15)
    if test.status_code == 200:
        print(f"Connected to {device['agent_name']}.")
    elif test.status_code == 401:
        print(f"API token rejected (401).")
        print(f"    Generate a new token in InfluxDB -> Load Data -> API Tokens")

        sys.exit(1)

    return session, base_url

def _load_cached_login() -> tuple[dict, list[dict]] | None:
    """Return (headers, devices) if a cached IXON token is still valid."""
    try:
        data = json.loads(TOKEN_CACHE.read_text())
    except (FileNotFoundError, ValueError):
        return None
    if data["expires_at"] - time.time() < 60:      # expired, or less than a minute left
        return None
    return data["headers"], data["devices"]

def _save_cached_login(headers: dict, devices: list[dict], lifetime: int = 3600):
    TOKEN_CACHE.parent.mkdir(exist_ok=True)
    TOKEN_CACHE.write_text(json.dumps({
        "headers": headers,                         # includes the Bearer token + Api-Company
        "devices": devices,
        "expires_at": time.time() + lifetime,
    }))
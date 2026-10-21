"""Minimal client for the herdr socket API (newline-delimited JSON)."""

import json
import os
import socket

PLUGIN_ID = os.environ.get("HERDR_PLUGIN_ID", "81zi.reficus")
# Id used before the public release; settings and keybindings are migrated.
LEGACY_PLUGIN_ID = "local.reficus"


class HerdrError(RuntimeError):
    pass


def rpc(method, params=None):
    path = os.environ.get("HERDR_SOCKET_PATH")
    if not path:
        raise HerdrError(f"{method}: HERDR_SOCKET_PATH is not set (run inside herdr)")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect(path)
    try:
        req = {"id": "reficus", "method": method, "params": params or {}}
        sock.sendall((json.dumps(req) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
    finally:
        sock.close()
    try:
        resp = json.loads(buf)
    except ValueError:
        raise HerdrError(f"{method}: no valid response from herdr") from None
    if "error" in resp:
        raise HerdrError(f"{method}: {resp['error']}")
    return resp["result"]


def toast(title, body=None):
    try:
        rpc("notification.show", {"title": title, "body": body, "sound": "none"})
    except (HerdrError, OSError):
        pass


def find_key(value, key):
    """First string value for `key` anywhere in a nested JSON payload."""
    if isinstance(value, dict):
        if isinstance(value.get(key), str):
            return value[key]
        value = list(value.values())
    if isinstance(value, list):
        for item in value:
            found = find_key(item, key)
            if found:
                return found
    return None

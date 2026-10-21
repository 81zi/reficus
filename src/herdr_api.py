"""Minimal client for the herdr socket API (newline-delimited JSON).

herdr recommends calling it through the CLI at HERDR_BIN_PATH, but the CLI
has no command for layout.export or layout.set_split_ratio (only relative
`pane resize`), and a process per call would slow every focus change. So
this talks to the Unix socket directly; the plugin is macOS/Linux only.
"""

import json
import os
import socket

PLUGIN_ID = os.environ.get("HERDR_PLUGIN_ID", "reficus")
# Ids of earlier releases, newest first; settings and keybindings are migrated.
LEGACY_PLUGIN_IDS = ("81zi.reficus", "local.reficus")

TIMEOUT = 5


class HerdrError(RuntimeError):
    pass


def socket_path():
    path = os.environ.get("HERDR_SOCKET_PATH")
    if not path:
        raise HerdrError("HERDR_SOCKET_PATH is not set (run inside herdr)")
    if not hasattr(socket, "AF_UNIX"):
        raise HerdrError("the herdr socket API needs Unix sockets (macOS or Linux)")
    return path


def rpc(method, params=None):
    path = socket_path()
    req_id = f"reficus:{os.getpid()}:{method}"
    req = {"id": req_id, "method": method, "params": params or {}}
    buf = b""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(TIMEOUT)
            sock.connect(path)
            sock.sendall((json.dumps(req) + "\n").encode())
            while b"\n" not in buf:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
    except socket.timeout:
        raise HerdrError(f"{method}: herdr did not answer within {TIMEOUT}s") from None
    except OSError as exc:
        raise HerdrError(f"{method}: cannot reach herdr at {path}: {exc.strerror or exc}") from None
    try:
        resp = json.loads(buf.split(b"\n", 1)[0])
    except ValueError:
        raise HerdrError(f"{method}: no valid response from herdr") from None
    if not isinstance(resp, dict) or resp.get("id") not in (req_id, None):
        raise HerdrError(f"{method}: unexpected response from herdr")
    if "error" in resp:
        raise HerdrError(f"{method}: {resp['error']}")
    if "result" not in resp:
        raise HerdrError(f"{method}: response has no result")
    return resp["result"]


def toast(title, body=None):
    try:
        rpc("notification.show", {"title": title, "body": body, "sound": "none"})
    except HerdrError:
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

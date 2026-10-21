"""Manages Reficus keybindings inside herdr's config.toml.

Bindings live in a marked block that this module owns and rewrites:

    # >>> reficus keybindings ...
    [[keys.command]]
    ...
    # <<< reficus keybindings

Before every write the previous config.toml is copied to
config.toml.reficus-backup (and, the first time only, to
config.toml.reficus-original). Writes are atomic; if herdr rejects the new
config, the previous text is restored and reloaded.
"""

import os
import re
import shutil
import tempfile

from herdr_api import LEGACY_PLUGIN_ID, PLUGIN_ID, HerdrError, rpc

BLOCK_START = "# >>> reficus keybindings (managed by the Reficus plugin: edit them in its popup) >>>"
BLOCK_END = "# <<< reficus keybindings <<<"
KEY_RE = re.compile(r'^[a-z0-9]+(\+[^\s+"\\]+)*$')

ACTION_LABELS = {
    "settings": "Open settings popup",
    "toggle": "Toggle on/off",
    "cycle-profile": "Next profile",
    "resume": "Resume tab",
    "restore": "Restore tab layout",
    "equalize": "Equalize tab",
}

# herdr 0.8.2 default bindings (keys.* in the config reference), used for
# conflict checks. User overrides from [keys] replace these.
HERDR_DEFAULT_KEYS = {
    "help": "prefix+?", "settings": "prefix+s", "new_workspace": "prefix+shift+n",
    "new_worktree": "prefix+shift+g", "rename_workspace": "prefix+shift+w",
    "close_workspace": "prefix+shift+d", "workspace_picker": "prefix+w", "goto": "prefix+g",
    "detach": "prefix+q", "reload_config": "prefix+shift+r", "open_notification_target": "prefix+o",
    "remote_image_paste": "ctrl+v", "new_tab": "prefix+c", "rename_tab": "prefix+shift+t",
    "previous_tab": "prefix+p", "next_tab": "prefix+n", "close_tab": "prefix+shift+x",
    "rename_pane": "prefix+shift+p", "edit_scrollback": "prefix+e", "copy_mode": "prefix+[",
    "focus_pane_left": "prefix+h", "focus_pane_down": "prefix+j", "focus_pane_up": "prefix+k",
    "focus_pane_right": "prefix+l", "swap_pane_left": "prefix+shift+h",
    "swap_pane_down": "prefix+shift+j", "swap_pane_up": "prefix+shift+k",
    "swap_pane_right": "prefix+shift+l", "cycle_pane_next": "prefix+tab",
    "cycle_pane_previous": "prefix+shift+tab", "split_vertical": "prefix+v",
    "split_horizontal": "prefix+minus", "close_pane": "prefix+x", "zoom": "prefix+z",
    "resize_mode": "prefix+r", "toggle_sidebar": "prefix+b",
}
SWITCH_TAB_KEYS = {"prefix+%d" % i: "switch_tab" for i in range(1, 10)}


def config_toml_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "herdr", "config.toml")


def normalize(key):
    return (key or "").strip().lower().replace(" ", "")


def validate(key):
    key = normalize(key)
    if not key or not KEY_RE.match(key):
        return "invalid key %r (examples: prefix+shift+f, prefix+f, f12, alt+r)" % key
    if key.split("+")[-1] in ("shift", "ctrl", "alt", "prefix"):
        return "key %r has no final key" % key
    return None


def _read_text():
    try:
        with open(config_toml_path()) as f:
            return f.read()
    except OSError:
        return ""


def _parse_toml(text):
    try:
        import tomllib
    except ImportError:  # Python < 3.11: conflict checks fall back to defaults
        return {}
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}


def used_keys(own_bindings):
    """Map key -> who uses it, excluding Reficus' own bindings."""
    data = _parse_toml(_read_text())
    used = {}
    defaults = dict(HERDR_DEFAULT_KEYS)
    user_keys = data.get("keys", {}) if isinstance(data.get("keys"), dict) else {}
    for name, value in user_keys.items():
        if name not in ("command", "prefix") and isinstance(value, (str, list)):
            defaults[name] = value
    for name, value in defaults.items():
        for k in value if isinstance(value, list) else [value]:
            if isinstance(k, str) and k != "unset":
                used[normalize(k)] = "herdr %s" % name
    for k, name in SWITCH_TAB_KEYS.items():
        used.setdefault(k, "herdr %s" % name)
    for cmd in user_keys.get("command", []) if isinstance(user_keys.get("command"), list) else []:
        command = str(cmd.get("command", ""))
        if _action_of(command):
            continue
        used[normalize(cmd.get("key"))] = "custom command %r" % (cmd.get("description") or command[:40])
    for action, key in own_bindings.items():
        if key:
            used[normalize(key)] = "Reficus %s" % ACTION_LABELS.get(action, action)
    return used


def conflict(action, key, bindings):
    others = {a: k for a, k in bindings.items() if a != action}
    return used_keys(others).get(normalize(key))


def _action_of(command):
    """Action name of a `<plugin id>.<action>` command, for our current or legacy id."""
    for plugin_id in (PLUGIN_ID, LEGACY_PLUGIN_ID):
        if command.startswith(plugin_id + "."):
            return command[len(plugin_id) + 1:]
    return None


def _strip_ours(text):
    """Remove the managed block and any hand-written Reficus [[keys.command]].

    Returns (remaining lines, {action: key} of the hand-written entries)."""
    lines = text.splitlines()
    out, found, i = [], {}, 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == BLOCK_START:
            while i < len(lines) and lines[i].strip() != BLOCK_END:
                i += 1
            i += 1
            continue
        if line.strip() == "[[keys.command]]":
            j = i + 1
            while j < len(lines) and not lines[j].lstrip().startswith("["):
                j += 1
            chunk = "\n".join(lines[i:j])
            command = re.search(r'^\s*command\s*=\s*"([^"]*)"', chunk, re.M)
            action = _action_of(command.group(1)) if command else None
            if action:
                key = re.search(r'^\s*key\s*=\s*"([^"]*)"', chunk, re.M)
                if key and action in ACTION_LABELS:
                    found[action] = normalize(key.group(1))
                while out and out[-1].lstrip().startswith("#") and "reficus" in out[-1].lower():
                    out.pop()
                i = j
                continue
        out.append(line)
        i += 1
    while out and not out[-1].strip():
        out.pop()
    return out, found


def render_block(bindings):
    block = [BLOCK_START]
    for action in ACTION_LABELS:
        key = bindings.get(action)
        if not key:
            continue
        block += [
            "[[keys.command]]",
            'key = "%s"' % normalize(key),
            'type = "plugin_action"',
            'command = "%s.%s"' % (PLUGIN_ID, action),
            'description = "reficus: %s"' % ACTION_LABELS[action].lower(),
            "",
        ]
    if block[-1] == "":
        block.pop()
    block.append(BLOCK_END)
    return block


def has_reficus_binding():
    text = _read_text()
    return BLOCK_START in text or any('"%s.' % i in text for i in (PLUGIN_ID, LEGACY_PLUGIN_ID))


def has_legacy_binding():
    return ('"%s.' % LEGACY_PLUGIN_ID) in _read_text()


def adopt(bindings):
    """Hand-written Reficus bindings outside the managed block fill actions
    that have no binding yet, so rewriting the block never drops them."""
    _, found = _strip_ours(_read_text())
    merged = dict(bindings)
    for action, key in found.items():
        if not merged.get(action):
            merged[action] = key
    return merged


def _write_atomic(path, text):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".config.toml.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        if os.path.exists(path):
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def write(bindings):
    """Rewrite the managed block and reload herdr.

    Returns (status message, bindings actually written)."""
    # Write through a symlink (dotfiles setups) instead of replacing it.
    path = os.path.realpath(config_toml_path())
    original = _read_text()
    lines, _ = _strip_ours(original)
    bindings = adopt(bindings)
    if lines:
        lines.append("")
    if any(bindings.values()):
        lines += render_block(bindings)
    new_text = "\n".join(lines) + "\n"
    if new_text == original:
        return "keybindings unchanged", bindings
    if original:
        if not os.path.exists(path + ".reficus-original"):
            shutil.copyfile(path, path + ".reficus-original")
        shutil.copyfile(path, path + ".reficus-backup")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _write_atomic(path, new_text)
    try:
        result = rpc("server.reload_config")
    except HerdrError as exc:
        result = {"diagnostics": [str(exc)]}
    diagnostics = result.get("diagnostics") or []
    if diagnostics:
        if original:
            _write_atomic(path, original)
            try:
                rpc("server.reload_config")
            except HerdrError:
                pass
        raise ValueError("herdr rejected the config, restored backup: %s" % diagnostics)
    return "keybindings saved, herdr config reloaded", bindings

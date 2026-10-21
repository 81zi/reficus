"""Config (user-editable, config.json) and runtime state (state.json).

The top-level tunables are the *working set* the engine uses. A profile is a
saved copy of all tunables; selecting it copies its values into the working
set. Profile "manual" means the working set is not tied to a saved profile.
"""

import copy
import fcntl
import json
import os
import shutil
import tempfile
from contextlib import contextmanager

from herdr_api import LEGACY_PLUGIN_ID, PLUGIN_ID

STRATEGIES = ["weighted", "golden", "fixed", "accordion", "ancestors", "equal"]
AXES = ["both", "horizontal", "vertical"]
NARROW_MODES = ["zoom", "equal"]
SCOPE_MODES = ["all", "allow", "deny"]
MANUAL_MODES = ["override", "keep", "pause"]
MANUAL_PROFILE = "manual"

TUNABLE_DEFAULTS = {
    "strategy": "weighted",
    "ratio": 0.65,
    "fixed_cols": 120,
    "fixed_rows": 40,
    "min_cols": 20,
    "min_rows": 5,
    "accordion_cols": 12,
    "accordion_rows": 3,
    "axis": "both",
    "dwell_ms": 120,
    "animate_frames": 0,
    "on_manual_resize": "override",
    "narrow_cols": 0,
    "narrow_mode": "zoom",
    "agent_boost": 1.0,
    "idle_weight": 1.0,
}
TUNABLES = list(TUNABLE_DEFAULTS)


def _profile(**overrides):
    values = dict(TUNABLE_DEFAULTS)
    values.update(overrides)
    return values


BUILTIN_PROFILES = {
    "coding": _profile(),
    "review": _profile(ratio=0.8),
    "monitor": _profile(strategy="equal", ratio=0.5),
}

# Actions that can get a keybinding, in popup order.
KEY_ACTIONS = ["settings", "toggle", "cycle-profile", "resume", "restore", "equalize"]

DEFAULTS = dict(
    TUNABLE_DEFAULTS,
    enabled=True,
    profile="coding",
    profiles=copy.deepcopy(BUILTIN_PROFILES),
    rules=[],
    scope_mode="all",
    scope_workspaces=[],
    scope_tabs=[],
    keybindings=dict({action: None for action in KEY_ACTIONS}, settings="prefix+shift+f"),
    keybindings_initialized=False,
)

# Defaults for a new rule. `match` is a regex searched in the pane's agent
# name and foreground process names/command lines. Null fields are ignored.
RULE_DEFAULTS = {
    "match": "",
    "ratio": None,
    "min_cols": None,
    "min_rows": None,
    "max_cols": None,
    "max_rows": None,
}


def _plugin_file(env_key, fallback_parent, name):
    """Path of `name` in this plugin's config/state dir. The first time it is
    missing, a copy is taken from the pre-release `local.reficus` dir next to it."""
    directory = os.environ.get(env_key) or os.path.join(os.path.expanduser(fallback_parent), PLUGIN_ID)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name)
    legacy = os.path.join(os.path.dirname(os.path.abspath(directory)), LEGACY_PLUGIN_ID, name)
    if not os.path.exists(path) and os.path.exists(legacy) and os.path.abspath(legacy) != os.path.abspath(path):
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-")
        os.close(fd)
        shutil.copyfile(legacy, tmp)
        os.replace(tmp, path)
    return path


def config_path():
    return _plugin_file("HERDR_PLUGIN_CONFIG_DIR", "~/.config/herdr/plugins/config", "config.json")


def state_path():
    return _plugin_file("HERDR_PLUGIN_STATE_DIR", "~/.local/state/herdr/plugins", "state.json")


def _read_json(path):
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _migrate(cfg, user):
    given = set(user)
    # 0.2: `respect_manual` bool -> `on_manual_resize`.
    if "on_manual_resize" not in user and "respect_manual" in user:
        cfg["on_manual_resize"] = "pause" if user["respect_manual"] else "override"
        given.add("on_manual_resize")
    cfg.pop("respect_manual", None)
    # 0.2: profiles held only strategy/ratio on top of global values.
    for name, values in cfg["profiles"].items():
        full = {key: cfg[key] for key in TUNABLES}
        full.update({k: v for k, v in values.items() if k in TUNABLE_DEFAULTS})
        cfg["profiles"][name] = full
    # Tunables missing from the file (hand-written partial configs, 0.2
    # files) come from the active profile; the ones in the file win.
    if cfg["profile"] in cfg["profiles"]:
        saved = cfg["profiles"][cfg["profile"]]
        cfg.update({key: saved[key] for key in TUNABLES if key not in given})


def load_config():
    cfg = copy.deepcopy(DEFAULTS)
    user = _read_json(config_path())
    for key, value in user.items():
        if key == "profiles" and isinstance(value, dict):
            cfg["profiles"] = value
        elif key == "keybindings" and isinstance(value, dict):
            cfg["keybindings"].update({a: k for a, k in value.items() if a in KEY_ACTIONS})
        else:
            cfg[key] = value
    _migrate(cfg, user)
    if cfg["profile"] != MANUAL_PROFILE and cfg["profile"] not in cfg["profiles"]:
        cfg["profile"] = MANUAL_PROFILE
    return cfg


def save_config(cfg):
    _write_json(config_path(), cfg)


def effective(cfg):
    eff = dict(cfg)
    eff["ratio"] = min(max(float(eff["ratio"]), 0.5), 0.95)
    return eff


# ---- profiles -----------------------------------------------------------

def apply_profile(cfg, name):
    if name != MANUAL_PROFILE:
        cfg.update(copy.deepcopy(cfg["profiles"][name]))
    cfg["profile"] = name


def profile_modified(cfg):
    name = cfg["profile"]
    if name == MANUAL_PROFILE:
        return False
    saved = cfg["profiles"].get(name, {})
    return any(cfg[key] != saved.get(key) for key in TUNABLES)


def save_profile(cfg, name):
    cfg["profiles"][name] = {key: cfg[key] for key in TUNABLES}
    cfg["profile"] = name


def delete_profile(cfg, name):
    cfg["profiles"].pop(name, None)
    if cfg["profile"] == name:
        cfg["profile"] = MANUAL_PROFILE


# ---- runtime state ------------------------------------------------------

@contextmanager
def locked_state():
    """Exclusive read-modify-write of state.json across hook processes."""
    path = state_path()
    with open(path + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = _read_json(path)
        state.setdefault("tabs", {})
        state.pop("pins", None)
        yield state
        _write_json(path, state)


def read_state():
    state = _read_json(state_path())
    state.setdefault("tabs", {})
    return state


@contextmanager
def apply_lock():
    """Serializes layout changes so concurrent hooks don't interleave."""
    with open(state_path() + ".apply.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield

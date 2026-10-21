"""herdr reficus plugin entry point.

Usage: reficus.py <command>
  hook            event hooks (dispatches on HERDR_PLUGIN_EVENT)
  open-settings   open the settings popup
  settings        settings TUI (runs inside the popup)
  ensure-keys     startup: write the default keybindings once
  toggle | equalize | resume | restore | cycle-profile
"""

import json
import os
import sys
import traceback

import core
import settings
from herdr_api import PLUGIN_ID, rpc, toast


def event_payload():
    try:
        return json.loads(os.environ.get("HERDR_PLUGIN_EVENT_JSON") or "{}")
    except ValueError:
        return {}


def hook():
    event = os.environ.get("HERDR_PLUGIN_EVENT", "")
    payload = event_payload()
    if event == "pane.focused":
        core.on_focused(payload)
    elif event in ("pane.created", "pane.closed"):
        core.on_structure_changed(payload)
    elif event == "pane.agent_status_changed":
        core.on_agent_status(payload)


def open_settings():
    rpc("plugin.pane.open", {
        "plugin_id": PLUGIN_ID,
        "entrypoint": "settings",
    })


def toggle():
    cfg = settings.load_config()
    cfg["enabled"] = not cfg["enabled"]
    settings.save_config(cfg)
    if cfg["enabled"]:
        core.reset_tracking()
        core.apply(pane_id=core.current_pane())
    else:
        core.restore_all()
    toast("Reficus " + ("on" if cfg["enabled"] else "off"))


def cycle_profile():
    cfg = settings.load_config()
    names = list(cfg["profiles"])
    current = names.index(cfg["profile"]) if cfg["profile"] in names else -1
    settings.apply_profile(cfg, names[(current + 1) % len(names)])
    settings.save_config(cfg)
    core.apply(pane_id=core.current_pane())
    toast("Reficus profile: " + cfg["profile"])


def tab_of(pane_id):
    return core.export(pane_id=pane_id)["tab_id"]


def resume():
    pane_id = core.current_pane()
    core.reset_tracking(tab_of(pane_id))
    core.apply(pane_id=pane_id)
    toast("Reficus resumed for this tab")


def restore():
    pane_id = core.current_pane()
    tab_id = tab_of(pane_id)
    core.set_paused(tab_id, True)
    ok = core.restore_tab(tab_id)
    toast("Reficus paused", "Layout restored." if ok else "No saved layout for this tab.")


def ensure_keys():
    """Startup: put the default bindings into config.toml (once), and move
    bindings that still call the pre-release plugin id to the current one."""
    import keys
    cfg = settings.load_config()
    if cfg["keybindings_initialized"]:
        if keys.has_legacy_binding():
            message, cfg["keybindings"] = keys.write(cfg["keybindings"])
            settings.save_config(cfg)
            print(message)
        return
    bindings = {a: k for a, k in cfg["keybindings"].items()
                if k and (keys.has_reficus_binding() or not keys.conflict(a, k, {}))}
    message, written = keys.write(bindings)
    print(message)
    cfg["keybindings"] = {a: written.get(a) for a in cfg["keybindings"]}
    cfg["keybindings_initialized"] = True
    settings.save_config(cfg)


COMMANDS = {
    "hook": hook,
    "open-settings": open_settings,
    "toggle": toggle,
    "equalize": lambda: core.apply(pane_id=core.current_pane(), force_strategy="equal", ignore_pause=True),
    "resume": resume,
    "restore": restore,
    "cycle-profile": cycle_profile,
    "ensure-keys": ensure_keys,
}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "hook"
    if cmd == "settings":
        import settings_tui
        settings_tui.run()
        return
    try:
        COMMANDS[cmd]()
    except Exception:
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

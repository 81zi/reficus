"""Reads live herdr state, plans ratios with engine.Planner and applies them."""

import json
import os
import re
import time

import engine
import keys
import settings
from herdr_api import PLUGIN_ID, HerdrError, find_key, rpc, toast

MANUAL_TOLERANCE = 0.01
APPLY_TOLERANCE = 0.004
FRAME_SECONDS = 0.012


def path_key(path):
    return "".join("1" if step else "0" for step in path)


def key_path(key):
    return [ch == "1" for ch in key]


def export(pane_id=None, tab_id=None):
    params = {"pane_id": pane_id} if pane_id else {"tab_id": tab_id} if tab_id else {}
    return rpc("layout.export", params)["layout"]


def pane_layout(pane_id):
    return rpc("pane.layout", {"pane_id": pane_id})["layout"]


def current_pane():
    pane_id = os.environ.get("HERDR_PANE_ID")
    if pane_id:
        return pane_id
    try:
        ctx = json.loads(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON") or "{}")
        if ctx.get("focused_pane_id"):
            return ctx["focused_pane_id"]
    except ValueError:
        pass
    return rpc("pane.current")["pane"]["pane_id"]


def in_scope(cfg, workspace_id, tab_id):
    mode = cfg["scope_mode"]
    if mode == "all":
        return True
    ws = rpc("workspace.get", {"workspace_id": workspace_id}).get("workspace", {})
    tab = rpc("tab.get", {"tab_id": tab_id}).get("tab", {})
    ws_hit = any(w in (ws.get("workspace_id"), ws.get("label")) for w in cfg["scope_workspaces"])
    tab_hit = any(re.search(pat, tab.get("label") or "") for pat in cfg["scope_tabs"] if pat)
    hit = ws_hit or tab_hit
    return hit if mode == "allow" else not hit


def match_rule(rules, candidates):
    for rule in rules:
        pattern = rule.get("match")
        if not pattern:
            continue
        try:
            if any(re.search(pattern, c) for c in candidates if c):
                return rule
        except re.error:
            continue
    return None


def pane_infos(cfg, state, workspace_id, ids):
    listed = {p["pane_id"]: p for p in rpc("pane.list", {"workspace_id": workspace_id})["panes"]}
    infos = {}
    for pane_id in ids:
        pane = listed.get(pane_id, {})
        rule = None
        if cfg["rules"]:
            candidates = [pane.get("agent") or ""]
            try:
                info = rpc("pane.process_info", {"pane_id": pane_id})["process_info"]
                for proc in info.get("foreground_processes", []):
                    candidates += [proc.get("name"), proc.get("argv0"), proc.get("cmdline")]
            except HerdrError:
                pass
            rule = match_rule(cfg["rules"], candidates)
        infos[pane_id] = engine.PaneInfo(pane.get("agent_status"), rule)
    return infos


def set_ratios(tab_id, start, targets, frames):
    changed = {p: r for p, r in targets.items() if abs(r - start.get(p, r)) > APPLY_TOLERANCE}
    if not changed:
        return
    frames = max(int(frames), 1)
    for step in range(1, frames + 1):
        for path, target in changed.items():
            ratio = start[path] + (target - start[path]) * step / frames
            rpc("layout.set_split_ratio", {"tab_id": tab_id, "path": list(path), "ratio": round(ratio, 4)})
        if step < frames:
            time.sleep(FRAME_SECONDS)


def update_tab(tab_id, **fields):
    with settings.locked_state() as state:
        state["tabs"].setdefault(tab_id, {}).update(fields)


def manual_changes(tab, sig, current):
    """Split paths whose ratio differs from what we last applied to the same
    pane structure, i.e. splits the user resized by hand."""
    last = tab.get("last")
    if not last or tab.get("sig") != sig:
        return []
    return [path_key(p) for p, r in current.items() if abs(r - last.get(path_key(p), r)) > MANUAL_TOLERANCE]


def apply(pane_id=None, tab_id=None, expect_focus=None, force_strategy=None, ignore_pause=False):
    """Recomputes and applies ratios for the tab containing pane_id/tab_id."""
    cfg = settings.effective(settings.load_config())
    if not cfg["enabled"] and not force_strategy:
        return
    if force_strategy:
        cfg["strategy"] = force_strategy

    with settings.apply_lock():
        exp = export(pane_id, tab_id)
        tab_id, focused = exp["tab_id"], exp.get("focused_pane_id")
        if not focused or (expect_focus and focused != expect_focus):
            return
        state = settings.read_state()
        tab = state["tabs"].get(tab_id, {})
        if tab.get("paused") and cfg["on_manual_resize"] == "pause" and not ignore_pause:
            return
        if not force_strategy and not in_scope(cfg, exp["workspace_id"], tab_id):
            return

        lay = pane_layout(focused)
        width = lay["area"]["width"]
        narrow = bool(cfg["narrow_cols"]) and width < cfg["narrow_cols"]
        if narrow and cfg["narrow_mode"] == "zoom" and not force_strategy:
            if not lay["zoomed"] or tab.get("narrow_zoomed"):
                rpc("pane.zoom", {"pane_id": focused, "mode": "on"})
                update_tab(tab_id, narrow_zoomed=True, narrow=True)
            return
        if tab.get("narrow_zoomed"):
            rpc("pane.zoom", {"pane_id": focused, "mode": "off"})
            update_tab(tab_id, narrow_zoomed=False)
            lay = pane_layout(focused)
        if narrow:
            cfg["strategy"] = "equal"
        if lay["zoomed"]:
            return

        root = exp["root"]
        sig = engine.signature(root)
        start = engine.current_ratios(root)
        fields = {"narrow": narrow, "sig": sig}
        frozen = set(tab.get("frozen", [])) if tab.get("sig") == sig else set()
        manual = [] if force_strategy or ignore_pause else manual_changes(tab, sig, start)
        if manual and cfg["on_manual_resize"] == "pause":
            update_tab(tab_id, paused=True)
            toast("Reficus paused", "Manual resize detected in this tab. Resume from the Reficus popup.")
            return
        if manual and cfg["on_manual_resize"] == "keep":
            frozen.update(manual)
        fields["frozen"] = sorted(frozen)
        if tab.get("sig") != sig or "snapshot" not in tab:
            fields["snapshot"] = {path_key(p): r for p, r in start.items()}

        infos = pane_infos(cfg, state, exp["workspace_id"], engine.pane_ids(root))
        frozen_paths = [tuple(key_path(k)) for k in frozen]
        targets = engine.Planner(cfg, focused, infos, frozen_paths).plan(
            root, lay["area"]["width"], lay["area"]["height"]
        )
        update_tab(tab_id, **fields)
        set_ratios(tab_id, start, targets, cfg["animate_frames"] or 1)
        # Store what herdr actually kept (it may clamp), so manual-resize
        # detection compares against reality.
        actual = engine.current_ratios(export(tab_id=tab_id)["root"])
        update_tab(tab_id, last={path_key(p): r for p, r in actual.items()})


def on_structure_changed(event):
    """pane.created / pane.closed: re-plan the affected tab."""
    if not settings.load_config()["enabled"]:
        return
    pane_id, tab_id = find_key(event, "pane_id"), find_key(event, "tab_id")
    try:
        apply(pane_id=pane_id) if pane_id else apply(tab_id=tab_id)
    except HerdrError:
        # The closed pane is gone; fall back to its tab or the active pane.
        apply(tab_id=tab_id) if tab_id else apply(pane_id=current_pane())


def reset_tracking(tab_id=None):
    """Forget applied ratios, pauses and frozen splits; next apply starts fresh."""
    with settings.locked_state() as state:
        tabs = [tab_id] if tab_id else list(state["tabs"])
        for tid in tabs:
            tab = state["tabs"].setdefault(tid, {})
            tab.pop("last", None)
            tab["paused"] = False
            tab["frozen"] = []


def on_focused(event):
    pane_id = find_key(event, "pane_id") or os.environ.get("HERDR_PANE_ID")
    if not pane_id:
        return
    cfg = settings.load_config()
    if not cfg["enabled"]:
        return
    dwell = max(int(cfg["dwell_ms"]), 0) / 1000.0
    if dwell:
        token = "%s@%f" % (pane_id, time.time())
        with settings.locked_state() as state:
            state["focus_token"] = token
        time.sleep(dwell)
        if settings.read_state().get("focus_token") != token:
            return
    apply(pane_id=pane_id, expect_focus=pane_id)


def on_agent_status(event):
    cfg = settings.effective(settings.load_config())
    if float(cfg["agent_boost"]) == 1.0 and float(cfg["idle_weight"]) == 1.0:
        return
    pane_id = find_key(event, "pane_id")
    if pane_id:
        apply(pane_id=pane_id)


def restore_tab(tab_id):
    tab = settings.read_state()["tabs"].get(tab_id, {})
    if tab.get("narrow_zoomed"):
        try:
            rpc("pane.zoom", {"pane_id": export(tab_id=tab_id)["focused_pane_id"], "mode": "off"})
        except HerdrError:
            pass
        update_tab(tab_id, narrow_zoomed=False)
    snapshot = tab.get("snapshot")
    if not snapshot:
        return False
    try:
        root = export(tab_id=tab_id)["root"]
    except HerdrError:
        return False
    if engine.signature(root) != tab.get("sig"):
        return False
    targets = {tuple(key_path(k)): r for k, r in snapshot.items()}
    with settings.apply_lock():
        set_ratios(tab_id, engine.current_ratios(root), targets, 1)
    return True


def restore_all():
    for tab_id in list(settings.read_state()["tabs"]):
        restore_tab(tab_id)


def set_paused(tab_id, paused):
    update_tab(tab_id, paused=paused)


def cleanup():
    """Undo what Reficus changed before `herdr plugin uninstall`: restore saved
    layouts, remove its keybindings, disable it so no hook recreates state,
    then delete its config and state. Returns a status message."""
    restore_all()
    message = keys.remove()
    rpc("plugin.disable", {"plugin_id": PLUGIN_ID})
    settings.remove_data()
    return "layouts restored, %s, plugin disabled, settings deleted" % message

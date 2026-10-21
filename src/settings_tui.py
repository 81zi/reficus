"""Curses settings popup. Every change is saved and applied immediately."""

import curses
import os

import core
import keys
import settings

HELP = "↑↓ move  ←→ change  enter edit  e equalize  r resume  x restore  q close"
RULES_HELP = "↑↓ move  enter edit  a add  d delete  q back"
RULE_HELP = "↑↓ move  ←→ change  enter edit (empty = unset)  q back"


def row(key, label, kind, **opts):
    return dict(key=key, label=label, kind=kind, **opts)


MAIN_ROWS = [
    ("General", [
        row("enabled", "Enabled", "bool"),
    ]),
    ("Profile", [
        row("profile", "Active profile", "profile"),
        row("profile_save", "Save to active profile", "profile_save"),
        row("profile_save_as", "Save as new profile…", "profile_save_as"),
        row("profile_revert", "Revert unsaved changes", "profile_revert"),
        row("profile_delete", "Delete active profile", "profile_delete"),
    ]),
    ("Sizing", [
        row("strategy", "Strategy", "choice", choices=settings.STRATEGIES),
        row("ratio", "Focused share", "float", lo=0.5, hi=0.95, step=0.05),
        row("fixed_cols", "Fixed cols", "int", lo=20, hi=400, step=5),
        row("fixed_rows", "Fixed rows", "int", lo=5, hi=200, step=2),
        row("min_cols", "Min cols", "int", lo=0, hi=200, step=2),
        row("min_rows", "Min rows", "int", lo=0, hi=100, step=1),
        row("accordion_cols", "Accordion strip cols", "int", lo=1, hi=60, step=1),
        row("accordion_rows", "Accordion strip rows", "int", lo=1, hi=30, step=1),
        row("axis", "Axis", "choice", choices=settings.AXES),
    ]),
    ("Behaviour", [
        row("dwell_ms", "Dwell delay ms", "int", lo=0, hi=1000, step=20),
        row("animate_frames", "Animation frames (0=off)", "int", lo=0, hi=12, step=1),
        row("on_manual_resize", "On manual resize", "choice", choices=settings.MANUAL_MODES),
        row("narrow_cols", "Narrow below cols (0=off)", "int", lo=0, hi=400, step=10),
        row("narrow_mode", "Narrow mode", "choice", choices=settings.NARROW_MODES),
    ]),
    ("Agents (weighted/accordion/ancestors)", [
        row("agent_boost", "Blocked agent weight", "float", lo=1.0, hi=4.0, step=0.1),
        row("idle_weight", "Idle/done agent weight", "float", lo=0.2, hi=1.0, step=0.1),
    ]),
    ("Rules", [
        row("rules", "Process rules", "rules"),
    ]),
    ("Scope", [
        row("scope_mode", "Scope mode", "choice", choices=settings.SCOPE_MODES),
        row("scope_workspaces", "Workspaces (id/label)", "list"),
        row("scope_tabs", "Tab label regexes", "list"),
    ]),
    ("Keybindings (enter to set, empty = none)", [
        row(action, keys.ACTION_LABELS[action], "key") for action in settings.KEY_ACTIONS
    ]),
    ("Uninstall", [
        row("cleanup", "Clean up and disable…", "cleanup"),
    ]),
]

RULE_ROWS = [
    ("Rule", [
        row("match", "Match regex", "text"),
        row("ratio", "Focused share", "float", lo=0.5, hi=0.95, step=0.05, nullable=True),
        row("min_cols", "Min cols", "int", lo=0, hi=300, step=5, nullable=True),
        row("min_rows", "Min rows", "int", lo=0, hi=100, step=1, nullable=True),
        row("max_cols", "Max cols", "int", lo=5, hi=400, step=5, nullable=True),
        row("max_rows", "Max rows", "int", lo=2, hi=200, step=2, nullable=True),
    ]),
]

PROFILE_ACTIONS = ("profile_save", "profile_save_as", "profile_revert", "profile_delete")


class App:
    def __init__(self, scr):
        self.scr = scr
        self.cfg = settings.load_config()
        # Show hand-written bindings too; the next key change adopts them.
        self.cfg["keybindings"] = keys.adopt(self.cfg["keybindings"])
        self.status = ""
        try:
            self.pane_id = core.current_pane()
            self.tab_id = core.export(pane_id=self.pane_id)["tab_id"]
        except Exception as exc:  # popup still works for editing config
            self.pane_id, self.tab_id = None, None
            self.status = "no pane context: %s" % exc

    # ---- data access -------------------------------------------------
    def put(self, r, target, value):
        target[r["key"]] = value
        self.commit()

    def commit(self, status="saved"):
        settings.save_config(self.cfg)
        self.status = status
        if not self.pane_id:
            return
        try:
            core.apply(pane_id=self.pane_id)
        except Exception as exc:
            self.status = "%s; apply failed: %s" % (status, exc)

    def profile_label(self):
        name = self.cfg["profile"]
        if name == settings.MANUAL_PROFILE:
            return "manual (not saved as a profile)"
        return name + ("  * unsaved changes" if settings.profile_modified(self.cfg) else "")

    def display(self, r, target):
        kind = r["kind"]
        if kind == "profile":
            return self.profile_label()
        if kind in PROFILE_ACTIONS or kind == "cleanup":
            return ""
        if kind == "key":
            return self.cfg["keybindings"].get(r["key"]) or "—"
        if kind == "rules":
            return "%d rule(s) →" % len(self.cfg["rules"])
        value = target.get(r["key"])
        if value is None:
            return "—"
        if kind == "bool":
            return "on" if value else "off"
        if kind == "float":
            return "%.2f" % value
        if kind == "list":
            return ", ".join(value) or "—"
        return str(value)

    # ---- editing -----------------------------------------------------
    def step(self, r, target, direction):
        kind = r["kind"]
        value = target.get(r["key"])
        if kind == "profile":
            self.switch_profile(direction)
        elif kind == "bool":
            self.put(r, target, not value)
        elif kind == "choice":
            opts = r["choices"]
            idx = opts.index(value) if value in opts else 0
            self.put(r, target, opts[(idx + direction) % len(opts)])
        elif kind in ("int", "float"):
            if value is None:
                value = r["lo"]
            elif r.get("nullable") and direction < 0 and value <= r["lo"]:
                self.put(r, target, None)
                return
            else:
                value = min(max(value + direction * r["step"], r["lo"]), r["hi"])
            self.put(r, target, round(value, 2) if kind == "float" else int(value))

    def edit(self, r, target):
        kind = r["kind"]
        if kind in ("bool", "choice", "profile"):
            self.step(r, target, 1)
        elif kind in PROFILE_ACTIONS:
            self.profile_action(kind)
        elif kind == "key":
            self.edit_key(r["key"])
        elif kind == "cleanup":
            self.cleanup()
        elif kind == "rules":
            self.rules_screen()
        elif kind == "list":
            text = self.prompt(r["label"] + " (comma separated): ", ", ".join(target.get(r["key"])))
            if text is not None:
                self.put(r, target, [t.strip() for t in text.split(",") if t.strip()])
        elif kind == "text":
            text = self.prompt(r["label"] + ": ", target.get(r["key"]) or "")
            if text is not None:
                self.put(r, target, text)
        else:
            current = target.get(r["key"])
            text = self.prompt(r["label"] + ": ", "" if current is None else str(current))
            if text is None:
                return
            if text == "" and r.get("nullable"):
                self.put(r, target, None)
                return
            try:
                value = float(text) if kind == "float" else int(text)
            except ValueError:
                self.status = "not a number"
                return
            self.put(r, target, min(max(value, r["lo"]), r["hi"]))

    # ---- profiles ----------------------------------------------------
    def switch_profile(self, direction):
        names = list(self.cfg["profiles"]) + [settings.MANUAL_PROFILE]
        current = self.cfg["profile"]
        target = names[(names.index(current) + direction) % len(names)]
        if target != settings.MANUAL_PROFILE and settings.profile_modified(self.cfg):
            if not self.confirm("Discard unsaved changes to '%s'?" % current):
                return
        settings.apply_profile(self.cfg, target)
        self.commit("profile: %s" % target)

    def profile_action(self, kind):
        name = self.cfg["profile"]
        manual = name == settings.MANUAL_PROFILE
        if kind == "profile_save" and not manual:
            settings.save_profile(self.cfg, name)
            self.commit("saved profile '%s'" % name)
        elif kind == "profile_save_as" or (kind == "profile_save" and manual):
            new = self.prompt("New profile name: ", "")
            new = (new or "").strip()
            if not new:
                return
            if new == settings.MANUAL_PROFILE:
                self.status = "'manual' is reserved"
                return
            if new in self.cfg["profiles"] and not self.confirm("Overwrite profile '%s'?" % new):
                return
            settings.save_profile(self.cfg, new)
            self.commit("saved profile '%s'" % new)
        elif kind == "profile_revert" and not manual:
            settings.apply_profile(self.cfg, name)
            self.commit("reverted to '%s'" % name)
        elif kind == "profile_delete" and not manual:
            if len(self.cfg["profiles"]) <= 1:
                self.status = "keep at least one profile"
            elif self.confirm("Delete profile '%s'? Current values stay as 'manual'." % name):
                settings.delete_profile(self.cfg, name)
                self.commit("deleted '%s'" % name)
        else:
            self.status = "no saved profile active (manual)"

    # ---- keybindings -------------------------------------------------
    def edit_key(self, action):
        bindings = dict(self.cfg["keybindings"])
        text = self.prompt("Key for '%s' (empty = none): " % keys.ACTION_LABELS[action],
                           bindings.get(action) or "")
        if text is None:
            return
        key = keys.normalize(text) or None
        if key:
            error = keys.validate(key)
            if error:
                self.status = error
                return
            used_by = keys.conflict(action, key, bindings)
            if used_by:
                self.status = "%s is already used by %s" % (key, used_by)
                return
        elif action == "settings" and not self.confirm(
            "Unbind the popup key? Reopen later with: herdr plugin action invoke %s.settings" % keys.PLUGIN_ID
        ):
            return
        bindings[action] = key
        try:
            message, bindings = keys.write(bindings)
        except Exception as exc:
            self.status = str(exc)
            return
        self.cfg["keybindings"] = bindings
        self.cfg["keybindings_initialized"] = True
        settings.save_config(self.cfg)
        self.status = message

    # ---- uninstall ---------------------------------------------------
    def cleanup(self):
        if not self.confirm("Undo all changes, disable Reficus and delete its settings?"):
            return
        try:
            core.cleanup()
        except Exception as exc:
            self.status = "clean-up failed: %s" % exc
            return
        self.prompt("Done. Run: herdr plugin uninstall %s  (enter) " % keys.PLUGIN_ID, "")
        raise SystemExit

    # ---- prompts -----------------------------------------------------
    def prompt(self, label, initial):
        h, w = self.scr.getmaxyx()
        curses.curs_set(1)
        win = curses.newwin(1, w, h - 1, 0)
        win.keypad(True)
        win.addnstr(0, 0, label, w - 1, curses.A_BOLD)
        start = min(len(label), w - 2)
        buf = list(initial)
        while True:
            win.move(0, start)
            win.clrtoeol()
            win.addnstr(0, start, "".join(buf)[-(w - start - 1):], w - start - 1)
            win.refresh()
            ch = win.get_wch()
            if ch in ("\n", "\r", curses.KEY_ENTER):
                curses.curs_set(0)
                return "".join(buf)
            if ch == "\x1b":
                curses.curs_set(0)
                return None
            if ch in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                if buf:
                    buf.pop()
            elif isinstance(ch, str) and ch.isprintable():
                buf.append(ch)

    def confirm(self, question):
        answer = self.prompt(question + " (y/N) ", "")
        return (answer or "").strip().lower() in ("y", "yes")

    # ---- tab actions -------------------------------------------------
    def tab_action(self, key):
        if not self.tab_id:
            return
        try:
            if key == "e":
                core.apply(pane_id=self.pane_id, force_strategy="equal", ignore_pause=True)
                self.status = "equalized"
            elif key == "r":
                core.reset_tracking(self.tab_id)
                core.apply(pane_id=self.pane_id)
                self.status = "resumed (pause and kept splits cleared)"
            elif key == "x":
                core.set_paused(self.tab_id, True)
                self.status = "restored + paused" if core.restore_tab(self.tab_id) else "nothing to restore; paused"
        except Exception as exc:
            self.status = "failed: %s" % exc

    def tab_status(self):
        if not self.tab_id:
            return ""
        tab = settings.read_state()["tabs"].get(self.tab_id, {})
        flags = []
        if not self.cfg["enabled"]:
            flags.append("DISABLED")
        if tab.get("paused") and self.cfg["on_manual_resize"] == "pause":
            flags.append("PAUSED (r to resume)")
        if tab.get("frozen") and self.cfg["on_manual_resize"] == "keep":
            flags.append("%d split(s) kept from manual resize (r to clear)" % len(tab["frozen"]))
        if tab.get("narrow_zoomed"):
            flags.append("narrow zoom")
        return "tab %s  %s" % (self.tab_id, "  ".join(flags) or "active")

    # ---- screens -----------------------------------------------------
    def form(self, title, groups, target, help_text):
        items = [(g, r) for g, rows in groups for r in rows]
        sel = 0
        while True:
            self.draw_form(title, groups, target, items[sel][1], help_text)
            ch = self.scr.get_wch()
            r = items[sel][1]
            if ch in ("q", "\x1b"):
                return
            if ch in (curses.KEY_UP, "k"):
                sel = (sel - 1) % len(items)
            elif ch in (curses.KEY_DOWN, "j"):
                sel = (sel + 1) % len(items)
            elif ch in (curses.KEY_LEFT, "h"):
                self.step(r, target, -1)
            elif ch in (curses.KEY_RIGHT, "l"):
                self.step(r, target, 1)
            elif ch in ("\n", "\r", " ", curses.KEY_ENTER):
                self.edit(r, target)
            elif ch in ("e", "r", "x") and target is self.cfg:
                self.tab_action(ch)

    def draw_form(self, title, groups, target, selected, help_text):
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        y = 0
        self.put_line(y, title, curses.A_BOLD)
        y += 1
        self.put_line(y, self.tab_status(), curses.A_DIM)
        y += 2
        label_w = 28
        lines = []
        for group, rows in groups:
            lines.append((group, None))
            lines.extend((None, r) for r in rows)
            lines.append(("", None))
        sel_idx = next(i for i, (_, r) in enumerate(lines) if r is selected)
        body_h = h - y - 2
        offset = max(0, sel_idx - body_h + 2)
        for group, r in lines[offset:offset + body_h]:
            if r is None:
                self.put_line(y, group, curses.A_BOLD | curses.A_UNDERLINE if group else 0)
            else:
                attr = curses.A_REVERSE if r is selected else 0
                text = "  %-*s %s" % (label_w, r["label"], self.display(r, target))
                self.put_line(y, text, attr)
            y += 1
        self.put_line(h - 2, self.status, curses.A_DIM)
        self.put_line(h - 1, help_text, curses.A_DIM)
        self.scr.refresh()

    def put_line(self, y, text, attr=0):
        h, w = self.scr.getmaxyx()
        if 0 <= y < h:
            self.scr.addnstr(y, 0, text.ljust(w - 1), w - 1, attr)

    def rules_screen(self):
        sel = 0
        while True:
            rules = self.cfg["rules"]
            self.scr.erase()
            h, w = self.scr.getmaxyx()
            self.put_line(0, "Process rules (first match wins; matches agent + process names)", curses.A_BOLD)
            if not rules:
                self.put_line(2, "  no rules — press a to add (e.g. match 'nvim', ratio 0.75)")
            for i, rule in enumerate(rules[: h - 4]):
                parts = ["%-20s" % (rule.get("match") or "(empty)")]
                for k in ("ratio", "min_cols", "min_rows", "max_cols", "max_rows"):
                    if rule.get(k) is not None:
                        parts.append("%s=%s" % (k, rule[k]))
                self.put_line(2 + i, "  " + "  ".join(parts), curses.A_REVERSE if i == sel else 0)
            self.put_line(h - 2, self.status, curses.A_DIM)
            self.put_line(h - 1, RULES_HELP, curses.A_DIM)
            self.scr.refresh()
            ch = self.scr.get_wch()
            if ch in ("q", "\x1b"):
                return
            if ch in (curses.KEY_UP, "k") and rules:
                sel = (sel - 1) % len(rules)
            elif ch in (curses.KEY_DOWN, "j") and rules:
                sel = (sel + 1) % len(rules)
            elif ch == "a":
                rules.append(dict(settings.RULE_DEFAULTS))
                sel = len(rules) - 1
                self.form("Edit rule", RULE_ROWS, rules[sel], RULE_HELP)
                self.commit()
            elif ch == "d" and rules:
                rules.pop(sel)
                sel = max(0, min(sel, len(rules) - 1))
                self.commit()
            elif ch in ("\n", "\r", curses.KEY_ENTER) and rules:
                self.form("Edit rule", RULE_ROWS, rules[sel], RULE_HELP)
                self.commit()


def _main(scr):
    curses.curs_set(0)
    curses.use_default_colors()
    scr.keypad(True)
    app = App(scr)
    app.form("Reficus settings", MAIN_ROWS, app.cfg, HELP)


def run():
    os.environ.setdefault("ESCDELAY", "25")
    curses.wrapper(_main)

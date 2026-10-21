<p align="center">
  <img src="docs/logo.svg" width="120" height="120" alt="Reficus logo: a ficus leaf beside two smaller leaves, above a pot">
</p>

<h1 align="center">Reficus</h1>

<p align="center"><b>Focus up front.</b> Ficus in the back.</p>

<p align="center"><code>open-source terminal plugin · the pane you're in grows, the rest quietly shrink</code></p>

---

A [herdr](https://herdr.dev) plugin that resizes panes for you: the pane
you're working in gets the space, and the others stay visible but smaller.
You never have to press a resize key.

![Reficus resizing herdr panes as focus moves](docs/demo.gif)

- **No extra keys.** Move focus the usual way (`prefix+h/j/k/l`, mouse, `prefix+tab`) and the sizes follow.
- **Nothing gets hidden.** Unlike zoom, you still see agents working and logs scrolling.
- **Agent-aware.** An agent waiting for your input can grow by itself, and idle ones shrink.
- **Profiles.** Tune the sizing, save it as a mode, and switch modes with a key.
- **Easy to undo.** Turning it off restores your original layout.

Requires herdr ≥ 0.8.2 and `python3` ≥ 3.9 on macOS or Linux. It has no
dependencies beyond the Python standard library.

## Install

```bash
herdr plugin install 81zi/reficus
```

On the next herdr server start, it binds `prefix+shift+f` to the settings
popup (unless that key is already taken). Until then, open the popup with
`herdr plugin action invoke reficus.settings`.

> `python3` must be on the `PATH` the herdr **server** was started with.

Upgrading from `81zi.reficus` or `local.reficus`? See
[the upgrade notes](docs/reference.md#upgrading-from-an-earlier-plugin-id).

## Use

1. Split a few panes and move focus around. The focused pane gets 65 % of each split it sits in.
2. Press `prefix+shift+f` to open the settings. Changes apply live.
3. Pick a profile (`coding`, `review`, `monitor`), or tune it and use **Save as new profile…**.

| Strategy | Effect |
|---|---|
| `weighted` *(default)* | The focused pane gets `ratio` of each split, and the others share the rest equally |
| `golden` | The focused pane always gets 61.8 % |
| `fixed` | The focused pane is exactly `fixed_cols` × `fixed_rows` |
| `accordion` | The focused pane takes almost everything, and the others shrink to thin strips |
| `ancestors` | Only the splits containing the focused pane change |
| `equal` | Every split is 50/50 |

You can also set per-program rules (for example, `nvim` gets 75 % and `tail -f`
is capped at 12 rows), a zoom fallback for narrow screens, which tabs it runs in,
and what happens after you resize by hand. All of this is covered in the
**[full reference](docs/reference.md)**.

## Uninstall

```bash
herdr plugin action invoke reficus.cleanup   # restore layouts, remove keybindings and config
herdr plugin uninstall reficus
```

## More

- [Reference](docs/reference.md): settings, rules, keybindings, troubleshooting
- [Security](docs/reference.md#security): Reficus runs as you, never reads pane output, and makes no network calls. Report issues through [security advisories](https://github.com/81zi/reficus/security/advisories/new).
- Contributing: PRs are welcome. Use only the standard library, and run `python3 -m unittest discover -s tests` before sending a change.

[MIT](LICENSE)

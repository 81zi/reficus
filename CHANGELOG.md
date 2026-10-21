# Changelog

## 0.4.0 — first public release

- Plugin id is now `81zi.reficus` (was `local.reficus`). Settings, runtime
  state and keybindings from `local.reficus` are migrated automatically on
  first run.
- Install from GitHub: `herdr plugin install 81zi/reficus`.
- Fix: hand-written Reficus `[[keys.command]]` entries were dropped when the
  popup rewrote the keybinding block; they are now adopted into it.
- Fix: a hand-written partial `config.json` (e.g. only `narrow_cols`) had its
  values overwritten by the active profile.
- `config.toml` is written atomically, through symlinks, keeps its file mode,
  and the very first version is kept as `config.toml.reficus-original`.
- An empty or malformed herdr API response raises a clean error.
- Unit tests and CI (Linux, macOS; Python 3.9 and 3.14).

## 0.3.0

- Profiles save every tunable; `manual` profile; manual-resize modes
  `override` / `keep` / `pause`; keybindings managed from the popup.

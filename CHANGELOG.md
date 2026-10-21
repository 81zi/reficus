# Changelog

## 0.5.0

- Plugin id is now `reficus` (was `81zi.reficus`), so action names and
  paths don't carry the GitHub owner: `reficus.settings`, `reficus.toggle`,
  … Settings, state and keybindings from `81zi.reficus` and `local.reficus`
  are migrated automatically. The install source stays `81zi/reficus`.
- New `reficus.cleanup` action (also in the popup): restores layouts,
  removes Reficus keybindings from config.toml, disables the plugin and
  deletes its config and state, so `herdr plugin uninstall reficus` leaves
  nothing behind.
- Source moved to `src/`; manifest commands run `src/reficus.py`.
- Plugin commands run with `python3 -B`, so no `__pycache__` is written
  into the plugin directory.
- herdr API client: connection failures and timeouts raise a clean
  `HerdrError`, responses are matched to the request id, and the socket is
  always closed. Tests added for the client.
- README: new Security section (what Reficus reads, writes and runs).

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

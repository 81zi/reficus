#!/bin/sh
# Records docs/demo.gif with VHS (brew install vhs) in a throwaway herdr
# session. Panes run a bare bash with a "$ " prompt and no rc files, so no
# hostname, user name or personal paths show up. Your Reficus config is
# restored afterwards (the demo switches profiles).
set -eu
cd "$(dirname "$0")/.."
tmp=$(mktemp -d)
demo=$tmp/demo-project
mkdir -p "$demo"
printf '#!/bin/sh\nexec /bin/bash --noprofile --norc -i\n' > "$tmp/demo-shell"
chmod +x "$tmp/demo-shell"
config="$(herdr plugin config-dir reficus)/config.json"
[ -f "$config" ] && cp "$config" "$tmp/config.json"
reset_session() {
    herdr session stop reficus-demo >/dev/null 2>&1 || true
    herdr session delete reficus-demo >/dev/null 2>&1 || true
}
reset_session
restore() {
    reset_session
    [ -f "$tmp/config.json" ] && cp "$tmp/config.json" "$config"
    rm -rf "$tmp"
}
trap restore EXIT
env -i HOME="$HOME" PATH="$PATH" TERM=xterm-256color LANG=en_US.UTF-8 \
    SHELL="$tmp/demo-shell" PS1='$ ' BASH_SILENCE_DEPRECATION_WARNING=1 \
    sh -c "cd '$demo' && vhs '$PWD/docs/demo.tape' -o '$PWD/docs/demo.gif'"

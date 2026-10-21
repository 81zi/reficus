# Reficus demo. Record with: docs/record-demo.sh

Set Shell "bash"
Set FontSize 14
Set Width 1400
Set Height 800
Set Padding 12
Set TypingSpeed 40ms
Set Theme "Catppuccin Mocha"

Hide
Type "herdr --session reficus-demo" Enter
Sleep 3s
# Three panes: A | (B / C)
Type "clear; echo 'A  editor'" Enter
Ctrl+B
Type "v"
Sleep 1s
Type "clear; echo 'B  agent'" Enter
Ctrl+B
Type "-"
Sleep 1s
Type "clear; while :; do date +%T' log line'; sleep 1; done" Enter
Sleep 1s
Show

Sleep 1.5s
# Move focus around: the focused pane grows
Ctrl+B
Type "h"
Sleep 2s
Ctrl+B
Type "l"
Sleep 2s
Ctrl+B
Type "k"
Sleep 2s
Ctrl+B
Type "j"
Sleep 2s

# Settings popup: switch to the "review" profile, then see it in action
Ctrl+B
Type "F"
Sleep 1.5s
Down
Sleep 500ms
Right
Sleep 1.5s
Type "q"
Sleep 1s
Ctrl+B
Type "l"
Sleep 2s
Ctrl+B
Type "h"
Sleep 2.5s

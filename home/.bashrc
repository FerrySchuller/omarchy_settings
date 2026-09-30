# Omarchy environment (OMARCHY_PATH + PATH), needed even for non-interactive shells
[[ -r /usr/share/omarchy/default/bash/env-bootstrap ]] && source /usr/share/omarchy/default/bash/env-bootstrap

# ~/bin in PATH (voor alle shells, ook niet-interactieve)
case ":$PATH:" in
  *":$HOME/bin:"*) ;;
  *) export PATH="$HOME/bin:$PATH" ;;
esac

# ssh-agent: eenmalig per sessie starten, daarna dezelfde socket hergebruiken
export SSH_AUTH_SOCK="${XDG_RUNTIME_DIR:-/tmp}/ssh-agent.sock"
ssh-add -l >/dev/null 2>&1
if [ "$?" -eq 2 ]; then
  [ -S "$SSH_AUTH_SOCK" ] && rm -f "$SSH_AUTH_SOCK"
  eval "$(ssh-agent -a "$SSH_AUTH_SOCK" -s)" >/dev/null
fi

# If not running interactively, don't do anything else (leave this above the rc source)
[[ $- != *i* ]] && return

# All the default Omarchy aliases and functions
# (don't mess with these directly, just overwrite them here!)
source "$OMARCHY_PATH/default/bash/rc"

# Add your own exports, aliases, and functions here.
#
# Make an alias for invoking commands you use constantly
# alias p='python'

alias poker='cd /prod/apps/pokermgr.io && . env/bin/activate'
alias leads='cd /prod/apps/leads && . env/bin/activate'
alias vavo='cd /prod/apps/vavo && . env/bin/activate'

# GNU ls in plaats van de eza-alias van Omarchy
unalias ls 2>/dev/null
alias ls='ls --color=auto -h'

alias vi='vim'

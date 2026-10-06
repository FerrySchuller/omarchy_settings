# Omarchy setup — personal desktop & shell configuration (Ferry Schuller)

Master guide to bring a **clean Omarchy install (4.x, Hyprland)** into the
desired state: theme, default apps, shell, prompt, git, terminal, hooks and
theming. Hand this file **plus the rest of this repo** to an AI agent (or run
it yourself).

> **For the agent:** work through the phases in order. Copy files from this
> repo (`home/` → `$HOME`) instead of retyping them. Use `sudo` where needed.
> Don't skip anything marked "MACHINE-SPECIFIC" without asking the user.

Scope: **Omarchy/desktop/shell only**. Server infrastructure (nginx, vavo,
mongo, docker, ufw, LUKS, systemd units) is intentionally out of scope.

---

## 0. Assumptions

- Clean Omarchy install, up to date: `omarchy update`.
- User `ferry` in group `wheel` (Omarchy default).
- All paths below are **relative to the repo root**.

### Machine-specific values

| Value | Current | Command |
|---|---|---|
| Hostname | `thuis` | `sudo hostnamectl set-hostname thuis` |
| Timezone | `Europe/Amsterdam` | `sudo timedatectl set-timezone Europe/Amsterdam` |
| Git identity | Ferry Schuller / ferry@f-inter.net | `home/.config/git/config` |

### Repo layout

```
SETUP.md            ← this file
packages/           packages to add
home/               files that go 1:1 into $HOME
```

---

## 1. Packages

```bash
omarchy pkg add $(grep -v '^#' packages/extra.txt)
omarchy pkg aur add $(grep -v '^#' packages/aur.txt)
```

- `extra.txt`: `google-chrome` (Omarchy repo), `kitty`, `vim`.
- `aur.txt`: `spotifast-bin` — only needed for the theme-set hook (§4).
  Drop it if Spotifast is not used.

`omarchy pkg add` skips packages that are already installed, so this is
idempotent.

---

## 2. Omarchy desktop settings

```bash
# Theme
omarchy theme set Hackerman

# Default editor + coding agent
omarchy default editor vim
omarchy default agent pi

# Default terminal (installs if needed + sets xdg-terminal-exec)
omarchy install terminal kitty

# Default browser (Chrome + XDG handlers)
omarchy default browser chrome

# Restore web apps (incl. HEY for mailto)
omarchy install preinstalls
```

Workspace 2 in `dwindle` layout (instead of scrolling):

```bash
mkdir -p ~/.local/state/omarchy/workspace-layouts
cp home/.local/state/omarchy/workspace-layouts/2.lua \
   ~/.local/state/omarchy/workspace-layouts/2.lua
# or: focus workspace 2 and use the toggle-layout keybinding
```

All Hyprland config stays **default** except `bindings.lua`, which repoints
the file-manager key (see §3). `extensions/omarchy-menu.jsonc` stays
**default**.

The only `shell.json` change is the idle lock: one hour instead of five
minutes (the screensaver stays at the default 2.5 minutes). It ships in
`home/.config/omarchy/shell.json` and is applied in §3.

---

## 3. Shell & dotfiles (`home/` → `$HOME`)

```bash
cp -a home/. "$HOME"/
chmod +x ~/.config/omarchy/hooks/theme-set.d/spotifast-theme

xdg-user-dirs-update
mise install                 # installs codex / node / pi
omarchy restart terminal     # reload terminal config
hyprctl reload && hyprctl configerrors   # apply + validate Hyprland bindings
```

What this sets:

| File | Change vs default |
|---|---|
| `~/.bashrc` | `~/bin` in PATH; ssh-agent on a fixed socket; aliases `poker`/`leads`/`vavo`; `ls` → GNU ls; `vi` → `vim` |
| `~/.vimrc` | `set t_ti= t_te=` (text stays in the terminal scrollback after `:wq`) |
| `~/.XCompose` | name + email via Multi-key |
| `~/.config/starship.toml` | always show hostname + python venv prompt |
| `~/.config/git/config` | `user.name` / `user.email` |
| `~/.config/herdr/config.toml` | minimal config (`prefix = ctrl+space`) |
| `~/.config/btop/btop.conf` | `proc net cpu mem`, `proc_per_core`, `io_mode` |
| `~/.config/mise/config.toml` | tools `codex` / `node` / `pi`, `auto_prune=false` |
| `~/.config/xdg-terminals.list` | `kitty.desktop` |
| `~/.config/mimeapps.list` | Chrome as browser, HEY for mailto |
| `~/.config/user-dirs.dirs` | Desktop/Templates/PublicShare → `$HOME`, plus `PROJECTS` |
| `~/.config/omarchy/defaults/agent` | `pi` |
| `~/.config/omarchy/shell.json` | idle lock 300 → 3600s (1 hour) |
| `~/.config/hypr/bindings.lua` | SUPER+SHIFT+F → `flea` (was nautilus) |

> The aliases `poker`/`leads`/`vavo` point at `/prod/apps/...`; they only do
> something if those projects exist.

---

## 4. Omarchy hooks & theming

Already in the `home/` tree and working automatically after §3:

- `~/.config/omarchy/hooks/theme-set.d/spotifast-theme`
  — writes a palette to Spotifast on every theme change.
- `~/.config/omarchy/themed/spotifast.json.tpl`
  — template used to generate that palette.

Test:

```bash
omarchy theme set Hackerman     # triggers the hook
```

The post-update hooks (`install-voxtype`, `setup-agent`, `setup-fingerprint`)
are **stock** first-run invites and don't need to be copied.

---

## 5. Verification

```bash
omarchy theme current                 # → Hackerman
omarchy default editor                # → vim
omarchy default agent                 # → pi
omarchy default terminal              # → kitty
xdg-settings get default-web-browser  # → google-chrome.desktop
type ls | head -1                     # → ls --color=auto -h
omarchy menu keybindings --print | grep 'File manager'   # → SUPER SHIFT + F
```

---

## 6. Reset to defaults

```bash
omarchy refresh shell
omarchy refresh hyprland
omarchy refresh config <relative-path>   # e.g. hypr/bindings.lua
```

This repo intentionally does **not** touch `omarchy-menu.jsonc`, the rest of
`~/.config/hypr/` (only `bindings.lua` is overridden), terminals, tmux,
lazygit, fastfetch or GTK/dconf — those are all default here.

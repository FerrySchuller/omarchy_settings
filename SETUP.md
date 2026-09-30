# Omarchy instellen — persoonlijke desktop- & shellsetup (Ferry Schuller)

Master-gids om een **schone Omarchy-install (4.x, Hyprland)** in de gewenste
staat te brengen: thema, standaard-apps, shell, prompt, git, terminal, hooks en
theming. Geef dit bestand **plus de rest van deze repo** aan een AI-agent (of
voer het zelf uit).

> **Voor de agent:** werk de fases in volgorde af. Kopieer bestanden uit deze
> repo (`home/` → `$HOME`) in plaats van ze na te typen. Gebruik `sudo` waar
> nodig. Sla niets over dat "MACHINE-SPECIFIEK" of "SECRET" heet zonder de
> gebruiker te vragen.

Scope: **alleen Omarchy/desktop/shell**. Server-infra (nginx, vavo, mongo,
docker, ufw, LUKS, systemd-units) valt hier bewust buiten.

---

## 0. Uitgangspunten

- Schone Omarchy-install, up-to-date: `omarchy update`.
- Gebruiker `ferry` in groep `wheel` (standaard Omarchy).
- Alle paden hieronder zijn **relatief t.o.v. de repo-root**.

### Machine-specifieke waarden

| Waarde | Huidige | Commando |
|---|---|---|
| Hostname | `thuis` | `sudo hostnamectl set-hostname thuis` |
| Tijdzone | `Europe/Amsterdam` | `sudo timedatectl set-timezone Europe/Amsterdam` |
| Git identiteit | Ferry Schuller / ferry@f-inter.net | `home/.config/git/config` |

### Repo-layout

```
SETUP.md            ← dit bestand
packages/           packages om toe te voegen
home/               bestanden die 1-op-1 naar $HOME gaan
```

---

## 1. Packages

```bash
omarchy pkg add $(grep -v '^#' packages/extra.txt)
omarchy pkg aur add $(grep -v '^#' packages/aur.txt)
```

- `extra.txt`: `google-chrome` (Omarchy-repo), `kitty`, `vim`.
- `aur.txt`: `spotifast-bin` — alleen nodig voor de theme-set hook (§4).
  Laat weg als Spotifast niet gebruikt wordt.

`omarchy pkg add` slaat reeds geïnstalleerde packages over, dus dit is
idempotent.

---

## 2. Omarchy desktop-instellingen

```bash
# Thema
omarchy theme set Hackerman

# Standaard editor + coding-agent
omarchy default editor vim
omarchy default agent pi

# Standaard terminal (installeert indien nodig + zet xdg-terminal-exec)
omarchy install terminal kitty

# Standaard browser (Chrome + XDG-handlers)
omarchy default browser chrome

# Web-apps (o.a. HEY voor mailto) terugzetten
omarchy install preinstalls
```

Workspace 2 in `dwindle`-layout (i.p.v. scrolling):

```bash
mkdir -p ~/.local/state/omarchy/workspace-layouts
cp home/.local/state/omarchy/workspace-layouts/2.lua \
   ~/.local/state/omarchy/workspace-layouts/2.lua
# of: focus workspace 2 en gebruik de toggle-layout-sneltoets
```

Alle overige Hyprland-config (`~/.config/hypr/*`), `shell.json` en
`extensions/omarchy-menu.jsonc` blijven **default** — daar is niets aangepast.
Ook idle blijft default (150s screensaver / 300s lock).

---

## 3. Shell & dotfiles (`home/` → `$HOME`)

```bash
cp -a home/. "$HOME"/
chmod +x ~/.config/omarchy/hooks/theme-set.d/spotifast-theme

xdg-user-dirs-update
mise install                 # installeert codex / node / pi
omarchy restart terminal     # terminal-config herladen
```

Wat er wordt gezet:

| Bestand | Wijziging t.o.v. default |
|---|---|
| `~/.bashrc` | `~/bin` in PATH; ssh-agent op vaste socket; aliases `poker`/`leads`/`vavo`; `ls` → GNU ls; `vi` → `vim` |
| `~/.vimrc` | `set t_ti= t_te=` (tekst blijft in terminal-scrollback na `:wq`) |
| `~/.XCompose` | naam + e-mail via Multi-key |
| `~/.config/starship.toml` | hostname altijd tonen + python-venv prompt |
| `~/.config/git/config` | `user.name` / `user.email` |
| `~/.config/herdr/config.toml` | minimale config (`prefix = ctrl+space`) |
| `~/.config/btop/btop.conf` | `proc net cpu mem`, `proc_per_core`, `io_mode` |
| `~/.config/mise/config.toml` | tools `codex` / `node` / `pi`, `auto_prune=false` |
| `~/.config/xdg-terminals.list` | `kitty.desktop` |
| `~/.config/mimeapps.list` | Chrome als browser, HEY voor mailto |
| `~/.config/user-dirs.dirs` | Desktop/Templates/PublicShare → `$HOME`, plus `PROJECTS` |
| `~/.config/omarchy/defaults/agent` | `pi` |

> De aliases `poker`/`leads`/`vavo` verwijzen naar `/prod/apps/...`; die zijn
> alleen zinvol als die projecten bestaan.

---

## 4. Omarchy-hooks & theming

Zit al in de `home/`-tree en werkt na §3 automatisch:

- `~/.config/omarchy/hooks/theme-set.d/spotifast-theme`
  — schrijft bij elke themawissel een palette naar Spotifast.
- `~/.config/omarchy/themed/spotifast.json.tpl`
  — template waarmee dat palette wordt gegenereerd.

Test:

```bash
omarchy theme set Hackerman     # triggert de hook
```

De post-update hooks (`install-voxtype`, `setup-agent`, `setup-fingerprint`)
zijn **stock** first-run-invites en hoeven niet gekopieerd te worden.

---

## 5. Secrets — HANDMATIG, NOOIT COMMITTEN

Horen **niet** in de repo. Zet ze handmatig over (SSH-sleutels staan al klaar
vóórdat deze repo gekloond wordt; agent-login doe je met `/login`):

| Secret | Pad | Opmerking |
|---|---|---|
| GPG-sleutels | `~/.gnupg/` | |

```bash
chmod 700 ~/.gnupg
```

`~/.pi/agent/settings.json` (thema `omarchy-system`, provider `opencode-go`,
model, editor `vim`) bevat geen secrets en mag gekopieerd worden zodra Pi
geïnstalleerd is.

---

## 6. Verificatie

```bash
omarchy theme current                 # → Hackerman
omarchy default editor                # → vim
omarchy default agent                 # → pi
omarchy default terminal              # → kitty
xdg-settings get default-web-browser  # → google-chrome.desktop
type ls | head -1                     # → ls --color=auto -h
```

---

## 7. Resetten naar default

```bash
omarchy refresh shell
omarchy refresh hyprland
omarchy refresh config <relatief-pad>   # b.v. hypr/bindings.lua
```

Deze repo raakt bewust **niet** `~/.config/hypr/`, `shell.json`,
`omarchy-menu.jsonc`, terminals, tmux, lazygit, fastfetch of GTK/dconf aan —
die zijn hier allemaal default.

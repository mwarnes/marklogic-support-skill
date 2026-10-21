#!/usr/bin/env bash
# Install, update, check or remove the MarkLogic support skills for pi, Claude Code, Codex and GitHub Copilot.
#
# Usage: ./install.sh [install|update|status|uninstall] [options]
#   --agents LIST    comma list of: pi, claude, codex, copilot, all   (default: all)
#   --copy           copy the skill folders instead of symlinking them (re-run `update` to refresh)
#   --force          replace a real (non-symlink) folder of the same name, keeping a .bak-<time> copy
#   --no-pull        update: do not run `git pull` first (just re-link)
#   --clean-legacy   move superseded command files (ticket/kcs/kcs-review .md) aside, to .bak-<time>
#   -h, --help       show this help
#
# Where the skills go (user level):
#   ~/.agents/skills/<skill>   read by pi, Codex and GitHub Copilot
#   ~/.claude/skills/<skill>   read by Claude Code (and by GitHub Copilot)
# The skills are the folders under skills/ in this repository: marklogic-support, ticket, kcs, kcs-review.
# macOS / Linux (bash 3.2 or newer). Windows: use install.ps1.
set -u

REPO="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CMD=install; AGENTS=all; COPY=0; FORCE=0; PULL=1; CLEAN_LEGACY=0
STAMP="$(date +%Y%m%d-%H%M%S)"
MARK=".installed-by-marklogic-support-skill"
PROBLEMS=0

usage() { sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; }
say() { printf '%s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
problem() { warn "$*"; PROBLEMS=$((PROBLEMS + 1)); }

while [ $# -gt 0 ]; do
  case "$1" in
    install|update|status|uninstall) CMD="$1" ;;
    --agents) shift; AGENTS="${1:-}" ;;
    --agents=*) AGENTS="${1#--agents=}" ;;
    --copy) COPY=1 ;;
    --force) FORCE=1 ;;
    --no-pull) PULL=0 ;;
    --clean-legacy) CLEAN_LEGACY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) warn "unknown argument: $1"; usage >&2; exit 2 ;;
  esac
  shift
done

# --- which target directories for the chosen agents -------------------------------------------------
TARGETS=""
add_target() { case " $TARGETS " in *" $1 "*) ;; *) TARGETS="$TARGETS $1" ;; esac; }
OLDIFS="$IFS"; IFS=','
for a in $AGENTS; do
  case "$a" in
    all) add_target "$HOME/.agents/skills"; add_target "$HOME/.claude/skills" ;;
    pi|codex|copilot) add_target "$HOME/.agents/skills" ;;
    claude) add_target "$HOME/.claude/skills" ;;
    *) IFS="$OLDIFS"; warn "unknown agent '$a' (use pi, claude, codex, copilot or all)"; exit 2 ;;
  esac
done
IFS="$OLDIFS"
[ -n "$TARGETS" ] || { warn "no agents selected"; exit 2; }

SKILLS=""
discover_skills() {    # run after any git pull so newly added skills are seen
  local d
  SKILLS=""
  for d in "$REPO"/skills/*/; do
    [ -f "$d/SKILL.md" ] && SKILLS="$SKILLS $(basename "$d")"
  done
  [ -n "$SKILLS" ] || { warn "no skills found under $REPO/skills"; exit 1; }
}

# --- helpers ----------------------------------------------------------------------------------------
link_target() { readlink "$1" 2>/dev/null; }

is_ours() {            # a link into this repo, or a copy carrying our marker
  if [ -L "$1" ]; then case "$(link_target "$1")" in "$REPO"/skills/*) return 0 ;; esac; return 1; fi
  [ -f "$1/$MARK" ]
}

install_one() {        # $1 = skill name, $2 = target dir
  local tdir="$2" src="$REPO/skills/$1" dest="$2/$1"
  mkdir -p "$tdir"
  if [ -L "$dest" ]; then
    if [ "$COPY" = 0 ] && [ "$(link_target "$dest")" = "$src" ]; then say "ok        $dest"; return; fi
    local old; old="$(link_target "$dest")"
    rm "$dest"; say "relinked  $dest (was -> $old)"
  elif [ -e "$dest" ]; then
    if [ -f "$dest/$MARK" ]; then rm -rf "$dest"
    elif [ "$FORCE" = 1 ]; then mv "$dest" "$dest.bak-$STAMP"; say "backed up $dest -> $dest.bak-$STAMP"
    else problem "$dest exists and is not managed by this installer; re-run with --force to replace it (a backup is kept)"; return
    fi
  fi
  if [ "$COPY" = 1 ]; then
    cp -R "$src" "$dest" && : > "$dest/$MARK" && say "copied    $dest"
  else
    ln -s "$src" "$dest" && say "linked    $dest -> $src"
  fi
}

status_one() {
  local dest="$2/$1" src="$REPO/skills/$1"
  if [ -L "$dest" ]; then
    if [ "$(link_target "$dest")" = "$src" ]; then say "ok        $dest"; else say "stale     $dest -> $(link_target "$dest") (run: ./install.sh update)"; PROBLEMS=$((PROBLEMS + 1)); fi
  elif [ -f "$dest/$MARK" ]; then say "copy      $dest (refresh with: ./install.sh update --copy)"
  elif [ -e "$dest" ]; then say "conflict  $dest is not managed by this installer"; PROBLEMS=$((PROBLEMS + 1))
  else say "missing   $dest"; PROBLEMS=$((PROBLEMS + 1))
  fi
}

uninstall_one() {
  local dest="$2/$1"
  if [ -L "$dest" ] || [ -e "$dest" ]; then
    if is_ours "$dest"; then rm -rf "$dest"; say "removed   $dest"; else say "kept      $dest (not installed by this repo)"; fi
  fi
}

LEGACY_DIRS="$HOME/.claude/commands $HOME/.pi/agent/prompts $HOME/.codex/prompts"
legacy() {
  local d n f
  for d in $LEGACY_DIRS; do
    for n in ticket kcs kcs-review; do
      f="$d/$n.md"
      [ -e "$f" ] || [ -L "$f" ] || continue
      if [ "$CLEAN_LEGACY" = 1 ]; then mv "$f" "$f.bak-$STAMP"; say "moved     $f -> $f.bak-$STAMP (superseded by the $n skill)"
      else say "legacy    $f is superseded by the '$n' skill; remove it with --clean-legacy"; fi
    done
  done
}

deps() {
  command -v python3 >/dev/null 2>&1 || problem "python3 not found: the analysis and ticket scripts need Python 3"
  command -v git >/dev/null 2>&1 || warn "git not found: needed for 'update'"
  command -v pandoc >/dev/null 2>&1 || say "note      pandoc not found: /kcs cannot write the Word/HTML versions until it is installed (https://pandoc.org/installing.html)"
}

commit() { git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown; }

# --- run --------------------------------------------------------------------------------------------
case "$CMD" in
  update)
    if [ "$PULL" = 1 ]; then
      command -v git >/dev/null 2>&1 || { warn "git is required for update (or use --no-pull)"; exit 1; }
      before="$(commit)"
      if ! git -C "$REPO" pull --ff-only; then warn "git pull failed; fix the repository (local changes? no network?) and re-run, or use --no-pull"; exit 1; fi
      after="$(commit)"
      if [ "$before" = "$after" ]; then say "repository already at $after"; else say "repository updated $before -> $after"; fi
    fi
    ;;
esac

discover_skills

case "$CMD" in
  install|update)
    for t in $TARGETS; do for s in $SKILLS; do install_one "$s" "$t"; done; done
    legacy; deps
    ;;
  status)
    say "repository $REPO at $(commit)"
    for t in $TARGETS; do for s in $SKILLS; do status_one "$s" "$t"; done; done
    legacy; deps
    ;;
  uninstall)
    for t in $TARGETS; do for s in $SKILLS; do uninstall_one "$s" "$t"; done; done
    ;;
esac

if [ "$PROBLEMS" -gt 0 ]; then exit 1; fi
exit 0

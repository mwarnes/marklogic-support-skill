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
# shellcheck disable=SC2329  # the per-skill functions are called indirectly by for_each_target
set -u

SELF="${BASH_SOURCE[0]}"
while [ -L "$SELF" ]; do       # run through a symlink: find the script's real directory
  d="$(cd -P "$(dirname "$SELF")" && pwd)"
  SELF="$(readlink "$SELF")"
  case "$SELF" in /*) ;; *) SELF="$d/$SELF" ;; esac
done
REPO="$(cd -P "$(dirname "$SELF")" && pwd)"
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
[ -n "${HOME:-}" ] || { warn "HOME is not set; cannot tell where to install"; exit 1; }
WANT_AGENTS=0; WANT_CLAUDE=0
OLDIFS="$IFS"; IFS=','
for a in $AGENTS; do
  a="${a#"${a%%[![:space:]]*}"}"; a="${a%"${a##*[![:space:]]}"}"
  case "$a" in
    all) WANT_AGENTS=1; WANT_CLAUDE=1 ;;
    pi|codex|copilot) WANT_AGENTS=1 ;;
    claude) WANT_CLAUDE=1 ;;
    *) IFS="$OLDIFS"; warn "unknown agent '$a' (use pi, claude, codex, copilot or all)"; exit 2 ;;
  esac
done
IFS="$OLDIFS"
[ "$WANT_AGENTS" = 1 ] || [ "$WANT_CLAUDE" = 1 ] || { warn "no agents selected"; exit 2; }

for_each_skill() {     # $1 = function, $2 = target dir; calls: function skill target
  local s
  for s in $SKILLS; do "$1" "$s" "$2"; done
}
for_each_target() {    # $1 = function
  if [ "$WANT_AGENTS" = 1 ]; then for_each_skill "$1" "$HOME/.agents/skills"; fi
  if [ "$WANT_CLAUDE" = 1 ]; then for_each_skill "$1" "$HOME/.claude/skills"; fi
}

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

repo_link() {          # $1 = link, $2 = skill: dangling, or pointing at <clone>/skills/<skill> of a checkout of this repo
  local t; t="$(link_target "$1")"
  [ -e "$1" ] || return 0
  case "$t" in /*) ;; *) t="$(dirname "$1")/$t" ;; esac
  case "$t" in
    */skills/"$2") [ -f "$(dirname "$(dirname "$t")")/install.sh" ] ;;
    *) return 1 ;;
  esac
}

bak_path() {           # a backup name that does not exist yet
  local p="$1.bak-$STAMP" i=1
  while [ -e "$p" ] || [ -L "$p" ]; do p="$1.bak-$STAMP-$i"; i=$((i + 1)); done
  printf '%s' "$p"
}

install_one() {        # $1 = skill name, $2 = target dir
  local name="$1" tdir="$2" src="$REPO/skills/$1" dest="$2/$1" old bak
  mkdir -p "$tdir" || { problem "cannot create $tdir"; return; }
  if [ -L "$dest" ]; then
    old="$(link_target "$dest")"
    if [ "$COPY" = 0 ] && [ "$old" = "$src" ]; then say "ok        $dest"; return; fi
    if repo_link "$dest" "$name"; then
      rm "$dest" || { problem "cannot remove the old link $dest"; return; }
      say "relinked  $dest (was -> $old)"
    elif [ "$FORCE" = 1 ]; then
      bak="$(bak_path "$dest")"
      mv "$dest" "$bak" || { problem "cannot back up $dest"; return; }
      say "backed up $dest -> $bak"
    else
      problem "$dest is a link to $old that this installer did not create; re-run with --force to replace it (a backup is kept)"; return
    fi
  elif [ -e "$dest" ]; then
    if [ -f "$dest/$MARK" ]; then
      rm -rf "$dest" || { problem "cannot remove the old copy $dest"; return; }
    elif [ "$FORCE" = 1 ]; then
      bak="$(bak_path "$dest")"
      mv "$dest" "$bak" || { problem "cannot back up $dest"; return; }
      say "backed up $dest -> $bak"
    else problem "$dest exists and is not managed by this installer; re-run with --force to replace it (a backup is kept)"; return
    fi
  fi
  if [ "$COPY" = 1 ]; then
    if ! cp -R "$src" "$dest"; then rm -rf "$dest"; problem "copy to $dest failed"; return; fi
    if ! : > "$dest/$MARK"; then rm -rf "$dest"; problem "cannot mark the copy $dest"; return; fi
    say "copied    $dest"
  else
    ln -s "$src" "$dest" || { problem "cannot link $dest"; return; }
    say "linked    $dest -> $src"
  fi
}

status_one() {
  local dest="$2/$1" src="$REPO/skills/$1"
  if [ -L "$dest" ]; then
    if [ "$(link_target "$dest")" = "$src" ]; then say "ok        $dest"
    elif repo_link "$dest" "$1"; then say "stale     $dest -> $(link_target "$dest") (run: ./install.sh update)"; PROBLEMS=$((PROBLEMS + 1))
    else say "conflict  $dest is a link to $(link_target "$dest") that this installer did not create"; PROBLEMS=$((PROBLEMS + 1))
    fi
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

legacy_dir() {         # $1 = a directory that older versions put command files in
  local n f bak
  for n in ticket kcs kcs-review; do
    f="$1/$n.md"
    [ -e "$f" ] || [ -L "$f" ] || continue
    if [ "$CLEAN_LEGACY" = 1 ]; then
      bak="$(bak_path "$f")"
      if mv "$f" "$bak"; then say "moved     $f -> $bak (superseded by the $n skill)"; else problem "cannot move $f aside"; fi
    else say "legacy    $f is superseded by the '$n' skill; remove it with --clean-legacy"; fi
  done
}
legacy() {
  legacy_dir "$HOME/.claude/commands"
  legacy_dir "$HOME/.pi/agent/prompts"
  legacy_dir "$HOME/.codex/prompts"
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
    for_each_target install_one
    legacy; deps
    ;;
  status)
    say "repository $REPO at $(commit)"
    for_each_target status_one
    legacy; deps
    ;;
  uninstall)
    for_each_target uninstall_one
    ;;
esac

if [ "$PROBLEMS" -gt 0 ]; then exit 1; fi
exit 0

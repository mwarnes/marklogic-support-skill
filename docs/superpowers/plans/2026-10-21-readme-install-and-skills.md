# README, Cross-Agent Install and Skill Conversion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the MarkLogic support skills installable and updatable on pi, Claude Code, Codex and GitHub Copilot from one clone (macOS, Linux, Windows), by converting the `/ticket`, `/kcs` and `/kcs-review` prompt files into skills, adding install/update scripts, and rewriting the README.

**Architecture:** The four skills (`marklogic-support`, `ticket`, `kcs`, `kcs-review`) live under `skills/`; an installer links each folder into `~/.agents/skills` (pi, Codex, Copilot) and `~/.claude/skills` (Claude Code, Copilot), so one clone serves every agent and `git pull` updates all of them. A cross-platform Python script replaces the bash setup step of `/ticket`.

**Tech Stack:** bash 3.2+ (macOS/Linux installer), PowerShell 5.1+ (Windows installer, not executable in CI), Python 3 stdlib, Markdown skills. Tests: `python3 -m unittest discover -s tests` (pytest is not installed); `shellcheck` is used by one test when present.

## Global Constraints

Decisions agreed with the user, and facts from official docs (fetched 2026-10-21):

- **Convert the commands to skills** (`ticket`, `kcs`, `kcs-review`); the `prompts/` folder is deleted and `package.json` drops its `prompts` entry. Skills are invoked: Claude Code `/ticket 12345`; pi `/skill:ticket 12345`; Codex `$ticket 12345` (or `/skills`); Copilot picks a skill from its description (no slash command for skills).
- **Install locations (user level):** `~/.agents/skills/<skill>` is read by pi (https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/docs/skills.md), Codex (https://learn.chatgpt.com/docs/build-skills) and Copilot (https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/create-skills); `~/.claude/skills/<skill>` is read by Claude Code (https://code.claude.com/docs/en/skills) and Copilot. Symlinked skill folders are supported by Claude Code and Codex. Copilot personal skills may also live in `~/.copilot/skills`.
- **Arguments:** in Claude Code `$1` is the *second* argument (`$0` the first), so the skills use `$ARGUMENTS` with a fallback sentence: if the text `$ARGUMENTS` is still literal or empty, take the value from the user's message (pi appends text after `/skill:name` to the skill as the request; Codex and Copilot take it from the user's message).
- **pi updates:** `pi update --extensions` updates installed packages; `pi update <source>` updates one package; plain `pi update` updates pi itself (verified with `pi update --help` and https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/docs/packages.md). pi packages are installed with `pi install git:<repo>`.
- **Installer behaviour (install.sh / install.ps1):** commands `install` (default), `update`, `status`, `uninstall`; `--agents` (pi, claude, codex, copilot, all); `--copy`; `--force` (keeps a `.bak-<time>` copy); `--no-pull`; `--clean-legacy` (moves old `ticket|kcs|kcs-review` `.md` files in `~/.claude/commands`, `~/.pi/agent/prompts`, `~/.codex/prompts` aside to `.bak-<time>`, never deletes). `update` runs `git pull --ff-only` and re-discovers skills **after** the pull. Never overwrite a real folder without `--force`; never remove anything not installed by the installer. Windows uses directory junctions (no admin rights); `-Copy` is the fallback.
- **Repository URL** is the placeholder `<repo-url>` everywhere in the README (the team has not decided where it will live).
- **Copilot Enterprise:** the docs describe no organisation-level skill distribution; the README says so, and offers per-user install, `.github/skills/` in a team repository, and notes `gh skill` (preview) without documenting its syntax.
- **Not verified:** the Windows installer is not run in CI (no PowerShell here) and junction behaviour with Codex/Copilot is untested; the README says so.
- The security incident gate, SAR mode, KCS rules and every other behaviour of the skills are unchanged; only locations, argument handling and the ticket-folder setup change. Existing tests keep passing (paths in `tests/test_security_docs.py` are updated).
- `KCS_SolutionContentStandard.txt`, `SECURITY_HANDLING.txt` and `kcs-drafts/` are untracked: never `git add` them.

---

## File Structure

- Create `skills/marklogic-support/scripts/ticket_init.py`, `tests/test_ticket_init.py`.
- Create `install.sh`, `install.ps1`, `.gitattributes`, `tests/test_install.py`.
- Create `skills/ticket/SKILL.md`; move `prompts/kcs.md` → `skills/kcs/SKILL.md` and `prompts/kcs-review.md` → `skills/kcs-review/SKILL.md` (edited); delete `prompts/`.
- Modify `skills/marklogic-support/SKILL.md`, `package.json`, `tests/test_security_docs.py`; create `tests/test_skill_layout.py`.
- Rewrite `README.md`; create `tests/test_readme.py`.

---

### Task 1: `ticket_init.py` (cross-platform ticket folder setup)

**Files:**
- Create: `skills/marklogic-support/scripts/ticket_init.py`
- Create: `tests/test_ticket_init.py`

**Interfaces:**
- Produces (used by Task 3): CLI `ticket_init.py TICKET [--root DIR] [--check]`. Creates `<root>/<TICKET>/audit-trail/` with `Analysis.md Problems.md Required-Diagnostics.md Root-Cause.md Timeline.md` (each `# <Name>\n\n`), never touching existing files; prints the ticket directory then the file names; `--check` creates nothing and exits 1 with "not found" if the audit trail is missing; ids must match `[A-Za-z0-9][A-Za-z0-9._-]*` and not contain `..`. Default root = git top-level of the current directory, else the current directory. Python names: `project_root`, `check_id`, `check`, `init`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_ticket_init.py` exactly:

```python
import subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/marklogic-support/scripts/ticket_init.py"
sys.path.insert(0, str(SCRIPT.parent))
import ticket_init

FILES = ["Analysis.md", "Problems.md", "Required-Diagnostics.md", "Root-Cause.md", "Timeline.md"]


def run(*args, cwd=None):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, cwd=cwd)


class TicketInitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_creates_the_five_audit_files_with_title_lines(self):
        r = run("12345", "--root", self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        trail = self.root / "12345" / "audit-trail"
        self.assertEqual(sorted(p.name for p in trail.iterdir()), FILES)
        self.assertEqual((trail / "Timeline.md").read_text(), "# Timeline\n\n")
        self.assertEqual((trail / "Root-Cause.md").read_text(), "# Root-Cause\n\n")
        lines = r.stdout.splitlines()
        self.assertEqual(lines[0], str(self.root / "12345"))
        self.assertEqual(lines[1:], FILES)

    def test_never_truncates_existing_files(self):
        run("12345", "--root", self.root)
        f = self.root / "12345" / "audit-trail" / "Analysis.md"
        f.write_text("# Analysis\n\n## 2026-10-20 10:00 — [Diagnosis]\nkept\n")
        self.assertEqual(run("12345", "--root", self.root).returncode, 0)
        self.assertIn("kept", f.read_text())

    def test_rejects_ids_that_could_escape_the_root(self):
        for bad in ("../x", "a/b", "..", "", "-rf", "a b", ".hidden/.."):
            r = run(bad, "--root", self.root)
            self.assertNotEqual(r.returncode, 0, bad)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_accepts_typical_ids(self):
        for ok in ("12345", "ML-2026-10", "case_7.1"):
            self.assertEqual(run(ok, "--root", self.root).returncode, 0, ok)

    def test_default_root_is_the_git_toplevel(self):
        repo = self.root / "repo"; sub = repo / "sub" / "dir"; sub.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        r = run("777", cwd=sub)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((repo / "777" / "audit-trail" / "Timeline.md").exists())
        self.assertFalse((sub / "777").exists())

    def test_default_root_without_git_is_the_current_directory(self):
        d = self.root / "plain"; d.mkdir()
        self.assertEqual(run("888", cwd=d).returncode, 0)
        self.assertTrue((d / "888" / "audit-trail" / "Timeline.md").exists())

    def test_check_lists_an_existing_ticket_and_never_creates(self):
        r = run("404", "--root", self.root, "--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not found", r.stderr)
        self.assertFalse((self.root / "404").exists())
        run("404", "--root", self.root)
        r = run("404", "--root", self.root, "--check")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), [str(self.root / "404")] + FILES)

    def test_check_rejects_bad_ids(self):
        self.assertNotEqual(run("../x", "--root", self.root, "--check").returncode, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_ticket_init 2>&1 | tail -5`
Expected: ERROR — `No module named 'ticket_init'`.

- [ ] **Step 3: Write the implementation** — create `skills/marklogic-support/scripts/ticket_init.py` exactly:

```python
#!/usr/bin/env python3
"""Create a MarkLogic support ticket working directory and its audit trail.

Usage: ticket_init.py TICKET [--root DIR] [--check]
Creates <root>/<TICKET>/audit-trail/ with Timeline.md, Analysis.md, Required-Diagnostics.md,
Problems.md and Root-Cause.md (a title line each) when they do not exist; existing files are never
touched. <root> defaults to the git top-level directory of the current directory, else the current
directory. Prints the ticket directory and the audit-trail file names.
With --check nothing is created: it lists an existing ticket's audit trail, or exits 1 if the ticket
(or its audit-trail directory) does not exist.
"""
import argparse, re, subprocess, sys
from pathlib import Path

FILES = ["Timeline", "Analysis", "Required-Diagnostics", "Problems", "Root-Cause"]
TICKET_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def project_root(cwd):
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    except OSError:
        pass
    return Path(cwd)


def check_id(ticket):
    if not TICKET_RE.fullmatch(ticket) or ".." in ticket:
        sys.exit(f"ticket_init: invalid ticket id {ticket!r} (use letters, digits, '.', '_' and '-' only)")


def check(ticket, root):
    check_id(ticket)
    trail = Path(root) / ticket / "audit-trail"
    if not trail.is_dir():
        sys.exit(f"ticket_init: ticket {ticket} not found under {root} (no audit-trail/ directory)")
    return trail.parent, sorted(p.name for p in trail.iterdir())


def init(ticket, root):
    check_id(ticket)
    trail = Path(root) / ticket / "audit-trail"
    trail.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        f = trail / f"{name}.md"
        if not f.exists():
            f.write_text(f"# {name}\n\n")
    return trail.parent, sorted(p.name for p in trail.iterdir())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ticket")
    ap.add_argument("--root")
    ap.add_argument("--check", action="store_true", help="list an existing ticket; never create anything")
    a = ap.parse_args(argv)
    root = Path(a.root) if a.root else project_root(Path.cwd())
    ticket_dir, names = (check if a.check else init)(a.ticket, root)
    print(ticket_dir)
    print("\n".join(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the new tests and the whole suite**

Run: `python3 -W error::ResourceWarning -m unittest tests.test_ticket_init 2>&1 | tail -4` then `python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK` both times (8 new tests).

- [ ] **Step 5: Commit**

```bash
git add skills/marklogic-support/scripts/ticket_init.py tests/test_ticket_init.py
git commit -m "feat: ticket_init.py creates/checks a ticket folder and audit trail (cross-platform)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Installers (`install.sh`, `install.ps1`) and tests

**Files:**
- Create: `install.sh`, `install.ps1`, `.gitattributes`
- Create: `tests/test_install.py`

**Interfaces:**
- Produces (used by Task 4's README): the commands and options in Global Constraints; message prefixes `ok        `, `relinked  `, `linked    `, `copied    `, `backed up `, `stale     `, `missing   `, `conflict  `, `removed   `, `kept      `, `legacy    `, `moved     ` (the PowerShell test checks both scripts use the same words); marker file `.installed-by-marklogic-support-skill` in copied skills; exit code 1 when `status`/`install` found a problem, 2 for bad arguments.

- [ ] **Step 1: Write the failing tests** — create `tests/test_install.py` exactly:

```python
import os, shutil, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.home = self.base / "home"; self.home.mkdir()
        self.repo = self.base / "repo"
        for name in ("alpha", "beta"):
            (self.repo / "skills" / name).mkdir(parents=True)
            (self.repo / "skills" / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n")
        shutil.copy(INSTALL, self.repo / "install.sh")
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@e.com",
                        "commit", "-q", "-m", "init"], check=True)

    def run_install(self, *args):
        env = dict(os.environ, HOME=str(self.home))
        return subprocess.run(["bash", str(self.repo / "install.sh"), *args], capture_output=True, text=True, env=env)

    def link(self, root, name):
        return self.home / root / "skills" / name

    def test_install_links_every_skill_for_all_agents(self):
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stderr)
        for root in (".agents", ".claude"):
            for name in ("alpha", "beta"):
                p = self.link(root, name)
                self.assertTrue(p.is_symlink(), p)
                self.assertEqual(os.readlink(p), str(self.repo / "skills" / name))

    def test_install_is_idempotent(self):
        self.run_install()
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ok        ", r.stdout)
        self.assertNotIn("linked    ", r.stdout)

    def test_agents_option_selects_targets(self):
        self.assertEqual(self.run_install("--agents", "claude").returncode, 0)
        self.assertTrue(self.link(".claude", "alpha").is_symlink())
        self.assertFalse((self.home / ".agents").exists())
        self.assertEqual(self.run_install("--agents", "pi,codex,copilot").returncode, 0)
        self.assertTrue(self.link(".agents", "beta").is_symlink())
        r = self.run_install("--agents", "emacs")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown agent", r.stderr)

    def test_stale_symlink_to_another_clone_is_relinked(self):
        other = self.base / "other" / "alpha"; other.mkdir(parents=True)
        dest = self.link(".claude", "alpha"); dest.parent.mkdir(parents=True)
        dest.symlink_to(other)
        r = self.run_install("--agents", "claude")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("relinked", r.stdout)
        self.assertEqual(os.readlink(dest), str(self.repo / "skills" / "alpha"))

    def test_real_directory_is_not_overwritten_without_force(self):
        dest = self.link(".claude", "alpha"); dest.mkdir(parents=True)
        (dest / "mine.txt").write_text("mine")
        r = self.run_install("--agents", "claude")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--force", r.stderr)
        self.assertTrue((dest / "mine.txt").exists())
        self.assertTrue(self.link(".claude", "beta").is_symlink())      # other skills still installed
        r = self.run_install("--agents", "claude", "--force")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(dest.is_symlink())
        backups = [p for p in dest.parent.iterdir() if p.name.startswith("alpha.bak-")]
        self.assertEqual(len(backups), 1)
        self.assertTrue((backups[0] / "mine.txt").exists())

    def test_copy_mode_copies_and_update_refreshes(self):
        self.assertEqual(self.run_install("--agents", "claude", "--copy").returncode, 0)
        dest = self.link(".claude", "alpha")
        self.assertTrue(dest.is_dir() and not dest.is_symlink())
        self.assertTrue((dest / ".installed-by-marklogic-support-skill").exists())
        (self.repo / "skills" / "alpha" / "new.txt").write_text("new")
        self.assertEqual(self.run_install("update", "--no-pull", "--agents", "claude", "--copy").returncode, 0)
        self.assertTrue((dest / "new.txt").exists())

    def test_update_links_skills_added_since_install(self):
        self.run_install()
        (self.repo / "skills" / "gamma").mkdir()
        (self.repo / "skills" / "gamma" / "SKILL.md").write_text("---\nname: gamma\ndescription: x\n---\n")
        r = self.run_install("update", "--no-pull")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.link(".agents", "gamma").is_symlink())
        self.assertTrue(self.link(".claude", "gamma").is_symlink())

    def test_update_pulls_from_origin(self):
        origin = self.base / "origin"
        subprocess.run(["git", "clone", "-q", "--bare", str(self.repo), str(origin)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "remote", "add", "origin", str(origin)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "fetch", "-q", "origin"], check=True)
        branch = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True, check=True).stdout.strip()
        subprocess.run(["git", "-C", str(self.repo), "branch", "-q", f"--set-upstream-to=origin/{branch}"], check=True)
        work = self.base / "work"
        subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)
        (work / "skills" / "delta").mkdir()
        (work / "skills" / "delta" / "SKILL.md").write_text("---\nname: delta\ndescription: x\n---\n")
        for cmd in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@e.com", "commit", "-q", "-m", "add delta"],
                    ["push", "-q"]):
            subprocess.run(["git", "-C", str(work), *cmd], check=True)
        r = self.run_install("update")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("repository updated", r.stdout)
        self.assertTrue(self.link(".claude", "delta").is_symlink())

    def test_status_reports_ok_missing_stale_and_conflict(self):
        r = self.run_install("status", "--agents", "claude")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("missing   ", r.stdout)
        self.run_install("--agents", "claude")
        r = self.run_install("status", "--agents", "claude")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok        ", r.stdout)
        dest = self.link(".claude", "alpha"); dest.unlink(); dest.symlink_to(self.base)
        self.assertIn("stale     ", self.run_install("status", "--agents", "claude").stdout)
        dest.unlink(); dest.mkdir()
        self.assertIn("conflict  ", self.run_install("status", "--agents", "claude").stdout)

    def test_uninstall_removes_only_our_links(self):
        self.run_install()
        foreign = self.home / ".claude" / "skills" / "other"; foreign.mkdir()
        mine = self.link(".agents", "alpha"); mine.unlink(); mine.mkdir()      # now a foreign real dir
        r = self.run_install("uninstall")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.link(".claude", "alpha").exists())
        self.assertFalse(self.link(".agents", "beta").exists())
        self.assertTrue(foreign.exists())
        self.assertTrue(mine.exists())
        self.assertIn("kept", r.stdout)

    def test_legacy_command_files_are_reported_then_moved_aside(self):
        legacy = self.home / ".claude" / "commands"; legacy.mkdir(parents=True)
        (legacy / "kcs.md").write_text("old"); (legacy / "mine.md").write_text("keep")
        r = self.run_install("--agents", "claude")
        self.assertIn("legacy    ", r.stdout)
        self.assertTrue((legacy / "kcs.md").exists())
        r = self.run_install("--agents", "claude", "--clean-legacy")
        self.assertIn("moved     ", r.stdout)
        self.assertFalse((legacy / "kcs.md").exists())
        self.assertTrue((legacy / "mine.md").exists())
        self.assertEqual(len([p for p in legacy.iterdir() if p.name.startswith("kcs.md.bak-")]), 1)

    def test_help_and_bad_arguments(self):
        r = self.run_install("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("--agents", r.stdout)
        self.assertEqual(self.run_install("--bogus").returncode, 2)

    @unittest.skipUnless(shutil.which("shellcheck"), "shellcheck not installed")
    def test_shellcheck_clean(self):
        r = subprocess.run(["shellcheck", "-s", "bash", str(INSTALL)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)


class PowerShellScriptTest(unittest.TestCase):
    """install.ps1 is not executed in CI (no PowerShell); these checks only keep it in step with install.sh."""
    PS = (ROOT / "install.ps1").read_text()

    def test_is_ascii_and_has_the_same_commands_and_options(self):
        self.PS.encode("ascii")
        for needle in ("'install', 'update', 'status', 'uninstall'", "$Agents", "$Copy", "$Force", "$NoPull",
                       "$CleanLegacy", ".agents\\skills", ".claude\\skills", "-ItemType Junction",
                       "git -C $Repo pull --ff-only", ".installed-by-marklogic-support-skill"):
            self.assertIn(needle, self.PS, needle)

    def test_legacy_and_skill_names_match_install_sh(self):
        sh = INSTALL.read_text()
        for needle in ("ticket", "kcs", "kcs-review", ".claude", ".pi", ".codex"):
            self.assertIn(needle, self.PS)
            self.assertIn(needle, sh)

    def test_message_prefixes_match_install_sh(self):
        sh = INSTALL.read_text()
        for word in ("ok        ", "relinked  ", "linked    ", "copied    ", "stale     ", "missing   ",
                     "conflict  ", "removed   ", "kept      ", "legacy    ", "moved     ", "backed up "):
            self.assertIn(word, self.PS, word)
            self.assertIn(word, sh, word)

    def test_gitattributes_keeps_shell_script_lf(self):
        text = (ROOT / ".gitattributes").read_text()
        self.assertIn("*.sh text eol=lf", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_install 2>&1 | tail -6`
Expected: ERRORS — `install.sh` does not exist.

- [ ] **Step 3: Create the files.** `.gitattributes`:

```text
*.sh text eol=lf
*.ps1 text eol=crlf
```

`install.sh` (then `chmod +x install.sh`):

```bash
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
```

`install.ps1` (ASCII only — the test enforces it):

```powershell
<#
.SYNOPSIS
  Install, update, check or remove the MarkLogic support skills for pi, Claude Code, Codex and GitHub Copilot (Windows).

.DESCRIPTION
  Links (directory junctions, no administrator rights or Developer Mode needed) or copies the folders under
  skills\ into:
    %USERPROFILE%\.agents\skills\<skill>   read by pi, Codex and GitHub Copilot
    %USERPROFILE%\.claude\skills\<skill>   read by Claude Code (and by GitHub Copilot)
  Same behaviour as install.sh. This script has not been run in the project's automated tests.

.PARAMETER Command   install (default) | update | status | uninstall
.PARAMETER Agents    comma list of: pi, claude, codex, copilot, all (default all)
.PARAMETER Copy      copy the skill folders instead of linking (re-run update to refresh)
.PARAMETER Force     replace a real folder of the same name, keeping a .bak-<time> copy
.PARAMETER NoPull    update: do not run git pull first
.PARAMETER CleanLegacy  move superseded command files (ticket/kcs/kcs-review .md) aside to .bak-<time>

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\install.ps1
  powershell -ExecutionPolicy Bypass -File .\install.ps1 -Command update
#>
[CmdletBinding()]
param(
    [ValidateSet('install', 'update', 'status', 'uninstall')][string]$Command = 'install',
    [string]$Agents = 'all',
    [switch]$Copy,
    [switch]$Force,
    [switch]$NoPull,
    [switch]$CleanLegacy
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Mark = '.installed-by-marklogic-support-skill'
$script:Problems = 0

function Say($m) { Write-Output $m }
function Problem($m) { Write-Warning $m; $script:Problems++ }

# --- targets ---------------------------------------------------------------------------------------
$Targets = New-Object System.Collections.Generic.List[string]
function Add-Target($p) { if (-not $Targets.Contains($p)) { $Targets.Add($p) } }
foreach ($a in ($Agents -split ',')) {
    switch ($a.Trim().ToLower()) {
        'all'     { Add-Target (Join-Path $HOME '.agents\skills'); Add-Target (Join-Path $HOME '.claude\skills') }
        { $_ -in 'pi', 'codex', 'copilot' } { Add-Target (Join-Path $HOME '.agents\skills') }
        'claude'  { Add-Target (Join-Path $HOME '.claude\skills') }
        default   { Write-Error "unknown agent '$a' (use pi, claude, codex, copilot or all)"; exit 2 }
    }
}

function Get-Skills {
    Get-ChildItem -Directory (Join-Path $Repo 'skills') |
        Where-Object { Test-Path (Join-Path $_.FullName 'SKILL.md') } | ForEach-Object { $_.Name }
}

function Get-LinkTarget($path) {
    $item = Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
    if ($item -and $item.LinkType) { return [string]($item.Target | Select-Object -First 1) }
    return $null
}

function Remove-Link($path) { [System.IO.Directory]::Delete($path, $false) }    # removes the junction, not its contents

function Test-Ours($path) {
    $t = Get-LinkTarget $path
    if ($t) { return $t.StartsWith((Join-Path $Repo 'skills'), [System.StringComparison]::OrdinalIgnoreCase) }
    return (Test-Path -LiteralPath (Join-Path $path $Mark))
}

function Install-One($name, $tdir) {
    $src = Join-Path (Join-Path $Repo 'skills') $name
    $dest = Join-Path $tdir $name
    New-Item -ItemType Directory -Force -Path $tdir | Out-Null
    $existing = Get-Item -LiteralPath $dest -Force -ErrorAction SilentlyContinue
    if ($existing) {
        $lt = Get-LinkTarget $dest
        if ($lt) {
            if (-not $Copy -and $lt -eq $src) { Say "ok        $dest"; return }
            Remove-Link $dest; Say "relinked  $dest (was -> $lt)"
        }
        elseif (Test-Path -LiteralPath (Join-Path $dest $Mark)) { Remove-Item -Recurse -Force -LiteralPath $dest }
        elseif ($Force) { Move-Item -LiteralPath $dest -Destination "$dest.bak-$Stamp"; Say "backed up $dest -> $dest.bak-$Stamp" }
        else { Problem "$dest exists and is not managed by this installer; re-run with -Force to replace it (a backup is kept)"; return }
    }
    if ($Copy) {
        Copy-Item -Recurse -LiteralPath $src -Destination $dest
        New-Item -ItemType File -Path (Join-Path $dest $Mark) | Out-Null
        Say "copied    $dest"
    }
    else {
        New-Item -ItemType Junction -Path $dest -Target $src | Out-Null
        Say "linked    $dest -> $src"
    }
}

function Status-One($name, $tdir) {
    $src = Join-Path (Join-Path $Repo 'skills') $name
    $dest = Join-Path $tdir $name
    $lt = Get-LinkTarget $dest
    if ($lt) {
        if ($lt -eq $src) { Say "ok        $dest" } else { Say "stale     $dest -> $lt (run: .\install.ps1 -Command update)"; $script:Problems++ }
    }
    elseif (Test-Path -LiteralPath (Join-Path $dest $Mark)) { Say "copy      $dest (refresh with: .\install.ps1 -Command update -Copy)" }
    elseif (Test-Path -LiteralPath $dest) { Say "conflict  $dest is not managed by this installer"; $script:Problems++ }
    else { Say "missing   $dest"; $script:Problems++ }
}

function Uninstall-One($name, $tdir) {
    $dest = Join-Path $tdir $name
    if (Test-Path -LiteralPath $dest) {
        if (Test-Ours $dest) {
            if (Get-LinkTarget $dest) { Remove-Link $dest } else { Remove-Item -Recurse -Force -LiteralPath $dest }
            Say "removed   $dest"
        }
        else { Say "kept      $dest (not installed by this repo)" }
    }
}

function Show-Legacy {
    foreach ($d in @((Join-Path $HOME '.claude\commands'), (Join-Path $HOME '.pi\agent\prompts'), (Join-Path $HOME '.codex\prompts'))) {
        foreach ($n in 'ticket', 'kcs', 'kcs-review') {
            $f = Join-Path $d "$n.md"
            if (-not (Test-Path -LiteralPath $f)) { continue }
            if ($CleanLegacy) { Move-Item -LiteralPath $f -Destination "$f.bak-$Stamp"; Say "moved     $f -> $f.bak-$Stamp (superseded by the $n skill)" }
            else { Say "legacy    $f is superseded by the '$n' skill; remove it with -CleanLegacy" }
        }
    }
}

function Show-Deps {
    if (-not ((Get-Command python3 -ErrorAction SilentlyContinue) -or (Get-Command python -ErrorAction SilentlyContinue) -or (Get-Command py -ErrorAction SilentlyContinue))) {
        Problem 'Python 3 not found: the analysis and ticket scripts need it (install from https://www.python.org/downloads/)'
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Write-Warning "git not found: needed for 'update'" }
    if (-not (Get-Command pandoc -ErrorAction SilentlyContinue)) { Say 'note      pandoc not found: /kcs cannot write the Word/HTML versions until it is installed (https://pandoc.org/installing.html)' }
}

function Get-Commit { try { (& git -C $Repo rev-parse --short HEAD 2>$null) } catch { 'unknown' } }

# --- run -------------------------------------------------------------------------------------------
if ($Command -eq 'update' -and -not $NoPull) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Write-Error 'git is required for update (or use -NoPull)'; exit 1 }
    $before = Get-Commit
    & git -C $Repo pull --ff-only
    if ($LASTEXITCODE -ne 0) { Write-Error 'git pull failed; fix the repository (local changes? no network?) and re-run, or use -NoPull'; exit 1 }
    $after = Get-Commit
    if ($before -eq $after) { Say "repository already at $after" } else { Say "repository updated $before -> $after" }
}

$Skills = @(Get-Skills)
if ($Skills.Count -eq 0) { Write-Error "no skills found under $Repo\skills"; exit 1 }

switch ($Command) {
    { $_ -in 'install', 'update' } {
        foreach ($t in $Targets) { foreach ($s in $Skills) { Install-One $s $t } }
        Show-Legacy; Show-Deps
    }
    'status' {
        Say "repository $Repo at $(Get-Commit)"
        foreach ($t in $Targets) { foreach ($s in $Skills) { Status-One $s $t } }
        Show-Legacy; Show-Deps
    }
    'uninstall' {
        foreach ($t in $Targets) { foreach ($s in $Skills) { Uninstall-One $s $t } }
    }
}

if ($script:Problems -gt 0) { exit 1 }
exit 0
```

- [ ] **Step 4: Run the tests, shellcheck and the whole suite**

Run: `chmod +x install.sh && python3 -W error::ResourceWarning -m unittest tests.test_install 2>&1 | tail -4 && shellcheck -s bash install.sh && python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK` (17 tests), no shellcheck output, `OK`.

- [ ] **Step 5: Smoke-test against the real repository in a throw-away HOME** (never touch the real home):

```bash
H=$(mktemp -d); HOME=$H ./install.sh && HOME=$H ./install.sh status && ls -l $H/.agents/skills $H/.claude/skills; HOME=$H ./install.sh uninstall && ls $H/.agents/skills $H/.claude/skills; rm -rf $H
```
Expected: at this point the repository has only the `marklogic-support` skill (Task 3 adds the others): install links it into both folders, `status` reports `ok` for each, uninstall removes the links.

- [ ] **Step 6: Commit**

```bash
git add install.sh install.ps1 .gitattributes tests/test_install.py
git commit -m "feat: install.sh / install.ps1 install, update, check and remove the skills for all four agents

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Convert the prompts to skills

**Files:**
- Create: `skills/ticket/SKILL.md`
- Move + modify: `prompts/kcs.md` → `skills/kcs/SKILL.md`; `prompts/kcs-review.md` → `skills/kcs-review/SKILL.md` (use `git mv`, then edit)
- Delete: `prompts/` (after the moves, `prompts/ticket.md` is deleted with `git rm`)
- Modify: `skills/marklogic-support/SKILL.md`, `package.json`, `tests/test_security_docs.py`
- Test: `tests/test_skill_layout.py` (create)

**Interfaces:**
- Consumes: `scripts/ticket_init.py` (Task 1). The workflow skills locate the `marklogic-support` directory with the shared locate paragraph and then call `<skill-dir>/scripts/...`.

- [ ] **Step 1: Write the failing layout test** — create `tests/test_skill_layout.py` exactly:

```python
import re, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted(p for p in (ROOT / "skills").iterdir() if (p / "SKILL.md").exists())
EXPECTED = {"marklogic-support", "ticket", "kcs", "kcs-review"}


def frontmatter(path):
    m = re.match(r"---\n(.*?)\n---\n", path.read_text(), re.S)
    assert m, f"{path} has no frontmatter"
    return dict(l.split(":", 1) for l in m.group(1).splitlines() if ":" in l and not l.startswith(" "))


class SkillLayoutTest(unittest.TestCase):
    def test_the_four_skills_exist(self):
        self.assertEqual({p.name for p in SKILLS}, EXPECTED)

    def test_frontmatter_name_matches_folder_and_is_valid(self):
        for p in SKILLS:
            fm = frontmatter(p / "SKILL.md")
            self.assertEqual(fm["name"].strip(), p.name, p)
            self.assertRegex(p.name, r"^[a-z0-9]+(-[a-z0-9]+)*$")
            self.assertTrue(fm.get("description", "").strip(), p)

    def test_no_agent_specific_leftovers_in_the_workflow_skills(self):
        for name in ("ticket", "kcs", "kcs-review"):
            text = (ROOT / "skills" / name / "SKILL.md").read_text()
            self.assertNotIn("$1", text, name)                      # $1 is the second argument in Claude Code
            self.assertNotIn(".pi/", text, name)
            self.assertNotIn("PI_CODING_AGENT_DIR", text, name)
            self.assertNotIn("prompts/", text, name)
            self.assertIn("~/.agents/skills/marklogic-support", text, name)
            self.assertIn("$ARGUMENTS", text, name)

    def test_ticket_skill_uses_the_cross_platform_script_not_bash(self):
        text = (ROOT / "skills/ticket/SKILL.md").read_text()
        self.assertIn("scripts/ticket_init.py", text)
        self.assertNotIn("mkdir -p", text)
        self.assertNotIn("printf", text)
        kcs = (ROOT / "skills/kcs/SKILL.md").read_text()
        self.assertIn("ticket_init.py", kcs)
        self.assertIn("--check", kcs)
        self.assertNotIn("git rev-parse", kcs)

    def test_prompts_folder_is_gone_and_nothing_points_at_it(self):
        self.assertFalse((ROOT / "prompts").exists())
        for p in [ROOT / "README.md", ROOT / "package.json", *ROOT.glob("skills/**/*.md"), *ROOT.glob("tests/*.py")]:
            if p.name == "test_skill_layout.py":
                continue
            self.assertNotIn("prompts/", p.read_text(), str(p))

    def test_pi_package_manifest_lists_skills_only(self):
        import json
        pkg = json.loads((ROOT / "package.json").read_text())
        self.assertEqual(pkg["pi"], {"skills": ["skills"]})
        self.assertEqual(pkg["version"], "1.1.0")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_skill_layout 2>&1 | tail -8`
Expected: FAIL — only `marklogic-support` exists, `prompts/` still exists.

- [ ] **Step 3: Create `skills/ticket/SKILL.md`** exactly (and `git rm prompts/ticket.md`):

````markdown
---
name: ticket
description: Set up a working directory and audit trail for a MarkLogic support ticket and load the marklogic-support skill. Use when the user runs /ticket <number> or asks to start work on a support ticket.
argument-hint: <ticket number>
---

This is the `ticket` workflow (`/ticket <number>`) the user's own team maintains for triaging MarkLogic support tickets. It sets up a per-ticket working directory and its persistent audit trail, and loads the team's `marklogic-support` skill before asking for the ticket's problem description. The imperative wording below ("run this command now", "do not paraphrase") exists only because earlier testing found that softer, descriptive phrasing was sometimes narrated by the model instead of executed, or a step was silently skipped — it is a plain internal workflow for creating a folder and reading documentation files.

Ticket number: $ARGUMENTS

(If the line above still shows the literal text `$ARGUMENTS`, or nothing, take the ticket number from the user's message — for example `/skill:ticket 12345` or "start ticket 12345".)

1. **Locate the `marklogic-support` skill directory** (it holds `SKILL.md`, `references/` and `scripts/`; call it `<skill-dir>`). Check, in this order, and use the first that exists: `~/.agents/skills/marklogic-support`, `~/.claude/skills/marklogic-support`, `~/.copilot/skills/marklogic-support`, then in the project (the current directory and its parents up to the repository root) `.agents/skills/marklogic-support`, `.claude/skills/marklogic-support`, `.github/skills/marklogic-support`, then `skills/marklogic-support` if this repository is checked out. Do not search the filesystem. If none exists (or a symlink is broken), tell the user the skill is not installed and that the repository README explains how to install it, then stop. Scripts below are run with `python3`; on Windows use `python` or `py -3` if `python3` is not available.

2. Validate the ticket number is non-empty; if missing, ask the user in plain chat text (not a structured/multiple-choice question tool — the answer needs to be free-form pasted text) for the ticket reference number, and stop here. Otherwise run this single command now, in full, as one call — do not split it, paraphrase it, or substitute a path:

   ```
   python3 <skill-dir>/scripts/ticket_init.py "<ticket>"
   ```

   It creates the ticket working directory under the project root (the git top-level directory, else the current directory) and its persistent audit trail (5 files under `audit-trail/` — every ticket gets one, this is not optional), never truncating a file that already has content, and prints the ticket directory followed by the files. Check the output lists all 5 files (`Analysis.md`, `Problems.md`, `Required-Diagnostics.md`, `Root-Cause.md`, `Timeline.md`) — if any are missing or the command fails, say so and stop. See `references/ticket-auditing.md` in the skill for the format each file follows. All later tool calls in this session should default to the printed ticket directory.

3. Load the MarkLogic support skill now: read `<skill-dir>/SKILL.md` in full and follow its instructions for the rest of this session exactly as if the user had invoked the `marklogic-support` skill directly.

4. Check whether the user's message already contains the ticket's problem description (pasted text, an error log, a dump path, etc.) beyond just the ticket number.

5. If it does, proceed straight into analysis using the skill's instructions (which includes updating the audit trail — see the skill's "Audit trail" section). If it does not, ask the user in plain chat text (not a structured/multiple-choice question tool) to paste the ticket's problem description, and wait for their reply before doing any analysis. In either case, before any analysis, apply the skill's security check (`references/security-vulnerability-handling.md`): a security incident stops at the incident gate; a security vulnerability prints the banner and checklist first.
````

- [ ] **Step 4: Move and edit the other two.** `mkdir -p skills/kcs skills/kcs-review && git mv prompts/kcs.md skills/kcs/SKILL.md && git mv prompts/kcs-review.md skills/kcs-review/SKILL.md`. Read each file, then make these edits with the Edit tool (each anchor must match exactly once; if not, stop and report NEEDS_CONTEXT with details). Use this paragraph wherever `LOCATE` appears below:

> **Locate the `marklogic-support` skill directory** (it holds `SKILL.md`, `references/` and `scripts/`; call it `<skill-dir>`). Check, in this order, and use the first that exists: `~/.agents/skills/marklogic-support`, `~/.claude/skills/marklogic-support`, `~/.copilot/skills/marklogic-support`, then in the project (the current directory and its parents up to the repository root) `.agents/skills/marklogic-support`, `.claude/skills/marklogic-support`, `.github/skills/marklogic-support`, then `skills/marklogic-support` if this repository is checked out. Do not search the filesystem. If none exists (or a symlink is broken), tell the user the skill is not installed and that the repository README explains how to install it, then stop.

**`skills/kcs/SKILL.md`:**
1. Replace the YAML frontmatter (the first block between `---` lines) with:
```
---
name: kcs
description: Write a compliant KCS article (Markdown, Word, Salesforce HTML) from a completed MarkLogic support ticket. Use when the user runs /kcs or asks for a KCS article for a finished ticket.
argument-hint: [ticket number]
---
```
2. In the intro paragraph replace "(see `/ticket` in `prompts/ticket.md`, which creates the ticket folder and its `audit-trail/`)" with "(see the `ticket` skill, which creates the ticket folder and its `audit-trail/`)".
3. Replace the line `Ticket argument: $1` with these two lines:
```
Ticket argument: $ARGUMENTS

(If the line above still shows the literal text `$ARGUMENTS`, or nothing, take the ticket number from the user's message — for example `/skill:kcs 12345` or "write the KCS article for ticket 12345" — and if there is none, the ticket opened by the `ticket` skill earlier in this session.)
```
4. Replace the whole of step 1 ("**Resolve the ticket.**" with its three bullets) with:
```
1. **Resolve the ticket.**
   - If there is a ticket number (from the argument, the user's message, or the `ticket` skill earlier in this same session), that is the ticket. LOCATE Then run `python3 <skill-dir>/scripts/ticket_init.py --check "<ticket>"` (on Windows use `python` or `py -3` if `python3` is unavailable). If it reports the ticket was not found, tell the user ticket `<ticket>` was not found under the project root and stop — do not create it (that is the `ticket` skill's job).
   - If there is no ticket number, ask the user in plain chat text for an existing ticket number, and stop.
   - Work from the ticket directory the script printed from here on.
```
(with the LOCATE paragraph pasted in place of the word LOCATE).
5. In step 2 ("**Load the skill material.**") replace everything from "Read `skills/marklogic-support/references/kcs-writing.md`" up to and including "Set `<skill-dir>` to the directory that holds it." with "Read `<skill-dir>/references/kcs-writing.md` (`<skill-dir>` was located in step 1)."

**`skills/kcs-review/SKILL.md`:**
1. Replace the YAML frontmatter with:
```
---
name: kcs-review
description: Review a KCS article written by another engineer (md/html/docx or pasted text) and write the revised article as Markdown, Word and Salesforce HTML. Use when the user runs /kcs-review or asks to review a KCS article.
argument-hint: [path to article]
---
```
2. In the intro replace "(see `/kcs` in `prompts/kcs.md`, which writes articles from a ticket)" with "(see the `kcs` skill, which writes articles from a ticket)".
3. After the line `Article path argument (optional, may contain spaces): $ARGUMENTS` add a blank line and: `(If the line above still shows the literal text `$ARGUMENTS`, the user gave no path in this invocation; if they gave one in their message, for example `/skill:kcs-review path/to/article.md`, use that.)`
4. In step 1 ("**Load the skill material.**") replace everything from "Read `skills/marklogic-support/references/kcs-writing.md`" up to and including "Set `<skill-dir>` to the directory that holds it." with "LOCATE Read `<skill-dir>/references/kcs-writing.md`." (with the LOCATE paragraph pasted in place of the word LOCATE).

Then `git rm -r --quiet prompts` (the folder must no longer exist; `ls prompts` fails).

- [ ] **Step 5: Update the marklogic-support skill, package.json and the older test**

1. `skills/marklogic-support/SKILL.md`: replace "On `/kcs` (see `prompts/kcs.md`)" with "On `/kcs` (the `kcs` skill)" and "On `/kcs-review` (see `prompts/kcs-review.md`)" with "On `/kcs-review` (the `kcs-review` skill)". Immediately before the line `## Triage mode` add a paragraph: "Scripts are run with `python3`; on Windows use `python` or `py -3` if `python3` is not available."
2. `package.json` — replace the whole file with:
```json
{
  "name": "marklogic-support-skill",
  "version": "1.1.0",
  "description": "Agent skills for MarkLogic support engineers (pi, Claude Code, Codex, GitHub Copilot): triage configuration, security, performance, monitoring and DR/scaling issues, analyse support dumps, logs and SAR data, write and review KCS articles.",
  "keywords": ["pi-package", "pi-skill", "agent-skills", "claude-code", "codex", "github-copilot", "marklogic"],
  "license": "MIT",
  "pi": {
    "skills": ["skills"]
  }
}
```
3. `tests/test_security_docs.py`: replace every `ROOT / "prompts/ticket.md"` with `ROOT / "skills/ticket/SKILL.md"`, `ROOT / "prompts/kcs.md"` with `ROOT / "skills/kcs/SKILL.md"` and `ROOT / "prompts/kcs-review.md"` with `ROOT / "skills/kcs-review/SKILL.md"`. If an assertion about ticket.md fails because the text moved, fix the test to look at the same sentence in the new file — do not weaken what it checks.

- [ ] **Step 6: Run the full suite and the layout checks**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -4` and `grep -rn 'prompts/' skills README.md package.json tests tools | grep -v test_skill_layout.py` (the grep must print nothing).
Expected: `OK`; empty grep.

- [ ] **Step 7: Smoke-test the converted skills** with the throw-away-HOME install from Task 2 Step 5 (now four skills are listed) and run `python3 skills/marklogic-support/scripts/ticket_init.py SMOKE-1 --root "$(mktemp -d)"`, then `... --check SMOKE-1 --root <same dir>`.
Expected: four skills linked in both folders; the script prints the directory and five file names, and `--check` succeeds.

- [ ] **Step 8: Commit**

```bash
git add -A skills package.json tests prompts
git commit -m "feat: /ticket, /kcs and /kcs-review become skills; prompts/ removed

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
(`git add -A prompts` stages the deletions; do not add any untracked file outside `skills`, `tests`, `package.json`, `prompts`.)

---

### Task 4: README rewrite

**Files:**
- Rewrite: `README.md`
- Create: `tests/test_readme.py`

**Interfaces:**
- Consumes: everything above (installer options, skill names, scripts, reference file names). `tests/test_readme.py` fails if a script, a reference file or a skill is missing from the README.

- [ ] **Step 1: Write the failing test** — create `tests/test_readme.py` exactly:

```python
import re, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text()
SKILL = ROOT / "skills/marklogic-support"


class ReadmeTest(unittest.TestCase):
    def test_install_update_and_troubleshooting_sections_exist(self):
        for h in ("## Requirements", "## Install", "### macOS and Linux", "### Windows", "### Per agent",
                  "### Without the script", "## Update", "## Use", "## Uninstall", "## Troubleshooting"):
            self.assertIn(h + "\n", README, h)

    def test_names_all_four_agents_and_both_skill_folders(self):
        for word in ("Claude Code", "pi", "Codex", "GitHub Copilot", "~/.agents/skills", "~/.claude/skills",
                     ".github/skills", "install.sh", "install.ps1", "<repo-url>"):
            self.assertIn(word, README, word)

    def test_documents_the_update_commands(self):
        for cmd in ("./install.sh update", "pi update --extensions", "--clean-legacy", "./install.sh status",
                    "-Command update"):
            self.assertIn(cmd, README, cmd)

    def test_every_skill_script_and_reference_is_listed(self):
        for p in (SKILL / "scripts").glob("*.py"):
            self.assertIn(p.name, README, p.name)
        for p in (SKILL / "references").glob("*.md"):
            self.assertIn(p.stem, README, p.stem)
        for p in (ROOT / "skills").iterdir():
            if (p / "SKILL.md").exists():
                self.assertIn(p.name, README, p.name)

    def test_no_stale_claims(self):
        self.assertNotIn("prompts/", README)
        self.assertNotIn("neither has first-class skill discovery", README)
        self.assertNotIn("/skill:marklogic-support <ticket text", README)

    def test_invocation_table_matches_each_agents_syntax(self):
        self.assertIn("`/ticket 12345`", README)             # Claude Code
        self.assertIn("`/skill:ticket 12345`", README)       # pi
        self.assertIn("`$ticket 12345`", README)             # Codex

    def test_local_links_and_paths_in_the_readme_exist(self):
        for rel in re.findall(r"`((?:skills|tools|tests)/[\w./-]+)`", README):
            if "<" in rel or rel.endswith("/"):
                continue
            self.assertTrue((ROOT / rel).exists(), rel)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_readme 2>&1 | tail -8`
Expected: FAIL — the current README has none of the new sections.

- [ ] **Step 3: Replace `README.md`** with exactly this content (the repository URL stays the literal placeholder `<repo-url>`):

`````markdown
# marklogic-support-skill

Agent skills for MarkLogic support engineers. They work with [pi](https://pi.dev),
[Claude Code](https://code.claude.com/docs/en/skills), [OpenAI Codex](https://learn.chatgpt.com/docs/build-skills)
and GitHub Copilot ([CLI, VS Code agent mode and the cloud agent](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/create-skills)),
because all four read skills in the [Agent Skills](https://agentskills.io/specification) format (a folder with a `SKILL.md`).

What they do:

- **Triage** MarkLogic tickets: configuration, security, performance/tuning, monitoring, DR/scaling,
  server-side code (XQuery/JS/REST extensions) and client tooling (XCC, Java Client API, mlcp, ml-gradle, CoRB2).
- **Analyse** MarkLogic support dumps, logs (ErrorLog, messages, AccessLog, AuditLog) and Linux SAR data into
  incident timelines and ranked findings, and ask the customer for the right host-level data when it is missing.
- **Write and review KCS articles** that follow the company Solution Content Standard.
- **Follow the Progress security process** for vulnerability and security-incident tickets.

## The skills

| Skill | What it does | How to start it |
| --- | --- | --- |
| `marklogic-support` | Triage method, reference notes, dump/log/SAR analysis. The other three skills build on it. | Describe the problem, or paste a ticket, a dump path or a log path |
| `ticket` | Creates the ticket folder and its audit trail, loads `marklogic-support`, asks for the problem description | `/ticket 12345` |
| `kcs` | Drafts a KCS article from a finished ticket and renders Markdown, Word and Salesforce HTML | `/kcs 12345` |
| `kcs-review` | Reviews another engineer's KCS article and writes the revised version | `/kcs-review path/to/article.md` |

How you start a skill depends on the agent:

| Agent | Starting `ticket` | Notes |
| --- | --- | --- |
| Claude Code | `/ticket 12345` | A skill is a slash command named after its folder |
| pi | `/skill:ticket 12345` | Text after the name is passed to the skill |
| Codex | `$ticket 12345` (or `/skills` to pick) | Codex can also pick a skill from its description |
| GitHub Copilot | "use the ticket skill for case 12345" | Copilot chooses a skill from its description; there is no slash command for skills |

## Requirements

- **Python 3** — the analysis, rendering and ticket scripts use the standard library only. On Windows the agent
  may need `python` or `py -3` where the skills say `python3`.
- **git** — to install and update.
- **[pandoc](https://pandoc.org/installing.html)** (optional) — Word and HTML output for `kcs`, and `.html`/`.docx`
  input for `kcs-review`. Everything else works without it.
- One of the four agents above.

## Install

The repository holds the skills in `skills/`. The installer links each skill folder into the two folders the
agents read, so there is one copy on disk and updating is a `git pull`:

| Folder | Read by |
| --- | --- |
| `~/.agents/skills/` | pi, Codex, GitHub Copilot |
| `~/.claude/skills/` | Claude Code (and GitHub Copilot) |

### macOS and Linux

```bash
git clone <repo-url> ~/marklogic-support-skill
cd ~/marklogic-support-skill
./install.sh              # all four agents; see ./install.sh --help
./install.sh status       # check what is installed where
```

Then restart your agent (Codex and others only look for new skills at start-up).

Options: `--agents pi,claude,codex,copilot` (default `all`), `--copy` (copy instead of link), `--force`
(replace a real folder of the same name; a `.bak-<time>` copy is kept), `--clean-legacy` (see Update).

### Windows

```powershell
git clone <repo-url> $HOME\marklogic-support-skill
cd $HOME\marklogic-support-skill
powershell -ExecutionPolicy Bypass -File .\install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Command status
```

`install.ps1` links with directory junctions, which need no administrator rights. If an agent does not follow a
junction, use `-Copy`, and re-run `-Command update -Copy` after each update. Options: `-Agents`, `-Copy`, `-Force`,
`-NoPull`, `-CleanLegacy`. The Windows script is not run by the project's automated tests; please report problems.

### Per agent

- **Claude Code** — reads `~/.claude/skills/<name>/SKILL.md` and follows symlinked skill folders
  ([docs](https://code.claude.com/docs/en/skills)). Skills named `ticket`, `kcs` and `kcs-review` become
  `/ticket`, `/kcs` and `/kcs-review`.
- **pi** — reads `~/.agents/skills/` ([docs](https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/docs/skills.md)).
  You can also install the repository as a pi package instead of using the script:
  `pi install git:<repo-url>` (add `-l` to install for one project and record it in `.pi/settings.json`).
- **Codex** — reads `~/.agents/skills/` and follows symlinked skill folders
  ([docs](https://learn.chatgpt.com/docs/build-skills)). Codex custom prompts (`~/.codex/prompts`) are
  [deprecated](https://learn.chatgpt.com/docs/custom-prompts) in favour of skills, which is why the
  workflows here are skills too.
- **GitHub Copilot** — reads `~/.agents/skills/`, `~/.copilot/skills/` and `~/.claude/skills/` for personal skills,
  and `.github/skills/`, `.claude/skills/` or `.agents/skills/` inside a repository
  ([docs](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/create-skills)). The docs describe no
  organisation-wide distribution of skills, so on Copilot Enterprise each engineer installs the skills with the
  script, or a team commits them under `.github/skills/` in its own repository. The GitHub CLI's `gh skill`
  command (preview, GitHub CLI 2.90 or later) can also install skills from a GitHub repository; its exact usage is
  not covered here.

### Without the script

```bash
mkdir -p ~/.agents/skills ~/.claude/skills
for s in marklogic-support ticket kcs kcs-review; do
  ln -sfn ~/marklogic-support-skill/skills/$s ~/.agents/skills/$s
  ln -sfn ~/marklogic-support-skill/skills/$s ~/.claude/skills/$s
done
```

For one project only, create the same links under `<project>/.agents/skills/` (and `.claude/skills/` for Claude
Code, `.github/skills/` for Copilot).

## Update

```bash
cd ~/marklogic-support-skill
./install.sh update                 # git pull --ff-only, then re-link (picks up new skills); use --no-pull to skip the pull
./install.sh status
```

Windows: `.\install.ps1 -Command update`. Restart the agent afterwards.

- Because the installed skills are links to the clone, a plain `git pull` also updates them. `update` additionally
  links skills added in the new version and reports the old and new commit.
- **pi package installs:** `pi update --extensions` updates all installed packages, or `pi update git:<repo-url>`
  updates just this one (`pi update` on its own updates pi itself).
- **Copy installs** (`--copy` / `-Copy`) are not links: run `./install.sh update --copy` to refresh them.
- **Older versions of this repository** shipped `/ticket`, `/kcs` and `/kcs-review` as command files that people
  copied into `~/.claude/commands/` (or the pi/Codex prompt folders). Those copies do not update and are replaced by
  the skills. `install.sh` lists any it finds; `./install.sh update --clean-legacy` moves them aside to `.bak-<time>`.
- A skill link that pointed at a different clone is re-pointed at this one (the output says `relinked`).

## Use

Start a ticket, work it, and write it up:

```
/ticket 12345                     # creates 12345/audit-trail/, loads marklogic-support, asks for the problem
...triage, paste a dump or log path, a SAR file, ask follow-up questions...
/kcs 12345                        # draft the KCS article from the audit trail
/kcs-review path/to/article.md    # review someone else's article
```

(Use the form for your agent from the table above.) The skill classifies the input (ticket, question, support
dump, log files, SAR output) and routes to the right reference notes. See `skills/marklogic-support/SKILL.md`
for the routing table and output formats.

### Support dumps, logs and SAR data

`parse_dump.py` splits a support dump into config, status and logs with findings; `analyse_logs.py` classifies
ErrorLog, messages, AccessLog and AuditLog into an incident timeline; `analyse_sar.py` reads `sar -A` text output
and ranks saturation (iowait, disk latency, swap, memory, run queue, steal, network errors).
`performance-data-requests.md` holds ready-to-paste customer requests for SAR, iostat/vmstat/mpstat/pidstat,
kernel and OOM messages, thread dumps and, on cloud-hosted customers only, steal and EBS signals.

### Security tickets

A ticket that mentions a security incident, malware or a virus stops at an **incident gate**: no customer dump or
log is analysed until you confirm the Progress Security team and your manager are engaged. A vulnerability ticket
(CVE, CVSS, scanner output) prints the Progress process checklist first. See
`skills/marklogic-support/references/security-vulnerability-handling.md`.

### KCS articles

`kcs` writes `<ticket>/kcs/kcs-<ticket>-<problem|howto|troubleshoot>-<slug>.{md,docx,html}` — Markdown (canonical),
Word, and Salesforce-paste-ready HTML. Articles follow the company Solution Content Standard
(`KCS_SolutionContentStandard.txt`): 20 fields, title of 55 characters or fewer (70 at most), URL derived from the
title, a short symptom-only summary, standard Cause and Resolution statements. `kcs_render.py` checks these and prints
warnings; Internal Comments and Admin Ticket ID are always left for manual entry in Salesforce. The word "breach" is
rejected.

`kcs-review` reviews an article another engineer wrote (`.md`, `.html` or `.docx`, or pasted text), groups findings
as must-fix, should-fix or optional, and on acceptance writes `kcs-<title-slug>.{md,docx,html}` to `kcs-drafts/` if
that folder exists, otherwise to the working directory. The original is never modified.

## Uninstall

```bash
./install.sh uninstall          # removes only links (or marked copies) that point into this clone
```

Windows: `.\install.ps1 -Command uninstall`. Then delete the clone.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| The agent does not see the skills | Restart it. Run `./install.sh status` and check the folder for your agent (table above). |
| `status` says `stale` | Run `./install.sh update`; the link points at another clone. |
| `status` says `conflict` | A real folder with that name exists. Move it away, or re-run with `--force` (a backup is kept). |
| `/ticket 12345` does nothing in pi | pi skills are started as `/skill:ticket 12345`. |
| `/kcs` or `/ticket` still behaves like an old version | An old copy in `~/.claude/commands/` (or the pi/Codex prompt folder) is shadowing the skill: `./install.sh update --clean-legacy`. |
| "pandoc not found" from `kcs` | Install pandoc (https://pandoc.org/installing.html); the Markdown article is already written. |
| `python3` not found (Windows) | Install Python 3; the agent can run the scripts with `python` or `py -3`. |
| Windows: the agent ignores the linked skills | Re-run with `-Copy` (and `-Command update -Copy` after each update). |
| `git pull` fails during `update` | Commit or stash local changes in the clone, or run `update --no-pull`. |

## What's included

```
install.sh  install.ps1          install / update / status / uninstall (macOS+Linux / Windows)
skills/
├── marklogic-support/           triage method, routing table, dump / log / SAR modes
│   ├── SKILL.md
│   ├── scripts/
│   │   ├── parse_dump.py        splits a support dump into config/status/logs + findings
│   │   ├── analyse_logs.py      ErrorLog/messages/AccessLog/AuditLog -> incident timeline + patterns
│   │   ├── analyse_sar.py       sar -A text -> ranked saturation findings + per-host series
│   │   ├── kcs_render.py        KCS article .md -> .docx and Salesforce .html (pandoc), SCS checks
│   │   └── ticket_init.py       creates / checks a ticket folder and its audit trail
│   └── references/              each domain: Concepts -> Standard procedures -> Common mistakes
│       architecture · cluster-hosts-groups · databases-forests · app-servers · security
│       ha-backup-failover · memory-and-os · monitoring · performance-tuning · dr-scaling
│       app-code-review · client-integration · supportdump-anatomy · log-anatomy
│       sar-analysis · performance-data-requests · security-vulnerability-handling
│       ticket-auditing · kcs-writing · sources
├── ticket/SKILL.md              /ticket
├── kcs/SKILL.md                 /kcs
└── kcs-review/SKILL.md          /kcs-review
tests/    unit tests for the scripts, installer and documentation wiring (unittest, stdlib only)
tools/    check-ref.sh — validates the fixed reference-file shape
```

## Verifying and maintaining

Every mistake row in `references/*.md` cites a real doc URL, an `Inside MarkLogic Server` PDF page, or is marked
`[unverified — confirm]` — never silently fabricated. Before adding or editing a row: fetch the source, confirm it
supports the exact claim, then run

```bash
tools/check-ref.sh skills/marklogic-support/references/<file>.md
python3 -m unittest discover -s tests
```

## Licence

MIT — see `package.json`.
`````

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_readme 2>&1 | tail -4` then `python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK` both times.

- [ ] **Step 5: Verify every command in the README that the machine can run**, in a throw-away HOME: `H=$(mktemp -d); HOME=$H ./install.sh --help | head -3; HOME=$H ./install.sh; HOME=$H ./install.sh status; HOME=$H ./install.sh update --no-pull; HOME=$H ./install.sh uninstall; rm -rf $H` and `tools/check-ref.sh skills/marklogic-support/references/sar-analysis.md`.
Expected: each runs as described (status all `ok`; uninstall removes only links).

- [ ] **Step 6: Commit**

```bash
git add README.md tests/test_readme.py
git commit -m "docs: README covers install, update and use for pi, Claude Code, Codex and GitHub Copilot

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review (done)

- **Spec coverage:** README improved around installation and updating for the four agents → Task 4 (per-agent table, quick start, Windows, manual, update, troubleshooting) with facts from official docs and links; install/update tooling → Task 2; command portability (Codex deprecation, Copilot has no commands, Claude `$1` semantics, pi `/skill:`) → Task 3; the bash-only `/ticket` step → Task 1 + Task 3; stale-copy problem (your `~/.claude/commands` copies) → `--clean-legacy` + README; Windows → `install.ps1` (flagged untested).
- **Placeholders:** none; scripts, tests, skill text and README are given in full; edit steps give exact anchors.
- **Name consistency:** skill names, option names, message prefixes, `ticket_init.py` flags and the README's cross-checks (scripts, references, skills) are identical across tasks and tests.
- **Open items for the user:** (1) the repository URL placeholder; (2) the Windows installer needs a run on a Windows machine; (3) in pi the commands become `/skill:ticket`, `/skill:kcs`, `/skill:kcs-review`; (4) Copilot has no slash command for skills.

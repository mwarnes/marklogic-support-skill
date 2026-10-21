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

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

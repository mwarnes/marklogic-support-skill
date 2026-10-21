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

import re, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/marklogic-support"
REF = SKILL / "references/security-vulnerability-handling.md"
NAME = "security-vulnerability-handling.md"


class SecurityDocsTest(unittest.TestCase):
    def test_reference_exists_with_expected_sections(self):
        text = REF.read_text()
        heads = re.findall(r"^## (.+?)\s*$", text, re.M)
        for h in ("Detect", "Incident gate", "Vulnerability banner and checklist", "Wording rule",
                  "Audit trail on security tickets", "KCS articles"):
            self.assertIn(h, heads)

    def test_everything_points_at_the_reference(self):
        for p in (SKILL / "SKILL.md", SKILL / "references/ticket-auditing.md",
                  ROOT / "prompts/ticket.md", ROOT / "prompts/kcs.md"):
            self.assertIn(NAME, p.read_text(), p.name)

    def test_skill_routes_security_before_anything_else(self):
        text = (SKILL / "SKILL.md").read_text()
        always = text.split("## Triage mode")[0]
        self.assertIn(NAME, always)
        self.assertIn("incident gate", always.lower())

    def test_contact_wording_and_no_case_tag_advice(self):
        text = REF.read_text()
        self.assertIn("the MarkLogic product security team, or the Progress Security team if there is none", text)
        self.assertNotIn("Vulnerability component", text)


if __name__ == "__main__":
    unittest.main()

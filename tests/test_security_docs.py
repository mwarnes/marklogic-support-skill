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
                  ROOT / "skills/ticket/SKILL.md", ROOT / "skills/kcs/SKILL.md"):
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

    def test_kcs_docs_carry_the_security_rules(self):
        w = (SKILL / "references/kcs-writing.md").read_text()
        self.assertIn("Internal App", w)
        self.assertIn("Area of Interest to `Security`", w)
        self.assertIn('"breach"', w)
        self.assertIn("always `Security`", w)
        k = (ROOT / "skills/kcs/SKILL.md").read_text()
        self.assertIn("incident gate", k)
        self.assertIn("Area of Interest", k)
        r = (ROOT / "skills/kcs-review/SKILL.md").read_text()
        self.assertIn("breach", r)
        self.assertIn("Security", r)

    def test_incident_terms_consistent_everywhere(self):
        ref = REF.read_text()
        detect = ref.split("## Detect")[1].split("## Incident gate")[0].lower().replace("\n", " ")
        text = (SKILL / "SKILL.md").read_text().lower()
        always = text.split("## triage mode")[0].replace("\n", " ")
        row = [l for l in text.splitlines() if l.startswith("| cve")][0]
        for t in ("security incident", "security event", "malware", "virus", "ransomware",
                  "compromise", "intrusion"):
            self.assertIn(t, detect, t)
            self.assertIn(t, always, t)
            self.assertIn(t, row, t)

    def test_gate_wording_and_persistence_documented(self):
        for p in (SKILL / "SKILL.md", REF, ROOT / "skills/kcs/SKILL.md"):
            self.assertIn("Security incident gate raised", p.read_text(), p.name)
        for p in (SKILL / "SKILL.md", REF):
            self.assertIn("Security incident gate cleared", p.read_text(), p.name)
        text = (SKILL / "SKILL.md").read_text()
        for mode in ("## Dump mode", "## Log mode"):
            sec = text.split(mode)[1].split("\n## ")[0]
            self.assertIn("incident gate", sec, mode)

    def test_ticket_auditing_and_audit_paragraph(self):
        self.assertIn("## Security tickets", (SKILL / "references/ticket-auditing.md").read_text())
        self.assertIn("security vulnerability or incident ticket", (SKILL / "SKILL.md").read_text())

    def test_kcs_review_security_terms(self):
        r = (ROOT / "skills/kcs-review/SKILL.md").read_text()
        for t in ("INTERNAL", "Area of Interest", "breach"):
            self.assertIn(t, r)

    def test_ticket_prompt_security_check_applies_in_either_case(self):
        t = (ROOT / "skills/ticket/SKILL.md").read_text()
        self.assertGreater(t.index("In either case"), t.index("If it does not"))


if __name__ == "__main__":
    unittest.main()

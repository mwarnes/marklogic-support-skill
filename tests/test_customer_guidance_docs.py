"""Customer diagnostics guide and scope-of-support reference: content, caps, wiring, no verbatim article text."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/marklogic-support"
GUIDE = SKILL / "references/customer-diagnostics-guide.md"
SCOPE = SKILL / "references/support-scope.md"
SKILL_MD = (SKILL / "SKILL.md").read_text()
README = (ROOT / "README.md").read_text()
ARTICLE = "https://community.progress.com/s/article/How-to-Prepare-and-Share-Diagnostic-Information-for-Progress-MarkLogic-Support-Cases"


class GuideTest(unittest.TestCase):
    def setUp(self):
        self.t = GUIDE.read_text()

    def test_exists_within_cap(self):
        self.assertLessEqual(len(self.t.splitlines()), 110)

    def test_required_content(self):
        for w in (ARTICLE, "000299228", "reference only", "verbatim", "hosts/<hostname>/", "performance/meters/",
                  "repro/", "cloud/", "Secure Storage", "MoveIt", "| Problem | Part of the article to extract | Paraphrase |",
                  "# Customer diagnostics guide (reference only)", "## Rules for using it",
                  "## What to extract for which problem", "## Where our own requests fit (optional hints)", "## Sources"):
            self.assertIn(w, self.t, w)
        self.assertTrue("not mandatory" in self.t or "never mandatory" in self.t)

    def test_is_paraphrased_not_copied(self):
        for s in ("Perform a quick check (extract) before sharing.",
                  "Files from different environments (for example, Prod, QA, and Stage) should not be mixed."):
            self.assertNotIn(s, self.t)

    def test_no_breach_word(self):
        self.assertNotIn("breach", self.t.lower())


class ScopeTest(unittest.TestCase):
    def setUp(self):
        self.t = SCOPE.read_text()

    def test_exists_within_cap(self):
        self.assertLessEqual(len(self.t.splitlines()), 110)

    def test_required_content(self):
        for w in ("https://community.progress.com/s/products/marklogic/scope-of-support",
                  "https://community.progress.com/s/products/marklogic/support-guide", ARTICLE,
                  "Severity", "Priority", "Business Impact", "Scope flag", "Criteria", "SLA & Severity Definitions", "### Severity levels", "12 business hours", "14 calendar days", "21 calendar days", "30 days", "security incident gate",
                  "### Criteria (what is not covered)", "### Covered (no flag)", "In-depth performance tuning", "dedicated support engineer", "far beyond",
                  "# Scope of support and severity (reference only)", "## Rules for using it", "## Links",
                  "## Severity, priority and business impact", "## Scope check", "## Sources"):
            self.assertIn(w, self.t, w)

    def test_no_breach_word(self):
        self.assertNotIn("breach", self.t.lower())


class WiringTest(unittest.TestCase):
    def test_skill_md(self):
        for w in ("When asking a customer to send diagnostic or system data, you may point to the customer diagnostics guide "
                  "(`references/customer-diagnostics-guide.md`) — reference only, never mandatory",
                  "Scope awareness", "references/support-scope.md", "Scope flag",
                  "how to upload, attachments, file structure, secure storage, support dump upload, organise files, zip"):
            self.assertIn(w, SKILL_MD, w)
        always = SKILL_MD.split("## Triage mode")[0]
        self.assertIn("4. **Scope awareness", always)
        row = [l for l in SKILL_MD.splitlines() if l.startswith("|") and "references/customer-diagnostics-guide.md" in l]
        self.assertTrue(row)
        triage = SKILL_MD.split("## Triage mode")[1].split("## Q&A mode")[0]
        self.assertIn("severity, priority or business impact", triage)

    def test_readme_and_requests(self):
        for w in ("customer-diagnostics-guide", "support-scope"):
            self.assertIn(w, README)
        self.assertIn("customer-diagnostics-guide.md", (SKILL / "references/performance-data-requests.md").read_text())


if __name__ == "__main__":
    unittest.main()

import subprocess, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/marklogic-support"
sys.path.insert(0, str(SKILL / "scripts"))
import analyse_sar

SAR = SKILL / "references/sar-analysis.md"


class SarReferenceTest(unittest.TestCase):
    def test_reference_has_the_fixed_shape(self):
        r = subprocess.run(["bash", str(ROOT / "tools/check-ref.sh"), str(SAR)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_every_rule_and_threshold_is_documented(self):
        text = SAR.read_text()
        section = text.split("## Findings produced by analyse_sar.py")[1].split("\n## ")[0]
        for rule in analyse_sar.RULES:
            self.assertIn(rule.name, section, rule.name)
            self.assertIn(f"{rule.threshold:g}", section, rule.name)

    def test_gregg_use_checklist_and_sysstat_docs_are_cited(self):
        text = SAR.read_text()
        self.assertIn("https://brendangregg.com/USEmethod/use-linux.html", text)
        self.assertIn("sar.1", text)

    def test_sources_md_has_the_section(self):
        self.assertIn("## sar-analysis.md", (SKILL / "references/sources.md").read_text())


if __name__ == "__main__":
    unittest.main()

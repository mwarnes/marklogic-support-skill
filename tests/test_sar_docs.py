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


class RequestTemplateTest(unittest.TestCase):
    REQ = SKILL / "references/performance-data-requests.md"

    def test_sections_and_key_commands(self):
        text = self.REQ.read_text()
        for h in ("SAR export", "If SAR is not running", "Host metrics (iostat, vmstat, mpstat, pidstat)",
                  "Kernel and OOM messages", "Stack samples: pstack movie", "CPU profile: perf", "Memory growth: pmap", "Cloud-hosted customers"):
            self.assertIn("## " + h, text)
        self.assertIn("LC_ALL=C S_TIME_FORMAT=ISO sar -A -f", text)
        self.assertIn("iostat -xz", text)
        self.assertIn("mpstat -P ALL", text)
        self.assertIn("pidstat", text)

    def test_cloud_signals_only_in_the_cloud_section(self):
        text = self.REQ.read_text()
        cloud = text.split("## Cloud-hosted customers")[1]
        before = text.split("## Cloud-hosted customers")[0]
        self.assertIn("steal", cloud.lower())
        self.assertIn("EBS", cloud)
        self.assertNotIn("EBS", before)
        self.assertIn("on-prem", before.lower())

    def test_requests_are_security_gated_and_neutral(self):
        text = self.REQ.read_text()
        self.assertIn("incident gate", text)
        self.assertNotIn("breach", text.lower())


class WiringTest(unittest.TestCase):
    SKILL_MD = (SKILL / "SKILL.md").read_text()

    def test_skill_has_a_sar_mode_and_routing(self):
        t = self.SKILL_MD
        self.assertIn("## SAR mode", t)
        for needle in ("analyse_sar.py", "references/sar-analysis.md", "references/performance-data-requests.md"):
            self.assertIn(needle, t, needle)
        row = [l for l in t.splitlines() if l.startswith("|") and "sar-analysis.md" in l]
        self.assertTrue(row)
        for kw in ("sar", "iostat", "vmstat", "mpstat", "pidstat", "%iowait", "%steal"):
            self.assertIn(kw, row[0], kw)

    def test_sar_mode_checks_the_security_gate_and_is_classified(self):
        t = self.SKILL_MD
        mode = t.split("## SAR mode")[1].split("\n## ")[0]
        self.assertIn("incident gate", mode)
        always = t.split("## Triage mode")[0]
        self.assertIn("SAR mode", always)

    def test_triage_asks_for_host_data_on_performance_tickets(self):
        triage = self.SKILL_MD.split("## Triage mode")[1].split("## Q&A mode")[0]
        self.assertIn("performance-data-requests.md", triage)

    def test_tuning_and_memory_references_point_to_sar(self):
        for name in ("performance-tuning.md", "memory-and-os.md"):
            self.assertIn("sar-analysis.md", (SKILL / "references" / name).read_text(), name)

    def test_check_ref_still_passes_for_edited_references(self):
        for name in ("performance-tuning.md", "memory-and-os.md"):
            r = subprocess.run(["bash", str(ROOT / "tools/check-ref.sh"), str(SKILL / "references" / name)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()

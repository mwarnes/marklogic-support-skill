# SAR and Host-Performance Data Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the MarkLogic support skill analyse Linux SAR (sysstat) data from customers, request SAR and related host-level data on performance tickets, and point to well-known expert SAR documentation.

**Architecture:** A stdlib-only parser (`scripts/analyse_sar.py`, same style as `parse_dump.py` / `analyse_logs.py`) turns `sar -A` text into a ranked saturation summary; two new reference files hold the interpretation (`sar-analysis.md`, the fixed domain shape) and the customer-request templates (`performance-data-requests.md`); `SKILL.md` gains a SAR mode, a routing row and a triage rule.

**Tech Stack:** Python 3 stdlib (`unittest`), Markdown references, pandoc not needed. Tests: `python3 -m unittest discover -s tests` (pytest is not installed).

## Global Constraints

Decisions agreed with the user:

- **Scope:** reference + customer-request template + parser script. Extra data sources to cover: `iostat` / `vmstat` / `mpstat` / `pidstat`, OOM and kernel messages (`dmesg`, `/var/log/messages`), thread dumps (`pstack`/`gdb`) and `pmap`, and **cloud signals** (CPU steal, EBS burst/IOPS throttling) — the cloud signals are requested **only on cloud-hosted (for example AWS) performance tickets**, never on-prem. iostat/vmstat/mpstat/pidstat, kernel/OOM messages and thread dumps/pmap are very commonly requested on-prem.
- **Documentation sources to wire in** (fetch and read them before citing; a claim that is not supported by a fetched page is marked `[unverified — confirm]`): Brendan Gregg's USE Method Linux checklist (https://brendangregg.com/USEmethod/use-linux.html); the sysstat man pages `sar(1)` and `sadf(1)` (for example https://man7.org/linux/man-pages/man1/sar.1.html) and the sysstat README (https://sources.debian.org/src/sysstat/12.7.5-2/README.md); Red Hat's SAR article (https://access.redhat.com/solutions/276533 — may need a login; use it only if it can be fetched); thomas-krenn's SAR wiki (https://www.thomas-krenn.com/en/wiki/Collect_and_report_Linux_System_Activity_Information_with_sar); MarkLogic KB "mlstat" (https://help.marklogic.com/Knowledgebase/Article/View/138/0).
- **Reference rules (README "Verifying / maintaining"):** `sar-analysis.md` has the fixed shape (`## Concepts`, `## Standard procedures`, `## Common mistakes & symptoms` with the exact table header `| Mistake | Symptom seen by customer | How to confirm | Fix / best practice | Source |`, `## Sources`), at most 250 lines, every table row cites a URL or `[unverified — confirm]`; validate with `tools/check-ref.sh`.
- **Script rules:** Python 3 stdlib only; never print or dump whole input files; input is `sar -A` text (a binary `sa##` file is converted with the local `sar -A -f` under `LC_ALL=C S_TIME_FORMAT=ISO` only when sysstat is installed, otherwise the script tells the engineer to ask the customer for text output). A finding needs `--min-samples` (default 2) consecutive samples over the threshold.
- **Customer-supplied files:** SAR output from a customer is a customer-supplied file, so the **security incident gate** (see `security-vulnerability-handling.md`) applies before it is analysed or requested.
- **Request wording:** customer-facing request text is numbered, self-contained, states why each item is needed, and is Salesforce-paste-ready (same style as `Required-Diagnostics.md` in `ticket-auditing.md`); it never contains the word "breach".
- Existing behaviour and tests keep working. `KCS_SolutionContentStandard.txt`, `SECURITY_HANDLING.txt` and `kcs-drafts/` are untracked: never `git add` them.

---

## File Structure

- Create `skills/marklogic-support/scripts/analyse_sar.py` — parser, rules, report writer.
- Create `tests/test_analyse_sar.py`, `tests/fixture_sar/sar-d1.txt`, `tests/fixture_sar/sar-d2-iso.txt`.
- Create `skills/marklogic-support/references/sar-analysis.md` — interpretation, thresholds, MarkLogic meaning, sources.
- Create `skills/marklogic-support/references/performance-data-requests.md` — what to ask the customer for, per scenario.
- Modify `skills/marklogic-support/references/sources.md`, `performance-tuning.md`, `memory-and-os.md` — links and pointers.
- Modify `skills/marklogic-support/SKILL.md` — SAR mode, routing row, triage rule, audit-trail and security-gate mentions.
- Create `tests/test_sar_docs.py` — drift guard.

---

### Task 1: `analyse_sar.py`, fixtures and tests

**Files:**
- Create: `tests/fixture_sar/sar-d1.txt`, `tests/fixture_sar/sar-d2-iso.txt`
- Create: `tests/test_analyse_sar.py`
- Create: `skills/marklogic-support/scripts/analyse_sar.py`

**Interfaces:**
- Produces (used by Tasks 2–4): CLI `analyse_sar.py PATH... [--out DIR] [--min-samples N]` writing `SUMMARY.md`, `findings.json`, `series-<host>.csv`; module names `RULES` (list of `Rule(name, severity, op, threshold, unit, value, meaning)`), `parse(text, fallback_host, notes) -> (rows, restarts)`, `find(rows, min_samples) -> list[dict]`. Rule names (documented in Task 2): `cpu_iowait`, `disk_await`, `disk_util`, `swap_io`, `mem_available`, `direct_reclaim`, `cpu_busy`, `run_queue`, `cpu_steal`, `major_faults`, `net_errors`. Thresholds: iowait > 20 %, await > 50 ms, %util > 80, swap > 1 page/s, available memory < 10 %, pgscand/s > 1, user+system > 90 %, run queue > 2 × CPUs, steal > 5 %, majflt/s > 100, any NIC error/drop/s > 0.

- [ ] **Step 1: Create the fixtures** — write these two files exactly (header lines contain TAB characters between fields; keep them):

`tests/fixture_sar/sar-d1.txt` (12-hour clock, incident host, ends with a `LINUX RESTART` marker):

```text
Linux 4.18.0-477.el8.x86_64 (ml-d1.example.com)	10/20/2026	_x86_64_	(8 CPU)

12:00:01 AM     CPU     %user     %nice   %system   %iowait    %steal     %idle
12:00:01 AM     all     12.00      0.00      3.00      0.40      0.00     84.60
12:10:01 AM     all     12.00      0.00      3.00      0.40      0.00     84.60
12:20:01 AM     all     12.00      0.00      3.00      0.40      0.00     84.60
12:30:01 AM     all     12.00      0.00      3.00     35.00      0.00     50.00
12:40:01 AM     all     12.00      0.00      3.00     35.00      0.00     50.00
12:50:01 AM     all     12.00      0.00      3.00     35.00      0.00     50.00
01:00:01 AM     all     12.00      0.00      3.00      0.40      0.00     84.60
01:10:01 AM     all     12.00      0.00      3.00      0.40      0.00     84.60
Average:        all     12.00      0.00      3.00      9.00      0.00     76.00

12:00:01 AM   runq-sz  plist-sz   ldavg-1   ldavg-5  ldavg-15   blocked
12:00:01 AM         2       812      1.50      1.20      1.00         0
12:10:01 AM         2       812      1.50      1.20      1.00         0
12:20:01 AM         2       812      1.50      1.20      1.00         0
12:30:01 AM        40       812      1.50      1.20      1.00         0
12:40:01 AM        40       812      1.50      1.20      1.00         0
12:50:01 AM        40       812      1.50      1.20      1.00         0
01:00:01 AM         2       812      1.50      1.20      1.00         0
01:10:01 AM         2       812      1.50      1.20      1.00         0
Average:           10       812      1.50      1.20      1.00         0

12:00:01 AM  pswpin/s pswpout/s
12:00:01 AM      0.00      0.00
12:10:01 AM      0.00      0.00
12:20:01 AM      0.00      0.00
12:30:01 AM      0.00      0.00
12:40:01 AM    120.00    120.00
12:50:01 AM    120.00    120.00
01:00:01 AM      0.00      0.00
01:10:01 AM      0.00      0.00
Average:        30.00     30.00

12:00:01 AM kbmemfree   kbavail kbmemused  %memused kbbuffers  kbcached  kbcommit   %commit  kbactive   kbinact   kbdirty
12:00:01 AM   9000000  24000000  23000000     71.88    120000  22000000  30000000     93.00  15000000   9000000      2000
12:10:01 AM   9000000  24000000  23000000     71.88    120000  22000000  30000000     93.00  15000000   9000000      2000
12:20:01 AM   9000000  24000000  23000000     71.88    120000  22000000  30000000     93.00  15000000   9000000      2000
12:30:01 AM   9000000  24000000  23000000     71.88    120000  22000000  30000000     93.00  15000000   9000000      2000
12:40:01 AM    300000    400000  31700000     99.06    120000  22000000  30000000     93.00  15000000   9000000      2000
12:50:01 AM    300000    400000  31700000     99.06    120000  22000000  30000000     93.00  15000000   9000000      2000
01:00:01 AM    300000    400000  31700000     99.06    120000  22000000  30000000     93.00  15000000   9000000      2000
01:10:01 AM    300000    400000  31700000     99.06    120000  22000000  30000000     93.00  15000000   9000000      2000
Average:     5000000  12000000  27000000     84.00    120000  22000000  30000000     93.00  15000000   9000000      2000

12:00:01 AM  pgpgin/s pgpgout/s   fault/s  majflt/s  pgfree/s pgscank/s pgscand/s pgsteal/s    %vmeff
12:00:01 AM    100.00    200.00   1500.00      2.00   9000.00      0.00      0.00      0.00      0.00
12:10:01 AM    100.00    200.00   1500.00      2.00   9000.00      0.00      0.00      0.00      0.00
12:20:01 AM    100.00    200.00   1500.00      2.00   9000.00      0.00      0.00      0.00      0.00
12:30:01 AM    100.00    200.00   1500.00      2.00   9000.00      0.00      0.00      0.00      0.00
12:40:01 AM    100.00    200.00   1500.00      2.00   9000.00      0.00    800.00      0.00      0.00
12:50:01 AM    100.00    200.00   1500.00      2.00   9000.00      0.00    800.00      0.00      0.00
01:00:01 AM    100.00    200.00   1500.00      2.00   9000.00      0.00      0.00      0.00      0.00
01:10:01 AM    100.00    200.00   1500.00      2.00   9000.00      0.00      0.00      0.00      0.00
Average:      100.00    200.00   1500.00      2.00   9000.00      0.00    200.00      0.00      0.00

12:00:01 AM       DEV       tps     rkB/s     wkB/s     dkB/s   areq-sz    aqu-sz     await     %util
12:00:01 AM       sda    150.00   9000.00   4000.00      0.00     86.00      3.00      2.00     15.00
12:00:01 AM       sdb      5.00     20.00     10.00      0.00      6.00      0.01      1.00      0.50
12:10:01 AM       sda    150.00   9000.00   4000.00      0.00     86.00      3.00      2.00     15.00
12:10:01 AM       sdb      5.00     20.00     10.00      0.00      6.00      0.01      1.00      0.50
12:20:01 AM       sda    150.00   9000.00   4000.00      0.00     86.00      3.00      2.00     15.00
12:20:01 AM       sdb      5.00     20.00     10.00      0.00      6.00      0.01      1.00      0.50
12:30:01 AM       sda    150.00   9000.00   4000.00      0.00     86.00      3.00    180.00     97.00
12:30:01 AM       sdb      5.00     20.00     10.00      0.00      6.00      0.01      1.00      0.50
12:40:01 AM       sda    150.00   9000.00   4000.00      0.00     86.00      3.00    180.00     97.00
12:40:01 AM       sdb      5.00     20.00     10.00      0.00      6.00      0.01      1.00      0.50
12:50:01 AM       sda    150.00   9000.00   4000.00      0.00     86.00      3.00    180.00     97.00
12:50:01 AM       sdb      5.00     20.00     10.00      0.00      6.00      0.01      1.00      0.50
01:00:01 AM       sda    150.00   9000.00   4000.00      0.00     86.00      3.00      2.00     15.00
01:00:01 AM       sdb      5.00     20.00     10.00      0.00      6.00      0.01      1.00      0.50
01:10:01 AM       sda    150.00   9000.00   4000.00      0.00     86.00      3.00      2.00     15.00
01:10:01 AM       sdb      5.00     20.00     10.00      0.00      6.00      0.01      1.00      0.50
Average:       sda    150.00   9000.00   4000.00      0.00     86.00      3.00     40.00     35.00

12:00:01 AM     IFACE   rxerr/s   txerr/s    coll/s  rxdrop/s  txdrop/s  txcarr/s  rxfram/s  rxfifo/s  txfifo/s
12:00:01 AM      eth0      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00
12:10:01 AM      eth0      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00
12:20:01 AM      eth0      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00
12:30:01 AM      eth0      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00
12:40:01 AM      eth0      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00
12:50:01 AM      eth0      3.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00
01:00:01 AM      eth0      3.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00
01:10:01 AM      eth0      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00
Average:      eth0      1.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00

01:20:01 AM       LINUX RESTART      (8 CPU)

```

`tests/fixture_sar/sar-d2-iso.txt` (24-hour clock, ISO date, as produced with `S_TIME_FORMAT=ISO`; a quiet host):

```text
Linux 4.18.0-477.el8.x86_64 (ml-d2.example.com)	2026-10-20	_x86_64_	(8 CPU)

00:00:01     CPU     %user     %nice   %system   %iowait    %steal     %idle
00:00:01     all     12.00      0.00      3.00      0.40      0.00     84.60
00:10:01     all     12.00      0.00      3.00      0.40      0.00     84.60
00:20:01     all     12.00      0.00      3.00      0.40      0.00     84.60
00:30:01     all     12.00      0.00      3.00      0.40      0.00     84.60
00:40:01     all     12.00      0.00      3.00      0.40      0.00     84.60
00:50:01     all     12.00      0.00      3.00      0.40      0.00     84.60
01:00:01     all     12.00      0.00      3.00      0.40      0.00     84.60
01:10:01     all     12.00      0.00      3.00      0.40      0.00     84.60
Average:        all     12.00      0.00      3.00      9.00      0.00     76.00

00:00:01   runq-sz  plist-sz   ldavg-1   ldavg-5  ldavg-15   blocked
00:00:01         2       812      1.50      1.20      1.00         0
00:10:01         2       812      1.50      1.20      1.00         0
00:20:01         2       812      1.50      1.20      1.00         0
00:30:01         2       812      1.50      1.20      1.00         0
00:40:01         2       812      1.50      1.20      1.00         0
00:50:01         2       812      1.50      1.20      1.00         0
01:00:01         2       812      1.50      1.20      1.00         0
01:10:01         2       812      1.50      1.20      1.00         0
Average:           10       812      1.50      1.20      1.00         0

00:00:01  pswpin/s pswpout/s
00:00:01      0.00      0.00
00:10:01      0.00      0.00
00:20:01      0.00      0.00
00:30:01      0.00      0.00
00:40:01      0.00      0.00
00:50:01      0.00      0.00
01:00:01      0.00      0.00
01:10:01      0.00      0.00
Average:        30.00     30.00

00:00:01 kbmemfree   kbavail kbmemused  %memused kbbuffers  kbcached  kbcommit   %commit  kbactive   kbinact   kbdirty
00:00:01   9000000  24000000  23000000     71.88    120000  22000000  30000000     93.00  15000000   9000000      2000
00:10:01   9000000  24000000  23000000     71.88    120000  22000000  30000000     93.00  15000000   9000000      2000
00:20:01   9000000  24000000  23000000     71.88    120000  22000000  30000000     93.00  15000000   9000000      2000
00:30:01   9000000  24000000  23000000     71.88    120000  22000000  30000000     93.00  15000000   9000000      2000
00:40:01   9000000  24000000  23000000     71.88    120000  22000000  30000000     93.00  15000000   9000000      2000
00:50:01   9000000  24000000  23000000     71.88    120000  22000000  30000000     93.00  15000000   9000000      2000
01:00:01   9000000  24000000  23000000     71.88    120000  22000000  30000000     93.00  15000000   9000000      2000
01:10:01   9000000  24000000  23000000     71.88    120000  22000000  30000000     93.00  15000000   9000000      2000
Average:     5000000  12000000  27000000     84.00    120000  22000000  30000000     93.00  15000000   9000000      2000

00:00:01  pgpgin/s pgpgout/s   fault/s  majflt/s  pgfree/s pgscank/s pgscand/s pgsteal/s    %vmeff
00:00:01    100.00    200.00   1500.00      2.00   9000.00      0.00      0.00      0.00      0.00
00:10:01    100.00    200.00   1500.00      2.00   9000.00      0.00      0.00      0.00      0.00
00:20:01    100.00    200.00   1500.00      2.00   9000.00      0.00      0.00      0.00      0.00
00:30:01    100.00    200.00   1500.00      2.00   9000.00      0.00      0.00      0.00      0.00
00:40:01    100.00    200.00   1500.00      2.00   9000.00      0.00      0.00      0.00      0.00
00:50:01    100.00    200.00   1500.00      2.00   9000.00      0.00      0.00      0.00      0.00
01:00:01    100.00    200.00   1500.00      2.00   9000.00      0.00      0.00      0.00      0.00
01:10:01    100.00    200.00   1500.00      2.00   9000.00      0.00      0.00      0.00      0.00
Average:      100.00    200.00   1500.00      2.00   9000.00      0.00    200.00      0.00      0.00

00:00:01       DEV       tps     rkB/s     wkB/s     dkB/s   areq-sz    aqu-sz     await     %util
00:00:01       sda    150.00   9000.00   4000.00      0.00     86.00      3.00      2.00     15.00
00:00:01       sdb      5.00     20.00     10.00      0.00      6.00      0.01      1.00      0.50
00:10:01       sda    150.00   9000.00   4000.00      0.00     86.00      3.00      2.00     15.00
00:10:01       sdb      5.00     20.00     10.00      0.00      6.00      0.01      1.00      0.50
00:20:01       sda    150.00   9000.00   4000.00      0.00     86.00      3.00      2.00     15.00
00:20:01       sdb      5.00     20.00     10.00      0.00      6.00      0.01      1.00      0.50
00:30:01       sda    150.00   9000.00   4000.00      0.00     86.00      3.00      2.00     15.00
00:30:01       sdb      5.00     20.00     10.00      0.00      6.00      0.01      1.00      0.50
00:40:01       sda    150.00   9000.00   4000.00      0.00     86.00      3.00      2.00     15.00
00:40:01       sdb      5.00     20.00     10.00      0.00      6.00      0.01      1.00      0.50
00:50:01       sda    150.00   9000.00   4000.00      0.00     86.00      3.00      2.00     15.00
00:50:01       sdb      5.00     20.00     10.00      0.00      6.00      0.01      1.00      0.50
01:00:01       sda    150.00   9000.00   4000.00      0.00     86.00      3.00      2.00     15.00
01:00:01       sdb      5.00     20.00     10.00      0.00      6.00      0.01      1.00      0.50
01:10:01       sda    150.00   9000.00   4000.00      0.00     86.00      3.00      2.00     15.00
01:10:01       sdb      5.00     20.00     10.00      0.00      6.00      0.01      1.00      0.50
Average:       sda    150.00   9000.00   4000.00      0.00     86.00      3.00     40.00     35.00

00:00:01     IFACE   rxerr/s   txerr/s    coll/s  rxdrop/s  txdrop/s  txcarr/s  rxfram/s  rxfifo/s  txfifo/s
00:00:01      eth0      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00
00:10:01      eth0      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00
00:20:01      eth0      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00
00:30:01      eth0      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00
00:40:01      eth0      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00
00:50:01      eth0      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00
01:00:01      eth0      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00
01:10:01      eth0      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00
Average:      eth0      1.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00      0.00

```

- [ ] **Step 2: Write the failing tests** — create `tests/test_analyse_sar.py` with exactly:

```python
import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/marklogic-support/scripts/analyse_sar.py"
FIX = Path(__file__).with_name("fixture_sar")
sys.path.insert(0, str(SCRIPT.parent))
import analyse_sar


def run(*args, env=None):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=env)


class AnalyseSarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp()) / "out"
        r = run(FIX, "--out", cls.out)
        assert r.returncode == 0, r.stderr
        cls.stdout = r.stdout
        cls.findings = json.loads((cls.out / "findings.json").read_text())

    def test_both_time_formats_parse_into_two_hosts(self):
        s = (self.out / "SUMMARY.md").read_text()
        self.assertIn("| ml-d1.example.com | 8 | 2026-10-20 00:00:01 | 2026-10-20 01:10:01 | 8 | 10 min |", s)
        self.assertIn("| ml-d2.example.com | 8 |", s)          # ISO date, 24-hour times
        self.assertIn("2026-10-20 01:20:01", s)                 # LINUX RESTART marker
        self.assertIn("2 hosts", self.stdout)

    def test_incident_host_findings(self):
        self.assertEqual({f["rule"] for f in self.findings},
                         {"cpu_iowait", "disk_await", "disk_util", "swap_io", "mem_available",
                          "direct_reclaim", "run_queue", "net_errors"})
        self.assertTrue(all(f["host"] == "ml-d1.example.com" for f in self.findings))
        disk = [f for f in self.findings if f["rule"] == "disk_await"][0]
        self.assertEqual((disk["key"], disk["samples"], disk["peak"]), ("sda", 3, 180.0))
        self.assertEqual(disk["start"], "2026-10-20 00:30:01")
        self.assertEqual(disk["end"], "2026-10-20 00:50:01")

    def test_quiet_device_and_clean_host_not_flagged(self):
        self.assertFalse([f for f in self.findings if f["key"] == "sdb"])
        self.assertFalse([f for f in self.findings if f["host"] == "ml-d2.example.com"])

    def test_likely_causes_ranked_before_checks(self):
        sev = [f["severity"] for f in self.findings]
        self.assertEqual(sev, sorted(sev))
        self.assertEqual(sev[0], 0)
        self.assertEqual(sev[-1], 1)

    def test_summary_table_and_limits_section(self):
        s = (self.out / "SUMMARY.md").read_text()
        self.assertIn("cpu_iowait (likely cause)", s)
        self.assertIn("run_queue (check)", s)
        self.assertIn("## What SAR cannot show", s)

    def test_series_csv_for_graphing(self):
        with (self.out / "series-ml-d1.example.com.csv").open() as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 8)
        peak = max(rows, key=lambda r: float(r["iowait"]))
        self.assertEqual((peak["time"], float(peak["iowait"]), float(peak["disk_await_max"])),
                         ("2026-10-20 00:30:01", 35.0, 180.0))

    def test_min_samples_filters_short_runs(self):
        out = Path(tempfile.mkdtemp())
        self.assertEqual(run(FIX, "--out", out, "--min-samples", 4).returncode, 0)
        rules = {f["rule"] for f in json.loads((out / "findings.json").read_text())}
        self.assertEqual(rules, {"mem_available"})              # the only 4-sample run


class ParseTest(unittest.TestCase):
    def test_aliases_midnight_rollover_and_sections_restart_at_first_sample(self):
        text = ("Linux 5.14.0 (h1)\t2026-10-20\t_x86_64_\t(4 CPU)\n\n"
                "23:50:01     CPU      %usr     %nice      %sys   %iowait    %steal      %irq     %soft    %guest    %gnice     %idle\n"
                "23:50:01     all     50.00      0.00     45.00      0.00      0.00      0.00      0.00      0.00      0.00      5.00\n"
                "00:00:01     all     50.00      0.00     45.00      0.00      0.00      0.00      0.00      0.00      0.00      5.00\n"
                "\n"
                "23:50:01  pswpin/s pswpout/s\n23:50:01      0.00      0.00\n00:00:01      0.00      0.00\n")
        rows, restarts = analyse_sar.parse(text, "x", set())
        cpu = [r for r in rows if "%user" in r["m"]]
        self.assertEqual([str(r["ts"]) for r in cpu], ["2026-10-20 23:50:01", "2026-10-21 00:00:01"])
        self.assertEqual(cpu[0]["m"]["%system"], 45.0)           # %sys aliased to %system
        swap = [r for r in rows if "pswpin/s" in r["m"]]
        self.assertEqual(str(swap[0]["ts"]), "2026-10-20 23:50:01")   # second section restarts the clock
        self.assertEqual(restarts, [])
        findings = analyse_sar.find(rows, 2)
        self.assertEqual([f["rule"] for f in findings], ["cpu_busy"])

    def test_12_hour_midnight_and_noon(self):
        text = ("Linux 5.14.0 (h1)\t10/20/2026\t_x86_64_\t(4 CPU)\n\n"
                "11:50:01 PM  pswpin/s pswpout/s\n11:50:01 PM 0.00 0.00\n12:00:01 AM 0.00 0.00\n"
                "11:50:01 AM 0.00 0.00\n12:00:01 PM 0.00 0.00\n")
        rows, _ = analyse_sar.parse(text, "x", set())
        self.assertEqual([r["ts"].hour for r in rows], [23, 0, 11, 12])

    def test_ambiguous_date_is_noted(self):
        notes = set()
        analyse_sar.parse("Linux 5.14.0 (h1)\t10/11/2026\t_x86_64_\t(4 CPU)\n", "x", notes)
        self.assertTrue(any("ambiguous" in n for n in notes))
        notes = set()
        analyse_sar.parse("Linux 5.14.0 (h1)\t20/10/2026\t_x86_64_\t(4 CPU)\n", "x", notes)
        self.assertFalse(notes)


class InputErrorTest(unittest.TestCase):
    def test_binary_file_without_sar_asks_for_text_output(self):
        d = Path(tempfile.mkdtemp()); p = d / "sa20"; p.write_bytes(b"\x00\x01\x02binary")
        r = run(p, "--out", d / "o", env={"PATH": tempfile.mkdtemp()})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("sar -A", r.stderr)
        self.assertIn("S_TIME_FORMAT=ISO", r.stderr)

    def test_no_sar_data_is_an_error(self):
        d = Path(tempfile.mkdtemp()); (d / "notes.txt").write_text("just some text\n")
        r = run(d, "--out", d / "o")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no SAR data", r.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run to verify they fail**

Run: `python3 -m unittest tests.test_analyse_sar 2>&1 | tail -6`
Expected: ERROR — the script does not exist (`No module named 'analyse_sar'`).

- [ ] **Step 4: Write the implementation** — create `skills/marklogic-support/scripts/analyse_sar.py` (executable bit not required) with exactly:

```python
#!/usr/bin/env python3
"""Analyse Linux SAR (sysstat) output into a saturation summary.

Usage: analyse_sar.py PATH... [--out DIR] [--min-samples N]
Inputs: `sar -A` / `sar -u -r -d ...` text output (files or directories, recursed); a binary sa## file is
        converted with the local `sar -A -f` when sysstat is installed (otherwise ask the customer for the
        text output: LC_ALL=C S_TIME_FORMAT=ISO sar -A -f /var/log/sa/saDD > saDD.txt).
Writes: SUMMARY.md findings.json series-<host>.csv
Thresholds are the RULES table below; a finding needs --min-samples (default 2) consecutive samples.
"""
import argparse, csv, json, os, re, shutil, statistics, subprocess, sys
from collections import defaultdict, namedtuple
from datetime import datetime, timedelta
from pathlib import Path

HEADER_RE = re.compile(r"^Linux (\S+) \(([^)]+)\)\s+(\S+)(?:\s+_\S+_)?(?:\s+\((\d+) CPU\))?")
TIME_RE = re.compile(r"^(\d{1,2}):(\d\d):(\d\d)(?: ([AP]M))?\s+(.*)$")
KEYED = {"CPU", "DEV", "IFACE", "FILESYS", "TTY", "INTR", "BUS", "FAN", "TEMP", "IN", "MHz", "DEVICE"}
ALIAS = {"%usr": "%user", "%sys": "%system"}
NET_ERR = ("rxerr/s", "txerr/s", "coll/s", "rxdrop/s", "txdrop/s", "txcarr/s", "rxfram/s", "rxfifo/s", "txfifo/s")

Rule = namedtuple("Rule", "name severity op threshold unit value meaning")


def _all_cpu(col):
    return lambda m, k, n: m.get(col) if k == "all" else None


def _cpu_busy(m, k, n):
    if k != "all" or "%user" not in m or "%system" not in m:
        return None
    return m["%user"] + m["%system"] + m.get("%nice", 0.0)


def _runq(m, k, n):
    return m["runq-sz"] / n if "runq-sz" in m and n else None


def _swap(m, k, n):
    return m["pswpin/s"] + m["pswpout/s"] if "pswpin/s" in m and "pswpout/s" in m else None


def _mem_avail(m, k, n):
    if all(c in m for c in ("kbavail", "kbmemfree", "kbmemused")):
        total = m["kbmemfree"] + m["kbmemused"]
        return 100.0 * m["kbavail"] / total if total else None
    return None


def _per_dev(col):
    return lambda m, k, n: m.get(col) if k and "%util" in m else None


def _net_err(m, k, n):
    if not k or "rxerr/s" not in m:
        return None
    return sum(m.get(c, 0.0) for c in NET_ERR)


# severity: 0 = likely cause of a MarkLogic slowdown, 1 = contributing / check
RULES = [
    Rule("cpu_iowait", 0, ">", 20.0, "% iowait", _all_cpu("%iowait"), "CPUs idle while waiting on disk I/O"),
    Rule("disk_await", 0, ">", 50.0, "ms await", _per_dev("await"), "disk requests queue and complete slowly"),
    Rule("disk_util", 0, ">", 80.0, "% util", _per_dev("%util"), "device close to saturation"),
    Rule("swap_io", 0, ">", 1.0, "pages/s", _swap, "memory pressure: pages moved to/from swap"),
    Rule("mem_available", 0, "<", 10.0, "% avail", _mem_avail, "little memory available to the OS"),
    Rule("direct_reclaim", 0, ">", 1.0, "pgscand/s", lambda m, k, n: m.get("pgscand/s"),
         "processes reclaiming memory directly (stalls)"),
    Rule("cpu_busy", 1, ">", 90.0, "% user+sys", _cpu_busy, "CPU saturated"),
    Rule("run_queue", 1, ">", 2.0, "x CPUs", _runq, "more runnable tasks than CPUs can serve"),
    Rule("cpu_steal", 1, ">", 5.0, "% steal", _all_cpu("%steal"), "hypervisor taking CPU (noisy neighbour / throttling)"),
    Rule("major_faults", 1, ">", 100.0, "majflt/s", lambda m, k, n: m.get("majflt/s"), "pages read from disk on demand"),
    Rule("net_errors", 1, ">", 0.0, "errors+drops/s", _net_err, "network interface errors or drops"),
]


def is_num(t):
    try:
        float(t)
        return True
    except ValueError:
        return False


def parse_date(s):
    """-> (date, ambiguous). ISO, MM/DD/YYYY, DD/MM/YYYY, with 2- or 4-digit years."""
    m = re.fullmatch(r"(\d{4})-(\d\d)-(\d\d)", s)
    if m:
        return datetime(int(m[1]), int(m[2]), int(m[3])), False
    m = re.fullmatch(r"(\d\d)/(\d\d)/(\d{2}|\d{4})", s)
    if not m:
        return None, False
    a, b, y = int(m[1]), int(m[2]), int(m[3])
    y += 2000 if y < 100 else 0
    if a > 12:
        return datetime(y, b, a), False
    return datetime(y, a, b), b <= 12 and a != b


def sniff(path):
    try:
        raw = path.read_bytes()[:4096]
    except OSError:
        return None
    if b"\0" in raw:
        return "binary"
    text = raw.decode("utf-8", "replace")
    return "text" if re.search(r"^Linux \S+ \(", text, re.M) and re.search(TIME_RE.pattern, text, re.M) else None


def binary_to_text(path):
    sar = shutil.which("sar")
    if not sar:
        sys.exit(f"analyse_sar: {path} is a binary sa file and sysstat's `sar` is not installed here. Ask the customer "
                 "for text output: LC_ALL=C S_TIME_FORMAT=ISO sar -A -f /var/log/sa/saDD > saDD.txt")
    env = dict(os.environ, LC_ALL="C", S_TIME_FORMAT="ISO")
    r = subprocess.run([sar, "-A", "-f", str(path)], capture_output=True, text=True, env=env)
    if r.returncode or not r.stdout.strip():
        sys.exit(f"analyse_sar: `sar -A -f {path}` failed ({r.stderr.strip() or 'no output'}); the file was probably "
                 "written by a different sysstat version. Ask the customer for text output (see --help).")
    return r.stdout


def parse(text, fallback_host, notes):
    """Yield sample dicts and restart markers from one sar text output."""
    host, ncpu, base, day, prev, cols, keyed = fallback_host, None, None, None, None, None, False
    rows, restarts = [], []
    for line in text.splitlines():
        h = HEADER_RE.match(line)
        if h:
            host, ncpu = h[2], int(h[4]) if h[4] else ncpu
            base, amb = parse_date(h[3])
            day = base
            if amb:
                notes.add(f"{host}: date '{h[3]}' is ambiguous; read as MM/DD/YYYY (ask for S_TIME_FORMAT=ISO output)")
            prev, cols = None, None
            continue
        if not line.strip():
            cols, prev, day = None, None, base                    # each sar section restarts at the first sample time
            continue
        m = TIME_RE.match(line)
        if not m or day is None:
            continue
        hh, mm, ss, ap, rest = int(m[1]), int(m[2]), int(m[3]), m[4], m[5].split()
        if ap:
            hh = hh % 12 + (12 if ap == "PM" else 0)
        secs = hh * 3600 + mm * 60 + ss
        if prev is not None and secs < prev - 3600:
            day += timedelta(days=1)
        prev = secs
        ts = day + timedelta(seconds=secs)
        if rest[:2] == ["LINUX", "RESTART"]:
            restarts.append((host, ts)); cols = None
            continue
        if not any(is_num(t) for t in rest):                       # a column-header line
            keyed = rest[0] in KEYED
            cols = [ALIAS.get(c, c) for c in (rest[1:] if keyed else rest)]
            prev, day = None, base
            continue
        if cols is None:
            continue
        key, vals = (rest[0], rest[1:]) if keyed else ("", rest)
        if len(vals) != len(cols) or not all(is_num(v) for v in vals):
            continue
        rows.append({"host": host, "ncpu": ncpu, "ts": ts, "key": key, "m": dict(zip(cols, map(float, vals)))})
    return rows, restarts


def find(rows, min_samples):
    runs, out = {}, []

    def close(k):
        run = runs.pop(k, None)
        if run and len(run) >= min_samples:
            rule = next(r for r in RULES if r.name == k[1])
            pick = max if rule.op == ">" else min
            peak = pick(run, key=lambda s: s[1])
            out.append({"host": k[0], "rule": rule.name, "key": k[2], "severity": rule.severity,
                        "start": run[0][0].isoformat(" "), "end": run[-1][0].isoformat(" "),
                        "samples": len(run), "peak": round(peak[1], 2), "peak_at": peak[0].isoformat(" "),
                        "threshold": rule.threshold, "op": rule.op, "unit": rule.unit, "meaning": rule.meaning})

    for r in sorted(rows, key=lambda r: r["ts"]):
        for rule in RULES:
            v = rule.value(r["m"], r["key"], r["ncpu"])
            if v is None:
                continue
            k = (r["host"], rule.name, r["key"])
            if (v > rule.threshold) if rule.op == ">" else (v < rule.threshold):
                runs.setdefault(k, []).append((r["ts"], v))
            else:
                close(k)
    for k in list(runs):
        close(k)
    return sorted(out, key=lambda f: (f["severity"], -f["samples"], f["host"], f["start"]))


def inventory(rows, restarts):
    by = defaultdict(list)
    for r in rows:
        by[r["host"]].append(r)
    inv = {}
    for host, rs in by.items():
        stamps = sorted({r["ts"] for r in rs})
        deltas = [(b - a).total_seconds() for a, b in zip(stamps, stamps[1:])]
        interval = statistics.median(deltas) if deltas else None
        gaps = [(a, b) for a, b in zip(stamps, stamps[1:]) if interval and (b - a).total_seconds() > 3 * interval]
        inv[host] = {"ncpu": rs[0]["ncpu"], "start": stamps[0], "end": stamps[-1], "samples": len(stamps),
                     "interval": interval, "gaps": gaps, "restarts": [t for h, t in restarts if h == host]}
    return inv


def write_series(rows, out):
    by = defaultdict(lambda: defaultdict(dict))
    for r in rows:
        m, k, n, d = r["m"], r["key"], r["ncpu"], by[r["host"]][r["ts"]]
        for name, col in (("cpu_busy", None), ("iowait", "%iowait"), ("steal", "%steal"), ("runq", "runq-sz"),
                          ("ldavg1", "ldavg-1"), ("pgscand", "pgscand/s")):
            v = _cpu_busy(m, k, n) if name == "cpu_busy" else (m.get(col) if col else None)
            if v is not None and (k in ("all", "") or name == "cpu_busy"):
                d[name] = v
        for rule, name in ((RULES[3], "swap_io"), (RULES[4], "mem_avail_pct")):
            v = rule.value(m, k, n)
            if v is not None:
                d[name] = v
        for col, name in (("%util", "disk_util_max"), ("await", "disk_await_max")):
            if k and col in m:
                d[name] = max(d.get(name, 0.0), m[col])
        v = _net_err(m, k, n)
        if v is not None:
            d["net_err"] = d.get("net_err", 0.0) + v
    cols = ["cpu_busy", "iowait", "steal", "runq", "ldavg1", "swap_io", "mem_avail_pct", "pgscand",
            "disk_util_max", "disk_await_max", "net_err"]
    for host, series in by.items():
        with (out / f"series-{host}.csv").open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["time"] + cols)
            for ts in sorted(series):
                w.writerow([ts.isoformat(" ")] + [round(series[ts][c], 2) if c in series[ts] else "" for c in cols])


def write_summary(inv, findings, notes, out):
    L = ["# SAR analysis", "", "## Hosts", "",
         "| Host | CPUs | From | To | Samples | Interval | Restarts | Gaps |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for host, i in sorted(inv.items()):
        iv = f"{i['interval'] / 60:g} min" if i["interval"] else "n/a"
        L.append(f"| {host} | {i['ncpu'] or '?'} | {i['start']} | {i['end']} | {i['samples']} | {iv} | "
                 f"{', '.join(str(t) for t in i['restarts']) or '-'} | {len(i['gaps'])} |")
    L += ["", "## Findings (ranked: likely cause first)", ""]
    if findings:
        L += ["| Host | Finding | Where | Window | Samples | Peak | Meaning |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for f in findings:
            tag = "likely cause" if f["severity"] == 0 else "check"
            cond = f"{f['op']} {f['threshold']:g} {f['unit']}"
            L.append(f"| {f['host']} | {f['rule']} ({tag}) | {f['key'] or '-'} | {f['start']} to {f['end']} | {f['samples']} | "
                     f"{f['peak']:g} at {f['peak_at']} (threshold {cond}) | {f['meaning']} |")
    else:
        L.append("No sustained saturation found at the default thresholds.")
    for host, i in sorted(inv.items()):
        for a, b in i["gaps"][:5]:
            L.append(f"\n- {host}: no samples between {a} and {b} (sar was not collecting, or the host was down).")
    L += ["", "## What SAR cannot show", "",
          "- Which process or MarkLogic task caused the load (use pidstat, the ErrorLog and Monitoring History).",
          "- Anything between samples: a 10-minute interval hides short stalls.",
          "- Whether a threshold is abnormal for this system: compare with a quiet period or baseline."]
    if notes:
        L += ["", "## Notes", ""] + [f"- {n}" for n in sorted(notes)]
    (out / "SUMMARY.md").write_text("\n".join(L) + "\n")


def load(paths, notes):
    rows, restarts = [], []
    files = []
    for p in map(Path, paths):
        files += sorted(f for f in p.rglob("*") if f.is_file()) if p.is_dir() else [p]
    used = 0
    for f in files:
        kind = sniff(f)
        if kind is None:
            continue
        text = binary_to_text(f) if kind == "binary" else f.read_text(errors="replace")
        r, rs = parse(text, f.stem, notes)
        rows += r; restarts += rs; used += 1
    return rows, restarts, used


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out")
    ap.add_argument("--min-samples", type=int, default=2)
    a = ap.parse_args(argv)
    notes = set()
    rows, restarts, used = load(a.paths, notes)
    if not rows:
        sys.exit("analyse_sar: no SAR data found (expected `sar -A` text output with a 'Linux ... (N CPU)' header).")
    out = Path(a.out) if a.out else Path("sar-analysis") / Path(a.paths[0]).stem
    out.mkdir(parents=True, exist_ok=True)
    findings, inv = find(rows, a.min_samples), inventory(rows, restarts)
    (out / "findings.json").write_text(json.dumps(findings, indent=2) + "\n")
    write_series(rows, out)
    write_summary(inv, findings, notes, out)
    print(f"wrote {out}: {used} files, {len(inv)} hosts, {len(rows)} samples, {len(findings)} findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the new tests, then the whole suite**

Run: `python3 -W error::ResourceWarning -m unittest tests.test_analyse_sar 2>&1 | tail -4` then `python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: both `OK` (12 new tests).

- [ ] **Step 6: Smoke-test the CLI on the fixtures**

Run: `python3 skills/marklogic-support/scripts/analyse_sar.py tests/fixture_sar --out /tmp/sar-smoke && head -20 /tmp/sar-smoke/SUMMARY.md`
Expected: first line `wrote /tmp/sar-smoke: 2 files, 2 hosts, 128 samples, 8 findings`; the findings table lists `mem_available (likely cause)` first for `ml-d1.example.com`.

- [ ] **Step 7: Commit**

```bash
git add skills/marklogic-support/scripts/analyse_sar.py tests/test_analyse_sar.py tests/fixture_sar
git commit -m "feat: analyse_sar.py turns sar -A output into a ranked saturation summary

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `sar-analysis.md` reference and source links

**Files:**
- Create: `skills/marklogic-support/references/sar-analysis.md`
- Modify: `skills/marklogic-support/references/sources.md` (new `## sar-analysis.md` section, same style as the others, inserted after the `## performance-tuning.md` section)
- Test: `tests/test_sar_docs.py` (create)

**Interfaces:**
- Consumes: the rule names and thresholds from Task 1 (`analyse_sar.RULES`).
- Produces: `references/sar-analysis.md` with a section `## Findings produced by analyse_sar.py` (rule table) and a `## Sources` list; the file name `sar-analysis.md` used by Tasks 3–4.

- [ ] **Step 1: Write the failing drift test** — create `tests/test_sar_docs.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_sar_docs 2>&1 | tail -6`
Expected: FAIL/ERROR — `sar-analysis.md` does not exist.

- [ ] **Step 3: Research** — use WebFetch to read, in this order, and note for each claim you will write which page supports it: the USE Method Linux checklist; `sar(1)` (man7.org) for the meaning of the columns the rules use (`%iowait`, `%steal`, `runq-sz`, `ldavg-*`, `pswpin/s`/`pswpout/s`, `kbavail`, `pgscand/s`, `majflt/s`, `await`, `%util`, `rxerr/s` …) and for `-s`/`-e`/`-f` options; `sadf(1)`; the sysstat README (collection: `sa1`/`sa2`, cron vs systemd timers, file locations); the thomas-krenn page; the Red Hat article if it can be fetched; the MarkLogic mlstat KB article; and MarkLogic documentation for what MarkLogic itself does on disk and in memory (merges, forests, caches, Huge Pages, swap: start from `references/databases-forests.md`, `references/memory-and-os.md` and their `## Sources`). Do not rely on search-result summaries.

- [ ] **Step 4: Write `skills/marklogic-support/references/sar-analysis.md`** (at most 250 lines) with exactly these sections in this order:

1. `# Linux SAR (sysstat) analysis for MarkLogic performance tickets`
2. `## Concepts` — what SAR/sysstat is (`sar`, `sadc`/`sa1`/`sa2`, `sadf`, `sa##` binary files vs text, default 10-minute interval, collection by cron or systemd timers, usual locations `/var/log/sa/` and `/var/log/sysstat/`); the USE method (utilization, saturation, errors per resource) and the SAR flags that answer it for CPU, memory, swap/paging, disk, network (from the Gregg checklist); time-format and timezone pitfalls (12-hour AM/PM locale output, `LC_ALL=C S_TIME_FORMAT=ISO`, SAR time is the host's local time vs ErrorLog time); what SAR cannot show (per-process attribution, sub-interval stalls, abnormal-for-this-system without a baseline).
3. `## Standard procedures` — numbered: run `scripts/analyse_sar.py`; confirm the data covers the incident window and has the sections needed (`-u`, `-q`, `-r`, `-S`/`-W`, `-B`, `-d`, `-n DEV,EDEV`); align timestamps with the ErrorLog timeline; read findings likely-cause first; compare against a quiet window; hand-over to MarkLogic-side checks (Monitoring History, `xdmp:host-status()`, merges/forest status — link `monitoring.md`, `databases-forests.md`, `memory-and-os.md`, `performance-tuning.md`); how to ask for more data (link `performance-data-requests.md`).
4. `## Findings produced by analyse_sar.py` — a table with one row per rule in `analyse_sar.RULES` (columns: Rule, Threshold, Meaning, First MarkLogic-side check) using the exact rule names and the thresholds from Task 1's Interfaces (`20`, `50`, `80`, `1`, `10`, `1`, `90`, `2`, `5`, `100`, `0`), the `--min-samples` rule (2 consecutive samples by default), and one sentence that thresholds are generic starting points (an SSD and a spinning disk have very different normal `await`).
5. `## Common mistakes & symptoms` — the exact header row `| Mistake | Symptom seen by customer | How to confirm | Fix / best practice | Source |`, then at least these rows (each row's Source is a URL you fetched that supports it, `Inside MarkLogic p.<n>` only if you have it, otherwise `[unverified — confirm]`): reading `%iowait` or `%util` alone as "slow disk" without `await`/`aqu-sz`; ignoring `%steal` on virtual machines; treating a high run queue as proof of CPU shortage without checking `blocked` and `%iowait`; calling swap activity harmless because `%memused` looks fine (use `kbavail`, `pswpin/s`/`pswpout/s`, `pgscand/s`); SAR not collecting or too coarse an interval so the incident falls between samples; comparing SAR (host local time, possibly 12-hour) against ErrorLog (MarkLogic time) without aligning timezone; reading the "Average:" lines for an incident window; analysing one node when the issue is on a different d-node/e-node; sysstat binary file from a different sysstat version that cannot be read elsewhere; MarkLogic's own merge activity being mistaken for an external disk problem (only keep this row if a MarkLogic source supports how merges use disk I/O; otherwise mark `[unverified — confirm]`).
6. `## Sources` — a bulleted list of every URL actually cited above, each with a few words on what it supports (must include the Gregg checklist, the `sar(1)` man page, the sysstat README, thomas-krenn, the MarkLogic mlstat KB article, and any Red Hat or MarkLogic documentation pages used).

- [ ] **Step 5: Add the sources section** — in `skills/marklogic-support/references/sources.md` insert, after the `## performance-tuning.md` section and before `## monitoring.md`, a `## sar-analysis.md` section whose bullets repeat the Sources list from Step 4, one line each in the file's existing style (`- <url> — what it supports`).

- [ ] **Step 6: Validate and test**

Run: `tools/check-ref.sh skills/marklogic-support/references/sar-analysis.md && python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK: skills/marklogic-support/references/sar-analysis.md` then `OK`. If `check-ref.sh` reports a row without a source, add the URL or `[unverified — confirm]`.

- [ ] **Step 7: Commit**

```bash
git add skills/marklogic-support/references/sar-analysis.md skills/marklogic-support/references/sources.md tests/test_sar_docs.py
git commit -m "docs: SAR analysis reference with USE-method mapping, thresholds and sources

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Customer data-request templates

**Files:**
- Create: `skills/marklogic-support/references/performance-data-requests.md`
- Test: `tests/test_sar_docs.py` (extend)

**Interfaces:**
- Consumes: `sar-analysis.md` (Task 2) for cross-references; the Salesforce-ready request style in `ticket-auditing.md` ("Required-Diagnostics.md").
- Produces: `references/performance-data-requests.md` with headings `## SAR export`, `## If SAR is not running`, `## Host metrics (iostat, vmstat, mpstat, pidstat)`, `## Kernel and OOM messages`, `## Hangs: thread dumps and pmap`, `## Cloud-hosted customers`, used by Task 4.

- [ ] **Step 1: Extend the drift test** — add to `tests/test_sar_docs.py` inside a new class:

```python
class RequestTemplateTest(unittest.TestCase):
    REQ = SKILL / "references/performance-data-requests.md"

    def test_sections_and_key_commands(self):
        text = self.REQ.read_text()
        for h in ("SAR export", "If SAR is not running", "Host metrics (iostat, vmstat, mpstat, pidstat)",
                  "Kernel and OOM messages", "Hangs: thread dumps and pmap", "Cloud-hosted customers"):
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_sar_docs.RequestTemplateTest 2>&1 | tail -6`
Expected: ERROR — the file does not exist.

- [ ] **Step 3: Research** — WebFetch and read: the sysstat README and `sar(1)` man page (collection, `-s`, `-e`, `-f`, file locations, RHEL systemd timers `sysstat-collect.timer`, how to change the interval); `iostat(1)`, `vmstat(8)`, `mpstat(1)`, `pidstat(1)` man pages (man7.org or sysstat docs) for the exact options below; for the cloud section, AWS documentation on EBS volume CloudWatch metrics (burst balance, queue length, read/write ops, throughput/IOPS limits) and EC2 CPU credits / steal time — if a metric name or behaviour is not on a page you fetched, mark it `[unverified — confirm]`. For thread dumps and `pmap`: read MarkLogic documentation or KB (help.marklogic.com) on collecting stack traces from a hung MarkLogic process; if none can be found, say so in the file and keep the caution wording below with `[unverified — confirm]`.

- [ ] **Step 4: Write `skills/marklogic-support/references/performance-data-requests.md`** (at most 200 lines), opening with a short paragraph: use these blocks to build the "Questions to ask the customer" and `Required-Diagnostics.md` entries on performance tickets that have no host-level data; copy a block, fill the `<...>` parts; each block is numbered, states why it is needed, and is plain language ready to paste into Salesforce; apply the security incident gate (`security-vulnerability-handling.md`) before asking for any file from a customer who mentioned a security incident; never use the word "breach". Then these sections, in this order, each with a ready-to-paste customer-facing request (a numbered list with the reason for each item) followed by a short "Engineer notes" bullet list:

1. `## SAR export` — for customers whose hosts already run sysstat: for each MarkLogic host involved (data and evaluation nodes), the incident date and a margin before and after; find the file (`/var/log/sa/saDD` on RHEL-family, `/var/log/sysstat/saDD` on Debian/Ubuntu — state which pages you verified); export with `LC_ALL=C S_TIME_FORMAT=ISO sar -A -f <file> > sar-<host>-<date>.txt` (and the `-s HH:MM:SS -e HH:MM:SS` window form); send the text files, and the raw `sa##` files too, explaining raw files are tied to the sysstat version and architecture; state the host's timezone and the exact incident time. Engineer notes: run `scripts/analyse_sar.py` on the text files; a binary file can only be converted on a host with a compatible sysstat.
2. `## If SAR is not running` — how to install and enable sysstat and collect going forward (package name, enabling `sysstat-collect.timer` on RHEL 8/9 or the cron job on older releases, shortening the interval to 1 minute while the issue is reproducible — only the settings you verified), plus a bounded live capture to run during the problem: `sar -u -q -r -S -B -d -n DEV,EDEV 5 120 > sar-live-<host>.txt` (check each flag against `sar(1)`); engineer note that a 5-second 10-minute capture during the incident beats a day of 10-minute averages.
3. `## Host metrics (iostat, vmstat, mpstat, pidstat)` — one capture per host during the problem, each with a fixed interval and count (for example `iostat -xz 5 120`, `vmstat -t 5 120`, `mpstat -P ALL 5 120`, `pidstat -u -r -d -t -p ALL 5 120` — verify each against the man pages), redirected to named files; explain what each shows (disk latency and queue, run queue/swap/blocked, per-CPU imbalance, which process uses CPU/memory/disk). Engineer notes: drop the first line of `vmstat`/`iostat` output (average since boot); a `pidstat` line for the MarkLogic process attributes the load.
4. `## Kernel and OOM messages` — `dmesg -T` filtered for out-of-memory, killed process, hung task and I/O errors (root may be needed), and the matching lines from `/var/log/messages*` (or `journalctl -k` on systemd hosts) for the incident window; why: shows whether the OOM killer or storage errors were involved. Engineer note: cross-check with the Log mode `TIMELINE.md`.
5. `## Hangs: thread dumps and pmap` — only for hangs or runaway memory: the MarkLogic process id, `pmap -x <pid>`, and thread stack traces (`pstack <pid>` or `gdb -p <pid> -batch -ex "thread apply all bt"`) taken three times about 10 seconds apart; caution that attaching a debugger to a production process can pause it briefly, so the customer should agree a time and take them only during the hang. Mark anything you could not verify `[unverified — confirm]`.
6. `## Cloud-hosted customers` — request **only** when the customer runs MarkLogic on a cloud provider (for example AWS), never on-prem: the instance type and size; the volume type, size and provisioned IOPS/throughput; for AWS, CloudWatch metrics for each data volume over the incident window (burst balance for burstable volume types, queue length, read/write operations and throughput versus the volume's limits) and for burstable instance types the CPU credit balance; and a note to look at `%steal` in the SAR/mpstat output. Use the metric names from the AWS pages you fetched. Engineer notes: steal above a few percent means the hypervisor is taking CPU; throttled volumes show high `await` with `%util` and IOPS pinned at the volume limit; keep this section provider-neutral where you cannot cite the provider's documentation.

- [ ] **Step 5: Run tests**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`. Note: the cloud/EBS test needs the word `EBS` to appear only in the Cloud section and `on-prem` before it — keep that wording.

- [ ] **Step 6: Commit**

```bash
git add skills/marklogic-support/references/performance-data-requests.md tests/test_sar_docs.py
git commit -m "docs: customer data-request templates for performance tickets (SAR, iostat, OOM, dumps, cloud)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Wire SAR into the skill

**Files:**
- Modify: `skills/marklogic-support/SKILL.md`
- Modify: `skills/marklogic-support/references/performance-tuning.md`
- Modify: `skills/marklogic-support/references/memory-and-os.md`
- Test: `tests/test_sar_docs.py` (extend)

**Interfaces:**
- Consumes: `scripts/analyse_sar.py` (Task 1), `references/sar-analysis.md` (Task 2), `references/performance-data-requests.md` (Task 3).

- [ ] **Step 1: Extend the drift test** — add to `tests/test_sar_docs.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_sar_docs.WiringTest 2>&1 | tail -8`
Expected: FAIL on the SAR-mode, triage and pointer tests.

- [ ] **Step 3: Edit `skills/marklogic-support/SKILL.md`** (read it first; Edit tool; each anchor must match exactly once — if not, stop and report NEEDS_CONTEXT):

1. In "Always first" step 2's classification list, after the line beginning `   - Log files (ErrorLog*, messages*, AccessLog, AuditLog` add:
```
   - Linux SAR/sysstat output (a `sar -A` text file, a binary `sa##` file, or a folder of them) → **SAR mode**
```
2. In "Triage mode", after the `For a security vulnerability ticket, print the banner ...` line, add:
```
For a performance or resource-pressure ticket with no host-level data (no SAR, iostat, vmstat or mpstat output), put a request from `references/performance-data-requests.md` in "Questions to ask the customer" — the SAR export or live capture, the host metrics, and, only when the customer runs on a cloud provider (for example AWS), its cloud signals. Ask for kernel/OOM messages on memory symptoms and thread dumps/`pmap` only for hangs.
```
3. Insert a new section between "## Log mode" (ending with its step 5) and "## Audit trail":
```
## SAR mode

Check the security incident gate first (Always first, step 3): SAR output is a customer-supplied file.

1. Run `scripts/analyse_sar.py <files or dirs> --out sar-analysis/<name>`, resolving `scripts/` relative to THIS skill's own directory (see Dump mode step 1). Never read a raw SAR file wholesale. If it reports a binary `sa##` file it cannot convert, ask the customer for text output using the "SAR export" request in `references/performance-data-requests.md`.
2. Read `references/sar-analysis.md`, then `<out>/SUMMARY.md`. Open `<out>/series-<host>.csv` only for a specific window and `findings.json` for exact values.
3. Output: **Host timeline** — per host the window, interval, restarts and gaps (SAR not collecting); **Findings** — each ranked finding (likely causes first) with what it means for MarkLogic and the confirming check from `sar-analysis.md`; then the Triage-mode format. Align SAR times with the ErrorLog timezone before correlating (Log mode `TIMELINE.md`), and say what SAR cannot show.
4. If the data does not cover the incident window, or lacks a section a finding needs (for example no `-d` disk data), say so and request it from `references/performance-data-requests.md`.
5. Then update the audit trail per the **Audit trail** section below; a data request is a `Required-Diagnostics.md` entry.
```
4. Add a routing-table row immediately after the security row (the first row):
```
| sar, sysstat, sadf, iostat, vmstat, mpstat, pidstat, %iowait, await, %util, run queue, load average, %steal, swap in/out, slow disk, OOM killer, performance data | `references/sar-analysis.md` and `references/performance-data-requests.md` |
```
5. In "Out of scope", leave unchanged.

- [ ] **Step 4: Edit `references/performance-tuning.md`** — add to `## Standard procedures` a new last numbered item:
`7. **Check host-level saturation first when queries are slow across the board**: if slowness is not specific to one query, look at the host (CPU, disk latency, swap, steal) with SAR before tuning queries — see \`sar-analysis.md\`; request the data with \`performance-data-requests.md\`.`
(plain backticks; the file must stay at most 250 lines and pass `tools/check-ref.sh`).

- [ ] **Step 5: Edit `references/memory-and-os.md`** — in standard procedure `8. **Monitor memory usage**`, append the sentence: ` SAR history (\`sar -r -S -B\`) shows swap and reclaim pressure over time — see \`sar-analysis.md\`.` (plain backticks).

- [ ] **Step 6: Run tests**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -3` and `tools/check-ref.sh skills/marklogic-support/references/performance-tuning.md && tools/check-ref.sh skills/marklogic-support/references/memory-and-os.md`
Expected: `OK` and two `OK:` lines.

- [ ] **Step 7: Commit**

```bash
git add skills/marklogic-support/SKILL.md skills/marklogic-support/references/performance-tuning.md skills/marklogic-support/references/memory-and-os.md tests/test_sar_docs.py
git commit -m "feat: SAR mode, routing and triage rule for host-level performance data

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review (done)

- **Spec coverage:** SAR parsing and analysis → T1; expert documentation (Gregg USE, sysstat man pages/README, Red Hat, thomas-krenn, MarkLogic mlstat) wired in and cited → T2 (`sources.md` + reference); request template covering SAR, iostat/vmstat/mpstat/pidstat, kernel/OOM, thread dumps/pmap, and cloud signals only for cloud tickets → T3; skill integration (mode, routing, triage rule, security gate, audit trail) → T4.
- **Placeholders:** none; code, fixtures and tests are given in full; research steps name the exact pages and the rule for unverified claims.
- **Name consistency:** rule names, thresholds, `SUMMARY.md`/`findings.json`/`series-<host>.csv`, and the file and section names used across tasks and the drift tests are identical.
- **Open items for the user:** thresholds are generic defaults (documented as such); README coverage of `analyse_sar.py` and the new references is deliberately left to the README/installation plan so it is written once.

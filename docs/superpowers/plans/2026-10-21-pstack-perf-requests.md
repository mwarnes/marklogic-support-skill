# pstack movie and perf Customer Requests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the skill request stack-sample and CPU-profile diagnostics from customers exactly as the Progress KB articles describe (pstack movie, perf), include the customer script verbatim, and route performance/hang tickets to those requests. (Phase 1 of 2: the analysis scripts follow once sample output is available.)

**Architecture:** One vendored script (`assets/support-scripts/pstack.sh`) with a README naming its source article; `performance-data-requests.md` gets three new customer-request sections replacing the old unverified "Hangs: thread dumps and pmap" section; `SKILL.md` routes hang/CPU keywords and the triage rule; tests pin the script bytes and the wiring.

**Tech Stack:** Markdown references, one bash script (not modified), Python `unittest`. Tests: `python3 -m unittest discover -s tests` (pytest is not installed).

## Global Constraints

Sources (pasted by the maintainer on 2026-10-21 because Progress community pages cannot be fetched; both are company KB articles):
- KB 000266816 "Creating a pstack movie for support" (https://community.progress.com/s/article/creating-a-pstack-movie-for-support, article dated Oct 15, 2024): the `pstack.sh` script; run as root, e.g. `./pstack.sh 60`; writes `/tmp/<HHMMSS-MM-DD-YYYY>.zip` to attach to the case; recommended run time 60 seconds; prerequisites `yum -y install pstack sysstat psutils gdb`; someone with root access must run it; running pstack stops the process while it records the threads (performance impact); "some cases are better handled by perf". The script samples every `INTERVAL=3` seconds (the article text says 5 — the script is what runs); `/etc/MarkLogic/proc-util.sh pstack` applies to MarkLogic 11.3.1 and later (RHEL9-based builds); for earlier versions, or 11.3.x builds not based on RHEL9, the script's own comment says to use `service MarkLogic pstack >> /tmp/$TSTAMP/pstack.log` instead. The article's "longer script (ml-support-dump.sh)" listing is identical to `pstack.sh` (no OS-level collection in what was supplied), so only `pstack.sh` is vendored.
- KB 000268341 "Using perf to understand performance" (https://community.progress.com/s/article/using-perf-to-understand-performance, article dated Oct 15, 2024): install `yum install perf` (RHEL/CentOS); as root/sudo on the MarkLogic host that is busy (all steps on the same host): `cd /tmp`; `perf record -F 99 -ag -- sleep 60` (about one minute, writes `perf.data` in the working directory); `perf report --header -I --stdio > `hostname -s`.`date -Is`.report`; `perf script > `hostname -s`.`date -Is`.script` (large but compresses well); `perf top` is a quick live view. perf samples the process (statistical, lighter than pstack, which pauses it); a typical use is about a minute while CPU is high.
- When to ask for which (from the articles only): pstack movie for "a query that seems to display unexpected behavior or a situation where the server appears to become unresponsive for a period of time"; perf when CPU is high / the cost of pausing the process matters.
- The security incident gate (`security-vulnerability-handling.md`) applies before asking a customer for files (stack traces and perf data are customer-supplied files); customer-facing text is numbered, plain, says why each item is needed, and never contains the word "breach".
- Every claim not in the two articles must be supported by a page fetched with WebFetch (man7.org man pages for `perf-record(1)`, `perf-report(1)`, `perf-script(1)`, `perf-top(1)`, `pmap(1)`; `date(1)`), or marked `[unverified — confirm]`. MarkLogic KB / community pages cannot be fetched; do not cite pages you could not read other than the two articles above, which are cited as the maintainer-supplied sources.
- `pmap -x <pid>` stays as a separate small memory-growth request (it was verified against `pmap(1)` earlier); the old unverified `gdb -p`/`pstack <pid>` manual commands are removed because the KB procedure replaces them.
- `KCS_SolutionContentStandard.txt`, `SECURITY_HANDLING.txt` and `kcs-drafts/` are untracked: never `git add` them. Existing tests keep passing.

---

## File Structure

- Create `skills/marklogic-support/assets/support-scripts/pstack.sh` (verbatim), `skills/marklogic-support/assets/support-scripts/README.md`.
- Create `tests/test_support_scripts.py`, `tests/test_pstack_perf_docs.py`.
- Modify `skills/marklogic-support/references/performance-data-requests.md`, `references/sources.md`, `SKILL.md`, `README.md`, `tests/test_sar_docs.py` (heading list only).

---

### Task 1: Vendor `pstack.sh`

**Files:**
- Create: `skills/marklogic-support/assets/support-scripts/pstack.sh` (executable)
- Create: `skills/marklogic-support/assets/support-scripts/README.md`
- Test: `tests/test_support_scripts.py`

**Interfaces:**
- Produces (used by Tasks 2–3): the path `assets/support-scripts/pstack.sh` inside the skill directory; the README names KB 000266816.

- [ ] **Step 1: Write the failing tests** — create `tests/test_support_scripts.py` exactly:

```python
import hashlib, os, subprocess, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "skills/marklogic-support/assets/support-scripts"
PSTACK = DIR / "pstack.sh"
PSTACK_SHA256 = "7664a2c0e7d7e71e6ac7ba280391422b9b4ddaad13bf12182ae00701a400ab21"


class PstackScriptTest(unittest.TestCase):
    def test_script_is_the_kb_article_script_verbatim(self):
        self.assertEqual(hashlib.sha256(PSTACK.read_bytes()).hexdigest(), PSTACK_SHA256,
                         "pstack.sh must stay byte-identical to the KB article; if the article changed, update the "
                         "script, this hash and the README together")

    def test_parses_and_is_executable(self):
        self.assertTrue(PSTACK.read_text().startswith("#!/bin/bash\n"))
        self.assertTrue(os.access(PSTACK, os.X_OK))
        r = subprocess.run(["bash", "-n", str(PSTACK)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    @unittest.skipIf(getattr(os, "geteuid", lambda: 1)() == 0, "must not run the script as root")
    def test_refuses_to_run_without_root_before_doing_anything(self):
        r = subprocess.run(["bash", str(PSTACK), "1"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("must be run as root", r.stderr)
        self.assertEqual(r.stdout, "")

    def test_script_contains_the_commands_the_requests_rely_on(self):
        text = PSTACK.read_text()
        for needle in ("INTERVAL=3", "/etc/MarkLogic/proc-util.sh pstack", "service MarkLogic pstack",
                       "zip -9 -r /tmp/$TSTAMP.zip /tmp/$TSTAMP"):
            self.assertIn(needle, text, needle)

    def test_readme_names_the_source_and_the_rules(self):
        text = (DIR / "README.md").read_text()
        for needle in ("000266816", "creating-a-pstack-movie-for-support", "verbatim", "INTERVAL=3",
                       "000268341", "ml-support-dump.sh"):
            self.assertIn(needle, text, needle)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_support_scripts 2>&1 | tail -6`
Expected: FAIL/ERROR — the files do not exist.

- [ ] **Step 3: Create `skills/marklogic-support/assets/support-scripts/pstack.sh`** with exactly this content (byte for byte, 1071 bytes, trailing newline), then `chmod +x` it. Do not "fix" or reformat anything in it:

```bash
#!/bin/bash

# root check
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root" 1>&2
   exit 1
fi

# default argument check
if [[ -z $1 ]]; then
        echo Usage: ./pstack.sh \[running time in seconds\]
        echo e.g. ./pstack.sh 60 \(runs the application for 1 minute before closing\)
        exit 1
fi

# global vars
TSTAMP=`date +"%H%M%S-%m-%d-%Y"`
INTERVAL=3 TIME=$1

# main
echo Support script started at: $TSTAMP - running for $TIME seconds with a sample every $INTERVAL seconds
mkdir /tmp/$TSTAMP

while [ $TIME -gt 0 ]; do
    date >> /tmp/$TSTAMP/pstack.log
    /etc/MarkLogic/proc-util.sh pstack >> /tmp/$TSTAMP/pstack.log
# For MarkLogic versions earlier than 11.3.1, or for any 11.3.x builds not based on RHEL9,
# the service command may also be used for this. In such cases, adjust the above command as follows:
# service MarkLogic pstack >> /tmp/$TSTAMP/pstack.log
    sleep $INTERVAL
    echo -e ". \c"
    let TIME-=$(($INTERVAL))
done
echo completed

# create zip
zip -9 -r /tmp/$TSTAMP.zip /tmp/$TSTAMP
echo /tmp/$TSTAMP.zip created
```

- [ ] **Step 4: Create `skills/marklogic-support/assets/support-scripts/README.md`** exactly:

````markdown
# Support scripts that are given to customers

These scripts are copied **verbatim** from Progress Knowledge Base articles so the engineer can hand the customer the
exact file. Do not edit them. If the article changes, replace the file, update its SHA-256 in
`tests/test_support_scripts.py`, and update this table.

| File | Source of truth | Copied |
| --- | --- | --- |
| `pstack.sh` | KB 000266816 "Creating a pstack movie for support" — https://community.progress.com/s/article/creating-a-pstack-movie-for-support (article dated Oct 15, 2024) | 2026-10-21, pasted by the maintainer (community pages cannot be fetched by the skill) |

## pstack.sh

Run as root on the MarkLogic host while the problem is happening: `./pstack.sh 60` records a stack trace of the MarkLogic
process every `INTERVAL=3` seconds for 60 seconds into `/tmp/<HHMMSS-MM-DD-YYYY>/pstack.log` and zips it to
`/tmp/<HHMMSS-MM-DD-YYYY>.zip`. Prerequisites (from the article): `yum -y install pstack sysstat psutils gdb`.

Things to know when sending it:

- **Interval:** the script samples every 3 seconds (`INTERVAL=3`); the article's text says 5 seconds. The script is what runs.
- **MarkLogic version:** the script calls `/etc/MarkLogic/proc-util.sh pstack` (MarkLogic 11.3.1 and later, RHEL9-based builds).
  For earlier versions, or 11.3.x builds not based on RHEL9, the script's own comment says to replace that line with
  `service MarkLogic pstack >> /tmp/$TSTAMP/pstack.log`.
- **Impact:** pstack stops the process while it records the threads, so each sample pauses MarkLogic briefly.
- **`ml-support-dump.sh`:** the article also lists a "longer pstack script" that is said to collect OS-level information, but the
  listing supplied for it is identical to `pstack.sh`, so only `pstack.sh` is kept here. Ask for OS-level data with the SAR and
  host-metrics requests in `references/performance-data-requests.md`.
- **Alternative:** KB 000268341 "Using perf to understand performance" (https://community.progress.com/s/article/using-perf-to-understand-performance)
  samples instead of pausing the process; see the perf request in `references/performance-data-requests.md`.
````

- [ ] **Step 5: Run tests and the whole suite**

Run: `chmod +x skills/marklogic-support/assets/support-scripts/pstack.sh && python3 -m unittest tests.test_support_scripts 2>&1 | tail -4 && python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK` (5 new tests; the root-refusal test is skipped only if you are root).

- [ ] **Step 6: Commit**

```bash
git add skills/marklogic-support/assets tests/test_support_scripts.py
git commit -m "feat: vendor the KB pstack.sh script verbatim with its source README

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Customer-request sections for pstack and perf

**Files:**
- Modify: `skills/marklogic-support/references/performance-data-requests.md`
- Modify: `skills/marklogic-support/references/sources.md`
- Modify: `tests/test_sar_docs.py` (the heading list in `RequestTemplateTest.test_sections_and_key_commands` only)
- Test: `tests/test_pstack_perf_docs.py` (create)

**Interfaces:**
- Consumes: Task 1's `assets/support-scripts/pstack.sh`.
- Produces: sections `## Stack samples: pstack movie`, `## CPU profile: perf`, `## Memory growth: pmap` in `performance-data-requests.md` (in that order, replacing `## Hangs: thread dumps and pmap`, before `## Cloud-hosted customers`).

- [ ] **Step 1: Write the failing tests** — create `tests/test_pstack_perf_docs.py` exactly:

```python
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/marklogic-support"
REQ = (SKILL / "references/performance-data-requests.md").read_text()
SOURCES = (SKILL / "references/sources.md").read_text()


def section(name):
    return REQ.split("## " + name + "\n", 1)[1].split("\n## ", 1)[0]


class StackAndPerfRequestTest(unittest.TestCase):
    def test_sections_exist_in_order_before_the_cloud_section(self):
        heads = [l[3:] for l in REQ.splitlines() if l.startswith("## ")]
        i = heads.index("Stack samples: pstack movie")
        self.assertEqual(heads[i:i + 4], ["Stack samples: pstack movie", "CPU profile: perf",
                                          "Memory growth: pmap", "Cloud-hosted customers"])
        self.assertNotIn("Hangs: thread dumps and pmap", heads)

    def test_pstack_request_follows_the_kb_procedure(self):
        s = section("Stack samples: pstack movie")
        for needle in ("assets/support-scripts/pstack.sh", "sudo ./pstack.sh 60", "yum -y install pstack sysstat psutils gdb",
                       "/etc/MarkLogic/proc-util.sh pstack", "service MarkLogic pstack", "11.3.1", "/tmp/",
                       "000266816", "creating-a-pstack-movie-for-support", "pauses", "while the problem is happening"):
            self.assertIn(needle, s, needle)
        self.assertIn("3 seconds", s)

    def test_perf_request_follows_the_kb_procedure(self):
        s = section("CPU profile: perf")
        for needle in ("yum install perf", "cd /tmp", "perf record -F 99 -ag -- sleep 60", "perf report --header -I --stdio",
                       "perf script", "same host", "000268341", "using-perf-to-understand-performance", "perf top"):
            self.assertIn(needle, s, needle)

    def test_old_unverified_manual_stack_commands_are_gone(self):
        self.assertNotIn("gdb -p <pid>", REQ)
        self.assertNotIn("pstack <pid>", REQ)
        self.assertNotIn("No official MarkLogic documentation or KB article describing process-level stack collection", REQ)

    def test_pmap_request_kept(self):
        self.assertIn("pmap -x <pid>", section("Memory growth: pmap"))

    def test_cloud_and_gate_rules_still_hold(self):
        before = REQ.split("## Cloud-hosted customers")[0]
        self.assertNotIn("EBS", before)
        self.assertIn("incident gate", REQ)
        self.assertNotIn("breach", REQ.lower())

    def test_sources_md_lists_both_kb_articles(self):
        for needle in ("https://community.progress.com/s/article/creating-a-pstack-movie-for-support",
                       "https://community.progress.com/s/article/using-perf-to-understand-performance",
                       "perf-record.1.html"):
            self.assertIn(needle, SOURCES, needle)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_pstack_perf_docs 2>&1 | tail -8`
Expected: FAIL — the new sections do not exist.

- [ ] **Step 3: Research.** WebFetch and read `perf-record(1)` (https://man7.org/linux/man-pages/man1/perf-record.1.html), `perf-report(1)`, `perf-script(1)`, `perf-top(1)` (same site) and `pmap(1)` / `date(1)` if needed, to confirm: `-F 99` (sampling frequency), `-a` (all CPUs, system-wide), `-g` (call graphs), `-- sleep 60` (record while the command runs), `perf report --header`, `-I` (check what it is in perf-report(1); do not guess), `--stdio`, `perf script` output, `perf top`, and that perf normally needs root or a relaxed `perf_event_paranoid`; and `date -Is` (ISO 8601 with colons in the file name). Anything you cannot confirm from a fetched page is marked `[unverified — confirm]`.

- [ ] **Step 4: Edit `performance-data-requests.md`.** Replace the whole section from the line `## Hangs: thread dumps and pmap` up to (not including) `## Cloud-hosted customers` with the three sections below, keeping the file's style (a `> ` blockquote customer request with numbered items and a reason for each, followed by `Engineer notes:`). Keep the file at most 200 lines (tighten other wording if needed without changing meaning). Content:

**`## Stack samples: pstack movie`** — intro line for the engineer: use for a hang, an unresponsive period, or a query that behaves unexpectedly (KB 000266816, https://community.progress.com/s/article/creating-a-pstack-movie-for-support, maintainer-supplied). Customer request (plain language):
1. Why: "We need to see what the MarkLogic server threads are doing over a short time while the problem is happening. A script from Support records a stack trace of the MarkLogic process every 3 seconds and zips the result."
2. "Someone with root access on the MarkLogic host runs these steps. First install the tools if they are missing: `yum -y install pstack sysstat psutils gdb` (RHEL/CentOS)."
3. "Copy the attached `pstack.sh` to the host and make it executable (`chmod +x pstack.sh`)."
4. "While the problem is happening, run it for 60 seconds: `sudo ./pstack.sh 60`."
5. "It writes a zip file in `/tmp/` named after the server time and date (for example `/tmp/101530-10-21-2026.zip`). Please attach it to the case, with the host name and the time the problem happened."
6. A caution paragraph: "Each sample briefly pauses the MarkLogic process while it records the threads, so this has a small performance impact. Please agree a time with us first on a production system, and run it only while the problem is happening."
7. For MarkLogic older than 11.3.1, or an 11.3.x build not based on RHEL 9: tell the customer to open `pstack.sh` and replace the line `/etc/MarkLogic/proc-util.sh pstack >> /tmp/$TSTAMP/pstack.log` with `service MarkLogic pstack >> /tmp/$TSTAMP/pstack.log` (the script contains this as a comment).
Engineer notes (bullets): the script is `<skill-dir>/assets/support-scripts/pstack.sh` (vendored verbatim from the KB article; give the customer that file); the article text says 5-second samples but the script uses 3; the article's `ml-support-dump.sh` listing is identical to `pstack.sh`, so ask for OS-level data with the SAR/host-metrics requests; pstack pauses the process, so if the problem is sustained high CPU prefer the perf request below; the security incident gate applies before asking for the file; the zip contains `pstack.log` (a dated series of stack traces) — analysis tooling for it is planned (phase 2).

**`## CPU profile: perf`** — intro: use when CPU is high or when pausing the process is a concern (KB 000268341, https://community.progress.com/s/article/using-perf-to-understand-performance, maintainer-supplied; perf samples the process instead of pausing it, so it is lighter than pstack). Customer request:
1. Why: "We need a statistical profile of where the CPU time goes while the CPU is high."
2. "On the MarkLogic host that is busy, as root (or with sudo), install perf if it is missing: `yum install perf` (RHEL/CentOS)."
3. "While the CPU is high, run these on that same host: `cd /tmp` then `perf record -F 99 -ag -- sleep 60`. It takes about a minute and writes `perf.data` in the current directory."
4. "Create the report: `perf report --header -I --stdio > $(hostname -s).$(date -Is).report`"
5. "Create the script output: `perf script > $(hostname -s).$(date -Is).script`. It can be large but compresses well, so please zip it."
6. "Please attach the `.report` file and the zipped `.script` file to the case."
Engineer notes: all steps must be run on the same MarkLogic host; `perf top` gives a quick live view of what is using the CPU; add the flag meanings you verified from `perf-record(1)` etc. (cite the man pages) and mark the rest `[unverified — confirm]`; `date -Is` puts colons in the file names (fine on Linux; rename if the files are copied to Windows); the files hold function names and counts, not document content `[unverified — confirm]`; analysis tooling is planned (phase 2).

**`## Memory growth: pmap`** — keep the existing `pmap -x <pid>` request and its engineer notes from the old section (memory map at the start and end of the growth, compare), drop everything about gdb and manual pstack, and keep the verified/unverified markers exactly as they were for what remains. Add the process-id lookup only if it was in the old text.

- [ ] **Step 5: Update the other files.**
1. `tests/test_sar_docs.py`: in `RequestTemplateTest.test_sections_and_key_commands` replace the heading name `"Hangs: thread dumps and pmap"` with the three names `"Stack samples: pstack movie", "CPU profile: perf", "Memory growth: pmap"` (same loop, in file order). Change nothing else there.
2. `references/sources.md`: in the `## performance-data-requests.md` section add one line per source, in the file's existing style (`- <url> — what it supports`): the two KB URLs (note "maintainer-supplied copy; community pages cannot be fetched"), and every man7.org page you fetched in Step 3 (perf-record.1.html, perf-report.1.html, perf-script.1.html, perf-top.1.html, and any other). Remove or rewrite the existing line that describes mlstat/pstack gist only if it now contradicts the new text.

- [ ] **Step 6: Run tests and the whole suite**

Run: `python3 -m unittest tests.test_pstack_perf_docs tests.test_sar_docs 2>&1 | tail -4 && python3 -m unittest discover -s tests 2>&1 | tail -3 && wc -l skills/marklogic-support/references/performance-data-requests.md`
Expected: `OK`, `OK`, at most 200 lines.

- [ ] **Step 7: Commit**

```bash
git add skills/marklogic-support/references/performance-data-requests.md skills/marklogic-support/references/sources.md tests/test_sar_docs.py tests/test_pstack_perf_docs.py
git commit -m "docs: pstack movie and perf customer requests from the KB articles

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Route hang and CPU tickets to the requests

**Files:**
- Modify: `skills/marklogic-support/SKILL.md`, `README.md`
- Test: `tests/test_pstack_perf_docs.py` (extend)

- [ ] **Step 1: Extend the tests** — add to `tests/test_pstack_perf_docs.py` (before the `if __name__` line):

```python
class WiringTest(unittest.TestCase):
    SKILL_MD = (SKILL / "SKILL.md").read_text()
    README = (ROOT / "README.md").read_text()

    def test_routing_row_has_hang_and_cpu_keywords(self):
        rows = [l for l in self.SKILL_MD.splitlines() if l.startswith("|") and "performance-data-requests.md" in l]
        self.assertTrue(rows)
        for kw in ("pstack", "perf", "hang", "unresponsive", "high CPU"):
            self.assertIn(kw, rows[0], kw)

    def test_triage_rule_chooses_between_pstack_and_perf(self):
        triage = self.SKILL_MD.split("## Triage mode")[1].split("## Q&A mode")[0]
        for needle in ("pstack", "perf", "pauses"):
            self.assertIn(needle, triage, needle)

    def test_readme_lists_the_script_and_the_requests(self):
        for needle in ("assets/support-scripts/pstack.sh", "pstack movie", "perf"):
            self.assertIn(needle, self.README, needle)
        self.assertNotIn("thread dumps and, on cloud-hosted", self.README)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_pstack_perf_docs.WiringTest 2>&1 | tail -6`
Expected: FAIL.

- [ ] **Step 3: Edit `skills/marklogic-support/SKILL.md`** (read first; anchors must match once, else report NEEDS_CONTEXT):
1. In "Triage mode", extend the paragraph that begins `For a performance or resource-pressure ticket with no host-level data` by appending these sentences: ` For a hang, an unresponsive period or a query behaving unexpectedly, ask for the pstack movie; for sustained high CPU, or when pausing the process is a concern, ask for perf instead — pstack pauses the MarkLogic process while it records the threads, perf only samples it (both procedures are in \`references/performance-data-requests.md\`; the customer script is \`assets/support-scripts/pstack.sh\`). Never ask for either from a customer who mentioned a security incident until the incident gate is cleared.` (plain backticks)
2. In the routing-table row that contains `references/performance-data-requests.md`, add these keywords to the "If the ticket mentions…" cell: `pstack, perf, stack trace, hang, unresponsive, high CPU`.

- [ ] **Step 4: Edit `README.md`.** In the "Support dumps, logs and SAR data" section replace the sentence ending `kernel and OOM messages, thread dumps and, on cloud-hosted customers only, steal and EBS signals.` so it reads: `kernel and OOM messages, the pstack movie and perf requests (from the Progress KB articles; the customer script is vendored at \`skills/marklogic-support/assets/support-scripts/pstack.sh\`) and, on cloud-hosted customers only, steal and EBS signals.` In the "What's included" tree add, under `skills/marklogic-support/`, a line `│   ├── assets/support-scripts/pstack.sh   customer script from KB 000266816 (verbatim)` placed between `SKILL.md` and `scripts/` (keep the tree's alignment style). Keep every other README statement unchanged (tests/test_readme.py must still pass).

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add skills/marklogic-support/SKILL.md README.md tests/test_pstack_perf_docs.py
git commit -m "feat: route hang and high-CPU tickets to the pstack movie and perf requests

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review (done)

- **Spec coverage:** request pstack diagnostics using the KB article and its scripts → T1 (vendored verbatim, source README) + T2 (customer request); perf analysis request → T2; ticket handling (when to ask for which, gate) → T2 notes + T3 triage rule and routing; sources recorded → T2 `sources.md`. Phase 2 (not in this plan, needs sample output): `analyse_pstack.py` and a perf-report summariser, plus a pstack-reading reference.
- **Placeholders:** none; the script and customer text are given; the research step names the exact pages and the unverified-marker rule.
- **Name consistency:** `assets/support-scripts/pstack.sh`, section names, KB article numbers and URLs are identical across tasks and tests.
- **Open items for the user:** (1) confirm 3-second interval is the intended one (the article text says 5); (2) the real `ml-support-dump.sh` (the pasted copy duplicates `pstack.sh`); (3) a sample pstack movie and a sample `perf report`/`perf script` for phase 2; (4) any notes on interpreting MarkLogic stacks.

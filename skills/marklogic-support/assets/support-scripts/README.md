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

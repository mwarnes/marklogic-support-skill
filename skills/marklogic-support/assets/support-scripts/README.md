# Support scripts that are given to customers

These scripts are copied from Progress Knowledge Base articles so the engineer can hand the customer the exact file.
`pstack.sh` has **one deliberate change** from the article: `INTERVAL=5` instead of the article script's `INTERVAL=3`
(maintainer decision 2026-10-21; the article text says 5 seconds, but its script uses 3). A customer who downloads the
script from the KB article gets the 3-second version. To re-derive: `tests/test_support_scripts.py` pins the hash of the
original article script and the hash of this file, and a test proves that replacing `INTERVAL=5 TIME=$1` with
`INTERVAL=3 TIME=$1` reproduces the original, so the interval line is the only difference. Do not otherwise edit the
scripts. If the article changes, replace the file, update both hashes here and in `tests/test_support_scripts.py`, and
update this table.

| File | Source of truth | Copied |
| --- | --- | --- |
| `pstack.sh` | KB 000266816 "Creating a pstack movie for support" — https://community.progress.com/s/article/creating-a-pstack-movie-for-support (article dated Oct 15, 2024), with `INTERVAL=5` instead of `INTERVAL=3` | 2026-10-21, pasted by the maintainer (community pages cannot be fetched by the skill); interval changed 2026-10-21 |

Hashes (SHA-256): original KB script `7664a2c0e7d7e71e6ac7ba280391422b9b4ddaad13bf12182ae00701a400ab21`; this file `cbd5ad316f28a5e44d53d3da5b8f87633b97870eaecfbb9aa7aa79981d78a58c`.

## pstack.sh

Run as root on the MarkLogic host while the problem is happening: `./pstack.sh 60` records a stack trace of the MarkLogic
process every `INTERVAL=3` seconds for 60 seconds into `/tmp/<HHMMSS-MM-DD-YYYY>/pstack.log` and zips it to
`/tmp/<HHMMSS-MM-DD-YYYY>.zip`. Prerequisites (from the article): `yum -y install pstack sysstat psutils gdb`.

Things to know when sending it:

- **Interval:** this copy samples every 5 seconds (`INTERVAL=5`). The article text says 5 seconds but its own script uses 3, so a customer who downloads the KB copy gets 3-second samples.
- **MarkLogic version:** the script calls `/etc/MarkLogic/proc-util.sh pstack` (MarkLogic 11.3.1 and later, RHEL9-based builds).
  For earlier versions, or 11.3.x builds not based on RHEL9, the script's own comment says to replace that line with
  `service MarkLogic pstack >> /tmp/$TSTAMP/pstack.log`.
- **Impact:** pstack pauses the MarkLogic process while it records the threads, which has a performance impact.
- **`ml-support-dump.sh`:** the article also lists a "longer pstack script" said to collect OS-level information, but its
  listing is identical to `pstack.sh` (the maintainer confirmed the community site's copy is a duplicate too), so only
  `pstack.sh` is kept here and it is what customers use. Support dumps are usually generated separately or supplied through
  the telemetry link; OS-level data is requested with the SAR and host-metrics requests in
  `references/performance-data-requests.md`.
- **Alternative:** KB 000268341 "Using perf to understand performance" (https://community.progress.com/s/article/using-perf-to-understand-performance)
  samples instead of pausing the process; see the perf request in `references/performance-data-requests.md`.

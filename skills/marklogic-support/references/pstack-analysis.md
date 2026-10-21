# Reading a pstack movie

Guide for reading a pstack movie and a perf report, with the two analysis scripts. It is built from the maintainer notes plus one anonymised customer capture (the worked example); the notes are dated 2026-10-21 ("very simplified"). Other facts are already recorded in `performance-data-requests.md` and `assets/support-scripts/README.md`. Anything beyond those is marked `[unverified — confirm]`. Do not infer what a MarkLogic frame or thread name means from this guide.

## Concepts

- A pstack movie is the `pstack.log` inside the zip written by `assets/support-scripts/pstack.sh` (KB 000266816): a `date` line, then one whole-process stack trace for each sample. The copy in this repo samples every 5 seconds. Each sample pauses the MarkLogic process.
- Three things to look for (maintainer notes, 2026-10-21):
  1. Thread states: threads that repeat across multiple snapshots at the exact same instruction or function call.
  2. Lock contention or waiting: threads stuck in sleep, poll or synchronisation primitives indicate waiting on external resources, I/O or cluster locks.
  3. CPU spinning: identical C++/internal MarkLogic function stacks across rapid-fire traces point to hot spots or runaway queries.
- What a given MarkLogic function or thread name means, and which frames count as "waiting", is not recorded here `[unverified — confirm]`.
- This guide is simplified and is refined from real samples. Two scripts do the counting; the engineer does the interpreting.
- `scripts/analyse_pstack.py <pstack.log|zip|dir> --out DIR` writes `SUMMARY.md`, `findings.json` and `snapshots.csv` (counts and top signatures, never whole stacks). `date` lines start a snapshot; without them a new snapshot starts where the thread numbers restart, and the sample times are unknown. `--min-samples` and `--min-threads` default to 3.
- `scripts/analyse_perf.py <report> --out DIR` reads `perf report --stdio` text and writes `SUMMARY.md`, `findings.json` and `top-symbols.csv`.
- The maintainer notes supply only the three categories above (same place across snapshots; waiting in sleep/poll/sync; identical internal stacks). The specific wait and lock function name lists and the allocator and `CacheListStorage` patterns in the scripts are the script author's heuristics, derived from one real capture; they are not a statement of what MarkLogic functions do `[unverified — confirm]`.

## Finding rules

- pstack: frame names are normalised (`__GI_`, `__libc_`, leading underscores, `.constprop.N`/`.isra.N`/`.part.N`/`.cold` removed) and the first 3 frames are checked. A thread is Waiting when any of them is a sleep, poll, accept, semaphore, condition or futex wait; Lock wait when the top frame, or the frame directly under a wait/futex frame, is a mutex wait, and for `sched_yield`; otherwise Running.
- `allocator_purge`: 3+ threads in a snapshot have `pages_purge` or `arena_purge` in the stack (jemalloc purging dirty pages, which calls `madvise`). `thread_cache_flush`: a jemalloc thread cache is flushed or destroyed. `allocator_lock_wait` and `list_cache_lock_wait`: a lock wait under a jemalloc arena or `CacheListStorage` frame.
- `bursty_*`: a pattern present in some snapshots and absent in others (needs 3+ snapshots). `same_stack_across_snapshots`: non-waiting threads with the same top frames in 3+ consecutive snapshots. `thread_churn`: 10% or more of the thread ids appear in only one snapshot (needs 3+ snapshots).
- perf: `kernel_dominant` when kernel code of the busiest command is at least 50% of samples; `time_under_user_wrapper` when a user-space symbol is at least 25% inclusive but at most 1% self (the time is in the functions it calls; thread entry points such as `start_thread` and `__clone` are ignored, at most 2 reported; kernel time is stated only when the kernel share is also at least 50%); the busiest command ignores `swapper`/`idle`; `unresolved_kernel_symbols` when at least 50% of kernel time is bare addresses; `user_hotspot` at 5% self for one user symbol; `allocator_share` at 5% self in allocator code.

## Several hosts

- Give the script the customer's zip or folder as it is: one zip per host (even zips in zips), macOS junk and duplicate copies are handled, and the host name is the nearest enclosing zip stem or folder name (innermost first) that is not generic (`pstack logs`, `logs`, `tmp`, `data`, ...) or a capture timestamp, else the last two parts of the file path; two hosts with the same name get the file name appended. Folder, member and header names are cleaned of control characters, `|` and backticks before they reach SUMMARY.md or the CSVs, and special files (FIFOs, devices) are never opened.
- With more than one input SUMMARY.md and `hosts.csv` start with one row per host: Host, Snapshots, Span (first to last date line, `-` when the dates do not parse), Threads, Running and Lock wait (the maximum in one snapshot) and Top finding (the first finding's rule). Hosts with a severity-0 finding come first.
- Threads are compared per host: the same-stack, burst and churn rules run on each input on its own, never across hosts. Snapshots from different hosts are not taken at the same instant unless the customer ran pstack.sh on all hosts at the same time `[unverified — confirm]`, so do not line them up by snapshot number.
- perf overview (several nodes): one row per node with Host (the `perf.data` header host name, else the zip or folder name), Input kind (`perf.data` or `report`), Kernel, CPUs, Memory, Window, Capture command, Analysed and, when analysed, the kernel share of the busiest command and the top finding; also `hosts.csv`. A raw `perf.data` is analysed only with `--convert` (local perf); otherwise it is a header row (convert it or re-request the text report: `Raw perf.data received: convert or re-request` in `performance-data-requests.md`). When the kernel or capture command differs between nodes a note says the nodes were not captured the same way: compare their numbers with care `[unverified — confirm]`.
- Very large logs are parsed whole in memory: hundreds of MB of log can need several GB of RAM `[unverified — confirm]`. With more than 20 inputs only those with a finding get a section (the table lists all).
- Only the first input gets the thread kinds and top frames; the per-snapshot counts and findings of all of them are in `snapshots.csv` and `findings.json`.

## Standard procedures

1. Run `scripts/analyse_pstack.py` (pstack.log or zip) and `scripts/analyse_perf.py` (perf report) and read their SUMMARY.md before reading anything by hand.
2. Confirm the data: the zip, `pstack.log` inside it, the number of samples, the `date` lines (they give the sample times) and that they fall inside the incident window the customer gave.
3. Compare each thread across samples: note the threads whose top frames do not change from one sample to the next.
4. Classify each repeating thread by the three patterns in Concepts: same place across samples, waiting in sleep/poll/synchronisation, or identical internal stacks across rapid traces.
5. Cross-reference `/var/opt/MarkLogic/Logs/ErrorLog.txt` for the same time window (see `log-anatomy.md`) for concurrent query or system errors. Debug log level is ideal per the notes; what Debug adds beyond that is `[unverified — confirm]`. Align time zones, host local time against MarkLogic log time `[unverified — confirm]`.
6. Correlate with host metrics: SAR (`references/sar-analysis.md`), iostat, vmstat and pmap output, or the community tool mlstat (MarkLogic Monitoring and System Stats) to line OS metrics up with server activity. Requests for these are in `references/performance-data-requests.md`.
7. If the problem is sustained high CPU, prefer the perf request (KB 000268341) because pstack pauses the process; perf is lightweight statistical CPU sampling.
8. Triage questions to ask the customer: is MarkLogic experiencing high CPU or appearing hung/unresponsive? Are there multiple pstack samples or ErrorLog.txt snippets to interpret?
9. Never ask for stack data, and never open it, until the security incident gate is cleared (`security-vulnerability-handling.md`).

## Common mistakes & symptoms

| Mistake | Symptom seen by customer | How to confirm | Fix / best practice | Source |
| --- | --- | --- | --- | --- |
| Reading a single sample as a hang | A server called "hung" on the evidence of one trace | Compare the same thread across several samples; a hang repeats at the same call | Look for threads repeating at the exact same function across snapshots | maintainer notes 2026-10-21; https://community.progress.com/s/article/creating-a-pstack-movie-for-support |
| Not cross-referencing ErrorLog.txt | Stack findings with no explanation of the trigger | Read `/var/opt/MarkLogic/Logs/ErrorLog.txt` for the sample window | Check concurrent query or system errors; Debug level ideal [unverified — confirm] beyond the notes | maintainer notes 2026-10-21; [unverified — confirm] |
| Using pstack for sustained high CPU when perf is lighter | Further slowdown while data is collected | CPU stays high for long periods in SAR or host metrics | Ask for the perf request (KB 000268341) instead | maintainer notes 2026-10-21; https://community.progress.com/s/article/using-perf-to-understand-performance |
| Forgetting pstack pauses the process | Production slows or stalls during collection | Each sample pauses MarkLogic (KB 000266816) | Agree a time first and run it only while the problem happens | maintainer notes 2026-10-21; https://community.progress.com/s/article/creating-a-pstack-movie-for-support |

## Worked example (anonymised, 2015, MarkLogic on EC2)

Facts from the captures (a customer reported sustained high CPU on MarkLogic on AWS EC2: Linux with glibc 2.12 (RHEL/CentOS 6 era), jemalloc, a Xen network driver in the perf report):

- perf (95K `cpu-clock` samples): the MarkLogic process is 82.5% of samples; about 67% of all samples are kernel code of that process; 66.5% are inclusive under `madvise` with about 0.01% self (the time is inside the kernel call). Kernel symbols were unresolved addresses (82.7%). MarkLogic user-space code is about 15%; the top user symbol, `xdmp::CacheListPostingIterator::_skip`, is 2.6%.
- pstack (4 snapshots of 147, 144, 144 and 147 threads, no timestamps): snapshots 1 and 3 had 15 and 12 threads whose stacks go `madvise <- pages_purge <- arena_purge` (reached through thread-cache destroy/flush and freeing buffers); snapshots 2 and 4 had none. One thread in snapshot 1 waited on a jemalloc arena lock under `tcache_create`. 22 of 167 distinct thread ids appeared in only one snapshot (thread churn).
- The customer had earlier connected the load balancer directly to MarkLogic and then reduced the App Server HTTP timeout (and resized and changed cache sizes); afterwards they reported sustained CPU falling from 90%+ to under 10%. They still wanted the issue reproduced and fixed.

Inference (all `[unverified — confirm]`):

- CPU was burning in kernel memory-release calls triggered by allocator purging, not in query evaluation.
- The files do not show why the kernel call is expensive on that platform, nor any effect of the HTTP timeout. Several settings changed at once, so the change is a mitigation or workaround, not shown to be a root-cause fix.
- Both files are a single capture taken before the change.

Follow-ups: capture perf and pstack again after the change under similar load; run perf so kernel symbols resolve (how and where perf was run decides this `[unverified — confirm]`) and send the `--header` output; record the kernel version, instance type and Transparent Huge Page setting; take the allocator finding to engineering.

## Sources

- Maintainer notes, 2026-10-21 (simplified, pasted by the maintainer; not a URL).
- anonymised 2015 customer capture used for the worked example and the test fixtures; not kept in the repository (not a URL).
- KB 000266816, https://community.progress.com/s/article/creating-a-pstack-movie-for-support (maintainer-supplied copy; page cannot be fetched).
- KB 000268341, https://community.progress.com/s/article/using-perf-to-understand-performance (maintainer-supplied copy; page cannot be fetched).
- `scripts/analyse_pstack.py` and `scripts/analyse_perf.py` in this skill (thresholds are constants at the top of each script).
- https://github.com/marklogic-community/mlstat (community tool, not official guidance).

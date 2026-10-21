# Reading a pstack movie

Manual guide for reading a pstack movie by hand. It is built only from the maintainer notes, 2026-10-21 ("very simplified") and facts already recorded in `performance-data-requests.md` and `assets/support-scripts/README.md`. Anything beyond those is marked `[unverified — confirm]`. Do not infer what a MarkLogic frame or thread name means from this guide.

## Concepts

- A pstack movie is the `pstack.log` inside the zip written by `assets/support-scripts/pstack.sh` (KB 000266816): a `date` line, then one whole-process stack trace for each sample. The copy in this repo samples every 5 seconds. Each sample pauses the MarkLogic process.
- Three things to look for (maintainer notes, 2026-10-21):
  1. Thread states: threads that repeat across multiple snapshots at the exact same instruction or function call.
  2. Lock contention or waiting: threads stuck in sleep, poll or synchronisation primitives indicate waiting on external resources, I/O or cluster locks.
  3. CPU spinning: identical C++/internal MarkLogic function stacks across rapid-fire traces point to hot spots or runaway queries.
- What a given MarkLogic function or thread name means, and which frames count as "waiting", is not recorded here `[unverified — confirm]`.
- This guide is simplified and will be refined from real samples. An `analyse_pstack.py` script is planned; there is no analysis script yet, so analyse by hand.

## Standard procedures

1. Confirm the data: the zip, `pstack.log` inside it, the number of samples, the `date` lines (they give the sample times) and that they fall inside the incident window the customer gave.
2. Compare each thread across samples: note the threads whose top frames do not change from one sample to the next.
3. Classify each repeating thread by the three patterns in Concepts: same place across samples, waiting in sleep/poll/synchronisation, or identical internal stacks across rapid traces.
4. Cross-reference `/var/opt/MarkLogic/Logs/ErrorLog.txt` for the same time window (see `log-anatomy.md`) for concurrent query or system errors. Debug log level is ideal per the notes; what Debug adds beyond that is `[unverified — confirm]`. Align time zones, host local time against MarkLogic log time `[unverified — confirm]`.
5. Correlate with host metrics: SAR (`references/sar-analysis.md`), iostat, vmstat and pmap output, or the community tool mlstat (MarkLogic Monitoring and System Stats) to line OS metrics up with server activity. Requests for these are in `references/performance-data-requests.md`.
6. If the problem is sustained high CPU, prefer the perf request (KB 000268341) because pstack pauses the process; perf is lightweight statistical CPU sampling.
7. Triage questions to ask the customer: is MarkLogic experiencing high CPU or appearing hung/unresponsive? Are there multiple pstack samples or ErrorLog.txt snippets to interpret?
8. Never ask for stack data, and never open it, until the security incident gate is cleared (`security-vulnerability-handling.md`).

## Common mistakes & symptoms

| Mistake | Symptom seen by customer | How to confirm | Fix / best practice | Source |
| --- | --- | --- | --- | --- |
| Reading a single sample as a hang | A server called "hung" on the evidence of one trace | Compare the same thread across several samples; a hang repeats at the same call | Look for threads repeating at the exact same function across snapshots | maintainer notes 2026-10-21; https://community.progress.com/s/article/creating-a-pstack-movie-for-support |
| Not cross-referencing ErrorLog.txt | Stack findings with no explanation of the trigger | Read `/var/opt/MarkLogic/Logs/ErrorLog.txt` for the sample window | Check concurrent query or system errors; Debug level ideal [unverified — confirm] beyond the notes | maintainer notes 2026-10-21; [unverified — confirm] |
| Using pstack for sustained high CPU when perf is lighter | Further slowdown while data is collected | CPU stays high for long periods in SAR or host metrics | Ask for the perf request (KB 000268341) instead | maintainer notes 2026-10-21; https://community.progress.com/s/article/using-perf-to-understand-performance |
| Forgetting pstack pauses the process | Production slows or stalls during collection | Each sample pauses MarkLogic (KB 000266816) | Agree a time first and run it only while the problem happens | maintainer notes 2026-10-21; https://community.progress.com/s/article/creating-a-pstack-movie-for-support |

## Sources

- Maintainer notes, 2026-10-21 (simplified, pasted by the maintainer; not a URL).
- KB 000266816, https://community.progress.com/s/article/creating-a-pstack-movie-for-support (maintainer-supplied copy; page cannot be fetched).
- KB 000268341, https://community.progress.com/s/article/using-perf-to-understand-performance (maintainer-supplied copy; page cannot be fetched).
- https://github.com/marklogic-community/mlstat (community tool, not official guidance).

# Linux SAR (sysstat) analysis for MarkLogic performance tickets

## Concepts

- **What SAR is**: `sar` is part of the sysstat package. `sadc` is the collector backend; `sa1` stores binary samples in the daily data file and `sa2` writes a daily summary report; both are designed to run from cron or systemd. `sadf` re-exports saved data (CSV, JSON, XML). Source: sysstat README, `sar(1)`, `sadf(1)`.
- **Default interval and enabling**: the default collection interval is 10 minutes (it can be as small as 1 second). Collection is not necessarily on: sysstat is not installed by default on RHEL, and on Debian logging is off until `ENABLED` is set to true in `/etc/default/sysstat`. Source: sysstat README, Red Hat solution, thomas-krenn.
- **Cron or systemd**: RHEL 4-7 use `/etc/cron.d/sysstat`; RHEL 8 and 9 use systemd timers; recent sysstat versions use systemd instead of cron. Source: Red Hat solution, sysstat README.
- **Files**: `/var/log/sa/` on RHEL/CentOS, `/var/log/sysstat/` on Debian. `saNN` files are binary, `sarNN` files are text; NN is the day of the month (newer sysstat can also write `saYYYYMMDD`). Retention is set by `HISTORY`: Red Hat says it defaults to 28 days, while the older thomas-krenn example keeps a week (maximum 28). Check the actual retention on the customer host. Source: Red Hat solution, thomas-krenn, `sar(1)`.
- **Reading history**: `sar -f <file>` reads a saved file; `-s`/`-e` (hh:mm:ss, 24-hour) select the window, and **without them the report defaults to 08:00:00-18:00:00**, so an overnight incident is silently cut off. Source: `sar(1)`, `sadf(1)`.
- **USE method**: for each resource, check utilization, saturation and errors. Source: Gregg checklist.
- **SAR flags that answer USE** (from the Gregg checklist):
  - CPU: utilization `sar -u` (all fields except `%idle` and `%iowait`); saturation `sar -q` `runq-sz`.
  - Memory: utilization `sar -r` `%memused`; saturation `sar -B` `pgscank`+`pgscand` and `sar -W`; the OOM killer shows in `dmesg`.
  - Disk: utilization `sar -d` `%util`; saturation `sar -d` high `await` or queue length above 1.
  - Network: utilization `sar -n DEV`; errors and drops `sar -n EDEV` (`rxerr/s`, `txerr/s`).
- **Column meanings** (`sar(1)`): `%iowait` is CPU idle time while a disk I/O request was outstanding; `%steal` is involuntary wait while the hypervisor served another virtual CPU; `runq-sz` is tasks running or waiting for CPU; `blocked` is tasks waiting for I/O; `ldavg-*` count runnable tasks plus uninterruptible (D) sleepers; `kbavail` is memory available for new applications without swapping; `pswpin/s`/`pswpout/s` are swap pages in/out; `pgscand/s` is direct page scanning which stalls the process; `majflt/s` is faults that needed a page loaded from disk; `await` is average I/O time including queue time; `aqu-sz` is average queue length; `%util` is the share of time requests were issued to the device.
- **Time format**: setting `S_TIME_FORMAT=ISO` makes `sar` ignore the locale for the header date and use ISO 8601 timestamps (`sar(1)`). `sadf -t` prints the original local time of the machine that created the file, `-T` the local time of the machine running `sadf`, and the default is UTC (`sadf(1)`). Locale-dependent 12-hour AM/PM output and `LC_ALL=C` are `[unverified — confirm]`; `analyse_sar.py` handles AM/PM input.
- **Time zones**: SAR times are the customer host's clock as recorded by the collector; the ErrorLog uses MarkLogic's timestamps. Confirm both offsets before correlating `[unverified — confirm]`.
- **Baseline**: alert thresholds only mean something against "normal patterns of performance" for that workload, so compare an incident window with a quiet window from the same host. Source: MarkLogic Monitoring guidance on a performance baseline.
- **What SAR cannot show**: per-process attribution (use `pidstat`, `top`, `pmap`; Gregg lists these for per-process data), stalls shorter than the sample interval (it reports interval averages), and "abnormal for this system" without a baseline.
- **MarkLogic side**: Monitoring History charts CPU, I/O, memory, network and database resources per host; `mlstat` (archived community tool) combines MarkLogic stats (ingest, saves, merges, stand counts, caches) with `iostat`/`vmstat`/`pmap`.

## Standard procedures

1. Run `python3 scripts/analyse_sar.py <files or dirs> --out <dir>` on the customer's `sar -A` text output (security incident gate applies first; see `security-vulnerability-handling.md`). It writes `SUMMARY.md`, `findings.json` and per-host CSV series. A binary `sa##` file can be converted on a host with sysstat installed: `LC_ALL=C S_TIME_FORMAT=ISO sar -A -f /var/log/sa/saDD > saDD.txt`. If the file is binary from another sysstat version, ask for text output instead (`sadf -c` converts old formats only; the file must come from a compatible sar).
2. Confirm coverage: the file spans the incident window (check `-s`/`-e` were not left at their defaults) and contains the sections the rules need: `-u`, `-q`, `-r`, `-S`/`-W`, `-B`, `-d`, `-n DEV,EDEV`. Missing sections mean the matching rule cannot fire, not that the resource is healthy.
3. Align timestamps with the ErrorLog timeline: establish the host's time zone and any AM/PM or date-order ambiguity, then map the incident start/end to SAR local time.
4. Read the findings likely-cause first. Severity 0 rules (iowait, disk, swap, memory, reclaim) come before severity 1 (CPU, run queue, steal, faults, network).
5. Compare with a quiet window from the same host (a prior day, same hour). A value that is also present when the system is healthy is not a cause.
6. Hand over to MarkLogic-side checks for the same window: Monitoring History and `xdmp:host-status()` (`monitoring.md`), merges and forest status (`databases-forests.md`), cache, huge pages and swap configuration (`memory-and-os.md`), query and app behaviour (`performance-tuning.md`).
7. Look at the other nodes: repeat for every d-node and e-node involved, not just the host the customer named.
8. If the data is too coarse or missing, ask for more (`performance-data-requests.md` has the customer-ready request text). Typical asks: a 1-minute interval sample during a reproduction, `iostat -x`, `vmstat`, `mpstat`, `pidstat`.

## Findings produced by analyse_sar.py

A finding needs `--min-samples` consecutive samples over the threshold (default 2). Thresholds are generic starting points: an SSD and a spinning disk have very different normal `await`, so judge against the baseline.

| Rule | Threshold | Meaning | First MarkLogic-side check |
| --- | --- | --- | --- |
| cpu_iowait | > 20 % iowait | CPUs idle while waiting on disk I/O | Merges and reindexing in forest status; Monitoring History disk charts |
| disk_await | > 50 ms await | Disk requests queue and complete slowly | Merge activity and forest placement on that device; compare with a quiet window |
| disk_util | > 80 % util | Device close to saturation | Which forests live on the device; merges, backup, restore running |
| swap_io | > 1 pages/s | Memory pressure: pages moved to/from swap | Group cache sizes vs host RAM; huge pages; `memory-process-swap-size` in host status |
| mem_available | < 10 % avail | Little memory available to the OS | Group caches plus range indexes against RAM (`memory-and-os.md`) |
| direct_reclaim | > 1 pgscand/s | Processes reclaiming memory directly (stalls) | Same as swap_io; check ErrorLog for slow-request and memory messages |
| cpu_busy | > 90 % user+sys | CPU saturated | Expensive queries in Monitoring History; app server and task server load |
| run_queue | > 2 x CPUs | More runnable tasks than CPUs can serve | Concurrent request and thread counts; see `performance-tuning.md` |
| cpu_steal | > 5 % steal | Hypervisor taking CPU (noisy neighbour, throttling) | Not a MarkLogic problem: raise with the customer's virtualization or cloud team |
| major_faults | > 100 majflt/s | Pages read from disk on demand | Range-index page-in and cache sizing (`memory-and-os.md`) |
| net_errors | > 0 errors+drops/s | Network interface errors or drops | XDQP timeouts and host-to-host messages in ErrorLog |

## Common mistakes & symptoms

| Mistake | Symptom seen by customer | How to confirm | Fix / best practice | Source |
| --- | --- | --- | --- | --- |
| Reading `%iowait` or `%util` alone as "slow disk" | Disk blamed and replaced, slowness remains | Check `await` and `aqu-sz` in `sar -d` for the same samples; `%util` is only the share of time requests were issued | Judge saturation by `await` and queue length (Gregg: queue above 1 or high `await`) | <https://brendangregg.com/USEmethod/use-linux.html> and <https://man7.org/linux/man-pages/man1/sar.1.html> |
| Ignoring `%steal` on virtual machines | Query times vary with no MarkLogic cause; CPU looks idle or moderate | `%steal` in `sar -u` over the incident window | Take it to the hypervisor or cloud owner; do not tune MarkLogic for it | <https://man7.org/linux/man-pages/man1/sar.1.html> |
| High run queue treated as proof of CPU shortage | Customer adds CPUs, no improvement | `runq-sz` against CPU count, plus `blocked` and `%iowait`; `ldavg` also counts uninterruptible (D) tasks | Check `blocked` and `%iowait` before concluding CPU; D-state waiters inflate load average | <https://man7.org/linux/man-pages/man1/sar.1.html> |
| Swap called harmless because `%memused` looks fine | Intermittent stalls and timeouts despite "enough" memory | `kbavail`, `pswpin/s`/`pswpout/s` (`-W`), `pgscand/s` (`-B`) | Use available memory and paging activity, not `%memused`; `-B` and `-W` are the Gregg memory saturation flags | <https://brendangregg.com/USEmethod/use-linux.html> and <https://man7.org/linux/man-pages/man1/sar.1.html> |
| SAR not collecting, or interval too coarse | No data for the incident, or a spike lost in a 10-minute average | `ls /var/log/sa` or `/var/log/sysstat`; sample spacing in the file | Enable sysstat; shorten the interval (default 10 minutes, as low as 1 second) for the reproduction | <https://sources.debian.org/src/sysstat/12.7.5-2/README.md> and <https://access.redhat.com/solutions/276533> |
| Comparing SAR (host local time, maybe 12-hour) with ErrorLog without aligning time zone | Findings appear hours off the incident | Compare a known event in both sources; check `sadf -t` vs `-T` and the header date | Set `S_TIME_FORMAT=ISO`, record the host time zone, align before correlating | <https://man7.org/linux/man-pages/man1/sadf.1.html> and <https://man7.org/linux/man-pages/man1/sar.1.html> |
| Report left at default time window | Report starts at 08:00 and stops at 18:00; night incident missing | Check the first and last timestamps in the output | Pass `-s` and `-e` with `-f` to cover the incident | <https://man7.org/linux/man-pages/man1/sar.1.html> |
| Reading the "Average:" lines for an incident window | A 20-minute spike disappears into a day-long average | Per-sample rows for the window, not the footer | Use per-sample rows (what `analyse_sar.py` does); `sar` also takes `-x` for min and max | [unverified — confirm] |
| Analysing one node when the issue is on a different d-node or e-node | Clean SAR from the wrong host, no cause found | Which host logged the slow requests or XDQP errors in ErrorLog | Collect and analyse SAR from every host in the request path | [unverified — confirm] |
| Sysstat binary file from a different sysstat version cannot be read elsewhere | `sar -f` errors on the engineer's machine | Compare versions on both hosts | Ask for text output made on the customer host; `sadf -c` only converts old formats (9.1.6 and later) | <https://man7.org/linux/man-pages/man1/sadf.1.html> |
| MarkLogic's own merge activity mistaken for an external disk problem | High `%iowait` and `await` on forest devices during merges | Merge activity in the ErrorLog or host status for the same window; mlstat treats high `%nice` as merge time | Correlate the disk spike with merges; background I/O for merge, backup and restore is capped per host (group setting) | <https://github.com/marklogic-community/mlstat> and <https://docs.marklogic.com/admin-help/group> |

## Sources

- <https://brendangregg.com/USEmethod/use-linux.html> — USE method; SAR flags for CPU, memory, disk and network utilization/saturation/errors
- <https://man7.org/linux/man-pages/man1/sar.1.html> — `sar(1)`: column meanings, `-s`/`-e`/`-f`, default 08:00-18:00 window, `S_TIME_FORMAT`, file names
- <https://man7.org/linux/man-pages/man1/sadf.1.html> — `sadf(1)`: `-t`/`-T`/`-U` time handling, `-c` conversion, version compatibility
- <https://sources.debian.org/src/sysstat/12.7.5-2/README.md> — sa1/sa2/sadc, cron or systemd, 10-minute default, enabling collection
- <https://access.redhat.com/solutions/276533> — RHEL collection (cron and systemd timers), `/var/log/sa`, saNN vs sarNN, retention
- <https://www.thomas-krenn.com/en/wiki/Collect_and_report_Linux_System_Activity_Information_with_sar> — enabling collection, Debian `/var/log/sysstat`, `-f` for history (2013 article, old sysstat)
- <https://github.com/marklogic-community/mlstat> — mlstat (archived): system plus MarkLogic stats, `%nice` and merges, blocked/iowait
- <https://docs.progress.com/bundle/marklogic-server-monitor-12/page/topics/marklogic-server-monitoring-history/view-monitoring-history.html> — Monitoring History charts
- <https://docs.progress.com/bundle/marklogic-server-monitor-12/page/topics/introduction/guidelines-for-configuring-your-monitoring-tools/establish-a-performance-baseline.html> — baseline of normal performance
- <https://docs.marklogic.com/admin-help/group> — background I/O limit covers merge, backup, restore

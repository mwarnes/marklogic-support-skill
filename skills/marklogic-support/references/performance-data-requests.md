# Customer data requests for performance tickets

Use these blocks to build the "Questions to ask the customer" and `Required-Diagnostics.md` entries on performance tickets that have no host-level data. Copy a block, fill the `<...>` parts and paste it into Salesforce. Each customer block is numbered, says why each item is needed and is plain language. Apply the security incident gate (`security-vulnerability-handling.md`) before asking for any file from a customer who mentioned a security incident. How to read what comes back: `sar-analysis.md`. Cloud signals are requested only from cloud-hosted customers, never on-prem (see the last section). Commands are checked against the man7.org pages for `sar(1)`, `iostat(1)`, `vmstat(8)`, `mpstat(1)`, `pidstat(1)`, `dmesg(1)`, `journalctl(1)`, `perf-record(1)`, `perf-report(1)`, `perf-script(1)`, `perf-top(1)`, `date(1)`; anything not on a page read is marked `[unverified — confirm]`.

## SAR export

Customer request:

> To see what the servers were doing during the slowdown, please send the system activity (SAR) history for **each** MarkLogic host involved, including the hosts that run queries (evaluation nodes) and the hosts that store data (data nodes). The incident was on `<date>` at `<time>` (`<time zone of the host>`); please cover from `<start margin>` to `<end margin>`.
>
> 1. Find the daily file for that date. It is named `saDD` (DD is the day of the month) in `/var/log/sa/` on Red Hat-family systems or `/var/log/sysstat/` on Debian-family systems. We need this because it holds the recorded CPU, memory, disk and network figures.
> 2. Convert it to text: `LC_ALL=C S_TIME_FORMAT=ISO sar -A -f /var/log/sa/saDD > sar-<host>-<date>.txt` (use `/var/log/sysstat/saDD` on Debian-family). This gives us every report in one readable file with unambiguous dates.
> 3. If the problem was outside the default report hours, add a time window so the report is not cut off: `... sar -A -f <file> -s HH:MM:SS -e HH:MM:SS > sar-<host>-<date>.txt`. Without it the report covers only 08:00 to 18:00.
> 4. Send the text files and also the original `saDD` files. The originals only open on a system with a compatible sysstat version and architecture, but they let us re-run the report if something is missing.
> 5. Tell us each host's time zone and the exact time the problem started and ended, so we can line the SAR times up with the MarkLogic logs.

Engineer notes:
- Run `scripts/analyse_sar.py` on the text files (`sar-analysis.md`, procedure 1). Binary files convert only on a host with a compatible sysstat; `sadf -c` converts older formats only.
- Retention is set by `HISTORY` (Red Hat's example in `/etc/sysconfig/sysstat` sets 28 days; the page does not state a default); check the actual retention and ask early on older incidents.
- Verified: file locations and retention (Red Hat solution 276533, thomas-krenn, `sar(1)`); `-f`, `-s`, `-e` defaults and `S_TIME_FORMAT=ISO` (`sar(1)`). `LC_ALL=C` effect is `[unverified — confirm]`.

## If SAR is not running

Customer request:

> Your hosts do not appear to keep system activity history, which is the data we need to explain the slowdown. Please do the following on each MarkLogic host.
>
> Note: installing and enabling sysstat changes the host. Follow your change process or ask your administrator before doing this.
>
> 1. Install sysstat: `sudo dnf install sysstat` (Red Hat 8/9; `yum` on Red Hat 7) or `sudo apt-get install sysstat` (Debian-family). It records CPU, memory, disk and network usage over time.
> 2. Turn on collection: `sudo systemctl enable --now sysstat` (Red Hat-family; on Red Hat 7 use `systemctl enable sysstat` then `systemctl start sysstat`). On Ubuntu run `sudo dpkg-reconfigure sysstat` and answer "Yes". Without this nothing is recorded.
> 3. By default it records one sample every 10 minutes. While the problem can still be reproduced, please shorten this to 1 minute (tell us your operating system and version and we will send the exact steps), because 10-minute averages hide short stalls.
> 4. While the problem is happening, run this once per host and send the file: `LC_ALL=C S_TIME_FORMAT=ISO sar -u -q -r -S -W -B -d -n DEV,EDEV 5 120 > sar-live-<host>.txt`. It takes 10 minutes and records CPU, run queue, memory, swap space and swapping, paging, disks and network every 5 seconds.

Engineer notes:
- Interval on Red Hat 7: edit `/etc/cron.d/sysstat`, change `*/10` to `*/1` (Red Hat solution 276533). On Red Hat 8/9 timers are used; the timer names (`sysstat-collect.timer`) and the override steps are `[unverified — confirm]` (the Red Hat article points to solution 5115491, not read). Debian-family: `ENABLED` in `/etc/default/sysstat`; interval setting `[unverified — confirm]`.
- A 5-second 10-minute capture during the incident beats a day of 10-minute averages. Flags checked against `sar(1)`: `-u`, `-q`, `-r`, `-S` (swap space used), `-W` (swapping activity, `pswpin/s`/`pswpout/s`, which `analyse_sar.py`'s swap rule needs), `-B`, `-d`, `-n DEV,EDEV`, then interval and count.
- Collection only helps future incidents; for the current one use this capture or the host-metrics block.

## Host metrics (iostat, vmstat, mpstat, pidstat)

Customer request:

> Please run these four commands at the same time on each MarkLogic host while the problem is happening. Each runs for 10 minutes (120 samples, 5 seconds apart) and writes to its own file. Send all four files per host.
>
> 1. `iostat -xz 5 120 > iostat-<host>.txt` shows how busy each disk is and how long requests wait (hidden if a disk is idle). It tells us whether storage is the bottleneck.
> 2. `vmstat -t 5 120 > vmstat-<host>.txt` shows waiting processes, swapping and CPU waiting for disk, with a time on each line. It tells us whether the server is short of CPU or memory.
> 3. `mpstat -P ALL 5 120 > mpstat-<host>.txt` shows each CPU separately. It tells us whether one CPU is overloaded while others are idle.
> 4. `pidstat -u -r -d 5 120 > pidstat-<host>.txt` shows which processes use CPU, memory and disk (idle processes are left out). It tells us whether MarkLogic or something else is responsible.
>
> Please also tell us the time you started the commands and the host's time zone.

Engineer notes:
- Drop the first report of `iostat` and `vmstat`: it is the average since boot (`iostat(1)`, `vmstat(8)`). `mpstat` and `pidstat` also report an average at the end.
- `iostat`: `await` (ms, includes queueing), `aqu-sz`, `%util` (can mislead on SSDs and RAID). `vmstat`: `r` runnable, `b` blocked on I/O, `si`/`so` swap, `wa` I/O wait, `st` stolen. `mpstat`: `%iowait`, `%steal`.
- A `pidstat` line for the MarkLogic process attributes the load. With no task selected, `pidstat` reports only active tasks (non-zero statistics); an explicit `-p ALL` reports every task, so it is deliberately omitted (`pidstat(1)`). Adding `-t` (threads) is `[unverified — confirm]`; the man page does not say how it combines with the default.
- `pidstat -d` needs a 2.6.20+ kernel (`pidstat(1)`).
- Compare against a quiet window from the same host (`sar-analysis.md`).

## Kernel and OOM messages

Customer request:

> To check whether the operating system stopped a process or hit disk errors, please send the following for each MarkLogic host for `<date>` `<start>` to `<end>`.
>
> 1. `sudo dmesg -T | grep -i -E "out of memory|killed process|hung task|i/o error" > dmesg-<host>.txt`. This shows whether the system ran out of memory and ended a process, or reported disk problems. (Root access may be needed.)
> 2. The same period from the system log, only the lines for the incident date (`<Mon DD>`, for example `Oct 20`; the log's date format may differ, so check the first line of the file): `sudo zgrep -h -i -E "out of memory|killed process|hung task|i/o error" /var/log/messages* | grep "<Mon DD>" > messages-<host>.txt` (`zgrep` reads both plain and compressed rotated files `[unverified — confirm]`). If that returns nothing, send the lines from `/var/log/messages` around `<incident time>` instead. On systems without that file, use `sudo journalctl -k --since "<YYYY-MM-DD HH:MM:SS>" --until "<YYYY-MM-DD HH:MM:SS>" > journal-<host>.txt`. Older messages roll off the live kernel buffer, so this log is the better record for earlier incidents.
> 3. If a MarkLogic process stopped or restarted, tell us the time.

Engineer notes:
- Why: shows whether the OOM killer or storage errors were involved. Cross-check times with the Log mode `TIMELINE.md`.
- `dmesg -T` timestamps can be inaccurate and are not updated after suspend/resume (`dmesg(1)`); it can fail with permission denied when `dmesg_restrict` is set. `journalctl -k` shows only the current boot unless a boot is chosen, so after a reboot the incident may be in an earlier boot (how to select one: `[unverified — confirm]`).
- The kernel message strings in the filter (`Out of memory`, `Killed process`, `hung task`, `I/O error`) were not checked against a kernel documentation page `[unverified — confirm]`; widen the filter if it returns nothing.

## Stack samples: pstack movie

Use for a hang, an unresponsive period, or a query that behaves unexpectedly. Source: KB 000266816 (https://community.progress.com/s/article/creating-a-pstack-movie-for-support, maintainer-supplied copy).

Customer request:

> 1. We need to see what the MarkLogic server threads are doing over a short time while the problem is happening. A script from Support records a stack trace of the MarkLogic process every 3 seconds and zips the result.
> 2. Someone with root access on the MarkLogic host runs these steps. First install the tools if they are missing: `yum -y install pstack sysstat psutils gdb` (RHEL/CentOS).
> 3. Copy the attached `pstack.sh` to the host and make it executable: `chmod +x pstack.sh`.
> 4. While the problem is happening, run it for 60 seconds: `sudo ./pstack.sh 60`.
> 5. It writes a zip file in `/tmp/` named after the server time and date (for example `/tmp/101530-10-21-2026.zip`). Please attach it to the case, with the host name and the time the problem happened.
> 6. Each sample pauses the MarkLogic process while it records the threads, which has a performance impact. Please agree a time with us first on a production system, and run it only while the problem is happening.
> 7. MarkLogic older than 11.3.1, or an 11.3.x build not based on RHEL 9: open `pstack.sh` and replace the line `/etc/MarkLogic/proc-util.sh pstack >> /tmp/$TSTAMP/pstack.log` with `service MarkLogic pstack >> /tmp/$TSTAMP/pstack.log` (the script contains this as a comment).

Engineer notes:
- The script is `<skill-dir>/assets/support-scripts/pstack.sh`, vendored verbatim from the KB article; give the customer that file.
- The article text says 5-second samples but the script uses 3 (`INTERVAL=3`).
- The article's `ml-support-dump.sh` listing is identical to `pstack.sh`, so ask for OS-level data with the SAR and host-metrics requests.
- pstack pauses the process; for sustained high CPU prefer the perf request below.
- Apply the security incident gate before asking for the file.
- `pstack.sh` runs `zip -9 -r ...`, but the article's prerequisite line does not install `zip`. If `zip` is missing the script still leaves the `/tmp/<HHMMSS-MM-DD-YYYY>` directory; ask the customer to send that directory instead (for example archived with `tar`) `[unverified — confirm]`.
- The zip contains `pstack.log`, a dated series of stack traces. Analysis tooling for it is planned (phase 2).

## CPU profile: perf

Use when CPU is high or when pausing the process is a concern. Source: KB 000268341 (https://community.progress.com/s/article/using-perf-to-understand-performance, maintainer-supplied copy). perf samples the process instead of pausing it, so it is lighter than pstack.

Customer request:

> 1. We need a statistical profile of where the CPU time goes while the CPU is high.
> 2. On the busy MarkLogic host, as root (or with sudo), install perf if it is missing: `yum install perf` (RHEL/CentOS).
> 3. While the CPU is high, run all of steps 3 to 5 as root (or prefix each perf command with `sudo`), on that same host. On a production system, please agree a time with us first. `cd /tmp` then `perf record -F 99 -ag -- sleep 60`. It takes about a minute and writes `perf.data` in the current directory.
> 4. Create the report: `perf report --header -I --stdio > $(hostname -s).$(date -Is).report`
> 5. Create the script output: `perf script > $(hostname -s).$(date -Is).script`. It can be large but compresses well, so please zip it.
> 6. Please attach the `.report` file and the zipped `.script` file to the case, with the host name and the time the CPU was high.

Engineer notes:
- All steps must be run on the same MarkLogic host. `perf top` gives a quick live view of what is using the CPU.
- Verified (`perf-record(1)`): `-F 99` profiles at 99 samples per second; `-a` is system-wide collection from all CPUs; `-g` records call graphs; `-- sleep 60` records while the command runs; the description says the profile is written "into perf.data". `perf-report(1)`: `--header` "Show header information in the perf.data file. Currently only --stdio output supports this feature."; `-I`/`--show-info` "Display extended information about the perf.data file... currently includes: cpu and numa topology of the host system."; `--stdio` selects the plain-text interface. What else the header contains and how large the output is `[unverified — confirm]`. `perf-script(1)` prints the recorded trace; `perf-top(1)` shows a real-time profile. `date -Is` is ISO 8601 to seconds (`date(1)`).
- Needing root or a relaxed `perf_event_paranoid` is `[unverified — confirm]`; the `perf-record(1)` page does not mention it.
- Whether a `sudo perf record` followed by a plain `perf report` can fail on root-owned `perf.data` is `[unverified — confirm]`; hence the request to run steps 3 to 5 all as root.
- Apply the security incident gate before asking for the files.
- `date -Is` puts colons in the file names (fine on Linux; rename if copied to Windows).
- The files hold function names and counts, not document content `[unverified — confirm]`.
- Analysis tooling is planned (phase 2).

## Memory growth: pmap

Use only for runaway memory.

Customer request:

> Please agree a time with us first. Take a memory map of the MarkLogic process at the start and at the end of the growth.
>
> 1. Find the MarkLogic process id: `pgrep -x MarkLogic` `[unverified — confirm process name]`. We need it to target the right process.
> 2. Memory map: `pmap -x <pid> > pmap-<host>-<n>.txt`, once at the start and once at the end. This shows how the process's memory is divided.

Engineer notes:
- `pmap -x` is the documented "extended format" (`pmap(1)`); the man page does not describe the columns. Compare the start and end maps for growth.
- On some Linux systems `pmap` on the MarkLogic process needs root (mlstat README, not re-checked). Community scripts such as `mlstat` loop `pstack`/`pmap`/`iostat`/`vmstat`; they are not official guidance.
- If the customer is reluctant, ask for the SAR/host-metrics data first.

## Cloud-hosted customers

Request this block **only** when the customer runs MarkLogic on a cloud provider (for example AWS), never for on-prem hosts. AWS items below use metric names from the AWS EBS and EC2 CloudWatch pages (`using_cloudwatch_ebs.html`, `viewing_metrics_with_cloudwatch.html`, `burstable-credits-baseline-concepts.html`, `ebs-volume-types.html`). For other providers keep the questions the same and ask for the equivalent figures `[unverified — confirm]`.

Customer request:

> Because the servers run in the cloud, the provider can limit disk and CPU speed independently of the server itself. Please send the following for `<date>` `<start>` to `<end>`.
>
> 1. The instance type and size of each MarkLogic host (for example `m5.2xlarge`). It sets the CPU, memory, and storage-bandwidth limits.
> 2. For each data volume: volume type, size, and provisioned IOPS and throughput (for example `gp3`, 1 TiB, 6000 IOPS, 250 MiB/s). The volume has its own speed limits.
> 3. For AWS, a CloudWatch graph or export (1-minute period) for each data volume over the window: `VolumeReadOps`, `VolumeWriteOps`, `VolumeReadBytes`, `VolumeWriteBytes`, `VolumeQueueLength`, and `BurstBalance` if the volume is `gp2`, `st1` or `sc1`. Where available, `VolumeIOPSExceededCheck` and `VolumeThroughputExceededCheck` (only for volumes on Nitro instances, AWS's current generation of EC2 hardware; if you are unsure, skip them). These show whether the volume hit its limit.
> 4. For AWS instances, `InstanceEBSIOPSExceededCheck` and `InstanceEBSThroughputExceededCheck` (Nitro instances only), and for T-series burstable instances `CPUCreditBalance` and, in Unlimited mode, `CPUSurplusCreditBalance`. A drained credit balance slows the CPU.
> 5. Tell us whether the SAR or `mpstat` output shows a non-zero `%steal` (the share of time the host's CPU was given to another virtual machine); if you are not sure, send the files and we will check.

Engineer notes:
- `%steal` is involuntary wait while the hypervisor serves another virtual CPU (`sar(1)`, `mpstat(1)`); `vmstat` shows it as `st`. Steal above a few percent means the hypervisor is taking CPU (the "few percent" threshold is engineering judgment, `[unverified — confirm]`).
- Throttled volume: high `await` with `%util` and IOPS pinned at the volume limit, `BurstBalance` near 0, or the exceeded-check metrics at 1. Volume maximums: `gp3` 80,000 IOPS / 2,000 MiB/s, `gp2` 16,000 / 250 MiB/s (128-250 depending on volume size), `io1` 64,000 / 1,000 MiB/s, `st1` 500 / 500 MiB/s, `sc1` 250 / 250 MiB/s (`ebs-volume-types.html`, re-read 2026-10-20; `io1` 1,000 MiB/s needs 64,000 IOPS and a Nitro instance; AWS may change these).
- The `*ExceededCheck` metrics are not supported on Multi-Attach volumes and cannot be used in Outposts, Local Zones or Wavelength Zones (`using_cloudwatch_ebs.html`); if the customer uses these, ask for the other metrics only.
- EC2 CloudWatch volume metrics are 1-minute; instance metrics are 5-minute by default and CPU credit metrics are 5-minute only. `CPUUtilization` from CloudWatch can differ from OS tools.
- `sar -d` shows what the guest saw, CloudWatch what AWS delivered; use both.

# Customer data requests for performance tickets

Use these blocks to build the "Questions to ask the customer" and `Required-Diagnostics.md` entries on performance tickets that have no host-level data. Copy a block, fill the `<...>` parts and paste it into Salesforce. Each customer block is numbered, says why each item is needed and is plain language. Apply the security incident gate (`security-vulnerability-handling.md`) before asking for any file from a customer who mentioned a security incident. How to read what comes back: `sar-analysis.md`. Cloud signals are requested only from cloud-hosted customers, never on-prem (see the last section). Commands are checked against the man7.org pages for `sar(1)`, `iostat(1)`, `vmstat(8)`, `mpstat(1)`, `pidstat(1)`, `dmesg(1)`, `journalctl(1)`; anything not on a page read is marked `[unverified — confirm]`.

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
- Default retention is 28 days on Red Hat (`HISTORY` in `/etc/sysconfig/sysstat`); ask early on older incidents.
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
> 4. While the problem is happening, run this once per host and send the file: `sar -u -q -r -S -W -B -d -n DEV,EDEV 5 120 > sar-live-<host>.txt`. It takes 10 minutes and records CPU, run queue, memory, swap space and swapping, paging, disks and network every 5 seconds.

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

## Hangs: thread dumps and pmap

Use only for hangs or runaway memory. No official MarkLogic documentation or KB article describing process-level stack collection could be fetched (help.marklogic.com pages do not load; `dbg:stack` is a request-level function, not a process dump). The wording below is therefore general Linux practice, `[unverified — confirm]` with MarkLogic Support or a current KB article before sending.

Customer request:

> Because the server is hanging, we need a snapshot of what its threads are doing. Please agree a time with us first, and take these only while the hang is happening.
>
> 1. Find the MarkLogic process id: `pgrep -x MarkLogic` `[unverified — confirm process name]`. We need it to target the right process.
> 2. Memory map: `pmap -x <pid> > pmap-<host>-<n>.txt`, once at the start and once at the end. This shows how the process's memory is divided.
> 3. Thread stacks, three times about 10 seconds apart: `pstack <pid> > pstack-<host>-<n>.txt`, or if `pstack` is not installed `gdb -p <pid> -batch -ex "thread apply all bt" > stacks-<host>-<n>.txt`. Three samples show whether the threads are stuck in the same place.
>
> Please note that attaching a debugger to a production process can pause it briefly. Run this only at the agreed time, during the hang.

Engineer notes:
- `pmap -x` is the documented "extended format" (`pmap(1)`); the man page does not describe the columns. Compare the start and end maps for growth.
- Community scripts (for example a MarkLogic pstack gist and `mlstat`) loop `pstack`/`pmap`/`iostat`/`vmstat`; they are not official guidance. On some Linux systems `pmap` on the MarkLogic process needs root (mlstat README, not re-checked).
- The `gdb -batch -ex` form and the pause risk are `[unverified — confirm]`. If the customer is reluctant, ask for the three-sample SAR/host-metrics data first.

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

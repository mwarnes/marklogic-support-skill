# MarkLogic memory & OS configuration

## Concepts

- **Group-level caches**: Memory allocated per host at startup for list cache (termlists), compressed tree cache (on-disk fragments), expanded tree cache (in-memory fragments), and triple cache. Cache sizes are configured per-group → all hosts in the group allocate the same amounts. Total cache memory across all groups must fit in host RAM alongside range indexes and OS overhead.

- **Cache sizing methods**: Groups support automatic (MarkLogic calculates cache sizes), enode (optimized for evaluation nodes), dnode (optimized for data nodes), or manual sizing. With automatic/enode/dnode, manual settings are ignored.

- **Range indexes**: Memory-mapped per forest, managed by OS virtual memory. MarkLogic allocates space and loads the range index files (on-demand or via preload), treating them as in-memory arrays. Paging out previously loaded data slows server operation.

- **Memory allocation timing**: Group caches allocated at server startup based on config file values. Range indexes mapped when forests mount. Adding a differently-sized host to an existing group inherits the group's cache settings, potentially causing memory overcommit.

- **Linux Huge Pages**: 2MB memory blocks (vs normal 4KB pages) that are locked in memory and cannot be paged out. Provides more efficient memory access and prevents paging of MarkLogic data structures. Recommended at 3/8 of physical RAM size.

- **Transparent Huge Pages (THP)**: Kernel feature that automatically promotes regular pages to huge pages. MarkLogic recommends disabling THP due to performance inconsistencies and potential for memory fragmentation.

- **Swap space**: Temporary memory store used when physical RAM is exhausted. When MarkLogic uses swap, performance degrades severely. Allows graceful degradation instead of OOM kills.

- **Resource ratios**: General guideline of 2 vCPUs and 8GB RAM per forest that is actively updated and queried. Maximum recommended forest size ~512GB. These ratios may need adjustment based on indexing configuration and workload.

## Standard procedures

1. **Set Linux Huge Pages**: Configure `vm.nr_hugepages` in `/etc/sysctl.conf` to 3/8 of physical RAM (in 2MB blocks). Check with `cat /proc/meminfo | grep Huge` and restart MarkLogic after changes.

2. **Disable Transparent Huge Pages**: Add `echo never > /sys/kernel/mm/transparent_hugepage/enabled` to startup scripts. Verify with `cat /sys/kernel/mm/transparent_hugepage/enabled` showing `[never]`.

3. **Configure swap space**:
   - If RAM ≤ 32GB: set swap = physical RAM size
   - If RAM > 32GB: set swap = 32GB
   - Create with `fallocate -l [size] /swapfile` and enable with `swapon`

4. **Set I/O scheduler**: On Red Hat Linux, configure deadline I/O scheduler in `/etc/default/grub` with `elevator=deadline` kernel parameter. Reboot to apply.

5. **Configure file descriptors**: Set `ulimit -n` for MarkLogic daemon user per installation guide requirements. Typically in `/etc/security/limits.conf` or systemd service files.

6. **Size group caches**: Calculate total cache memory (list + compressed tree + expanded tree + triple) to use ~1/3 to 1/2 of available RAM, leaving remainder for range indexes and OS. Monitor cache hit rates in `xdmp:host-status()`.

7. **Separate groups for different host sizes**: When adding hosts with different memory configurations, create separate groups with appropriately sized caches rather than using one group for all.

8. **Monitor memory usage**: Track cache hit ratios, swap usage (`swapon -s`), and range index page-in rates. Set up alerts for memory warnings in ErrorLog.txt.

## Common mistakes & symptoms

| Mistake | Symptom seen by customer | How to confirm | Fix / best practice | Source |
| --- | --- | --- | --- | --- |
| Group cache sizes summed exceed host RAM (esp. after adding a small host to a group of large ones) | Host OOM-killed, swap thrash, `XDMP-MEMCANCELED` | Compare group caches (list, compressed tree, expanded tree, triple) + range index footprint vs host RAM in Admin UI › Groups › Configure; `sysctl`/`free -g` | Size caches so total ≈ 1/3–1/2 RAM; separate groups for differently sized hosts | [unverified — confirm] |
| Huge pages not configured / THP enabled | Slow, erratic latency, `Linux Huge Pages` warning in ErrorLog at startup; memory pressure escalates to a stall/OOM faster because MarkLogic's memory structures fall back to ordinary swappable pages | ErrorLog "Linux Huge Pages: detected 0, recommended N"; `cat /sys/kernel/mm/transparent_hugepage/enabled` | Set `vm.nr_hugepages` per ErrorLog recommendation (≈3/8 of physical RAM); disable THP | <https://help.marklogic.com/Knowledgebase/Article/View/16/0/linux-huge-pages> |
| No/too little swap | Process killed instead of degrading; `memory-process-swap-size` in Host Status far below expected sizing | `swapon -s`; Host Status `memory-process-swap-size` | Swap ≈ (physical RAM − Huge Pages size), capped at 32 GB | <https://help.marklogic.com/knowledgebase/article/View/21/19/swap-space-requirements> |
| Too many forests for host RAM/vCPU | Performance degradation when guidelines greatly exceeded | Count forests per host vs 2 vCPU + 8 GB per forest rule | Reduce forests or add hosts | <https://docs.progress.com/bundle/marklogic-server-configure-scal-avail-perf-12/page/topics/scalability.html> |
| Expanded tree cache too small for large docs | `XDMP-EXPNTREECACHEFULL` | Error text; group setting | Raise expanded tree cache size / partitions; reduce result size | [unverified — confirm] |
| List cache too small | `XDMP-LISTCACHEFULL`, slow queries | Error text; cache hit rates in `xdmp:host-status` / Monitoring | Raise list cache size; check index selectivity | <https://docs.marklogic.com/admin-help/group> |
| Low `ulimit -n` | `XDMP-TOOMANYOPENFILES` / forest mount failures | `ulimit -n` for the daemon user | Set per install guide | [unverified — confirm] |
| Wrong I/O scheduler on Red Hat Linux | Poor I/O performance, operations starve/never complete | `cat /sys/block/[device]/queue/scheduler` | Set deadline scheduler with kernel parameter (required on Red Hat Linux) | Inside MarkLogic p.119 |
| Mixed E-node and D-node cache settings | Cache thrash on D-nodes, wasted memory on E-nodes | Cache hit ratios, memory utilization per node role | Use automatic enode/dnode cache sizing or separate groups | [unverified — confirm] |

### Cache behavior notes

- **Cache memory allocation**: All group caches are allocated per host at startup, regardless of whether the host actually uses them (e.g., E-nodes get D-node caches if in a mixed group).

- **Per-group vs per-host**: List cache, compressed tree cache, expanded tree cache, and triple cache are per-group settings → every host in the group allocates these amounts. Range indexes are per-forest → memory usage scales with forest count.

- **Memory-mapped range indexes**: Range indexes use memory-mapped files, not cache allocations. OS manages loading/paging. Preload option forces immediate loading vs on-demand. **(v12)** Check if preload behavior changed from v11.

## Sources

- Inside MarkLogic Server (PDF) p.119 — Linux Huge Pages, swap space, deadline I/O scheduler recommendations
- <https://help.marklogic.com/Knowledgebase/Article/View/16/0/linux-huge-pages> — Linux Huge Pages and Transparent Huge Pages
- <https://help.marklogic.com/knowledgebase/article/View/21/19/swap-space-requirements> — Swap Space Requirements
- <https://docs.marklogic.com/admin-help/group> — cache sizing methods and configuration
- <https://docs.progress.com/bundle/marklogic-server-configure-scal-avail-perf-12/page/topics/scalability.html> — forest sizing guidelines (2 vCPU + 8GB per forest)
- <https://www.progress.com/blogs/scaling-memory-in-marklogic-server> — memory scaling strategies, E-node vs D-node considerations

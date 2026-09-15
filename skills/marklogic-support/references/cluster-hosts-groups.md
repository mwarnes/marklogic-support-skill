# MarkLogic clusters, hosts, and groups — management procedures

## Concepts

- **Cluster membership**: A MarkLogic cluster consists of multiple hosts running identical software, communicating via XDQP protocol on ports 7997-7999. All hosts must run the same platform and MarkLogic version for compatibility.

- **Host lifecycle**: Hosts join clusters by connecting to an existing cluster member during installation. To leave, a host must have no forests or app servers assigned and can only leave if it won't break quorum.

- **Groups and host assignment**: Groups contain configuration shared by member hosts (cache sizes, app servers, timeouts). Each host belongs to exactly one group. Moving hosts between groups applies the target group's configuration.

- **Quorum requirement**: Clusters require >50% of hosts online to maintain quorum and prevent split-brain scenarios. Even-numbered clusters (especially 2-node) are vulnerable to quorum loss when one host fails.

- **XDQP communication**: Inter-host communication uses XDQP (XML Data Query Protocol) on TCP ports 7997 (inter-cluster), 7998 (intra-cluster), and 7999 (group communication). Firewall issues cause hosts to appear offline.

- **Bootstrap and first host**: The first host installed becomes the bootstrap host and creates the Default group. Additional hosts join by providing the bootstrap host's address during installation.

- **Hostname dependency**: MarkLogic tracks hosts by hostname in `hosts.xml`. OS-level hostname changes without proper MarkLogic rename procedures cause rejoining failures.

- **Clock synchronization**: Cluster hosts require synchronized clocks (via NTP) to prevent authentication failures and replication lag. Clock skew causes digest auth problems and inconsistent timestamps.

- **Version compatibility**: During rolling upgrades, the cluster "effective version" remains at the lowest version until all hosts are upgraded. Features from newer versions remain unavailable.

- **Coupled clusters**: Multiple clusters can be coupled for database replication, requiring foreign bind ports and cross-cluster authentication setup.

## Standard procedures

1. **Join host to cluster**: Install MarkLogic → provide existing cluster member hostname → ensure ports 7997-7999 open → verify same version/license tier → host appears in Admin Interface
2. **Create group**: Admin Interface › Groups › Create → specify cache settings appropriate for hardware class → configure timeouts and schedulers
3. **Move host between groups**: Groups › [target group] › add host → host inherits new group's configuration including cache sizes and app server settings
4. **Leave cluster**: Ensure host has no forests assigned → no app servers depending on it → click "leave" button in host configuration (only visible when connected to that host)
5. **Rename host**: Use Admin Interface host rename procedure → do not change hostname at OS level without MarkLogic-aware rename → updates internal `hosts.xml`
6. **Couple clusters for replication**: Configure foreign bind ports → establish cross-cluster authentication → create database replication relationships
7. **NTP setup**: Configure NTP/chrony on all hosts → verify synchronization with `ntpq -p` or `chronyc sources` → monitor for clock skew warnings in ErrorLog
8. **Rolling upgrade**: Upgrade hosts one at a time → monitor "effective version" in Admin Interface › Clusters → complete all hosts to unlock new features
9. **Handle quorum loss**: Add hosts to restore >50% quorum → consider arbiter-style extra host for even-numbered clusters → investigate why hosts went offline

## Common mistakes & symptoms

| Mistake | Symptom seen by customer | How to confirm | Fix / best practice | Source |
| --- | --- | --- | --- | --- |
| Even number of hosts / 2-node cluster, one host down | Cluster loses quorum, all forests unmounted | Host count vs online hosts; ErrorLog "quorum" messages | Use ≥3 hosts (or arbiter-style extra host); >50% needed | <https://help.marklogic.com/Knowledgebase/Article/View/start-up-quorum-and-forest-level-failover> |
| XDQP ports blocked between hosts / firewall change | Hosts flap offline, `XDMP-HOSTOFFLINE`, XDQP timeouts | `nc -z host 7999` both directions; ErrorLog XDQP errors | Open 7997–7999 TCP bidirectionally between all hosts | Inside MarkLogic p.11 |
| Clock skew between hosts | Auth failures (digest), replication lag, odd timestamps | ErrorLog time warnings; `chronyc sources`/`ntpq -p` | Configure NTP on all hosts; monitor synchronization | <https://help.marklogic.com/Knowledgebase/Article/View/24/0/synchronizing-system-clocks-in-a-cluster> |
| Version mismatch during rolling upgrade held too long | "effective version" stuck, features unavailable | Admin UI › Clusters shows effective version vs individual host versions | Complete upgrade on all hosts to unlock new features | <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/clusters.html> |
| Removing a host that still owns forests | Forests offline, data unavailable | Forest host assignment in Admin Interface | Migrate/replicate forests to other hosts first | <https://help.marklogic.com/Knowledgebase/Article/View/removing-hosts-from-a-marklogic-cluster-minimizing-downtime> |
| Host added to (or moved into) a group whose cache sizes were tuned for hosts with more RAM | Memory overcommit on the smaller host: OOM-kill / MarkLogic restarts, host flaps offline (`XDMP-HOSTOFFLINE`), its forests unmount; or under-utilised caches on larger hosts | Sum group cache sizes (list, compressed tree, expanded tree, triple) + range-index footprint vs the host's RAM (Admin UI › Groups › Configure; `free -g`); ErrorLog for memory warnings / OOM in `dmesg` | Create a group per hardware class and size caches for the smallest host in it; see `memory-and-os.md` | [unverified — confirm] |
| Hostname changed at OS level without ML rename | Host cannot rejoin, `XDMP-HOSTNAME`-style errors | Compare `hosts.xml` vs `hostname -f` output | Use Admin Interface host rename procedure, not OS rename | <https://help.marklogic.com/Knowledgebase/Article/View/hostname-in-marklogic/0> |
| Host timeout too low on slow network | Spurious host offline events, false failovers | Group › host timeout setting vs network latency | Raise host timeout cautiously; fix underlying network issues | <https://help.marklogic.com/knowledgebase/article/View/248/0/what-is-xdmp-xdqpver-and-what-should-be-done-about-it> |
| XDQP timeout too low on busy cluster | Query failures during high load | XDQP timeout in group settings vs query patterns | Increase XDQP timeout to prevent premature disconnection | <https://help.marklogic.com/Knowledgebase/Article/View/60/0/how-to-handle-xdqp-timeout-on-a-busy-cluster> |
| Insufficient foreign cluster permissions | Cross-cluster replication fails | Foreign cluster authentication settings | Configure proper cross-cluster authentication and permissions | [unverified — confirm] |
| Mixed MarkLogic versions in cluster | Unpredictable behavior, feature conflicts | Check version consistency across all hosts | Ensure all hosts run identical MarkLogic version | Inside MarkLogic p.5 |
| Hosts added without license capacity | License violations, reduced functionality | License status in Admin Interface vs host count | Acquire additional licenses before adding hosts | [unverified — confirm] |

## Sources

- Inside MarkLogic Server (PDF) — clustering overview (p.5, 10-11), failover and clustering (p.47, 104)
- <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/clusters.html>
- <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/hosts.html>  
- <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/groups.html>
- <https://docs.progress.com/bundle/marklogic-server-configure-scal-avail-perf-12/page/topics/distributed.html>
- <https://docs.marklogic.com/admin-help/host>
- <https://help.marklogic.com/Knowledgebase/Article/View/start-up-quorum-and-forest-level-failover>
- <https://help.marklogic.com/Knowledgebase/Article/View/24/0/synchronizing-system-clocks-in-a-cluster>
- <https://help.marklogic.com/Knowledgebase/Article/View/60/0/how-to-handle-xdqp-timeout-on-a-busy-cluster>
- <https://help.marklogic.com/knowledgebase/article/View/248/0/what-is-xdmp-xdqpver-and-what-should-be-done-about-it>
- <https://help.marklogic.com/Knowledgebase/Article/View/hostname-in-marklogic/0>
- <https://help.marklogic.com/Knowledgebase/Article/View/removing-hosts-from-a-marklogic-cluster-minimizing-downtime>

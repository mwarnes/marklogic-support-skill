# Disaster Recovery and Scaling — cross-cluster replication and capacity growth

## Concepts

- **Database Replication**: MarkLogic's modern cross-cluster replication mechanism for disaster recovery. Asynchronous, forest-level replication using journal frame replay between coupled clusters. Standard DR procedure: redirect application traffic from master cluster's database to replica cluster's database after rolling back replica to non-blocking timestamp.

- **Flexible Replication**: Legacy mechanism for cross-cluster replication. Asynchronous, non-transactional, single-master, trigger-based, document-level replication using Content Processing Framework (CPF). Still used for selective content replication with transformation/filtering. More overhead than Database Replication due to CPF triggers and document properties.

- **Foreign cluster coupling**: Prerequisite for Database Replication. Bootstrap hosts from each cluster establish initial XDQP connections, exchange configuration, enable cross-cluster authentication. Requires foreign bind ports and admin role for configuration.

- **Rebalancer + Assignment Policy**: Two-part mechanism for capacity scaling and data redistribution. Assignment policy (bucket/segment/statistical/range/query) determines document placement on insert and rebalance. Rebalancer executes actual data movement between forests to achieve balanced distribution.

- **Automatic rebalancing triggers**: Configuration changes (forest added/retired), backup completion, restore completion trigger rebalancer when enabled. Not a periodic timer — event-driven redistribution.

- **Scaling out procedure**: Add hosts → create new forests on them → attach to database → assignment policy routes new documents there → enable rebalancer to redistribute existing data across expanded topology.

- **Scaling down considerations**: Host removal procedure differs by scenario: temporary (host returns) vs permanent removal, whether host still holds forests. Must migrate/detach forests before host removal to prevent data loss.

## Standard procedures

1. **Set up Database Replication between clusters**: Couple foreign cluster (establish bootstrap hosts, configure foreign bind ports, authentication) → create Master database configuration on primary cluster → create Replica database configuration on foreign cluster → verify replication status shows active.

2. **Configure Flexible Replication**: Enable Content Processing Framework on Master cluster only (not Replica) → create HTTP App Servers for both Master and Replica databases → configure push/pull scheduled tasks → test replication triggers.

3. **Test DR failover procedure**: Roll back replica database to non-blocking timestamp → disable Database Replication on replica → redirect application traffic to replica cluster → verify application functionality → document specific cutover steps in runbook.

4. **Test DR failback procedure**: Establish new replication relationship (former replica as new master) → roll back original primary → redirect traffic back → verify data consistency between clusters.

5. **Scale out capacity**: Add new hosts to cluster → create forests on new hosts → attach forests to target database → verify assignment policy appropriate for workload → enable rebalancer → monitor redistribution progress.

6. **Safely retire/remove host**: Disable rebalancer → detach all forests from host (migrate data to other forests first if permanent removal) → verify no app servers depend on host → remove host from cluster configuration.

## Common mistakes & symptoms

| Mistake | Symptom seen by customer | How to confirm | Fix / best practice | Source |
| --------- | ------------------------- | ---------------- | ------------------- | --------- |
| Database Replication configured but failover/failback never tested | DR exists on paper only — when disaster strikes, unknown cutover steps, untested procedures fail | Check if DR runbook exists with specific steps; ask when last DR test performed | Schedule regular DR tests (quarterly/annually); document exact failover steps; test application connectivity to replica cluster | [unverified — confirm] |
| Flexible Replication Content Processing configured on Replica instead of Master | Replication breaks or produces unexpected results; CPF triggers not firing on Replica | Check CPF status on both clusters; verify which cluster runs CPF domains | Enable CPF and domains on Master cluster only; disable CPF on Replica cluster | <https://docs.marklogic.com/admin-help/flexrep> |
| Replica cluster reindexes unexpectedly after DR failback | Long reindex operation during emergency recovery; replica becomes unavailable during reindexing | Check reindexing status after removing Database Replication configuration from former replica | Ensure identical index settings on both primary and replica before disaster; expect reindex when removing replication config | <https://docs.progress.com/bundle/marklogic-server-configure-database-replication-11/page/topics/dbrep_intro.html> |
| Rebalancer disabled after adding capacity | New forests stay empty while old forests stay full and overloaded; uneven query performance | Compare forest document counts; check rebalancer enable setting on database | Enable rebalancer on database; verify appropriate assignment policy; monitor redistribution progress | <http://docs.marklogic.com/9.0/guide/admin/database-rebalancing> |
| Rebalancing triggered during peak traffic | I/O contention causes query timeouts, performance degradation during business hours | Check rebalancer throttle setting; correlate rebalancing activity with performance issues | Lower rebalancer throttle (1-2) or schedule capacity changes for maintenance windows; cross-reference databases-forests.md reindexer throttle guidance | <http://docs.marklogic.com/9.0/guide/admin/database-rebalancing> |
| Removing/retiring host that still holds forests | Forests become unavailable; XDMP-FORESTNOT errors on queries; data loss risk | Check forest host assignments before host removal; verify forest states | Migrate forest data to other forests or detach forests from database before removing host; cross-reference cluster-hosts-groups.md host removal procedure | <https://help.marklogic.com/Knowledgebase/Article/View/removing-hosts-from-a-marklogic-cluster-minimizing-downtime> |
| Scaling by adding forests to existing hosts without adding host capacity | All growth on same hardware causes memory/CPU/I/O bottlenecks; no actual capacity increase | Compare forest distribution across hosts; check resource utilization on hosts with new forests | Add new physical/virtual hosts first, then add forests to new hosts; cross-reference memory-and-os.md for per-host capacity planning | <https://docs.progress.com/bundle/marklogic-server-configure-scal-avail-perf-12/page/topics/scalability.html> |
| No documented DR runbook | During disaster, nobody knows actual cutover steps, application endpoints, authentication changes | Ask for written DR procedures; check if application teams know replica cluster endpoints | Document step-by-step DR cutover including application configuration changes, DNS/load balancer updates, user notification | [unverified — confirm] |

## Sources

- <https://docs.progress.com/bundle/marklogic-server-configure-database-replication-11/page/topics/dbrep_intro.html>
- <https://docs.progress.com/bundle/marklogic-server-configure-database-replication-11/page/topics/configuring.html>
- <https://docs.marklogic.com/admin-help/flexrep>
- <http://docs.marklogic.com/9.0/guide/admin/database-rebalancing>
- <https://docs.marklogic.com/guide/admin/database-rebalancing>
- <https://docs.progress.com/bundle/marklogic-server-configure-scal-avail-perf-12/page/topics/scalability.html>
- <https://docs.progress.com/bundle/marklogic-server-configure-scal-avail-perf-12/page/topics/distributed.html>
- <https://help.marklogic.com/Knowledgebase/Article/View/removing-hosts-from-a-marklogic-cluster-minimizing-downtime>

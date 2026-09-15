# MarkLogic app servers — configuration and troubleshooting

## Concepts

- **App server types**: HTTP (XQuery/JavaScript over HTTP), XDBC (XCC client connections), WebDAV (file system-like access), ODBC (SQL queries over ODBC). Each type serves different client protocols but shares core configuration patterns.

- **Group-level configuration**: App servers are defined at the group level and run on every host in that group. Port must be unique within the group across all hosts. Configuration changes apply to all hosts in the group simultaneously.

- **Core settings**: Port (unique per group), root directory (filesystem path or database URI prefix), content database (where queries run), modules database (where XQuery/JS code lives, or filesystem), authentication method, default user, thread limits, timeouts.

- **Modules storage**: Can use a modules database (consistent across cluster) or filesystem (local to each host). Database storage ensures consistency in multi-host groups; filesystem allows direct file editing during development.

- **Authentication schemes**: digest/basic (HTTP auth), application-level (custom auth logic with default user), certificate (SSL client certs), Kerberos, SAML. Default user applies only to application-level authentication.

- **Thread and connection limits**: Each app server has max threads per host, backlog (pending connections), concurrent request limit per user, request timeout (first request), keep-alive timeout (subsequent requests).

- **SSL configuration**: Uses certificate templates defined at cluster level. When configured, app server uses encrypted protocols (https, davs, xccs). Certificate must match hostname or include SAN entries.

- **Error handling**: Custom error handler pages, URL rewriters for custom routing, output options for content type handling, static content expiration headers.

- **Request flow**: Client connects → authentication → thread allocation → modules resolution (DB or filesystem) → query execution against content database → response formatting → connection cleanup.

## Standard procedures

1. **Create app server**: Choose unique port (avoid 7997-8002 reserved), set root path, select content database and modules database/filesystem, configure authentication
2. **Configure authentication**: Set scheme (digest/basic recommended), create users/roles in Security database, avoid privileged default users for application-level auth
3. **SSL setup**: Create certificate template with proper hostname/SAN, assign to app server, verify certificate chain and expiration dates
4. **Thread tuning**: Set max threads based on host CPU cores, adjust backlog for connection spikes, set concurrent request limits per user to prevent resource exhaustion
5. **Timeout configuration**: Set request timeout for initial connections, keep-alive timeout for persistent connections, max/default time limits for query execution
6. **Modules management**: Use modules database for multi-host consistency, filesystem only for single-host development, ensure modules accessible on all group hosts
7. **Monitoring setup**: Configure appropriate log levels (notice for production), enable access logs if needed, set up request monitoring for performance analysis
8. **Testing**: Verify app server starts without errors, test connectivity from clients, validate authentication works correctly, check SSL certificate chain

## Common mistakes & symptoms

| Mistake | Symptom seen by customer | How to confirm | Fix / best practice | Source |
| --- | --- | --- | --- | --- |
| Port already used by another app server in same group or by OS | Server won't start, `SVC-SOCBIND`/`SVC-SOCACC` in ErrorLog | Check ErrorLog; `ss -ltnp \| grep :PORT` or `netstat -an \| grep :PORT` | Use unique port per group; avoid 7997–8002 reserved range | <https://help.marklogic.com/Knowledgebase/Article/View/266/0/resolving-svc-socbind-error> |
| Modules on filesystem in multi-host group, deployed to one host only | Requests served by hosts lacking modules fail — typically 404/`XDMP-MODNOTFOUND` [inferred] | Check if modules path exists on every group host | Use modules database for multi-host groups | <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/http-servers.html> |
| Application-level auth with default user `admin` or privileged role | Unauthenticated access with full administrative privileges | Check app server default user setting and role assignments | Use digest/basic auth, or least-privilege default user | <https://docs.marklogic.com/admin-help/http-server> |
| `request timeout`/`default time limit` raised cluster-wide to hide slow queries | Thread exhaustion, everything slows down | Compare timeout settings vs typical request duration | Fix root cause in queries; use per-request `xdmp:set-request-time-limit` | <https://docs.marklogic.com/admin-help/http-server> |
| `max threads` set too high for host CPU count | CPU contention, increased latency under load | threads × app servers per host vs CPU cores | Keep threads near default; add hosts for scale | <https://docs.progress.com/bundle/marklogic-server-configure-scal-avail-perf-12/page/topics/scalability.html> |
| Content database and modules database swapped after environment clone | Module not found errors, empty query results | Verify app server database field settings match intent | Correct database references in app server config | [unverified — confirm] |
| `distribute timestamps` / MVCC set to `nonblocking` without understanding | Stale reads, read-after-write inconsistency | Check app server MVCC setting | Use default `fast`/`contemporaneous` unless justified | Inside MarkLogic p.46 |
| SSL enabled but certificate template expired, wrong hostname, or unsigned | TLS handshake failures, certificate errors in clients | `openssl s_client -connect HOST:PORT`; check cert validity | Renew certificate, ensure hostname/SAN matches | <https://docs.marklogic.com/admin-help/http-server> |
| Repurposing or disabling built-in app servers (8000/8001/8002) | Admin UI, REST API, or QConsole becomes unreachable | Check which app server serves port 8001 (App-Services) | Never modify App-Services, Admin, or Manage servers | [unverified — confirm] |
| `log level` set to `debug`/`finest` in production | Massive ErrorLog files, disk space issues | Check group log level setting and disk usage | Set to `notice` for production; `debug` only temporarily | <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/log-files.html> |
| Request timeout shorter than typical query time | Frequent `XDMP-EXTIME` timeout errors | Compare request timeout vs actual query duration | Increase timeout or optimize query performance | <https://help.marklogic.com/knowledgebase/article/View/27/16/xdmp-canceled-vs-xdmp-extime> |
| URL rewriter or error handler points to non-existent module | 500 errors on every request, `XDMP-MODNOTFOUND` | Check rewriter/error handler paths exist in modules location | Correct paths or remove rewriter/error handler settings | <https://docs.marklogic.com/admin-help/http-server> |
| `backlog` set too low for connection spikes | Connection refused errors during peak load | Monitor connection patterns vs backlog setting | Increase backlog to handle connection bursts | <https://docs.marklogic.com/admin-help/http-server> |

## Sources

- <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/http-servers.html> — HTTP Server configuration, modules database vs filesystem, authentication options
- <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/xdbc-servers.html> — XDBC Server setup, XCC connectivity, security model
- <https://docs.marklogic.com/admin-help/http-server> — Complete reference for HTTP Server configuration parameters
- <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/log-files.html> — Log levels, ErrorLog monitoring, access logs
- Inside MarkLogic Server p.46 — distribute timestamps and MVCC settings
- <https://help.marklogic.com/Knowledgebase/Article/View/266/0/resolving-svc-socbind-error> — SVC-SOCBIND port conflict resolution
- <https://help.marklogic.com/knowledgebase/article/View/27/16/xdmp-canceled-vs-xdmp-extime> — Understanding timeout errors
- <https://docs.progress.com/bundle/marklogic-server-configure-scal-avail-perf-12/page/topics/scalability.html> — Thread configuration and scalability considerations

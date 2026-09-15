# MarkLogic client-side integration tooling — XCC, Java Client API, mlcp, ml-gradle

## Concepts

- **XCC (XML Content Connector)**: Older Java/.NET connection API using `ContentSource` → `Session` model. XCC manages connection pooling internally — the session metaphor is designed so that common JDBC patterns like pooling connections are not appropriate with XCC. Sessions are lightweight objects that should be created and released as needed rather than pooled. Largely superseded for new work by the Java Client API, though still supported. The central abstraction is the `Session` interface created by factory methods on a `ContentSource` instance.

- **Java Client API**: Current MarkLogic Java API. `DatabaseClient` instances created via `DatabaseClientFactory`. Requires one client per (host, port, database, security-context) combination. `ServerEvaluationCall` for executing XQuery/JavaScript requires the `xdbc:eval` privilege; `xdbc:invoke` requires the `xdbc:invoke` privilege. For cross-database operations targeting a database other than the REST server's default, requires additional privileges: `xdbc:eval-in` and `xdbc:invoke-in`. Includes Data Movement SDK (DMSDK) for bulk operations. Ideal for applications wishing to build upon the MarkLogic REST API.

- **mlcp (MarkLogic Content Pump)**: Command-line tool for bulk import/export/copy of documents and database archives. Key tuning parameters include batch size (documents per request), transaction size (documents per transaction), and thread count. The `-fastload` option can significantly speed up ingestion but comes with correctness tradeoffs — it bypasses document assignment policy calculations on the server by performing them client-side, but this can create duplicate URIs if forest topology or assignment policies change between operations.

- **ml-gradle**: Gradle plugin for deployment automation of modules, security configuration, and server resources via the Management API. Uses `gradle.properties` for environment-specific placeholder substitution with default `%%property%%` token format. Token replacement occurs during deployment — missing properties in `gradle.properties` can result in literal `%%property%%` tokens being deployed to configuration files rather than resolved values.

- **CoRB2 (Content Reprocessing in Bulk)**: Java tool for bulk content-reprocessing of documents in MarkLogic using URI selection (URIS-MODULE or URIS-FILE) plus per-URI processing (PROCESS-MODULE or PROCESS-TASK), with optional PRE-BATCH-MODULE/POST-BATCH-MODULE/INIT-MODULE hooks. Entry point `com.marklogic.developer.corb.Manager`. Depends on XCC (see XCC section above) — requires the MarkLogic XCC JAR on the classpath, preferably matching the MarkLogic server version. Key tuning parameters include THREAD-COUNT (default 1) and BATCH-SIZE (default 1 — when greater than 1, PROCESS-MODULE receives a delimited string of URIs that must be tokenized).

## Standard procedures

1. **Basic XCC connection**: Create `ContentSource` via `ContentSourceFactory.newContentSource()`, then obtain sessions via `contentSource.newSession()`. Do not pool sessions — create and release as needed.

2. **Java Client API setup**: Create `DatabaseClient` using `DatabaseClientFactory.newClient()` with specific host, port, database, and authentication. Use one client per server/database combination.

3. **mlcp job sizing**: Start with default batch size (100) and transaction size (10), then tune based on document size and server capacity. Increase thread count (`-thread_count`) for I/O bound operations; decrease for memory-constrained scenarios.

4. **ml-gradle deployment debugging**: Check property substitution by examining deployed configuration files for literal `%%property%%` tokens. Use `mlDeploy` task verbose output to identify which properties are missing from `gradle.properties`.

5. **XCC session pooling verification**: Ensure application code doesn't implement additional connection pooling around XCC `ContentSource` objects, as XCC handles this internally.

6. **Java Client API privilege verification**: For cross-database operations, confirm user has both `xdbc:eval-in`/`xdbc:invoke-in` privileges in addition to basic `xdbc:eval`/`xdbc:invoke`.

## Common mistakes & symptoms

| Mistake | Symptom seen by customer | How to confirm | Fix / best practice | Source |
| ------- | ----------------------- | ------------- | ------------------ | ------ |
| Manual connection pooling around XCC ContentSource/Session | Resource exhaustion or connection leaks despite XCC's internal pooling | Review application code for JDBC-style connection pools wrapping XCC objects | Remove external pooling; create and release XCC sessions as needed | <https://docs.marklogic.com/javadoc/xcc/overview-summary.html> |
| New client development using XCC instead of Java Client API | Missing modern features; using deprecated API | Check project dependencies and import statements for `com.marklogic.xcc` packages | Use Java Client API for new development; XCC is largely superseded | <https://developer.marklogic.com/products/java/> |
| Java Client API missing xdbc:eval-in/xdbc:invoke-in privileges for cross-database operations | `SEC-PRIV` errors when ServerEvaluationCall targets different database than REST server default | Test cross-database eval operations; check user privileges in Security database | Grant `xdbc:eval-in` and `xdbc:invoke-in` privileges for cross-database access | <https://docs.marklogic.com/javadoc/client/com/marklogic/client/DatabaseClient.html> |
| mlcp using default batch/transaction sizes on large datasets | Poor throughput; memory pressure during large imports | Monitor import performance and server memory usage during bulk operations | Increase batch size (1000+) and transaction size (100+) for large documents; tune based on available memory | <https://docs.marklogic.com/9.0/guide/mlcp/import> |
| mlcp -fastload used without understanding correctness tradeoffs | Duplicate document URIs when forest topology or assignment policies change | Check for duplicate URIs after rebalancing or forest changes; verify assignment policy hasn't changed | Only use `-fastload` for new documents with stable forest topology; avoid during updates or rebalancing | <https://docs.marklogic.com/9.0/guide/mlcp/import> |
| ml-gradle deployment with missing gradle.properties entries | Literal `%%property%%` tokens appear in deployed configuration instead of resolved values | Examine deployed config files in Admin Interface for unresolved `%%` tokens | Define all required properties in `gradle.properties`; check `mlDeploy` output for property resolution warnings | <https://github.com/marklogic-community/ml-gradle/wiki/Property-reference> |
| ml-gradle redeploy conflict with existing resources | Deployment failures during `mlDeploy` with resource conflict errors | Check `mlDeploy` task output for specific resource conflict messages | Use `mlUndeploy` before `mlDeploy`, or configure resource update policies in ml-gradle settings | [unverified — confirm] |
| One DatabaseClient used across multiple hosts/databases | Connection errors or unexpected database targeting | Review DatabaseClient instantiation patterns in application code | Create separate DatabaseClient instances per (host, port, database, auth) combination | <https://github.com/marklogic/java-client-api> |
| CoRB2 large URI set held entirely in memory without DISK-QUEUE | OutOfMemory errors during URI processing phase | Check CoRB logs for memory exceptions; review URI set size vs available heap | Enable DISK-QUEUE=true and set DISK-QUEUE-MAX-IN-MEMORY-SIZE (default 1000) to spill URIs to disk | <https://github.com/marklogic-community/corb2/blob/master/README.md> |
| CoRB2 FAIL-ON-ERROR left at default (true) on long-running jobs | Single document error aborts entire batch with no record of successful processing | Check CoRB job logs for early termination after first error; no completion metrics for processed URIs | Set FAIL-ON-ERROR=false and configure ERROR-FILE-NAME to log failed URIs and continue processing | <https://github.com/marklogic-community/corb2/blob/master/README.md> |
| CoRB2 JavaScript URIS-MODULE returning array instead of Sequence | Module fails to load or execute with type errors | Test URIS-MODULE execution independently; check for plain JavaScript array returns vs MarkLogic Sequence | Use Sequence.from() to convert arrays or fn.insertBefore() to build Sequences; avoid single quotes (escape as two single quotes if needed) | <https://github.com/marklogic-community/corb2/blob/master/README.md> |
| CoRB2 XCC jar version mismatch with MarkLogic server version | Connection failures, unexpected behavior, or compatibility errors | Check CoRB classpath XCC version vs target MarkLogic server version | Use XCC JAR version that corresponds to the MarkLogic server version | [unverified — confirm] |

## Sources

- <https://docs.marklogic.com/javadoc/xcc/overview-summary.html>
- <https://developer.marklogic.com/products/java/>
- <https://github.com/marklogic/java-client-api>
- <https://docs.marklogic.com/javadoc/client/com/marklogic/client/DatabaseClient.html>
- <https://developer.marklogic.com/products/mlcp/>
- <https://github.com/marklogic/marklogic-contentpump>
- <https://docs.marklogic.com/9.0/guide/mlcp/import>
- <https://developer.marklogic.com/code/ml-gradle/>
- <https://github.com/marklogic-community/ml-gradle>
- <https://github.com/marklogic-community/ml-gradle/wiki/Property-reference>

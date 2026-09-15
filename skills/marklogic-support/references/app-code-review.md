# MarkLogic application code review — XQuery/JavaScript modules, REST extensions

## Concepts

- **Search two-step manifesting in application code**: MarkLogic search works by first resolving from indexes (fast), then filtering results for accuracy (slow). Application code forces filtering when it retrieves broad `cts:search` results then applies XQuery/JavaScript predicates afterward instead of composing all constraints into the `cts:query` expression directly. This bypasses index optimization and creates the filtered search performance problem covered in `performance-tuning.md` from a config-diagnosis angle.

- **REST extension structure and conventions**: Custom resource service extensions live under `/config/resources` with a strict namespace convention: `"http://marklogic.com/rest-api/resource/{resource-name}"` for XQuery extensions, and the module prefix must match the resource name. The extension framework expects specific function signatures (`get`, `post`, `put`, `delete`) and uses `map:map` parameters for `$context` and `$params`. Violations break Client API interoperability.

- **REST extension error handling**: Errors must be reported to REST clients using `fn:error` (XQuery) or `fn.error` (JavaScript) with the `RESTAPI-SRVEXERR` error code and a specific parameter sequence: `(status-code, status-message, response-payload)`. Other error handling approaches (generic exceptions, `Error` objects) result in unhelpful `500 Internal Error` responses with no diagnostic information reaching the client.

- **XQuery/JavaScript interop and performance overhead**: `xdmp:javascript-eval` calls JavaScript from XQuery; `xdmp.xqueryEval`/`xdmp.eval` call XQuery from JavaScript. [unverified — confirm] Each boundary crossing has performance overhead when used repeatedly (e.g., inside a loop) vs. crossing once outside the loop. The XQuery profiling API cannot see into Server-Side JavaScript functions - if your code calls a JavaScript function, you will only see data for the top level call.

- **Amps and dynamic evaluation in application code**: `xdmp:eval`/`xdmp:invoke`/`xdmp.eval` used for privilege escalation in application code when static function calls or amps would suffice. This creates security risks covered in `security.md` from config-level amp-scope guidance; the code-level smell is using dynamic evaluation for non-dynamic requirements.

## Standard procedures

1. **Check REST extension structure**: Verify extension lives under `/config/resources`, follows namespace convention `http://marklogic.com/rest-api/resource/{resource-name}`, and module prefix matches resource name.

2. **Review cts:search usage pattern**: Look for `cts:search` calls followed by XQuery/JavaScript filtering code. Check if filtering constraints can be composed into `cts:and-query`/`cts:or-query` instead of post-processing results.

3. **Identify unbounded sequence materialization**: Search for large `cts:search` results without pagination that then call `fn:count()`, `fn:reverse()`, or other functions that force full sequence materialization in memory.

4. **Examine error handling in REST extensions**: Confirm catch blocks use `fn:error`/`fn.error` with `RESTAPI-SRVEXERR` rather than swallowing errors or returning generic responses.

5. **Find unnecessary eval/invoke calls**: Look for `xdmp:eval`/`xdmp:invoke`/`xdmp.eval` used for static logic that could be handled by fixed function calls or amp privileges instead.

6. **Check XQuery/JavaScript boundary crossings**: Identify `xdmp:javascript-eval`/`xdmp.xqueryEval` calls inside loops where the boundary could be crossed once outside the loop.

7. **Validate input parameters**: Review REST extension parameter handling to ensure input validation occurs before parameters are used in `cts:query` or document manipulation functions.

8. **Scan for hardcoded credentials**: Search for connection strings, passwords, or credentials embedded in module code rather than using external security or app-server configuration.

## Common mistakes & symptoms

| Mistake | Symptom seen by customer | How to confirm | Fix / best practice | Source |
| ------- | ----------------------- | ------------- | ------------------ | ------ |
| Post-filtering `cts:search` results with XQuery/JS predicates instead of composing into `cts:query` | Poor search performance despite proper indexes configured | Look for `cts:search` calls followed by XQuery `where` clauses, `[predicate]` expressions, or JavaScript `filter()` operations on results | Compose all filtering constraints into `cts:and-query`/`cts:or-query`; let indexes filter, not application code | <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/perftune.html> |
| Unbounded sequence realized in memory | Memory pressure, `XDMP-TREECACHEFULL`, slow response times | Code calls `fn:count()`, `fn:reverse()`, or iterates large `cts:search` results without limit/pagination | Add result limits, implement pagination, avoid forcing full sequence materialization | <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/perftune.html> |
| REST extension catch block swallows errors or returns generic response | Client receives no diagnostic information for failed requests | Catch blocks that don't call `fn:error`/`fn.error` with `RESTAPI-SRVEXERR`; generic error responses | Use `fn:error((), "RESTAPI-SRVEXERR", (status-code, message, payload))` for proper error reporting | <https://docs.marklogic.com/guide/rest-dev/extensions> |
| REST extension violates `/config/resources` naming/namespace convention | Extension not accessible via Client API; import/deployment failures | Namespace doesn't match `"http://marklogic.com/rest-api/resource/{resource-name}"` or module prefix doesn't match resource name | Follow strict naming convention; ensure namespace and prefix consistency | <https://docs.marklogic.com/guide/rest-dev/extensions> |
| `xdmp:eval`/`xdmp:invoke` used for static logic that doesn't need dynamic evaluation | Unnecessary privilege escalation risk; performance overhead | Code uses eval/invoke for logic that could be direct function calls or amps | Replace with direct function calls or amp privileges; reserve eval/invoke for truly dynamic requirements | <https://docs.progress.com/bundle/marklogic-server-secure-12/page/topics/role-based-security-model/understanding-roles/assigning-privileges-to-roles/execute-privileges.html> |
| Crossing XQuery/JavaScript boundary repeatedly inside loops | Poor performance due to repeated language transition overhead [unverified — confirm] | `xdmp:javascript-eval`/`xdmp.xqueryEval` called per-iteration rather than once outside loop | Move boundary crossing outside loops; batch operations in target language | [unverified — confirm] |
| Missing input validation on REST extension parameters | Security vulnerabilities; injection attacks possible [unverified — confirm] | REST parameters used directly in `cts:query` or document operations without validation | Validate all input parameters before use; sanitize data for query construction | [unverified — confirm] |
| Hardcoded credentials or connection strings in module code | Security exposure; credentials in source control | Grep for passwords, connection strings, API keys embedded in .xqy/.sjs files | Use external security, app-server configuration, or secure credential stores instead | [unverified — confirm] |

## Sources

- <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/perftune.html>
- <https://docs.progress.com/bundle/marklogic-server-secure-12/page/topics/role-based-security-model/understanding-roles/assigning-privileges-to-roles/execute-privileges.html>
- <https://docs.marklogic.com/9.0/guide/performance/profile>
- <https://docs.marklogic.com/guide/rest-dev/extensions>
- <https://docs.marklogic.com/REST/client/service-extension>
- <https://docs.marklogic.com/xdmp:javascript-eval>
- <https://docs.progress.com/bundle/marklogic-server-develop-rest-api-12/page/topics/intro.html>
- <https://docs.progress.com/bundle/marklogic-server-xquery-xslt-reference-12/page/topics/whatis.html>
- <https://docs.progress.com/bundle/marklogic-server-javascript-reference-12/page/topics/language.html>

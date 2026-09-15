# MarkLogic security — access control, authentication & auditing

## Concepts

- **Role-based security**: Users → Roles → Privileges/Permissions. User gets effective permissions from all assigned roles. Roles can inherit from other roles, creating hierarchies.

- **Execute privileges**: Named permissions for specific operations (e.g., `xdmp:eval`, `xdmp:document-insert`). Required to run built-in functions beyond basic read operations.

- **URI privileges**: Control access to specific URI patterns or resources. Can be scoped to exact URIs or URI patterns for broader control.

- **Document permissions**: Each document has read/update/insert/execute capabilities granted to specific roles. Permissions are checked on every document access.

- **Amps (Amplified Functions)**: Controlled privilege escalation. Allow a function to run with higher privileges than the calling user. Target specific module/function combinations.

- **Security database**: Special database storing users, roles, privileges, amps, external security objects. One per cluster, typically named `Security`.

- **Default permissions/collections**: Applied automatically to documents when inserted by users/roles. Set on roles and users to ensure consistent document access.

- **External security**: Integration with LDAP, Active Directory, Kerberos, SAML for authentication/authorization. Maps external groups to MarkLogic roles.

- **Element Level Security (ELS)**: Fine-grained permissions on XML elements/attributes. Uses query rolesets to determine which parts of documents users can see.

- **Query rolesets**: Define which roles can see protected elements/attributes when ELS is enabled. Attached to protected paths configuration.

- **Certificate authentication**: X.509 client certificates for strong authentication. Uses certificate templates to map certificate fields to users/roles.

- **Auditing**: Logs security events, configuration changes, document access. Events stored in audit database or files. Essential for compliance and forensics.

- **Encryption at rest**: Database-level encryption using keystores (internal KMS) or external KMS integration. Protects data files on disk.

- **Compartment security**: **(v12)** Advanced isolation between different security domains within same cluster. Prevents cross-contamination of data access.

### Network & infrastructure hardening

- **Port management**: Development tool ports 8000, 8001, 8002 (App-Services/QConsole, Admin Interface, Manage server) must be protected behind corporate firewalls. Application ports (like :80, :443) may be publicly accessible, but administrative interfaces should never be exposed to public internet.

- **XDQP SSL configuration**: Internal cluster communication uses XDQP protocol on ports 7997-7999. SSL cipher configuration is set per-group using `admin:group-set-xdqp-ssl-ciphers`. No outside authority is used to sign certificates for internal XDQP connections — certificates are self-signed and trusted by each server in the cluster.

- **CORS on REST servers**: Cross-Origin Resource Sharing headers control which web domains can access REST API endpoints. Overly permissive `Access-Control-Allow-Origin` settings (e.g., `*`) allow any website to make API requests.

- **Password and account policies**: MarkLogic supports password complexity requirements and account lockout policies. Without proper configuration, weak passwords are accepted and repeated authentication failures don't lock accounts.

## Standard procedures

1. Create security hierarchy: Create roles → assign execute/URI privileges → create users → assign roles to users
2. Set default permissions on roles/users to ensure documents are accessible by intended audiences
3. Configure document collections and permissions during ingestion to control access patterns
4. Create amps for controlled privilege escalation when applications need specific elevated operations
5. Set up external security objects (LDAP/SAML) and bind to app servers for centralized authentication
6. Configure Security database backups as part of regular backup schedule (user/role data loss is unrecoverable)
7. Enable auditing on groups with focus on security events, configuration changes, and compliance requirements
8. Configure password policies and account lockout settings through security configuration
9. Set up encryption-at-rest with keystore management and key backup procedures for production environments
10. Configure element-level security with protected paths and corresponding query rolesets when fine-grained access control is needed
11. Test privilege escalation paths and external security failover scenarios during maintenance windows

## Common mistakes & symptoms

| Mistake | Symptom seen by customer | How to confirm | Fix / best practice | Source |
| --- | --- | --- | --- | --- |
| Documents inserted by `admin` with no explicit permissions | Non-admin users see no documents (`SEC-PERMDENIED` or empty results) | `xdmp:document-get-permissions()` shows only admin permissions; admin role has full authority regardless of permissions set | Insert documents with explicit role permissions; set default permissions on application ingest roles | <https://docs.progress.com/bundle/marklogic-server-secure-11/page/topics/role-based-security-model/the-admin-and-security-roles.html> |
| Application users given `admin` role | Any application bug becomes total security compromise; audit trails become useless | Check role membership in Security database | Create least-privilege application roles; use amps for specific elevated operations | <https://docs.progress.com/bundle/marklogic-server-secure-12/page/topics/role-based-security-model/understanding-roles/assigning-privileges-to-roles.html> |
| Role granted overly broad URI privileges like `/` | Users can write/execute anywhere in the database | Review role privileges in Admin Interface | Scope URI privileges to specific URI prefixes; use collection-based permissions instead | <https://docs.progress.com/bundle/marklogic-server-secure-12/page/topics/role-based-security-model/understanding-roles/assigning-privileges-to-roles/uri-privileges.html> |
| Security database not backed up or restored from different cluster | Users/roles lost after restore; role ID mismatches cause `SEC-ROLEDNE` errors | Check backup schedule includes Security database; verify role IDs match | Include Security database in every backup set; restore Security database with content databases | <https://help.marklogic.com/Knowledgebase/Article/View/192/0/restoring-security-database> |
| External security (LDAP) configured without internal admin fallback | Complete lockout when LDAP server unavailable | External security configuration shows no internal authentication method | Keep internal admin user enabled; test LDAP failover procedures | <https://help.marklogic.com/Knowledgebase/Article/View/152> |
| `xdmp:eval`/`xdmp:invoke` amps granted too widely | Allows privilege escalation and code injection attacks | Review amp configurations for eval/invoke functions | Minimize amp scope to specific modules; avoid eval amps in user-facing code | <https://docs.progress.com/bundle/marklogic-server-secure-12/page/topics/role-based-security-model/understanding-roles/assigning-privileges-to-roles/execute-privileges.html> |
| Auditing disabled in production environments | Security and configuration events not recorded; cannot reconstruct who changed what | Check Group › Auditing configuration | Enable key audit events (security changes, document access, configuration changes) | <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/auditing-events.html> |
| Encryption-at-rest enabled without key export/backup | Data becomes unrecoverable after host failure or cluster rebuild | Verify keystore backup procedures exist | Export and securely store encryption keys; document key recovery procedures | <https://help.marklogic.com/Knowledgebase/Article/View/how-to-reset-wallet-password-when-you-lost-the-existing-password> |
| Element-level security configured without corresponding query rolesets | Queries return nothing or throw query roleset errors like `SEC-NOQUERYROLESET` | Check protected paths configuration vs query rolesets | Create query rolesets for each protected path; assign appropriate roles | <https://docs.progress.com/bundle/marklogic-server-secure-12/page/topics/element-level-security/configuring-element-level-security/query-rolesets/query-for-protected-paths-on-a-document.html> |
| Lost admin password with no recovery mechanism | Complete administrative lockout of cluster | Check if other admin users exist or external admin access configured | Maintain multiple admin users; document password reset procedures | <https://help.marklogic.com/Base/UserLostPassword/Index> |
| Certificate authentication misconfigured or templates incorrect | Certificate authentication fails; users cannot connect with valid certificates | Check certificate template configuration and user/role mappings | Verify certificate template field mappings; test certificate authentication flow | <https://help.marklogic.com/knowledgebase/article/View/573/0/troubleshooting-marklogic-certificate-based-authentication> |
| LDAP nested group lookup fails with Active Directory | Users with nested AD group membership cannot authenticate or get proper role assignments | Check LDAP configuration logs and nested group settings | Configure proper LDAP group search base and nested group lookup options | <https://help.marklogic.com/Knowledgebase/Article/View/641/0/> |
| Default collections not set properly on ingest roles | Documents inserted into default collection, breaking collection-based security model | Check default collection settings on users/roles; verify document collection assignments | Set appropriate default collections on application roles; verify collection-based permissions | <https://docs.progress.com/bundle/marklogic-server-secure-12/page/topics/protecting-documents/example-using-permissions/default-permission-settings.html> |
| Security database restored with lingering certificate template IDs in config | Certificate authentication references non-existent templates causing authentication failures | Check configuration files for orphaned template references after Security database restore | Clean up configuration references after Security database restore; re-create certificate templates | <https://help.marklogic.com/Knowledgebase/Article/View/security-database-restore-leading-to-lingering-certificate-template-id-in-config-files> |
| Development tool ports (:8000, :8001, :8002) accessible from public internet | Security vulnerability; unauthorized access to App-Services/QConsole, Admin Interface, or Manage server | Check network accessibility from external IPs; verify firewall rules | Place administrative interfaces behind corporate firewall; restrict access to internal networks only | <https://docs.progress.com/bundle/marklogic-server-secure-12/page/topics/securing-your-production-deployment/infrastructure-hardening/port-management.html> |
| XDQP SSL cipher configuration set to weak or default values | Cluster communication vulnerable to interception; performance issues with inappropriate cipher selection | Review group cipher settings in Admin UI; check `admin:group-set-xdqp-ssl-ciphers` configuration | Configure appropriate cipher suites for security/performance balance; avoid weak ciphers | <https://docs.marklogic.com/admin:group-set-xdqp-ssl-ciphers>; <https://docs.marklogic.com/9.0/guide/security/SSL> |
| CORS misconfigured on REST app server with overly permissive origins | Cross-site request forgery; unauthorized web applications can access REST API | Check app server CORS settings; review `Access-Control-Allow-Origin` headers in responses | Set specific allowed origins instead of wildcard (`*`); validate origin headers appropriately | [unverified — confirm] |
| No password policy or account lockout configured | Weak passwords accepted; no protection against brute force authentication attacks | Review security configuration for password complexity and account lockout settings | Configure minimum password requirements and account lockout after failed attempts | [unverified — confirm] |

## Sources

- <https://docs.progress.com/bundle/marklogic-server-secure-12/page/topics/introduction-to-security.html>
- <https://docs.progress.com/bundle/marklogic-server-secure-12/page/topics/administering-security.html>
- <https://docs.progress.com/bundle/marklogic-server-secure-12/page/topics/securing-your-production-deployment.html>
- <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/security-administration.html>
- <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/auditing-events.html>
- <https://help.marklogic.com/Knowledgebase/Article/View/192/0/restoring-security-database>
- <https://help.marklogic.com/Knowledgebase/Article/View/152>
- <https://help.marklogic.com/Base/UserLostPassword/Index>
- <https://help.marklogic.com/knowledgebase/article/View/573/0/troubleshooting-marklogic-certificate-based-authentication>
- <https://help.marklogic.com/Knowledgebase/Article/View/641/0/>
- <https://help.marklogic.com/Knowledgebase/Article/View/how-to-reset-wallet-password-when-you-lost-the-existing-password>
- <https://help.marklogic.com/Knowledgebase/Article/View/security-database-restore-leading-to-lingering-certificate-template-id-in-config-files>

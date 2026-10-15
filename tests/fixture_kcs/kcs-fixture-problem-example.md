<!--
KCS ARTICLE — Problem/Solution
Paste each section below into the matching Salesforce field.
-->

## Title
MarkLogic OAuth 2.0 Authorization Code flow returns "request is otherwise malformed" from the Identity Provider

## URL Name
marklogic-oauth-2-0-authorization-code-request-otherwise-malformed

## Validation Status
Unverified

## Summary
With the MarkLogic 12.1 OAuth 2.0 Authorization Code flow, the Identity Provider (IdP) rejects MarkLogic's authorization request with `invalid_request` / "The request is otherwise malformed" instead of showing its sign-in page. The cause is the IdP client registration: the `authorization_code` grant type is not enabled for the client that MarkLogic uses.

## Article Number
*(assigned by Salesforce on save)*

## Environment
Product: MarkLogic\
Version: All supported versions\
OS: All supported platforms\
Component: Security

## Question/Problem Description
After configuring the OAuth 2.0 Authorization Code flow, browsing to the protected app server redirects to the IdP's authorization endpoint, but the IdP returns an error immediately instead of showing a sign-in page. The browser is returned to the MarkLogic app server URL with `error=invalid_request` and `error_description=The request is otherwise malformed` in the query string.

## Steps to Reproduce
1. Register an OAuth 2.0 / OIDC client for the MarkLogic app server on the IdP with no allowed grant types (in Authentik, an OAuth2 provider created through the REST API without a `grant_types` value).
2. Configure a MarkLogic External Security configuration for the Authorization Code flow using that client's ID and secret, and select it on the HTTPS app server.
3. Browse to the app server in a new private browser window.
4. The IdP returns `invalid_request` / "The request is otherwise malformed" instead of a sign-in page.

## Clarifying Information
**Environment details:** MarkLogic Server 12.1.0 and later; External Security configuration with `oauth-flow-type` = `Authorization code`; Identity Provider whose OAuth 2.0 / OIDC client registration has an allowed grant types setting (reproduced with Authentik 2026.8).

The error text does not name the parameter at fault, so it is easily mistaken for a redirect URI mismatch or a malformed PKCE `code_challenge`. The request reaches the IdP and is rejected before sign-in; MarkLogic receives only the error response on its redirect URI and cannot tell which IdP client setting caused it. The IdP's own log identifies the reason.

## Error Message
Returned to the app server's redirect URI as query parameters:

```
error=invalid_request
error_description=The request is otherwise malformed
```

Authentik server log:

```
Invalid grant_type for provider
```

## Defect Number
N/A

## Enhancement Number
N/A

## Cause
The IdP client registration did not allow the `authorization_code` grant type, so the IdP rejected the authorization request. In Authentik, an OAuth2 provider created through the REST API defaults `grant_types` to an empty list; a provider created with the Admin Interface wizard includes `authorization_code`. Other IdPs have an equivalent per-client setting (for example "Standard flow" in Keycloak, or "Authorization Code" under the application's grant types in Okta).

## Resolution
1. On the IdP, open the OAuth 2.0 / OIDC client used by MarkLogic (the client ID in the External Security configuration's `oauth-client-id`).
2. Enable the **Authorization Code** grant type for that client and save. In Authentik, the provider's `grant_types` must include `authorization_code`.
3. While the client is open, confirm the redirect URI matches the MarkLogic `oauth-redirect-uri` exactly, for example `https://marklogic.example.com:8000` (scheme, host and port, no path). In testing with Authentik, a regular-expression redirect URI that required a path after the port did not match.
4. Retry in a new private browser window. The IdP should show its sign-in page, and after sign-in the browser should return to the app server.

Verified on MarkLogic 12.1.0 with Authentik 2026.8: with `grant_types` empty the Authentik log showed `Invalid grant_type for provider` and the browser received `invalid_request`; after setting `authorization_code` the login completed.

## Workaround
N/A — enabling the grant type on the IdP client is the fix.

## Notes
When an Authorization Code configuration fails before the IdP sign-in page appears, check the IdP client registration (enabled grant types, redirect URI, client ID) and the IdP's log before changing MarkLogic settings.

**Related articles:**
- How to configure MarkLogic OAuth 2.0 Authorization Code flow
- MarkLogic OAuth 2.0 Authorization Code login redirects in a loop and never completes

## Keyword Phrase
MarkLogic OAuth2 Authorization Code invalid_request "request is otherwise malformed" grant type authorization_code IdP client registration redirect URI Authentik

## Admin Ticket ID
*(fill in if applicable)*

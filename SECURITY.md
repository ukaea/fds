# Security Policy

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Report it through [GitHub's private vulnerability reporting](https://github.com/ukaea/fds/security/advisories/new),
which opens a draft advisory visible only to the maintainers. If you cannot use
that, email the maintainers.

Useful things to include: the endpoint or component affected, what an
unauthorised caller can reach, and the steps to reproduce it. A failing test or a
`curl` transcript is ideal.

We will acknowledge a report within five working days and tell you whether we
consider it a vulnerability, and if so what the fix and timeline look like.

## Scope

FDS is a metadata catalogue and data-access broker, so the parts most worth your
attention are:

- **Read access control.** `PUBLIC` / `EMBARGOED` / `RESTRICTED` levels are
  inherited down Device → Shot → Dataset, and enforced in the service layer. A
  route that returns metadata the caller's policy does not permit is a
  vulnerability, including via a sub-resource or a semantic projection such as
  JSON-LD.
- **Credential vending.** FDS mints short-lived, scoped storage credentials
  (S3 STS, GCS downscoped tokens, Azure user-delegation SAS). Credentials wider
  in scope or longer in life than the request warrants are a vulnerability.
- **Token validation.** JWT / OIDC signature checking, issuer and audience
  validation, and JWKS handling.

## Supported versions

FDS is pre-production and has no deployments. Only the `main` branch is
supported; fixes land there and are not backported. Releases before `0.1.0`
carry no stability guarantee.

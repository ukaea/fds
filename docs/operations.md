# Operations

How to run FDS outside a development checkout: what it needs, every setting it reads, and how the
database schema is managed. Nothing here is specific to any one installation.

## Shape of a deployment

FDS is one container image serving HTTP on port 8000. It is stateless: everything it knows is in
its database or in the object stores it brokers access to. A deployment therefore has three parts,
and FDS provides only the first.

| Part | Provided by | Notes |
| --- | --- | --- |
| The API | the FDS image | Serves `/api/v1/...`, `/health`, and its OpenAPI explorer at `/docs`. Runs as an unprivileged user inside the container. |
| PostgreSQL | you | The only supported database. FDS applies its migrations on start. |
| An identity provider | you | FDS verifies tokens from the issuers listed in `FDS_TRUSTED_IDPS`. It never issues tokens and holds no client secret. |

FDS speaks plain HTTP and does not terminate TLS; how requests reach it is your decision. Two
things about its behaviour bear on that:

- The identifiers in its JSON-LD output are built from the host the request arrived with, so the
  hostname clients use becomes part of the catalogue's public identity. Choose one you intend to
  keep.
- When something in front of FDS rewrites requests, it believes `X-Forwarded-*` headers only from
  senders listed in `FORWARDED_ALLOW_IPS`; otherwise identifiers would name the internal hop.

Any web front end is a separate deployable that calls the API.

## Database

FDS runs on PostgreSQL and has no other backend. Point it at one with `FDS_DB_HOST` and friends,
or give it a complete URL in `FDS_DB_URL`.

### Schema migrations

The schema is created and changed only by the Alembic migrations shipped with the code, in
`alembic/versions/`. A migration describes how the table layout changes from one release to the
next. It carries no data and nothing about any particular installation; the connection comes from
the environment at run time. The only per-installation state is a one-row `alembic_version` table
recording which migration that database has reached.

The image runs `alembic upgrade head` before starting the server, so a new database is built and
an existing one brought up to date on every start. To run it separately, for example before
swapping in a new image:

```bash
alembic upgrade head
```

Every migration is reversible. Rolling back to an older release that expects an older schema means
downgrading first, then deploying the older image:

```bash
alembic downgrade <revision>
```

Back up the database before either operation on data you care about.

## Moving to a new hostname

FDS stores nothing about its own address. The URLs in its responses, including every JSON-LD
`@id`, are built from the incoming request's host, and a record created locally carries no
`origin` (only records ingested from another catalogue do). So a change of hostname needs no
change to the database. What it does need is outside FDS:

- **Records held elsewhere.** Harvesters, other catalogues and citations hold the old URLs.
  Keeping the old hostname answering with redirects for as long as you can is the usual remedy.
- **DOIs.** Update the landing URL on each DOI record at the registrar; that indirection is what a
  DOI is for.

The same reasoning applies in the other direction. When ingesting records from another catalogue,
set their `origin` to the most persistent identifier that catalogue has (a re3data record, a DOI,
an identifier it advertises in its own DCAT catalogue) and use the same value every time; its URL
is the fallback, and it goes stale if that catalogue moves.

## Settings

Every setting is an environment variable. `.env.example` in the repository lists them with their
defaults.

### Application

| Setting | Effect |
| --- | --- |
| `FDS_APP_NAME` | Service name in the OpenAPI document and in traces. Default `fds`. |
| `FDS_ENVIRONMENT` | `dev` or `prod`. Selects the default log format. |
| `FDS_DEBUG` | Enables debug behaviour. Off in production. |
| `FDS_LOG_FORMAT`, `FDS_LOG_LEVEL` | See [Logging](logging.md). |

### Database

| Setting | Effect |
| --- | --- |
| `FDS_DB_HOST` | PostgreSQL host. Default `localhost`. |
| `FDS_DB_PORT` | PostgreSQL port. Default `5432`. |
| `FDS_DB_NAME` | Database name. Default `fds`. |
| `FDS_DB_USER`, `FDS_DB_PASSWORD` | Credentials. |
| `FDS_DB_URL` | A complete SQLAlchemy URL, which overrides the four settings above. |

### Identity

| Setting | Effect |
| --- | --- |
| `FDS_TRUSTED_IDPS` | JSON list of issuers whose tokens are accepted, each with the scopes it may grant, and optionally where its keys come from. See [Access Control](access-control.md#where-fds-finds-an-issuers-keys). Empty means no token is accepted and only public metadata is readable. |
| `FDS_OIDC_AUDIENCE` | The `aud` claim a token must carry. |

### Storage

| Setting | Effect |
| --- | --- |
| `FDS_STORAGE_PROVIDERS` | JSON list of object stores FDS can vend credentials for. For S3-compatible stores: `endpoint_url` (what clients connect to), `sts_endpoint_url` (what FDS calls, if different), `region`, `sts_role_arn`, and optionally `sts_access_key_id` / `sts_secret_access_key`; without the last two, the standard AWS credential chain applies. |
| `FDS_CREDENTIAL_TOKEN_DURATION` | Lifetime in seconds of vended credentials. Default `3600`. |

### Serving

Read by the web server and the tracing library rather than by FDS itself.

| Setting | Effect |
| --- | --- |
| `WEB_CONCURRENCY` | Number of worker processes. Default one. See [Logging](logging.md) for what several workers mean for the log stream. |
| `FORWARDED_ALLOW_IPS` | Senders whose `X-Forwarded-*` headers are trusted. Default `127.0.0.1`; `*` when nothing but the intended front can reach the container. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Where to send traces. Unset means traces are not exported. Other `OTEL_*` variables are honoured as documented by OpenTelemetry. |

## Health

`GET /health` returns `200` with the running version when the process is up. It does not touch the
database; use it for container health checks and uptime probes, and monitor the database directly.

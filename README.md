# Fusion Data Service (FDS)

[![CI](https://github.com/ukaea/fds/actions/workflows/ci.yml/badge.svg)](https://github.com/ukaea/fds/actions/workflows/ci.yml)
[![Licence](https://img.shields.io/badge/licence-Apache--2.0-blue.svg)](LICENSE)

The Fusion Data Service (FDS) is a platform designed to provide scalable, FAIR-compliant access to fusion experiment metadata and data. It aligns with fusion community standards (like IMAS) to ensure interoperability and supports a flexible data hierarchy suitable for multimodal fusion research data.

> **Status: pre-production.** FDS has no deployments yet. The API and data model can change without a deprecation cycle until `0.1.0`, and releases before then carry no stability guarantee. Feedback and issues are welcome; treat the interface as provisional.

## Features

- **Flexible Data Hierarchy**: Organises data into `Device` -> `Shot` -> `Dataset` structures where appropriate.
- **Provenance Tracking**: Tracks provenance (Sources, Datasets) to ensure accountability and reproducibility.
- **Hybrid Storage Support**: Native support for S3, Google Cloud Storage (GCS), and Azure Blob Storage.
- **Security & Authorization**:
  - Integration with external Identity Providers (IdPs) via JWT/OIDC.
  - Granular access control (Public, Restricted) with layered enforcement.
  - Dynamic Public Key Validation (JWKS).
- **High Performance Access**: Supports "Direct Cloud Access" patterns (presigned URLs) for massive parallel I/O, avoiding API bottlenecks.
- **FAIR Compliance**: Aligned with DCAT (Data Catalog Vocabulary) standards.

## Requirements

- **[uv](https://docs.astral.sh/uv/)**, which manages the dependencies and fetches the Python
  version the project pins, so no separate Python install is needed.
- **A container runtime with Compose**: Docker, or Podman (see the note under
  [Running locally](#running-locally) if you are on macOS).
- **[prek](https://github.com/j178/prek)**, if you intend to commit: it runs the pre-commit hooks.

## Documentation

Published at **<https://ukaea.github.io/fds/>**, covering the data model, access control, provenance, and the DCAT / JSON-LD semantic projection. Built with [Zensical](https://zensical.org/) from the `docs/` directory and deployed by GitHub Actions on every push to `main`, so it does not depend on anyone running a local stack.

To preview changes locally before opening a pull request:

```bash
uvx zensical serve
```

## Running locally

`compose.yaml` starts FDS.

```bash
# once: a key pair this stack trusts, so you can sign your own tokens
uv run scripts/mint-token.py init --out-dir dev

docker compose up -d --build        # or: podman compose up -d --build
```

That starts FDS and the PostgreSQL it runs on, applying the migrations on the way up. FDS is then
on `http://localhost:8000`, with its OpenAPI explorer at `/docs`. Reads of public
metadata need no token; to write, sign one:

```bash
export FDS_TOKEN=$(uv run scripts/mint-token.py mint)
curl -H "Authorization: Bearer $FDS_TOKEN" ...
```

The catalogue starts empty. To register the example datasets the documentation refers to:

```bash
FDS_TOKEN=$(uv run scripts/mint-token.py mint) uv run scripts/seed-example-catalogue.py
```

No identity provider runs by default, because nothing needs one: tokens are signed locally.
Keycloak, carrying a development realm, is there when you want to log in through the reference
UI or to check that a realm's mappers produce tokens FDS accepts:

```bash
docker compose --profile ui up -d --build   # FDS + Keycloak + the reference UI
```

That serves the UI on `http://localhost:3000` and Keycloak on `http://localhost:8080`
(`admin`/`admin`; realm users `admin`, `user`, `mast_admin`, all with password `password`).
`--profile idp` starts Keycloak without the UI.

To work on FDS itself, start the database alone and run FDS from your checkout with reload:

```bash
docker compose up -d postgres
uv run alembic upgrade head
FDS_DB_PASSWORD=fds uv run uvicorn app.main:app --reload
```

> **Podman on macOS:** if `podman compose up` hangs, `scripts/podman-up.sh` works around it
> (add `--ui` for Keycloak and the UI). Docker users do not need it.

To see request traces and browse them in Grafana, add the observability overlay:

```bash
docker compose -f compose.yaml -f compose.observability.yaml up -d --build
```

That adds Grafana on `http://localhost:3002` and turns on trace export and JSON log output. It is
off by default because it pulls a 2.5 GB image and adds around 700 MB of memory.

## Local Development Setup

1. **Clone the repository:**

    ```bash
    git clone https://github.com/ukaea/fds.git
    cd fds
    ```

2. **Install dependencies:**

    ```bash
    uv sync
    ```

3. **Install pre-commit hooks:**

    ```bash
    prek install
    ```

## Configuration

The application uses `pydantic-settings` for configuration. Environment variables can be set in a `.env` file or exported in the shell.

Key configuration areas:

- **Database**: the PostgreSQL FDS runs on (`FDS_DB_HOST`, `FDS_DB_PORT`, `FDS_DB_NAME`, `FDS_DB_USER`, `FDS_DB_PASSWORD`, or `FDS_DB_URL` for a complete URL).
- **Authentication**: the issuers whose tokens are accepted and the audience expected (`FDS_TRUSTED_IDPS`, `FDS_OIDC_AUDIENCE`). See [Access Control](https://ukaea.github.io/fds/access-control/).
- **Storage**: the object stores FDS vends credentials for (`FDS_STORAGE_PROVIDERS`).

`.env.example` lists every setting with its default.

## Development

### Running Tests

```bash
uv run pytest
```

The tests need a PostgreSQL to run against, because FDS has no other backend. They use
`FDS_TEST_DB_URL` when it is set, and otherwise start a container for the run and throw it away:

```bash
# against the compose stack's database
FDS_TEST_DB_URL=postgresql+psycopg://fds:fds@localhost:5432/fds uv run --all-extras pytest

# or let the tests start their own
uv run --all-extras pytest
```

Each test runs in a transaction that is rolled back, and the schema is built once per run by the
committed migrations, so a run also proves the migrations produce the schema the models expect.

The end-to-end tests drive a running FDS over HTTP and are excluded by default:

```bash
docker compose up -d --build
uv run pytest -m end_to_end
```

They assert only over HTTP, so the same suite runs against a deployment as its smoke test:

```bash
FDS_URL=https://api.example.org/api/v1 FDS_TOKEN=<jwt> uv run pytest -m end_to_end
```

Everything they create, they delete. Without a token the tests that write are skipped.

### Running Linting & Formatting

This project uses `ruff` for linting and formatting.

```bash
prek run
```

### Database Migrations

The schema is versioned with Alembic, and the migrations in `alembic/versions/` are the only thing
that creates or changes tables. The container image applies them before starting, so a fresh
database is built and an existing one brought up to date on every start. To run them yourself:

```bash
uv run alembic upgrade head
```

Any change to a `table=True` model needs a migration in the same change:

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic check   # passes only when the models and migrations agree
```

Review what is generated, and make sure `downgrade()` reverses it: rolling back a release that
migrated means downgrading before deploying the older image. CI runs `alembic check` and a
downgrade-and-re-apply cycle, so drift and irreversible migrations fail the build.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup, the checks CI runs, and the conventions we follow. Please open an issue before starting anything substantial.

Security problems should not be filed as issues. [SECURITY.md](SECURITY.md) explains how to report them privately.

## Licence

Copyright 2025-2026 UK Atomic Energy Authority.

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.

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

## Documentation

Published at **<https://ukaea.github.io/fds/>**, covering the data model, access control, provenance, and the DCAT / JSON-LD semantic projection. Built with [Zensical](https://zensical.org/) from the `docs/` directory and deployed by GitHub Actions on every push to `main`, so it does not depend on anyone running the demo.

To preview changes locally before opening a pull request:

```bash
uvx zensical serve
```

## Quick Start Demo

A self-contained demo environment is available in the `demo/` directory. It includes FDS, Keycloak, MinIO, a reference UI, and a [Marimo](https://marimo.io/) notebook for the live data-access workflows. The documentation is not part of the stack: it is published separately, so it stays available whether or not the demo is running.

### 1. Start the Environment

```bash
cd demo
# Using Docker
docker compose up --build
# OR using Podman
podman compose up --build
```

> **Podman + git worktrees:** the compose project name is always `demo`, so
> launching from a second worktree reuses the first's containers and can serve
> stale code. `demo/run.sh` forces a clean, current stack from whichever worktree
> you run it in. It's podman-only; docker users use the command above.

Services started:

- **FDS API**: `http://localhost:8000`
- **Keycloak**: `http://localhost:8080` (User/Pass: `admin`/`admin`)
- **MinIO**: `http://localhost:9000` (User/Pass: `admin`/`password`)

> **First run note:** On first launch, the demo automatically pulls real MAST shot data from the STFC public S3 store, which can take several minutes. Run without `-d` to see a progress bar in the terminal. Once downloaded, the data persists in a named volume (`demo_minio-data`) across restarts, so subsequent launches are fast. It survives `down`, but `down -v` deletes it and the next launch re-downloads everything.

Prefix any of the above with `FDS_DEMO_SEED=0` to come up with an empty catalog; populate it later with `uv run demo/generate_data.py` and `uv run demo/seed_metadata.py`.

To see request traces and browse them in Grafana, add the observability overlay:

```bash
docker compose -f docker-compose.yaml -f docker-compose.observability.yaml up --build
```

That adds Grafana on `http://localhost:3002` and turns on trace export and JSON log output. It is
off by default because it pulls a 2.5 GB image and adds around 700 MB of memory, roughly doubling
the footprint of the demo.

### 2. Explore

The stack **auto-populates** the catalog on startup: the `metadata-seeder` service runs `demo/seed_metadata.py` once FDS is healthy. Browse it at `http://localhost:3000`, via `GET /api/v1/devices/`, or read the docs at <https://ukaea.github.io/fds/>.

The docs walk through registering and reading data with copy-pasteable `curl` / Python / JavaScript examples. A few read-back workflows are best seen running live (storage-layer access enforcement, credential vending, and parallel Dask reads), and those are in a marimo notebook:

```bash
uvx marimo edit demo/explore.py --sandbox
```

To reseed the catalog by hand at any time:

```bash
uv run demo/seed_metadata.py
```

## Local Development Setup

This project uses `uv` for dependency management.

### Prerequisites

- Python 3.14+
- `uv` package manager
- `prek` for pre-commit checks

### Setup

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

- **Database**: Connection string for the metadata store.
- **Authentication**: IdP details (Issuer, Audience, JWKS URI).
- **Storage**: Credentials and bucket information for S3, GCS, or Azure.

## Development

### Running Tests

```bash
uv run pytest
```

This runs the unit and service tests only. Integration tests require the demo docker-compose stack to be running and are excluded by default:

```bash
# Start the demo stack first
podman compose -f demo/docker-compose.yaml up -d

# Then run integration tests
uv run pytest -m integration
```

Integration tests exercise the full stack: real HTTP calls to FDS, real Keycloak auth, and real MinIO storage.

### Running Linting & Formatting

This project uses `ruff` for linting and formatting.

```bash
prek run
```

### Database Migrations

Managed via `alembic`:

```bash
uv run alembic upgrade head
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup, the checks CI runs, and the conventions we follow. Please open an issue before starting anything substantial.

Security problems should not be filed as issues. [SECURITY.md](SECURITY.md) explains how to report them privately.

## Licence

Copyright 2025-2026 UK Atomic Energy Authority.

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.

# Fusion Data Service (FDS)

The Fusion Data Service (FDS) is a platform designed to provide scalable, FAIR-compliant access to fusion experiment metadata and data. It aligns with fusion community standards (like IMAS) to ensure interoperability and supports a flexible data hierarchy suitable for multimodal fusion research data.

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

Detailed architectural decisions for the Fusion Data Service are recorded as Architecture Decision Records (ADRs) in the [`docs/adrs/`](docs/adrs/) directory.

## Quick Start Demo

A self-contained demo environment is available in the `demo/` directory. It includes FDS, Keycloak, MinIO, a documentation site, and a [Marimo](https://marimo.io/) notebook for the live data-access workflows.

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
> you run it in. It's podman-only — docker users use the command above.

Services started:

- **FDS API**: `http://localhost:8000`
- **Keycloak**: `http://localhost:8080` (User/Pass: `admin`/`admin`)
- **MinIO**: `http://localhost:9000` (User/Pass: `admin`/`password`)

> **First run note:** On first launch, the demo automatically pulls real MAST shot data from the STFC public S3 store, which can take several minutes. Run without `-d` to see a progress bar in the terminal. Once downloaded, the data persists in `demo/minio-data/` across restarts, so subsequent launches are fast — unless you delete that directory.

Prefix any of the above with `FDS_DEMO_SEED=0` to come up with an empty catalog; populate it later with `uv run demo/generate_data.py` and `uv run demo/seed_metadata.py`.

### 2. Explore

The stack **auto-populates** the catalog on startup — the `metadata-seeder` service runs `demo/seed_metadata.py` once FDS is healthy. Browse it at `http://localhost:3000`, via `GET /api/v1/devices/`, or read the docs at `http://localhost:4001`.

The docs walk through registering and reading data with copy-pasteable `curl` / Python / JavaScript examples. A few read-back workflows are best seen running live — storage-layer access enforcement, credential vending, and parallel Dask reads — and those are in a marimo notebook:

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
    git clone <repository-url>
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

Integration tests exercise the full stack — real HTTP calls to FDS, real Keycloak auth, and real MinIO storage.

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

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

A self-contained demo environment is available in the `demo/` directory. It includes FDS, Keycloak, MinIO, and a [Marimo](https://marimo.io/) notebook to demonstrate the authentication and data access workflow.

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

### 2. Run the Demonstration Notebook

The `demonstration.py` notebook walks through the FDS workflow (Auth -> Registration -> Token Exchange -> Data Access).

```bash
# From the root of the repository
uvx marimo edit demo/demonstration.py --sandbox
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

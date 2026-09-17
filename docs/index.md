# Fusion Data Service

The **Fusion Data Service (FDS)** is a metadata catalog and access broker for fusion experiment data. It provides scalable, FAIR-compliant discovery and authenticated data access, aligned with fusion community standards (IMAS/DCAT).

## Key capabilities

| Capability | Description |
| --- | --- |
| **Metadata catalog** | Organises data into `Device → Shot → Dataset / Collection` hierarchies |
| **Provenance tracking** | Records who produced what, when, and from which inputs (PROV-O) |
| **Access control** | Public / Embargoed / Restricted with hierarchical inheritance |
| **Credential vending** | Issues short-lived STS tokens so clients never hold long-lived cloud keys (for data on cloud storage) |
| **Semantic metadata** | Full DCAT + PROV-O via `Accept: application/ld+json` content negotiation |
| **Federation** | Datasets from other catalogues and FDS instances can be included, improving findability |

## Running the demo

The demo stack runs FDS, Keycloak, MinIO, these docs, and the UI, and **auto-populates
the catalogue** on startup via the `metadata-seeder` service:

```bash
docker compose -f demo/docker-compose.yaml up -d --build   # or: podman compose -f demo/docker-compose.yaml up -d --build
```

To also collect request traces and browse them in Grafana, add the observability overlay:

```bash
docker compose -f demo/docker-compose.yaml -f demo/docker-compose.observability.yaml up -d --build
```

That puts Grafana on `http://localhost:3002`. It is off by default because it roughly doubles the
demo's memory use and adds a 2.5 GB image to the first download.

Give Keycloak a few seconds to finish importing its realm. The catalogue is then filled
with the example data used throughout these pages. To reseed by hand at any time:

```bash
uv run demo/seed_metadata.py
```

To start with an empty catalogue instead, set `FDS_DEMO_SEED=0` on that command. The
examples on these pages assume the seeded catalogue.

A few read-back workflows are best seen running live: storage-layer access enforcement,
credential vending, and parallel Dask reads. Those are in a marimo notebook:

```bash
uvx marimo edit demo/explore.py --sandbox
```

### Conventions for the examples

The code examples throughout these pages use a base-URL variable and, where a call needs
authentication, a bearer token from [Access Control →
Authentication](access-control.md#authentication):

- **Shell:** `API=http://localhost:8000/api/v1`, `TOKEN=<jwt>`
- **Python:** `API = "http://localhost:8000/api/v1"`, `headers = {"Authorization": f"Bearer {TOKEN}"}`
- **JavaScript:** `const API = "http://localhost:8000/api/v1"`, `const TOKEN = "<jwt>"`

Public reads need no token; creating data or reading restricted data does.

## Services in the demo environment

| Service | URL |
| --- | --- |
| FDS API (Swagger UI) | [http://localhost:8000/docs](http://localhost:8000/docs) |
| FDS API (ReDoc) | [http://localhost:8000/redoc](http://localhost:8000/redoc) |
| Keycloak (IdP) | [http://localhost:8080](http://localhost:8080), `admin` / `admin` |
| MinIO (object store) | [http://localhost:9001](http://localhost:9001), `admin` / `password` |
| Frontend UI | [http://localhost:3000](http://localhost:3000) |

## Where to start

- **[Access Control](access-control.md)**: authenticate (get a `TOKEN`), access levels, and credential vending
- **[Data Model](data-model/index.md)**: the hierarchy and core entities, and how to register them
- **[Provenance](provenance.md)**: how FDS tracks the origin of datasets
- **[Semantic Metadata](dcat-jsonld.md)**: DCAT / PROV-O and content negotiation

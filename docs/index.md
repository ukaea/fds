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

## Running FDS locally

The examples on these pages assume a local FDS holding a small example catalogue. From a checkout
of the repository:

```bash
uv run scripts/mint-token.py init --out-dir dev   # once: a key pair the stack trusts
docker compose up -d --build                      # or: podman compose up -d --build
```

FDS is then on `http://localhost:8000`. Reading public metadata needs no token; anything else
does, and you sign your own:

```bash
export TOKEN=$(uv run scripts/mint-token.py mint)
```

Then register the example catalogue these pages refer to. It registers two real MAST shots where
they already live at STFC, and metadata-only fixtures for a synthetic MAST-U shot, reference
geometry and calibration, and an annotated shot:

```bash
FDS_TOKEN=$TOKEN uv run scripts/seed-example-catalogue.py
```

No identity provider runs by default: see [Access Control](access-control.md#issuing-tokens-without-an-identity-provider)
for what signing your own tokens does and does not give you. To log in through the reference UI
instead, start the stack with `docker compose --profile ui up -d --build`, which adds Keycloak on
`http://localhost:8080` and the UI on `http://localhost:3000`.

No object store runs either, so credential vending has no real store to vend against; that is a
deployment concern.

To also collect request traces and browse them in Grafana, add the observability overlay:

```bash
docker compose -f compose.yaml -f compose.observability.yaml up -d --build
```

That puts Grafana on `http://localhost:3002`. It is off by default because it roughly doubles the
stack's memory use and adds a 2.5 GB image to the first download.

### Conventions for the examples

The code examples throughout these pages use a base-URL variable and, where a call needs
authentication, a bearer token from [Access Control →
Authentication](access-control.md#authentication):

- **Shell:** `API=http://localhost:8000/api/v1`, `TOKEN=<jwt>`
- **Python:** `API = "http://localhost:8000/api/v1"`, `headers = {"Authorization": f"Bearer {TOKEN}"}`
- **JavaScript:** `const API = "http://localhost:8000/api/v1"`, `const TOKEN = "<jwt>"`

Public reads need no token; creating data or reading restricted data does.

## Services in the local stack

| Service | URL |
| --- | --- |
| FDS API (OpenAPI explorer) | [http://localhost:8000/docs](http://localhost:8000/docs) |
| FDS API (ReDoc) | [http://localhost:8000/redoc](http://localhost:8000/redoc) |
| Keycloak, with `--profile idp` or `--profile ui` | [http://localhost:8080](http://localhost:8080), `admin` / `admin` |
| Reference UI, with `--profile ui` | [http://localhost:3000](http://localhost:3000) |

## Where to start

- **[Access Control](access-control.md)**: authenticate (get a `TOKEN`), access levels, and credential vending
- **[Data Model](data-model/index.md)**: the hierarchy and core entities, and how to register them
- **[Provenance](provenance.md)**: how FDS tracks the origin of datasets
- **[Semantic Metadata](dcat-jsonld.md)**: DCAT / PROV-O and content negotiation

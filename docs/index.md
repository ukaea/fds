# Fusion Data Service

The **Fusion Data Service (FDS)** is a metadata catalog and access broker for fusion experiment data. It provides scalable, FAIR-compliant discovery and authenticated data access, aligned with fusion community standards (IMAS/DCAT).

## Key capabilities

| Capability | Description |
| --- | --- |
| **Metadata catalog** | Organises data into `Device → Shot → Dataset / Collection` hierarchies |
| **Provenance tracking** | Records who produced what, when, and from which inputs (PROV-O) |
| **Access control** | Public / Embargoed / Restricted with hierarchical inheritance |
| **Credential vending** | Issues short-lived STS tokens so clients never hold long-lived cloud keys |
| **Semantic metadata** | Full DCAT + PROV-O via `Accept: application/ld+json` content negotiation |
| **Federation** | Datasets can be registered from remote FDS nodes and accessed transparently |

## Services in the demo environment

| Service | URL |
| --- | --- |
| FDS API (Swagger UI) | [http://localhost:8000/docs](http://localhost:8000/docs) |
| FDS API (ReDoc) | [http://localhost:8000/redoc](http://localhost:8000/redoc) |
| Keycloak (IdP) | [http://localhost:8080](http://localhost:8080) — `admin` / `admin` |
| MinIO (object store) | [http://localhost:9001](http://localhost:9001) — `admin` / `password` |
| Frontend UI | [http://localhost:3000](http://localhost:3000) |
| **These docs** | [http://localhost:4001](http://localhost:4001) |

## Where to start

- **[Data Model](concepts/data-model.md)** — understand the hierarchy and core entities
- **[Provenance](concepts/provenance.md)** — how FDS tracks the origin of datasets
- **[Access Control](concepts/access-control.md)** — access levels and credential vending
- **[Semantic Metadata](concepts/dcat-jsonld.md)** — DCAT / PROV-O and content negotiation
- **[Demo walkthrough](demo/walkthrough.md)** — annotated guide to the demonstration notebook

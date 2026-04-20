# Semantic Metadata (DCAT & JSON-LD)

FDS exposes its metadata as proper linked data via HTTP content negotiation. This satisfies the **Findable** and **Interoperable** pillars of FAIR. See [ADR-0009](../adrs/0009-content-negotiation-for-dcat.md) and [ADR-0019](../adrs/0019-two-tier-schema-driven-semantic-projection.md).

## Content negotiation

The same endpoint serves two representations depending on the `Accept` header:

| `Accept` header | Response format | Use case |
|---|---|---|
| `application/json` (default) | FDS relational JSON | Application code, API clients |
| `application/ld+json` | JSON-LD mapped to DCAT + PROV-O | Catalogues, semantic search, DOI registration |

```http
GET /api/v1/datasets/id/{uuid}
Accept: application/ld+json
```

## Dataset vs Distribution

The standard JSON API returns a **denormalised convenience view**: `url`, `media_type`, and `format` are inlined directly on the Dataset object. This is intentional — the common case of "give me the access URL" is a single JSON field.

Under the hood, however, FDS follows the [W3C DCAT ontology](https://www.w3.org/TR/vocab-dcat/):

- A **`dcat:Dataset`** is a conceptual entity — *what* the data is.
- A **`dcat:Distribution`** is a physical access path — *how* to get it.

When you request `application/ld+json`, FDS re-separates these back into the correct DCAT structure. The inlined `url` and `media_type` fields re-emerge as a `dcat:Distribution` node nested inside the `dcat:Dataset`.

```json
{
  "@context": {"dcat": "https://www.w3.org/ns/dcat#", ...},
  "@type": "dcat:Dataset",
  "@id": "http://localhost:8000/api/v1/datasets/id/abc123",
  "dct:title": "Equilibrium — Shot 30421",
  "dcat:downloadURL": "s3://fds-data/shots/30421/equilibrium",
  "dcat:distribution": [
    {
      "@type": "dcat:Distribution",
      "dcat:downloadURL": "s3://fds-data/shots/30421/equilibrium",
      "dcat:mediaType": "application/x-zarr"
    }
  ],
  "prov:wasGeneratedBy": {
    "@type": "prov:Activity",
    "prov:wasAssociatedWith": {"@id": "…/sources/efit"}
  }
}
```

## Collection as `dcat:Catalog`

A **Collection** maps to `dcat:Catalog`. Requesting a collection endpoint with `Accept: application/ld+json` returns the catalog document with member datasets listed as `dcat:dataset` references and the provenance Activity embedded as `prov:wasGeneratedBy`.

```http
GET /api/v1/devices/mast/shots/30420/collections/jintrac-v220922
Accept: application/ld+json
```

## Ontology mapping summary

| FDS concept | DCAT / PROV-O term |
|---|---|
| Dataset | `dcat:Dataset` |
| Distribution (inlined) | `dcat:Distribution` |
| Collection | `dcat:Catalog` |
| Source | `prov:SoftwareAgent` |
| Activity | `prov:Activity` |
| "dataset produced by" | `prov:wasGeneratedBy` |
| "activity used input" | `prov:used` |
| "activity ran agent" | `prov:wasAssociatedWith` |

## FAIR alignment

| FAIR principle | FDS mechanism |
|---|---|
| **Findable** | Stable URIs (`/datasets/id/{uuid}`), rich metadata, JSON-LD catalogues |
| **Accessible** | OIDC auth, STS credential vending, open API |
| **Interoperable** | IMAS/IDS naming conventions, DCAT + PROV-O linked data |
| **Reusable** | Provenance graph, access level declarations, citable Collections |

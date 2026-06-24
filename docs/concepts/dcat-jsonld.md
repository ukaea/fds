# Semantic Metadata (DCAT & JSON-LD)

FDS exposes its metadata as proper linked data via HTTP content negotiation. This satisfies the **Findable** and **Interoperable** pillars of FAIR. See [ADR-0009](../adrs/0009-content-negotiation-for-dcat.md) and [ADR-0019](../adrs/0019-two-tier-schema-driven-semantic-projection.md).

## Content negotiation

The same endpoint serves two representations depending on the `Accept` header:

| `Accept` header | Response format | Use case |
| --- | --- | --- |
| `application/json` (default) | FDS relational JSON | Application code, API clients |
| `application/ld+json` | JSON-LD mapped to DCAT + PROV-O | Catalogues, semantic search, DOI registration |

JSON-LD is supported on **Device**, **Shot**, **Dataset**, and **Collection** endpoints:

```http
GET /api/v1/devices/{device}
GET /api/v1/devices/{device}/shots/{shot_id}
GET /api/v1/datasets/id/{id}
GET /api/v1/devices/{device}/shots/{shot_id}/collections/{name}
Accept: application/ld+json
```

## Dataset vs Distribution

FDS follows the [W3C DCAT ontology](https://www.w3.org/TR/vocab-dcat/): a **`dcat:Dataset`** is the abstract metadata entity describing *what* the data is, while a **`dcat:Distribution`** is a concrete physical access path describing *how* to retrieve it.

The standard JSON API returns a **denormalised convenience view** where the primary distribution's `url`, `media_type`, and `format` are inlined directly on the Dataset object. A Dataset can be registered without any distributions (metadata-first); distributions are added via `POST /datasets/{id}/distributions`. Multiple distributions are supported — for example, the same data as HDF5 and CSV — provided all distributions are scientifically interchangeable.

When you request `application/ld+json`, FDS re-separates these back into the correct DCAT structure. Each distribution emits `dcat:accessURL` (required by DCAT 3). The value depends on the URL scheme:

- **Public HTTPS** (e.g. `https://s3.echo.stfc.ac.uk/…`): `dcat:accessURL` and `dcat:downloadURL` both point to the URL — it is directly accessible.
- **Cloud storage** (`s3://`, `gs://`, `az://`): `dcat:accessURL` points to the FDS dataset endpoint, which is where clients obtain credentials. `dcat:downloadURL` carries the raw storage URI for use with a protocol-specific client (e.g. `xarray`, `fsspec`).

```json
{
  "@context": {"dcat": "http://www.w3.org/ns/dcat#", "...": "..."},
  "@type": "dcat:Dataset",
  "@id": "http://localhost:8000/api/v1/datasets/id/42",
  "dct:title": "Equilibrium — Shot 30421",
  "dcat:distribution": [
    {
      "@type": "dcat:Distribution",
      "dcat:accessURL": "http://localhost:8000/api/v1/datasets/id/42",
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

## Shot as `dcat:Dataset`

A **Shot** maps to `dcat:Dataset`. Requesting a shot endpoint with `Accept: application/ld+json` returns a document that includes the experimental temporal coverage, creator, and scientific metadata. Temporal coverage is emitted as a `dct:PeriodOfTime`: a closed period (`startDate`+`endDate`) when an end is known or derivable from `shot_duration`, or an open period (`startDate` only) when just `shot_at` is set, as below:

```http
GET /api/v1/devices/mast/shots/30421
Accept: application/ld+json
```

```json
{
  "@context": {
    "dct": "http://purl.org/dc/terms/",
    "dcat": "http://www.w3.org/ns/dcat#",
    "prov": "http://www.w3.org/ns/prov#",
    "schema": "https://schema.org/",
    "...": "..."
  },
  "@type": "dcat:Dataset",
  "@id": "http://localhost:8000/api/v1/devices/mast/shots/30421",
  "title": "Shot 30421",
  "identifier": "30421",
  "dct:temporal": {
    "@type": "dct:PeriodOfTime",
    "startDate": "2008-11-18T14:32:00+00:00"
  },
  "dct:creator": "MAST Team",
  "accessRights": "public",
  "schema:additionalProperty": [
    {
      "@type": "schema:PropertyValue",
      "schema:name": "plasma_current",
      "schema:value": 0.4,
      "schema:unitText": "MA"
    },
    {
      "@type": "schema:PropertyValue",
      "schema:name": "confinement_mode",
      "schema:value": "L-mode"
    }
  ]
}
```

## Collection as `dcat:Catalog`

A **Collection** maps to `dcat:Catalog`. Requesting a collection endpoint with `Accept: application/ld+json` returns the catalog document with member datasets listed as `dcat:dataset` references and the provenance Activity embedded as `prov:wasGeneratedBy`.

```http
GET /api/v1/devices/mast/shots/30420/collections/jintrac-v220922
Accept: application/ld+json
```

## Namespaces

| Prefix | URI | Used for |
| --- | --- | --- |
| `dcat` | `http://www.w3.org/ns/dcat#` | Core DCAT terms (Dataset, Distribution, Catalog) |
| `dct` | `http://purl.org/dc/terms/` | Dublin Core (title, creator, publisher, temporal) |
| `prov` | `http://www.w3.org/ns/prov#` | PROV-O provenance (Activity, wasGeneratedBy) |
| `xsd` | `http://www.w3.org/2001/XMLSchema#` | Typed literals (dateTime) |
| `schema` | `https://schema.org/` | Scientific metadata properties (`schema:PropertyValue`) |
| `dqv` | `http://www.w3.org/ns/dqv#` | Data quality annotations (`dqv:hasQualityAnnotation`) |
| `oa` | `http://www.w3.org/ns/oa#` | Web Annotation, used by `dqv:QualityAnnotation` (`oa:motivatedBy`, `oa:hasBody`) |

## Ontology mapping summary

| FDS concept / field | JSON-LD term | Ontology |
| --- | --- | --- |
| Dataset | `dcat:Dataset` | DCAT 3 |
| Distribution (inlined) | `dcat:Distribution` | DCAT 3 |
| Distribution access service | `dcat:accessURL` | DCAT 3 |
| Distribution direct download | `dcat:downloadURL` | DCAT 3 |
| Collection | `dcat:Catalog` | DCAT 3 |
| Shot | `dcat:Dataset` | DCAT 3 |
| Device | `dcat:Catalog` | DCAT 3 |
| Source | `prov:SoftwareAgent` | PROV-O |
| Activity | `prov:Activity` | PROV-O |
| "dataset produced by" | `prov:wasGeneratedBy` | PROV-O |
| "activity used input" | `prov:used` | PROV-O |
| "activity ran agent" | `prov:wasAssociatedWith` | PROV-O |
| `publisher` | `dct:publisher` | Dublin Core |
| `creator` | `dct:creator` | Dublin Core |
| `shot_at` / `shot_end` / `shot_duration` | `dct:temporal` → `dct:PeriodOfTime` | Dublin Core / DCAT 3 |
| `temporal_start` / `temporal_end` | `dct:temporal` → `dct:PeriodOfTime` | Dublin Core / DCAT 3 |
| `quality_flag` | `dqv:hasQualityAnnotation` | W3C DQV |
| `scientific_metadata` | `schema:additionalProperty` / `schema:PropertyValue` | schema.org |

## FAIR alignment

| FAIR principle | FDS mechanism |
| --- | --- |
| **Findable** | Stable URIs (`/datasets/id/{id}`), rich metadata, JSON-LD catalogues, `schema:PropertyValue` indexable by Google Dataset Search |
| **Accessible** | OIDC auth, STS credential vending, open API |
| **Interoperable** | IMAS/IDS naming conventions, DCAT + PROV-O + schema.org linked data |
| **Reusable** | Provenance graph, access level declarations, citable Collections, controlled vocabularies |

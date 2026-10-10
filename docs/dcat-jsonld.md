# Semantic Metadata (DCAT & JSON-LD)

FDS exposes its metadata as proper linked data via HTTP content negotiation. This satisfies the **Findable** and **Interoperable** pillars of FAIR.

## Content negotiation

The same endpoint serves two representations depending on the `Accept` header:

| `Accept` header | Response format | Use case |
| --- | --- | --- |
| `application/json` (default) | FDS relational JSON | Application code, API clients |
| `application/ld+json` | JSON-LD mapped to DCAT + PROV-O | Catalogues, semantic search, DOI registration |

JSON-LD is supported on **Device**, **Shot**, **Dataset**, and **Collection** endpoints:

```http
GET /v1/devices/{device}
GET /v1/devices/{device}/shots/{shot_id}
GET /v1/datasets/id/{id}
GET /v1/devices/{device}/shots/{shot_id}/collections/{name}
Accept: application/ld+json
```

## Identifiers

The `@id` of every entity is the name FDS publishes for it: what another catalogue stores when it
harvests from here, what provenance links point at, and what a DOI resolves to. Those names are
served, and they carry no API version:

```http
GET /datasets/{id}
GET /collections/{id}
GET /sources/{id}
GET /activities/{id}
GET /devices/{device}
GET /devices/{device}/shots/{shot_id}
```

A version belongs to the contract between the service and a client, not to a dataset, so putting
one in the name would give the same dataset a second identifier every time the API moved on. The
versioned endpoints above are addresses for clients to read and write through; they are never
published as identifiers.

### Persistent identifiers

A record can also carry an identifier registered for it elsewhere, in `persistent_identifier`:
a DOI for a dataset, collection or shot, an instrument identifier (PIDINST) for a device or
diagnostic, ORCID for a person, ROR for an organisation. FDS stores it; registering it is up
to the record's owners.

Give it as an absolute URI or in compact form: `doi:`, `hdl:` and `swh:` are expanded to their
resolvers. It is published as `adms:identifier`, while `dct:identifier` stays FDS's own:

```json
{
  "@id": "https://example.org/datasets/13",
  "identifier": "13",
  "adms:identifier": {
    "@type": "adms:Identifier",
    "skos:notation": {"@value": "https://doi.org/10.5072/example", "@type": "xsd:anyURI"}
  }
}
```

A value in any other form is published exactly as given and is not turned into a link.

A dataset, collection or shot can also record when it was formally published, in `issued`.
That is the date a citation gives, published as the resource's own `dct:issued`
(`{"@value": "2024-03-01", "@type": "xsd:date"}`). It is distinct from the catalogue record's
`issued`, which is when FDS listed the resource.

When a dataset or collection was generated is not a field of its own: it is when the activity
that produced it ended. The JSON-LD states it on the resource as `prov:generatedAtTime`, taken
from that activity's `ended_at`, and omits it when there is no activity or it has no end.

### Where identifiers point

An identifier names the **service**, not its API. A deployment typically answers on two addresses:

| Address | What is there |
| --- | --- |
| `https://example.org` | the service, navigable in a browser |
| `https://api.example.org` | the REST API, which the browser interface itself uses |

A dataset is therefore named `https://example.org/datasets/13`, and `FDS_BASE_URL` is how
the API is told the service's address.

!!! warning "Set this in production"

    Left empty, identifiers are built from the address each caller used to reach FDS, which the
    request carries in its `Host` header: what they dialled, not where they dialled from. That is
    correct when FDS is reached directly, which is how it runs in development, and unreliable
    behind anything that terminates TLS: the request then genuinely arrives as plain HTTP from inside the
    network, and the proxy's assertion that it began as HTTPS is honoured only if that proxy is
    trusted (`FORWARDED_ALLOW_IPS`). Get that wrong and every identifier is published with the
    wrong scheme. Nothing fails, the responses are well-formed, and the wrong names are what other
    catalogues copy.

    FDS logs a warning when it sees a request carrying forwarded headers it did not trust while no
    address is configured. Setting `FDS_BASE_URL` removes the guess entirely, and is the
    reason to prefer it over tuning the proxy's trust.

What answers at `https://example.org/datasets/13` is the deployment's business. A browser
interface serves a page there and passes `application/ld+json` requests through to the API; where
there is no interface, the API answers those paths itself with the JSON-LD above. This matters for
DOIs, which must land a reader on something readable: registering one means having an interface
that answers the identifier.

## The resource and FDS's record of it

A Device, Shot, Dataset or Collection document holds two nodes in an `@graph`. One is the
resource, carrying what its provider said about it. The other is a `dcat:CatalogRecord`: FDS's
entry for that resource, saying when FDS listed it (`dct:issued`) and when FDS last changed the
entry (`dct:modified`).

```json
{
  "@context": { "...": "..." },
  "@graph": [
    {
      "@type": "dcat:Catalog",
      "@id": "https://example.org/devices/mast/shots/28352",
      "title": "Shot 28352",
      "dct:temporal": {"@type": "dct:PeriodOfTime", "startDate": "2012-01-27T15:52:00+00:00"}
    },
    {
      "@type": "dcat:CatalogRecord",
      "@id": "https://example.org/devices/mast/shots/28352#record",
      "foaf:primaryTopic": {"@id": "https://example.org/devices/mast/shots/28352"},
      "issued": "2026-09-28T13:55:58+00:00",
      "modified": "2026-10-01T15:46:07+00:00"
    }
  ]
}
```

The two are kept apart because they are claims about different things. Shot 28352 happened in
2012 and nothing about it has changed since; FDS listed it in 2026 and has edited its entry.
Putting FDS's dates on the shot would say the shot was created in 2026. The resource node therefore
carries no creation or modification date of its own, and a shot's one date is its temporal
coverage.

The record has no route of its own: its identifier is the resource's with `#record` appended, so it
resolves to the document that holds it. A catalogue that lists other resources, such as the
catalogue of devices, embeds their nodes without their records.

## Dataset vs Distribution

FDS follows the [W3C DCAT ontology](https://www.w3.org/TR/vocab-dcat/): a **`dcat:Dataset`** is the abstract metadata entity describing *what* the data is, while a **`dcat:Distribution`** is a concrete physical access path describing *how* to retrieve it.

The standard JSON API returns a **denormalised convenience view** where the primary distribution's `url`, `group`, `conforms_to`, `media_type`, and `format` are inlined directly on the Dataset object. A Dataset can be registered without any distributions (metadata-first); distributions are added via `POST /datasets/{id}/distributions`. Multiple distributions are supported, for example the same data as HDF5 and CSV, provided all of them carry the same information.

When you request `application/ld+json`, FDS re-separates these back into the correct DCAT structure. Each distribution emits `dcat:accessURL` (required by DCAT 3). The value depends on the URL scheme:

- **Public HTTPS** (e.g. `https://s3.echo.stfc.ac.uk/…`): `dcat:accessURL` and `dcat:downloadURL` both point to the URL, which is directly accessible.
- **Cloud storage** (`s3://`, `gs://`, `az://`): `dcat:accessURL` points to the FDS dataset endpoint, which is where clients obtain credentials. `dcat:downloadURL` carries the raw storage URI for use with a protocol-specific client (e.g. `xarray`, `fsspec`).

A distribution's `conforms_to` is published as `dct:conformsTo`, naming the schema the copy follows. Two distributions of one Dataset can follow different schemas, such as two versions of the IMAS Data Dictionary.

A distribution's `group` is not published. DCAT has no term for a part of a file, so a distribution that is one group of a larger file appears in JSON-LD as the whole file. The JSON API carries the group.

```json
{
  "@context": {"dcat": "http://www.w3.org/ns/dcat#", "...": "..."},
  "@type": "dcat:Dataset",
  "@id": "http://localhost:8000/datasets/42",
  "dct:title": "Equilibrium (Shot 30421)",
  "dcat:distribution": [
    {
      "@type": "dcat:Distribution",
      "dcat:accessURL": "http://localhost:8000/v1/datasets/id/42",
      "dcat:downloadURL": "s3://fds-data/shots/30421/equilibrium",
      "dcat:mediaType": "application/x-zarr"
    }
  ],
  "prov:wasGeneratedBy": {
    "@type": "prov:Activity",
    "prov:wasAssociatedWith": {"@id": "…/sources/efit", "@type": "prov:SoftwareAgent"},
    "prov:qualifiedAssociation": [
      {"@type": "prov:Association", "prov:agent": {"@id": "…/sources/efit"}, "prov:hadRole": "executor"}
    ],
    "prov:qualifiedUsage": [
      {"@type": "prov:Usage", "prov:entity": {"@id": "…/datasets/3"}, "prov:hadRole": "input"}
    ]
  }
}
```

## Shot as `dcat:Catalog`

A **Shot** maps to `dcat:Catalog`. A shot holds no data itself. The data sits in the Datasets and Collections that carry its `shot_id`, and each of those has its own download URL, so a shot never gets one. Calling it a `dcat:Dataset` would promise something to download. In DCAT 3 a `dcat:Catalog` is a kind of `dcat:Dataset`, so nothing is lost: temporal coverage, creator, scientific metadata and access rights are all still valid. It also puts a shot alongside the Device above it and the Collections beside it, all three being catalogs.

This document does not list the shot's datasets, because there can be any number of them. Ask the dataset listing for them instead, which is paged. Requesting a shot endpoint with `Accept: application/ld+json` returns a document that includes the experimental temporal coverage, creator, and scientific metadata. Temporal coverage is emitted as a `dct:PeriodOfTime`: a closed period (`startDate`+`endDate`) when an end is known or derivable from `shot_duration`, or an open period (`startDate` only) when just `shot_at` is set, as below:

=== "curl"

    ```bash
    curl -H "Accept: application/ld+json" "$API/devices/mast/shots/30421"
    ```

=== "Python (requests)"

    ```python
    doc = requests.get(
        f"{API}/devices/mast/shots/30421",
        headers={"Accept": "application/ld+json"},
    ).json()
    ```

=== "Python (httpx)"

    ```python
    doc = httpx.get(
        f"{API}/devices/mast/shots/30421",
        headers={"Accept": "application/ld+json"},
    ).json()
    ```

=== "JavaScript (fetch)"

    ```javascript
    const doc = await (
      await fetch(`${API}/devices/mast/shots/30421`, {
        headers: { Accept: "application/ld+json" },
      })
    ).json();
    ```

The response:

```json
{
  "@context": {
    "dct": "http://purl.org/dc/terms/",
    "dcat": "http://www.w3.org/ns/dcat#",
    "prov": "http://www.w3.org/ns/prov#",
    "schema": "https://schema.org/",
    "...": "..."
  },
  "@type": "dcat:Catalog",
  "@id": "http://localhost:8000/devices/mast/shots/30421",
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

## Collection as catalogue and entity

A **Collection** is typed as both `dcat:Catalog` and `prov:Collection`, so its `@type` is an array. The two vocabularies answer different questions and both are wanted: DCAT catalogues it for discovery, publisher and distribution, while PROV makes it an entity whose contents and origin can be reasoned over. A consumer must therefore read `@type` as a list rather than a string.

Requesting a collection endpoint with `Accept: application/ld+json` returns the catalog document with members listed twice over: as `dcat:dataset` and `dcat:catalog` references, and as `prov:hadMember` for the provenance view. The producing Activity is embedded as `prov:wasGeneratedBy`.

=== "curl"

    ```bash
    curl -H "Accept: application/ld+json" \
      "$API/devices/mast/shots/30420/collections/jintrac-v220922"
    ```

=== "Python (requests)"

    ```python
    catalog = requests.get(
        f"{API}/devices/mast/shots/30420/collections/jintrac-v220922",
        headers={"Accept": "application/ld+json"},
    ).json()
    ```

=== "Python (httpx)"

    ```python
    catalog = httpx.get(
        f"{API}/devices/mast/shots/30420/collections/jintrac-v220922",
        headers={"Accept": "application/ld+json"},
    ).json()
    ```

=== "JavaScript (fetch)"

    ```javascript
    const catalog = await (
      await fetch(`${API}/devices/mast/shots/30420/collections/jintrac-v220922`, {
        headers: { Accept: "application/ld+json" },
      })
    ).json();
    ```

## Provenance graph

The standard JSON response carries `activity_id` on each Dataset. Requesting a Dataset as
`application/ld+json` instead returns its full PROV-O provenance graph: the producing
Activity, the agents it was associated with, the entities it used, and the upstreams the
dataset was derived from.

=== "curl"

    ```bash
    curl -H "Accept: application/ld+json" "$API/datasets/id/$DATASET_ID"
    ```

=== "Python (requests)"

    ```python
    doc = requests.get(
        f"{API}/datasets/id/{dataset_id}",
        headers={"Accept": "application/ld+json"},
    ).json()
    ```

=== "Python (httpx)"

    ```python
    doc = httpx.get(
        f"{API}/datasets/id/{dataset_id}",
        headers={"Accept": "application/ld+json"},
    ).json()
    ```

=== "JavaScript (fetch)"

    ```javascript
    const doc = await (
      await fetch(`${API}/datasets/id/${datasetId}`, {
        headers: { Accept: "application/ld+json" },
      })
    ).json();
    ```

The response carries:

| Term | Carries |
| --- | --- |
| `prov:wasGeneratedBy` | the producing Activity, embedded, with its own `@id` to follow |
| `prov:qualifiedUsage` | each entity the run used, with its title and role: an input dataset or an instrument |
| `prov:qualifiedAssociation` | each agent, typed by its kind, with its role in the run, and for the executor the version it ran as `prov:hadPlan` |
| `prov:actedOnBehalfOf` | delegation between two of those agents |
| `prov:wasDerivedFrom` | each upstream entity the dataset was derived from |
| `prov:qualifiedDerivation` | the same, tied to the Activity that caused it, where there is one |

Every `prov:hadRole` is a reference to a role concept rather than a plain string, so a consumer
can resolve what a role means instead of pattern-matching a label:

```json
"prov:qualifiedAssociation": [{
  "@type": "prov:Association",
  "prov:agent": {"@id": "https://fds.example/sources/12"},
  "prov:hadRole": {"@id": "fuel:executor"},
  "prov:hadPlan": {"@type": "prov:Plan", "dcat:version": "v2.3.1"}
}]
```

The version belongs to the run, not to the agent: two runs of the same code at different versions
share one agent and differ only in their plans. The plan has no address of its own; it is part of
the run's description.

A derived-from upstream is identified as far as it can be. A registered dataset resolves to its
FDS address, a DOI or other persistent identifier to a resolvable URI, and an upstream that can
only be described appears as a node with no address at all, carrying just its title and
description. The document is explicit about which of those you have.

See [Provenance](provenance.md) for the model behind these terms.

## Namespaces

| Prefix | URI | Used for |
| --- | --- | --- |
| `dcat` | `http://www.w3.org/ns/dcat#` | Core DCAT terms (Dataset, Distribution, Catalog) |
| `dct` | `http://purl.org/dc/terms/` | Dublin Core (title, creator, publisher, temporal) |
| `prov` | `http://www.w3.org/ns/prov#` | PROV-O provenance (Activity, wasGeneratedBy) |
| `xsd` | `http://www.w3.org/2001/XMLSchema#` | Typed literals (dateTime) |
| `schema` | `https://schema.org/` | Scientific metadata properties (`schema:PropertyValue`) |
| `dqv` | `http://www.w3.org/ns/dqv#` | Data quality annotations (`dqv:hasQualityAnnotation`) |
| `foaf` | `http://xmlns.com/foaf/0.1/` | `foaf:primaryTopic`, linking a catalogue record to the resource it describes |
| `oa` | `http://www.w3.org/ns/oa#` | Web Annotation, used by `dqv:QualityAnnotation` (`oa:motivatedBy`, `oa:hasBody`) |
| `adms` | `http://www.w3.org/ns/adms#` | `adms:identifier`, a persistent identifier registered elsewhere |
| `skos` | `http://www.w3.org/2004/02/skos/core#` | `skos:notation`, the value of that identifier |
| `fuel` | `https://w3id.org/fuel/ns#` | Fusion Energy Lexicon, the role concepts used by `prov:hadRole` and `dcat:hadRole` |

## Ontology mapping summary

| FDS concept / field | JSON-LD term | Ontology |
| --- | --- | --- |
| Dataset | `dcat:Dataset` | DCAT 3 |
| Distribution (inlined) | `dcat:Distribution` | DCAT 3 |
| Distribution access service | `dcat:accessURL` | DCAT 3 |
| Distribution direct download | `dcat:downloadURL` | DCAT 3 |
| Collection | `dcat:Catalog` and `prov:Collection` | DCAT 3, PROV-O |
| Shot | `dcat:Catalog` | DCAT 3 |
| Device | `dcat:Catalog` | DCAT 3 |
| Source (`kind=software`/`person`/`organization`) | `prov:SoftwareAgent` / `prov:Person` / `prov:Organization` | PROV-O |
| Source (`kind=instrument`) | `prov:Entity` (used with role `instrument`) | PROV-O |
| Activity | `prov:Activity` | PROV-O |
| "dataset produced by" | `prov:wasGeneratedBy` | PROV-O |
| "activity used input / instrument" | `prov:used` + `prov:qualifiedUsage` (`prov:hadRole`) | PROV-O |
| "activity associated with agent" | `prov:wasAssociatedWith` + `prov:qualifiedAssociation` (`prov:hadRole`) | PROV-O |
| `persistent_identifier` | `adms:identifier` → `adms:Identifier` | ADMS, DCAT-AP |
| `issued` (publication date) | `dct:issued` on the resource | Dublin Core, DCAT 3 |
| producing Activity's `ended_at` | `prov:generatedAtTime` on the resource | PROV-O |
| `publisher` | `dct:publisher` | Dublin Core |
| `creator` | `dct:creator` | Dublin Core |
| `shot_at` / `shot_end` / `shot_duration` | `dct:temporal` → `dct:PeriodOfTime` | Dublin Core / DCAT 3 |
| `temporal_start` / `temporal_end` | `dct:temporal` → `dct:PeriodOfTime` | Dublin Core / DCAT 3 |
| `quality_flag` | `dqv:hasQualityAnnotation` | W3C DQV |
| `created_at` (when FDS listed the resource) | `dct:issued` on its `dcat:CatalogRecord` | DCAT 3, Dublin Core |
| `updated_at` (when FDS last changed the entry) | `dct:modified` on its `dcat:CatalogRecord` | DCAT 3, Dublin Core |
| `scientific_metadata` | `schema:additionalProperty` / `schema:PropertyValue` | schema.org |

## FAIR alignment

| FAIR principle | FDS mechanism |
| --- | --- |
| **Findable** | Stable URIs (`/datasets/id/{id}`), rich metadata, JSON-LD catalogues, `schema:PropertyValue` indexable by Google Dataset Search |
| **Accessible** | OIDC auth, STS credential vending, open API |
| **Interoperable** | IMAS/IDS naming conventions, DCAT + PROV-O + schema.org linked data |
| **Reusable** | Provenance graph, access level declarations, citable Collections, controlled vocabularies |

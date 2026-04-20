# Access Control

FDS implements layered access control across the data hierarchy. See [ADR-0008](../adrs/0008-three-tier-data-access-levels.md) and [ADR-0010](../adrs/0010-tiered-data-access-strategy.md) for the full rationale.

## Access levels

| Level | Metadata visible? | Data accessible? |
|---|---|---|
| `public` | Yes (unauthenticated) | Yes (unauthenticated) |
| `embargoed` | Yes (discoverable) | Only to authorised users |
| `restricted` | Only to authenticated users | Only to authorised users |

The global default is **restricted** — anything not explicitly marked otherwise is invisible to unauthenticated requests.

## Hierarchical inheritance

Access levels cascade down the hierarchy. A more specific level overrides a less specific one:

```
Device (access_level = public)
└── Shot (access_level = not set → inherits public)
    ├── Dataset (access_level = not set → inherits public)
    └── Dataset (access_level = restricted → restricted wins)
```

This means you can open an entire Device to the public with a single flag while still protecting individual sensitive shots or datasets.

## Authentication

FDS delegates identity to an external OIDC Identity Provider (Keycloak in the demo). Clients obtain a JWT via the standard OIDC flow and include it as a `Bearer` token:

```http
Authorization: Bearer <jwt>
```

FDS validates the token against the IdP's JWKS endpoint and extracts the user's identity and granted scopes. See [ADR-0007](../adrs/0007-externalized-identity-and-trust-registry.md).

## Credential vending (STS token pattern)

FDS does **not** hold long-lived cloud credentials on behalf of users. Instead, it vends **short-lived STS tokens** at query time.

When a client requests a dataset with `include_storage_options=true`, FDS:

1. Evaluates the user's effective access level for that dataset.
2. Calls the cloud provider's STS endpoint to obtain a scoped, time-limited token.
3. Embeds the token and endpoint URL directly into the dataset response as `storage_options`.

The client (or its workers) can then open the data directly using any cloud-native library without ever handling a long-lived key:

```python
import xarray as xr

ds_meta = fds_client.get_dataset(..., include_storage_options=True)
xr.open_dataset(ds_meta["url"], engine="zarr", storage_options=ds_meta["storage_options"])
```

## Bulk access: the Credential Manifest

For high-throughput workflows (thousands of datasets), requesting one token per dataset would create an API bottleneck and hit IAM policy size limits. FDS resolves this with the **Credential Manifest** pattern ([ADR-0011](../adrs/0011-credential-manifest-pattern.md)):

The response contains two parts:

1. **Tokens list** — a deduplicated set of time-limited tokens, chunked to stay within IAM limits.
2. **Resource map** — a lookup table mapping each dataset URI to the index of the token required to access it.

Worker nodes (Dask, Ray, Spark, etc.) receive the lightweight manifest and independently select the right token for each dataset they process. No further API calls are needed.

```
Tokens:  [token_A, token_B]
Map:     {ds_uri_1 → 0, ds_uri_2 → 0, ds_uri_3 → 1, …}
```

## What FDS does NOT do

FDS is a **metadata catalog and access broker** — it does not manage or enforce bucket policies on the underlying object store. The data owner is responsible for configuring the storage backend to match the access levels declared in FDS. FDS simply refuses to vend credentials for resources the requesting user is not authorised to access.

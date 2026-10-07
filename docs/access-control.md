# Access Control

FDS applies a layered access **policy** across the data hierarchy. These levels govern two things FDS itself controls: what metadata it exposes, and whether it will **vend storage credentials** for the underlying data. They do *not* make FDS the gatekeeper of the data bytes. That is enforced by the access policy of whereever the data are stored, which the data owner keeps in step with these levels (see [What FDS does NOT do](#what-fds-does-not-do)).

## Access levels

| Level | Metadata (catalog API) | Storage credentials from FDS |
| --- | --- | --- |
| `public` | Visible to everyone, unauthenticated | Vended to anyone, anonymous-compatible, no token needed |
| `embargoed` | Discoverable by everyone, unauthenticated | Vended only to authorised users |
| `restricted` | Visible only to authorised users | Vended only to authorised users |

The global default is **restricted**, so anything not explicitly marked otherwise is invisible to unauthenticated requests.

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

FDS delegates identity to an external OIDC Identity Provider. Clients obtain a JWT via the standard OIDC flow and include it as a `Bearer` token:

```http
Authorization: Bearer <jwt>
```

With the `idp` profile running, Keycloak issues tokens via the OIDC password grant. This
obtains one and stashes it as `TOKEN` / `headers` for the examples on the other pages (without it,
sign your own as described below):

=== "curl"

    ```bash
    export TOKEN=$(curl -s http://localhost:8080/realms/fds/protocol/openid-connect/token \
      -d client_id=fds-client -d client_secret=fds-client-secret \
      -d username=admin -d password=password \
      -d grant_type=password -d scope='openid profile fds-admin' \
      | jq -r .access_token)
    ```

=== "Python (requests)"

    ```python
    import requests

    resp = requests.post(
        "http://localhost:8080/realms/fds/protocol/openid-connect/token",
        data={
            "client_id": "fds-client",
            "client_secret": "fds-client-secret",
            "username": "admin",
            "password": "password",
            "grant_type": "password",
            "scope": "openid profile fds-admin",
        },
    )
    resp.raise_for_status()
    TOKEN = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {TOKEN}"}
    ```

=== "Python (httpx)"

    ```python
    import httpx

    resp = httpx.post(
        "http://localhost:8080/realms/fds/protocol/openid-connect/token",
        data={
            "client_id": "fds-client",
            "client_secret": "fds-client-secret",
            "username": "admin",
            "password": "password",
            "grant_type": "password",
            "scope": "openid profile fds-admin",
        },
    )
    resp.raise_for_status()
    TOKEN = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {TOKEN}"}
    ```

=== "JavaScript (fetch)"

    ```javascript
    const res = await fetch(
      "http://localhost:8080/realms/fds/protocol/openid-connect/token",
      {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          client_id: "fds-client",
          client_secret: "fds-client-secret",
          username: "admin",
          password: "password",
          grant_type: "password",
          scope: "openid profile fds-admin",
        }),
      },
    );
    const TOKEN = (await res.json()).access_token;
    ```

FDS validates the token against the IdP's JWKS endpoint and extracts the user's identity and granted scopes.

### Where FDS finds an issuer's keys

A token is trusted when it is signed by a key belonging to an issuer in `FDS_TRUSTED_IDPS`, so
FDS has to have that issuer's public keys. It gets them in one of three ways, per issuer:

| Configuration | Where the keys come from |
| --- | --- |
| `{"issuer": "https://idp.example.org"}` | Discovery: FDS fetches `{issuer}/.well-known/openid-configuration`, then the `jwks_uri` it advertises. The usual case. |
| `{"issuer": "...", "jwks_uri": "http://idp-internal:8080/realms/fds/protocol/openid-connect/certs"}` | The given URL. For when FDS reaches the provider at a different address from the one written in the token, as on a container network. The `iss` claim must still match `issuer` exactly. |
| `{"issuer": "...", "jwks_file": "/etc/fds/local-issuer.jwks.json"}` | A file on disk. No identity provider is contacted. |

Keys are cached for ten minutes however they are obtained, so replacing a file takes effect
within that window.

### Which scopes FDS accepts from an issuer

Each issuer lists `allowed_scopes`, the scopes FDS accepts from its tokens, as shell-style
patterns: `["mast:*", "openid"]`, or `["*"]` for every scope it issues. Any other scope in a
token is dropped. An issuer with no `allowed_scopes` passes none through: its users are
authenticated but carry no scopes, so they hold no role and cannot read anything a scope gates.
Trusting another organisation's identity provider therefore brings in none of its scopes until
you list the ones you accept. Listing `["*"]` for it would let it issue `fds-admin`.

### Issuing tokens without an identity provider

`jwks_file` exists so that a deployment can be administered before, or without, a working
identity provider: seeding a new catalogue, running an ingestion job, or getting in when the
provider is down. You hold an RSA private key, FDS holds the matching public key, and you sign
short-lived tokens yourself. The repository ships a script for both halves:

```bash
# once: writes the private key and the public key set
uv run scripts/mint-token.py init --out-dir dev

# then, whenever a token is needed
uv run scripts/mint-token.py mint --key dev/local-issuer.key --scope fds-admin --minutes 15
```

Point FDS at the public half and trust the issuer:

```bash
FDS_TRUSTED_IDPS='[{"issuer":"urn:fds:local","jwks_file":"dev/local-issuer.jwks.json","allowed_scopes":["*"]}]'
FDS_OIDC_AUDIENCE=fds-client
```

Such tokens go through exactly the same checks as any other: signature, audience, expiry, and
scope filtering. Actions taken with one are recorded in the audit trail with
`actor_issuer: urn:fds:local`, so they are distinguishable from actions taken by people who
signed in.

!!! warning "This is a bootstrap and break-glass path, not a way for people to log in"

    Anyone holding the private key can mint a token for any subject with any scope, bypassing
    whatever sign-in controls your organisation applies: no multi-factor authentication, no
    account suspension when somebody leaves. A minted token cannot be withdrawn before it
    expires; revocation means removing the issuer from `FDS_TRUSTED_IDPS` and restarting, which
    invalidates every token from that key at once.

    Keep the private key off the server and out of version control, keep lifetimes short
    (minutes), and give people accounts with your identity provider instead.

## Credential vending

FDS does **not** hold long-lived cloud credentials on behalf of users. Instead, it vends **short-lived tokens** at query time.

When a client requests a dataset with `include_storage_options=true`, FDS:

1. Evaluates the user's effective access level for that dataset.
2. Uses the appropriate cloud provider service to obtain a scoped, time-limited token. For example, STS, for s3 storage.
3. Embeds the token and endpoint URL directly into the dataset response as `storage_options`.

Request a dataset with `include_storage_options=true` and the vended credentials come back
inline under `storage_options`:

=== "curl"

    ```bash
    curl -s -H "Authorization: Bearer $TOKEN" \
      "$API/devices/mastu/shots/50000/datasets/thomson-raw?include_storage_options=true"
    ```

=== "Python (requests)"

    ```python
    meta = requests.get(
        f"{API}/devices/mastu/shots/50000/datasets/thomson-raw",
        headers=headers,
        params={"include_storage_options": True},
    ).json()[0]
    # meta["storage_options"] holds short-lived, scoped credentials
    ```

=== "Python (httpx)"

    ```python
    meta = httpx.get(
        f"{API}/devices/mastu/shots/50000/datasets/thomson-raw",
        headers=headers,
        params={"include_storage_options": True},
    ).json()[0]
    # meta["storage_options"] holds short-lived, scoped credentials
    ```

=== "JavaScript (fetch)"

    ```javascript
    const res = await fetch(
      `${API}/devices/mastu/shots/50000/datasets/thomson-raw?include_storage_options=true`,
      { headers: { Authorization: `Bearer ${TOKEN}` } },
    );
    const [meta] = await res.json();
    // meta.storage_options holds short-lived, scoped credentials
    ```

The client (or its workers) then open the data directly with any cloud-native library,
never handling a long-lived key:

```python
import xarray as xr

ds = xr.open_dataset(
    meta["url"], engine="h5netcdf", storage_options=meta["storage_options"]
)
```

Vending needs a configured provider (`FDS_STORAGE_PROVIDERS`) whose `endpoint_url` matches the
dataset's distribution. The local stack configures none, so these requests show the shape of the
exchange without returning credentials for a real store.

## Bulk access: the Credential Manifest

Requesting credentials one dataset at a time costs a round trip per dataset, and one set of
credentials cannot cover an unlimited number of objects. An IAM session policy has a size limit, so
there is a ceiling on how many prefixes a single token can name. For workflows that open many
datasets at once, `POST /v1/file-access/credentials` vends for a whole set in one request.

The request body selects what to vend for. At least one of `device_name`, `shot_id` and
`data_urls` has to be given: a body naming none of them vends nothing, so that a stray empty
request cannot ask for the whole catalogue.

=== "curl"

    ```bash
    curl -s -X POST -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"device_name": "mast", "shot_id": "30421"}' \
      "$API/file-access/credentials"
    ```

=== "Python (requests)"

    ```python
    manifest = requests.post(
        f"{API}/file-access/credentials",
        headers=headers,
        json={"device_name": "mast", "shot_id": "30421"},
    ).json()
    ```

Besides `device_name` and `shot_id`, the body accepts `data_urls` to name specific dataset URLs.

The response is a single `resource_map`, keyed by dataset URL, whose value is the credential for
that URL:

```json
{
  "resource_map": {
    "s3://mast/level2/shots/30421.zarr/thomson_scattering": {
      "access_key_id": "...",
      "secret_access_key": "...",
      "session_token": "...",
      "expiration": "2026-09-23T16:04:05Z",
      "endpoint_url": "https://s3.echo.stfc.ac.uk",
      "region": null,
      "storage_options": null
    },
    "s3://mast/level2/shots/30421.zarr/equilibrium": { "...": "..." }
  }
}
```

Worker nodes (Dask, Ray, Spark) receive the manifest and each look up the URL they are about to
open. No further API calls are needed.

Azure and GCS datasets carry their own credential fields rather than the S3 set above:
`account_name` and `sas_token` for Azure, `token` and `expiry` for GCS. One manifest can mix them, because FDS
resolves a provider per storage endpoint.

### What the server does with the request

FDS groups the requested URLs by storage endpoint and mints in chunks, so the number of calls it
makes to each storage provider grows with the number of chunks rather than with the number of
datasets, and each token's policy names only the prefixes in its own chunk. That is server-side
behaviour, and the manifest does not expose it: a credential covering several datasets is repeated
in full under each of their URLs, so the response grows linearly with the number of datasets
requested.

### Opener-ready storage options

Ask for `include_storage_options=true` and every entry carries `storage_options` as well as the
raw credential, in the same opener-ready shape the single-dataset path returns.

```python
import requests

# One request covers every dataset on the shot.
resource_map = requests.post(
    f"{API}/file-access/credentials",
    headers=headers,
    params={"include_storage_options": True},
    json={"device_name": "mast", "shot_id": "30421"},
).json()["resource_map"]

url = "s3://mast/level2/shots/30421.zarr/thomson_scattering"
```

A worker looks up the URL it was given and hands that entry's `storage_options` to its opener.

=== "fsspec (xarray, zarr, dask, pyarrow)"

    ```python
    ds = xr.open_dataset(
        url, engine="zarr", storage_options=resource_map[url]["storage_options"]
    )
    ```

=== "icechunk"

    ```python
    storage = icechunk.s3_storage(
        bucket="mast",
        prefix="level2/shots/30421.zarr",
        **resource_map[url]["storage_options"],
    )
    ```

FDS picks the shape per URL from that distribution's [`storage_options_type`](data-model/dataset.md#how-the-data-is-opened): `fsspec_s3` for the
s3fs family, `icechunk_s3` for `icechunk.s3_storage`. It also fills in the two settings that belong
to the endpoint rather than the credential, and that a hand-written mapping tends to miss:
`allow_http` for a plain `http://` endpoint, and `force_path_style` for an S3-compatible endpoint
that is not AWS. Against a non-AWS store, a missing `force_path_style` is the usual cause of a
connection that resolves but cannot find the bucket.

Azure and GCS entries carry their one shape instead: `account_name` and `sas_token` for adlfs,
`token` for gcsfs. A distribution whose `storage_options_type` is null is opened by its URL
directly, so it gets a credential and no `storage_options`.

Two things stay yours to supply.

**`bucket` and `prefix`.** FDS leaves them unset because only the caller knows which URL it is
opening: a Distribution's own `url` for a standalone Zarr, or a Collection's `root_url` for an
IceChunk store that holds the Distribution as a group.

**A fresh manifest when `expiration` passes.** It is the credential's lifetime, not a hint. A
worker holding a manifest across a long job has to request a new one rather than retry on failure.

As with the single-dataset path, vending needs a configured provider whose `endpoint_url` matches
the distribution, and the local stack configures none. These examples show the shape of the
exchange rather than something that runs against `compose.yaml` as shipped.

## What FDS does NOT do

FDS is a **metadata catalog and access broker**. It does not manage or enforce access policies on the underlying data store. The data owner is responsible for configuring the storage backend to match the access levels declared in FDS. FDS simply refuses to vend credentials for resources the requesting user is not authorised to access.

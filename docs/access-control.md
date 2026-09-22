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

FDS delegates identity to an external OIDC Identity Provider (Keycloak in the demo). Clients obtain a JWT via the standard OIDC flow and include it as a `Bearer` token:

```http
Authorization: Bearer <jwt>
```

In the demo, Keycloak issues tokens via the OIDC password grant. This obtains one and
stashes it as `TOKEN` / `headers` for the examples on the other pages:

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
FDS_TRUSTED_IDPS='[{"issuer":"urn:fds:local","jwks_file":"dev/local-issuer.jwks.json"}]'
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

See this run end-to-end, including the storage-layer denial when credentials are withheld,
in the `demo/explore.py` notebook (`uvx marimo edit demo/explore.py --sandbox`).

## Bulk access: the Credential Manifest

For high-throughput workflows (thousands of datasets), requesting one token per dataset would create an API bottleneck and hit IAM policy size limits. FDS resolves this with a **Credential Manifest**:

The response contains two parts:

1. **Tokens list**: a deduplicated set of time-limited tokens, chunked to stay within IAM limits.
2. **Resource map**: a lookup table mapping each dataset URI to the index of the token required to access it.

Worker nodes (Dask, Ray, Spark, etc.) receive the lightweight manifest and independently select the right token for each dataset they process. No further API calls are needed.

Each value in the map is a **0-based position in the `Tokens` list**:

```
Tokens:  [token_A, token_B]      # index 0 → token_A, index 1 → token_B
Map:     {ds_uri_1 → 0, ds_uri_2 → 0, ds_uri_3 → 1}
```

So `ds_uri_1` and `ds_uri_2` both resolve to `token_A`, and `ds_uri_3` to `token_B`.

The `demo/explore.py` notebook exercises this with a 4-worker Dask cluster reading every
group of a MAST-U `icechunk` store in parallel from a single vended manifest.

## What FDS does NOT do

FDS is a **metadata catalog and access broker**. It does not manage or enforce access policies on the underlying data store. The data owner is responsible for configuring the storage backend to match the access levels declared in FDS. FDS simply refuses to vend credentials for resources the requesting user is not authorised to access.

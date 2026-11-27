# Source

A Source is a global, reusable registry entry for the things that produce data: analysis codes, diagnostic systems, schedulers, people and organisations.

A Source is not one kind of thing in the provenance graph. Its `kind` decides what it becomes, which is why a diagnostic and an analysis code are registered the same way but appear differently in the lineage.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | Yes | Unique identifier for the source (e.g. `efit`, `jintrac`) |
| `description` | string | No | Extended description of the code or diagnostic |
| `kind` | enum | Yes | `software`, `instrument`, `person`, or `organization`. See below |
| `persistent_identifier` | string | No | ORCID for a person, ROR for an organisation, PIDINST for an instrument, a DOI or Software Heritage ID for software. See [Persistent identifiers](../dcat-jsonld.md#persistent-identifiers) |
| `device_name` | string | No | Optionally link the source to a device; global if omitted |
| `access_level` | enum | No | `public`, `embargoed`, or `restricted`. A source has no data, so `embargoed` reads as `public`. Inherits from the linked device if null; a source linked to no device is restricted |
| `read_roles` | list[string] | No | Roles that may read a restricted source. Inherits from the linked device if null |
| `write_roles` | list[string] | No | Roles that may change or delete the source; only `fds-admin` sets it. Inherits from the linked device if null |
| `allowed_idps` | list[string] | No | Trusted identity-provider issuers. Inherits from the linked device if null |

## Kinds

| `kind` | Example | Becomes | How it attaches to an Activity |
| --- | --- | --- | --- |
| `software` | EFIT, JINTRAC, a scheduler | a software agent | associated with the Activity, carrying a role |
| `instrument` | a Thomson scattering system | an entity | the Activity *used* it, in the `instrument` role |
| `person` | an operator, a principal investigator | a person | associated with, or attributed the data |
| `organization` | a diagnostic group, a facility | an organisation | associated with, or delegated to |

In particular, specifying when a source is an `instrument` is important. A diagnostic is a tool, not something that bears responsibility for a result, so it is an entity an Activity *used* rather than an agent the Activity was associated with. Because an instrument is an entity, measured data needs an Activity to attach it to. There is no direct link from a dataset to the instrument that produced it.

Register it once; reuse it across every Activity:

=== "curl"

    ```bash
    curl -X POST "$API/sources/" \
      -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      -d '{"name": "efit", "description": "EFIT equilibrium reconstruction code",
           "kind": "software", "access_level": "public"}'
    ```

=== "Python (requests)"

    ```python
    source = requests.post(
        f"{API}/sources/",
        headers=headers,
        json={
            "name": "efit",
            "description": "EFIT equilibrium reconstruction code",
            "kind": "software",
            "access_level": "public",
        },
    ).json()
    ```

=== "Python (httpx)"

    ```python
    source = httpx.post(
        f"{API}/sources/",
        headers=headers,
        json={
            "name": "efit",
            "description": "EFIT equilibrium reconstruction code",
            "kind": "software",
            "access_level": "public",
        },
    ).json()
    ```

=== "JavaScript (fetch)"

    ```javascript
    const source = await (
      await fetch(`${API}/sources/`, {
        method: "POST",
        headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          name: "efit",
          description: "EFIT equilibrium reconstruction code",
          kind: "software",
          access_level: "public",
        }),
      })
    ).json();
    ```

Read a source with `GET /sources/{id}`. A restricted source is shown only to callers holding one of its roles, and is left out of the runs that name it for everyone else; see [Sources](../access-control.md#sources). To find one by name, filter the listing: `GET /sources/?name=efit` gives a page holding that source, or an empty page if no source has the name.

See [Provenance](../provenance.md) for how a Source connects to the Activities and the Datasets they generate.

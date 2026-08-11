# Shot

A single plasma discharge on a Device.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | string | Yes | Shot ID/number (e.g. `30421`) |
| `device_name` | string | No | Parent device (taken from the URL path) |
| `shot_at` | datetime | No | When the plasma discharge began — distinct from `created_at` (the catalogue record timestamp) |
| `shot_end` | datetime | No | When the discharge ended |
| `shot_duration` | float | No | Discharge duration in seconds; must equal `shot_end − shot_at` when both are set |
| `t0_at` | datetime | No | Wall-clock instant of the shot's relative time base zero (`t=0`), e.g. plasma breakdown; may differ from `shot_at`. Provider-declared and optional; FDS stores it but never applies it to convert event times or assume datasets share a time base |
| `description` | string | No | Extended description |
| `publisher` | string | No | Institution making the data available (`dct:publisher`) |
| `creator` | string | No | Person or team who conducted the experiment (`dct:creator`) |
| `access_level` | enum | No | `public`, `embargoed`, or `restricted`; overrides device default if set |
| `required_scopes` | list[string] | No | OAuth scopes required when access is `restricted` |
| `allowed_idps` | list[string] | No | Trusted identity-provider issuers; inherits from device if null |
| `scientific_metadata` | list | No | Experimental conditions — see [Scientific metadata](index.md#scientific-metadata) below |

Shots are created under their parent device:

=== "curl"

    ```bash
    curl -X POST "$API/devices/mast/shots" \
      -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      -d '{"id": "30421", "device_name": "mast", "access_level": "public"}'
    ```

=== "Python (requests)"

    ```python
    requests.post(
        f"{API}/devices/mast/shots",
        headers=headers,
        json={"id": "30421", "device_name": "mast", "access_level": "public"},
    ).raise_for_status()
    ```

=== "Python (httpx)"

    ```python
    httpx.post(
        f"{API}/devices/mast/shots",
        headers=headers,
        json={"id": "30421", "device_name": "mast", "access_level": "public"},
    ).raise_for_status()
    ```

=== "JavaScript (fetch)"

    ```javascript
    await fetch(`${API}/devices/mast/shots`, {
      method: "POST",
      headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({ id: "30421", device_name: "mast", access_level: "public" }),
    });
    ```

## Listing and filtering

Shots are listed under their device, and can be filtered by feature annotation:

```text
GET /api/v1/devices/mast/shots
GET /api/v1/devices/mast/shots?annotation=disruption
GET /api/v1/devices/mast/shots?annotation=confinement_mode:H-mode
```

See [Finding annotated records](index.md#finding-annotated-records) for the full syntax.

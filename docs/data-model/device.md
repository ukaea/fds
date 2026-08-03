# Device

Represents a physical machine or facility.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | Yes | Short, unique name (e.g. `mast`, `mast-upgrade`) |
| `title` | string | No | Human-readable label |
| `description` | string | No | Extended description |
| `type` | string | No | Machine type (`tokamak`, `stellarator`, …) |
| `publisher` | string | No | Institution making the device catalog available (`dct:publisher`) |
| `creator` | string | No | Person or team responsible for the device (`dct:creator`) |
| `access_level` | enum | No | Default access level inherited by Shots and Datasets |

Register one with a `POST` (see [Access Control → Authentication](../access-control.md#authentication)
for `TOKEN`):

=== "curl"

    ```bash
    curl -X POST "$API/devices/" \
      -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      -d '{"name": "mast", "title": "Mega Ampere Spherical Tokamak", "type": "tokamak",
           "description": "Spherical tokamak experiment at UKAEA Culham, studying plasma confinement at low aspect ratio.",
           "access_level": "public"}'
    ```

=== "Python (requests)"

    ```python
    requests.post(
        f"{API}/devices/",
        headers=headers,
        json={
            "name": "mast",
            "title": "Mega Ampere Spherical Tokamak",
            "type": "tokamak",
            "description": "Spherical tokamak experiment at UKAEA Culham, studying plasma confinement at low aspect ratio.",
            "access_level": "public",
        },
    ).raise_for_status()
    ```

=== "Python (httpx)"

    ```python
    httpx.post(
        f"{API}/devices/",
        headers=headers,
        json={
            "name": "mast",
            "title": "Mega Ampere Spherical Tokamak",
            "type": "tokamak",
            "description": "Spherical tokamak experiment at UKAEA Culham, studying plasma confinement at low aspect ratio.",
            "access_level": "public",
        },
    ).raise_for_status()
    ```

=== "JavaScript (fetch)"

    ```javascript
    await fetch(`${API}/devices/`, {
      method: "POST",
      headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "mast",
        title: "Mega Ampere Spherical Tokamak",
        type: "tokamak",
        description: "Spherical tokamak experiment at UKAEA Culham, studying plasma confinement at low aspect ratio.",
        access_level: "public",
      }),
    });
    ```

# Searching Other Catalogues

FDS can search other catalogues as well as its own. When a search arrives, FDS asks each catalogue it is configured with, its **members**, and reports what each one answers. It keeps none of their records: a member's records stay where they are, as current as the member keeps them, and each one's address leads to the member.

Whoever runs FDS chooses the members (see [Operations](operations.md#federation)). So far a member can be another FDS, recent enough to answer its dataset listings in JSON-LD.

In the reference UI, a shot's page lists the datasets each member holds on that shot, and the Simulations page lists each member's simulated datasets with the page's filters. Both come after this FDS's own datasets, member by member, and each card opens the dataset in its own catalogue.

## Asking the members

The federated listings follow FDS's own dataset listings, under `/v1/federation`:

```http
GET /v1/federation/members
GET /v1/federation/datasets
GET /v1/federation/devices/{device}/datasets
GET /v1/federation/devices/{device}/shots/{shot_id}/datasets
```

Each takes the filters and paging of the dataset listing it follows, and each member applies them to its own records. For example, to ask every member for the simulated datasets on MAST shot 30421:

```http
GET /v1/federation/devices/mast/shots/30421/datasets?activity_type=simulation
```

`offset` and `limit` page through each member's datasets separately. `activity_id` and the `include_*` options are not offered, since they refer to records in this FDS. A member that has no such device or shot answers with no datasets.

## The answer

```json
{
  "@context": { "...": "..." },
  "answers": [
    {
      "member": {"id": "https://fds.example.org", "title": "Example FDS"},
      "status": "answered",
      "datasets": [
        {
          "@id": "https://fds.example.org/datasets/51",
          "@type": "dcat:Dataset",
          "title": "Core profiles",
          "fuel:device": "mast",
          "fuel:shot": "30421",
          "prov:wasGeneratedBy": { "...": "..." }
        }
      ]
    },
    {
      "member": {"id": "https://other.example.org", "title": "Other FDS"},
      "status": "failed",
      "detail": "did not answer in time",
      "datasets": []
    }
  ]
}
```

- **One answer per member**, in the order the members are listed. FDS does not merge the members' datasets or sort them together.
- **Datasets are JSON-LD `dcat:Dataset` nodes.** FDS rewrites each with its own `@context`, so the terms it knows read as they do in its own records, and terms it does not know keep their full IRIs. A dataset's `@id` is the member's identifier for it.
- **A member that fails is reported**, with `status` `failed` and the reason in `detail`: it did not answer in time, answered with an HTTP error, could not be reached, or did not answer in JSON-LD that FDS can read.
- **The members are asked at the same time**, so a search takes as long as the slowest of them, up to the timeout set in `FDS_FEDERATION_TIMEOUT`.

## Who sees what

FDS asks its members anonymously. The datasets listed are the ones each member shows anyone, whoever is asking, so a member's restricted datasets are never listed here, even to someone who may read them at that member.

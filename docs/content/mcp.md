# MCP Server

FDS answers the [Model Context Protocol](https://modelcontextprotocol.io) (MCP) at `/mcp`, so an LLM client can search the catalogue for you. Ask "which MAST shots reached a plasma current above 900 kA?" and the client looks up which properties the shots record and in which units, searches on them, and lists the shots it found with a link to each.

The server only reads. Its tools call FDS's own API, inside FDS, with the token that came with the client's request. The client sees what the token's holder would see through the API, and only public records when no token comes with the request. Each read a tool makes is logged as an API request under the caller's identity (see [Logging & Auditing](logging.md)).

A result read without a token carries `not_signed_in`, which says the answer covers public records only and where the client can log in. The server's instructions ask the model to pass that on, so a search that left out restricted records does not read as if the catalogue held nothing more.

## Connecting a client

The server's address is the API's address followed by `/mcp`, such as `https://api.fds.example.org/mcp`. Add the server to your MCP client by that address. Without logging in, its tools read public records.

### Logging in

To read restricted records, log in to the server through your MCP client. The client learns where from the server's own document, `/.well-known/oauth-protected-resource/mcp` (see [Access Control](access-control.md#how-a-program-finds-where-to-log-in)), and opens a browser at the login service. Once you have logged in, the client renews the token itself.

The login service may ask the client for a client ID: the name under which that login service knows MCP clients. Whoever runs your FDS tells you which, and you give it to your client once, when you add the server.

When a token comes with a request, the server checks it first. A token FDS would not accept, such as one that has expired, is answered `401`, which tells the client to get a fresh one.

A client that cannot log in can instead send a token you already hold, in an `Authorization: Bearer` header with every request. It then has to be replaced by hand when it expires.

## Tools

| Tool | What it returns |
| --- | --- |
| `list_devices` | The devices the catalogue holds records for. |
| `describe_shot_properties` | The properties a device's shots record, with their units and values. |
| `find_property_values` | The values one property takes, most common first, for a property with too many values to list. |
| `search_shots` | Shots matching filters and bounds on their properties. |
| `get_shot` | One shot with its properties, datasets and collections. |
| `search_datasets` | Datasets by name, by their own properties, by their shot's properties, or by the Activity that produced them. |
| `get_dataset` | One dataset with its distributions, the Activity that produced it and the datasets it was derived from. |
| `search_collections` | Collections by device, shot, name or property. |
| `get_collection` | One collection with its datasets and the collections inside it. |
| `open_dataset_code` | Python that opens a dataset with xarray (see [Opening data](#opening-data)). |

A listing returns at most 50 records a call, and gives `next_offset` when there are more.

When a question does not say which device, `describe_shot_properties` and `search_shots` ask you to choose one, if the catalogue holds more than one device and the client can show you a question. A client that cannot gets an error that names the devices, and asks you itself.

## Resources

A resource is a record the client can add to a conversation, in clients that offer resources.

| Address | What it holds |
| --- | --- |
| `fds://devices` | The devices. |
| `fds://shots/{device}/{shot}` | One shot, as `get_shot` returns it. |
| `fds://datasets/{id}` | One dataset, as `get_dataset` returns it. |
| `fds://collections/{id}` | One collection, as `get_collection` returns it. |

## Prompts

A prompt is a ready-made request, in clients that offer prompts.

| Prompt | What it asks for |
| --- | --- |
| `find_shots <device> <question>` | The device's shots that answer the question, in a table with the filters used. |
| `explain_dataset <id>` | What a dataset holds, what produced it and how to open it. The dataset's record comes with the request. |

Device names and shot IDs are suggested as you type them.

## Opening data

`open_dataset_code` returns Python that opens a dataset's default distribution with xarray. It opens Zarr, NetCDF and HDF5; for a distribution in any other format it gives the data's address instead.

- For a public dataset, the code carries the storage options FDS gives for anonymous access.
- For any other dataset, the code asks FDS for short-lived credentials when it runs (`POST /v1/file-access/credentials`), with a token it reads from the `FDS_TOKEN` environment variable wherever it runs.

The code reaches FDS at the address the client used for `/mcp`. Behind a proxy that ends TLS, that address starts with `https` only if FDS trusts the proxy's forwarded headers (`FORWARDED_ALLOW_IPS`, see [Operations](operations.md#serving)).

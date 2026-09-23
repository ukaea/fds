# Provenance

FDS tracks provenance using the **PROV-O ontology**, making the origin of every dataset auditable and reproducible.

## The core idea

A **Source** is the registry of things that produce data, but a Source is *not* a single PROV class. What a Source becomes in the graph depends on its `kind`:

| `Source.kind` | Example | PROV-O projection |
| --- | --- | --- |
| `software` | EFIT, JINTRAC, a scheduler | `prov:SoftwareAgent` |
| `instrument` | a Thomson scattering system | `prov:Entity`: a device an activity *used* (it has no agency) |
| `person` | an operator, a PI | `prov:Person` |
| `organization` | a diagnostic group | `prov:Organization` |

The other two primitives are unchanged:

| PROV-O term | FDS entity | Description |
| --- | --- | --- |
| `prov:Activity` | **Activity** | A *specific execution*, with timestamps, version, and parameters |
| `prov:Entity` | **Dataset** / **Collection** | The data produced |

A passive instrument is a *tool*, not an agent, so it is an Entity the run **used**, never an agent it `wasAssociatedWith`. Only software, people, and organisations bear responsibility.

## Two planes

Provenance edges fall into two planes:

- **Lineage**: *where did this data come from?* `Dataset wasGeneratedBy Activity`, `Activity used Entity` (input datasets and instruments), `Dataset wasDerivedFrom Dataset` (asserted by the producer, never inferred).
- **Responsibility**: *who is responsible?* `Activity wasAssociatedWith Agent` (each with a role), `Agent actedOnBehalfOf Agent`.

Coordination, for example a scheduler that triggers analysis codes, lives in the **responsibility** plane: the scheduler is an agent associated with the run (role `orchestrator`), never part of the data lineage. The code it coordinated records that it `actedOnBehalfOf` the scheduler, a `delegation` on that run.

## Declaring provenance

An Activity declares its whole provenance in a single request: the datasets it consumed, the instruments it used, the agents involved and any delegation between them. It can equally be built up afterwards, which suits a pipeline that registers a run before it can resolve its inputs. See [Data Model → Activity](data-model/activity.md) for the fields, the sub-resource endpoints and worked examples in four languages, and [Data Model → Source](data-model/source.md) for registering the agents and instruments a run refers to.

Output datasets and collections join a run by setting their `activity_id`. What a dataset was *derived from* is recorded separately, on the dataset itself, since a run's inputs and any one output's dependencies are not the same thing. See [Data Model → Dataset](data-model/dataset.md#recording-a-datasets-provenance).

## Kinds vs roles

`kind` (`instrument`, `software`, …) is a closed, typo-proof enum because it decides an entry's PROV node *type*.

**Roles** say what a thing did in one particular run, and they are closed too. Two qualify a `used` edge: `input` (the run consumed this dataset) and `instrument` (the run used this apparatus). Two qualify a `wasAssociatedWith` edge: `executor` (the agent that carried the run out) and `orchestrator` (the agent that coordinated it without executing it). You supply the agent role as a bare token, for example `role=orchestrator`; in the JSON-LD each role serialises as a vocabulary concept reference rather than a plain string, so a consumer can resolve what it means.

## Relationships

- Each **Dataset** records the Activity that produced it (`prov:wasGeneratedBy`).
- Each **Activity** records the agents it was associated with, each in a role (`prov:wasAssociatedWith`), and the entities it used: input datasets and instruments (`prov:used`).
- A **Dataset** records the upstream entities it was derived from, asserted rather than inferred (`prov:wasDerivedFrom`). An upstream need not be registered in FDS, so a DOI or even a description is enough to record one.
- A **Collection** can record a producing Activity too, so the whole output of a single run can be cited as one unit.

## Example: Thomson scattering

```text
Agents:      thomson-analysis (software)    intershot-scheduler (software)
Instrument:  thomson-scattering (kind=instrument → an Entity)
Activities:  acquisition                     analysis run
Entities:    raw_thomson                     T_e_profile

raw_thomson  wasGeneratedBy  acquisition   (which used the thomson device, role=instrument)
T_e_profile  wasGeneratedBy  analysis      (which used raw_thomson, role=input)
analysis     wasAssociatedWith  thomson-analysis (role=executor)
                              + intershot-scheduler (role=orchestrator)
thomson-analysis  actedOnBehalfOf  intershot-scheduler   (delegation, within this run)
```

## Querying provenance

Request `application/ld+json` to get the full PROV-O graph as linked data. See [Semantic Metadata → Provenance graph](dcat-jsonld.md#provenance-graph).

```http
GET /v1/datasets/id/{id}
Accept: application/ld+json
```

A dataset's standard JSON already carries `activity_id`. The linked-data response embeds `prov:wasGeneratedBy` with the run's `prov:qualifiedUsage` (roled inputs and instruments) and `prov:qualifiedAssociation` (roled agents, each typed by its kind).

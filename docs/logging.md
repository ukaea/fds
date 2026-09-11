# Logging and Auditing

FDS keeps a record of what happens to the catalogue: what went wrong, who changed what, and who
accessed data that was not open to everyone.

This page describes what is recorded, what is deliberately not recorded, and how an operator
controls it. It applies to any FDS instance; where the records are kept and for how long is
decided by whoever runs it.

## What is recorded

### What went wrong

Diagnostic messages, for the people running the service. A failed request records what failed,
which endpoint it was, and a full stack trace. These exist to get a bug fixed and are of no
interest once it is.

### Who changed what

Every create, update and delete leaves a record naming the person who made it, the thing they
changed, and which fields they changed.

For most fields only the name of the field is recorded, not its contents. So changing a
description records that the description changed, and nothing about what it now says. Access
policy fields are the exception: for those, both the old and new values are kept, because
"who opened this up, and when" is the question the record exists to answer.

A change that fails partway through, and is undone, records nothing. Only changes that actually
took effect are kept.

### Who accessed restricted data

Access is recorded at three levels of closeness:

| Level | Meaning |
| --- | --- |
| Appeared in a search | The item was one of the results of a listing or search |
| Opened | The item was fetched on its own |
| Downloaded | Credentials were issued to read the actual data files |

The first two are recorded only for **restricted** items, which are those whose metadata is
hidden from people without permission. Public and embargoed items are not recorded, because
their metadata is visible to everyone and no permission is involved. Embargoed data itself is
still protected, and any download of it is recorded.

Downloads are recorded at every access level, including public, since that is the point where
someone reaches the data rather than the description of it.

## How people are identified

FDS never records your name, your email address or your username.

When you sign in, your identity provider tells FDS who you are. FDS immediately converts that
into a fixed-length code by hashing it, and stores only the code. For example, a login might be
recorded as:

```text
actor_id=f7052ccfe8d443e523a549a36784e518c1162be037602208855df13b2a62d4bc
```

The same person always produces the same code, so it is possible to see that one person made a
series of changes. The code cannot be turned back into an identity by anyone reading the logs.
Requests made without signing in are recorded as `anonymous`.

## What is never recorded

- Descriptions, titles and scientific metadata values.
- The contents of any data file.
- Passwords, tokens, keys and credentials. Anything whose name suggests it is sensitive is
  replaced with `[redacted]` before the line is written, and this applies to messages from the
  underlying libraries as well as from FDS itself.

## For operators

### It is all one stream

Everything FDS records goes to standard output, as one JSON object per line. There is no second
stream, no error channel, no file. Records from FDS, from the web server and from the database
layer all pass through the same formatting, so a collector only ever has to parse one shape.

FDS does not write log files, rotate them or delete them. Whatever runs FDS captures that output,
and where it goes from there is your decision.

**Lines do not interleave.** Python serialises writes to the stream, so two requests being handled
at the same time cannot produce a mangled line, even when one of them is writing a several
kilobyte stack trace. Each line is always a complete, parseable JSON object.

That guarantee holds within one process. FDS ships as one process per container, which is the
normal arrangement and keeps it simple. If you deliberately run several worker processes sharing
one output, two things change: the operating system no longer guarantees that very long lines stay
whole, and the supervisor process prints a handful of plain-text startup and shutdown lines before
any worker has configured logging, like this one:

```text
INFO:     Started parent process [65514]
```

A collector should tolerate the occasional non-JSON line rather than fail on it. Running one
process per container avoids the question entirely.

### What a line looks like

Every line carries `timestamp`, `level`, `logger` and `event`, then whatever fields that
particular record needs. `event` is the short name of what happened, and `logger` says which part
of the system said it.

Something changed:

```json
{"actor_id": "f7052ccf...2d4bc", "resource_type": "device", "operation": "update", "id": 1,
 "name": "mast", "changed_fields": ["access_level"], "access_level_before": "restricted",
 "access_level_after": "public", "event": "device.update", "level": "info",
 "logger": "fds.audit", "timestamp": "2026-09-11T11:07:36.032770Z"}
```

A request finished, naming anything restricted it touched:

```json
{"method": "GET", "route": "/api/v1/datasets", "status": 200, "returned": 12,
 "restricted_listed": {"dataset": [31]}, "actor_id": "f7052ccf...2d4bc",
 "event": "request", "level": "info", "logger": "fds.audit",
 "trace_id": "9360d49cd07c6578aa9e7d3bc5d53a2a", "timestamp": "..."}
```

The web server said something, formatted exactly like our own lines:

```json
{"event": "Application startup complete.", "level": "info", "logger": "uvicorn.error",
 "timestamp": "..."}
```

### Sending audit records somewhere separate

This is the important one, because the two kinds of record have very different lifespans.

**The `logger` field is what you route on.** Every audit record, and only an audit record, has:

```text
"logger": "fds.audit"
```

Everything else carries the name of the component that produced it, such as
`app.api.exception_handlers` or `uvicorn.error`. So the rule is a single comparison:

| Destination | Condition |
|---|---|
| Audit store, kept for years | `logger == "fds.audit"` |
| Diagnostics, kept for weeks | everything else |

To look at them by hand, on one machine:

```bash
docker logs fds | jq -c 'select(.logger == "fds.audit")'      # the audit trail
docker logs fds | jq -c 'select(.logger != "fds.audit")'      # everything else
```

To route them to different places in a real deployment, give your log collector that same
condition. Any of the usual collectors can do it. As a worked example, using Vector:

```yaml
transforms:
  parsed:
    type: remap
    inputs: ["fds"]
    source: '. = parse_json!(.message)'
  split:
    type: route
    inputs: ["parsed"]
    route:
      audit: '.logger == "fds.audit"'

sinks:
  audit_store:                 # long retention, restricted access
    type: console
    inputs: ["split.audit"]
    encoding: { codec: json }
  diagnostics:                 # short retention
    type: console
    inputs: ["split._unmatched"]
    encoding: { codec: json }
```

Replace the two `console` sinks with wherever each stream should actually go. The shape of the
rule is the same in Fluent Bit, Logstash, Alloy or a cloud provider's own filtering.

Two things worth getting right when you do this. Audit records should go somewhere the people
being audited cannot edit, or the trail does not do its job. And because they identify
individuals, however indirectly, how long you keep them is a decision with privacy consequences
and is worth making deliberately rather than by default.

### Settings

| Setting | Effect |
|---|---|
| `FDS_LOG_FORMAT` | `json` for machines, `console` for a readable local terminal. Defaults from `FDS_ENVIRONMENT`. |
| `FDS_LOG_LEVEL` | Lowest level to record. Defaults to `INFO`. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Where to send traces. Unset means traces are not exported; everything else still works. |

Every line from a single request carries the same `trace_id`, so a report about one request can
be traced through everything the service did to serve it.

The demo stack ships an optional overlay that runs a trace collector and Grafana, as a worked
example. It turns on trace export and JSON output. Logs are not part of it: FDS writes them to
standard output and pushing them anywhere is the operator's choice, so collecting them is left
to whatever already gathers container output in your deployment.

```bash
docker compose -f demo/docker-compose.yaml -f demo/docker-compose.observability.yaml up -d
```

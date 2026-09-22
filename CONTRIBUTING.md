# Contributing to FDS

Thanks for your interest. FDS is pre-production and moving quickly, so the API
and data model can still change without a deprecation cycle.

## Before you start

For anything beyond a small fix, open an issue first. It is cheaper to agree on
an approach than to rework a finished branch, and some of what looks like a gap
is a decision we have already taken and recorded.

## Development setup

Prerequisites: Python 3.14+, [uv](https://docs.astral.sh/uv/), and
[prek](https://github.com/j178/prek) for the pre-commit hooks.

```bash
git clone https://github.com/ukaea/fds.git
cd fds
uv sync --all-extras
prek install
```

## Running the checks

CI runs exactly these, so running them locally first saves a round trip:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run --all-extras pytest
```

`prek run --all-files` runs the linting and formatting hooks in one go.

### Tests

`uv run --all-extras pytest` runs the unit and API tests. End-to-end tests are
excluded by default because they need a running FDS:

```bash
uv run scripts/mint-token.py init --out-dir dev   # once
docker compose up -d --build                      # or podman compose
uv run --all-extras pytest -m end_to_end
```

They drive FDS over HTTP and assert nothing about its internals, so they catch
wiring problems the in-process tests cannot, and the same suite runs against a
deployment as its smoke test. Behaviour belongs in the in-process tests, which
are faster and can look more closely.

## Code conventions

- `ruff` for linting and formatting, including import sorting. Line length 88.
- `pyright` in standard mode. New code should type-check without ignores.
- Imports at the top of the file unless there is a specific reason not to.
- Keep the layering: routers handle HTTP, services hold the business logic,
  models define the schema. In particular, **authorisation belongs in the
  service layer**, not the router. An endpoint that has to remember to call a
  check is an endpoint that will eventually forget.
- Comment what the code cannot show. A failing test usually explains a
  constraint better than a paragraph does.

## Pull requests

- Branch from `main`.
- One cohesive change per PR, with a short subject line saying what it does.
- Include tests. For a bug fix, a test that fails without the fix is the point.
- CI must pass before review.

## Reporting bugs

Use the issue templates. For anything with a security impact, do not open an
issue: follow [SECURITY.md](SECURITY.md) instead.

## Design decisions

FDS records its architectural decisions as ADRs. They are kept in a separate
internal repository rather than here, because they document why we built
something a particular way rather than how to use it. If a decision behind the
code is unclear, ask in an issue and we will explain it, or write it into the
documentation where it belongs.

## Licence

By contributing you agree that your contributions are licensed under the
Apache License 2.0, as set out in [LICENSE](LICENSE).

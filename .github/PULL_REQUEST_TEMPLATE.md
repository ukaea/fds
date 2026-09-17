## What this changes

<!-- What the change does, and why. Link the issue if there is one. -->

## How it was tested

<!--
New or changed tests, and anything you checked by hand. For a bug fix, say
which test fails without the change.
-->

## Checklist

- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass
- [ ] `uv run pyright` passes
- [ ] `uv run --all-extras pytest` passes
- [ ] Tests cover the change
- [ ] Documentation updated, if the change is user-visible
- [ ] Authorisation checks, if any, live in the service layer rather than the router

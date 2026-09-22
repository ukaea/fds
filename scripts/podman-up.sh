#!/usr/bin/env bash
#
# Bring the development stack (compose.yaml) up cleanly under podman, from the
# current git worktree. Pass --ui to include Keycloak and the reference UI.
#
# Podman only. This is a convenience wrapper around podman-specific problems (pod
# teardown, the podman-compose `up` hang, stale containers across worktrees). It
# works whichever compose provider podman uses (podman-compose or docker-compose),
# since container lookups key off compose labels rather than names. Docker-engine
# users don't hit these problems -- use `docker compose up --build` (see README).
#
# Why this exists: podman-compose 1.6 `up` creates every container but hangs
# before starting the last ones and never returns, and `up --build` rebuilds the
# image without recreating the running container onto it, so stale code keeps
# serving. Docker users do not need this: `docker compose up -d --build` works.
set -euo pipefail

PROJECT="fds-dev"   # matches `name:` in compose.yaml
ROOT="$(git rev-parse --show-toplevel)"
COMPOSE="$ROOT/compose.yaml"
PROFILE=""
[ "${1:-}" = "--ui" ] && PROFILE="--profile ui"

# Resolve the real container name for a compose service via its labels. Both
# podman-compose and docker-compose stamp com.docker.compose.{project,service},
# but they name containers differently (podman-compose: ${PROJECT}_fds_1 with
# underscores; docker-compose: ${PROJECT}-fds-1 with hyphens). Keying off labels
# instead of a constructed name keeps this script provider-agnostic.
cname() {
  podman ps -a \
    --filter "label=com.docker.compose.project=${PROJECT}" \
    --filter "label=com.docker.compose.service=$1" \
    --format '{{.Names}}' 2>/dev/null | head -1
}

echo "==> Tearing down any existing '$PROJECT' stack"
# podman-compose path: it wraps the stack in a pod ("pod_${PROJECT}"), and pod
# members can't be removed individually with `podman rm` -- you must remove the
# pod. docker-compose creates no pod, so this is a harmless no-op there (kept, not
# dead code: it's the only teardown for a podman-compose-created stack). The label
# sweep below handles the docker-compose path.
podman pod rm -f "pod_${PROJECT}" >/dev/null 2>&1 || true
# Sweep every container belonging to the stack, whichever worktree/provider created
# it. Filter on the compose project label (always "${PROJECT}") rather than a
# constructed name, so this catches both _ and - naming across worktrees.
names="$(podman ps -a --filter "label=com.docker.compose.project=${PROJECT}" --format '{{.Names}}' 2>/dev/null || true)"
if [ -n "$names" ]; then
  podman rm -f $names >/dev/null 2>&1 || true
fi

# Build first: `compose build` returns cleanly (~7s), but `up -d --build` hangs.
echo "==> Building images from $ROOT"
podman compose -p "$PROJECT" -f "$COMPOSE" $PROFILE build

# podman-compose 1.6.0 `up` creates every container but then HANGS before starting
# the last ones (they are left "Created"), and never returns. So
# run it detached and drive the stack up ourselves: poll the containers it created
# and `podman start` any left Created/Exited, rather than waiting on the wrapper.
echo "==> Starting stack"
podman compose -p "$PROJECT" -f "$COMPOSE" $PROFILE up -d >/tmp/fds-dev-up.log 2>&1 &
up_pid=$!

# Long-lived services that must end up Running.
services="fds"
[ -n "$PROFILE" ] && services="fds idp ui"
need="$(echo "$services" | wc -w | tr -d ' ')"

echo -n "==> Bringing stack up "
ready=0
for _ in $(seq 1 90); do
  running=0
  for s in $services; do
    name="$(cname "$s")"
    st="$(podman inspect "$name" --format '{{.State.Status}}' 2>/dev/null || echo missing)"
    case "$st" in
      running) running=$((running + 1)) ;;
      created|exited) podman start "$name" >/dev/null 2>&1 || true ;;
    esac
  done
  if [ "$running" -eq "$need" ] && curl -sf http://localhost:8000/openapi.json >/dev/null 2>&1; then
    ready=1
    break
  fi
  echo -n "."
  sleep 2
done
echo
kill "$up_pid" >/dev/null 2>&1 || true  # the wrapper has hung; we've driven the stack up ourselves
if [ "$ready" != 1 ]; then
  echo "!! Stack did not fully come up. Up log:"; tail -20 /tmp/fds-dev-up.log
  echo "   Container states:"; podman ps -a --filter "label=com.docker.compose.project=${PROJECT}" --format "   {{.Names}}\t{{.Status}}"
  exit 1
fi

# Guard against the exact stale-container bug this script exists to prevent: the
# running fds container must use the image we just built. Derive the image tag from
# the container itself (.ImageName) rather than hardcoding "localhost/${PROJECT}_fds",
# since the built tag varies by provider (e.g. docker.io/library/${PROJECT}-fds).
# .Image is the id the container actually runs; if the tag has since been rebuilt to
# a new id, they differ -> stale.
fds="$(cname fds)"
running="$(podman inspect "$fds" --format '{{.Image}}' 2>/dev/null || true)"
tag="$(podman inspect "$fds" --format '{{.ImageName}}' 2>/dev/null || true)"
latest="$(podman image inspect "$tag" --format '{{.Id}}' 2>/dev/null || true)"
if [ -n "$latest" ] && [ -n "$running" ] && [ "$latest" != "$running" ]; then
  echo "!! WARNING: $fds is NOT running the freshly built image (stale)."
fi

echo "==> Development stack is up:"
echo "   API    http://localhost:8000   (OpenAPI explorer: /docs)"
if [ -n "$PROFILE" ]; then
  echo "   IdP    http://localhost:8080"
  echo "   UI     http://localhost:3000"
fi
echo
echo "The catalogue is empty. To fill it with the documented examples:"
echo "   FDS_TOKEN=\$(uv run scripts/mint-token.py mint) uv run scripts/seed-example-catalogue.py"

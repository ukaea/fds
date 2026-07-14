#!/usr/bin/env bash
#
# Launch the FDS demo from the CURRENT git worktree, cleanly.
#
# Podman only. This is a convenience wrapper around podman-specific problems (pod
# teardown, the podman-compose `up` hang, stale containers across worktrees). It
# works whichever compose provider podman uses (podman-compose or docker-compose),
# since container lookups key off compose labels rather than names. Docker-engine
# users don't hit these problems -- use `docker compose up --build` (see README).
#
# Why this exists: podman-compose derives its project name from the compose
# file's parent dir ("demo"), which is identical in every worktree. So launching
# the demo from worktree B reuses worktree A's container/image/network names, and
# `up --build` rebuilds the image but does NOT recreate the running container onto
# it -> stale code keeps serving (e.g. missing routes). This script forces a clean
# slate: it removes whatever "demo" stack is running (whichever worktree owns it)
# and rebuilds everything from here. Only one demo runs at a time, on fixed ports.
set -euo pipefail

PROJECT="demo"
ROOT="$(git rev-parse --show-toplevel)"
COMPOSE="$ROOT/demo/docker-compose.yaml"

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

echo "==> Tearing down any existing '$PROJECT' stack (may belong to another worktree)"
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
podman compose -p "$PROJECT" -f "$COMPOSE" build

# podman-compose 1.6.0 `up` creates every container but then HANGS before starting
# the last ones (frontend/data-generator are left "Created"), and never returns. So
# run it detached and drive the stack up ourselves: poll the containers it created
# and `podman start` any left Created/Exited, rather than waiting on the wrapper.
echo "==> Starting stack"
podman compose -p "$PROJECT" -f "$COMPOSE" up -d >/tmp/fds-demo-up.log 2>&1 &
up_pid=$!

# Long-lived services that must end up Running (minio-setup/data-generator are
# one-shot and intentionally excluded).
services="fds idp minio docs frontend"
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
  echo "!! Stack did not fully come up. Up log:"; tail -20 /tmp/fds-demo-up.log
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

cat <<EOF
==> Demo is up:
   API    http://localhost:8000   (docs: /docs)
   UI     http://localhost:3000
   IdP     http://localhost:8080
   Docs    http://localhost:4001
   MinIO  http://localhost:9000

The catalog starts EMPTY. Populate it by walking through the ingest notebook:
   uvx marimo edit demo/ingest.py --sandbox
Or relaunch with the seed profile to auto-populate on startup:
   podman compose --profile seed -p demo -f demo/docker-compose.yaml up -d
EOF

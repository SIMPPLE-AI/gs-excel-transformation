#!/usr/bin/env bash
# Pull-based deploy for gs-excel-transformation on the AWS EC2 host.
#
# The systemd timer gs-excel-deploy.timer starts this script every 5 minutes.
# The installed copy is /usr/local/bin/gs-excel-deploy. A git pull does NOT update
# that copy. A person installs a new version (see docs/deployment.md).
#
# What the script does:
#   1. Fetch origin/main. Fast-forward the checkout if main moved.
#   2. If the running image is from a commit with the same app files, stop.
#   3. Build gs-excel-transformation:<sha7>.
#   4. Stop the running container and keep it as a backup.
#   5. Start the new container with the same settings.
#   6. If the new container is not healthy, start the backup again.
#   7. Keep the 2 newest backups, remove older backups and unused app images.
#
# A commit that did not deploy is written to $STATE_DIR/failed-sha. The script
# does not try that commit again. A new commit on main, or removal of the file,
# starts a new try.

set -euo pipefail

REPO=${GSX_REPO:-/home/ubuntu/gs-excel-transformation}
NAME=${GSX_NAME:-gs-excel-transformation}
STATE_DIR=${GSX_STATE_DIR:-/home/ubuntu/.gs-excel-deploy}
LOCK=${GSX_LOCK:-/tmp/gs-excel-deploy.lock}
HEALTH_URL=${GSX_HEALTH_URL:-http://127.0.0.1:8880/_stcore/health}
HEALTH_TIMEOUT=${GSX_HEALTH_TIMEOUT:-150}
KEEP=2
# Changes to these paths need a new image. Other changes (docs) only move the checkout.
APP_PATHS=(app requirements.txt Dockerfile .dockerignore)
RUN_ARGS=(
  --restart unless-stopped
  --memory 1g --memory-swap 1g --cpus 1 --pids-limit 256
  --cap-drop ALL --security-opt no-new-privileges
  --log-opt max-size=10m --log-opt max-file=3
  -p 0.0.0.0:8880:8501
)

log() { echo "gs-excel-deploy: $*"; }

# All work is in main(). Bash reads the whole function before it starts, so a
# change to this file during a run does not change the run.
main() {
  mkdir -p "$STATE_DIR"
  exec 9>"$LOCK"
  if ! flock -n 9; then
    log "another deploy runs, stop"
    return 0
  fi

  cd "$REPO"
  git fetch --quiet origin main
  local head remote moved=0
  head=$(git rev-parse HEAD)
  remote=$(git rev-parse origin/main)

  if [ "$head" != "$remote" ]; then
    if ! git merge-base --is-ancestor "$head" "$remote"; then
      log "ERROR: checkout $head is not an ancestor of origin/main $remote, stop"
      return 1
    fi
    if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
      log "ERROR: the checkout has local changes, stop"
      return 1
    fi
    git merge --ff-only --quiet origin/main
    log "checkout ${head:0:7} -> ${remote:0:7}"
    moved=1
  fi

  local target=${remote:0:7}
  local image="$NAME:$target"
  local running_image="" running_sha=""
  running_image=$(docker inspect -f '{{.Config.Image}}' "$NAME" 2>/dev/null || true)
  case "$running_image" in
    "$NAME":*) running_sha=${running_image#"$NAME":} ;;
  esac

  if [ "$running_sha" = "$target" ]; then
    return 0
  fi
  if [ -n "$running_sha" ] && git rev-parse --verify --quiet "$running_sha^{commit}" > /dev/null \
      && git diff --quiet "$running_sha" "$remote" -- "${APP_PATHS[@]}"; then
    [ "$moved" = 1 ] && log "no app change since $running_sha, the container stays on $running_image"
    return 0
  fi
  if [ -f "$STATE_DIR/failed-sha" ] && [ "$(cat "$STATE_DIR/failed-sha")" = "$remote" ]; then
    [ "$moved" = 1 ] && log "$target did not deploy before, no new try"
    return 0
  fi

  log "deploy $target (running: ${running_image:-none})"
  if ! docker build --quiet -t "$image" . > /dev/null; then
    log "ERROR: docker build of $target failed, the container stays on ${running_image:-none}"
    echo "$remote" > "$STATE_DIR/failed-sha"
    return 1
  fi

  local ts backup=""
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  if docker container inspect "$NAME" > /dev/null 2>&1; then
    backup="$NAME-backup-$ts-${running_sha:-unknown}"
    docker stop --time 30 "$NAME" > /dev/null
    docker rename "$NAME" "$backup"
    log "old container kept as $backup"
  fi

  if docker run -d --name "$NAME" "${RUN_ARGS[@]}" "$image" > /dev/null && wait_healthy; then
    rm -f "$STATE_DIR/failed-sha"
    echo "$(date -Is) $target $backup" >> "$STATE_DIR/deploys.log"
    log "OK: $image is healthy"
    cleanup
    return 0
  fi

  log "ERROR: $image is not healthy, roll back"
  echo "$remote" > "$STATE_DIR/failed-sha"
  if docker container inspect "$NAME" > /dev/null 2>&1; then
    docker stop --time 10 "$NAME" > /dev/null 2>&1 || true
    docker rename "$NAME" "$NAME-failed-$ts-$target"
  fi
  if [ -n "$backup" ]; then
    docker rename "$backup" "$NAME"
    docker start "$NAME" > /dev/null
    if wait_healthy; then
      log "rollback OK: $running_image runs again"
    else
      log "ERROR: rollback container $running_image is not healthy, a person must look"
    fi
  fi
  return 1
}

wait_healthy() {
  local end=$((SECONDS + HEALTH_TIMEOUT)) state
  while [ "$SECONDS" -lt "$end" ]; do
    state=$(docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "$NAME" 2>/dev/null || echo "missing")
    case "$state" in
      "running healthy")
        curl --fail --silent --max-time 5 "$HEALTH_URL" > /dev/null && return 0 ;;
      running*) ;;
      *) log "container state: $state"; return 1 ;;
    esac
    sleep 5
  done
  log "no healthy state after ${HEALTH_TIMEOUT}s"
  return 1
}

# Remove only containers and images of this app. Never use docker prune on this shared host.
cleanup() {
  local kind name
  for kind in backup failed; do
    docker ps -a --filter "name=^${NAME}-${kind}-" --format '{{.Names}}' | sort -r | tail -n +$((KEEP + 1)) |
      while read -r name; do
        docker rm "$name" > /dev/null && log "removed old container $name"
      done
  done
  local used tag
  used=$(docker ps -a --format '{{.Image}}')
  docker image ls "$NAME" --format '{{.Tag}}' | while read -r tag; do
    [ -z "$tag" ] || [ "$tag" = "<none>" ] && continue
    if ! grep -qxF "$NAME:$tag" <<< "$used"; then
      docker image rm "$NAME:$tag" > /dev/null 2>&1 && log "removed unused image $NAME:$tag"
    fi
  done
  return 0
}

main "$@"

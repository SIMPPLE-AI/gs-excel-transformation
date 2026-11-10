#!/usr/bin/env bash
# Offline test of deploy/deploy.sh with a fake docker, curl and flock.
# Run: bash deploy/test_deploy.sh
# It uses a temporary git repository as origin. It does not use Docker or the network.
set -euo pipefail

SRC=$(cd "$(dirname "$0")" && pwd)/deploy.sh
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/fake"
export FAKE="$T/fake"
: > "$FAKE/containers"   # lines: name image status

cat > "$T/bin/flock" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat > "$T/bin/curl" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat > "$T/bin/sleep" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
# Fake docker. State: $FAKE/containers, $FAKE/images. A tag in $FAKE/bad_tag is never healthy.
cat > "$T/bin/docker" <<'EOF'
#!/usr/bin/env bash
C="$FAKE/containers"; I="$FAKE/images"; touch "$I"
echo "docker $*" >> "$FAKE/calls"
get() { awk -v n="$1" '$1==n' "$C"; }
case "$1" in
  inspect)
    shift; fmt=""; [ "$1" = "-f" ] && { fmt=$2; shift 2; }
    line=$(get "$1"); [ -z "$line" ] && exit 1
    img=$(echo "$line" | awk '{print $2}'); st=$(echo "$line" | awk '{print $3}')
    case "$fmt" in
      *Config.Image*) echo "$img" ;;
      *State.Status*)
        if [ "$st" = running ]; then
          if [ -f "$FAKE/bad_tag" ] && [ "$img" = "$(cat "$FAKE/bad_tag")" ]; then echo "exited "; else echo "running healthy"; fi
        else echo "$st "; fi ;;
    esac ;;
  container) get "$3" | grep -q . ;;
  build) [ -f "$FAKE/build_fails" ] && exit 1; echo "$4" >> "$I"; echo sha256:x ;;
  stop) awk -v n="${@: -1}" '{ if ($1==n) $3="exited"; print }' "$C" > "$C.t" && mv "$C.t" "$C" ;;
  start) awk -v n="$2" '{ if ($1==n) $3="running"; print }' "$C" > "$C.t" && mv "$C.t" "$C" ;;
  rename) get "$3" | grep -q . && exit 1; awk -v a="$2" -v b="$3" '{ if ($1==a) $1=b; print }' "$C" > "$C.t" && mv "$C.t" "$C" ;;
  run) name=""; args=("$@"); for i in "${!args[@]}"; do [ "${args[$i]}" = "--name" ] && name=${args[$((i+1))]}; done
       echo "$name ${@: -1} running" >> "$C"; echo cid ;;
  rm) grep -v "^$2 " "$C" > "$C.t" || true; mv "$C.t" "$C" ;;
  ps) case "$*" in
        *name=*) pat=$(echo "$*" | sed -E 's/.*name=\^([^ ]*).*/\1/'); awk '{print $1}' "$C" | grep "^$pat" || true ;;
        *) awk '{print $2}' "$C" ;;
      esac ;;
  image)
    case "$2" in
      ls) sed 's/.*://' "$I" | sort -u ;;
      rm) awk '{print $2}' "$C" | grep -qxF "$3" && exit 1; grep -vxF "$3" "$I" > "$I.t" || true; mv "$I.t" "$I" ;;
    esac ;;
esac
EOF
chmod +x "$T/bin/"*
export PATH="$T/bin:$PATH"

# Origin repository with one app commit.
git init -q -b main "$T/origin"
cd "$T/origin"
git config user.email t@t; git config user.name t; git config core.autocrlf false
mkdir app; echo v1 > app/main.py; echo x > requirements.txt; echo FROM > Dockerfile; echo a > README.md
git add -A; git commit -qm one
git clone -q "$T/origin" "$T/repo"
c1=$(git rev-parse --short=7 HEAD)

export GSX_REPO="$T/repo" GSX_STATE_DIR="$T/state" GSX_LOCK="$T/lock" GSX_HEALTH_TIMEOUT=10
echo "gs-excel-transformation gs-excel-transformation:$c1 running" > "$FAKE/containers"
echo "gs-excel-transformation:$c1" > "$FAKE/images"

fail=0
check() { if eval "$2"; then echo "PASS $1"; else echo "FAIL $1"; fail=1; fi; }
running() { awk '$1=="gs-excel-transformation" {print $2, $3}' "$FAKE/containers"; }
run() { local rc=0; bash "$SRC" > "$T/out" 2>&1 || rc=$?; echo "$rc" > "$T/rc"; sed 's/^/    /' "$T/out"; }

echo "1. no change"
run
check "exit 0" '[ "$(cat $T/rc)" = 0 ]'
check "no output" '[ ! -s "$T/out" ]'

echo "2. docs-only commit"
cd "$T/origin"; echo b >> README.md; git commit -qam docs
run
check "checkout moved" 'grep -q "checkout" "$T/out"'
check "no build" '! grep -q "docker build" "$FAKE/calls"'
check "container same" '[ "$(running)" = "gs-excel-transformation:$c1 running" ]'

echo "3. app commit, healthy"
cd "$T/origin"; echo v2 > app/main.py; git commit -qam app2; c3=$(git rev-parse --short=7 HEAD)
run
check "exit 0" '[ "$(cat $T/rc)" = 0 ]'
check "new image runs" '[ "$(running)" = "gs-excel-transformation:$c3 running" ]'
check "backup kept" 'grep -q "^gs-excel-transformation-backup-.* gs-excel-transformation:$c1 exited" "$FAKE/containers"'
run
check "second run quiet" '[ ! -s "$T/out" ]'

echo "4. app commit, not healthy -> rollback"
cd "$T/origin"; echo v3 > app/main.py; git commit -qam app3; c4=$(git rev-parse --short=7 HEAD)
echo "gs-excel-transformation:$c4" > "$FAKE/bad_tag"
run
check "exit 1" '[ "$(cat $T/rc)" = 1 ]'
check "old image runs again" '[ "$(running)" = "gs-excel-transformation:$c3 running" ]'
check "failed container kept" 'grep -q "^gs-excel-transformation-failed-.* gs-excel-transformation:$c4" "$FAKE/containers"'
check "failed-sha written" '[ "$(cut -c1-7 "$T/state/failed-sha")" = "$c4" ]'

echo "5. same failed commit -> no new try"
: > "$FAKE/calls"
run
check "exit 0" '[ "$(cat $T/rc)" = 0 ]'
check "no build" '! grep -q "docker build" "$FAKE/calls"'

echo "6. build fails"
rm -f "$FAKE/bad_tag"; touch "$FAKE/build_fails"
cd "$T/origin"; echo v4 > app/main.py; git commit -qam app4
run
check "exit 1" '[ "$(cat $T/rc)" = 1 ]'
check "container same" '[ "$(running)" = "gs-excel-transformation:$c3 running" ]'
check "no stop" '! grep -q "docker stop" <(tail -n 3 "$FAKE/calls")'

echo "7. next commit builds, cleanup keeps 2 backups"
rm -f "$FAKE/build_fails"
for v in 5 6 7; do
  cd "$T/origin"; echo "v$v" > app/main.py; git commit -qam "app$v"
  run
done
c7=$(git -C "$T/origin" rev-parse --short=7 HEAD)
check "newest runs" '[ "$(running)" = "gs-excel-transformation:$c7 running" ]'
check "2 backups" '[ "$(grep -c "^gs-excel-transformation-backup-" "$FAKE/containers")" = 2 ]'
check "unused images removed" '[ "$(wc -l < "$FAKE/images")" -le 5 ]'

echo "8. local change in the checkout -> stop"
cd "$T/origin"; echo v8 > app/main.py; git commit -qam app8
echo dirty >> "$T/repo/app/main.py"
run
check "exit 1" '[ "$(cat $T/rc)" = 1 ]'
check "message" 'grep -q "local changes" "$T/out"'

exit $fail

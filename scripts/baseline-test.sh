#!/usr/bin/env bash
# Local fixture harness for scripts/baseline.py (ADR-PLT-0028 V6).
# Runs the real script against real YAML records in a throwaway git repo.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
pass=0; fail=0
ok()  { echo "PASS: $1"; pass=$((pass+1)); }
bad() { echo "FAIL: $1"; fail=$((fail+1)); }
run() { uv run --quiet --with pyyaml python "$HERE/baseline.py" "$@"; }

mkdir -p "$WORK/releases"
cd "$WORK"
git init -q . && git config user.email t@t && git config user.name t
printf 'order: [web]\n' > releases/baseline-order.yaml

# commit A -- deployed 0.1.0, digest d111, Worker version 32a8702c
cat > releases/prod.yaml <<'EOF'
env: prod
components:
  web:
    kind: worker
    repo: PalupGG/web
    executor: site-release.yml
    desired: {version: 0.1.0, commit: '0292562', digest: d111, build_run: '43857261233'}
    observed:
      version: 0.1.0
      commit: '0292562'
      digest: d111
      worker_version: 32a8702c-aaaa-bbbb-cccc-000000000001
      deployed_at: '2026-11-16T17:23:51Z'
      status: deployed
EOF
git add -A && git commit -qm A

# T1 -- observed matches desired: nothing to do
out=$(run plan --env prod --mode deploy --file releases/prod.yaml --components changed 2>&1)
echo "$out" | grep -q "nothing to do" && ok "T1 no-op when observed matches desired" || bad "T1 no-op ($out)"

# commit B -- desired moves to a new build, the environment has not moved yet
cat > releases/prod.yaml <<'EOF'
env: prod
components:
  web:
    kind: worker
    repo: PalupGG/web
    executor: site-release.yml
    desired: {version: 0.1.0, commit: aaa1111, digest: d222, build_run: '43857261233'}
    observed:
      version: 0.1.0
      commit: '0292562'
      digest: d111
      worker_version: 32a8702c-aaaa-bbbb-cccc-000000000001
      deployed_at: '2026-11-16T17:23:51Z'
      status: deployed
EOF
git add -A && git commit -qm B

# T2 -- deploy plan promotes exactly the changed component, carrying digest + build_run
out=$(run plan --env prod --mode deploy --file releases/prod.yaml --components changed 2>&1)
if echo "$out" | grep -q '"child_mode": "promote"' && echo "$out" | grep -q '"digest": "d222"' \
   && echo "$out" | grep -q '"build_run": "43857261233"' && echo "$out" | grep -q '"version_id": ""'; then
  ok "T2 deploy plan promotes the changed component (digest + build_run, no version id)"
else bad "T2 deploy plan: $out"; fi

# commit C -- the new build is live, so a rollback finally has something to do
cat > releases/prod.yaml <<'EOF'
env: prod
components:
  web:
    kind: worker
    repo: PalupGG/web
    executor: site-release.yml
    desired: {version: 0.1.0, commit: aaa1111, digest: d222, build_run: '43857261233'}
    observed:
      version: 0.1.0
      commit: aaa1111
      digest: d222
      worker_version: ffffffff-1111-2222-3333-444444444444
      deployed_at: '2026-11-16T19:00:00Z'
      status: deployed
EOF
git add -A && git commit -qm C

# T3 -- rollback to commit A restores by Worker version id (no artifact, no rebuild)
out=$(run plan --env prod --mode rollback --file releases/prod.yaml --to-ref HEAD~2 2>&1)
if echo "$out" | grep -q '"child_mode": "rollback"' \
   && echo "$out" | grep -q '32a8702c-aaaa-bbbb-cccc-000000000001'; then
  ok "T3 rollback restores by Worker version id (no artifact needed)"
else bad "T3 rollback by version id: $out"; fi

# T4 -- no version id anywhere: rollback falls back to a digest-pinned promote
cat > releases/prod.yaml <<'EOF'
env: prod
components:
  web:
    kind: worker
    repo: PalupGG/web
    executor: site-release.yml
    desired: {version: 0.1.0, commit: aaa1111, digest: d222, build_run: '1'}
    observed: {version: 0.1.0, commit: aaa1111, digest: d222, status: deployed}
    previous:
      observed: {version: 0.1.0, commit: c000, digest: d000, status: deployed}
EOF
out=$(run plan --env prod --mode rollback --file releases/prod.yaml 2>&1)
if echo "$out" | grep -q '"child_mode": "promote"' && echo "$out" | grep -q '"digest": "d000"'; then
  ok "T4 rollback without a version id falls back to a digest-pinned promote"
else bad "T4 rollback fallback: $out"; fi

# T5 -- a component absent from the order file is refused, not skipped
printf 'order: []\n' > releases/baseline-order.yaml
out=$(run plan --env prod --mode deploy --file releases/prod.yaml 2>&1); rc=$?
if [ $rc -ne 0 ] && echo "$out" | grep -q "missing from releases/baseline-order.yaml"; then
  ok "T5 undeclared component is refused"
else bad "T5 order guard rc=$rc: $out"; fi
printf 'order: [web]\n' > releases/baseline-order.yaml

# T6 -- record moves the old observed into previous and writes the new row
cat > releases/prod.yaml <<'EOF'
env: prod
components:
  web:
    kind: worker
    repo: PalupGG/web
    executor: site-release.yml
    desired: {version: 0.1.0, commit: aaa1111, digest: d222, build_run: '2'}
    observed:
      version: 0.1.0
      commit: '0292562'
      digest: d111
      worker_version: 32a8702c-aaaa-bbbb-cccc-000000000001
      deployed_at: '2026-11-16T17:23:51Z'
      status: deployed
EOF
cat > "$WORK/results.json" <<'EOF'
{"ok":true,"mode":"deploy","env":"prod","finished_at":"2026-11-16T20:00:00Z","results":[
 {"name":"web","version":"0.1.0","commit":"aaa1111","digest":"d222","build_run":"2",
  "previous_version_id":"ffffffff-1111-2222-3333-444444444444",
  "run_id":999,"conclusion":"success","worker_version":"ffffffff-1111-2222-3333-444444444444"}]}
EOF
run record --file releases/prod.yaml --results "$WORK/results.json" >/dev/null 2>&1
grep -q "32a8702c-aaaa-bbbb-cccc-000000000001" releases/prod.yaml \
  && ok "T6a record keeps the previous Worker version (the rollback ledger)" \
  || bad "T6a previous not kept"
grep -q "ffffffff-1111-2222-3333-444444444444" releases/prod.yaml \
  && ok "T6b record writes the new observed row" || bad "T6b new observed missing"

# T7 -- dry-run dispatches nothing and succeeds
cat > "$WORK/plan.json" <<'EOF'
{"env":"prod","mode":"deploy","dry_run":true,"components":[
 {"name":"web","kind":"worker","repo":"PalupGG/web","executor":"site-release.yml",
  "environment":"prod","child_mode":"promote","version":"0.1.0","commit":"aaa1111",
  "digest":"d222","build_run":"2","version_id":"",
  "previous_version_id":"ffffffff-1111-2222-3333-444444444444","changed":true}]}
EOF
out=$(run apply --plan "$WORK/plan.json" --results "$WORK/dry.json" 2>&1); rc=$?
if [ $rc -eq 0 ] && grep -q '"dry_run": true' "$WORK/dry.json" && echo "$out" | grep -q "\[dry-run\] POST"; then
  ok "T7 dry-run prints the dispatch and changes nothing"
else bad "T7 dry-run rc=$rc: $out"; fi

# T8 -- a real apply with no credential fails closed with exit 2
cat > "$WORK/plan2.json" <<'EOF'
{"env":"prod","mode":"deploy","dry_run":false,"components":[
 {"name":"web","kind":"worker","repo":"PalupGG/web","executor":"site-release.yml",
  "environment":"prod","child_mode":"promote","version":"0.1.0","commit":"aaa1111",
  "digest":"d222","build_run":"2","version_id":"","changed":true}]}
EOF
out=$(env -u GH_TOKEN -u BASELINE_TOKEN uv run --quiet --with pyyaml python "$HERE/baseline.py" apply --plan "$WORK/plan2.json" --results "$WORK/real.json" 2>&1); rc=$?
if [ $rc -eq 2 ] && echo "$out" | grep -q "refusing: BASELINE_TOKEN is not set"; then
  ok "T8 missing credential fails closed before any dispatch (exit 2)"
else bad "T8 fail-closed rc=$rc: $out"; fi

# T9 -- the version-id parser reads the child's log line
uv run --quiet --with pyyaml python - <<'PY'
import re
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
log = "...\nWorker Version ID: 32a8702c-aaaa-bbbb-cccc-000000000001\nDeployed prod-palupgg-web triggers\n"
hits = UUID.findall(log)
print("PASS: T9 version id parsed from the child log" if hits and hits[-1].startswith("32a8702c") else "FAIL: T9 parser")
PY

# T10 -- release notes carry the version-id rollback for each component
run notes --plan "$WORK/plan.json" --results "$WORK/results.json" --out "$WORK/notes.md" >/dev/null 2>&1
if grep -q "version_id=ffffffff-1111-2222-3333-444444444444" "$WORK/notes.md"; then
  ok "T10 release notes carry the version-id rollback command"
else bad "T10 notes missing rollback: $(cat "$WORK/notes.md")"; fi

echo "----"; echo "passed=$pass failed=$fail"
[ "$fail" -eq 0 ]
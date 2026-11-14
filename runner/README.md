# Self-hosted runner pool on the owned cluster (ADR-PLT-0015 #3)

Two persistent runner replicas in the `ci-runners` namespace, registered at the ORG
level so every private repository can use them, carrying the `palupgg-ci` label.
`runner-statefulset.yaml` is the pool (headless Service + StatefulSet, PVC-backed
registration); `network-policy.yaml` is the egress-only NetworkPolicy applied with it.
Cluster applies are founder actions: no kubeconfig exists on agent hosts, and a
registration token is founder-only to mint (fleet rule 10) — it expires in 1 hour.

## Founder apply runbook (two commands on a darkcloud host)

Sequence matters (ADR-PLT-0015): the pool exists and the label is proven BEFORE any
caller flips `runs-on` — flipping first queues every fleet PR on a label with no
runner. The `ci-runners` namespace is the only cluster-side assumption; if it is not
there yet, `kubectl create namespace ci-runners` once.

1. Mint a registration token (1-hour TTL — mint it right before applying). GitHub UI:
   org Settings → Actions → Runners → New self-hosted runner (the token is in the
   dialog), or the agent mints it on request:

       gh api --method POST orgs/PalupGG/actions/runners/registration-token --jq .token

   (needs an org-owner gh login with `admin:org`, or the fine-grained "runners"
   permission: `gh auth refresh -h github.com -s admin:org`)

2. On a darkcloud host, from this repository's root: put the token in the `runner-reg`
   secret, then apply the pool:

       kubectl -n ci-runners create secret generic runner-reg \
         --from-literal=token=<TOKEN> --dry-run=client -o yaml | kubectl apply -f -
       kubectl -n ci-runners apply -f runner/

   (`--dry-run=client -o yaml | kubectl apply` so a later re-apply with a fresh token
   updates the secret in place instead of failing on AlreadyExists.)

3. Verify: the pods come up, and the org runner list shows both registered with the
   `palupgg-ci` label:

       kubectl -n ci-runners get pods -w
       gh api orgs/PalupGG/actions/runners --jq '.runners[] | "\(.name) \(.status) \(.labels)"'

4. Tell the agent — the label selftest workflow and the `runs-on` flip wave follow in
   their own PRs (not in this repository's scope beyond the manifest).

## How it stays alive

- The runner registers into its PVC (`/data`). Pod restarts reuse the registration;
  the one-hour token expiry only matters at first registration.
- Scale with `kubectl -n ci-runners scale statefulset/actions-runner --replicas=N` —
  every replica registers as its own runner.
- The runner auto-updates itself; the image tag tracks the runner version — bump it
  deliberately.

## Security rules (why these files are shaped this way)

- **Private repositories only.** Never allow these runners for public repos or fork
  PRs (`use_public_self_hosted_runner` must stay off) — a fork PR must never land on
  this pool.
- Runs in `ci-runners` with `automountServiceAccountToken: false` and no host docker
  socket; CI jobs are rustup + cargo + sh. Image builds go through the separate
  `packages: write` job, not on this pool's host.
- The `FLEET_TOKEN` reaches jobs as a repository secret over the Actions channel;
  nothing is baked into the manifest. The registration token lives only in the
  founder-created `runner-reg` secret.
- **NetworkPolicy (`network-policy.yaml`)**: ingress is denied from outside
  `ci-runners` — the runners poll GitHub, nothing needs to reach them. Egress is DNS
  (port 53, cluster nameservers) and public HTTPS (443) only, with every private,
  link-local and CGNAT range excepted: GitHub endpoints and GHCR are reachable, and so
  are the crates index and the rust toolchain CDN the gates fetch, while the runner can
  never reach cluster services, node-local metadata or private networks.
- One limitation for the flip wave: GitHub job `services:` (the Postgres opt-in in
  `fleet-ci.yml` / `fleet-e2e.yml`) require Docker on the runner host; this pool has
  no docker socket, so DB-backed suites stay on `ubuntu-latest` until that is decided.

# Self-hosted runner on the owned cluster (ADR-PLT-0013)

One namespace, two persistent runner replicas, registered at the ORG level so every private
repository can use them. Registration is a founder action: it needs an org-owner token
(`admin:org`, or the "runners" fine-grained permission) to mint a registration token.

## Bootstrap (founder, once)

1. Mint a registration token (expires in 1 hour — mint it right before applying):

       gh api --method POST orgs/SanctuaryGG/actions/runners/registration-token --jq .token

   (requires `gh auth refresh -h github.com -s admin:org`, or the dashboard equivalent)

2. Put the token in the namespace secret and apply:

       kubectl create namespace ci-runners 2>/dev/null || true
       kubectl -n ci-runners create secret generic runner-registration \
         --from-literal=token=<REGISTRATION_TOKEN>
       kubectl apply -f runner-statefulset.yaml

3. Accept the runner in the org settings (Settings → Actions → Runners) the first time, and
   verify:

       gh api orgs/SanctuaryGG/actions/runners --jq '.runners[] | "\(.name) \(.status) \(.labels)"

## How it stays alive

- The runner registers into its PVC (`/data`). Pod restarts reuse the registration; the
  one-hour token expiry only matters at first registration.
- Scale with `kubectl -n ci-runners scale statefulset/actions-runner --replicas=N`.
- Runner auto-updates itself; the image tag below tracks the latest runner version — bump it
  deliberately.

## Security rules (why this manifest is shaped this way)

- **Private repositories only.** Never allow these runners for public repos or fork PRs
  (`use_public_self_hosted_runner` must stay off) — a fork PR must never land on this pool.
- Runs in the `ci-runners` namespace with no service account privileges beyond default;
  no host docker socket mounted. CI jobs today are rustup + cargo + sh — no container builds
  inside the runner. Image builds happen later through CI -> GHCR with a scoped
  `packages: write` job, not on this pool's host.
- The FLEET_TOKEN reaches jobs as a repository secret over the Actions channel; nothing is
  baked into the manifest.

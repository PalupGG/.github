# SanctuaryGG/.github — the org CI backbone

Reusable workflows, called by every code repository, pinned by full SHA (fleet rule 5,
ADR-PLT-0010 #3). Documentation of the whole pipeline lives in
`SanctuaryGG/platform` → `docs/ci-cd.md` (ADR-PLT-0009 as amended by ADR-PLT-0013).

## What is here

| Path | What |
|---|---|
| `.github/workflows/fleet-ci.yml` | The reusable workflow: the five gates (boundary selftest, boundary gate — service or kernel role, `cargo fmt --check`, `cargo clippy -D warnings`, `cargo test`) on the pinned toolchain, with the `FLEET_TOKEN` kernel fetch wired through the git CLI credential helper — plus an opt-in `postgres:17-alpine` service for database-backed suites, the Worker rail (`worker-tests` + `worker-smoke`), and an input-gated `edge-smoke` leg that curls a deployed `/healthz` through the WAN. |
| `.github/workflows/selftest.yml` | Composition selftests for the reusable workflows: plain, Postgres and Worker fixture callers prove which legs run per rail, edge-smoke fixtures prove the smoke contract (pass, wrong URL, stale version, network blip), and `matrix-proof` asserts all of it from the run's job list. |
| `.github/workflows/fleet-e2e.yml` | The application-level e2e workflow: builds the calling repo's crate, boots the real server (`cargo run`, background), waits for the health path, runs the repo's e2e suite against the live process — with the same `FLEET_TOKEN` wiring and `postgres:17-alpine` opt-in as fleet-ci. |
| `.github/workflows/fleet-worker.yml` | The assets-Worker deploy workflow: builds the caller's static assets (`build_command`), validates the bundle with `wrangler deploy --dry-run`, uploads the export as the `<service>-dist` artifact, then (non-PR runs only) deploys it with `wrangler deploy` from the `[self-hosted, palupgg-ci]` pool into the GitHub environment (default `staging`). Wrangler owns the script, assets, and version; DNS, the tunnel, WAF, and the custom domain stay in Terraform Cloud (gitops/edge). |
| `.github/workflows/fleet-worker-promote.yml` | Build once, promote the artifact (ADR-PLT-0025): three modes on one ladder — `build` (deterministic tar, sha256 digest, `versions upload` + `versions deploy <id>@100%`, 90-day artifact retention), `promote` (re-downloads the artifact from the source run and refuses on digest mismatch — same bytes, a different `worker_name`, never a rebuild), `rollback` (`wrangler rollback <version_id>`) — and outputs the deployed `version_id`. Worker Versions are scoped to one script, so the artifact digest is the identity that travels. |
| `.github/workflows/fleet-worker-code.yml` | The bundle-Worker executor (ADR-PLT-0028 §2): four modes — `build`, `promote` (digest-pinned), `reconcile` (version-id, same environment), `rollback` — for Rust Workers deployed from a `worker-build --release` bundle. Resolves and patches the D1 `database_id` at deploy time (the committed placeholder never becomes a real id in any tree; create only when absent), applies D1 migrations before the deploy, and asserts `workers_dev`/`preview_urls` are explicitly false in the config before anything publishes (ADR-PLT-0027 §5). Chat's hand-run `deploy.yml` becomes a thin caller of this workflow (the swap is chat's issue). |
| `.github/workflows/fleet-baseline.yml` | The baseline orchestrator (ADR-PLT-0028; caller `PalupGG/gitops`, record `releases/<environment>.yaml` there): `plan` reads the record and decides per component (deploy desired, or rollback to a ref / `previous`) via `scripts/baseline.py`, ordered by `releases/baseline-order.yaml`, with an actor allowlist gating prod; `apply` dispatches each component's executor sequentially, fail-fast, collecting the child run and its Worker version; `record` writes observed/previous back, commits, and publishes the release on a tag. Rollback is a first-class mode: it prefers the recorded version-id restore and only falls back to a digest-pinned promote. |
| `runner/` | The self-hosted runner for the owned cluster: manifest + bootstrap instructions. Not applied by agents; cluster changes are founder actions. |

## How a repository calls it

```yaml
# .github/workflows/ci.yml in any code repository
name: ci
on:
  push: { branches: [main] }
  pull_request:
permissions: { contents: read }
concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }
jobs:
  fleet:
    uses: SanctuaryGG/.github/.github/workflows/fleet-ci.yml@<full-commit-sha>
    secrets: inherit
```

The kernel repository adds `with: { kernel-role: true }`.

A repository with database-backed test suites opts in with
`with: { postgres: true, postgres-env: <CONNECTION_ENV_VAR> }`: the same gates then run beside
a `postgres:17-alpine` service (dummy job-local password, `pg_isready` health gate) with
`<CONNECTION_ENV_VAR>` set to `postgres://postgres:<password>@localhost:5432/<postgres-database>`
(`postgres-database` defaults to `test`).

A Rust Worker repository opts in with `with: { worker-tests: true }`. Its tests boot
`wrangler dev`, whose build command is `worker-build` (workers-rs), and neither that binary nor
the `wasm32-unknown-unknown` target is part of the pinned Rust toolchain — without both, the
suite fails at the build command, not at an assertion. The opt-in adds the target and a
version-pinned `worker-build` (0.9.0) to both gate jobs, and adds a `worker-smoke` job that
proves the environment independently of any service: a throwaway Worker must answer `/healthz`
and echo one WebSocket message. Trade-off: a cold `cargo install worker-build` costs a few
minutes; a pre-baked runner image would be faster but would move the toolchain version out of
this repository and into the cluster.

The SHA is bumped deliberately, in a PR, when the workflow changes — never a branch, never
a floating tag.

## The rail matrix (issue #36)

One workflow, rails chosen by inputs — the Postgres split is the `gates` / `gates-postgres`
twin (GitHub Actions has no conditional `services:`, so the twin is skipped by the matrix,
never a weakened or copy-pasted workflow), and the Worker rail is `worker-tests` plus the
`worker-smoke` environment proof:

| Repository | fleet-ci inputs (the rail) | Legs that run |
|---|---|---|
| `kernel` | `kernel-role: true` | `gates` (boundary gate in kernel role) |
| `chat` | `worker-tests: true` | `gates` + `worker-smoke` — no Postgres service (ADR-PLT-0030) |
| `identity` | `postgres: true`, `postgres-env: IDENTITY_DATABASE_URL` | `gates-postgres`; flips to the Worker rail when its D1 port lands (ADR-PLT-0031) |
| `marketplace` | `postgres: true`, `postgres-env: MARKETPLACE_DATABASE_URL` | `gates-postgres` |
| `ledger` | `postgres: true`, `postgres-env: LEDGER_DATABASE_URL` | `gates-postgres` |
| `web` | `runs-on: '["self-hosted","palupgg-build"]'` | `gates` (static-assets Worker; no database) |

Why the ledger is the exception: D1 has no roles or grants, no row locks and a 10 GB ceiling
(ADR-PLT-0029 §3), and buyer money may not move to a weaker guarantee. The ledger stays on
Postgres until ADR-PLT-0029 §4's five money proofs pass — append-only trigger, batch
atomicity, restore from an export, idempotent replay, reconciliation reporting zero diffs on
a clean run while catching a seeded diff — plus DEC-0011 (nightly export to R2, a performed
and recorded restore, reconciliation read by a human, human approval on every movement).
Until that record changes, no matrix leg runs the ledger's gates without Postgres.

The selftest proves the matrix on every push to main: the `postgres-fixture` caller must run
`gates-postgres` and skip `gates`, the `worker-fixture` must run `gates` + `worker-smoke` and
skip `gates-postgres`, and `matrix-proof` reads the run's job list and fails on any deviation.

### Edge smoke — `edge-smoke-url` / `edge-smoke-version`

A deploy is smoked through the WAN, not only loopback. A caller passes the deployed
environment's public `/healthz` URL and the version marker its body must contain; the leg
curls it once, hard-bounded. The contract, each line proven by a selftest fixture:

| Case | Behavior |
|---|---|
| answered 200, body contains `edge-smoke-version` | pass (`edge-smoke-pass`) |
| answered 404 or any other non-200 — wrong URL, broken deployment | fail (`edge-smoke-wrong-url`) |
| answered 200, marker missing or stale | fail (`edge-smoke-stale-version`) |
| no answer within `--connect-timeout 10` / `--max-time 20` — network blip | `::warning`, continue (`edge-smoke-no-answer`); a blip never blocks CI |
| 403 — runner egress not in the Cloudflare WAF allowlist | `::warning`, continue (same convention as the Worker ladder's smoke) |

Empty `edge-smoke-url` (the default) skips the leg, so existing callers are unaffected. Today
the fleet contract is `/healthz` → `ok`; a deploy version id fits `edge-smoke-version` once
services expose one. Capturing the URL at deploy time is `.github#21` (separate, still open).

## Application-level e2e — `fleet-e2e.yml`

`fleet-ci.yml` gates the code; `fleet-e2e.yml` proves the **built application**: build the
crate, boot the real server, wait for the health path, then run the e2e suite against the
live process. This is the foundation the roadmap's R6 browser e2e builds on — one layer
down, no browser yet.

Caller contract — the calling repo must provide:

- a server that binds from env (`BIND` and `PORT`; the job sets `BIND=127.0.0.1` and
  `PORT` from `app-port`);
- a liveness endpoint at `health-path` (default `/healthz`) answering 2xx once the app
  serves traffic;
- an e2e target the `e2e-command` runs (default `cargo test --test e2e`). The suite finds
  the app through the same `BIND`/`PORT` env vars, and reads the database URL from
  `postgres-env` when `postgres` is true.

Inputs (mirroring fleet-ci's conventions):

| Input | Default | What |
|---|---|---|
| `runs-on` | `ubuntu-latest` | Runner label, same as fleet-ci. |
| `postgres` | `false` | Boot a `postgres:17-alpine` service beside the app (same shape as fleet-ci's opt-in). |
| `postgres-env` | `DATABASE_URL` | Env var the app and e2e suite read the connection URL from; set to the service URL when `postgres` is true. |
| `postgres-database` | `test` | Database the service creates and the URL points at. |
| `app-port` | `8080` | Port the app binds (`PORT`); the e2e suite sees the same value. |
| `health-path` | `/healthz` | Path polled for up to 60 s before the suite runs (leading slash required). |
| `e2e-command` | `cargo test --test e2e` | Command that runs the e2e suite against the live app. |

`FLEET_TOKEN` is the same optional secret as fleet-ci (kernel fetch through the git
credential helper). If the app never answers the health path within 60 s the job fails
with the app's last 100 log lines; on any failure the full app log is uploaded as the
`app-log` artifact (7-day retention) under the run's Artifacts section.

```yaml
# .github/workflows/e2e.yml in any code repository
name: e2e
on:
  push: { branches: [main] }
  pull_request:
permissions: { contents: read }
concurrency: { group: e2e-${{ github.ref }}, cancel-in-progress: true }
jobs:
  fleet-e2e:
    uses: PalupGG/.github/.github/workflows/fleet-e2e.yml@<full-commit-sha>
    secrets: inherit
    with:
      postgres: true            # omit when the app needs no database
      postgres-env: DATABASE_URL
      app-port: 8080
      health-path: /healthz
      e2e-command: cargo test --test e2e
```

## Runner labels

Until the self-hosted pool exists, callers omit `runs-on` and jobs execute on GitHub-hosted
`ubuntu-latest` (metered minutes). When the cluster runner is live, the flip is one line per
caller: `with: { runs-on: "[self-hosted, sanctuary-ci]" }` — or a change of the default here.

## Rules that apply to this repository

- Only the reusable workflow and its runner manifest belong here; no product code ever lands
  in this repository.
- Third-party actions are pinned by full SHA; `permissions: contents: read` unless a job needs
  more.
- The FLEET_TOKEN secret never appears in a URL, a log, or this repository. A failed kernel
  fetch is an access problem to report, not to work around.

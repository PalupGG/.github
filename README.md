# SanctuaryGG/.github — the org CI backbone

Reusable workflows, called by every code repository, pinned by full SHA (fleet rule 5,
ADR-PLT-0010 #3). Documentation of the whole pipeline lives in
`SanctuaryGG/platform` → `docs/ci-cd.md` (ADR-PLT-0009 as amended by ADR-PLT-0013).

## What is here

| Path | What |
|---|---|
| `.github/workflows/fleet-ci.yml` | The reusable workflow: the five gates (boundary selftest, boundary gate — service or kernel role, `cargo fmt --check`, `cargo clippy -D warnings`, `cargo test`) on the pinned toolchain, with the `FLEET_TOKEN` kernel fetch wired through the git CLI credential helper — plus an opt-in `postgres:17-alpine` service for database-backed suites. |
| `.github/workflows/fleet-e2e.yml` | The application-level e2e workflow: builds the calling repo's crate, boots the real server (`cargo run`, background), waits for the health path, runs the repo's e2e suite against the live process — with the same `FLEET_TOKEN` wiring and `postgres:17-alpine` opt-in as fleet-ci. |
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

The SHA is bumped deliberately, in a PR, when the workflow changes — never a branch, never
a floating tag.

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
